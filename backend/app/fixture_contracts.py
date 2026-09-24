"""Versioned, synthetic-only inputs. Evaluation answers live outside this package."""

from typing import Annotated, Literal

from pydantic import Field, StrictInt, model_validator

from app.domain import CaseFamily
from app.schemas import Contract, Identifier, ShortText, Timestamp

ScenarioKey = Literal["DEMO-01", "DEMO-02", "DEMO-03", "DEMO-04", "DEMO-05"]
Variant = Literal["base", "missing_document", "unreadable_document", "wrong_loan", "followup"]


class DocumentFixture(Contract):
    key: Identifier
    title: ShortText
    availability: Literal["available", "missing", "unreadable"] = "available"
    kind: Literal["document", "amortization_schedule"] = "document"
    paragraphs: list[str] = Field(min_length=1)
    facts: dict = Field(default_factory=dict)
    declared_loan_identifier: Annotated[str, Field(pattern=r"^0099[0-9]{6}$")] | None = None


class TaskFixture(Contract):
    key: Identifier
    task_type: Identifier
    owner: ShortText
    status: Literal["pending", "completed"]
    pending_reason: str | None = None
    request: dict
    result: dict | None = None
    evidence_keys: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_result(self):
        if self.status == "completed" and not self.result:
            raise ValueError("A completed fixture task requires its supplied result.")
        if self.status == "pending" and (self.result is not None or not self.pending_reason):
            raise ValueError("A pending fixture task needs a reason and cannot claim a result.")
        return self


class ScenarioFixture(Contract):
    scenario_id: ScenarioKey
    version: Literal["1"]
    synthetic: Literal[True]
    title: ShortText
    family: CaseFamily
    client_code: Literal["DEMO-NORTH", "DEMO-HARBOR"]
    loan_identifier: Annotated[str, Field(pattern=r"^009900000[1-5]$")]
    ccid: Annotated[str, Field(pattern=r"^DEMO-CC-00[1-5]$")]
    borrower_display_name: ShortText
    borrower_email: Annotated[str, Field(pattern=r"^[a-z0-9._-]+@(example\.com|outlook\.com)$")]
    balance_minor: Annotated[StrictInt, Field(ge=0, le=9_007_199_254_740_991)]
    original_received_at: Timestamp
    evaluation_at: Timestamp
    correspondence_text: str
    concerns: list[str] = Field(min_length=1)
    loan_context: dict
    documents: list[DocumentFixture] = Field(min_length=1)
    tasks: list[TaskFixture]

    @model_validator(mode="after")
    def validate_references(self):
        keys = [doc.key for doc in self.documents]
        if len(set(keys)) != len(keys) or len({task.key for task in self.tasks}) != len(self.tasks):
            raise ValueError("Fixture document and task keys must be unique.")
        if any(set(task.evidence_keys) - set(keys) for task in self.tasks):
            raise ValueError("A fixture task references an unknown document.")
        if self.original_received_at > self.evaluation_at:
            raise ValueError("Fixture receipt cannot follow its evaluation clock.")
        return self


class FollowupFixture(Contract):
    scenario_id: ScenarioKey
    version: Literal["1"]
    synthetic: Literal[True]
    documents: list[DocumentFixture]
    tasks: list[TaskFixture]
    loan_context_patch: dict


class KnowledgeFixture(Contract):
    key: Identifier
    version: Literal[1]
    status: Literal["curated_demo"]
    title: ShortText
    kind: Literal["guidance", "template", "disclosure"]
    scenario_ids: list[ScenarioKey] = Field(min_length=1)
    client_codes: list[Literal["DEMO-NORTH", "DEMO-HARBOR"]] = Field(min_length=1)
    products: list[str] = Field(min_length=1)
    source_references: list[str] = Field(min_length=1)
    effective_at: Timestamp
    content: str
    limitations: list[str] = Field(min_length=1)
    required_facts: list[str]
    allowed_placeholders: list[str]
    owner: Literal["demo_implementation"]


class ClientFixture(Contract):
    code: Literal["DEMO-NORTH", "DEMO-HARBOR"]
    version: Literal[1, 2]
    display_name: ShortText
    settings: dict
