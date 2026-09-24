from sqlalchemy import select

from app.assessment import assess_case
from app.domain import DomainError
from app.models import (
    CaseEvent,
    Concern,
    CorrespondenceCase,
    Evidence,
    OutboxEntry,
    ResponseDraft,
    SpecialistHandoff,
    SpecialistTask,
)
from app.repository import case_read
from app.response_validation import validate_completion
from app.simulators.common import row_data


def read(ctx, operation):
    if operation == "cct.read":
        return {"case": case_read(ctx.session, ctx.case).model_dump(mode="json")}
    if operation == "cct.history":
        return {
            "events": [
                row_data(e)
                for e in ctx.session.scalars(
                    select(CaseEvent)
                    .where(CaseEvent.case_id == ctx.case.id)
                    .order_by(CaseEvent.sequence)
                )
            ]
        }
    cases = ctx.session.scalars(
        select(CorrespondenceCase)
        .where(
            CorrespondenceCase.simulation_id == ctx.simulation.id,
            CorrespondenceCase.loan_id == ctx.loan.id,
        )
        .order_by(CorrespondenceCase.original_received_at, CorrespondenceCase.id)
    )
    return {
        "cases": [
            case_read(ctx.session, c).model_dump(mode="json")
            for c in cases
            if operation != "cct.related" or c.id != ctx.case.id
        ]
    }


def apply_plan(ctx):
    if ctx.session.scalar(
        select(ResponseDraft.id).where(
            ResponseDraft.case_id == ctx.case.id,
            ResponseDraft.case_revision == ctx.case.content_revision,
        )
    ):
        raise DomainError(
            409,
            "plan_already_used",
            "A response already uses this plan. Revalidate changed inputs before replacing it.",
        )
    report, _ = assess_case(ctx.session, ctx.data_dir, ctx.case.id)
    ctx.case.classification = report.classification
    ctx.case.routing = report.routing.model_dump(mode="json")
    ctx.case.pending_work = [
        c.model_dump(mode="json") for c in report.concerns if c.disposition != "resolved"
    ]
    statuses = {
        "specialist_handoff": "waiting_on_department",
        "review_exception": "assignment_exception",
    }
    ctx.case.status = statuses.get(report.disposition, report.disposition)
    for plan in report.concerns:
        concern = ctx.scoped(Concern, plan.concern_id)
        concern.disposition, concern.evidence_ids = plan.disposition, plan.evidence_ids
    ctx.bump(material=True)
    return ctx.effect(
        ctx.case, "case", {"case": case_read(ctx.session, ctx.case).model_dump(mode="json")}
    )


def handoff(ctx):
    report, _ = assess_case(ctx.session, ctx.data_dir, ctx.case.id)
    if not ctx.case.routing:
        raise DomainError(
            409, "case_plan_required", "Record the concern and routing plan before a handoff."
        )
    pending = [c.model_dump(mode="json") for c in report.concerns if c.disposition != "resolved"]
    blocked = any(f.blocks for f in report.findings)
    special = report.routing.route not in {"Inquiry", "Disputes", None}
    if not pending and not blocked and not special:
        raise DomainError(
            422,
            "handoff_not_required",
            "No specialist or exception work is established by the assessment.",
        )
    if (
        pending
        and not special
        and all(c["disposition"] == "pending_borrower" for c in pending)
        and not any("response" in f.blocks for f in report.findings)
    ):
        # The borrower owns the next step and may be contacted: the information request is the
        # action, not a handoff. (Blocked contact, e.g. cease-and-desist, still hands off.)
        raise DomainError(
            422,
            "handoff_not_required",
            "The remaining work is borrower-pending and contact is permitted. Send the "
            "supported information request, then finish waiting_for_input without a handoff.",
        )
    for existing in ctx.rows(SpecialistHandoff):
        if existing.input_hash == report.input_hash:
            return ctx.effect(existing, "handoff", {"handoff": row_data(existing), "reused": True})
    route = (
        report.routing.route
        if special
        else "Supervisory review"
        if blocked
        else "Specialist review"
    )
    owner = (
        f"Demo {route} Team"
        if special
        else next(
            (c.owner for c in report.concerns if c.owner and c.disposition == "pending_department"),
            "Demo supervisor",
        )
    )
    item = SpecialistHandoff(
        case_id=ctx.case.id,
        action_id=ctx.action.id,
        route=route,
        owner=owner,
        status="requested",
        input_hash=report.input_hash,
        evidence_versions=report.evidence_versions,
        concerns=[c.model_dump(mode="json") for c in report.concerns],
        restrictions=report.routing.restrictions,
        routing_note=routing_note(ctx, report, route, owner),
    )
    ctx.session.add(item)
    ctx.case.status = "waiting_on_department"
    ctx.bump()
    return ctx.effect(item, "handoff")


def _team(name):
    return (name or "").removeprefix("Demo ")


def routing_note(ctx, report, route, owner):
    """Internal routing note for the receiving team, built only from persisted records."""
    from datetime import date, timedelta

    from app.response_validation import (
        DISPUTE_RESPONSE_DAYS,
        _eastern_iso_date,
        _eastern_long_date,
        _long_date,
    )

    case, loan = ctx.case, ctx.loan
    context = loan.context or {}
    received = case.original_received_at.isoformat()
    lines = [
        f"Referral to {route} – {_team(owner)}",
        f"Loan {loan.loan_identifier} · {loan.borrower_display_name} · Case {case.ccid} · "
        f"received {_eastern_long_date(received)}",
        f"Reason: {report.routing.reason}",
    ]
    docs = {
        e.details.get("key"): e.details.get("facts", {})
        for e in ctx.session.scalars(select(Evidence).where(Evidence.case_id == case.id))
    }
    order = docs.get("court-record", {})
    marker = context.get("servicing_bankruptcy_status")
    if order.get("case_number") and marker:
        determination = context.get("specialist_determination")
        task = next(
            (
                t
                for t in ctx.session.scalars(
                    select(SpecialistTask).where(SpecialistTask.case_id == case.id)
                )
                if t.task_type == "demo_bankruptcy_status_review"
            ),
            None,
        )
        court = (
            f"Court order in Chapter {order.get('chapter', 13)} case No. {order['case_number']} "
            f"shows the case dismissed on {_long_date(order['record_date'])} without a discharge."
            if order.get("reported_status") == "dismissed_without_discharge"
            and order.get("record_date")
            else f"Court record supplied for case No. {order['case_number']}."
        )
        if determination and task and task.status == "completed":
            lines.append(
                f"Bankruptcy: {court} Bankruptcy Team determination {determination}: "
                f"{marker.replace('_', ' ')}; the servicing marker has been corrected."
            )
        else:
            source = context.get("servicing_status_source", "").replace("_", " ")
            imported = context.get("servicing_status_imported_at")
            lines.append(
                f'Bankruptcy: {court} Servicing marker shows "{marker.replace("_", " ")}"'
                + (f" ({source}" if source else "")
                + (f", {_long_date(imported)}" if imported else "")
                + (")" if source else "")
                + ". Bankruptcy Team review "
                + ("pending." if task else "not found.")
            )
    if context.get("communication_restriction") == "representative_only":
        representative = ", ".join(
            v for v in (context.get("representative_name"), context.get("representative_firm")) if v
        )
        lines.append(
            "Contact: representative only – "
            + (
                f"{representative} <{context.get('authorized_recipient')}>"
                if representative
                else str(context.get("authorized_recipient"))
            )
            + ". Do not contact the borrower directly."
        )
    sent = ctx.session.scalar(
        select(OutboxEntry)
        .join(ResponseDraft, OutboxEntry.draft_id == ResponseDraft.id)
        .where(ResponseDraft.case_id == case.id, OutboxEntry.status == "sent")
        .order_by(OutboxEntry.created_at)
    )
    if sent is not None and ctx.simulation.scenario_key == "DEMO-04":
        due = date.fromisoformat(_eastern_iso_date(received)) + timedelta(
            days=DISPUTE_RESPONSE_DAYS
        )
        lines.append(
            f"Acknowledgment delivered to {sent.sent_content.get('recipient', 'the requester')} "
            f"({sent.delivery_reference}); written response promised by {_long_date(due)}."
        )
    open_items = [c for c in report.concerns if c.disposition != "resolved"]
    if open_items:
        lines.append("Open items:")
        lines += [
            f"- {c.description} ({c.disposition.replace('_', ' ')}"
            + (f"; owner {_team(c.owner)}" if c.owner else "")
            + ")"
            for c in open_items
        ]
    blocked = [f for f in report.findings if "closure" in f.blocks]
    if blocked:
        lines.append("Closure blocked until resolved:")
        lines += [f"- {f.message}" for f in blocked]
    if report.routing.restrictions:
        lines.append(
            "Restrictions: " + ", ".join(r.replace("_", " ") for r in report.routing.restrictions)
        )
    return "\n".join(lines)


def close(ctx, draft_id):
    draft = ctx.scoped(ResponseDraft, draft_id)
    latest = ctx.session.scalar(
        select(ResponseDraft.id)
        .where(ResponseDraft.case_id == ctx.case.id)
        .order_by(ResponseDraft.version.desc())
    )
    if draft.id != latest:
        raise DomainError(409, "stale_draft", "Closure must use the current response.")
    result = validate_completion(ctx.session, ctx.data_dir, ctx.case.id)
    if not result.valid:
        raise DomainError(422, "completion_blocked", "; ".join(f.message for f in result.findings))
    ctx.case.status = "closed"
    ctx.bump()
    return ctx.effect(
        ctx.case, "case", {"case": case_read(ctx.session, ctx.case).model_dump(mode="json")}
    )
