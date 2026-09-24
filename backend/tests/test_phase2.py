import json
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import MetaData, func, select

from app.catalogs import install_catalogs
from app.data_validation import validate_data
from app.fixture_data import load_fixture
from app.models import (
    CorrespondenceCase,
    Evidence,
    KnowledgeItem,
    SimulationInstance,
    SourceManifestEntry,
)
from app.source_catalog import DATA_ROOT, classify_source_row, read_json


def load(client, scenario="DEMO-02", variant="base", request_id=None):
    response = client.post(
        f"/api/scenarios/{scenario}/instances",
        json={"request_id": request_id or str(uuid4()), "variant": variant},
    )
    assert response.status_code == 201, response.text
    return response.json()


def evidence_for(client, case):
    return client.get(f"/api/cases/{case['id']}/evidence").json()


def test_source_and_document_artifacts_reconcile():
    result = validate_data()
    assert result["scenarios"] == 5
    assert result["scenario_variants"] == 12
    assert result["documents"] == {"available": 15, "missing": 2, "unreadable": 1}
    report = read_json(DATA_ROOT / "knowledge/reconciliation.v1.json")
    assert report["taxonomy_count"] == 149
    assert report["taxonomy_distinct_subclass_labels"] == 144
    assert report["knowledge_row_count"] == 527
    assert report["repeated_label_groups"] == 14
    assert report["summary_reported_rows"] == 525
    assert report["statuses"] == {"curated": 5, "excluded": 10, "requires_review": 512}


def test_credentials_and_raw_candidates_are_never_serialized(client, application):
    sentinel = "TEST-CREDENTIAL-DO-NOT-EXPORT"
    assert classify_source_row(474, (sentinel, sentinel, sentinel), [])[0] == "excluded"
    assert (
        classify_source_row(200, ("Escrow", "Example", f"Password: {sentinel}"), [])[0]
        == "excluded"
    )
    manifest = read_json(DATA_ROOT / "knowledge/source_manifest.v1.json")
    assert {row["row_number"] for row in manifest} == set(range(2, 529))
    assert all(
        set(row)
        == {"id", "row_number", "category", "status", "reason", "curated_item_keys", "review_flags"}
        for row in manifest
    )
    assert manifest[474 - 2]["curated_item_keys"] == []
    with application.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(SourceManifestEntry)) == 527
        # Runtime candidates have metadata only, not a text/quarantine field.
        assert "content" not in SourceManifestEntry.__table__.columns
        assert all(
            "S04:r474" not in row.source_reference for row in session.scalars(select(KnowledgeItem))
        )


def test_five_base_cases_have_scoped_synthetic_evidence_and_no_future_answers(client):
    all_evidence = set()
    loaded = {}
    for scenario in ("DEMO-01", "DEMO-02", "DEMO-03", "DEMO-04", "DEMO-05"):
        case = load(client, scenario)
        loaded[scenario] = case
        assert case["loan_identifier"].startswith("009900000")
        assert case["status"] == "queued" and case["classification"] is None
        evidence = evidence_for(client, case)
        assert all(row["case_id"] == case["id"] and row["synthetic"] for row in evidence)
        ids = {row["id"] for row in evidence}
        assert not ids & all_evidence
        all_evidence |= ids
        tasks = client.get(f"/api/cases/{case['id']}/tasks").json()
        assert all(
            set(task["request"]["evidence_ids"]) <= ids and task["case_id"] == case["id"]
            for task in tasks
        )
        concerns = client.get(f"/api/cases/{case['id']}/concerns").json()
        assert concerns and all(set(row["evidence_ids"]) <= ids for row in concerns)
        inspection = client.get(f"/api/simulations/{case['simulation_id']}").json()
        assert inspection["simulation"]["evaluation_at"] == "2026-09-22T16:00:00Z"
        assert inspection["outbox_count"] == inspection["action_count"] == 0
        text = json.dumps(evidence)
        assert "base_disposition" not in text and "required_findings" not in text
    profile = evidence_for(client, loaded["DEMO-01"])
    assert (
        next(row for row in profile if row["details"].get("key") == "legal-document")["details"][
            "availability"
        ]
        == "missing"
    )
    assert "DEMO-NAME-RESULT-001" not in json.dumps(profile)
    tax_facts = evidence_for(client, loaded["DEMO-03"])[0]["details"]["facts"]
    assert tax_facts["tax_status"] == "scheduled" and tax_facts["tax_paid_at"] is None
    credit = evidence_for(client, loaded["DEMO-04"])
    assert credit[0]["details"]["facts"]["servicing_bankruptcy_status"] == "discharged"
    assert any(
        row["details"]["facts"].get("reported_status") == "dismissed_without_discharge"
        for row in credit
    )
    assert (
        credit[0]["details"]["facts"]["authorized_recipient"]
        == "monica.ferrante@ferrantehale.example.com"
    )
    assert "BK-REV-260922-004" not in json.dumps(credit)
    eft = evidence_for(client, loaded["DEMO-05"])
    assert eft[0]["details"]["facts"]["eft_intent"] is None


@pytest.mark.parametrize(
    "variant,expected_status",
    [("base", 200), ("missing_document", 404), ("unreadable_document", 422), ("wrong_loan", 200)],
)
def test_document_downloads_validate_file_and_case_scope(client, variant, expected_status):
    case = load(client, variant=variant)
    attachment = next(
        row for row in evidence_for(client, case) if row["details"].get("key") == "amortization"
    )
    path = f"/api/cases/{case['id']}/evidence/{attachment['id']}/file"
    response = client.get(path)
    assert response.status_code == expected_status
    if expected_status == 200:
        reader = PdfReader(BytesIO(response.content), strict=True)
        content = "\n".join(page.extract_text() for page in reader.pages)
        assert "$0.00" in content
        # Provenance lives in PDF metadata rather than on every printed page.
        assert "SYNTHETIC" in str(reader.metadata.get("/Keywords", ""))
        claimed = "0099000099" if variant == "wrong_loan" else case["loan_identifier"]
        assert claimed in content
        assert attachment["details"]["loan_identifier"] == claimed
    other = load(client, "DEMO-01")
    assert (
        client.get(f"/api/cases/{other['id']}/evidence/{attachment['id']}/file").status_code == 404
    )


def test_repeat_load_is_idempotent_and_fresh_load_preserves_history(client, application):
    request_id = str(uuid4())
    first = load(client, request_id=request_id)
    assert load(client, request_id=request_id) == first
    mismatch = client.post(
        "/api/scenarios/DEMO-02/instances", json={"request_id": request_id, "variant": "wrong_loan"}
    )
    assert mismatch.status_code == 409
    first_evidence = evidence_for(client, first)
    assert (
        client.patch(
            f"/api/cases/{first['id']}",
            json={
                "mutation_id": str(uuid4()),
                "expected_revision": 1,
                "owner": "Retained reviewer",
            },
        ).status_code
        == 200
    )
    fresh = load(client)
    assert fresh["simulation_id"] != first["simulation_id"]
    assert client.get(f"/api/cases/{first['id']}").json()["owner"] == "Retained reviewer"
    assert evidence_for(client, first) == first_evidence
    assert len(client.get(f"/api/cases/{first['id']}/events").json()["items"]) == 2
    with application.state.sessions() as session, session.begin():
        install_catalogs(session)
        assert session.scalar(select(func.count()).select_from(KnowledgeItem)) == 17


@pytest.mark.parametrize("scenario", ["DEMO-01", "DEMO-03", "DEMO-04", "DEMO-05"])
def test_prepared_followups_are_separate_fresh_starting_states(client, scenario):
    base = load(client, scenario)
    supplied = load(client, scenario, "followup")
    assert base["simulation_id"] != supplied["simulation_id"]
    base_facts = evidence_for(client, base)[0]["details"]["facts"]
    followup_facts = evidence_for(client, supplied)[0]["details"]["facts"]
    if scenario == "DEMO-01":
        assert base_facts["profile_update_result"] is None
        assert followup_facts["profile_update_result"] == "DEMO-NAME-RESULT-001"
    elif scenario == "DEMO-03":
        assert followup_facts["tax_status"] == "scheduled" and followup_facts["tax_paid_at"] is None
    elif scenario == "DEMO-04":
        assert followup_facts["servicing_bankruptcy_status"] == "dismissed_without_discharge"
        assert followup_facts["communication_restriction"] == "representative_only"
    else:
        assert followup_facts["eft_intent"] == "outgoing_refund"
        assert followup_facts["refund_authorization"] is None


def test_knowledge_requires_applicability_and_curated_state(client, application):
    query = "/api/knowledge?scenario_id=DEMO-01&client_code=DEMO-NORTH"
    result = client.get(query).json()
    assert "profile-evidence" in {row["key"] for row in result}
    assert "demo-disclosure-north" in {row["key"] for row in result}
    assert "demo-disclosure-harbor" not in {row["key"] for row in result}
    assert "tax-schedule-guidance" not in {row["key"] for row in result}
    assert all(
        row["source_references"] and row["limitations"] and row["status"] == "curated_demo"
        for row in result
    )
    assert {row["key"] for row in client.get(query + "&q=legal-name&kind=guidance").json()} == {
        "profile-evidence"
    }
    selected = next(row for row in result if row["key"] == "profile-evidence")
    with application.state.sessions() as session, session.begin():
        session.get(KnowledgeItem, selected["id"]).status = "requires_review"
    assert "profile-evidence" not in {row["key"] for row in client.get(query).json()}
    assert client.get("/api/taxonomy?limit=200").json()["total"] == 149
    assert len(client.get("/api/clients").json()) == 2


def test_file_failure_rolls_back_case_and_removes_only_new_files(
    client, application, settings, monkeypatch
):
    original = Path.open
    opened = 0

    def fail_second_write(path, mode="r", *args, **kwargs):
        nonlocal opened
        if mode == "xb" and path.suffix == ".pdf":
            opened += 1
            if opened == 2:
                raise OSError("Synthetic disk write failure")
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_second_write)
    with pytest.raises(OSError, match="Synthetic disk write failure"):
        load(client, "DEMO-04")
    with application.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(CorrespondenceCase)) == 0
        assert session.scalar(select(func.count()).select_from(SimulationInstance)) == 0
        assert session.scalar(select(func.count()).select_from(Evidence)) == 0
    assert not list((settings.data_dir / "documents").glob("*.pdf"))


def test_bad_fixture_reference_is_rejected_before_loading():
    fixture = load_fixture("DEMO-03")
    data = fixture.model_dump()
    data["tasks"][0]["evidence_keys"] = ["not-a-document"]
    with pytest.raises(ValueError, match="unknown document"):
        type(fixture).model_validate(data)


def test_phase1_database_upgrade_preserves_case_event_and_evidence(settings):
    from app.db import make_engine
    from app.main import create_app
    from app.migrations import migration_config

    engine = make_engine(settings.database_url)
    config = migration_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001")
        metadata = MetaData()
        metadata.reflect(bind=connection)
        ids = {name: str(uuid4()) for name in ("simulation", "loan", "case", "evidence")}
        timestamp = "2026-09-17T14:00:00.123456+00:00"

        def insert(name, **values):
            connection.execute(metadata.tables[name].insert().values(**values))

        insert(
            "simulation_instances",
            id=ids["simulation"],
            scenario_key="foundation",
            fixture_version="0",
            evaluation_at=timestamp,
            created_at=timestamp,
        )
        insert(
            "loans",
            id=ids["loan"],
            simulation_id=ids["simulation"],
            loan_identifier="0000000042",
            client_code="DEMO-NORTH",
            borrower_display_name="Preserved Sample",
            balance_minor=12345,
            currency="USD",
            context={},
            created_at=timestamp,
        )
        insert(
            "cases",
            id=ids["case"],
            loan_id=ids["loan"],
            simulation_id=ids["simulation"],
            creation_key=str(uuid4()),
            creation_hash="0" * 64,
            ccid="00000099",
            subject="Preserve prior phase",
            correspondence_text="Synthetic retained request",
            family="document_request",
            owner="Original reviewer",
            status="queued",
            original_received_at=timestamp,
            revision=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
        insert(
            "case_events",
            case_id=ids["case"],
            kind="case.created",
            actor="local_presenter",
            payload={"revision": 1},
            created_at=timestamp,
        )
        insert(
            "evidence",
            id=ids["evidence"],
            case_id=ids["case"],
            title="Retained synthetic evidence",
            source="test",
            source_reference="fixture:prior",
            version=1,
            synthetic=True,
            created_at=timestamp,
        )
    engine.dispose()
    with TestClient(create_app(settings)) as client:
        case = client.get(f"/api/cases/{ids['case']}").json()
        assert case["loan_identifier"] == "0000000042" and case["balance_minor"] == 12345
        assert case["owner"] == "Original reviewer"
        assert case["original_received_at"] == "2026-09-17T14:00:00.123456Z"
        assert len(client.get(f"/api/cases/{ids['case']}/events").json()["items"]) == 1
        assert evidence_for(client, case)[0]["details"] == {}
        assert client.get("/api/health").json()["schema_revision"] == "0009"


def test_changed_file_is_not_served_as_verified_evidence(client, application, settings):
    case = load(client)
    attachment = next(
        row for row in evidence_for(client, case) if row["details"].get("key") == "amortization"
    )
    with application.state.sessions() as session:
        key = session.get(Evidence, attachment["id"]).storage_key
    path = settings.data_dir / "documents" / key
    path.write_bytes(path.read_bytes() + b"unexpected change")
    response = client.get(f"/api/cases/{case['id']}/evidence/{attachment['id']}/file")
    assert response.status_code == 409 and response.json()["error"]["code"] == "document_changed"
