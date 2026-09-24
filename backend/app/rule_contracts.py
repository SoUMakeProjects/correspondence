"""Contracts for deterministic preflight checks; no action execution authority."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictInt, StrictStr

from app.schemas import Contract, Timestamp

Disposition = Literal["resolved", "pending_borrower", "pending_department", "referred"]
ResponseType = Literal[
    "interim_acknowledgment", "information_request", "final_resolution", "referral", "repetitive"
]
Scalar = StrictStr | StrictInt | StrictBool | None


class Finding(Contract):
    code: str
    rule: str
    message: str
    blocks: list[Literal["response", "update", "closure", "ordinary_route"]] = Field(
        default_factory=list
    )
    evidence_ids: list[str] = Field(default_factory=list)


class AgingResult(Contract):
    original_received_at: str | None
    evaluation_at: str | None
    received_eastern_date: str | None = None
    evaluation_eastern_date: str | None = None
    workdays: int | None = None
    timezone: Literal["America/New_York"] = "America/New_York"
    calendar_version: Literal["eastern-mon-fri-v1"] = "eastern-mon-fri-v1"
    reason: str


class SpecialRoute(Contract):
    route: Literal["Legal", "Compliance", "Client specialist"]
    rule: str
    reason: str = Field(min_length=1)
    restrictions: list[Literal["no_work", "no_update", "no_contact"]] = Field(default_factory=list)


class RoutingInputs(Contract):
    assessment: Literal["inquiry", "dispute", "unassessed"] = "unassessed"
    channel: Literal["email", "chat", "call", "unknown"] = "unknown"
    queue: Literal["Inquiry", "Disputes", "Credit Reporting", "unknown"] = "unknown"
    assigned_team: str = "Inquiry"
    email_owners: list[str] = Field(default_factory=list)
    credit_error: bool = False
    modification_error: bool = False
    special_routes: list[SpecialRoute] = Field(default_factory=list)


class RoutingResult(Contract):
    route: str | None
    assessment: str
    rule: str
    reason: str
    restrictions: list[str]
    required_actions: list[str]
    findings: list[Finding]
    aging: AgingResult
    inputs: RoutingInputs


class ConcernPlan(Contract):
    concern_id: str
    description: str
    disposition: Disposition
    reason: str
    evidence_ids: list[str]
    owner: str | None = None
    next_review_at: Timestamp | None = None
    resume_requirement: str | None = None


class TaskPlan(Contract):
    task_id: str
    task_type: str
    action: Literal["reuse", "inspect_exception"]
    result_supported: bool
    reason: str


class AttachmentCheck(Contract):
    evidence_id: str
    title: str
    valid: bool
    code: str
    reason: str


class AssessmentReport(Contract):
    case_id: str
    case_revision: int
    policy_version: str
    evaluation_at: Timestamp
    input_hash: str
    evidence_versions: dict[str, int]
    client_version: int | None
    routing: RoutingResult
    classification: dict | None
    disposition: str
    review_required: bool
    authorized_recipient: str | None
    permitted_actions: list[str]
    findings: list[Finding]
    concerns: list[ConcernPlan]
    tasks: list[TaskPlan]
    attachments: list[AttachmentCheck]


class AssessmentCreate(Contract):
    request_id: UUID
    expected_revision: Annotated[StrictInt, Field(ge=1)]


class SavedAssessment(Contract):
    id: str
    created_at: Timestamp
    report: AssessmentReport


class FactualClaim(Contract):
    field: Literal[
        "loan_identifier",
        "tax_amount_minor",
        "tax_due_date",
        "tax_scheduled_date",
        "tax_status",
        "tax_bill_received_at",
        "tax_paid_at",
        "current_legal_name",
        "bankruptcy_status",
        "eft_intent",
        "task_completed",
        "document_attached",
    ]
    value: Scalar
    evidence_id: str


class ConcernResponse(Contract):
    concern_id: str
    disposition: Disposition


class DraftCandidate(Contract):
    case_revision: Annotated[StrictInt, Field(ge=1)]
    version: Annotated[StrictInt, Field(ge=1)] = 1
    response_type: ResponseType
    client_code: str
    client_version: Annotated[StrictInt, Field(ge=1)]
    sender: str
    recipient: str
    evidence_versions: dict[str, Annotated[StrictInt, Field(ge=1)]]
    attachment_ids: list[str] = Field(default_factory=list)
    disclosure_ids: list[str] = Field(default_factory=list)
    concerns: list[ConcernResponse]
    claims: list[FactualClaim] = Field(default_factory=list)
    body: str | None = Field(default=None, max_length=20000)


class ValidationReport(Contract):
    valid: bool
    policy_version: str
    findings: list[Finding]
    rendered_body: str
    response_type: ResponseType | None = None
    resulting_status: str
