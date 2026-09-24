from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select

from app.config import Settings
from app.main import create_app
from app.models import AgentRun, CaseEvent, CorrespondenceCase, Loan, SimulationInstance
from app.repository import claim_next_run, renew_lease


def create(client, payload):
    response = client.post("/api/cases", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_persistence_and_exact_values(application, settings, case_payload):
    with TestClient(application) as first:
        item = create(first, case_payload)
        assert item["loan_identifier"] == "000000012345"
        assert item["ccid"] == "00009876"
        assert item["balance_minor"] == 123456789
        assert item["original_received_at"] == "2026-11-01T05:30:00.123456Z"
        events = first.get(f"/api/cases/{item['id']}/events").json()
        assert len(events["items"]) == 1
    with TestClient(create_app(settings)) as second:
        assert second.get(f"/api/cases/{item['id']}").json() == item
        assert second.get(f"/api/cases/{item['id']}/events").json() == events
        assert second.get("/api/health").json()["schema_revision"] == "0009"


@pytest.mark.parametrize(
    "change",
    [
        {"loan_identifier": 12345},
        {"balance_minor": 12.34},
        {"balance_minor": True},
        {"balance_minor": -1},
        {"original_received_at": "2026-09-22T14:00:00"},
        {"owner": " "},
        {"family": "unknown"},
        {"unexpected_field": "should-not-be-echoed"},
    ],
)
def test_invalid_input_does_not_write_records(client, application, case_payload, change):
    response = client.post("/api/cases", json={**case_payload, **change})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert "should-not-be-echoed" not in response.text
    with application.state.sessions() as session:
        for model in (SimulationInstance, Loan, CorrespondenceCase, CaseEvent):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_update_revision_event_and_retry_are_atomic(client, case_payload):
    item = create(client, case_payload)
    path = f"/api/cases/{item['id']}"
    patch = {
        "mutation_id": str(uuid4()),
        "expected_revision": 1,
        "owner": "Second reviewer",
        "status": "under_review",
    }
    updated = client.patch(path, json=patch)
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    assert updated.json()["original_received_at"] == item["original_received_at"]
    assert client.patch(path, json=patch).json() == updated.json()
    mismatch = client.patch(path, json={**patch, "owner": "Different payload"})
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "mutation_id_reused"
    stale = client.patch(
        path, json={**patch, "mutation_id": str(uuid4()), "owner": "Stale reviewer"}
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_revision"
    assert client.get(path).json()["owner"] == "Second reviewer"
    events = client.get(path + "/events").json()
    assert len(events["items"]) == 2
    assert events["items"][1]["action_id"]
    assert len(client.get(path + "/actions").json()) == 1
    assert client.get(path + f"/events?after={events['next_cursor']}").json()["items"] == []


def test_forbidden_transition_and_empty_patch_do_not_write(client, case_payload):
    item = create(client, case_payload)
    path = f"/api/cases/{item['id']}"
    base = {"mutation_id": str(uuid4()), "expected_revision": 1}
    assert client.patch(path, json=base).status_code == 422
    assert client.patch(path, json={**base, "owner": None}).status_code == 422
    assert client.patch(path, json={**base, "status": "closed"}).status_code == 409
    assert (
        client.patch(
            path, json={**base, "original_received_at": "2026-09-22T00:00:00Z"}
        ).status_code
        == 422
    )
    assert client.get(path).json()["revision"] == 1
    assert len(client.get(path + "/events").json()["items"]) == 1


def test_create_idempotency_and_simulation_conflicts(client, application, case_payload):
    item = create(client, case_payload)
    assert create(client, case_payload)["id"] == item["id"]
    assert client.post("/api/cases", json={**case_payload, "owner": "Changed"}).status_code == 409
    duplicate = {**case_payload, "request_id": str(uuid4()), "simulation_id": item["simulation_id"]}
    assert client.post("/api/cases", json=duplicate).status_code == 409
    conflicting_loan = {**duplicate, "ccid": "different", "client_code": "OTHER-CLIENT"}
    assert client.post("/api/cases", json=conflicting_loan).status_code == 409
    # Conflict after creating a new loan must roll back that loan too.
    assert (
        client.post("/api/cases", json={**duplicate, "loan_identifier": "00000999"}).status_code
        == 409
    )
    with application.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(Loan)) == 1
        assert session.scalar(select(func.count()).select_from(CorrespondenceCase)) == 1
        assert session.scalar(select(func.count()).select_from(CaseEvent)) == 1


def test_worklist_order_pagination_and_case_scoped_events(client, case_payload):
    newer = create(client, case_payload)
    older = create(
        client,
        {
            **case_payload,
            "request_id": str(uuid4()),
            "original_received_at": "2026-01-01T00:00:00Z",
        },
    )
    assert client.get("/api/cases?limit=1").json()["items"][0]["id"] == older["id"]
    assert client.get("/api/cases?limit=1&offset=1").json()["items"][0]["id"] == newer["id"]
    history = client.get(f"/api/cases/{older['id']}/events").json()
    assert all(row["case_id"] == older["id"] for row in history["items"])
    assert client.get("/api/cases?limit=0").status_code == 422


def test_configuration_is_redacted_and_non_synthetic_execution_is_blocked(tmp_path, case_payload):
    settings = Settings(
        _env_file=None,
        app_data_dir=tmp_path,
        azure_openai_base_url="https://example.openai.azure.com/openai/v1/",
        azure_openai_deployment="private-deployment-name",
        azure_openai_api_key="test-secret-never-emit",
        azure_openai_live_tests_enabled=True,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/config")
        config = response.json()
        assert config["azure_configuration_complete"] is True
        assert config["model_connection_verified"] is False
        assert config["model_calls_enabled"] is True
        assert config["agent_available"] is True
        assert "private-deployment-name" not in response.text
        assert "test-secret-never-emit" not in response.text
        assert "example.openai" not in response.text
        item = create(client, case_payload)
        assert (
            client.post(f"/api/cases/{item['id']}/runs", json={"expected_revision": 1}).status_code
            == 422
        )
        assert client.get(f"/api/cases/{item['id']}/runs").json() == []
        assert (
            client.post(
                f"/api/cases/{item['id']}/reviews",
                json={
                    "draft_id": str(uuid4()),
                    "draft_version": 1,
                    "expected_case_revision": 1,
                    "decision": "approve",
                },
            ).status_code
            == 422
        )


def test_inspection_and_empty_evidence_have_real_counts(client, case_payload):
    item = create(client, case_payload)
    assert client.get(f"/api/cases/{item['id']}/evidence").json() == []
    inspection = client.get(f"/api/simulations/{item['simulation_id']}").json()
    assert inspection["case_count"] == inspection["loan_count"] == 1
    assert inspection["outbox_count"] == inspection["indexed_package_count"] == 0
    assert inspection["simulator_operations_available"] is True
    assert client.get(f"/api/cases/{uuid4()}/evidence").status_code == 404


def test_migration_creates_all_planned_record_tables(application, client):
    tables = set(inspect(application.state.engine).get_table_names())
    assert tables == {
        "mail_attachments",
        "mail_threads",
        "mail_messages",
        "automation_signals",
        "servicing_history",
        "rule_evaluations",
        "alembic_version",
        "simulation_instances",
        "loans",
        "cases",
        "concerns",
        "evidence",
        "knowledge_items",
        "specialist_tasks",
        "specialist_handoffs",
        "agent_runs",
        "response_drafts",
        "action_receipts",
        "review_decisions",
        "outbox_entries",
        "indexed_packages",
        "final_notes",
        "case_events",
        "taxonomy_entries",
        "source_manifest_entries",
        "client_configurations",
    }


def test_worker_ownership_is_persisted_and_old_tokens_are_fenced(application, client, case_payload):
    item = create(client, case_payload)
    with application.state.sessions.begin() as session:
        run = AgentRun(case_id=item["id"], case_revision=1)
        session.add(run)
        session.flush()
        run_id = run.id
    with application.state.sessions() as session:
        first = claim_next_run(session, "worker-one")
        token = first.lease_token
        assert first.checkpoint["reconciliation_required"] is False
        session.commit()
    with application.state.sessions() as session:
        assert claim_next_run(session, "worker-two") is None
        session.commit()
    with application.state.sessions.begin() as session:
        run = session.get(AgentRun, run_id)
        run.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with application.state.sessions() as session:
        reclaimed = claim_next_run(session, "worker-two")
        assert reclaimed.id == run_id
        assert reclaimed.lease_token != token
        assert reclaimed.checkpoint["reconciliation_required"] is True
        current_token = reclaimed.lease_token
        session.commit()
    with application.state.sessions.begin() as session:
        assert renew_lease(session, run_id, token) is False
        assert renew_lease(session, run_id, current_token) is True
