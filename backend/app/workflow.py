"""Presenter inputs and version-bound review. No real borrower or servicing connectors."""

import hashlib
from copy import deepcopy

from pydantic import ValidationError
from sqlalchemy import select, text

from app.assessment import assess_case
from app.db import utcnow
from app.documents import library_document, render_document
from app.domain import DomainError
from app.fixture_contracts import DocumentFixture, FollowupFixture
from app.fixture_data import load_fixture
from app.letter_emphasis import emphasis_spans
from app.mail_templates import EFT_REPLIES
from app.models import (
    ActionReceipt,
    AgentRun,
    CaseEvent,
    Concern,
    CorrespondenceCase,
    Evidence,
    Loan,
    MailMessage,
    OutboxEntry,
    ResponseDraft,
    ReviewDecision,
    SimulationInstance,
    SpecialistHandoff,
    SpecialistTask,
    new_id,
)
from app.repository import case_read, fingerprint, require_case
from app.response_validation import validate_response
from app.routing import EASTERN
from app.rule_contracts import DraftCandidate
from app.simulators.common import row_data, scope
from app.source_catalog import DATA_ROOT, read_json

# Designee used by the diagnostic "authorized representative" input (any scenario).
REPRESENTATIVE = {
    "representative_name": "Elena M. Ruiz",
    "representative_firm": "Brightpath Housing Counseling",
    "firm_practice": "HUD-approved housing counseling agency",
    "representative_email": "elena.ruiz@brightpathhousing.example.org",
    "representative_phone": "(614) 555-0127",
    "firm_address": "455 Linden Avenue, Suite 2, Columbus, OH 43215",
    "acceptance_label": "Accepted by counselor:",
}


def current_draft(session, case_id):
    return session.scalar(
        select(ResponseDraft)
        .where(ResponseDraft.case_id == case_id)
        .order_by(ResponseDraft.version.desc())
    )


def latest_review(session, case_id):
    return session.scalar(
        select(ReviewDecision)
        .where(ReviewDecision.case_id == case_id)
        .order_by(ReviewDecision.created_at.desc(), ReviewDecision.id.desc())
    )


def draft_state(session, data_dir, draft, report=None):
    report = report or assess_case(session, data_dir, draft.case_id)[0]
    try:
        candidate = DraftCandidate.model_validate(draft.validation.get("candidate"))
        validation = validate_response(session, data_dir, draft.case_id, candidate)
        current = (
            validation.valid
            and draft.validation.get("input_hash") == report.input_hash
            and draft.version == candidate.version
            and draft.case_revision == candidate.case_revision
            and draft.body == validation.rendered_body
            and draft.recipient == candidate.recipient
            and draft.response_type == candidate.response_type
            and draft.disclosure_ids == candidate.disclosure_ids
            and draft.attachment_ids == candidate.attachment_ids
            and draft.evidence_versions == candidate.evidence_versions
        )
    except ValidationError:
        current, validation = False, None
    review = latest_review(session, draft.case_id)
    approved = bool(
        current
        and review
        and review.decision == "approve"
        and review.draft_id == draft.id
        and review.draft_version == draft.version
        and review.case_revision == draft.case_revision
        and review.content_hash
        == fingerprint(
            {"candidate": draft.validation["candidate"], "input_hash": report.input_hash}
        )
    )
    sent = (
        session.scalar(select(OutboxEntry.id).where(OutboxEntry.draft_id == draft.id)) is not None
    )
    return {
        "id": draft.id,
        "version": draft.version,
        "response_type": draft.response_type,
        "recipient": draft.recipient,
        "body": draft.body,
        "emphasis": emphasis_spans(draft.body),
        "candidate": draft.validation.get("candidate", {}),
        "current": current,
        "sent": sent,
        "approved": approved,
        "review_required": bool(
            report.review_required or draft.validation.get("review_required") or review
        ),
        "returned": bool(review and review.draft_id == draft.id and review.decision == "return"),
        "findings": [f.model_dump(mode="json") for f in validation.findings] if validation else [],
    }


def options(scenario):
    specific = {
        "DEMO-01": ["name_legal_document"],
        "DEMO-02": ["amortization_document"],
        "DEMO-03": ["tax_specialist_result"],
        "DEMO-04": ["bankruptcy_specialist_result"],
        "DEMO-05": ["eft_clarification"],
    }
    return specific.get(scenario, []) + [
        "authority_missing",
        "authorized_representative",
        "assignment_exception",
        "resolve_assignment",
        "additional_concern",
        "unrelated_contact",
    ]


def workspace(session, data_dir, case_id):
    case = require_case(session, case_id)
    simulation = session.get(SimulationInstance, case.simulation_id)
    report, _ = assess_case(session, data_dir, case_id)
    custom = session.get(Loan, case.loan_id).context.get("mail_intake")
    return {
        "case_id": case_id,
        "revision": case.revision,
        "scenario": simulation.scenario_key,
        "input_options": (["eft_clarification"] if simulation.scenario_key == "DEMO-05" else [])
        if custom
        else options(simulation.scenario_key),
        "pending_work": [
            c.model_dump(mode="json") for c in report.concerns if c.disposition != "resolved"
        ],
        "drafts": [
            draft_state(session, data_dir, d, report)
            for d in session.scalars(
                select(ResponseDraft)
                .where(ResponseDraft.case_id == case_id)
                .order_by(ResponseDraft.version)
            )
        ],
        "reviews": [
            row_data(r)
            for r in session.scalars(
                select(ReviewDecision)
                .where(ReviewDecision.case_id == case_id)
                .order_by(ReviewDecision.created_at)
            )
        ],
        "handoffs": [
            {**row_data(h), "current": h.input_hash == report.input_hash}
            for h in session.scalars(
                select(SpecialistHandoff)
                .where(SpecialistHandoff.case_id == case_id)
                .order_by(SpecialistHandoff.created_at)
            )
        ],
        "contacts": [
            row_data(e)
            for e in session.scalars(
                select(CaseEvent)
                .where(CaseEvent.case_id == case_id, CaseEvent.kind == "input.received")
                .order_by(CaseEvent.sequence)
            )
        ],
    }


def begin_mutation(
    session, data_dir, case_id, payload, operation, revision=None, *, recovery=False
):
    session.execute(text("BEGIN IMMEDIATE"))
    case = require_case(session, case_id)
    loan = session.get(Loan, case.loan_id)
    ctx = scope(
        session, data_dir, case.simulation_id, case_id, loan.loan_identifier, loan.client_code
    )
    value = payload.model_dump(mode="json")
    digest = fingerprint({"operation": operation, "case_id": case_id, "payload": value})
    prior = session.get(ActionReceipt, str(payload.request_id))
    if prior:
        if prior.case_id != case_id or prior.payload_hash != digest:
            raise DomainError(
                409, "request_id_reused", "This request identity belongs to different input."
            )
        return ctx, prior, True
    expected = revision if revision is not None else payload.expected_revision
    if case.revision != expected:
        raise DomainError(
            409, "stale_revision", "The case changed. Refresh before submitting input or review."
        )
    if case.status == "closed" and not recovery:
        raise DomainError(409, "case_closed", "Completed cases cannot accept new workflow input.")
    if session.scalar(
        select(AgentRun.id).where(
            AgentRun.case_id == case_id, AgentRun.status.in_(["running", "queued"])
        )
    ):
        raise DomainError(
            409, "run_active", "Stop or wait for the active run before changing its inputs."
        )
    if not recovery and session.scalar(
        select(ActionReceipt.id).where(
            ActionReceipt.case_id == case_id, ActionReceipt.status.in_(["uncertain", "in_progress"])
        )
    ):
        raise DomainError(
            409, "reconciliation_required", "Reconcile the uncertain action before changing inputs."
        )
    action = ActionReceipt(
        id=str(payload.request_id),
        case_id=case_id,
        operation=operation,
        idempotency_key=f"presenter:{payload.request_id}",
        payload_hash=digest,
        payload=value,
        payload_version=7,
        status="simulated_complete",
    )
    session.add(action)
    session.flush()
    return ctx, action, False


def save_mutation(ctx, action, kind, actor, result, event_payload):
    action.result = {"data": result}
    ctx.session.add(
        CaseEvent(
            case_id=ctx.case.id, action_id=action.id, kind=kind, actor=actor, payload=event_payload
        )
    )
    ctx.session.flush()
    from app.automation import enqueue_workflow

    enqueue_workflow(ctx.session, ctx.case.id, action.id, kind, event_payload)
    return result


def put_document(ctx, document, content, source):
    evidence = next((e for e in ctx.rows(Evidence) if e.details.get("key") == document.key), None)
    if evidence is None:
        evidence = Evidence(
            case_id=ctx.case.id,
            title=document.title,
            source="Presenter-supplied synthetic evidence",
            source_reference=source,
        )
        ctx.session.add(evidence)
        ctx.session.flush()
    else:
        evidence.version += 1
    evidence.title, evidence.source_reference = document.title, source
    evidence.effective_at = ctx.simulation.evaluation_at
    evidence.storage_key = ctx.write_file(f"input-{new_id()}.pdf", content)
    evidence.content_sha256 = hashlib.sha256(content).hexdigest()
    evidence.details = {
        "key": document.key,
        "kind": document.kind,
        "availability": "available",
        "loan_identifier": ctx.loan.loan_identifier,
        "client_code": ctx.loan.client_code,
        "ccid": ctx.case.ccid,
        "facts": document.facts,
    }
    return evidence


def refresh_loan_evidence(ctx):
    related = ctx.session.scalars(
        select(CorrespondenceCase).where(CorrespondenceCase.loan_id == ctx.loan.id)
    ).all()
    for case in related:
        for evidence in ctx.session.scalars(select(Evidence).where(Evidence.case_id == case.id)):
            if (
                evidence.details.get("kind") == "record"
                and evidence.details.get("origin") != "mail_reply"
            ):
                evidence.version += 1
                evidence.details = {**evidence.details, "facts": deepcopy(ctx.loan.context)}
        if case.id != ctx.case.id:
            case.revision += 1
            case.content_revision = case.revision
            case.updated_at = utcnow()


def ingest(session, data_dir, case_id, payload, *, mail_message_id=None):
    ctx = None
    try:
        with session.begin():
            ctx, action, prior = begin_mutation(
                session, data_dir, case_id, payload, "workflow.input"
            )
            if prior:
                return action.result["data"]
            scenario, kind = ctx.simulation.scenario_key, payload.kind
            mail = session.get(MailMessage, mail_message_id) if mail_message_id else None
            if ctx.loan.context.get("mail_intake") and kind not in {"eft_clarification"}:
                raise DomainError(
                    422,
                    "custom_evidence_required",
                    "This request requires case-specific evidence; prepared demo follow-ups cannot be applied to custom mail.",
                )
            if kind not in options(scenario):
                raise DomainError(
                    422,
                    "input_not_applicable",
                    "This input is not applicable to the selected case.",
                )
            before = {
                "context": deepcopy(ctx.loan.context),
                "evidence": [row_data(e) for e in ctx.rows(Evidence)],
                "original_received_at": ctx.case.original_received_at.isoformat(),
            }
            summary = kind.replace("_", " ")
            if kind in {
                "name_legal_document",
                "tax_specialist_result",
                "bankruptcy_specialist_result",
                "amortization_document",
            }:
                variant = "base" if kind == "amortization_document" else "followup"
                fixture = load_fixture(scenario, variant)
                followup = (
                    FollowupFixture.model_validate(
                        read_json(DATA_ROOT / "presenter/v1" / f"{scenario}.json")
                    )
                    if variant == "followup"
                    else None
                )
                documents = followup.documents if followup else fixture.documents
                for document in documents:
                    if mail and document.key not in {
                        a["key"] for a in mail.attachments if not a.get("upload_id")
                    }:
                        continue
                    _, content = library_document(scenario, variant, document.key)
                    put_document(ctx, document, content, f"presenter:v1/{scenario}/{document.key}")
                if kind in {"tax_specialist_result", "bankruptcy_specialist_result"}:
                    ctx.loan.context = {**ctx.loan.context, **followup.loan_context_patch}
                    by_key = {e.details.get("key"): e.id for e in ctx.rows(Evidence)}
                    for supplied in followup.tasks:
                        task = next(
                            (
                                t
                                for t in ctx.rows(SpecialistTask)
                                if t.request.get("fixture_key") == supplied.key
                            ),
                            None,
                        )
                        if not task:
                            raise DomainError(
                                409,
                                "specialist_task_missing",
                                "The supplied result requires its original scoped specialist task.",
                            )
                        task.status, task.result, task.pending_reason = (
                            supplied.status,
                            supplied.result,
                            supplied.pending_reason,
                        )
                        task.request = {
                            **task.request,
                            **supplied.request,
                            "evidence_ids": [by_key[k] for k in supplied.evidence_keys],
                            "result_source": "presenter_supplied_synthetic",
                        }
                summary = "Supplied synthetic evidence received; the agent must inspect it before continuing."
            elif kind in {"eft_clarification", "authorized_representative"}:
                fixture = load_fixture(scenario)
                if kind == "eft_clarification":
                    if payload.eft_intent is None:
                        raise DomainError(
                            422, "intent_required", "Select the clarified EFT purpose."
                        )
                    facts = {
                        "eft_intent": payload.eft_intent,
                        "signed_refund_consent_received": False,
                    }
                    ctx.loan.context = {
                        **ctx.loan.context,
                        "eft_intent": payload.eft_intent,
                        "refund_authorization": None,
                    }
                    title, key = "Borrower reply – EFT clarification", "clarification"
                    summary = f"The request concerns {payload.eft_intent.replace('_', ' ')}. No signed consent or banking instructions are supplied."
                    # The document is the borrower's own reply: the received email text, or the
                    # prepared reply for this meaning when the presenter supplies it directly.
                    reply = payload.text.strip() or EFT_REPLIES[payload.eft_intent][1]
                    facts.update(
                        reply_from=ctx.loan.context.get("authorized_recipient", ""),
                        reply_subject="Re: " + ctx.case.subject,
                    )
                    paragraphs = [p.strip() for p in reply.split("\n\n") if p.strip()]
                else:
                    if ctx.loan.context.get("communication_restriction") == "cease_and_desist":
                        raise DomainError(
                            409,
                            "cease_and_desist",
                            "Representative authorization does not reverse cease-and-desist restrictions.",
                        )
                    borrower = ctx.loan.borrower_display_name
                    facts = {
                        **REPRESENTATIVE,
                        "borrower_name": borrower,
                        "signed_date": ctx.simulation.evaluation_at.astimezone(EASTERN)
                        .date()
                        .isoformat(),
                        "authorized_role": "authorized_representative",
                        "authorization_verified": True,
                    }
                    ctx.loan.context = {
                        **ctx.loan.context,
                        "requester_role": "authorized_representative",
                        "authorized_recipient": facts["representative_email"],
                        "representative_name": facts["representative_name"],
                        "representative_firm": facts["representative_firm"],
                        "representation_verified": True,
                        "communication_restriction": "representative_only",
                        "ils_recipient": facts["representative_email"],
                        "csp_recipient": facts["representative_email"],
                    }
                    title, key = "Third-Party Authorization", "representation"
                    summary = (
                        f"{borrower}'s signed authorization designates "
                        f"{facts['representative_name']} ({facts['representative_firm']}, "
                        f"{facts['representative_email']}); communication is now "
                        "representative-only."
                    )
                    paragraphs = [
                        f"I, {borrower}, am the borrower on the mortgage loan identified above. I "
                        f"am working with {facts['representative_name']}, a HUD-approved housing "
                        f"counselor at {facts['representative_firm']}, on questions about this "
                        "loan.",
                        "I authorize my servicer to discuss this loan with my counselor, to "
                        "release to her any information about the loan that she requests, and "
                        "to send all correspondence about this loan to her at the email address "
                        "below.",
                        "This authorization remains in effect until I revoke it in writing.",
                    ]
                document = DocumentFixture(
                    key=key,
                    title=title,
                    availability="available",
                    kind="document",
                    paragraphs=paragraphs,
                    facts=facts,
                )
                put_document(
                    ctx,
                    document,
                    render_document(fixture, document, "presenter-input"),
                    f"presenter:v1/{scenario}/{kind}",
                )
            elif kind == "authority_missing":
                ctx.loan.context = {
                    **ctx.loan.context,
                    "requester_role": "authorized_representative",
                    "representation_verified": False,
                }
                for evidence in ctx.rows(Evidence):
                    if evidence.details.get("facts", {}).get("authorization_verified"):
                        evidence.version += 1
                        evidence.details = {
                            **evidence.details,
                            "facts": {**evidence.details["facts"], "authorization_verified": False},
                        }
            elif kind == "assignment_exception":
                identity = new_id()
                related = CorrespondenceCase(
                    loan_id=ctx.loan.id,
                    simulation_id=ctx.simulation.id,
                    creation_key=identity,
                    creation_hash=fingerprint({"id": identity}),
                    ccid="DEMO-RELATED-" + identity[:8],
                    subject="Related synthetic correspondence",
                    correspondence_text="An unrelated contact with a different assigned owner.",
                    family=ctx.case.family,
                    owner="Demo alternate owner",
                    original_received_at=ctx.case.original_received_at,
                )
                session.add(related)
            elif kind == "resolve_assignment":
                for case in session.scalars(
                    select(CorrespondenceCase).where(CorrespondenceCase.loan_id == ctx.loan.id)
                ):
                    if case.id != ctx.case.id:
                        case.owner = ctx.case.owner
            elif kind == "additional_concern":
                if not payload.text.strip():
                    raise DomainError(422, "concern_required", "Describe the additional concern.")
                session.add(
                    Concern(case_id=case_id, description=payload.text.strip(), evidence_ids=[])
                )
                summary = payload.text.strip()
            else:
                if not payload.text.strip():
                    raise DomainError(422, "contact_required", "Describe the unrelated contact.")
                summary = payload.text.strip()
            if mail:
                session.add(
                    Evidence(
                        case_id=case_id,
                        title=mail.subject,
                        source="Email",
                        source_reference=f"mail:{mail.id}",
                        effective_at=ctx.simulation.evaluation_at,
                        details={
                            "kind": "record",
                            "origin": "mail_reply",
                            "loan_identifier": ctx.loan.loan_identifier,
                            "ccid": ctx.case.ccid,
                            "client_code": ctx.loan.client_code,
                            "sender": mail.sender,
                            "received_at": mail.created_at.isoformat(),
                            "extracted_text": mail.body,
                            "facts": {},
                        },
                    )
                )
            refresh_loan_evidence(ctx)
            ctx.bump(material=True)
            ctx.case.status = "under_review"
            session.flush()
            result = case_read(session, ctx.case).model_dump(mode="json")
            action.payload = {**action.payload, "before": before}
            return save_mutation(
                ctx,
                action,
                "input.received",
                payload.actor,
                result,
                {
                    "kind": kind,
                    "text": summary,
                    "revision": ctx.case.revision,
                    "original_received_at": ctx.case.original_received_at.isoformat(),
                    "review_invalidated": True,
                },
            )
    except Exception:
        if ctx:
            for path in ctx.written:
                path.unlink(missing_ok=True)
        raise


def review_response(session, data_dir, case_id, payload):
    with session.begin():
        ctx, action, prior = begin_mutation(
            session, data_dir, case_id, payload, "workflow.review", payload.expected_case_revision
        )
        if prior:
            return action.result["data"]
        if payload.decision == "return" and not payload.note.strip():
            raise DomainError(
                422,
                "review_note_required",
                "Describe the changes needed before returning the response.",
            )
        draft = current_draft(session, case_id)
        if not draft or draft.id != str(payload.draft_id) or draft.version != payload.draft_version:
            raise DomainError(409, "stale_draft", "Review the latest prepared draft and version.")
        state = draft_state(session, data_dir, draft)
        if state["sent"]:
            raise DomainError(
                409, "already_sent", "Sent content is immutable; inspect its saved delivery."
            )
        if not state["current"]:
            raise DomainError(
                409,
                "stale_evidence",
                "Inputs changed. Prepare a current draft before reviewing it.",
            )
        report = assess_case(session, data_dir, case_id)[0]
        review = ReviewDecision(
            case_id=case_id,
            draft_id=draft.id,
            draft_version=draft.version,
            case_revision=ctx.case.content_revision,
            actor=payload.actor,
            decision=payload.decision,
            note=payload.note,
            content_hash=fingerprint(
                {"candidate": draft.validation["candidate"], "input_hash": report.input_hash}
            ),
        )
        session.add(review)
        ctx.bump()
        session.flush()
        return save_mutation(
            ctx,
            action,
            "response.reviewed",
            payload.actor,
            row_data(review),
            {
                "draft_id": draft.id,
                "version": draft.version,
                "decision": payload.decision,
                "note": payload.note,
                "evidence_versions": draft.evidence_versions,
            },
        )


def edit_response(session, data_dir, case_id, payload):
    from app.agent_tools import observe, prepare_request

    # Validation and mutation share this transaction. Revision and latest-draft
    # checks are carried in the candidate and expected_revision; no material edit is rebased.
    with session.begin():
        ctx, action, prior = begin_mutation(session, data_dir, case_id, payload, "workflow.edit")
        if prior:
            return action.result["data"]
        draft = current_draft(session, case_id)
        if not draft or draft.id != str(payload.draft_id) or draft.version != payload.draft_version:
            raise DomainError(409, "stale_draft", "Edit the current draft version.")
        if session.scalar(select(OutboxEntry.id).where(OutboxEntry.draft_id == draft.id)):
            raise DomainError(409, "already_sent", "The sent response cannot be edited.")
        observation = observe(session, data_dir, case_id)
        args = payload.model_dump(
            mode="json", include={"response_type", "concerns", "claims", "attachment_ids"}
        )
        request = prepare_request("csp.prepare", args, observation, str(payload.request_id))
        from app.simulators.secure_mail import prepare

        ctx.action = action
        effect = prepare(ctx, request.command.candidate)
        new_draft = session.get(ResponseDraft, effect["resource"]["id"])
        new_draft.validation = {
            **new_draft.validation,
            "review_required": True,
            "edited_from": draft.id,
        }
        ctx.bump()
        return save_mutation(
            ctx,
            action,
            "response.edited",
            payload.actor,
            effect,
            {
                "draft_id": new_draft.id,
                "version": new_draft.version,
                "previous_draft_id": draft.id,
                "approval_invalidated": True,
            },
        )


def acknowledge(session, data_dir, case_id, payload):
    with session.begin():
        ctx, action, prior = begin_mutation(
            session, data_dir, case_id, payload, "workflow.handoff_acknowledged"
        )
        if prior:
            return action.result["data"]
        handoff = ctx.scoped(SpecialistHandoff, payload.handoff_id)
        report = assess_case(session, data_dir, case_id)[0]
        if handoff.input_hash != report.input_hash:
            raise DomainError(
                409,
                "stale_handoff",
                "The case changed; prepare a current handoff before acknowledging it.",
            )
        handoff.status, handoff.acknowledged_by, handoff.acknowledged_at = (
            "acknowledged",
            payload.actor,
            utcnow(),
        )
        team = handoff.owner.removeprefix("Demo ")
        open_items = [c for c in handoff.concerns if c.get("disposition") != "resolved"]
        handoff.acknowledgment_note = (
            f"Received by {payload.actor} for the {team}. The {team} accepts ownership of "
            f"{len(open_items)} open item{'s' if len(open_items) != 1 else ''} in this referral; "
            "the case is transferred and stays open until they are resolved."
            + (
                " Restrictions remain in force: "
                + ", ".join(r.replace("_", " ") for r in handoff.restrictions)
                + "."
                if handoff.restrictions
                else ""
            )
        )
        ctx.case.status = "transferred"
        ctx.bump()
        return save_mutation(
            ctx,
            action,
            "handoff.acknowledged",
            payload.actor,
            row_data(handoff),
            {
                "handoff_id": handoff.id,
                "owner": handoff.owner,
                "route": handoff.route,
                "concerns": handoff.concerns,
                "restrictions": handoff.restrictions,
                "case_status": "transferred",
            },
        )
