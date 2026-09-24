"""Demo 1 (DEMO-02 amortization): realistic fixture, schedule arithmetic and fulfillment letter."""

from io import BytesIO

import pytest
from pypdf import PdfReader
from sqlalchemy import select
from test_phase4 import complete, load, prepare, read

from app.catalogs import install_catalogs
from app.documents import library_document, schedule_entries
from app.fixture_contracts import ClientFixture, KnowledgeFixture
from app.fixture_data import load_fixture
from app.models import ClientConfiguration
from app.source_catalog import DATA_ROOT, read_json

CLIENTS = DATA_ROOT / "fixtures/v1/clients.json"
KNOWLEDGE = DATA_ROOT / "knowledge/curated.v1.json"


def test_schedule_reconciles_to_note_terms():
    fixture = load_fixture("DEMO-02")
    facts = fixture.documents[0].facts
    entries = schedule_entries(facts)
    assert len(entries) == facts["remaining_payments"] == 283
    assert entries[0]["number"] == 78 and entries[-1]["number"] == facts["term_months"]
    assert (entries[-1]["year"], entries[-1]["month"]) == (2050, 4)
    assert entries[-1]["balance"] == 0
    assert sum(e["principal"] for e in entries) == facts["opening_principal_minor"]
    assert all(e["payment"] == facts["principal_interest_minor"] for e in entries[:-1])
    # The final payment only absorbs cent rounding.
    assert abs(entries[-1]["payment"] - facts["principal_interest_minor"]) < 500
    assert fixture.balance_minor == facts["opening_principal_minor"]


def test_schedule_pdf_is_professional_and_keeps_provenance_in_metadata():
    _, content = library_document("DEMO-02", "base", "amortization")
    reader = PdfReader(BytesIO(content), strict=True)
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "SYNTHETIC" not in text and "Fixture version" not in text
    for expected in (
        "Northstar Residential Servicing",
        "Marcus J. Delgado",
        "1847 Larkspur Lane, Westfield, NJ 07090",
        "4.250% fixed",
        "$1,534.85",
        "10/01/2026",
        "04/01/2050",
        f"Page 1 of {len(reader.pages)}",
    ):
        assert expected in text, expected
    assert "SYNTHETIC" in reader.metadata["/Keywords"]
    assert "DEMO-NORTH" in reader.metadata["/Keywords"]


def test_wrong_loan_variant_names_a_different_borrower():
    _, content = library_document("DEMO-02", "wrong_loan", "amortization")
    text = "\n".join(p.extract_text() for p in PdfReader(BytesIO(content)).pages)
    assert "0099000099" in text and "Patricia L. Owens" in text
    assert "Marcus J. Delgado" not in text


def test_fulfillment_letter_is_rendered_from_verified_records(client):
    case = load(client)
    draft_id = prepare(client, case)
    sent, *_ = complete(client, case, draft_id)
    body = read(client, case, "csp.status", reference_id=sent["reference"]["id"])["outbox"][
        "sent_content"
    ]["body"]
    assert body.startswith("Dear Marcus J. Delgado,")
    for expected in (
        "We received your request on September 18, 2026",
        "loan ending in 0002",
        "283 remaining scheduled monthly payments",
        "payment due October 1, 2026",
        "$1,534.85",
        "4.250%",
        "April 1, 2050",
        "(800) 555-0142",
        "Customer Correspondence Team\nNorthstar Residential Servicing",
        "Northstar Residential Servicing, LLC is a debt collector.",
    ):
        assert expected in body, expected
    assert "Supported information is available" not in body
    assert "fictional records" not in body


@pytest.mark.parametrize(
    ("code", "old_name", "name", "notice", "sender", "signature"),
    [
        (
            "DEMO-NORTH",
            "Northstar Demo Servicing",
            "Northstar Residential Servicing",
            "northstar-servicing-notice",
            "correspondence@northstarresidential.com",
            "Customer Correspondence Team\nNorthstar Residential Servicing",
        ),
        (
            "DEMO-HARBOR",
            "Harbor Demo Servicing",
            "Harbor Point Mortgage Services",
            "harbor-servicing-notice",
            "correspondence@harborpointmortgage.com",
            "Customer Care Team\nHarbor Point Mortgage Services",
        ),
    ],
)
def test_newer_client_version_supersedes_stored_configuration(
    client, application, code, old_name, name, notice, sender, signature
):
    with application.state.sessions() as session, session.begin():
        stored = session.get(ClientConfiguration, code)
        stored.version, stored.display_name = 1, old_name
    with application.state.sessions() as session, session.begin():
        install_catalogs(session)
    with application.state.sessions() as session:
        stored = session.scalar(select(ClientConfiguration).where(ClientConfiguration.code == code))
        assert stored.version == 2
        assert stored.display_name == name
        assert stored.settings["disclosure_keys"] == [notice]
        assert stored.settings["sender_email"] == sender
        assert stored.settings["signature"] == signature


def test_harbor_keeps_review_gate_and_realistic_contact_details():
    clients = [ClientFixture.model_validate(r) for r in read_json(CLIENTS)]
    settings = next(c for c in clients if c.code == "DEMO-HARBOR").settings
    assert settings["default_review_mode"] == "review_required"
    for key in ("legal_name", "support_email", "support_phone", "support_hours", "website"):
        assert settings[key] and "demo" not in settings[key].lower(), key
    assert "Synthetic" not in settings["signature"]
    knowledge = [KnowledgeFixture.model_validate(r) for r in read_json(KNOWLEDGE)]
    notice = next(k for k in knowledge if k.key == "harbor-servicing-notice")
    assert notice.version == 1 and notice.client_codes == ["DEMO-HARBOR"]
    assert notice.content.startswith("Harbor Point Mortgage Services, LLC is a debt collector.")
