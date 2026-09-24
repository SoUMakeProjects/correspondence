"""Demo 4 (DEMO-04 bankruptcy): fixture, court and counsel documents, the counsel-only dispute
acknowledgment, the routing notes and the transferred (not closed) end state."""

import re
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pypdf import PdfReader
from test_phase3 import candidate_for, codes, load, report, validate
from test_phase4 import act
from test_phase7 import approve, current, supply, workflow

from app.agent_tools import verified_outcome
from app.documents import library_document, schedule_entries
from app.domain import DomainError
from app.fixture_data import load_fixture
from app.mail_templates import templates
from app.models import AgentRun

NOTICE = "Harbor Point Mortgage Services, LLC is a debt collector."
COUNSEL = "monica.ferrante@ferrantehale.example.com"
BORROWER = "greg.lindqvist@outlook.com"
ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
# The acknowledgment never states a reporting outcome, a correction or liability.
OUTCOME = re.compile(
    r"(has|have) been (corrected|updated|removed|deleted|fixed)"
    r"|we (corrected|updated|removed|deleted|will correct|will update|will remove|will delete)"
    r"|(is|was) (accurate|inaccurate)"
    r"|you (owe|do not owe)|not liable|liable for",
    re.IGNORECASE,
)


def pdf_text(content):
    reader = PdfReader(BytesIO(content), strict=True)
    return reader, "\n".join(page.extract_text() for page in reader.pages)


def ten_digit_numbers(text):
    return set(re.findall(r"(?<!\d)\d{10}(?!\d)", text))


def test_fixture_court_order_authorization_and_determination_reconcile():
    base, followup = load_fixture("DEMO-04"), load_fixture("DEMO-04", "followup")
    context = base.loan_context
    assert base.client_code == "DEMO-HARBOR"
    assert context["authorized_recipient"] == COUNSEL != base.borrower_email == BORROWER
    assert context["communication_restriction"] == "representative_only"
    assert context["servicing_bankruptcy_status"] == "discharged"
    assert context["specialist_determination"] is None
    docs = {d.key: d.facts for d in base.documents}
    order, authorization = docs["court-record"], docs["representation"]
    assert order["reported_status"] == "dismissed_without_discharge"
    assert order["discharge_entered"] is False
    assert order["case_number"] == context["bankruptcy_case_number"] == "24-10382"
    assert order["chapter"] == context["bankruptcy_chapter"] == 13
    assert order["filed_date"] == context["bankruptcy_filed_date"]
    assert f"{order['court']} for the {order['district']}" == context["bankruptcy_court"]
    assert order["debtor_name"] == authorization["borrower_name"] == base.borrower_display_name
    assert order["docket"][-1]["number"] == order["order_docket_number"]
    assert order["docket"][-1]["date"] == order["record_date"]
    # Filed, confirmed, motion, hearing, dismissed, imported marker, authorization, email.
    dates = [
        order["filed_date"],
        order["plan_confirmed_date"],
        order["docket"][2]["date"],
        order["hearing_date"],
        order["record_date"],
        context["servicing_status_imported_at"],
        authorization["signed_date"],
        base.original_received_at.date().isoformat(),
    ]
    assert dates == sorted(dates)
    assert authorization["representative_email"] == COUNSEL
    assert authorization["representative_name"] == context["representative_name"]
    assert authorization["representative_firm"] == context["representative_firm"]
    assert authorization["authorization_verified"] is True
    # The loan is current: 87 payments (July 2019 to September 2026) give the unpaid balance.
    entries = schedule_entries(
        {
            "opening_principal_minor": context["original_principal_minor"],
            "annual_rate_basis_points": context["annual_rate_basis_points"],
            "remaining_payments": context["term_months"],
            "first_payment_date": "2019-07-01",
        }
    )
    assert entries[0]["payment"] == context["principal_interest_minor"]
    assert entries[86]["balance"] == base.balance_minor
    assert context["remaining_payments"] == context["term_months"] - 87
    assert base.tasks[0].status == "pending" and base.tasks[0].owner == "Demo Bankruptcy Team"
    # The prepared determination agrees with the court order and the servicing patch.
    memo = next(d for d in followup.documents if d.key == "specialist-determination").facts
    result = followup.tasks[0].result
    patch = load_fixture("DEMO-04", "followup").loan_context
    assert memo["determination"] == result["status"] == patch["servicing_bankruptcy_status"]
    assert memo["reference"] == result["reference"] == patch["specialist_determination"]
    assert memo["dismissed_date"] == result["dismissed_date"] == order["record_date"]
    assert memo["case_number"] == order["case_number"]
    assert memo["communication_restriction"] == result["communication_restriction"]
    assert memo["reviewed_at"] < followup.evaluation_at.isoformat()


@pytest.mark.parametrize(
    "variant,key,expected",
    [
        (
            "base",
            "court-record",
            (
                "UNITED STATES BANKRUPTCY COURT",
                "DISTRICT OF BRANDYWINE",
                "GREGORY P. LINDQVIST",
                "Case No. 24-10382",
                "ORDER DISMISSING CHAPTER 13 CASE",
                "This Chapter 13 case is DISMISSED.",
                "has not received a discharge",
                "Dated: July 14, 2026",
                "United States Bankruptcy Judge",
                "Order dismissing Chapter 13 case. No discharge entered.",
                "Not an official court record",
            ),
        ),
        (
            "base",
            "representation",
            (
                "FERRANTE & HALE, LLC",
                "Authorization to Communicate Through Counsel",
                "Harbor Point Mortgage Services, LLC",
                "Gregory P. Lindqvist",
                COUNSEL,
                "do not contact me directly",
                "Signed and dated: September 18, 2026",
                "Accepted by counsel:",
            ),
        ),
        (
            "followup",
            "specialist-determination",
            (
                "Bankruptcy Status Determination – BK-REV-260922-004",
                "Andre K. Whitcombe, Bankruptcy Team",
                "Dismissed without discharge",
                "Discharged (August 3, 2026 bankruptcy data import)",
                "Not determined here; referred to Compliance",
                "Not for release to the borrower or counsel",
            ),
        ),
    ],
)
def test_documents_read_like_the_real_records(variant, key, expected):
    _, content = library_document("DEMO-04", variant, key)
    reader, text = pdf_text(content)
    assert len(reader.pages) == 1
    assert "SYNTHETIC" not in text and "Fixture version" not in text
    for phrase in expected:
        assert phrase in text, phrase
    # Mail intake treats any other 10-digit number in an attachment as a conflicting loan.
    assert ten_digit_numbers(text) <= {"0099000004"}
    keywords = reader.metadata["/Keywords"]
    assert "SYNTHETIC" in keywords and "DEMO-HARBOR" in keywords and "0099000004" in keywords


def test_mail_template_is_counsels_email_with_both_documents():
    initial = {t.key: t for t in templates()}["DEMO-04"]
    assert initial.sender == COUNSEL
    assert initial.subject == "Credit reporting dispute – Chapter 13 dismissal – loan ending 0004"
    assert initial.attachments == [
        {"key": "court-record", "title": "Order Dismissing Chapter 13 Case – No. 24-10382"},
        {"key": "representation", "title": "Authorization to Communicate Through Counsel"},
    ]
    for phrase in ("Case No. 24-10382", "July 14, 2026", "No discharge", "Monica A. Ferrante"):
        assert phrase in initial.body, phrase
    assert ten_digit_numbers(initial.body) == {"0099000004"}


def acknowledgment(client, case, response_type="interim_acknowledgment", claims=()):
    candidate = candidate_for(client, case, response_type)
    candidate["claims"] = list(claims)
    return candidate


def test_acknowledgment_confirms_receipt_and_referral_without_any_outcome(client):
    case = load(client, "DEMO-04")
    result = validate(client, case, acknowledgment(client, case))
    assert result["valid"], result
    body = result["rendered_body"]
    assert body.startswith("Dear Monica A. Ferrante,")
    for phrase in (
        "which we received on September 21, 2026",
        "your client, Gregory P. Lindqvist",
        "loan ending in 0004",
        "Chapter 13 case No. 24-10382 was dismissed",
        "signed authorization to communicate through counsel, dated September 18, 2026",
        "order dismissing the case, entered on July 14, 2026",
        "will not contact your client directly",
        "referred your dispute to our bankruptcy and credit reporting specialists",
        "It is not the result of our investigation.",
        "or about the bankruptcy status shown in our records",
        "does not change the terms of the loan",
        "by October 21, 2026, within 30 days of receiving your dispute",
        "(888) 555-0187",
        "Sincerely,\nCustomer Care Team\nHarbor Point Mortgage Services",
        "Loan number: 0099000004\nBorrower: Gregory P. Lindqvist\n",
        "Bankruptcy case: No. 24-10382 (Chapter 13), United States Bankruptcy Court for the "
        "District of Brandywine",
        "Dispute received: September 21, 2026\nWritten response by: October 21, 2026",
        "Correspondence: through counsel only (Monica A. Ferrante, Ferrante & Hale, LLC)",
        NOTICE,
    ):
        assert phrase in body, phrase
    assert not OUTCOME.search(body), OUTCOME.search(body)
    assert not ISO.search(body) and "_" not in body
    assert "synthetic" not in body.lower()
    assert "Thank you for choosing" not in body  # Addressed to counsel, not the customer.
    assert "Bankruptcy case status" not in body and "without a discharge." not in body


def test_supported_determination_is_reported_but_the_credit_review_is_not(client):
    case = load(client, "DEMO-04", "followup")
    determination = next(
        e
        for e in client.get(f"/api/cases/{case['id']}/evidence").json()
        if e["details"].get("key") == "specialist-determination"
    )
    claim = {
        "field": "bankruptcy_status",
        "value": "dismissed_without_discharge",
        "evidence_id": determination["id"],
    }
    result = validate(client, case, acknowledgment(client, case, "referral", [claim]))
    assert result["valid"], result
    body = result["rendered_body"]
    assert (
        "Our servicing records now show Chapter 13 case No. 24-10382 as dismissed on "
        "July 14, 2026, without a discharge." in body
    )
    assert "Our review of how the account is reported" in body
    assert "or about the bankruptcy status shown in our records" not in body
    assert body.count("Bankruptcy case status: Dismissed without discharge") == 1
    assert not OUTCOME.search(body)
    # The internal memo supports the citation but is never an outgoing attachment.
    attached = acknowledgment(client, case, "referral", [claim])
    attached["attachment_ids"] = [determination["id"]]
    assert "irrelevant_attachment" in codes(validate(client, case, attached))


def test_counsel_only_contact_and_supported_letter_types_are_enforced(client):
    case = load(client, "DEMO-04")
    wrong = acknowledgment(client, case)
    wrong["recipient"] = BORROWER
    assert "wrong_recipient" in codes(validate(client, case, wrong))
    assert "unsupported_information_request" in codes(
        validate(client, case, acknowledgment(client, case, "information_request"))
    )
    assert "unsupported_referral" in codes(
        validate(client, case, acknowledgment(client, case, "referral"))
    )
    assert "unresolved_concerns" in codes(
        validate(client, case, acknowledgment(client, case, "final_resolution"))
    )
    evidence = client.get(f"/api/cases/{case['id']}/evidence").json()
    order = next(e for e in evidence if e["details"].get("key") == "court-record")
    attached = acknowledgment(client, case)
    attached["attachment_ids"] = [order["id"]]
    attached["claims"] = [
        {"field": "document_attached", "value": order["title"], "evidence_id": order["id"]}
    ]
    assert "irrelevant_attachment" in codes(validate(client, case, attached))
    # The court order alone does not establish the status before the specialist result.
    premature = acknowledgment(
        client,
        case,
        claims=[
            {
                "field": "bankruptcy_status",
                "value": "dismissed_without_discharge",
                "evidence_id": order["id"],
            }
        ],
    )
    assert "unsupported_claim" in codes(validate(client, case, premature))


def outcome(application, settings, case, value):
    with application.state.sessions() as session:
        run = SimpleNamespace(case_id=case["id"], checkpoint={})
        return verified_outcome(session, settings.data_dir, run, value)


def send_acknowledgment(client, case):
    act(client, case, "cct.apply_plan")
    item = current(client, case)
    candidate = acknowledgment(client, item)
    candidate["version"] = len(workflow(client, case)["drafts"]) + 1
    candidate["case_revision"] = item["content_revision"]
    prepared, _ = act(client, case, "csp.prepare", candidate=candidate)
    draft_id = prepared["reference"]["id"]
    act(client, case, "csp.send", expected="awaiting_review", draft_id=draft_id)
    approve(client, case, draft_id)
    for operation in ("csp.send", "onbase.index", "ils.final_note"):
        act(client, case, operation, draft_id=draft_id)
    return draft_id


def test_counsel_is_acknowledged_once_then_the_case_transfers_without_closing(
    client, application, settings
):
    case = load(client, "DEMO-04")
    # A handoff alone does not answer counsel.
    act(client, case, "cct.apply_plan")
    act(client, case, "cct.handoff")
    with pytest.raises(DomainError) as blocked:
        outcome(application, settings, case, "waiting_for_input")
    assert blocked.value.code == "acknowledgment_not_sent"

    draft_id = send_acknowledgment(client, case)
    saved = client.get(f"/api/cases/{case['id']}/artifacts").json()
    assert [e["sent_content"]["recipient"] for e in saved["outbox"]] == [COUNSEL]
    assert saved["outbox"][0]["sent_content"]["sender"] == "correspondence@harborpointmortgage.com"
    assert len(saved["packages"]) == len(saved["notes"]) == 1
    # A second letter is refused; the sent acknowledgment itself stays valid.
    again = acknowledgment(client, current(client, case))
    again["version"] = 2
    again["case_revision"] = current(client, case)["content_revision"]
    assert "acknowledgment_already_sent" in codes(validate(client, case, again))
    assert workflow(client, case)["drafts"][-1]["sent"]
    act(client, case, "cct.handoff")
    assert outcome(application, settings, case, "waiting_for_input")["case_status"] == (
        "waiting_on_department"
    )
    first = workflow(client, case)["handoffs"][-1]
    note = first["routing_note"]
    for phrase in (
        "Referral to Compliance – Compliance Team",
        "Loan 0099000004 · Gregory P. Lindqvist · Case DEMO-CC-004 · received September 21, 2026",
        "Court order in Chapter 13 case No. 24-10382 shows the case dismissed on July 14, 2026 "
        "without a discharge.",
        'Servicing marker shows "discharged" (unverified import, August 3, 2026). '
        "Bankruptcy Team review pending.",
        "Contact: representative only – Monica A. Ferrante, Ferrante & Hale, LLC "
        f"<{COUNSEL}>. Do not contact the borrower directly.",
        f"Acknowledgment delivered to {COUNSEL} (DEMO-DELIVERY-",
        "written response promised by October 21, 2026",
        "Open items:",
        "Closure blocked until resolved:",
    ):
        assert phrase in note, phrase

    # The Bankruptcy Team result changes the inputs: the earlier handoff is no longer current.
    supply(client, case, "bankruptcy_specialist_result")
    assert not workflow(client, case)["handoffs"][-1]["current"]
    referral = acknowledgment(client, current(client, case), "referral")
    referral["version"] = 2
    assert "acknowledgment_already_sent" in codes(validate(client, case, referral))
    act(client, case, "cct.apply_plan")
    act(client, case, "cct.handoff")
    latest = workflow(client, case)["handoffs"][-1]
    assert latest["current"] and latest["owner"] == "Demo Compliance Team"
    assert (
        "Bankruptcy Team determination BK-REV-260922-004: dismissed without discharge; the "
        "servicing marker has been corrected." in latest["routing_note"]
    )
    assert outcome(application, settings, case, "waiting_for_input")
    response = client.post(
        f"/api/cases/{case['id']}/handoff-acknowledgments",
        json={
            "request_id": str(uuid4()),
            "expected_revision": current(client, case)["revision"],
            "handoff_id": latest["id"],
            "actor": "Compliance – credit reporting disputes",
        },
    )
    assert response.status_code == 200, response.text
    acknowledged = workflow(client, case)["handoffs"][-1]
    assert acknowledged["acknowledgment_note"].startswith(
        "Received by Compliance – credit reporting disputes for the Compliance Team."
    )
    assert "2 open items" in acknowledged["acknowledgment_note"]
    assert outcome(application, settings, case, "transferred")["case_status"] == "transferred"
    with pytest.raises(DomainError) as waiting:
        outcome(application, settings, case, "waiting_for_input")
    assert waiting.value.code == "handoff_acknowledged"
    assert current(client, case)["status"] == "transferred"
    assert not client.get(f"/api/cases/{case['id']}/completion-check").json()["valid"]
    with pytest.raises(DomainError):
        outcome(application, settings, case, "completed")
    # One reused task, one delivery, nothing to the borrower's own address.
    assert len(client.get(f"/api/cases/{case['id']}/tasks").json()) == 1
    sent = client.get(f"/api/cases/{case['id']}/artifacts").json()["outbox"]
    assert len(sent) == 1 and sent[0]["draft_id"] == draft_id
    assert all(BORROWER not in str(e["sent_content"]) for e in sent)
    assessment = report(client, case)
    assert assessment["classification"] is None
    assert assessment["authorized_recipient"] == COUNSEL


def test_routing_note_is_not_sent_to_the_model(client, application, settings):
    from app.agent_tools import observe
    from app.model_view import model_view

    case = load(client, "DEMO-04")
    act(client, case, "cct.apply_plan")
    act(client, case, "cct.handoff")
    with application.state.sessions() as session:
        observation = observe(session, settings.data_dir, case["id"])
    assert observation["handoffs"][0]["routing_note"]
    assert "routing_note" not in model_view(observation)["handoffs"][0]


def test_third_party_authorization_input_is_a_realistic_signed_letter(client, application):
    case = load(client)
    supply(client, case, "authorized_representative")
    evidence = next(
        e
        for e in client.get(f"/api/cases/{case['id']}/evidence").json()
        if e["details"].get("key") == "representation"
    )
    assert evidence["title"] == "Third-Party Authorization"
    assert evidence["details"]["facts"]["representative_email"] == (
        "elena.ruiz@brightpathhousing.example.org"
    )
    content = client.get(f"/api/cases/{case['id']}/evidence/{evidence['id']}/file").content
    _, text = pdf_text(content)
    for phrase in (
        "BRIGHTPATH HOUSING COUNSELING",
        "HUD-approved housing counseling agency",
        "Marcus J. Delgado",
        "Elena M. Ruiz",
        "Accepted by counselor:",
    ):
        assert phrase in text, phrase
    assert "SYNTHETIC" not in text and "delegate.demo" not in text
    with application.state.sessions() as session:
        assert session.query(AgentRun).count() == 0
