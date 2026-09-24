from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StrictInt

from app.rule_contracts import DraftCandidate
from app.schemas import Contract, Identifier


class Inspect(Contract):
    operation: Literal[
        "cct.read",
        "cct.worklist",
        "cct.related",
        "cct.history",
        "ils.read",
        "ils.history",
        "ils.tasks",
        "onbase.search",
        "onbase.validate",
        "csp.outbox",
        "csp.drafts",
        "rules.assess",
        "knowledge.search",
        "review.read",
    ]


class Retrieve(Contract):
    operation: Literal["ils.task", "onbase.retrieve", "csp.status", "action.status"]
    reference_id: UUID


class Write(Contract):
    action_id: UUID
    expected_revision: Annotated[StrictInt, Field(ge=1)]
    evidence_versions: dict[str, Annotated[StrictInt, Field(ge=1)]]
    input_hash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ApplyPlan(Write):
    operation: Literal["cct.apply_plan", "cct.handoff"]


class Prepare(Write):
    operation: Literal["csp.prepare"]
    candidate: DraftCandidate


class DraftAction(Write):
    operation: Literal["csp.send", "onbase.index", "ils.final_note", "cct.close"]
    draft_id: UUID


class CreateTask(Write):
    operation: Literal["ils.create_task"]
    task_type: Literal[
        "demo_profile_name_update", "demo_tax_schedule_review", "demo_bankruptcy_status_review"
    ]


class UpdateName(Write):
    operation: Literal["ils.update_name"]
    task_id: UUID


class Reconcile(Write):
    operation: Literal["action.reconcile"]
    reference_id: UUID


Command = Annotated[
    Inspect | Retrieve | ApplyPlan | Prepare | DraftAction | CreateTask | UpdateName | Reconcile,
    Field(discriminator="operation"),
]


class ToolRequest(Contract):
    loan_identifier: Identifier
    client_code: Identifier
    command: Command
    # Presenter/test control; deliberately not part of the model tool schemas.
    failure_mode: Literal["none", "before_write", "after_write_response_lost"] = "none"


class ResourceReference(Contract):
    kind: Literal["case", "loan", "task", "draft", "outbox", "package", "note", "action", "handoff"]
    id: str


class ToolResult(Contract):
    simulated: Literal[True] = True
    operation: str
    status: Literal[
        "ok",
        "prepared",
        "simulated_complete",
        "rejected",
        "awaiting_review",
        "failed",
        "uncertain",
        "in_progress",
    ]
    action_id: str | None = None
    reference: ResourceReference | None = None
    code: str
    message: str
    data: dict = Field(default_factory=dict)


class ToolDefinition(Contract):
    name: str
    system: str
    mutates: bool
    simulated: Literal[True] = True
    parameters: dict
