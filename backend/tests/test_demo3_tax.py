"""Demo 3 (DEMO-03 tax): realistic fixture, township tax bill and the scheduled-payment letter."""

import re
from io import BytesIO
from uuid import uuid4

from pypdf import PdfReader
from test_phase3 import candidate_for, codes, load, validate
from test_phase4 import act, complete, prepare
from test_phase7 import approve, current, new_response, supply, workflow

from app.documents import library_document, schedule_entries
from app.fixture_data import load_fixture
from app.mail_templates import templates

NOTICE = "Harbor Point Mortgage Services, LLC is a debt collector."
ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def pdf_text(content):
    reader = PdfReader(BytesIO(content), strict=True)
    return reader, "\n".join(page.extract_text() for page in reader.pages)


def test_fixture_bill_task_and_prepared_result_reconcile():
    base, followup = load_fixture("DEMO-03"), load_fixture("DEMO-03", "followup")
    context = base.loan_context
    assert base.client_code == "DEMO-HARBOR"
    assert context["authorized_recipient"] == base.borrower_email == "priya.raman@outlook.com"
    bill = next(d for d in base.documents if d.key == "tax-bill").facts
    assert bill["amount_minor"] == context["tax_amount_minor"] == 235000
    assert bill["due_date"] == context["tax_due_date"] == "2026-10-30"
    assert bill["payee"] == context["tax_payee"]
    assert bill["tax_period"] == context["tax_period"]
    assert bill["bill_number"] == context["tax_bill_number"]
    assert bill["parcel_id"] == context["tax_parcel_id"]
    assert bill["owner_name"] == base.borrower_display_name
    assert bill["property_address"] == context["property_address"]
    levies = bill["levies"]
    assert sum(r["annual_minor"] for r in levies) == bill["annual_tax_minor"]
    assert sum(r["installment_minor"] for r in levies) == bill["amount_minor"]
    assert bill["amount_minor"] * bill["installment_count"] == bill["annual_tax_minor"]
    # Millage x assessed value gives each annual levy.
    for row in levies:
        assert (
            round(float(row["mills"]) * bill["assessed_value_minor"] / 1000) == row["annual_minor"]
        )
    # Issued, received by the servicer, emailed by the borrower, scheduled, then due.
    received = context["tax_bill_received_at"][:10]
    assert bill["issued_date"] < received < base.original_received_at.date().isoformat()
    assert context["tax_scheduled_date"] < context["tax_due_date"]
    assert context["tax_status"] == "scheduled" and context["tax_paid_at"] is None
    assert context["escrow_balance_minor"] >= context["tax_amount_minor"]
    # The unpaid balance follows four payments (June to September) on the note terms.
    entries = schedule_entries(
        {
            "opening_principal_minor": context["original_principal_minor"],
            "annual_rate_basis_points": context["annual_rate_basis_points"],
            "principal_interest_minor": context["principal_interest_minor"],
            "remaining_payments": context["term_months"],
            "first_payment_date": "2026-06-01",
        }
    )
    assert entries[3]["balance"] == base.balance_minor
    assert context["remaining_payments"] == context["term_months"] - 4
    task = base.tasks[0]
    assert task.status == "pending" and task.request["tax_period"] == context["tax_period"]
    result = followup.tasks[0].result
    assert result["confirmed_status"] == context["tax_status"]
    assert result["scheduled_date"] == context["tax_scheduled_date"]
    assert result["paid_at"] is None
    assert result["reference"] == followup.loan_context["tax_schedule_verified_by"]


def test_tax_bill_reads_as_a_township_bill_without_conflicting_loan_numbers():
    _, content = library_document("DEMO-03", "base", "tax-bill")
    reader, text = pdf_text(content)
    assert "SYNTHETIC" not in text and "Fixture version" not in text
    for expected in (
        "WRENFIELD TOWNSHIP",
        "Office of the Tax Collector",
        "2026 REAL ESTATE TAX BILL",
        "4th Quarter Installment (4 of 4)",
        "Bill number 2026-RE-04417",
        "Parcel ID 34-12-071-400",
        "Priya S. Raman",
        "418 Hawthorne Ridge Road",
        "MORTGAGE COMPANY COPY SENT",
        "Harbor Point Mortgage Services",
        "Amount due on or before October 30, 2026",
        "$2,350.00",
        "$9,400.00",
        "REMITTANCE STUB",
        "Not an official tax bill",
    ):
        assert expected in text, expected
    # Mail intake treats any other 10-digit number in an attachment as a conflicting loan.
    assert not re.findall(r"(?<!\d)\d{10}(?!\d)", text)
    keywords = reader.metadata["/Keywords"]
    assert "SYNTHETIC" in keywords and "DEMO-HARBOR" in keywords and "0099000003" in keywords


def test_mail_template_carries_the_borrowers_email_and_bill():
    initial = {t.key: t for t in templates()}["DEMO-03"]
    assert initial.sender == "priya.raman@outlook.com"
    assert initial.subject == "Property tax bill – loan ending 0003"
    assert initial.attachments == [
        {"key": "tax-bill", "title": "2026 Real Estate Tax Bill – 4th Quarter Installment"}
    ]
    for expected in ("$2,350.00", "October 30, 2026", "escrow", "Priya Raman"):
        assert expected in initial.body, expected


def rendered(client, case, extra_claims=()):
    candidate = candidate_for(client, case)
    candidate["claims"] += list(extra_claims)
    result = validate(client, case, candidate)
    assert result["valid"], result
    return result["rendered_body"]


def test_letter_confirms_receipt_and_schedule_but_never_payment(client):
    body = rendered(client, load(client, "DEMO-03"))
    assert body.startswith("Dear Priya S. Raman,")
    for expected in (
        "We received your email on September 19, 2026",
        "2026 fourth-quarter real estate tax bill",
        "loan ending in 0003",
        "we received the Wrenfield Township Tax Collector's bill for $2,350.00 on "
        "September 18, 2026",
        "scheduled to be paid from your escrow account on October 27, 2026, before the "
        "October 30, 2026 due date",
        "it has not been paid yet",
        "please do not pay this installment yourself",
        "annual escrow account statement",
        "(888) 555-0187",
        "Customer Care Team\nHarbor Point Mortgage Services",
        "Loan number: 0099000003\n"
        "Tax bill: 2026 fourth-quarter real estate tax, Wrenfield Township Tax Collector\n"
        "Installment amount: $2,350.00\n"
        "Bill received: September 18, 2026\n"
        "Scheduled payment date: October 27, 2026\n"
        "Payment status: Scheduled (not yet paid)",
        NOTICE,
    ):
        assert expected in body, expected
    # Long-form dates only, no snake_case values, no "paid" status, no Tax Team claim yet.
    assert not ISO.search(body)
    assert "_" not in body
    assert "Payment status: Paid" not in body and "has been paid" not in body
    assert "Tax Team" not in body
    assert "Our response to your correspondence follows." not in body
    assert "synthetic" not in body.lower()


def test_tax_team_result_adds_the_review_sentence_and_reference(client):
    body = rendered(client, load(client, "DEMO-03", "followup"))
    assert "Our Tax Team has also reviewed the bill" in body
    assert body.count("Tax Team review reference: TAX-REV-260922-003") == 1
    assert "it has not been paid yet" in body


def test_task_reference_claim_is_labelled_once(client):
    case = load(client, "DEMO-03", "followup")
    task = client.get(f"/api/cases/{case['id']}/tasks").json()[0]
    body = rendered(
        client,
        case,
        [
            {
                "field": "task_completed",
                "value": task["result"]["reference"],
                "evidence_id": task["id"],
            }
        ],
    )
    assert body.count("TAX-REV-260922-003") == 1
    assert "Completed action reference" not in body


def test_paid_status_claim_is_still_rejected(client):
    case = load(client, "DEMO-03")
    candidate = candidate_for(client, case)
    for claim in candidate["claims"]:
        if claim["field"] == "tax_status":
            claim["value"] = "paid"
    result = validate(client, case, candidate)
    assert not result["valid"] and "unsupported_claim" in codes(result)
    assert "Payment status: Scheduled" not in result["rendered_body"]


def test_review_path_invalidates_edits_and_closes_with_the_rendered_letter(client):
    case = load(client, "DEMO-03")
    first = prepare(client, case)
    act(client, case, "csp.send", expected="awaiting_review", draft_id=first)
    supply(client, case, "tax_specialist_result")
    assert not workflow(client, case)["drafts"][-1]["current"]
    act(client, case, "csp.send", expected="rejected", draft_id=first)
    second = new_response(client, case)
    draft = workflow(client, case)["drafts"][-1]
    assert draft["id"] == second and "Tax Team review reference" in draft["body"]
    # The reviewer adds the verified due date as a structured claim, never as free text.
    record = next(
        e
        for e in client.get(f"/api/cases/{case['id']}/evidence").json()
        if e["details"]["kind"] == "record"
    )
    candidate = draft["candidate"]
    edit = {k: candidate[k] for k in ("response_type", "concerns", "claims", "attachment_ids")}
    edit["claims"] = [
        *edit["claims"],
        {"field": "tax_due_date", "value": "2026-10-30", "evidence_id": record["id"]},
    ]
    response = client.post(
        f"/api/cases/{case['id']}/draft-edits",
        json={
            "request_id": str(uuid4()),
            "expected_revision": current(client, case)["revision"],
            "draft_id": second,
            "draft_version": draft["version"],
            "actor": "Demo reviewing presenter",
            **edit,
        },
    )
    assert response.status_code == 200, response.text
    edited = workflow(client, case)["drafts"][-1]
    assert edited["id"] != second and edited["review_required"]
    assert "Installment amount: $2,350.00\nDue date: October 30, 2026\n" in edited["body"]
    # The stored body is exactly the checked rendering of the edited claims.
    assert (
        validate(client, case, {**edited["candidate"], "body": edited["body"]})["rendered_body"]
        == edited["body"]
    )
    approve(client, case, edited["id"])
    complete(client, case, edited["id"])
    assert current(client, case)["status"] == "closed"
    assert client.get(f"/api/cases/{case['id']}/completion-check").json()["valid"]
    sent = client.get(f"/api/cases/{case['id']}/artifacts").json()["outbox"]
    assert len(sent) == 1 and sent[0]["sent_content"]["body"] == edited["body"]
    assert sent[0]["sent_content"]["recipient"] == "priya.raman@outlook.com"
    assert sent[0]["sent_content"]["sender"] == "correspondence@harborpointmortgage.com"
    # The desk draft, the delivered mail and its HTML part carry the same derived emphasis.
    content = sent[0]["sent_content"]
    assert edited["emphasis"] and content["emphasis"] == edited["emphasis"]
    assert "<strong>please do not pay this installment yourself</strong>" in content["html_body"]
    packages = client.get(f"/api/cases/{case['id']}/artifacts").json()["packages"]
    row = current(client, case)
    pdf = client.get(
        f"/api/simulations/{row['simulation_id']}/cases/{case['id']}/packages/"
        f"{packages[-1]['id']}/file",
        params={"loan_identifier": row["loan_identifier"], "client_code": row["client_code"]},
    )
    assert pdf.status_code == 200, pdf.text
    letter = PdfReader(BytesIO(pdf.content)).pages[0]
    assert "do not pay this installment yourself" in " ".join(letter.extract_text().split())


def test_letter_emphasis_is_derived_from_the_plain_body(client):
    from app.letter_emphasis import emphasis_spans, html_body, reportlab_markup

    body = rendered(client, load(client, "DEMO-03"))
    bold = [body[a:b] for a, b in emphasis_spans(body)]
    for expected in (
        "$2,350.00",
        "October 27, 2026",
        "loan ending in 0003",
        "it has not been paid yet",
        "please do not pay this installment yourself",
        "Scheduled payment date:",
    ):
        assert expected in bold, expected
    # Salutation, signature and disclosures are never emphasized; the body itself is unchanged.
    assert not any("Priya" in b or "Sincerely" in b or NOTICE in b for b in bold)
    assert "**" not in body and "<" not in body
    assert emphasis_spans(body) == emphasis_spans(body)
    html = html_body(body)
    assert "<strong>it has not been paid yet</strong>" in html and html.startswith("<p>Dear ")
    assert "<b>$2,350.00</b>" in reportlab_markup(body)
    assert emphasis_spans("Our response to your correspondence follows.") == []


def test_every_emphasis_phrase_still_exists_in_a_letter_template():
    from pathlib import Path

    from app import letter_emphasis, response_validation

    source = Path(response_validation.__file__).read_text()
    joined = re.sub(r'"\s*\n\s*(?:\+\s*)?f?"', "", source)  # Join implicit string concatenation.
    for phrase in letter_emphasis.PHRASES:
        assert phrase in joined, phrase
