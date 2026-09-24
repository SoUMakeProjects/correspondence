from datetime import UTC
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    model_validator,
)

from app.domain import ActionStatus, CaseFamily, CaseStatus, RunStatus

Timestamp = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(UTC))]

Identifier = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=64)
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ErrorDetail(Contract):
    code: str
    message: str
    fields: list[str] = Field(default_factory=list)


class ErrorResponse(Contract):
    error: ErrorDetail


class HealthRead(Contract):
    status: Literal["ok"]
    database: Literal["connected"]
    schema_revision: str
    version: str


class ConfigurationRead(Contract):
    phase: Literal[9]
    environment: Literal["simulation"]
    model_provider: Literal["azure_openai"]
    azure_configuration_complete: bool
    missing_fields: list[str]
    model_connection_verified: bool
    azure_last_live_check: Timestamp | None = None
    model_calls_enabled: bool
    live_test_opt_in: bool
    agent_available: bool
    business_timezone: Literal["America/New_York"]
    message: str


class SimulationCreate(Contract):
    scenario_key: Identifier = "foundation"
    fixture_version: Identifier = "0"
    evaluation_at: Timestamp


class SimulationRead(SimulationCreate):
    id: UUID
    created_at: Timestamp
    variant: str


class CaseCreate(Contract):
    request_id: UUID
    simulation_id: UUID | None = None
    loan_identifier: Identifier
    ccid: Identifier
    client_code: Identifier
    borrower_display_name: ShortText
    balance_minor: Annotated[StrictInt, Field(ge=0, le=9_007_199_254_740_991)] = 0
    currency: Literal["USD"] = "USD"
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    correspondence_text: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)
    ]
    family: CaseFamily
    owner: ShortText = "Demo reviewer"
    original_received_at: Timestamp


class CaseRead(Contract):
    id: UUID
    simulation_id: UUID
    loan_id: UUID
    loan_identifier: str
    ccid: str
    client_code: str
    borrower_display_name: str
    balance_minor: int
    currency: str
    subject: str
    correspondence_text: str
    family: CaseFamily
    owner: str
    status: CaseStatus
    original_received_at: Timestamp
    created_at: Timestamp
    updated_at: Timestamp
    revision: int
    classification: dict | None
    content_revision: int
    routing: dict
    pending_work: list[dict]


class CaseList(Contract):
    items: list[CaseRead]
    total: int


class CasePatch(Contract):
    mutation_id: UUID
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    owner: ShortText | None = None
    status: CaseStatus | None = None

    @model_validator(mode="after")
    def meaningful_patch(self):
        changed = self.model_fields_set & {"owner", "status"}
        if not changed or any(getattr(self, name) is None for name in changed):
            raise ValueError("Supply a non-null owner or status to update.")
        return self


class EventRead(Contract):
    sequence: int
    case_id: UUID
    run_id: UUID | None
    action_id: UUID | None
    kind: str
    actor: str
    payload: dict
    created_at: Timestamp


class EventPage(Contract):
    items: list[EventRead]
    next_cursor: int


class EvidenceRead(Contract):
    id: UUID
    case_id: UUID
    title: str
    source: str
    source_reference: str
    version: int
    effective_at: Timestamp | None
    content_sha256: str | None
    synthetic: bool
    details: dict


RunFault = Literal[
    "none", "index_failure", "lost_send_response", "unknown_send_status", "lost_task_response"
]


class RunStart(Contract):
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    mode: Literal["automatic", "review_required"] = "automatic"
    resume_from: UUID | None = None
    fault: RunFault = "none"


class RunRead(Contract):
    id: UUID
    case_id: UUID
    case_revision: int
    status: RunStatus
    checkpoint: dict
    model_configuration: dict
    created_at: Timestamp
    updated_at: Timestamp


class ArtifactsRead(Contract):
    drafts: list[dict]
    outbox: list[dict]
    packages: list[dict]
    notes: list[dict]


class ReviewCreate(Contract):
    request_id: UUID = Field(default_factory=uuid4)
    actor: ShortText = "Demo reviewer"
    draft_id: UUID
    draft_version: Annotated[StrictInt, Field(ge=1)]
    expected_case_revision: Annotated[StrictInt, Field(ge=1)]
    decision: Literal["approve", "return"]
    note: Annotated[str, Field(max_length=4000)] = ""


class ReviewRead(Contract):
    id: UUID
    case_id: UUID
    draft_id: UUID
    draft_version: int
    case_revision: int
    actor: str
    decision: str
    note: str
    content_hash: str | None = None
    created_at: Timestamp


class ActionRead(Contract):
    id: UUID
    case_id: UUID
    run_id: UUID | None
    operation: str
    payload_version: int
    status: ActionStatus
    result: dict | None
    created_at: Timestamp


class SimulationInspection(Contract):
    simulation: SimulationRead
    case_count: int
    loan_count: int
    action_count: int
    outbox_count: int
    indexed_package_count: int
    note_count: int
    simulator_operations_available: Literal[True]
