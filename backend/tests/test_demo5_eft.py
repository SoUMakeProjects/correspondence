"""Demo 5 (DEMO-05 EFT): realistic fixture, escrow statement, replies and both letter rounds."""

import re
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import select
from test_custom_mail import IntakeModel
from test_mailbox import linked, send
from test_phase3 import candidate_for, change_context, codes, load, validate
from test_phase4 import act
from test_phase7 import supply

from app.documents import document_path, library_document, schedule_entries
from app.fixture_data import load_fixture
from app.mail_templates import EFT_REPLIES, templates
from app.main import create_app
from app.models import Evidence

NOTICE = "Northstar Residential Servicing, LLC is a debt collector."
# No letter may say that money moved, or will move, before authorization.
MONEY_MOVED = re.compile(
    r"(has|have) been (sent|deposited|drawn|advanced|transferred)"
    r"|will be (sent|deposited|drawn|advanced|transferred) (to|from|on)"
    r"|we (sent|deposited|transferred)"
    r"|we will (send|deposit|draw|advance|transfer)\b",
    re.IGNORECASE,
)


def moved(body):
    """Sentences that state money moved or will move, other than negated/conditional ones."""
    sentences = re.split(r"(?<=[.:])\s+|\n", body)
    return [
        s
        for s in sentences
        if MONEY_MOVED.search(s) and not re.match(r"(No|Until|Once|If)\b", s.strip("- "))
    ]


def pdf_text(content):
    reader = PdfReader(BytesIO(content), strict=True)
    return reader, "\n".join(page.extract_text() for page in reader.pages)


def test_fixture_escrow_statement_and_prepared_reply_reconcile():
    base, followup = load_fixture("DEMO-05"), load_fixture("DEMO-05", "followup")
    context = base.loan_context
    assert base.client_code == "DEMO-NORTH"
    assert context["authorized_recipient"] == base.borrower_email == "danielle.foster@outlook.com"
    assert context["eft_intent"] is None and context["refund_authorization"] is None
    statement = next(d for d in base.documents if d.key == "escrow-analysis").facts
    assert statement["surplus_minor"] == context["escrow_surplus_minor"] == 48627
    assert statement["analysis_date"] == context["escrow_analysis_date"]
    assert statement["new_escrow_minor"] == context["escrow_monthly_deposit_minor"]
    assert statement["new_payment_minor"] == context["new_payment_minor"]
    assert statement["principal_interest_minor"] == context["principal_interest_minor"]
    total = sum(r["amount_minor"] for r in statement["projected_disbursements"])
    assert total == statement["annual_disbursements_minor"]
    assert total == statement["new_escrow_minor"] * 12
    assert statement["required_cushion_minor"] * 6 == total
    assert (
        statement["projected_low_balance_minor"] - statement["required_cushion_minor"]
        == (statement["surplus_minor"])
    )
    assert statement["current_payment_minor"] == (
        statement["principal_interest_minor"] + statement["current_escrow_minor"]
    )
    assert statement["new_payment_minor"] == (
        statement["principal_interest_minor"] + statement["new_escrow_minor"]
    )
    # 86 payments (August 2019 to September 2026) on the note terms give the unpaid balance.
    entries = schedule_entries(
        {
            "opening_principal_minor": context["original_principal_minor"],
            "annual_rate_basis_points": context["annual_rate_basis_points"],
            "principal_interest_minor": context["principal_interest_minor"],
            "remaining_payments": context["term_months"],
            "first_payment_date": "2019-08-01",
        }
    )
    assert entries[85]["balance"] == base.balance_minor
    assert context["remaining_payments"] == context["term_months"] - 86
    assert (entries[-1]["year"], entries[-1]["month"]) == (2034, 7)
    # The borrower's email quotes the statement.
    for figure in ("$486.27", "$1,562.96", "September 10", "November 1"):
        assert figure in base.correspondence_text, figure
    reply = next(d for d in followup.documents if d.key == "clarification")
    assert "\n\n".join(reply.paragraphs) == EFT_REPLIES["outgoing_refund"][1]
    assert followup.loan_context["eft_intent"] == reply.facts["eft_intent"] == "outgoing_refund"


def test_escrow_statement_reads_as_a_servicer_statement():
    _, content = library_document("DEMO-05", "base", "escrow-analysis")
    reader, text = pdf_text(content)
    assert "SYNTHETIC" not in text and "Fixture version" not in text
    for expected in (
        "Northstar Residential Servicing",
        "Annual Escrow Account Disclosure Statement",
        "Statement date September 10, 2026",
        "Danielle R. Foster",
        "77 Birchwood Court, Westerville, OH 43081",
        "15-year fixed rate",
        "$1,603.56",
        "$1,562.96",
        "Linden County Treasurer",
        "$4,600.80",
        "$766.80",
        "$486.27",
        "a check for $486.27 will be mailed to you",
        f"Page 1 of {len(reader.pages)}",
    ):
        assert expected in text, expected
    # Only this loan's own number appears (any other 10-digit number is a conflicting loan).
    assert set(re.findall(r"(?<!\d)\d{10}(?!\d)", text)) == {"0099000005"}
    keywords = reader.metadata["/Keywords"]
    assert "SYNTHETIC" in keywords and "DEMO-NORTH" in keywords and "0099000005" in keywords


def test_mail_templates_carry_natural_borrower_emails():
    by_key = {t.key: t for t in templates()}
    initial = by_key["DEMO-05"]
    assert initial.sender == "danielle.foster@outlook.com"
    assert initial.subject == "EFT instead of checks – loan ending 0005"
    assert initial.attachments == [
        {"key": "escrow-analysis", "title": "Annual Escrow Account Disclosure Statement"}
    ]
    assert "Can you change this to an EFT instead?" in initial.body
    for intent, phrase in (
        ("outgoing_refund", "I meant the escrow refund"),
        ("incoming_payment", "automatically each month"),
        ("heloc_draw", "home equity line of credit"),
    ):
        reply = by_key[f"eft-{intent}"]
        assert reply.kind == "reply" and reply.eft_intent == intent
        assert reply.sender == initial.sender and not reply.attachments
        assert phrase in reply.body and reply.body.endswith("Danielle Foster\n(614) 555-0139")
        assert "EFT request concerns" not in reply.body


def letter(client, case):
    result = validate(client, case, candidate_for(client, case, "information_request"))
    assert result["valid"], result
    return result["rendered_body"]


def test_clarification_letter_explains_the_three_meanings(client):
    body = letter(client, load(client, "DEMO-05"))
    assert body.startswith("Dear Danielle R. Foster,")
    for expected in (
        "We received your email on September 21, 2026",
        "loan ending in 0005",
        "can mean one of three different things",
        "- A refund sent to you. For example, the escrow surplus refund of $486.27 from your "
        "escrow account statement dated September 10, 2026",
        "- Automatic monthly payments. Your mortgage payment ($1,562.96 beginning "
        "November 1, 2026)",
        "- A draw from a line of credit.",
        "tell us which one you mean",
        "We have not made any changes to your account.",
        "No money will be moved electronically until",
        "(800) 555-0142",
        "Customer Correspondence Team\nNorthstar Residential Servicing",
        "Loan number: 0099000005\nRequest: Electronic funds transfer (EFT)\n"
        "Request received: September 21, 2026",
        NOTICE,
    ):
        assert expected in body, expected
    assert not moved(body)
    assert "Additional information is required" not in body and "_" not in body


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        (
            "outgoing_refund",
            (
                "send your escrow surplus refund of $486.27 to your bank account",
                "A signed and dated Electronic Refund Authorization",
                "No money will move until we have received both items and verified",
                "Request: Refund by electronic transfer",
            ),
        ),
        (
            "incoming_payment",
            (
                "draw your monthly mortgage payment ($1,562.96 beginning November 1, 2026)",
                "automatic payment (ACH debit) authorization",
                "No payment will be drawn from your bank account until",
                "please continue to make your monthly payments",
                "Request: Automatic monthly payments by electronic transfer",
            ),
        ),
        (
            "heloc_draw",
            (
                "a draw from a home equity line of credit",
                "show a fixed-rate mortgage, not a line of credit",
                "A signed and dated draw request",
                "No funds will be advanced until",
                "Request: Line-of-credit draw by electronic transfer",
            ),
        ),
    ],
)
def test_authorization_letter_asks_only_for_what_that_purpose_needs(client, intent, expected):
    case = load(client, "DEMO-05")
    supply(client, case, "eft_clarification", eft_intent=intent)
    case = client.get(f"/api/cases/{case['id']}").json()
    assert "eft_authorization_required" in codes(
        client.get(f"/api/cases/{case['id']}/assessment").json()
    )
    body = letter(client, case)
    assert body.startswith("Dear Danielle R. Foster,\n\nThank you for your reply.")
    for phrase in (
        *expected,
        "- A voided check for that account, or a letter from your bank",
        "do not type your bank account number in the body of an email",
        "P.O. Box 4410, Columbus, OH 43216-4410",
        NOTICE,
    ):
        assert phrase in body, phrase
    assert not moved(body)
    assert "one of three different things" not in body
    # Each purpose asks for its own authorization, never another purpose's.
    others = {
        "outgoing_refund": "Electronic Refund Authorization",
        "incoming_payment": "ACH debit",
        "heloc_draw": "draw request",
    }
    for other, phrase in others.items():
        if other != intent:
            assert phrase not in body


def test_supplied_reply_is_stored_as_the_borrowers_email(client, application, settings):
    case = load(client, "DEMO-05")
    supply(client, case, "eft_clarification", eft_intent="outgoing_refund")
    with application.state.sessions() as session:
        reply = next(
            e
            for e in session.scalars(select(Evidence).where(Evidence.case_id == case["id"]))
            if e.details.get("key") == "clarification"
        )
        assert reply.title == "Borrower reply – EFT clarification"
        _, text = pdf_text(document_path(settings.data_dir, reply).read_bytes())
    assert "Re: EFT instead of checks – loan ending 0005" in text
    assert "danielle.foster@outlook.com" in text
    assert "I meant the escrow refund" in text
    assert "Synthetic" not in text and "SYNTHETIC" not in text


def test_no_funds_movement_tool_exists(client):
    names = {t["name"] for t in client.get("/api/simulator/tools").json()}
    assert not any(
        word in name for name in names for word in ("refund", "transfer", "eft", "disburse")
    )


def test_unchanged_prepared_reply_keeps_its_purpose_without_a_model_call(settings):
    model = IntakeModel("eft", eft_intent="incoming_payment")
    app = create_app(settings, agent_model=model, start_worker=False)
    with TestClient(app) as client:
        initial, _ = send(client, "DEMO-05")
        app.state.automation_worker.run_once()
        case_id = linked(client, initial)
        app.state.agent_worker.run_once()
        send(client, "eft-outgoing_refund", initial["thread_id"])
        app.state.automation_worker.run_once()
        state = client.get(f"/api/systems/cases/{case_id}").json()
        assert state["loan"]["context"]["eft_intent"] == "outgoing_refund"
        assert model.calls == 0
        printed = next(e for e in state["evidence"] if e["details"].get("key") == "clarification")
        assert printed["details"]["facts"]["reply_from"] == "danielle.foster@outlook.com"


def test_borrower_pending_work_is_not_handed_off_while_contact_is_permitted(client, application):
    case = load(client, "DEMO-05")
    supply(client, case, "eft_clarification", eft_intent="outgoing_refund")
    act(client, case, "cct.apply_plan")
    result, _ = act(client, case, "cct.handoff", expected="rejected")
    assert result["code"] == "handoff_not_required"
    assert client.get(f"/api/cases/{case['id']}").json()["status"] == "waiting_for_borrower"
    # When contact is blocked, the handoff remains the way to record ownership.
    blocked = load(client, "DEMO-05")
    change_context(application, blocked, {"communication_restriction": "cease_and_desist"})
    act(client, blocked, "cct.apply_plan")
    act(client, blocked, "cct.handoff")


def test_claimed_purpose_is_listed_once(client):
    case = load(client, "DEMO-05")
    supply(client, case, "eft_clarification", eft_intent="outgoing_refund")
    case = client.get(f"/api/cases/{case['id']}").json()
    candidate = candidate_for(client, case, "information_request")
    record = next(
        e
        for e in client.get(f"/api/cases/{case['id']}/evidence").json()
        if e["details"]["kind"] == "record"
    )
    candidate["claims"] = [
        {"field": "eft_intent", "value": "outgoing_refund", "evidence_id": record["id"]},
        {"field": "loan_identifier", "value": "0099000005", "evidence_id": record["id"]},
    ]
    result = validate(client, case, candidate)
    assert result["valid"], result
    body = result["rendered_body"]
    assert body.count("Request: Refund by electronic transfer") == 1
    assert body.count("Loan number: 0099000005") == 1
    assert "EFT purpose" not in body
