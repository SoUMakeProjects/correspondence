"""Read-only business assessment built from persisted inputs and actual files."""

from copy import deepcopy
from datetime import date
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.documents import document_path
from app.domain import DomainError
from app.fixture_data import load_fixture
from app.models import (
    ClientConfiguration,
    Concern,
    CorrespondenceCase,
    Evidence,
    Loan,
    SimulationInstance,
    SpecialistTask,
    TaxonomyEntry,
)
from app.repository import fingerprint, require_case
from app.routing import EASTERN, aware, next_review, route_case
from app.rule_contracts import (
    AssessmentReport,
    AttachmentCheck,
    ConcernPlan,
    Finding,
    RoutingInputs,
    TaskPlan,
)
from app.source_catalog import DATA_ROOT, read_json

POLICY = read_json(DATA_ROOT / "policies/phase3.v1.json")
POLICY_VERSION = POLICY["version"]


def decision_fingerprint(snapshot):
    """Operational status/sequence changes do not alter reviewed response content."""
    material = deepcopy(snapshot)
    for case in [material["case"], *material["related_cases"]]:
        for key in ("revision", "status", "updated_at"):
            case.pop(key, None)
    return fingerprint(material)


def finding(code, rule, message, blocks=(), evidence_ids=()):
    return Finding(
        code=code, rule=rule, message=message, blocks=list(blocks), evidence_ids=list(evidence_ids)
    )


def check_evidence(data_dir: Path, case, loan, evidence: Evidence) -> AttachmentCheck:
    details = evidence.details
    code, reason = "valid", "Evidence belongs to this case, loan and client."
    if evidence.case_id != case.id or details.get("ccid") != case.ccid:
        code, reason = (
            "wrong_case",
            "Evidence belongs to another or unidentified correspondence case.",
        )
    if details.get("loan_identifier") != loan.loan_identifier:
        code, reason = "wrong_loan", "Evidence belongs to another or unidentified loan."
    if details.get("client_code") != loan.client_code:
        code, reason = "wrong_client", "Evidence belongs to another or unidentified client."
    if code == "valid" and details.get("kind") != "record":
        try:
            document_path(data_dir, evidence)
        except DomainError as exc:
            code, reason = exc.code, exc.message
    return AttachmentCheck(
        evidence_id=evidence.id,
        title=evidence.title,
        valid=code == "valid",
        code=code,
        reason=reason,
    )


def task_matches(task, case, loan, scenario, task_type):
    request = task.request
    if (
        task.task_type != task_type
        or request.get("loan_identifier") != loan.loan_identifier
        or request.get("client_code") != loan.client_code
    ):
        return False
    context = loan.context
    if scenario == "DEMO-01":
        return request.get("requested_name") == context.get("requested_legal_name")
    if scenario == "DEMO-03":
        return request.get("tax_period") == context.get("tax_period") and request.get(
            "amount_minor"
        ) == context.get("tax_amount_minor")
    if scenario == "DEMO-04":
        return request.get("review_topic") == "bankruptcy_status_and_communication_restrictions"
    return False


def task_result_supported(task, context, valid_evidence):
    result = task.result or {}
    references = task.request.get("evidence_ids", [])
    if (
        task.status != "completed"
        or not result.get("reference")
        or not references
        or not set(references) <= set(valid_evidence)
    ):
        return False
    if task.task_type == "demo_profile_name_update":
        return (
            result.get("updated_name")
            == context.get("current_legal_name")
            == context.get("requested_legal_name")
            and result["reference"] == context.get("profile_update_result")
            and aware(result.get("completed_at")) is not None
        )
    if task.task_type == "demo_tax_schedule_review":
        return (
            result.get("confirmed_status") == context.get("tax_status")
            and result.get("scheduled_date") == context.get("tax_scheduled_date")
            and result.get("paid_at") == context.get("tax_paid_at")
            and result["reference"] == context.get("tax_schedule_verified_by")
        )
    if task.task_type == "demo_bankruptcy_status_review":
        return (
            result.get("status") == context.get("servicing_bankruptcy_status")
            and result["reference"] == context.get("specialist_determination")
            and result.get("communication_restriction") == context.get("communication_restriction")
            and any(
                e.details.get("facts", {}).get("reference") == result["reference"]
                and e.details.get("facts", {}).get("determination") == result.get("status")
                for e in valid_evidence.values()
            )
        )
    return False


def assess_case(session: Session, data_dir: Path, case_id: str) -> tuple[AssessmentReport, dict]:
    case = require_case(session, case_id)
    loan = session.get(Loan, case.loan_id)
    simulation = session.get(SimulationInstance, case.simulation_id)
    client = session.get(ClientConfiguration, loan.client_code)
    evidence = list(
        session.scalars(select(Evidence).where(Evidence.case_id == case.id).order_by(Evidence.id))
    )
    concerns = list(
        session.scalars(select(Concern).where(Concern.case_id == case.id).order_by(Concern.id))
    )
    related = list(
        session.scalars(
            select(CorrespondenceCase)
            .where(
                CorrespondenceCase.loan_id == loan.id,
                CorrespondenceCase.simulation_id == case.simulation_id,
            )
            .order_by(CorrespondenceCase.id)
        )
    )
    tasks = list(
        session.scalars(
            select(SpecialistTask)
            .where(SpecialistTask.case_id.in_([c.id for c in related]))
            .order_by(SpecialistTask.id)
        )
    )
    scenario, context = simulation.scenario_key, loan.context
    policy = POLICY["scenarios"].get(scenario, {}) if simulation.fixture_version == "1" else {}
    findings = []
    if context.get("mail_intake") and not policy:
        findings.append(
            finding(
                "custom_procedure_review",
                "FR-06",
                "Review this request's topics and establish a supported procedure before responding.",
                ["response", "update", "closure"],
            )
        )
    raw_routing = context.get(
        "routing",
        {
            "assessment": policy.get("assessment", "unassessed"),
            "credit_error": policy.get("credit_error", False),
            "channel": "email" if policy else "unknown",
            "queue": "Inquiry" if policy else "unknown",
        },
    )
    try:
        inputs = RoutingInputs.model_validate(raw_routing)
    except ValidationError:
        inputs = RoutingInputs()
        findings.append(
            finding(
                "invalid_routing_inputs",
                "FR-04",
                "Routing facts require correction.",
                ["response", "update", "closure"],
            )
        )
    if inputs.channel == "email":
        inputs.email_owners = [
            c.owner
            for c in related
            if c.id == case.id or (c.classification or {}).get("channel", inputs.channel) == "email"
        ]
    routing = route_case(case.original_received_at, simulation.evaluation_at, inputs)
    findings.extend(routing.findings)
    for restriction in routing.restrictions:
        blocks = (
            ["response", "update", "closure"]
            if restriction in {"no_work", "no_contact"}
            else ["update"]
        )
        findings.append(
            finding(
                restriction,
                "RULE-08",
                f"Active special restriction: {restriction.replace('_', ' ')}.",
                blocks,
            )
        )
    if routing.route is None and inputs.assessment == "dispute":
        findings.append(
            finding(
                "route_unresolved",
                "BRD-8.2",
                "Correct the original receipt clock before ordinary dispute handling.",
                ["response", "update", "closure"],
            )
        )

    attachments = [check_evidence(data_dir, case, loan, e) for e in evidence]
    valid = {
        e.id: e
        for e, checked in zip(evidence, attachments)
        if checked.valid and (e.effective_at is None or e.effective_at <= simulation.evaluation_at)
    }
    docs = {e.details.get("key"): e for e in valid.values() if e.details.get("kind") != "record"}
    records = [e for e in valid.values() if e.details.get("kind") == "record"]
    if not records or not any(e.details.get("facts") == context for e in records):
        findings.append(
            finding(
                "servicing_evidence_missing",
                "FR-08",
                "Current servicing facts lack a matching evidence snapshot.",
                ["response", "update", "closure"],
            )
        )
    for e, checked in zip(evidence, attachments):
        if not checked.valid:
            findings.append(finding(checked.code, "FR-19", checked.reason, ["closure"], [e.id]))
        if e.effective_at and e.effective_at > simulation.evaluation_at:
            findings.append(
                finding(
                    "future_evidence",
                    "FR-08",
                    "Evidence is later than the evaluation clock.",
                    ["response", "update", "closure"],
                    [e.id],
                )
            )

    recipient = context.get("authorized_recipient")
    role, restriction = context.get("requester_role"), context.get("communication_restriction")
    authority_docs = [e.details.get("facts", {}) for e in docs.values()]
    borrower_verified = role == "borrower" and bool(context.get("borrower_email"))
    other_verified = role in {
        "co_borrower",
        "authorized_representative",
        "sii",
        "executor",
        "attorney",
    } and any(
        f.get("authorized_role") == role and f.get("authorization_verified") is True
        for f in authority_docs
    )
    if not borrower_verified and not other_verified:
        findings.append(
            finding(
                "requester_authority_missing",
                "FR-07",
                "Obtain evidence for the requester's specific role and authority.",
                ["response", "update", "closure"],
            )
        )
    if restriction == "representative_only":
        if not (
            context.get("representation_verified") is True
            and any(
                f.get("representative_email") == recipient
                and f.get("authorization_verified") is True
                for f in authority_docs
            )
        ):
            findings.append(
                finding(
                    "representative_authority_missing",
                    "RULE-09",
                    "Verify the authorized representative and permitted destination.",
                    ["response", "update", "closure"],
                )
            )
    elif restriction == "cease_and_desist":
        reversal = any(f.get("written_cd_reversal") is True for f in authority_docs)
        findings.append(
            finding(
                "cease_and_desist",
                "RULE-09",
                "Written reversal requires approved processing before contact resumes."
                if reversal
                else "Active cease-and-desist; written reversal evidence is required.",
                ["response", "update", "closure"],
            )
        )
    elif restriction != "none":
        findings.append(
            finding(
                "communication_scope_missing",
                "RULE-09",
                "Establish the permitted communication scope.",
                ["response", "update", "closure"],
            )
        )
    elif recipient != context.get("borrower_email"):
        if not any(
            f.get("representative_email") == recipient and f.get("authorization_verified") is True
            for f in authority_docs
        ):
            findings.append(
                finding(
                    "recipient_unverified",
                    "FR-07",
                    "The destination is not supported by borrower or representative records.",
                    ["response", "closure"],
                )
            )
    if not recipient or any(
        context.get(key) and context[key] != recipient for key in ("ils_recipient", "csp_recipient")
    ):
        findings.append(
            finding(
                "recipient_conflict",
                "FR-07",
                "Resolve missing or conflicting ILS/CSP recipient records.",
                ["response", "closure"],
            )
        )
    snapshot = context.get("client_configuration", {})
    if not client or snapshot != {
        "code": client.code,
        "version": client.version,
        "display_name": client.display_name,
        **client.settings,
    }:
        findings.append(
            finding(
                "client_configuration_conflict",
                "FR-18",
                "Refresh and verify the case's client configuration snapshot.",
                ["response", "update", "closure"],
            )
        )
    if client and context.get("product") != client.settings.get("supported_product"):
        findings.append(
            finding(
                "product_policy_missing",
                "RULE-13",
                "This product requires a separate approved procedure, including HELOC identity checks.",
                ["response", "update", "closure"],
            )
        )

    taxonomy = (
        session.get(TaxonomyEntry, policy["taxonomy_id"]) if policy.get("taxonomy_id") else None
    )
    classification = (
        {
            k: getattr(taxonomy, k)
            for k in ("id", "work_type", "class_name", "subclass", "source_reference")
        }
        if taxonomy
        else None
    )
    if classification is None:
        findings.append(
            finding(
                "classification_mapping_missing",
                "GAP-08" if scenario == "DEMO-04" else "FR-06",
                "No approved operational mapping for this request. Preserve the topic and seek classification review.",
                ["closure"],
            )
        )
    if case.classification and (
        not classification
        or any(
            case.classification.get(k) != classification.get(k)
            for k in ("work_type", "class_name", "subclass")
        )
    ):
        findings.append(
            finding(
                "classification_conflict",
                "FR-06",
                "The stored classification does not match an approved complete taxonomy mapping.",
                ["update", "closure"],
            )
        )

    task_plans, completed = [], []
    for task in tasks:
        if task_matches(task, case, loan, scenario, policy.get("task_type")):
            supported = task_result_supported(task, context, valid)
            completed_at = aware((task.result or {}).get("completed_at"))
            if completed_at and completed_at > simulation.evaluation_at:
                supported = False
            if supported:
                completed.append(task)
            task_plans.append(
                TaskPlan(
                    task_id=task.id,
                    task_type=task.task_type,
                    action="reuse",
                    result_supported=supported,
                    reason="Reuse the relevant existing task; no duplicate action is needed.",
                )
            )
            if task.status == "completed" and not supported:
                findings.append(
                    finding(
                        "task_result_unsupported",
                        "RULE-05",
                        "Completed status lacks a consistent, evidenced result.",
                        ["update", "closure"],
                    )
                )
        elif task.task_type == policy.get("task_type"):
            task_plans.append(
                TaskPlan(
                    task_id=task.id,
                    task_type=task.task_type,
                    action="inspect_exception",
                    result_supported=False,
                    reason="Task type matches but loan, client or requested action does not.",
                )
            )
            findings.append(
                finding(
                    "task_scope_conflict", "RULE-05", task_plans[-1].reason, ["update", "closure"]
                )
            )

    disposition, reason, pending_owner = (
        "resolved",
        "Supported information is available for a response.",
        None,
    )
    if scenario == "DEMO-01":
        signed = docs.get("signed-request")
        legal = docs.get("legal-document")
        sf, lf = (
            (signed.details["facts"] if signed else {}),
            (legal.details["facts"] if legal else {}),
        )
        legal_ok = (
            lf.get("document_received") is True
            and lf.get("new_name") == context.get("requested_legal_name")
            and lf.get("previous_name")
            == (
                completed[0].result.get("previous_name")
                if completed
                else context.get("current_legal_name")
            )
        )
        try:
            signed_date = date.fromisoformat(sf.get("signed_date", ""))
        except (ValueError, TypeError):
            signed_date = None
        signed_ok = (
            sf.get("signed") is True
            and signed_date is not None
            and signed_date <= simulation.evaluation_at.astimezone(EASTERN).date()
            and sf.get("requested_name") == context.get("requested_legal_name")
        )
        if not signed_ok or not legal_ok:
            missing = []
            if not signed_ok:
                missing.append("a signed, dated handwritten request matching the requested name")
            if not legal_ok:
                missing.append("a legal document proving the name change")
            disposition, reason = (
                "pending_borrower",
                "Request "
                + " and ".join(missing)
                + "; obtain identity evidence if it remains unproven.",
            )
            findings.append(
                finding("name_change_evidence_missing", "RULE-13", reason, ["update", "closure"])
            )
        elif not completed:
            disposition, reason = (
                "pending_department",
                "Documents support review of the update; a completed update result is still required.",
            )
            pending_owner = "Demo Servicing Team"
    elif scenario == "DEMO-02" and "amortization" not in docs:
        disposition, reason, pending_owner = (
            "pending_department",
            "Obtain a readable amortization schedule for this case and loan.",
            "Demo Records Team",
        )
        findings.append(finding("required_attachment_missing", "FR-19", reason, ["closure"]))
    elif scenario == "DEMO-03":
        bill = docs.get("tax-bill")
        if bill and any(
            bill.details["facts"].get(field) != context.get(canonical)
            for field, canonical in (
                ("amount_minor", "tax_amount_minor"),
                ("due_date", "tax_due_date"),
                ("payee", "tax_payee"),
            )
        ):
            findings.append(
                finding(
                    "tax_evidence_conflict",
                    "FR-15",
                    "The tax bill and servicing record disagree on amount, due date or payee.",
                    ["response", "update", "closure"],
                    [bill.id],
                )
            )
        if (
            "tax-bill" not in docs
            or not context.get("tax_bill_received_at")
            or not context.get("tax_scheduled_date")
            or context.get("tax_status") not in {"scheduled", "paid"}
        ):
            disposition, reason, pending_owner = (
                "pending_department",
                "Reconcile the bill receipt and payment schedule with the Tax Team.",
                "Demo Tax Team",
            )
        else:
            reason = "Confirm bill receipt and the supported payment schedule. Scheduled payment does not mean disbursement."
    elif scenario == "DEMO-04":
        if not completed:
            disposition, reason, pending_owner = (
                "pending_department",
                "Reconcile the court dismissal and imported discharge with the existing bankruptcy specialist task.",
                "Demo Bankruptcy Team",
            )
            findings.append(
                finding("bankruptcy_determination_required", "FR-15", reason, ["update", "closure"])
            )
        else:
            disposition, reason, pending_owner = (
                "referred",
                "Use the supported dismissal determination for a Compliance handoff; retain representative-only communication and the classification exception.",
                "Demo Compliance Team",
            )
    elif scenario == "DEMO-05":
        intent = context.get("eft_intent")
        if intent not in {"incoming_payment", "outgoing_refund", "heloc_draw"}:
            disposition, reason = (
                "pending_borrower",
                "Clarify whether the EFT is an incoming payment, outgoing refund or HELOC draw.",
            )
            findings.append(finding("eft_intent_missing", "FR-12", reason, ["update", "closure"]))
        else:
            disposition, reason = (
                "pending_borrower",
                f"For the {intent.replace('_', ' ')}, obtain the applicable signed consent and verified instructions; clarification alone does not authorize funds movement.",
            )
            findings.append(
                finding("eft_authorization_required", "FR-12", reason, ["update", "closure"])
            )
    elif not policy:
        disposition, reason = (
            "pending_department",
            "A reviewer must establish this case's supported procedure and concern dispositions.",
        )
        pending_owner = "Demo supervisor"
    if not concerns:
        findings.append(
            finding(
                "concerns_missing",
                "FR-09",
                "Identify all borrower concerns before responding.",
                ["response", "closure"],
            )
        )
    known_concerns = set(load_fixture(scenario, "base").concerns) if policy else set()
    if policy and context.get("mail_intake"):
        known_concerns = set(context["mail_intake"]["concerns"])
    concern_plans = [
        ConcernPlan(
            concern_id=c.id,
            description=c.description,
            disposition=disposition,
            reason=reason,
            evidence_ids=list(valid),
            owner=(pending_owner or "Borrower via case owner")
            if disposition != "resolved"
            else None,
            next_review_at=next_review(simulation.evaluation_at)
            if disposition != "resolved"
            else None,
            resume_requirement=reason if disposition != "resolved" else None,
        )
        for c in concerns
    ]
    for concern in concern_plans:
        if concern.description not in known_concerns:
            concern.disposition = "pending_department"
            concern.reason = "This additional concern requires its own researched disposition."
            concern.owner = "Demo reviewer"
            concern.next_review_at = next_review(simulation.evaluation_at)
            concern.resume_requirement = concern.reason
            findings.append(
                finding("additional_concern_unassessed", "FR-09", concern.reason, ["closure"])
            )
            if disposition == "resolved":
                disposition = "pending_department"
    status = {
        "resolved": "ready_for_response",
        "pending_borrower": "waiting_for_borrower",
        "pending_department": "waiting_on_department",
        "referred": "specialist_handoff",
    }[disposition]
    if any(
        "response" in f.blocks or f.code in {"assignment_conflict", "manager_assignment"}
        for f in findings
    ):
        status = "review_exception"
    actions = list(routing.required_actions)
    actions += [f"Reuse task {t.task_id}." for t in task_plans if t.action == "reuse"]
    if not any("response" in f.blocks for f in findings):
        actions.append(
            "Prepare a supported response."
            if disposition == "resolved"
            else "Prepare an interim request or permitted specialist referral; keep the case pending."
        )
    if (
        scenario == "DEMO-01"
        and disposition == "pending_department"
        and not any("update" in f.blocks for f in findings)
    ):
        actions.append("Prepare the distinct authorized name update for the later simulator.")
    if not actions:
        actions.append("Resolve the listed exceptions with the assigned reviewer.")

    def serialize(rows):
        return [
            {
                column.name: (
                    getattr(row, column.name).isoformat()
                    if hasattr(getattr(row, column.name), "isoformat")
                    else getattr(row, column.name)
                )
                for column in row.__table__.columns
            }
            for row in rows
        ]

    snapshot = {
        "case": serialize([case])[0],
        "loan": serialize([loan])[0],
        "simulation": serialize([simulation])[0],
        "evidence": serialize(evidence),
        "concerns": serialize(concerns),
        "tasks": serialize(tasks),
        "related_cases": serialize(related),
        "client": serialize([client])[0] if client else None,
        "policy": POLICY,
        "taxonomy": classification,
        "file_checks": [a.model_dump() for a in attachments],
    }
    return AssessmentReport(
        case_id=case.id,
        case_revision=case.revision,
        policy_version=POLICY_VERSION,
        evaluation_at=simulation.evaluation_at,
        input_hash=decision_fingerprint(snapshot),
        evidence_versions={e.id: e.version for e in evidence},
        client_version=client.version if client else None,
        routing=routing,
        classification=classification,
        disposition=status,
        review_required=bool(
            client and client.settings.get("default_review_mode") == "review_required"
        ),
        authorized_recipient=recipient,
        permitted_actions=actions,
        findings=findings,
        concerns=concern_plans,
        tasks=task_plans,
        attachments=attachments,
    ), snapshot
