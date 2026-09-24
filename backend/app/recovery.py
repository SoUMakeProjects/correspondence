"""Receipt-based recovery; never replay an unverified simulator write."""

from uuid import UUID, uuid4

from sqlalchemy import select

from app.assessment import assess_case
from app.db import utcnow
from app.domain import DomainError
from app.models import ActionReceipt, AgentRun, Loan
from app.repository import require_case
from app.simulators.common import scope
from app.simulators.contracts import ToolRequest
from app.simulators.dispatcher import dispatch, probe_effect, reconcile, result_for
from app.workflow import begin_mutation, save_mutation
from app.workflow_contracts import PresenterMutation


class RestoreStatus(PresenterMutation):
    action_id: UUID


def context(session, data_dir, case_id):
    case = require_case(session, case_id)
    loan = session.get(Loan, case.loan_id)
    return scope(
        session, data_dir, case.simulation_id, case_id, loan.loan_identifier, loan.client_code
    )


def unresolved(session, case_id):
    return list(
        session.scalars(
            select(ActionReceipt)
            .where(
                ActionReceipt.case_id == case_id,
                ActionReceipt.status.in_(["uncertain", "in_progress"]),
            )
            .order_by(ActionReceipt.created_at, ActionReceipt.id)
        )
    )


def inspect_recovery(session, data_dir, case_id):
    ctx = context(session, data_dir, case_id)
    actions = list(
        session.scalars(
            select(ActionReceipt)
            .where(
                ActionReceipt.case_id == case_id,
                ActionReceipt.status.in_(["uncertain", "in_progress", "failed"]),
            )
            .order_by(ActionReceipt.created_at)
        )
    )
    return {
        "case_id": case_id,
        "revision": ctx.case.revision,
        "blocked": any(a.status in {"uncertain", "in_progress"} for a in actions),
        "actions": [
            {
                "id": a.id,
                "run_id": a.run_id,
                "operation": a.operation,
                "status": a.status,
                **probe_effect(ctx, a),
                "can_restore_status": (a.result or {}).get("fault_kind") == "unknown_send_status"
                and (a.result or {}).get("status_lookup_available") is False,
            }
            for a in actions
        ],
    }


def check_actions(session, data_dir, case_id, payload):
    with session.begin():
        ctx, receipt, prior = begin_mutation(
            session, data_dir, case_id, payload, "recovery.check", recovery=True
        )
        if prior:
            return receipt.result["data"]
        ctx.action = receipt
        checked = []
        for action in unresolved(session, case_id):
            verification = probe_effect(ctx, action)
            if verification["outcome"] == "applied":
                reconcile(ctx, action.id)
            checked.append({"action_id": action.id, "operation": action.operation, **verification})
        ctx.bump()
        return save_mutation(
            ctx,
            receipt,
            "recovery.checked",
            payload.actor,
            {"checks": checked, "blocked": bool(unresolved(session, case_id))},
            {"checks": checked},
        )


def restore_status(session, data_dir, case_id, payload):
    with session.begin():
        ctx, receipt, prior = begin_mutation(
            session, data_dir, case_id, payload, "recovery.restore_status", recovery=True
        )
        if prior:
            return receipt.result["data"]
        action = ctx.scoped(ActionReceipt, payload.action_id)
        if (action.result or {}).get("fault_kind") != "unknown_send_status":
            raise DomainError(
                422, "not_a_status_fault", "This action has no simulated status-service outage."
            )
        # Restore read access only. The original effect/hash must still pass independent verification.
        action.result = {**action.result, "status_lookup_available": True}
        ctx.bump()
        return save_mutation(
            ctx,
            receipt,
            "recovery.status_restored",
            payload.actor,
            {"action_id": action.id, "status_access": "available"},
            {"action_id": action.id},
        )


def recover_worker(worker, run_id, case_id, token):
    """Reconcile committed effects under the new lease and reconstruct a missed checkpoint."""
    checks = []
    with worker.sessions() as session:
        ids = [a.id for a in unresolved(session, case_id)]
    for identity in ids:
        with worker.sessions() as session:
            ctx = context(session, worker.settings.data_dir, case_id)
            action = ctx.scoped(ActionReceipt, identity)
            verification = probe_effect(ctx, action)
            checks.append({"action_id": identity, "operation": action.operation, **verification})
            if verification["outcome"] != "applied":
                continue
            report = assess_case(session, worker.settings.data_dir, case_id)[0]
            request = ToolRequest(
                loan_identifier=ctx.loan.loan_identifier,
                client_code=ctx.loan.client_code,
                command={
                    "operation": "action.reconcile",
                    "action_id": str(uuid4()),
                    "reference_id": identity,
                    "expected_revision": ctx.case.revision,
                    "evidence_versions": report.evidence_versions,
                    "input_hash": report.input_hash,
                },
            )
            simulation_id = ctx.simulation.id
        with worker.sessions() as session:
            result = dispatch(
                session,
                worker.settings.data_dir,
                simulation_id,
                case_id,
                request,
                run_id=run_id,
                lease_token=token,
            )
            if result.status != "simulated_complete":
                checks[-1] = {**checks[-1], "outcome": "unknown", "code": result.code}
    with worker.sessions() as session:
        run = session.get(AgentRun, run_id)
        checkpoint = dict(run.checkpoint)
        history = list(checkpoint.get("history", []))
        planned = checkpoint.get("planned_action_id")
        receipt = session.get(ActionReceipt, planned) if planned else None
        if (
            receipt
            and receipt.case_id == case_id
            and not any(h.get("action_id") == planned for h in history)
        ):
            result = result_for(receipt).model_dump(mode="json")
            history.append(
                {
                    "step": len(history) + 1,
                    "tool": checkpoint.get("current_tool", "recovered_action"),
                    **{
                        k: result[k]
                        for k in ("status", "code", "message", "action_id", "reference")
                    },
                    "recovered": True,
                }
            )
        blocked = bool(unresolved(session, case_id))
    worker.save(
        run_id,
        token,
        {
            "history": history,
            "steps": len(history),
            "planned_action_id": None,
            "reconciliation_required": blocked,
            "recovery_pending": False,
            "recovery_count": checkpoint.get("recovery_count", 0) + 1,
            "usage_incomplete": checkpoint.get("usage_incomplete", False)
            or checkpoint.get("phase") == "choosing_tool",
            "recovery_checks": [*checkpoint.get("recovery_checks", []), *checks],
            "last_recovered_at": utcnow().isoformat(),
        },
        kind="agent.recovered",
        payload={"checks": checks, "blocked": blocked},
    )
    return not blocked
