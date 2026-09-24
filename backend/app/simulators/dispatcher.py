"""One scoped mutation boundary for presenter controls and the Azure agent."""

from typing import get_args

from pydantic import ValidationError
from sqlalchemy import select, text

from app.assessment import assess_case
from app.catalogs import search_knowledge
from app.db import utcnow
from app.domain import DomainError
from app.models import (
    ActionReceipt,
    AgentRun,
    CaseEvent,
    CorrespondenceCase,
    FinalNote,
    IndexedPackage,
    Loan,
    OutboxEntry,
    ResponseDraft,
    ReviewDecision,
    SpecialistHandoff,
    SpecialistTask,
)
from app.repository import fingerprint
from app.simulators import cct, ils, onbase, secure_mail
from app.simulators.artifacts import verify_package, verify_sent_files
from app.simulators.common import row_data, scope
from app.simulators.contracts import (
    ApplyPlan,
    CreateTask,
    DraftAction,
    Inspect,
    Prepare,
    Reconcile,
    Retrieve,
    ToolDefinition,
    ToolResult,
    UpdateName,
    Write,
)

COMMAND_TYPES = (
    Inspect,
    Retrieve,
    ApplyPlan,
    CreateTask,
    DraftAction,
    Prepare,
    Reconcile,
    UpdateName,
)
RESOURCE_TYPES = {
    "case": CorrespondenceCase,
    "loan": Loan,
    "task": SpecialistTask,
    "draft": ResponseDraft,
    "outbox": OutboxEntry,
    "package": IndexedPackage,
    "note": FinalNote,
    "action": ActionReceipt,
    "handoff": SpecialistHandoff,
}


def registry():
    definitions = []
    for model in COMMAND_TYPES:
        for operation in get_args(model.model_fields["operation"].annotation):
            schema = model.model_json_schema()
            schema["properties"]["operation"] = {"const": operation, "type": "string"}
            definitions.append(
                ToolDefinition(
                    name=operation,
                    system=operation.split(".")[0],
                    mutates=issubclass(model, Write),
                    parameters=schema,
                )
            )
    return definitions


def result_for(action):
    recorded = action.result or {}
    confirmed = action.status == "simulated_complete"
    return ToolResult(
        operation=action.operation,
        action_id=action.id,
        status=action.status,
        reference=recorded.get("resource") if confirmed else None,
        code=recorded.get("code", action.status),
        message=recorded.get(
            "message",
            "Simulated operation completed."
            if confirmed
            else "Reconcile this action before continuing.",
        ),
        data=recorded.get("data", {}) if confirmed else {},
    )


def inspect(ctx, command):
    operation = command.operation
    ref = getattr(command, "reference_id", None)
    if operation.startswith("cct."):
        return cct.read(ctx, operation)
    if operation.startswith("ils."):
        return ils.read(ctx, operation, ref)
    if operation.startswith("onbase."):
        return onbase.read(ctx, operation, ref)
    if operation.startswith("csp."):
        return secure_mail.read(ctx, operation, ref)
    if operation == "action.status":
        action = ctx.scoped(ActionReceipt, ref)
        return {
            "action": result_for(action).model_dump(mode="json"),
            "verification": probe_effect(ctx, action),
        }
    if operation == "rules.assess":
        return {
            "assessment": assess_case(ctx.session, ctx.data_dir, ctx.case.id)[0].model_dump(
                mode="json"
            )
        }
    if operation == "knowledge.search":
        return {
            "items": search_knowledge(
                ctx.session, ctx.simulation.scenario_key, ctx.loan.client_code
            )
        }
    return {"decisions": [row_data(r) for r in ctx.rows(ReviewDecision)]}


def probe_effect(ctx, action):
    """Query local system evidence; an unknown result is never interpreted as not-applied."""
    if action.status in {"failed", "rejected", "awaiting_review"}:
        return {"outcome": "not_applied", "code": "no_committed_effect"}
    if action.status == "simulated_complete":
        return {"outcome": "applied", "code": "committed_receipt"}
    effect = action.result or {}
    if action.status != "uncertain" or effect.get("status_lookup_available") is False:
        return {"outcome": "unknown", "code": "status_unavailable"}
    reference = effect.get("resource", {})
    model = RESOURCE_TYPES.get(reference.get("kind"))
    row = ctx.session.get(model, reference.get("id")) if model else None
    if row is None or fingerprint(row_data(row)) != effect.get("effect_hash"):
        return {"outcome": "unknown", "code": "effect_not_verified"}
    try:
        if isinstance(row, CorrespondenceCase) and row.id != ctx.case.id:
            return {"outcome": "unknown", "code": "foreign_effect"}
        if isinstance(row, Loan) and row.id != ctx.loan.id:
            return {"outcome": "unknown", "code": "foreign_effect"}
        if isinstance(row, SpecialistTask):
            owner = ctx.session.get(CorrespondenceCase, row.case_id)
            if (
                not owner
                or owner.loan_id != ctx.loan.id
                or owner.simulation_id != ctx.simulation.id
            ):
                return {"outcome": "unknown", "code": "foreign_effect"}
        if isinstance(
            row, (OutboxEntry, IndexedPackage, ResponseDraft, FinalNote, SpecialistHandoff)
        ):
            ctx.scoped(model, row.id)
        if isinstance(row, OutboxEntry):
            verify_sent_files(ctx.data_dir, row.sent_content)
        if isinstance(row, IndexedPackage):
            draft = ctx.scoped(ResponseDraft, row.index_fields["draft_id"])
            outbox = ctx.scoped(OutboxEntry, row.index_fields["outbox_id"])
            verify_package(ctx.data_dir, row, outbox, ctx.case, ctx.loan, draft)
    except (DomainError, OSError, KeyError):
        return {"outcome": "unknown", "code": "artifact_not_verified"}
    return {"outcome": "applied", "code": "effect_verified"}


def reconcile(ctx, reference_id):
    action = ctx.scoped(ActionReceipt, reference_id)
    if action.id == ctx.action.id:
        raise DomainError(422, "invalid_reconciliation", "Choose an earlier action to reconcile.")
    if action.status == "uncertain":
        effect = action.result or {}
        reference = effect.get("resource", {})
        if probe_effect(ctx, action)["outcome"] != "applied":
            raise DomainError(
                409,
                "effect_not_verified",
                "The prior write cannot be verified. Keep it uncertain for investigation.",
            )
        action.status = "simulated_complete"
        action.result = {
            **effect,
            "code": "reconciled",
            "message": "The persisted simulated result was independently verified.",
        }
        ctx.session.add(
            CaseEvent(
                case_id=ctx.case.id,
                action_id=action.id,
                kind="action.reconciled",
                actor="recovery_service",
                run_id=ctx.action.run_id,
                payload={"operation": action.operation, "resource": reference},
            )
        )
    elif action.status == "in_progress":
        raise DomainError(
            409,
            "effect_not_verified",
            "The in-progress action needs recovery evidence before retrying.",
        )
    return ctx.effect(action, "action", {"action": result_for(action).model_dump(mode="json")})


def mutate(ctx, command):
    match command.operation:
        case "cct.apply_plan":
            return cct.apply_plan(ctx)
        case "cct.handoff":
            return cct.handoff(ctx)
        case "cct.close":
            return cct.close(ctx, command.draft_id)
        case "ils.create_task":
            return ils.create_task(ctx, command.task_type)
        case "ils.update_name":
            return ils.update_name(ctx, command.task_id)
        case "ils.final_note":
            return ils.final_note(ctx, command.draft_id)
        case "csp.prepare":
            return secure_mail.prepare(ctx, command.candidate)
        case "csp.send":
            return secure_mail.send(ctx, command.draft_id)
        case "onbase.index":
            return onbase.index(ctx, command.draft_id)
        case "action.reconcile":
            return reconcile(ctx, command.reference_id)
    raise DomainError(422, "unknown_operation", "This operation is not in the simulator registry.")


def dispatch(session, data_dir, simulation_id, case_id, request, *, run_id=None, lease_token=None):
    command = request.command
    with session.begin():
        if isinstance(command, Write):
            session.execute(text("BEGIN IMMEDIATE"))
        ctx = scope(
            session, data_dir, simulation_id, case_id, request.loan_identifier, request.client_code
        )
        if run_id:
            run = session.get(AgentRun, run_id)
            if (
                not run
                or run.case_id != ctx.case.id
                or run.status != "running"
                or run.lease_token != lease_token
                or not run.lease_expires_at
                or run.lease_expires_at <= utcnow()
            ):
                raise DomainError(409, "lease_lost", "The worker no longer owns this run.")
            if run.checkpoint.get("stop_requested"):
                raise DomainError(
                    409, "stop_requested", "The run is stopping before the next action."
                )
        if not isinstance(command, Write):
            if request.failure_mode != "none":
                raise DomainError(
                    422,
                    "failure_mode_not_applicable",
                    "Failure injection is available only for simulator writes.",
                )
            return ToolResult(
                operation=command.operation,
                status="ok",
                code="read_complete",
                message="Scoped synthetic records retrieved.",
                data=inspect(ctx, command),
            )
        payload = {
            "simulation_id": str(simulation_id),
            "case_id": str(case_id),
            "loan_identifier": request.loan_identifier,
            "client_code": request.client_code,
            "command": command.model_dump(mode="json"),
        }
        payload_hash = fingerprint(payload)
        prior = session.get(ActionReceipt, str(command.action_id))
        if prior:
            if prior.case_id != ctx.case.id:
                raise DomainError(
                    404, "reference_not_found", "No matching action exists in this case."
                )
            if prior.payload_hash != payload_hash:
                raise DomainError(
                    409,
                    "action_id_reused",
                    "The action identity already belongs to a different payload. Inspect its status before preparing another action.",
                )
            return result_for(prior)
        action = ActionReceipt(
            id=str(command.action_id),
            case_id=ctx.case.id,
            run_id=run_id,
            operation=command.operation,
            idempotency_key=f"simulator:{command.action_id}",
            payload_hash=payload_hash,
            payload_version=4,
            payload=payload,
            status="in_progress",
        )
        session.add(action)
        session.flush()
        ctx.action = action
        failure_mode = request.failure_mode
        fault = run.checkpoint.get("fault", {}) if run_id else {}
        fault_target = {
            "index_failure": "onbase.index",
            "lost_send_response": "csp.send",
            "unknown_send_status": "csp.send",
            "lost_task_response": "ils.create_task",
        }
        injected = bool(
            fault
            and not fault.get("consumed")
            and fault_target.get(fault.get("kind")) == command.operation
        )
        if injected:
            # This presenter-configured, single-use fault is consumed atomically with its receipt.
            failure_mode = (
                "before_write" if fault["kind"] == "index_failure" else "after_write_response_lost"
            )
            run.checkpoint = {
                **run.checkpoint,
                "fault": {**fault, "consumed": True, "action_id": action.id},
            }
        before_case = row_data(ctx.case)
        try:
            with session.begin_nested():
                if command.operation != "action.reconcile" and session.scalar(
                    select(ActionReceipt.id).where(
                        ActionReceipt.case_id == ctx.case.id,
                        ActionReceipt.id != action.id,
                        ActionReceipt.status.in_(["uncertain", "in_progress"]),
                    )
                ):
                    raise DomainError(
                        409,
                        "reconciliation_required",
                        "Reconcile the outstanding action before another mutation.",
                    )
                if ctx.case.status == "closed" and command.operation != "action.reconcile":
                    raise DomainError(
                        409,
                        "case_closed",
                        "This case is closed. Inspect the existing action results.",
                    )
                report, _ = assess_case(session, data_dir, ctx.case.id)
                if command.expected_revision != ctx.case.revision:
                    raise DomainError(
                        409,
                        "stale_revision",
                        "The case changed; reload it and prepare a fresh action.",
                    )
                if (
                    command.evidence_versions != report.evidence_versions
                    or command.input_hash != report.input_hash
                ):
                    raise DomainError(
                        409,
                        "stale_evidence",
                        "Evidence or decision inputs changed; reassess before writing.",
                    )
                if failure_mode == "before_write":
                    raise OSError("Controlled failure before mutation")
                effect = mutate(ctx, command)
                action.result = {
                    **effect,
                    "code": "simulated_complete",
                    "message": "Simulated operation completed.",
                }
                action.status = "simulated_complete"
                if failure_mode == "after_write_response_lost":
                    action.status = "uncertain"
                    action.result = {
                        **effect,
                        "code": "response_lost",
                        "message": "The simulated response was lost. Query and reconcile the original action; do not repeat its write.",
                        "status_lookup_available": not (
                            injected and fault["kind"] == "unknown_send_status"
                        ),
                        "fault_kind": fault.get("kind") if injected else None,
                    }
        except (DomainError, OSError, ValidationError) as exc:
            for path in ctx.written:
                path.unlink(missing_ok=True)
            if isinstance(exc, DomainError):
                action.status = "awaiting_review" if exc.code == "review_required" else "rejected"
                action.result = {"code": exc.code, "message": exc.message}
            else:
                action.status = "failed"
                action.result = {
                    "code": "write_failed",
                    "message": "The simulated write failed before completion. No applied result was committed.",
                }
        session.add(
            CaseEvent(
                case_id=ctx.case.id,
                action_id=action.id,
                kind="simulator.action",
                run_id=run_id,
                actor="azure_agent"
                if run_id and run.model_configuration.get("source") == "live_azure"
                else "test_double"
                if run_id
                else "local_presenter",
                payload={
                    "operation": action.operation,
                    "status": action.status,
                    "code": action.result["code"],
                    "revision": ctx.case.revision,
                    "before": before_case,
                    "after": row_data(ctx.case),
                },
            )
        )
        session.flush()
        return result_for(action)
