from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictInt

from app.agent_contracts import PrepareResponse
from app.schemas import Contract, ShortText


class PresenterMutation(Contract):
    request_id: UUID
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    actor: ShortText = "Demo reviewer"


class CaseInput(PresenterMutation):
    actor: str = Field(default="Demo reviewer", min_length=1, max_length=254)
    kind: Literal[
        "name_legal_document",
        "tax_specialist_result",
        "bankruptcy_specialist_result",
        "eft_clarification",
        "amortization_document",
        "authority_missing",
        "authorized_representative",
        "assignment_exception",
        "resolve_assignment",
        "additional_concern",
        "unrelated_contact",
    ]
    text: str = Field(default="", max_length=12000)
    eft_intent: Literal["incoming_payment", "outgoing_refund", "heloc_draw"] | None = None


class DraftEdit(PresenterMutation, PrepareResponse):
    draft_id: UUID
    draft_version: Annotated[StrictInt, Field(ge=1)]


class HandoffAcknowledge(PresenterMutation):
    handoff_id: UUID


class WorkflowRead(Contract):
    case_id: str
    revision: int
    scenario: str
    input_options: list[str]
    pending_work: list[dict]
    drafts: list[dict]
    reviews: list[dict]
    handoffs: list[dict]
    contacts: list[dict]
