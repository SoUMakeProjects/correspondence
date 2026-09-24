from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, utcnow


def new_id() -> str:
    return str(uuid4())


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class SimulationInstance(Identity, Base):
    __tablename__ = "simulation_instances"
    scenario_key: Mapped[str] = mapped_column(String(80))
    fixture_version: Mapped[str] = mapped_column(String(40))
    evaluation_at: Mapped[datetime] = mapped_column(UTCDateTime())
    variant: Mapped[str] = mapped_column(String(40), default="base", server_default="base")
    seed_key: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    seed_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Loan(Identity, Base):
    __tablename__ = "loans"
    __table_args__ = (
        UniqueConstraint("simulation_id", "loan_identifier"),
        UniqueConstraint("id", "simulation_id"),
        CheckConstraint("balance_minor >= 0", name="positive_balance"),
    )
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulation_instances.id"), index=True)
    loan_identifier: Mapped[str] = mapped_column(String(64))
    client_code: Mapped[str] = mapped_column(String(60))
    borrower_display_name: Mapped[str] = mapped_column(String(120))
    balance_minor: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    context: Mapped[dict] = mapped_column(JSON, default=dict)


class CorrespondenceCase(Identity, Base):
    __tablename__ = "cases"
    __table_args__ = (
        UniqueConstraint("simulation_id", "ccid"),
        ForeignKeyConstraint(["loan_id", "simulation_id"], ["loans.id", "loans.simulation_id"]),
        CheckConstraint("revision >= 1", name="positive_case_revision"),
    )
    loan_id: Mapped[str] = mapped_column(String(36), index=True)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulation_instances.id"), index=True)
    creation_key: Mapped[str] = mapped_column(String(36), unique=True)
    creation_hash: Mapped[str] = mapped_column(String(64))
    ccid: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(String(200))
    correspondence_text: Mapped[str] = mapped_column(Text)
    family: Mapped[str] = mapped_column(String(40))
    owner: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="queued")
    original_received_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    content_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    routing: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    pending_work: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    classification: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Concern(Identity, Base):
    __tablename__ = "concerns"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    disposition: Mapped[str] = mapped_column(String(40), default="unassessed")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)


class Evidence(Identity, Base):
    __tablename__ = "evidence"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(80))
    source_reference: Mapped[str] = mapped_column(String(300))
    version: Mapped[int] = mapped_column(Integer, default=1)
    effective_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    synthetic: Mapped[bool] = mapped_column(default=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")


class TaxonomyEntry(Base):
    __tablename__ = "taxonomy_entries"
    __table_args__ = (UniqueConstraint("work_type", "class_name", "subclass"),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    work_type: Mapped[str] = mapped_column(String(200))
    class_name: Mapped[str] = mapped_column(String(200))
    subclass: Mapped[str] = mapped_column(String(300))
    source_reference: Mapped[str] = mapped_column(String(300))


class SourceManifestEntry(Base):
    __tablename__ = "source_manifest_entries"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    row_number: Mapped[int] = mapped_column(Integer, unique=True)
    category: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(String(200))
    curated_item_keys: Mapped[list] = mapped_column(JSON, default=list)
    review_flags: Mapped[list] = mapped_column(JSON, default=list)


class ClientConfiguration(Base):
    __tablename__ = "client_configurations"
    code: Mapped[str] = mapped_column(String(60), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    display_name: Mapped[str] = mapped_column(String(120))
    settings: Mapped[dict] = mapped_column(JSON)


class KnowledgeItem(Identity, Base):
    __tablename__ = "knowledge_items"
    source_reference: Mapped[str] = mapped_column(String(300))
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40), default="requires_review")
    applicability: Mapped[dict] = mapped_column(JSON, default=dict)
    content: Mapped[str] = mapped_column(Text)


class SpecialistTask(Identity, Base):
    __tablename__ = "specialist_tasks"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(80))
    owner: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="prepared")
    pending_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_review_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    request: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AgentRun(Identity, Base):
    __tablename__ = "agent_runs"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    case_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    model_configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class ResponseDraft(Identity, Base):
    __tablename__ = "response_drafts"
    __table_args__ = (UniqueConstraint("case_id", "version"),)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    case_revision: Mapped[int] = mapped_column(Integer)
    response_type: Mapped[str] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text)
    recipient: Mapped[str] = mapped_column(String(254))
    evidence_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    attachment_ids: Mapped[list] = mapped_column(JSON, default=list)
    disclosure_ids: Mapped[list] = mapped_column(JSON, default=list)
    validation: Mapped[dict] = mapped_column(JSON, default=dict)


class ActionReceipt(Identity, Base):
    __tablename__ = "action_receipts"
    __table_args__ = (UniqueConstraint("case_id", "idempotency_key"),)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    operation: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    payload_hash: Mapped[str] = mapped_column(String(64))
    payload_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40), default="prepared")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ReviewDecision(Identity, Base):
    __tablename__ = "review_decisions"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("response_drafts.id"))
    draft_version: Mapped[int] = mapped_column(Integer)
    case_revision: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(120))
    decision: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class RuleEvaluation(Identity, Base):
    __tablename__ = "rule_evaluations"
    __table_args__ = (UniqueConstraint("case_id", "request_id"),)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    case_revision: Mapped[int] = mapped_column(Integer)
    policy_version: Mapped[str] = mapped_column(String(80))
    input_hash: Mapped[str] = mapped_column(String(64))
    inputs: Mapped[dict] = mapped_column(JSON)
    report: Mapped[dict] = mapped_column(JSON)


class OutboxEntry(Identity, Base):
    __tablename__ = "outbox_entries"
    action_id: Mapped[str] = mapped_column(ForeignKey("action_receipts.id"), unique=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("response_drafts.id"))
    status: Mapped[str] = mapped_column(String(40))
    delivery_reference: Mapped[str] = mapped_column(String(120), unique=True)
    sent_content: Mapped[dict] = mapped_column(JSON)


class IndexedPackage(Identity, Base):
    __tablename__ = "indexed_packages"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("action_receipts.id"), unique=True)
    storage_key: Mapped[str] = mapped_column(String(200))
    content_sha256: Mapped[str] = mapped_column(String(64))
    index_fields: Mapped[dict] = mapped_column(JSON)


class FinalNote(Identity, Base):
    __tablename__ = "final_notes"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("action_receipts.id"), unique=True)
    department: Mapped[str] = mapped_column(String(80))
    note_type: Mapped[str] = mapped_column(String(80))
    content: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")


class ServicingHistory(Identity, Base):
    __tablename__ = "servicing_history"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    loan_id: Mapped[str] = mapped_column(ForeignKey("loans.id"), index=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("action_receipts.id"), unique=True)
    operation: Mapped[str] = mapped_column(String(80))
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON)


class CaseEvent(Base):
    __tablename__ = "case_events"
    __table_args__ = {"sqlite_autoincrement": True}
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    action_id: Mapped[str | None] = mapped_column(ForeignKey("action_receipts.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(80))
    actor: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class SpecialistHandoff(Identity, Base):
    __tablename__ = "specialist_handoffs"
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("action_receipts.id"), unique=True)
    route: Mapped[str] = mapped_column(String(120))
    owner: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="requested")
    input_hash: Mapped[str] = mapped_column(String(64))
    evidence_versions: Mapped[dict] = mapped_column(JSON)
    concerns: Mapped[list] = mapped_column(JSON)
    restrictions: Mapped[list] = mapped_column(JSON)
    acknowledged_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class MailThread(Identity, Base):
    __tablename__ = "mail_threads"
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), unique=True, nullable=True)
    template_key: Mapped[str] = mapped_column(String(80))
    subject: Mapped[str] = mapped_column(String(200))


class MailMessage(Identity, Base):
    __tablename__ = "mail_messages"
    thread_id: Mapped[str] = mapped_column(ForeignKey("mail_threads.id"), index=True)
    template_key: Mapped[str] = mapped_column(String(80))
    sender: Mapped[str] = mapped_column(String(254))
    recipient: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40), default="received")


class MailAttachment(Identity, Base):
    __tablename__ = "mail_attachments"
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("mail_messages.id"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(200))
    content_sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int] = mapped_column(Integer)
    media_type: Mapped[str] = mapped_column(String(40), default="application/pdf")
    extracted_text: Mapped[str] = mapped_column(Text)


class AutomationSignal(Identity, Base):
    __tablename__ = "automation_signals"
    event_key: Mapped[str] = mapped_column(String(120), unique=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("mail_threads.id"), index=True)
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id"), nullable=True, index=True)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("mail_messages.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    detail: Mapped[str] = mapped_column(Text, default="Message received; awaiting processing.")
