"""BRD 8.2: date-based Eastern weekdays, independent of assignment history."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.rule_contracts import AgingResult, Finding, RoutingInputs, RoutingResult, SpecialRoute

EASTERN = ZoneInfo("America/New_York")


def aware(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError, TypeError):
        return None


def age(received: object, evaluated: object) -> AgingResult:
    def display(value):
        return value.isoformat() if isinstance(value, datetime) else str(value) if value else None

    result = AgingResult(
        original_received_at=display(received),
        evaluation_at=display(evaluated),
        reason="Original receipt and evaluation must be valid timestamps with explicit offsets.",
    )
    start, end = aware(received), aware(evaluated)
    if start is None or end is None:
        return result
    if end < start:
        result.reason = "Evaluation precedes original receipt; no age can be assigned."
        return result
    first, last = start.astimezone(EASTERN).date(), end.astimezone(EASTERN).date()
    result.received_eastern_date, result.evaluation_eastern_date = (
        first.isoformat(),
        last.isoformat(),
    )
    weeks, remainder = divmod((last - first).days, 7)
    result.workdays = weeks * 5 + sum(
        (first + timedelta(days=offset)).weekday() < 5 for offset in range(1, remainder + 1)
    )
    result.reason = "Receipt date is day 0; count subsequent Monday–Friday dates through evaluation, including weekday holidays."
    return result


def route_case(received: object, evaluated: object, inputs: RoutingInputs) -> RoutingResult:
    aging = age(received, evaluated)
    findings, actions = [], []
    if aging.workdays is None:
        findings.append(
            Finding(
                code="invalid_receipt_clock",
                rule="BRD-8.2",
                message=aging.reason,
                blocks=["ordinary_route"],
                evidence_ids=[],
            )
        )
    if len(set(inputs.email_owners)) > 1:
        actions.append("Supervisor must reconcile owners of email CCIDs for this loan.")
        findings.append(
            Finding(
                code="assignment_conflict",
                rule="FR-03",
                message=actions[-1],
                blocks=["update", "closure"],
                evidence_ids=[],
            )
        )
    if inputs.assigned_team == "Inquiry" and (
        inputs.channel in {"chat", "call"} or inputs.queue == "Credit Reporting"
    ):
        actions.append("Manager must correct the channel/queue assignment.")
        findings.append(
            Finding(
                code="manager_assignment",
                rule="FR-03",
                message=actions[-1],
                blocks=["update", "closure"],
                evidence_ids=[],
            )
        )
    special = list(inputs.special_routes)
    if inputs.credit_error or inputs.modification_error:
        special.append(
            SpecialRoute(
                route="Compliance",
                rule="RULE-04",
                reason="Alleged credit-reporting or specific modification error: Customer Upset / Compliance.",
            )
        )
        actions.append("Coordinate Customer Upset / Compliance assignment with the manager.")
    restrictions = sorted({r for rule in special for r in rule.restrictions})
    routes = {rule.route for rule in special}
    route, rule, reason = (
        None,
        "assessment_required",
        "Determine inquiry/dispute assessment from the correspondence.",
    )
    if len(routes) > 1:
        route, rule = "Supervisory disposition", "RULE-08"
        reason = "Conflicting special routes require a supervisor or specialist decision."
        findings.append(
            Finding(
                code="special_route_conflict",
                rule=rule,
                message=reason,
                blocks=["response", "update", "closure"],
                evidence_ids=[],
            )
        )
        actions.append("Obtain supervisory disposition while preserving all restrictions.")
    elif special:
        route = special[0].route
        rule = ", ".join(sorted({item.rule for item in special}))
        reason = " ".join(item.reason for item in special)
    elif inputs.assessment == "inquiry":
        route, rule, reason = (
            "Inquiry",
            "RULE-03",
            "Neutral inquiry; the dispute-age threshold does not apply.",
        )
    elif inputs.assessment == "dispute" and aging.workdays is not None:
        route = "Disputes" if aging.workdays <= 20 else "Inquiry"
        rule = "RULE-01" if aging.workdays <= 20 else "RULE-02"
        reason = f"Ordinary dispute at {aging.workdays} Eastern workdays from original receipt."
    if inputs.assessment == "unassessed" and not special:
        findings.append(
            Finding(
                code="assessment_missing",
                rule="FR-04",
                message=reason,
                blocks=["response", "update", "closure"],
                evidence_ids=[],
            )
        )
    return RoutingResult(
        route=route,
        assessment=inputs.assessment,
        rule=rule,
        reason=reason,
        restrictions=restrictions,
        required_actions=actions,
        findings=findings,
        aging=aging,
        inputs=inputs,
    )


def next_review(evaluation: datetime) -> datetime:
    local = evaluation.astimezone(EASTERN)
    while True:
        local += timedelta(days=1)
        if local.weekday() < 5:
            return local.astimezone(UTC)
