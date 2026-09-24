"""Demo 2 (DEMO-01 name change): realistic fixture, borrower documents and both letters."""

import re
from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import select
from test_phase3 import candidate_for, load, validate
from test_phase4 import act, prepare
from test_phase7 import new_response, supply

from app.agent_tools import verified_outcome
from app.documents import library_document
from app.domain import DomainError
from app.fixture_data import load_fixture
from app.mail_templates import templates
from app.models import Evidence

NOTICE = "Northstar Residential Servicing, LLC is a debt collector."


def pdf_text(content):
    reader = PdfReader(BytesIO(content), strict=True)
    return reader, "\n".join(page.extract_text() for page in reader.pages)


def test_fixture_and_prepared_follow_up_reconcile():
    base, followup = load_fixture("DEMO-01"), load_fixture("DEMO-01", "followup")
    context = base.loan_context
    assert base.borrower_display_name == context["current_legal_name"] == "Lauren E. Whitaker"
    assert context["requested_legal_name"] == "Lauren E. Castellano"
    assert context["authorized_recipient"] == base.borrower_email == "lauren.whitaker@outlook.com"
    signed = next(d for d in base.documents if d.key == "signed-request")
    assert signed.facts["signed"] and signed.facts["signed_date"] == "2026-09-16"
    assert signed.facts["requested_name"] == context["requested_legal_name"]
    assert signed.facts["signed_date"] < base.original_received_at.date().isoformat()
    legal = next(d for d in followup.documents if d.key == "legal-document")
    assert legal.availability == "available" and legal.facts["document_received"]
    assert legal.facts["previous_name"] == context["current_legal_name"]
    assert legal.facts["new_name"] == context["requested_legal_name"]
    assert (
        legal.facts["marriage_date"] < legal.facts["certified_date"] < signed.facts["signed_date"]
    )
    result = followup.tasks[0].result
    assert (result["previous_name"], result["updated_name"]) == (
        "Lauren E. Whitaker",
        "Lauren E. Castellano",
    )
    assert followup.loan_context["current_legal_name"] == result["updated_name"]


def test_signed_request_reads_as_the_borrowers_own_letter():
    _, content = library_document("DEMO-01", "base", "signed-request")
    reader, text = pdf_text(content)
    assert "SYNTHETIC" not in text and "Fixture version" not in text
    for expected in (
        "Lauren E. Castellano",
        "(formerly Lauren E. Whitaker)",
        "2214 Bramblewood Drive",
        "September 16, 2026",
        "Northstar Residential Servicing, LLC",
        "P.O. Box 4410",
        "Loan number: 0099000001",
        "Signed and dated: September 16, 2026",
    ):
        assert expected in text, expected
    keywords = reader.metadata["/Keywords"]
    assert "SYNTHETIC" in keywords and "DEMO-NORTH" in keywords and "0099000001" in keywords


def test_marriage_record_is_a_certified_copy_without_conflicting_loan_numbers():
    _, content = library_document("DEMO-01", "followup", "legal-document")
    reader, text = pdf_text(content)
    assert "SYNTHETIC" not in text
    for expected in (
        "PROBATE COURT OF LINDEN COUNTY",
        "Certified Copy of Marriage Record",
        "Lauren Elizabeth Whitaker",
        "Lauren Elizabeth Castellano",
        "Daniel Robert Castellano",
        "August 22, 2026",
        "2026-ML-01873",
        "Not an official document",
    ):
        assert expected in text, expected
    # Mail intake treats any other 10-digit number in an attachment as a conflicting loan.
    assert not re.findall(r"(?<!\d)\d{10}(?!\d)", text)
    assert "SYNTHETIC" in reader.metadata["/Keywords"]


def test_mail_templates_carry_the_borrowers_messages():
    by_key = {t.key: t for t in templates()}
    initial, reply = by_key["DEMO-01"], by_key["name-proof"]
    assert initial.sender == reply.sender == "lauren.whitaker@outlook.com"
    assert initial.subject == "Name change request – loan ending 0001"
    assert [a["key"] for a in initial.attachments] == ["signed-request"]
    assert "Lauren E. Whitaker to Lauren E. Castellano" in initial.body
    assert "Lauren E. Whitaker to Lauren E. Castellano" in reply.body
    assert reply.attachments == [
        {"key": "legal-document", "title": "Certified Copy of Marriage Record"}
    ]


def test_information_request_letter_names_only_the_missing_document(client):
    case = load(client, "DEMO-01")
    body = validate(client, case, candidate_for(client, case, "information_request"))[
        "rendered_body"
    ]
    assert body.startswith("Dear Lauren E. Whitaker,")
    for expected in (
        "We received your request on September 17, 2026",
        "loan ending in 0001 from Lauren E. Whitaker to Lauren E. Castellano",
        "signed and dated request, dated September 16, 2026",
        "marriage certificate or marriage record, a divorce decree, or a court order",
        "P.O. Box 4410, Columbus, OH 43216-4410",
        "We have not changed the name on your loan yet.",
        "(800) 555-0142",
        "Customer Correspondence Team\nNorthstar Residential Servicing",
        "Loan number: 0099000001\nRequested name: Lauren E. Castellano",
        NOTICE,
    ):
        assert expected in body, expected
    assert "need two documents" not in body
    assert "Additional information is required" not in body


def test_information_request_asks_for_both_documents_when_the_signature_is_missing(
    client, application
):
    case = load(client, "DEMO-01")
    with application.state.sessions() as session, session.begin():
        signed = next(
            e
            for e in session.scalars(select(Evidence).where(Evidence.case_id == case["id"]))
            if e.details.get("key") == "signed-request"
        )
        signed.details = {**signed.details, "facts": {**signed.details["facts"], "signed": False}}
    body = validate(client, case, candidate_for(client, case, "information_request"))[
        "rendered_body"
    ]
    assert "we need two documents from you:\n- A written request" in body
    assert "\n- A copy of a legal document" in body


def completed_update(client, case):
    interim = prepare(client, case, "information_request")
    for operation in ("csp.send", "onbase.index", "ils.final_note"):
        act(client, case, operation, draft_id=interim)
    supply(client, case, "name_legal_document")
    task, _ = act(client, case, "ils.create_task", task_type="demo_profile_name_update")
    act(client, case, "ils.update_name", task_id=task["reference"]["id"])
    final = new_response(client, case)
    act(client, case, "csp.send", draft_id=final)
    return final


def test_confirmation_letter_is_rendered_from_the_completed_update(client):
    case = load(client, "DEMO-01")
    final = completed_update(client, case)
    body = next(
        o["sent_content"]["body"]
        for o in client.get(f"/api/cases/{case['id']}/artifacts").json()["outbox"]
        if o["draft_id"] == final
    )
    assert body.startswith("Dear Lauren E. Castellano,")
    for expected in (
        "we have updated the name on your mortgage loan ending in 0001",
        "Our records now show your name as Lauren E. Castellano, replacing Lauren E. Whitaker.",
        "The change was made on September 22, 2026.",
        "does not change the name on your property deed",
        "Name on loan: Lauren E. Castellano",
        "Name change reference: DEMO-NAME-",
        NOTICE,
    ):
        assert expected in body, expected
    assert "Supported information is available" not in body


def test_agent_cannot_pause_after_confirmation_without_the_classification_handoff(
    client, application, settings
):
    case = load(client, "DEMO-01")
    final = completed_update(client, case)
    for operation in ("onbase.index", "ils.final_note"):
        act(client, case, operation, draft_id=final)

    class Run:
        case_id, checkpoint = case["id"], {}

    with application.state.sessions() as session, pytest.raises(DomainError) as rejected:
        verified_outcome(session, settings.data_dir, Run, "waiting_for_input")
    assert rejected.value.code == "handoff_required"
    act(client, case, "cct.handoff")
    with application.state.sessions() as session:
        outcome = verified_outcome(session, settings.data_dir, Run, "waiting_for_input")
    assert outcome["case_status"] == "waiting_on_department"
