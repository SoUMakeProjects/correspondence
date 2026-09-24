"""Built-in mailbox and connected system views over the same persisted records."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.agent import ACTIVE
from app.agent_tools import artifacts
from app.db import get_session
from app.domain import DomainError
from app.fixture_data import load_fixture
from app.mail_attachments import bind_uploads, upload_response
from app.mail_attachments import router as attachments_router
from app.mail_content import uses_custom_intake
from app.mail_contracts import (
    AutomationResume,
    IntakeResolution,
    MailMessageRead,
    MailSend,
    MailTemplate,
    OperationsRead,
    SignalRead,
    SystemCaseRead,
    ThreadDetail,
)
from app.mail_templates import SERVICE_ADDRESS, templates
from app.models import (
    AgentRun,
    AutomationSignal,
    CaseEvent,
    CorrespondenceCase,
    Evidence,
    Loan,
    MailAttachment,
    MailMessage,
    MailThread,
    OutboxEntry,
    ResponseDraft,
    ServicingHistory,
    SimulationInstance,
    SpecialistHandoff,
    SpecialistTask,
)
from app.repository import case_read, fingerprint, require_case
from app.schemas import RunRead
from app.simulators.common import row_data
from app.workflow import workspace

router = APIRouter(prefix="/api", tags=["Mailbox and system workspaces"])
router.include_router(attachments_router)
SessionDep = Annotated[Session, Depends(get_session)]


def template_file(template_key, attachment_key):
    from app.documents import library_document

    template = next((t for t in templates() if t.key == template_key), None)
    if not template or not any(a["key"] == attachment_key for a in template.attachments):
        raise DomainError(404, "attachment_not_found", "Attachment not found in this message.")
    variant = "followup" if template.key == "name-proof" else "base"
    _, content = library_document(template.scenario, variant, attachment_key)
    if content is None:
        raise DomainError(404, "attachment_not_found", "This attachment is unavailable.")
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{attachment_key}.pdf"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/mail/templates/{template_key}/attachments/{attachment_key}")
def preview_template(template_key: str, attachment_key: str):
    return template_file(template_key, attachment_key)


@router.get("/mail/messages/{message_id}/attachments/{index}")
def preview_message(message_id: UUID, index: int, request: Request, session: SessionDep):
    message = session.get(MailMessage, str(message_id))
    if not message or not 0 <= index < len(message.attachments):
        raise DomainError(404, "attachment_not_found", "Attachment not found in this message.")
    attachment = message.attachments[index]
    if attachment.get("upload_id"):
        row = session.get(MailAttachment, attachment["upload_id"])
        if not row or row.message_id != message.id:
            raise DomainError(404, "attachment_not_found", "Attachment not found in this message.")
        return upload_response(row, request.app.state.settings.data_dir)
    return template_file(message.template_key, attachment["key"])


@router.get("/mail/deliveries/{delivery_id}/attachments/{index}")
def preview_delivery(delivery_id: UUID, index: int, request: Request, session: SessionDep):
    from app.simulators.artifacts import verified_file

    delivery = session.get(OutboxEntry, str(delivery_id))
    attachments = delivery.sent_content.get("attachments", []) if delivery else []
    if not 0 <= index < len(attachments):
        raise DomainError(404, "attachment_not_found", "Attachment not found in this delivery.")
    attachment = attachments[index]
    media_type = attachment.get("media_type", "application/pdf")
    path = verified_file(
        request.app.state.settings.data_dir,
        attachment["storage_key"],
        attachment["sha256"],
        pdf=media_type == "application/pdf",
    )
    return FileResponse(
        path,
        media_type=media_type,
        filename=f"attachment{path.suffix}",
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/mail/intake-reviews")
def intake_reviews(session: SessionDep):
    from app.custom_intake import record_catalog

    signals = session.scalars(
        select(AutomationSignal)
        .join(MailMessage, MailMessage.id == AutomationSignal.message_id)
        .where(
            AutomationSignal.status == "blocked",
            AutomationSignal.case_id.is_(None),
        )
        .order_by(AutomationSignal.created_at)
    ).all()
    return {
        "reviews": [
            {
                "signal_id": s.id,
                "detail": s.detail,
                "classification": s.input_payload.get("classification"),
                "message": MailMessageRead.model_validate(
                    session.get(MailMessage, s.message_id)
                ).model_dump(mode="json"),
            }
            for s in signals
            if uses_custom_intake(session.get(MailMessage, s.message_id))
        ],
        "loans": [
            {
                "id": r.loan_identifier,
                "borrower": r.borrower_display_name,
                "recipient": r.loan_context.get("authorized_recipient", r.borrower_email),
            }
            for r in record_catalog()
        ],
    }


def require_intake(session, identity):
    signal = session.get(AutomationSignal, str(identity))
    message = session.get(MailMessage, signal.message_id) if signal else None
    if not message or not uses_custom_intake(message) or signal.case_id:
        raise DomainError(404, "intake_not_found", "Pending custom intake not found.")
    return signal, message


@router.post("/mail/intake/{signal_id}/retry", response_model=SignalRead)
def retry_intake(signal_id: UUID, request: Request, session: SessionDep):
    session.execute(text("BEGIN IMMEDIATE"))
    signal, message = require_intake(session, signal_id)
    if signal.status != "blocked":
        return signal
    signal.status, message.status = "pending", "received"
    signal.detail = "Classification retry queued."
    session.commit()
    request.app.state.automation_worker.wake.set()
    return signal


@router.post("/mail/intake/{signal_id}/resolve", response_model=SignalRead)
def resolve_intake(
    signal_id: UUID, payload: IntakeResolution, request: Request, session: SessionDep
):
    from app.custom_intake import record_catalog

    session.execute(text("BEGIN IMMEDIATE"))
    submitted = payload.model_dump(mode="json")
    previous = session.get(AutomationSignal, str(signal_id))
    if previous and previous.input_payload.get("resolution") == submitted:
        return previous
    signal, message = require_intake(session, signal_id)
    if signal.status != "blocked":
        raise DomainError(409, "intake_processing", "This request is already being processed.")
    if payload.loan_identifier not in {r.loan_identifier for r in record_catalog()}:
        raise DomainError(422, "unknown_loan", "Choose a loan from the servicing records.")
    classification = signal.input_payload.get("classification") or {
        "request_type": payload.request_type,
        "certain": True,
        "loan_identifiers": [],
        "concern_quotes": [message.body],
        "requested_name": None,
        "eft_intent": None,
    }
    signal.input_payload = {
        **signal.input_payload,
        "classification": classification,
        "resolution": submitted,
    }
    signal.status, message.status = "pending", "received"
    signal.detail = "Identity reviewed; agent processing queued."
    session.commit()
    request.app.state.automation_worker.wake.set()
    return signal


@router.post("/automation/cases/{case_id}/resume", response_model=SignalRead, status_code=202)
def resume_processing(
    case_id: UUID, payload: AutomationResume, request: Request, session: SessionDep
):
    session.execute(text("BEGIN IMMEDIATE"))
    key = f"resume:{payload.request_id}"
    submitted = payload.model_dump(mode="json")
    prior = session.scalar(select(AutomationSignal).where(AutomationSignal.event_key == key))
    if prior:
        if prior.case_id != str(case_id) or prior.input_payload != submitted:
            raise DomainError(
                409, "request_id_reused", "This request ID belongs to another continuation."
            )
        return prior
    case = require_case(session, str(case_id))
    thread = session.scalar(select(MailThread).where(MailThread.case_id == case.id))
    if not thread:
        raise DomainError(409, "mailbox_required", "Use the earlier case controls for this case.")
    if case.revision != payload.expected_revision:
        raise DomainError(409, "stale_revision", "The case changed. Refresh before continuing.")
    if case.status == "closed":
        raise DomainError(409, "case_closed", "This case is already complete.")
    if session.scalar(
        select(AgentRun.id).where(AgentRun.case_id == case.id, AgentRun.status.in_(ACTIVE))
    ):
        raise DomainError(409, "run_active", "This case already has a queued or running agent.")
    signal = AutomationSignal(
        event_key=key,
        thread_id=thread.id,
        case_id=case.id,
        kind="operator.resume",
        status="ready",
        input_payload=submitted,
        detail="Continuation requested. Pending mail will be processed first.",
    )
    session.add(signal)
    session.commit()
    request.app.state.automation_worker.wake.set()
    return signal


@router.get("/mail/templates", response_model=list[MailTemplate])
def mail_templates():
    return templates()


@router.post("/mail/messages", response_model=MailMessageRead, status_code=202)
def send_message(payload: MailSend, request: Request, session: SessionDep):
    identity = str(payload.request_id)
    submitted = payload.model_dump(mode="json")
    if not payload.attachment_ids:
        submitted.pop("attachment_ids")
    if not payload.excluded_attachment_keys:
        submitted.pop("excluded_attachment_keys")
    digest = fingerprint(submitted)
    session.execute(text("BEGIN IMMEDIATE"))
    prior = session.get(MailMessage, identity)
    if prior:
        if prior.request_hash != digest:
            raise DomainError(
                409, "message_id_reused", "This message ID belongs to a different message."
            )
        return prior
    template = next((t for t in templates() if t.key == payload.template_key), None)
    if payload.template_key == "CUSTOM":
        template = MailTemplate(
            key="CUSTOM",
            scenario="CUSTOM",
            title="Custom",
            kind="initial",
            sender=payload.sender,
            recipient=SERVICE_ADDRESS,
            subject=payload.subject,
            body=payload.body,
            attachments=[],
        )
    if not template:
        raise DomainError(422, "template_unknown", "Choose an available message template.")
    excluded = set(payload.excluded_attachment_keys)
    if len(excluded) != len(payload.excluded_attachment_keys) or not excluded.issubset(
        {a["key"] for a in template.attachments}
    ):
        raise DomainError(
            422, "attachment_selection_invalid", "This attachment does not belong to the draft."
        )
    subject = (
        payload.subject
        if payload.subject is not None
        else ("Re: " if template.kind == "reply" else "") + template.subject
    )
    if template.kind == "initial":
        if payload.thread_id:
            raise DomainError(
                422, "new_thread_required", "An initial request starts a new conversation."
            )
        thread = MailThread(id=identity, template_key=template.key, subject=subject)
        session.add(thread)
        session.flush()
    else:
        thread = session.get(MailThread, str(payload.thread_id)) if payload.thread_id else None
        if not thread or thread.template_key != template.scenario:
            raise DomainError(
                422,
                "reply_scope_mismatch",
                "This reply does not belong to the selected conversation.",
            )
        if thread.case_id and require_case(session, thread.case_id).status == "closed":
            raise DomainError(
                409, "case_closed", "This case is complete. Send a new request for a new case."
            )
    message = MailMessage(
        id=identity,
        thread_id=thread.id,
        template_key=template.key,
        sender=payload.sender if payload.sender is not None else template.sender,
        recipient=template.recipient,
        subject=subject,
        body=payload.body if payload.body is not None else template.body,
        attachments=[a for a in template.attachments if a["key"] not in excluded],
        request_hash=digest,
    )
    session.add(message)
    session.flush()
    bind_uploads(session, message, payload.attachment_ids, request.app.state.settings.data_dir)
    if template.kind == "initial" and uses_custom_intake(message):
        thread.template_key = "CUSTOM"
    session.add(
        AutomationSignal(
            event_key=f"mail:{identity}",
            thread_id=thread.id,
            message_id=identity,
            case_id=thread.case_id,
            kind="mail.received",
            status="pending",
        )
    )
    session.commit()
    request.app.state.automation_worker.wake.set()
    return message


@router.get("/mail/threads/{thread_id}", response_model=ThreadDetail)
def thread_detail(thread_id: UUID, session: SessionDep):
    thread = session.get(MailThread, str(thread_id))
    if not thread:
        raise DomainError(404, "thread_not_found", "Conversation not found.")
    closed = bool(thread.case_id and require_case(session, thread.case_id).status == "closed")
    deliveries = (
        list(
            session.scalars(
                select(OutboxEntry)
                .join(ResponseDraft, OutboxEntry.draft_id == ResponseDraft.id)
                .where(ResponseDraft.case_id == thread.case_id)
                .order_by(OutboxEntry.created_at)
            )
        )
        if thread.case_id
        else []
    )
    return {
        "thread": thread,
        "messages": list(
            session.scalars(
                select(MailMessage)
                .where(MailMessage.thread_id == thread.id)
                .order_by(MailMessage.created_at, MailMessage.id)
            )
        ),
        "deliveries": [row_data(e) for e in deliveries],
        "signals": list(
            session.scalars(
                select(AutomationSignal)
                .where(AutomationSignal.thread_id == thread.id)
                .order_by(AutomationSignal.created_at, AutomationSignal.id)
            )
        ),
        "reply_templates": [
            t
            for t in templates()
            if not closed and t.kind == "reply" and t.scenario == thread.template_key
        ],
    }


@router.get("/operations", response_model=OperationsRead)
def operations(request: Request, session: SessionDep):
    cases = list(
        session.scalars(
            select(CorrespondenceCase).order_by(CorrespondenceCase.created_at.desc()).limit(200)
        )
    )
    ids = [c.id for c in cases]
    runs = list(
        session.scalars(
            select(AgentRun)
            .where(AgentRun.case_id.in_(ids))
            .order_by(AgentRun.created_at, AgentRun.id)
        )
    )
    candidate_ids = set(
        session.scalars(select(ResponseDraft.case_id).where(ResponseDraft.case_id.in_(ids)))
    )
    candidate_ids.update(
        session.scalars(
            select(SpecialistHandoff.case_id).where(
                SpecialistHandoff.case_id.in_(ids),
                SpecialistHandoff.status == "requested",
            )
        )
    )
    managed_ids = set(session.scalars(select(MailThread.case_id)))
    review_ids = []
    for case in cases:
        if case.id not in candidate_ids or case.id not in managed_ids or case.status == "closed":
            continue
        state = workspace(session, request.app.state.settings.data_dir, case.id)
        latest = state["drafts"][-1] if state["drafts"] else None
        if (
            latest
            and latest["current"]
            and not latest["sent"]
            and latest["review_required"]
            and not latest["approved"]
        ) or any(h["current"] and h["status"] == "requested" for h in state["handoffs"]):
            review_ids.append(case.id)
    return {
        "cases": [case_read(session, case) for case in cases],
        "threads": list(
            session.scalars(select(MailThread).order_by(MailThread.created_at.desc()).limit(200))
        ),
        "signals": list(
            session.scalars(
                select(AutomationSignal).order_by(AutomationSignal.created_at.desc()).limit(500)
            )
        ),
        "runs": [RunRead.model_validate(run) for run in runs],
        "review_case_ids": review_ids,
    }


@router.get("/systems/cases/{case_id}", response_model=SystemCaseRead)
def system_case(case_id: UUID, session: SessionDep):
    case = require_case(session, str(case_id))
    saved = artifacts(session, case.id)
    scenario = session.get(SimulationInstance, case.simulation_id).scenario_key
    specialist_results = []
    if scenario in {"DEMO-03", "DEMO-04"} and not session.get(Loan, case.loan_id).context.get(
        "mail_intake"
    ):
        specialist_results = [
            t.model_dump(mode="json") for t in load_fixture(scenario, "followup").tasks
        ]

    def records(model):
        return list(
            session.scalars(
                select(model).where(model.case_id == case.id).order_by(model.created_at)
            )
        )

    return {
        "case": case_read(session, case),
        "loan": row_data(session.get(Loan, case.loan_id)),
        "evidence": [row_data(e) for e in records(Evidence)],
        "tasks": [row_data(t) for t in records(SpecialistTask)],
        "specialist_results": specialist_results,
        "handoffs": [row_data(h) for h in records(SpecialistHandoff)],
        "history": [row_data(h) for h in records(ServicingHistory)],
        **saved,
        "runs": [RunRead.model_validate(r) for r in records(AgentRun)],
        "events": [row_data(e) for e in records(CaseEvent)],
        "thread": session.scalar(select(MailThread).where(MailThread.case_id == case.id)),
        "signals": records(AutomationSignal),
    }
