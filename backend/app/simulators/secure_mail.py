from sqlalchemy import func, select

from app.assessment import assess_case
from app.documents import document_path
from app.domain import DomainError
from app.letter_emphasis import emphasis_spans, html_body
from app.models import AgentRun, Concern, Evidence, OutboxEntry, ResponseDraft, new_id
from app.response_validation import validate_response
from app.simulators.artifacts import digest
from app.simulators.common import checked_draft, row_data


def read(ctx, operation, reference_id=None):
    if operation == "csp.drafts":
        return {"drafts": [row_data(d) for d in ctx.rows(ResponseDraft)]}
    if operation == "csp.status":
        return {"outbox": row_data(ctx.scoped(OutboxEntry, reference_id))}
    entries = ctx.session.scalars(
        select(OutboxEntry)
        .join(ResponseDraft, OutboxEntry.draft_id == ResponseDraft.id)
        .where(ResponseDraft.case_id == ctx.case.id)
        .order_by(OutboxEntry.created_at)
    )
    return {"outbox": [row_data(e) for e in entries]}


def prepare(ctx, candidate):
    report = validate_response(ctx.session, ctx.data_dir, ctx.case.id, candidate)
    if not report.valid:
        raise DomainError(422, "response_invalid", "; ".join(f.message for f in report.findings))
    assessment, _ = assess_case(ctx.session, ctx.data_dir, ctx.case.id)
    concerns = {c.id: c for c in ctx.rows(Concern)}
    if any(concerns[c.concern_id].disposition != c.disposition for c in assessment.concerns):
        raise DomainError(
            409,
            "case_plan_required",
            "Record the supported concern plan before preparing a response.",
        )
    next_version = (
        ctx.session.scalar(
            select(func.max(ResponseDraft.version)).where(ResponseDraft.case_id == ctx.case.id)
        )
        or 0
    ) + 1
    if candidate.version != next_version:
        raise DomainError(
            409, "draft_version_conflict", f"The next draft version is {next_version}."
        )
    run = ctx.session.get(AgentRun, ctx.action.run_id) if ctx.action and ctx.action.run_id else None
    draft = ResponseDraft(
        case_id=ctx.case.id,
        version=candidate.version,
        case_revision=candidate.case_revision,
        response_type=candidate.response_type,
        body=report.rendered_body,
        recipient=candidate.recipient,
        evidence_versions=candidate.evidence_versions,
        attachment_ids=candidate.attachment_ids,
        disclosure_ids=candidate.disclosure_ids,
        validation={
            "candidate": candidate.model_dump(mode="json"),
            "input_hash": assessment.input_hash,
            "simulator_contract": 4,
            "review_required": bool(
                assessment.review_required
                or (run and run.checkpoint.get("mode") == "review_required")
            ),
            "report": report.model_dump(mode="json"),
        },
    )
    ctx.session.add(draft)
    return ctx.effect(draft, "draft")


def send(ctx, draft_id):
    draft = checked_draft(ctx, draft_id, require_approval=True)
    prior = ctx.session.scalar(select(OutboxEntry).where(OutboxEntry.draft_id == draft.id))
    if prior:
        return ctx.effect(
            ctx.scoped(OutboxEntry, prior.id), "outbox", {"outbox": row_data(prior), "reused": True}
        )
    identity = new_id()
    attachments = []
    for index, evidence_id in enumerate(draft.attachment_ids):
        evidence = ctx.scoped(Evidence, evidence_id)
        path = document_path(ctx.data_dir, evidence)
        content = path.read_bytes()
        key = ctx.write_file(f"sent-{identity}-{index}{path.suffix}", content)
        attachments.append(
            {
                "evidence_id": evidence.id,
                "version": evidence.version,
                "title": evidence.title,
                "storage_key": key,
                "sha256": digest(content),
                "media_type": evidence.details.get("media_type", "application/pdf"),
            }
        )
    sent = {
        "schema_version": 4,
        "draft_id": draft.id,
        "draft_version": draft.version,
        "case_revision": draft.case_revision,
        "body": draft.body,
        # Presentation only; the plain body above stays the checked, hashed content.
        "emphasis": emphasis_spans(draft.body),
        "html_body": html_body(draft.body),
        "recipient": draft.recipient,
        "attachment_ids": draft.attachment_ids,
        "attachments": attachments,
        "evidence_versions": draft.evidence_versions,
        "loan_identifier": ctx.loan.loan_identifier,
        "ccid": ctx.case.ccid,
        "simulation_id": ctx.simulation.id,
        "client_code": ctx.loan.client_code,
        "sender": ctx.loan.context["client_configuration"]["sender_email"],
    }
    entry = OutboxEntry(
        id=identity,
        action_id=ctx.action.id,
        draft_id=draft.id,
        status="sent",
        delivery_reference=f"DEMO-DELIVERY-{identity}",
        sent_content=sent,
    )
    ctx.session.add(entry)
    if draft.response_type == "final_resolution":
        ctx.case.status = "records_incomplete"
    ctx.bump()
    return ctx.effect(entry, "outbox")
