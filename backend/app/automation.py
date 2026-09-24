"""Durable, idempotent email intake and event-driven agent scheduling."""

import logging
import threading
from uuid import UUID

from sqlalchemy import select, text

from app.agent import ACTIVE, start
from app.domain import DomainError
from app.mail_content import uses_custom_intake
from app.mail_templates import templates
from app.models import (
    ActionReceipt,
    AgentRun,
    AutomationSignal,
    CaseEvent,
    CorrespondenceCase,
    Evidence,
    Loan,
    MailMessage,
    MailThread,
)
from app.schemas import RunStart
from app.seeding import seed_scenario
from app.workflow_contracts import CaseInput

logger = logging.getLogger(__name__)


def enqueue_workflow(session, case_id, action_id, kind, payload):
    """Called inside the same transaction as a successful human intervention."""
    if kind not in {"input.received", "response.reviewed", "handoff.acknowledged"}:
        return
    if kind == "input.received" and payload.get("kind") == "unrelated_contact":
        return
    thread = session.scalar(select(MailThread).where(MailThread.case_id == case_id))
    if not thread or session.get(MailMessage, action_id):
        return
    key = f"workflow:{action_id}"
    if not session.scalar(select(AutomationSignal.id).where(AutomationSignal.event_key == key)):
        session.add(
            AutomationSignal(
                event_key=key,
                thread_id=thread.id,
                case_id=case_id,
                kind=kind,
                status="ready",
                detail="Case updated; agent continuation queued.",
            )
        )


class AutomationWorker:
    def __init__(self, settings, sessions, agent_worker):
        self.settings, self.sessions, self.agent_worker = settings, sessions, agent_worker
        self.halt = threading.Event()
        self.wake = threading.Event()
        self.thread = None

    def launch(self):
        self.thread = threading.Thread(target=self.loop, name="mailbox-intake", daemon=True)
        self.thread.start()

    def shutdown(self):
        self.halt.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=15)

    def loop(self):
        while not self.halt.is_set():
            try:
                self.run_once()
            except Exception as exc:
                logger.error("Mailbox processing deferred (%s).", type(exc).__name__)
            self.wake.wait(0.75)
            self.wake.clear()

    def run_once(self):
        # Intake all currently available messages before scheduling continuation,
        # so new evidence supersedes an older approval before the next run starts.
        for status, handler in (("pending", self.apply_message), ("ready", self.dispatch)):
            with self.sessions() as session:
                ids = list(
                    session.scalars(
                        select(AutomationSignal.id)
                        .where(AutomationSignal.status == status)
                        .order_by(AutomationSignal.created_at, AutomationSignal.id)
                    )
                )
            for identity in ids:
                if self.halt.is_set():
                    return
                try:
                    handler(identity)
                except DomainError as exc:
                    transient = exc.code in {
                        "run_active",
                        "stale_revision",
                        "azure_not_configured",
                        "reconciliation_required",
                        "automation_paused",
                        "mail_pending",
                    }
                    self.defer(
                        identity,
                        exc.message,
                        failed=not transient,
                        reset_input=exc.code == "stale_revision",
                    )

    def defer(self, identity, detail, *, failed=False, reset_input=False):
        with self.sessions() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            signal = session.get(AutomationSignal, identity)
            if signal.status not in {"pending", "ready"}:
                return
            signal.detail = detail
            if (
                reset_input
                and signal.status == "pending"
                and signal.message_id
                and not session.get(ActionReceipt, signal.message_id)
            ):
                signal.input_payload = {}
            if failed:
                signal.status = "blocked"
                if signal.message_id:
                    session.get(MailMessage, signal.message_id).status = "needs_attention"
            session.commit()

    def latest_run(self, session, case_id):
        return session.scalar(
            select(AgentRun)
            .where(AgentRun.case_id == case_id)
            .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        )

    def check_idle(self, session, case_id):
        latest = self.latest_run(session, case_id)
        if latest and latest.status in ACTIVE:
            raise DomainError(409, "run_active", "Message saved; waiting for the active run.")
        resume_requested = session.scalar(
            select(AutomationSignal.id).where(
                AutomationSignal.case_id == case_id,
                AutomationSignal.kind == "operator.resume",
                AutomationSignal.status == "ready",
            )
        )
        if latest and latest.status == "stopped" and not resume_requested:
            raise DomainError(
                409, "automation_paused", "Automation was stopped. Resume the agent to continue."
            )

    def apply_message(self, identity):
        with self.sessions() as session:
            signal = session.get(AutomationSignal, identity)
            if signal.status != "pending":
                return
            message = session.get(MailMessage, signal.message_id)
            thread = session.get(MailThread, message.thread_id)
            custom = uses_custom_intake(message)
        if custom:
            from app.custom_intake import receive_custom

            case_id = receive_custom(self, identity)
            if case_id:
                self.mark_received(identity, case_id)
            return
        with self.sessions() as session:
            message = session.get(MailMessage, signal.message_id)
            thread = session.get(MailThread, message.thread_id)
            template = next(t for t in templates() if t.key == message.template_key)
            case_id, message_id = thread.case_id, message.id
            if case_id:
                self.check_idle(session, case_id)
        if template.kind == "initial":
            with self.sessions() as session:
                case = seed_scenario(
                    session, self.settings, template.scenario, "base", UUID(message_id)
                )
                case_id = str(case.id)
        else:
            if not case_id:
                return  # The original message is still being received.
            with self.sessions() as session:
                case = session.get(CorrespondenceCase, case_id)
                loan = session.get(Loan, case.loan_id)
                from app.mail_replies import reply_intent

                intent = (
                    signal.input_payload.get("eft_intent")
                    if signal.input_payload
                    else reply_intent(self, message, template, loan)
                )
            with self.sessions() as session:
                session.execute(text("BEGIN IMMEDIATE"))
                signal = session.get(AutomationSignal, identity)
                if signal.status != "pending":
                    return
                if not signal.input_payload:
                    case = session.get(CorrespondenceCase, case_id)
                    signal.input_payload = CaseInput(
                        request_id=UUID(message_id),
                        expected_revision=case.revision,
                        actor=message.sender,
                        kind=template.input_kind,
                        eft_intent=intent,
                        text=message.body,
                    ).model_dump(mode="json")
                payload = dict(signal.input_payload)
                session.commit()
            from app.workflow import ingest

            with self.sessions() as session:
                ingest(
                    session,
                    self.settings.data_dir,
                    case_id,
                    CaseInput.model_validate(payload),
                    mail_message_id=message_id,
                )
        self.mark_received(identity, case_id)

    def mark_received(self, identity, case_id):
        with self.sessions() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            signal = session.get(AutomationSignal, identity)
            if signal.status != "pending":
                return
            thread = session.get(MailThread, signal.thread_id)
            message = session.get(MailMessage, signal.message_id)
            thread.case_id = case_id
            from app.mail_attachments import import_prepared_mail, import_uploads

            import_uploads(session, message, case_id)
            if uses_custom_intake(message):
                import_prepared_mail(session, message, case_id, self.settings.data_dir)
            evidence = {
                e.details.get("key"): e
                for e in session.scalars(select(Evidence).where(Evidence.case_id == case_id))
            }
            message.attachments = [
                {**a, "evidence_id": evidence[a["key"]].id} if a["key"] in evidence else a
                for a in message.attachments
            ]
            message.status = "processed"
            signal.case_id, signal.status = case_id, "ready"
            signal.detail = "Message linked to case; agent continuation queued."
            session.add(
                CaseEvent(
                    case_id=case_id,
                    kind="mail.received",
                    actor=message.sender,
                    payload={
                        "message_id": message.id,
                        "thread_id": thread.id,
                        "subject": message.subject,
                        "template_key": message.template_key,
                    },
                )
            )
            session.commit()

    def dispatch(self, identity):
        with self.sessions() as session:
            signal = session.get(AutomationSignal, identity)
            if signal.status != "ready":
                return
            case_id = signal.case_id
            self.check_idle(session, case_id)
            # Pending/blocked inbound evidence must not be bypassed by an approval.
            if session.scalar(
                select(AutomationSignal.id).where(
                    AutomationSignal.thread_id == signal.thread_id,
                    AutomationSignal.status.in_(["pending", "blocked"]),
                )
            ):
                return
            case = session.get(CorrespondenceCase, case_id)
            if case.status == "closed":
                signal.status, signal.detail = "handled", "Case is already complete."
                session.commit()
                return
            previous = self.latest_run(session, case_id)
            payload = RunStart(
                expected_revision=case.revision,
                resume_from=UUID(previous.id)
                if previous
                and previous.status
                in {
                    "waiting_for_input",
                    "waiting_for_review",
                    "failed",
                    "stopped",
                }
                else None,
            )
        with self.sessions() as session:
            start(
                session,
                self.settings,
                case_id,
                payload,
                self.agent_worker.model.source,
                trigger_id=identity,
            )
        self.agent_worker.wake.set()
