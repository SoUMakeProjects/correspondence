"""Read-only demo summaries and an allowlisted, text-free evidence export."""

from datetime import datetime
from re import fullmatch

from sqlalchemy import select

from app.assessment import assess_case
from app.db import utcnow
from app.domain import DomainError
from app.models import (
    ActionReceipt,
    AgentRun,
    CaseEvent,
    Evidence,
    FinalNote,
    IndexedPackage,
    OutboxEntry,
    ResponseDraft,
    ReviewDecision,
    SpecialistHandoff,
)
from app.recovery import context, inspect_recovery
from app.simulators.dispatcher import probe_effect, registry

INTERVENTIONS = {
    "input.received",
    "response.reviewed",
    "response.edited",
    "handoff.acknowledged",
    "recovery.checked",
    "recovery.status_restored",
    "agent.stop_requested",
    "case.updated",
}


def require_run(session, run_id):
    run = session.get(AgentRun, run_id)
    if not run:
        raise DomainError(404, "run_not_found", "This run was not found.")
    return run


def run_summary(session, data_dir, run_id):
    run = require_run(session, run_id)
    ctx = context(session, data_dir, run.case_id)
    checkpoint = run.checkpoint
    actions = list(
        session.scalars(
            select(ActionReceipt)
            .where(ActionReceipt.run_id == run.id)
            .order_by(ActionReceipt.created_at)
        )
    )
    end = (
        datetime.fromisoformat(checkpoint["finished_at"])
        if checkpoint.get("finished_at")
        else utcnow()
        if run.status in {"running", "queued"}
        else run.updated_at
    )
    start = (
        datetime.fromisoformat(checkpoint["started_at"])
        if checkpoint.get("started_at")
        else run.created_at
    )
    events = list(
        session.scalars(
            select(CaseEvent)
            .where(CaseEvent.case_id == run.case_id, CaseEvent.created_at <= end)
            .order_by(CaseEvent.sequence)
        )
    )
    interventions = [e for e in events if e.kind in INTERVENTIONS]
    report = assess_case(session, data_dir, run.case_id)[0]
    completed = [
        a for a in actions if a.status == "simulated_complete" and a.operation != "action.reconcile"
    ]
    effects = {(a.operation, (a.result or {}).get("resource", {}).get("id")) for a in completed}
    return {
        "run_id": run.id,
        "case_id": run.case_id,
        "scenario": ctx.simulation.scenario_key,
        "status": run.status,
        "current_case_status": ctx.case.status,
        "resumed_from": checkpoint.get("resumed_from"),
        "reason": checkpoint.get("reason"),
        "elapsed_seconds": round(max(0, (end - start).total_seconds()), 2),
        "elapsed_includes_recovery_waits": True,
        "model_calls": checkpoint.get("model_calls", 0),
        "reported_tokens": checkpoint.get("usage", {}).get("total_tokens", 0),
        "usage_complete": not checkpoint.get("usage_incomplete", False) and run.status != "failed",
        "source": run.model_configuration.get("source", "unknown"),
        "completed_actions": len(effects),
        "failed_actions": sum(a.status in {"failed", "rejected"} for a in actions),
        "reconciled_actions": sum(
            a.operation == "action.reconcile" and a.status == "simulated_complete" for a in actions
        ),
        "case_interventions_through_run": len(interventions),
        "interventions": [
            {"event_sequence": e.sequence, "kind": e.kind, "created_at": e.created_at.isoformat()}
            for e in interventions
        ],
        "recovery_count": checkpoint.get("recovery_count", 0),
        "pending_concerns": sum(c.disposition != "resolved" for c in report.concerns),
        "actions": [
            {"id": a.id, "operation": a.operation, "status": a.status, **probe_effect(ctx, a)}
            for a in actions
        ],
        "recovery": inspect_recovery(session, data_dir, run.case_id),
        "measurement_scope": "Local synthetic demo. Action counts belong to this run; interventions include this case's history through the run; pending state is current.",
    }


def evidence_export(session, data_dir, run_id):
    run = require_run(session, run_id)
    ctx = context(session, data_dir, run.case_id)
    summary = run_summary(session, data_dir, run_id)
    report = assess_case(session, data_dir, run.case_id)[0]

    def rows(model):
        return list(
            session.scalars(
                select(model)
                .where(model.case_id == run.case_id)
                .order_by(model.created_at, model.id)
            )
        )

    allowed_ops = {r.name for r in registry()} | {
        "foundation.case.update",
        "workflow.input",
        "workflow.edit",
        "workflow.review",
        "workflow.handoff_acknowledged",
        "recovery.check",
        "recovery.restore_status",
    }
    receipts = rows(ActionReceipt)
    outbox = list(
        session.scalars(
            select(OutboxEntry).join(ActionReceipt).where(ActionReceipt.case_id == run.case_id)
        )
    )
    # Arbitrary correspondence, facts, notes, names, IDs from servicing, file paths, provider
    # content and presenter-entered text never enter this export. References are generated UUIDs.
    return {
        "format": "correspondence-demo-evidence-v1",
        "synthetic": True,
        "exported_at": utcnow().isoformat(),
        "scope": "Selected run metrics and current case record references at export time; text and servicing identifiers omitted.",
        "run": {
            **{
                k: summary[k]
                for k in (
                    "run_id",
                    "case_id",
                    "status",
                    "current_case_status",
                    "elapsed_seconds",
                    "model_calls",
                    "reported_tokens",
                    "usage_complete",
                    "completed_actions",
                    "failed_actions",
                    "reconciled_actions",
                    "case_interventions_through_run",
                    "recovery_count",
                    "pending_concerns",
                )
            },
            "source": run.model_configuration.get("source")
            if run.model_configuration.get("source") in {"live_azure", "test_double"}
            else "unknown",
            "configuration_id": run.model_configuration.get("configuration_id")
            if fullmatch(r"[0-9a-f]{64}", run.model_configuration.get("configuration_id") or "")
            else None,
        },
        "scenario": ctx.simulation.scenario_key
        if ctx.simulation.scenario_key in {f"DEMO-0{i}" for i in range(1, 6)}
        else "custom_synthetic",
        "input_hash": report.input_hash,
        "evidence_versions": report.evidence_versions,
        "evidence": [
            {
                "id": e.id,
                "version": e.version,
                "content_sha256": e.content_sha256,
                "synthetic": e.synthetic,
            }
            for e in rows(Evidence)
        ],
        "actions": [
            {
                "id": a.id,
                "run_id": a.run_id,
                "operation": a.operation if a.operation in allowed_ops else "other",
                "status": a.status,
                "payload_hash": a.payload_hash,
                "outcome": probe_effect(ctx, a)["outcome"],
            }
            for a in receipts
        ],
        "drafts": [
            {
                "id": d.id,
                "version": d.version,
                "case_revision": d.case_revision,
                "evidence_versions": d.evidence_versions,
                "attachment_ids": d.attachment_ids,
            }
            for d in rows(ResponseDraft)
        ],
        "reviews": [
            {
                "id": r.id,
                "draft_id": r.draft_id,
                "draft_version": r.draft_version,
                "decision": r.decision,
                "content_hash": r.content_hash,
            }
            for r in rows(ReviewDecision)
        ],
        "outbox": [
            {"id": o.id, "action_id": o.action_id, "draft_id": o.draft_id, "status": o.status}
            for o in outbox
        ],
        "packages": [
            {
                "id": p.id,
                "action_id": p.action_id,
                "content_sha256": p.content_sha256,
                "draft_id": p.index_fields.get("draft_id"),
            }
            for p in rows(IndexedPackage)
        ],
        "notes": [
            {"id": n.id, "action_id": n.action_id, "draft_id": n.details.get("draft_id")}
            for n in rows(FinalNote)
        ],
        "handoffs": [
            {
                "id": h.id,
                "status": h.status,
                "input_hash": h.input_hash,
                "acknowledged_at": h.acknowledged_at.isoformat() if h.acknowledged_at else None,
            }
            for h in rows(SpecialistHandoff)
        ],
        "concerns": [
            {
                "id": c.concern_id,
                "disposition": c.disposition,
                "evidence_ids": c.evidence_ids,
                "next_review_at": c.next_review_at.isoformat() if c.next_review_at else None,
            }
            for c in report.concerns
        ],
        "interventions": summary["interventions"],
    }
