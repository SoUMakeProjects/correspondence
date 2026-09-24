"""Fail-closed structured response and durable completion checks.

Free prose cannot be proved by a citation list. This phase accepts a controlled
rendering of checked claims/dispositions; later drafting must use a reviewed
adapter for additional prose instead of treating these checks as an NLP oracle.
"""

from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessment import POLICY, POLICY_VERSION, assess_case, finding
from app.catalogs import search_knowledge
from app.domain import DomainError
from app.models import (
    ActionReceipt,
    Concern,
    CorrespondenceCase,
    FinalNote,
    IndexedPackage,
    Loan,
    OutboxEntry,
    ResponseDraft,
    ReviewDecision,
)
from app.repository import fingerprint
from app.rule_contracts import DraftCandidate, ValidationReport
from app.simulators.artifacts import sent_matches, verify_package, verify_sent_files

LABELS = {
    "loan_identifier": "Loan",
    "tax_amount_minor": "Tax amount",
    "tax_due_date": "Tax due date",
    "tax_scheduled_date": "Scheduled tax payment date",
    "tax_status": "Tax payment status",
    "tax_bill_received_at": "Tax bill received",
    "tax_paid_at": "Tax payment disbursed",
    "current_legal_name": "Current legal name",
    "bankruptcy_status": "Specialist bankruptcy determination",
    "eft_intent": "EFT purpose",
    "task_completed": "Completed action reference",
    "document_attached": "Attached document",
}


def validate_response(session: Session, data_dir: Path, case_id: str, candidate: DraftCandidate):
    assessment, snapshot = assess_case(session, data_dir, case_id)
    findings = [f for f in assessment.findings if "response" in f.blocks]
    context, loan = snapshot["loan"]["context"], snapshot["loan"]
    scenario = snapshot["simulation"]["scenario_key"]
    client = snapshot["client"]
    evidence = {e["id"]: e for e in snapshot["evidence"]}
    checks = {a.evidence_id: a for a in assessment.attachments}
    tasks = {t["id"]: t for t in snapshot["tasks"]}

    def reject(code, message, rule="FR-18", ids=()):
        findings.append(finding(code, rule, message, ["response", "closure"], ids))

    if candidate.case_revision != snapshot["case"]["content_revision"]:
        reject("stale_case_revision", "The draft was prepared against an earlier case revision.")
    if candidate.evidence_versions != assessment.evidence_versions:
        reject(
            "stale_evidence", "Refresh the complete evidence version snapshot before responding."
        )
    if (
        not client
        or candidate.client_code != loan["client_code"]
        or candidate.client_version != client["version"]
    ):
        reject("wrong_client", "The draft client and version must match current servicing records.")
    if not client or candidate.sender != client["settings"].get("sender_email"):
        reject("wrong_sender", "Use the verified sender for this client.")
    if candidate.recipient != assessment.authorized_recipient:
        reject(
            "wrong_recipient", "Use the verified recipient and active representation restrictions."
        )

    proposed = {c.concern_id: c for c in candidate.concerns}
    required = {c.concern_id: c for c in assessment.concerns}
    if len(proposed) != len(candidate.concerns) or set(proposed) != set(required):
        reject(
            "concern_coverage", "Every current concern must have exactly one disposition.", "FR-09"
        )
    for identity, concern in proposed.items():
        if identity in required and concern.disposition != required[identity].disposition:
            reject(
                "unsupported_disposition",
                "A concern disposition contradicts the supported assessment.",
                "FR-09",
            )
    if candidate.response_type == "final_resolution" and any(
        c.disposition != "resolved" for c in assessment.concerns
    ):
        reject(
            "unresolved_concerns",
            "A final resolution cannot leave concerns pending or merely referred.",
            "FR-20",
        )
    if candidate.response_type == "repetitive":
        reject(
            "repetitive_approval_missing",
            "The selected scenarios supply no approved identical-repeat determination.",
            "RULE-06",
        )
    if candidate.response_type == "referral" and not any(
        c.disposition == "referred" for c in assessment.concerns
    ):
        reject("unsupported_referral", "A referral requires a supported specialist disposition.")
    if candidate.response_type == "information_request" and not any(
        c.disposition.startswith("pending") for c in assessment.concerns
    ):
        reject(
            "unsupported_information_request",
            "Record the missing information and resume requirement before requesting it.",
        )

    selected = set(candidate.attachment_ids)
    if len(selected) != len(candidate.attachment_ids):
        reject("duplicate_attachment", "Each attachment must be selected once.")
    relevant_keys = POLICY["scenarios"].get(scenario, {}).get("required_documents", [])
    for identity in selected:
        row, checked = evidence.get(identity), checks.get(identity)
        if not row or not checked or not checked.valid or row["details"].get("kind") == "record":
            reject(
                "invalid_attachment",
                "An attachment is missing, unreadable, changed or outside this case/loan/client.",
                "FR-19",
                [identity],
            )
        elif row["details"].get("key") not in relevant_keys:
            reject(
                "irrelevant_attachment",
                "This attachment is not relevant to the selected response procedure.",
                "FR-19",
                [identity],
            )
    if (
        scenario == "DEMO-02"
        and candidate.response_type == "final_resolution"
        and not any(
            e["id"] in selected and e["details"].get("key") == "amortization"
            for e in evidence.values()
        )
    ):
        reject(
            "required_attachment_missing",
            "Fulfillment requires the actual current amortization schedule.",
            "FR-19",
        )

    lines, seen, attached_claims = [], {}, set()
    for claim in candidate.claims:
        row = evidence.get(claim.evidence_id)
        facts = row["details"].get("facts", {}) if row else {}
        actual = context.get(claim.field)
        cited = facts.get(claim.field)
        supported = bool(row and checks[claim.evidence_id].valid)
        if claim.field == "loan_identifier":
            actual = loan["loan_identifier"]
            cited = row["details"].get("loan_identifier") if row else None
        elif claim.field == "tax_amount_minor":
            cited = facts.get("tax_amount_minor", facts.get("amount_minor"))
        elif claim.field == "tax_due_date":
            cited = facts.get("tax_due_date", facts.get("due_date"))
        elif claim.field == "bankruptcy_status":
            actual = context.get("servicing_bankruptcy_status")
            cited = facts.get("determination", facts.get("servicing_bankruptcy_status"))
            supported = (
                supported
                and bool(context.get("specialist_determination"))
                and any(
                    t.result_supported and t.task_type == "demo_bankruptcy_status_review"
                    for t in assessment.tasks
                )
            )
        elif claim.field == "current_legal_name":
            supported = supported and any(
                t.result_supported and t.task_type == "demo_profile_name_update"
                for t in assessment.tasks
            )
        elif claim.field == "task_completed":
            task = tasks.get(claim.evidence_id)
            supported = any(
                t.task_id == claim.evidence_id and t.result_supported for t in assessment.tasks
            )
            actual = cited = (task.get("result") or {}).get("reference") if task else None
        elif claim.field == "document_attached":
            actual = cited = row["title"] if row else None
            supported = supported and claim.evidence_id in selected
            attached_claims.add(claim.evidence_id)
        if claim.field in {"tax_status", "tax_paid_at"} and (
            claim.value == "paid" or (claim.field == "tax_paid_at" and claim.value is not None)
        ):
            supported = (
                supported
                and context.get("tax_status") == "paid"
                and bool(context.get("tax_paid_at") and context.get("tax_payment_reference"))
            )
        if (
            claim.field != "document_attached"
            and claim.field in seen
            and seen[claim.field] != claim.value
        ):
            reject(
                "contradictory_claims",
                f"Conflicting statements about {LABELS[claim.field].lower()}.",
                "FR-15",
            )
        seen[claim.field] = claim.value
        if (
            not supported
            or actual is None
            or type(claim.value) is not type(actual)
            or claim.value != actual
            or cited != actual
        ):
            reject(
                "unsupported_claim",
                f"Evidence does not establish the claimed {LABELS[claim.field].lower()}.",
                "FR-15",
                [claim.evidence_id],
            )
        value = (
            f"${claim.value / 100:,.2f}"
            if claim.field == "tax_amount_minor" and type(claim.value) is int
            else str(claim.value).replace("_", " ")
        )
        lines.append(f"{LABELS[claim.field]}: {value}.")
    if attached_claims != selected:
        reject(
            "attachment_statement_mismatch",
            "The attached-document statements and selected files must agree exactly.",
            "FR-19",
        )
    required_claims = {
        "DEMO-01": {"current_legal_name", "task_completed"},
        "DEMO-02": {"document_attached"},
        "DEMO-03": {"tax_bill_received_at", "tax_status", "tax_scheduled_date"},
    }
    if any(c.disposition == "resolved" for c in candidate.concerns) and not required_claims.get(
        scenario, set()
    ) <= set(seen):
        reject(
            "resolution_support_missing",
            "The response lacks the facts needed to answer every resolved concern.",
            "FR-09",
        )

    disclosures = search_knowledge(session, scenario, loan["client_code"], kind="disclosure")
    applicable = {d["key"]: d for d in disclosures}
    expected = client["settings"].get("disclosure_keys", []) if client else []
    if set(candidate.disclosure_ids) != set(expected) or any(
        k not in applicable for k in candidate.disclosure_ids
    ):
        reject(
            "disclosure_mismatch", "Include the currently curated demo disclosures for this client."
        )
    letter = (
        fulfillment_letter(scenario, candidate, snapshot, evidence, lines, applicable, client)
        or name_change_letter(
            scenario,
            candidate,
            snapshot,
            evidence,
            checks,
            tasks,
            lines,
            applicable,
            client,
            assessment,
        )
        or tax_letter(
            scenario,
            candidate,
            snapshot,
            evidence,
            checks,
            tasks,
            lines,
            applicable,
            client,
            assessment,
        )
        or eft_letter(
            scenario,
            candidate,
            snapshot,
            evidence,
            checks,
            tasks,
            lines,
            applicable,
            client,
            assessment,
        )
    )
    body = letter or "\n".join(
        [
            {
                "interim_acknowledgment": "We are reviewing your correspondence.",
                "information_request": "Additional information is required to proceed.",
                "final_resolution": "Our response to your correspondence follows.",
                "referral": "Your concerns require specialist handling.",
                "repetitive": "This correspondence repeats a prior request.",
            }[candidate.response_type],
            *[f"{c.description}: {c.reason}" for c in assessment.concerns],
            *lines,
            *_disclosures(candidate, applicable),
        ]
    )
    if candidate.body is not None and candidate.body != body:
        reject(
            "unchecked_response_text",
            "Response text differs from the checked rendering. Added claims require structured verification or later review.",
            "FR-15",
        )
    final = candidate.response_type == "final_resolution"
    return ValidationReport(
        valid=not findings,
        policy_version=POLICY_VERSION,
        findings=findings,
        rendered_body=body,
        response_type=candidate.response_type,
        resulting_status="ready_for_response"
        if final
        else (
            assessment.disposition
            if assessment.disposition != "ready_for_response"
            else "under_review"
        ),
    )


def validate_completion(session: Session, data_dir: Path, case_id: str) -> ValidationReport:
    assessment, snapshot = assess_case(session, data_dir, case_id)
    findings = [f for f in assessment.findings if "closure" in f.blocks]
    draft = session.scalar(
        select(ResponseDraft)
        .where(ResponseDraft.case_id == case_id)
        .order_by(ResponseDraft.version.desc())
    )

    def reject(code, message):
        findings.append(finding(code, "FR-20", message, ["closure"]))

    body, response_type = "", None
    if not draft:
        reject(
            "response_not_prepared", "A validated final response and actual delivery are required."
        )
    else:
        try:
            candidate = DraftCandidate.model_validate(draft.validation.get("candidate"))
            report = validate_response(session, data_dir, case_id, candidate)
            findings.extend(report.findings)
            body, response_type = report.rendered_body, candidate.response_type
            if candidate.response_type != "final_resolution":
                reject(
                    "interim_cannot_close",
                    "An acknowledgment, information request or referral alone cannot close the case.",
                )
            if (
                draft.version != candidate.version
                or draft.case_revision != candidate.case_revision
                or draft.body != body
                or draft.recipient != candidate.recipient
                or draft.response_type != candidate.response_type
                or draft.evidence_versions != candidate.evidence_versions
                or draft.attachment_ids != candidate.attachment_ids
                or draft.disclosure_ids != candidate.disclosure_ids
                or draft.validation.get("input_hash") != assessment.input_hash
            ):
                reject(
                    "stale_draft",
                    "The stored draft or its evidence inputs changed after validation.",
                )
            review = session.scalar(
                select(ReviewDecision)
                .where(ReviewDecision.case_id == case_id)
                .order_by(ReviewDecision.created_at.desc(), ReviewDecision.id.desc())
            )
            if (
                assessment.review_required or draft.validation.get("review_required") or review
            ) and (
                not review
                or review.decision != "approve"
                or review.draft_id != draft.id
                or review.draft_version != draft.version
                or review.case_revision != snapshot["case"]["content_revision"]
                or review.content_hash
                != fingerprint(
                    {
                        "candidate": candidate.model_dump(mode="json"),
                        "input_hash": assessment.input_hash,
                    }
                )
            ):
                reject(
                    "approval_missing_or_stale",
                    "Current approval must match this draft, version and case revision.",
                )
        except ValidationError:
            reject(
                "draft_validation_missing",
                "The stored draft lacks a valid structured candidate snapshot.",
            )
    persisted = list(session.scalars(select(Concern).where(Concern.case_id == case_id)))
    if (
        not persisted
        or any(c.disposition != "resolved" for c in persisted)
        or any(c.disposition != "resolved" for c in assessment.concerns)
    ):
        reject(
            "concerns_incomplete",
            "All concerns require supported, persisted resolution before closure.",
        )

    def completed_receipt(identity, operation):
        action = session.get(ActionReceipt, identity)
        return bool(
            action
            and action.case_id == case_id
            and action.operation == operation
            and action.status == "simulated_complete"
            and action.result
        )

    sent = list(
        session.scalars(
            select(OutboxEntry)
            .join(ActionReceipt, OutboxEntry.action_id == ActionReceipt.id)
            .where(ActionReceipt.case_id == case_id)
        )
    )
    case = session.get(CorrespondenceCase, case_id)
    loan = session.get(Loan, case.loan_id)
    delivered = []
    for entry in sent:
        if (
            not draft
            or entry.draft_id != draft.id
            or entry.status != "sent"
            or not completed_receipt(entry.action_id, "csp.send")
            or not sent_matches(draft, case, loan, entry.sent_content)
        ):
            continue
        try:
            verify_sent_files(data_dir, entry.sent_content)
        except (DomainError, KeyError, TypeError):
            continue
        delivered.append(entry)
    if not delivered:
        reject(
            "delivery_missing",
            "No reconciled successful send exists for this exact response. Approved no-response exceptions are not supplied by these scenarios.",
        )
    packages = list(
        session.scalars(select(IndexedPackage).where(IndexedPackage.case_id == case_id))
    )
    indexed = False
    for package in packages:
        if delivered and completed_receipt(package.action_id, "onbase.index"):
            try:
                verify_package(data_dir, package, delivered[0], case, loan, draft)
                indexed = True
            except (DomainError, KeyError, TypeError):
                pass
    if not indexed:
        reject("index_missing", "A matching indexed package and verified stored file are required.")
    notes = list(session.scalars(select(FinalNote).where(FinalNote.case_id == case_id)))
    if not any(
        draft
        and n.department == "Servicing"
        and n.note_type == "INQ Email Reply"
        and n.details.get("standout_comment") is True
        and n.details.get("recipient") == draft.recipient
        and delivered
        and n.details.get("outbox_id") == delivered[0].id
        and n.content.strip()
        and completed_receipt(n.action_id, "ils.final_note")
        and draft
        and session.get(ActionReceipt, n.action_id)
        .payload.get("command", session.get(ActionReceipt, n.action_id).payload)
        .get("draft_id")
        == draft.id
        and n.details.get("draft_version") == draft.version
        for n in notes
    ):
        reject("final_note_missing", "The final ILS note must be recorded for this response.")
    if session.scalar(
        select(ActionReceipt.id).where(
            ActionReceipt.case_id == case_id, ActionReceipt.status == "uncertain"
        )
    ):
        reject("uncertain_action", "An uncertain action must be reconciled before closure.")
    return ValidationReport(
        valid=not findings,
        policy_version=POLICY_VERSION,
        findings=findings,
        rendered_body=body,
        response_type=response_type,
        resulting_status="closed"
        if not findings
        else "records_incomplete"
        if delivered
        and any(
            f.code in {"index_missing", "final_note_missing", "uncertain_action"} for f in findings
        )
        else assessment.disposition,
    )


MONTH_NAMES = (
    "January February March April May June July August September October November December"
).split()


def _long_date(value) -> str:
    text = value if isinstance(value, str) else value.isoformat()
    year, month, day = map(int, text[:10].split("-"))
    return f"{MONTH_NAMES[month - 1]} {day}, {year}"


def _salutation(name) -> str:
    return f"Dear {name},"


def _contact_paragraph(settings, lead="If you have questions") -> str:
    """Customer Care contact sentence built from client settings."""
    return (
        f"{lead}, please reply to this email or call Customer Care at "
        f"{settings.get('support_phone', '')}, {settings.get('support_hours', '')}."
    )


def _closing(client) -> list[str]:
    """'Thank you for choosing ...' plus 'Sincerely,' and the client signature."""
    brand = client["display_name"]
    return [
        f"Thank you for choosing {brand}.",
        "Sincerely,\n" + client["settings"].get("signature", brand),
    ]


def _disclosures(candidate, applicable) -> list[str]:
    """Content of the selected client disclosures that apply to this case."""
    return [applicable[k]["content"] for k in candidate.disclosure_ids if k in applicable]


def _letter(parts) -> str:
    """Join non-empty paragraphs with blank lines."""
    return "\n\n".join(p for p in parts if p.strip())


def fulfillment_letter(scenario, candidate, snapshot, evidence, lines, applicable, client):
    """Deterministic amortization fulfillment letter.

    Every variable part comes from persisted records: the case receipt, the loan record, the
    selected (already identity-checked) schedule's own facts, client configuration and the
    validated claim lines. The model contributes only structured choices, never prose.
    Returns None when the prerequisites are absent, so the generic rendering is used.
    """
    if scenario != "DEMO-02" or candidate.response_type != "final_resolution" or not client:
        return None
    schedule = next(
        (
            evidence[i]
            for i in candidate.attachment_ids
            if i in evidence and evidence[i]["details"].get("key") == "amortization"
        ),
        None,
    )
    facts = schedule["details"].get("facts", {}) if schedule else {}
    required = ("remaining_payments", "first_payment_date", "maturity_date")
    if not all(facts.get(k) for k in required):
        return None
    from app.documents import schedule_entries

    entries = schedule_entries(facts)
    settings = client["settings"]
    loan = snapshot["loan"]
    loan_id = loan["loan_identifier"]
    name = loan.get("borrower_display_name") or "Borrower"
    received = snapshot["case"]["original_received_at"]
    rate = facts.get("annual_rate_basis_points")
    payment = f"${entries[0]['payment'] / 100:,.2f}"
    paragraphs = [
        _salutation(name),
        f"Thank you for contacting {client['display_name']}. We received your request on "
        f"{_long_date(received)} for a current amortization schedule for your mortgage loan "
        f"ending in {loan_id[-4:]}.",
        f"As requested, the amortization schedule for loan {loan_id} is attached. It lists your "
        f"{facts['remaining_payments']} remaining scheduled monthly payments, beginning with the "
        f"payment due {_long_date(facts['first_payment_date'])}, and shows how each regular "
        f"principal and interest payment of {payment} is applied"
        + (f" at your fixed note rate of {rate / 100:.3f}%" if rate else "")
        + ". If each payment is made as scheduled, your loan will be paid in full with the "
        f"payment due {_long_date(facts['maturity_date'])}.",
        "Please keep in mind that the schedule reflects principal and interest only. It does not "
        "include escrow deposits for property taxes or homeowners insurance, and it is not a "
        "payoff statement. "
        + _contact_paragraph(
            settings, "If you need a payoff quote or have questions about your escrow account"
        ),
        *_closing(client),
        _reference_block(lines, None, renames=(("Attached document: ", "Enclosure: "),)),
        *_disclosures(candidate, applicable),
    ]
    return _letter(paragraphs)


def _reference_block(lines, loan_id, extra=(), renames=()):
    """Reference lines under the signature: loan number, fixed extras, then validated claims.

    "Loan: " claims are renamed to "Loan number: ". When no loan claim was made and ``loan_id``
    is given, a "Loan number" line is added first; pass ``None`` to omit it.
    """
    claimed = []
    for line in lines:
        for before, after in (("Loan: ", "Loan number: "), *renames):
            line = line.replace(before, after)
        claimed.append(line.rstrip("."))
    block = (
        []
        if loan_id is None or any(c.startswith("Loan number: ") for c in claimed)
        else [f"Loan number: {loan_id}"]
    )
    return "\n".join([*block, *extra, *[c for c in claimed if c not in extra]])


def name_change_letter(
    scenario, candidate, snapshot, evidence, checks, tasks, lines, applicable, client, assessment
):
    """Deterministic name-change letters (DEMO-01): the evidence request and the confirmation.

    As with the amortization letter, every variable part comes from persisted records: the case
    receipt, the loan record, the case's (identity-checked) documents, the completed ILS task
    result and client configuration. The model contributes only structured choices. Returns None
    when the prerequisites are absent, so the generic checked rendering is used instead.
    """
    if scenario != "DEMO-01" or not client:
        return None
    settings = client["settings"]
    brand = client["display_name"]
    loan = snapshot["loan"]
    context = loan["context"]
    loan_id = loan["loan_identifier"]
    current = context.get("current_legal_name") or loan.get("borrower_display_name") or "Borrower"
    requested = context.get("requested_legal_name")
    contact = _contact_paragraph(settings)
    closing = _closing(client)
    disclosures = _disclosures(candidate, applicable)

    if candidate.response_type == "information_request":
        if not requested or not any(
            f.code == "name_change_evidence_missing" for f in assessment.findings
        ):
            return None
        docs = {
            row["details"].get("key"): row["details"].get("facts", {})
            for identity, row in evidence.items()
            if identity in checks and checks[identity].valid
        }
        signed, legal = docs.get("signed-request", {}), docs.get("legal-document", {})
        signed_ok = (
            signed.get("signed") is True
            and bool(signed.get("signed_date"))
            and signed.get("requested_name") == requested
        )
        legal_ok = legal.get("document_received") is True and legal.get("new_name") == requested
        if signed_ok and legal_ok:
            return None
        signed_item = (
            "a written request to change your name that you have signed and dated by hand, "
            "showing both your current name and your new name"
        )
        legal_item = (
            "a copy of a legal document that shows your name change, such as a marriage "
            "certificate or marriage record, a divorce decree, or a court order for a name change"
        )
        if signed_ok:
            received = (
                "Thank you for including your signed and dated request, dated "
                f"{_long_date(signed['signed_date'])}. Before we can update our records, we also "
                f"need {legal_item}."
            )
        elif legal_ok:
            received = (
                "Thank you for including your legal name-change document. Before we can update "
                f"our records, we also need {signed_item}."
            )
        else:
            received = (
                "Before we can update our records, we need two documents from you:\n"
                f"- {signed_item[0].upper() + signed_item[1:]}.\n"
                f"- {legal_item[0].upper() + legal_item[1:]}."
            )
        mail_to = ", ".join(
            v
            for v in (
                settings.get("legal_name", brand),
                "Attn: Customer Correspondence",
                settings.get("mailing_address", ""),
            )
            if v
        )
        paragraphs = [
            _salutation(current),
            f"Thank you for contacting {brand}. We received your request on "
            f"{_long_date(snapshot['case']['original_received_at'])} to change the name on your "
            f"mortgage loan ending in {loan_id[-4:]} from {current} to {requested}.",
            received,
            "You can reply to this email and attach a clear, complete copy, or mail a copy to "
            f"{mail_to}. Please include your loan number with anything you send, and please do "
            "not send original documents.",
            "We have not changed the name on your loan yet. When we receive the document, we "
            "will review it, update our records and confirm the change to you in writing. Your "
            "loan terms, monthly payment and due date are not affected, so please continue to "
            "make your payments as scheduled.",
            contact,
            *closing,
            _reference_block(lines, loan_id, [f"Requested name: {requested}"]),
            *disclosures,
        ]
        return _letter(paragraphs)

    if candidate.response_type != "final_resolution":
        return None
    task = next(
        (
            tasks.get(c.evidence_id)
            for c in candidate.claims
            if c.field == "task_completed" and c.evidence_id in tasks
        ),
        None,
    )
    result = (task or {}).get("result") or {}
    updated, previous = result.get("updated_name"), result.get("previous_name")
    if not (updated and previous and result.get("completed_at")) or updated != current:
        return None
    paragraphs = [
        _salutation(updated),
        "Thank you for sending the documents we requested. We have reviewed your signed request "
        "and the supporting legal document, and we have updated the name on your mortgage loan "
        f"ending in {loan_id[-4:]}.",
        f"Our records now show your name as {updated}, replacing {previous}. The change was made "
        f"on {_long_date(result['completed_at'])}. Your future statements, letters and year-end "
        "mortgage interest statement will be issued in your new name.",
        "This change does not affect your loan terms, interest rate, monthly payment or due "
        "date, and no further action is needed from you. It updates your loan servicing records "
        "only. It does not change the name on your property deed or on your homeowners "
        "insurance policy; to update those, please contact your county recorder's office and "
        "your insurance provider.",
        contact,
        *closing,
        _reference_block(
            lines,
            loan_id,
            renames=(
                ("Current legal name: ", "Name on loan: "),
                ("Completed action reference: ", "Name change reference: "),
            ),
        ),
        *disclosures,
    ]
    return _letter(paragraphs)


def _eastern_long_date(value) -> str:
    """Long date of an instant as seen in America/New_York (calendar dates pass through)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    text = value if isinstance(value, str) else value.isoformat()
    if len(text) <= 10:
        return _long_date(text)
    moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        return _long_date(text)
    return _long_date(moment.astimezone(ZoneInfo("America/New_York")).date())


def tax_letter(
    scenario, candidate, snapshot, evidence, checks, tasks, lines, applicable, client, assessment
):
    """Deterministic tax-bill receipt and scheduled-payment letter (DEMO-03).

    Variable parts come from the case receipt, the loan record, the identity-checked tax bill
    (which the assessment has already reconciled with the servicing tax line), a supported Tax
    Team result, client configuration and the validated claims. "Scheduled" is never presented
    as "paid". Returns None when the prerequisites are absent, so the generic checked rendering
    is used instead.
    """
    if scenario != "DEMO-03" or candidate.response_type != "final_resolution" or not client:
        return None
    context = snapshot["loan"]["context"]
    claimed = {c.field: c.value for c in candidate.claims}
    if not {"tax_bill_received_at", "tax_status", "tax_scheduled_date"} <= set(claimed):
        return None
    if (
        claimed["tax_status"] != "scheduled"
        or context.get("tax_status") != "scheduled"
        or context.get("tax_paid_at") is not None
        or claimed["tax_scheduled_date"] != context.get("tax_scheduled_date")
        or claimed["tax_bill_received_at"] != context.get("tax_bill_received_at")
    ):
        return None
    bill = next(
        (
            row["details"].get("facts", {})
            for identity, row in evidence.items()
            if row["details"].get("key") == "tax-bill"
            and identity in checks
            and checks[identity].valid
        ),
        None,
    )
    required = ("tax_period", "tax_payee", "tax_amount_minor", "tax_due_date")
    if (
        not bill
        or not all(context.get(k) for k in required)
        or bill.get("amount_minor") != context["tax_amount_minor"]
        or bill.get("due_date") != context["tax_due_date"]
        or bill.get("payee") != context["tax_payee"]
    ):
        return None
    review = next(
        (
            (tasks.get(t.task_id) or {}).get("result") or {}
            for t in assessment.tasks
            if t.task_type == "demo_tax_schedule_review" and t.result_supported
        ),
        {},
    )
    reviewed = review.get("reference")
    settings = client["settings"]
    brand = client["display_name"]
    loan = snapshot["loan"]
    loan_id = loan["loan_identifier"]
    name = loan.get("borrower_display_name") or "Borrower"
    period, payee = context["tax_period"], context["tax_payee"]
    amount = f"${context['tax_amount_minor'] / 100:,.2f}"
    due = _long_date(context["tax_due_date"])
    scheduled = _long_date(context["tax_scheduled_date"])
    received = _eastern_long_date(context["tax_bill_received_at"])
    checked = (
        "Our Tax Team has also reviewed the bill against the tax information on your escrow "
        "account and confirmed the payment schedule."
        if reviewed
        else "The bill matches the tax information on file for your escrow account."
    )
    formatted = {
        "tax_due_date": f"Due date: {due}",
        "tax_bill_received_at": f"Bill received: {received}",
        "tax_scheduled_date": f"Scheduled payment date: {scheduled}",
        "tax_status": "Payment status: Scheduled (not yet paid)",
        "tax_amount_minor": f"Installment amount: {amount}",
    }
    order = ("tax_due_date", "tax_bill_received_at", "tax_scheduled_date", "tax_status")
    extra = [
        f"Tax bill: {period}, {payee}",
        f"Installment amount: {amount}",
        *[formatted[f] for f in order if f in claimed],
        *([f"Tax Team review reference: {reviewed}"] if reviewed else []),
    ]
    others = [
        line
        for claim, line in zip(candidate.claims, lines, strict=False)
        if claim.field not in formatted and claim.field != "loan_identifier"
    ]
    paragraphs = [
        _salutation(name),
        f"Thank you for contacting {brand}. We received your email on "
        f"{_eastern_long_date(snapshot['case']['original_received_at'])} about the {period} bill "
        f"for the property that secures your mortgage loan ending in {loan_id[-4:]}.",
        f"We have your bill. Our records show that we received the {payee}'s bill for "
        f"{amount} on {received}. {checked}",
        f"The installment is scheduled to be paid from your escrow account on {scheduled}, "
        f"before the {due} due date. Please note that it has not been paid yet: this letter "
        "confirms the scheduled payment only. To avoid paying the bill twice, please do not pay "
        "this installment yourself.",
        "After the payment is sent, it will appear as a tax disbursement in the escrow activity "
        "on your next monthly mortgage statement and on your annual escrow account statement. "
        f"The {payee}'s records may take a few business days to show the payment.",
        _contact_paragraph(
            settings, "If you have questions about this bill or your escrow account"
        ),
        *_closing(client),
        _reference_block(
            others,
            loan_id,
            extra,
            renames=(("Completed action reference: ", "Tax Team review reference: "),),
        ),
        *_disclosures(candidate, applicable),
    ]
    return _letter(paragraphs)


EFT_REQUESTS = {
    "outgoing_refund": "Refund by electronic transfer",
    "incoming_payment": "Automatic monthly payments by electronic transfer",
    "heloc_draw": "Line-of-credit draw by electronic transfer",
}


def eft_letter(
    scenario, candidate, snapshot, evidence, checks, tasks, lines, applicable, client, assessment
):
    """Deterministic EFT letters (DEMO-05): the clarification request and, once the purpose is
    known, the request for the matching signed authorization and verified bank instructions.

    Variable parts come from the case receipt, the loan record (product, escrow analysis and
    payment figures), the assessed pending requirement, client configuration and the validated
    claims. No letter says money has moved or will move before authorization. Returns None when
    the prerequisites are absent, so the generic checked rendering is used instead.
    """
    if scenario != "DEMO-05" or candidate.response_type != "information_request" or not client:
        return None
    codes = {f.code for f in assessment.findings}
    context = snapshot["loan"]["context"]
    intent = context.get("eft_intent")
    if "eft_intent_missing" in codes:
        variant = None
    elif "eft_authorization_required" in codes and intent in EFT_REQUESTS:
        variant = intent
    else:
        return None
    settings = client["settings"]
    brand = client["display_name"]
    loan = snapshot["loan"]
    loan_id = loan["loan_identifier"]
    name = loan.get("borrower_display_name") or "Borrower"
    surplus = context.get("escrow_surplus_minor")
    refund = f"${surplus / 100:,.2f}" if isinstance(surplus, int) and surplus > 0 else None
    payment = context.get("new_payment_minor")
    payment_text = (
        f"${payment / 100:,.2f} beginning {_long_date(context['new_payment_effective_date'])}"
        if isinstance(payment, int) and context.get("new_payment_effective_date")
        else None
    )
    mail_to = ", ".join(
        v
        for v in (
            settings.get("legal_name", brand),
            "Attn: Customer Correspondence",
            settings.get("mailing_address", ""),
        )
        if v
    )
    formatted = {"eft_intent": lambda v: f"Request: {EFT_REQUESTS.get(v, v)}"}
    claimed = [
        formatted[c.field](c.value)
        for c in candidate.claims
        if c.field in formatted and isinstance(c.value, str)
    ]
    others = [
        line
        for claim, line in zip(candidate.claims, lines, strict=False)
        if claim.field not in formatted and claim.field != "loan_identifier"
    ]
    contact = _contact_paragraph(settings)
    received = _eastern_long_date(snapshot["case"]["original_received_at"])

    if variant is None:
        refund_item = (
            f"A refund sent to you. For example, the escrow surplus refund of {refund}"
            + (
                f" from your escrow account statement dated "
                f"{_long_date(context['escrow_analysis_date'])}"
                if context.get("escrow_analysis_date")
                else ""
            )
            + " could be deposited into your bank account instead of being mailed as a check."
            if refund
            else "A refund sent to you, such as an escrow surplus refund, deposited into your "
            "bank account instead of being mailed as a check."
        )
        payment_item = (
            "Automatic monthly payments. Your mortgage payment"
            + (f" ({payment_text})" if payment_text else "")
            + " would be drawn from your bank account each month instead of being paid by check."
        )
        paragraphs = [
            _salutation(name),
            f"Thank you for contacting {brand}. We received your email on {received} asking us "
            "to use an electronic funds transfer (EFT) instead of a paper check for your "
            f"mortgage loan ending in {loan_id[-4:]}.",
            "We want to be sure we set up the right thing. On a mortgage account, an electronic "
            "transfer can mean one of three different things, and each one needs its own "
            "authorization:\n"
            f"- {refund_item}\n"
            f"- {payment_item}\n"
            "- A draw from a line of credit. If you have a home equity line of credit, money "
            "would be advanced from the line to your bank account.",
            "Please reply to this email and tell us which one you mean. Once we know, we will "
            "tell you exactly what we need from you to set it up.",
            "We have not made any changes to your account. No money will be moved electronically "
            "until we know what you are asking for and have received and verified your written "
            "authorization. In the meantime, please continue to make your monthly payments as "
            "you do now.",
            contact,
            *_closing(client),
            _reference_block(
                others,
                loan_id,
                ["Request: Electronic funds transfer (EFT)", f"Request received: {received}"],
            ),
            *_disclosures(candidate, applicable),
        ]
        return _letter(paragraphs)

    bank_proof = (
        "A voided check for that account, or a letter from your bank on its letterhead, showing "
        "the account holder's name and the routing and account numbers."
    )
    bank_details = (
        "the name of the account holder, the name of your bank, whether the account is checking "
        "or savings, and the routing and account numbers"
    )
    if variant == "outgoing_refund":
        what = "your escrow surplus refund" + (f" of {refund}" if refund else "")
        opening = (
            f"Thank you for your reply. You have asked us to send {what} to your bank account by "
            "electronic transfer instead of by check."
        )
        needed = [
            "A signed and dated Electronic Refund Authorization. It must give "
            f"{bank_details}, and authorize us to deposit the refund"
            + (f" of {refund}" if refund else "")
            + " to that account.",
            bank_proof,
        ]
        until = (
            "No money will move until we have received both items and verified the bank "
            "account. We have not made any changes to your account yet. Once everything is "
            "verified, we will confirm the refund details to you in writing."
        )
        labels = [
            "Documents needed: signed Electronic Refund Authorization; voided check or bank letter"
        ]
    elif variant == "incoming_payment":
        opening = (
            "Thank you for your reply. You have asked us to draw your monthly mortgage payment"
            + (f" ({payment_text})" if payment_text else "")
            + " from your bank account automatically each month."
        )
        needed = [
            "A signed and dated automatic payment (ACH debit) authorization. It must give "
            f"{bank_details}, and authorize us to draw your monthly mortgage payment from that "
            "account each month.",
            bank_proof,
        ]
        until = (
            "No payment will be drawn from your bank account until we have received both items, "
            "verified the bank account and confirmed the start date to you in writing. Until "
            "then, please continue to make your monthly payments as you do now so that no "
            "payment is late."
        )
        labels = [
            "Documents needed: signed automatic payment authorization; voided check or bank letter"
        ]
    else:
        product = (
            f" Our records for the loan ending in {loan_id[-4:]} show a fixed-rate mortgage, not "
            "a line of credit, so please also tell us the account number of the line of credit "
            "you mean."
            if context.get("product") == "fixed_mortgage"
            else ""
        )
        opening = (
            "Thank you for your reply. You have asked about a draw from a home equity line of "
            f"credit by electronic transfer.{product}"
        )
        needed = [
            "A signed and dated draw request. It must name the line of credit, state the amount "
            f"you want to draw and give {bank_details} for the account that should receive it.",
            bank_proof,
        ]
        until = (
            "No funds will be advanced until we have received both items, verified the line of "
            "credit and the bank account, and confirmed the draw to you in writing. We have not "
            "made any changes to your account."
        )
        labels = ["Documents needed: signed draw request; voided check or bank letter"]
    paragraphs = [
        _salutation(name),
        opening,
        "Before we can set this up, we need two items from you:\n"
        + "\n".join(f"- {item}" for item in needed),
        "You can attach clear copies to a reply to this email, or mail them to "
        f"{mail_to}. Please include your loan number with anything you send. For your security, "
        "please do not type your bank account number in the body of an email; include it only in "
        "the signed authorization and the voided check or bank letter.",
        until,
        contact,
        *_closing(client),
        _reference_block(
            others,
            loan_id,
            list(dict.fromkeys([f"Request: {EFT_REQUESTS[variant]}", *labels, *claimed])),
        ),
        *_disclosures(candidate, applicable),
    ]
    return _letter(paragraphs)
