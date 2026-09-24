from copy import deepcopy

from sqlalchemy import select

from app.assessment import assess_case, task_matches
from app.domain import DomainError
from app.models import CorrespondenceCase, Evidence, FinalNote, ServicingHistory, SpecialistTask
from app.routing import next_review
from app.simulators.common import checked_draft, outbox_for, row_data


def read(ctx, operation, reference_id=None):
    if operation == "ils.read":
        return {"loan": row_data(ctx.loan)}
    if operation == "ils.history":
        return {
            "history": [row_data(r) for r in ctx.rows(ServicingHistory)],
            "notes": [row_data(r) for r in ctx.rows(FinalNote)],
        }
    if operation == "ils.task":
        return {"task": row_data(ctx.scoped(SpecialistTask, reference_id))}
    return {"tasks": [row_data(t) for t in ctx.rows(SpecialistTask)]}


def history(ctx, before, after):
    ctx.session.add(
        ServicingHistory(
            case_id=ctx.case.id,
            loan_id=ctx.loan.id,
            action_id=ctx.action.id,
            operation=ctx.action.operation,
            before=before,
            after=after,
        )
    )


def name_prerequisites(ctx):
    report, _ = assess_case(ctx.session, ctx.data_dir, ctx.case.id)
    if ctx.simulation.scenario_key != "DEMO-01" or any(
        "update" in f.blocks for f in report.findings
    ):
        raise DomainError(
            422,
            "update_not_authorized",
            "A name update requires matching signed/legal evidence, authority and an approved ordinary product procedure.",
        )
    if ctx.loan.context.get("profile_update_result"):
        raise DomainError(
            409,
            "update_already_complete",
            "Inspect the existing name-update result instead of executing another update.",
        )
    return report


def create_task(ctx, task_type):
    related_ids = select(CorrespondenceCase.id).where(
        CorrespondenceCase.loan_id == ctx.loan.id,
        CorrespondenceCase.simulation_id == ctx.simulation.id,
    )
    for task in ctx.session.scalars(
        select(SpecialistTask).where(SpecialistTask.case_id.in_(related_ids))
    ):
        if task_matches(task, ctx.case, ctx.loan, ctx.simulation.scenario_key, task_type):
            return ctx.effect(task, "task", {"task": row_data(task), "reused": True})
    if task_type != "demo_profile_name_update":
        raise DomainError(
            422,
            "distinct_action_not_authorized",
            "An absent task alone does not authorize creating one. The selected case supplies no additional authorized action of this type.",
        )
    report = name_prerequisites(ctx)
    task = SpecialistTask(
        case_id=ctx.case.id,
        task_type=task_type,
        owner="Demo Servicing Team",
        status="pending",
        pending_reason="Verified name-change documents await the authorized update.",
        next_review_at=next_review(ctx.simulation.evaluation_at),
        request={
            "synthetic": True,
            "loan_identifier": ctx.loan.loan_identifier,
            "client_code": ctx.loan.client_code,
            "requested_name": ctx.loan.context["requested_legal_name"],
            "evidence_ids": [
                e.evidence_id
                for e in report.attachments
                if e.valid and e.title != "Synthetic servicing record"
            ],
        },
    )
    ctx.session.add(task)
    ctx.session.flush()
    ctx.bump(material=True)
    history(ctx, {}, {"task": row_data(task)})
    return ctx.effect(task, "task", {"task": row_data(task), "reused": False})


def update_name(ctx, task_id):
    task = ctx.scoped(SpecialistTask, task_id)
    name_prerequisites(ctx)
    if (
        not task_matches(
            task, ctx.case, ctx.loan, ctx.simulation.scenario_key, "demo_profile_name_update"
        )
        or task.status != "pending"
    ):
        raise DomainError(
            422,
            "task_not_applicable",
            "The pending task must authorize this loan's requested name update.",
        )
    before = deepcopy(ctx.loan.context)
    result = {
        "reference": f"DEMO-NAME-{ctx.action.id}",
        "completed_at": ctx.simulation.evaluation_at.isoformat(),
        "previous_name": before["current_legal_name"],
        "updated_name": before["requested_legal_name"],
        "simulated": True,
    }
    ctx.loan.context = {
        **before,
        "current_legal_name": result["updated_name"],
        "profile_update_result": result["reference"],
    }
    # Refresh each servicing snapshot on this loan; evidence on other loans is untouched.
    case_ids = select(CorrespondenceCase.id).where(CorrespondenceCase.loan_id == ctx.loan.id)
    for evidence in ctx.session.scalars(select(Evidence).where(Evidence.case_id.in_(case_ids))):
        if evidence.details.get("kind") == "record":
            evidence.details = {**evidence.details, "facts": ctx.loan.context}
            evidence.version += 1
    task.status, task.result, task.pending_reason, task.next_review_at = (
        "completed",
        result,
        None,
        None,
    )
    ctx.bump(material=True)
    history(ctx, {"context": before}, {"context": ctx.loan.context, "task": row_data(task)})
    return ctx.effect(task, "task", {"task": row_data(task), "update": result})


def final_note(ctx, draft_id):
    draft = checked_draft(ctx, draft_id, require_approval=True)
    outbox = outbox_for(ctx, draft.id)
    existing = next(
        (n for n in ctx.rows(FinalNote) if n.details.get("outbox_id") == outbox.id), None
    )
    if existing:
        return ctx.effect(existing, "note", {"note": row_data(existing), "reused": True})
    details = {
        "standout_comment": True,
        "draft_id": draft.id,
        "draft_version": draft.version,
        "outbox_id": outbox.id,
        "recipient": draft.recipient,
        "ccid": ctx.case.ccid,
        "tracking_update": f"Simulated response delivered: {outbox.delivery_reference}",
    }
    note = FinalNote(
        case_id=ctx.case.id,
        action_id=ctx.action.id,
        department="Servicing",
        note_type="INQ Email Reply",
        details=details,
        content=f"Standout Comment\nTo: {draft.recipient}\n{details['tracking_update']}\n{draft.body}",
    )
    ctx.session.add(note)
    ctx.session.flush()
    history(ctx, {}, {"note": row_data(note)})
    return ctx.effect(note, "note")
