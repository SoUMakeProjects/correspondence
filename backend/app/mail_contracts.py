from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas import CaseRead, Contract, RunRead, Timestamp


class MailTemplate(Contract):
    key: str
    scenario: str
    title: str
    kind: Literal["initial", "reply"]
    sender: str
    recipient: str
    subject: str
    body: str
    attachments: list[dict]
    input_kind: str | None = None
    eft_intent: str | None = None


class MailSend(Contract):
    request_id: UUID
    template_key: str = Field(min_length=1, max_length=80)
    thread_id: UUID | None = None
    sender: str | None = Field(default=None, max_length=254)
    subject: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=12000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)
    excluded_attachment_keys: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def custom_envelope(self):
        import re

        if self.template_key == "CUSTOM" and self.thread_id:
            raise ValueError("A custom request starts a new conversation.")
        if self.template_key == "CUSTOM" or self.sender is not None:
            if not self.sender or not re.fullmatch(r"[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+", self.sender):
                raise ValueError("Enter a valid From email address.")
        if self.template_key == "CUSTOM" or self.subject is not None:
            if (
                not self.subject
                or not self.subject.strip()
                or any(c in self.subject for c in "\r\n")
            ):
                raise ValueError("Enter a subject on one line.")
        if self.template_key == "CUSTOM" or self.body is not None:
            if not self.body or not self.body.strip():
                raise ValueError("Enter a message body.")
        return self


class MailAttachmentRead(Contract):
    id: str
    title: str
    size_bytes: int
    page_count: int
    media_type: str = "application/pdf"


class IntakeResolution(Contract):
    request_id: UUID
    loan_identifier: str = Field(pattern=r"^0099[0-9]{6}$")
    request_type: Literal["name_change", "amortization", "tax", "bankruptcy", "eft", "other"]
    actor: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=10, max_length=2000)
    identity_verified: Literal[True]


class AutomationResume(Contract):
    request_id: UUID
    expected_revision: int = Field(ge=1)


class MailMessageRead(Contract):
    id: str
    thread_id: str
    template_key: str
    sender: str
    recipient: str
    subject: str
    body: str
    attachments: list[dict]
    status: str
    created_at: Timestamp


class ThreadRead(Contract):
    id: str
    case_id: str | None
    template_key: str
    subject: str
    created_at: Timestamp


class SignalRead(Contract):
    id: str
    case_id: str | None
    thread_id: str
    message_id: str | None
    kind: str
    status: str
    run_id: str | None
    detail: str
    created_at: Timestamp


class OperationsRead(Contract):
    cases: list[CaseRead]
    threads: list[ThreadRead]
    signals: list[SignalRead]
    runs: list[RunRead]
    review_case_ids: list[str]


class SystemCaseRead(Contract):
    case: CaseRead
    loan: dict
    evidence: list[dict]
    tasks: list[dict]
    specialist_results: list[dict]
    handoffs: list[dict]
    history: list[dict]
    packages: list[dict]
    notes: list[dict]
    outbox: list[dict]
    drafts: list[dict]
    runs: list[RunRead]
    events: list[dict]
    thread: ThreadRead | None
    signals: list[SignalRead]


class ThreadDetail(Contract):
    thread: ThreadRead
    messages: list[MailMessageRead]
    deliveries: list[dict]
    signals: list[SignalRead]
    reply_templates: list[MailTemplate]
