"""Message-driven acceptance: no browser start/resume calls are needed."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_phase6 import TestModel
from test_phase7 import approve

from app.main import create_app
from app.models import AutomationSignal, ClientConfiguration, MailMessage


def send(client, template="DEMO-02", thread=None, request_id=None):
    payload = {
        "request_id": request_id or str(uuid4()),
        "template_key": template,
        "thread_id": thread,
    }
    result = client.post("/api/mail/messages", json=payload)
    assert result.status_code == 202, result.text
    return result.json(), payload


def linked(client, message):
    response = client.get(f"/api/mail/threads/{message['thread_id']}")
    assert response.status_code == 200, response.text
    return response.json()["thread"]["case_id"]


@pytest.mark.parametrize("template", [f"DEMO-0{i}" for i in range(1, 6)])
def test_each_mail_template_creates_its_case_and_waits_for_connection(
    client, application, template
):
    message, payload = send(client, template)
    assert client.get("/api/cases").json()["total"] == 0
    application.state.automation_worker.run_once()
    case_id = linked(client, message)
    case = client.get(f"/api/cases/{case_id}").json()
    assert case["loan_identifier"] == "009900000" + template[-1]
    assert case["correspondence_text"] == message["body"]
    assert client.post("/api/mail/messages", json=payload).json()["id"] == message["id"]
    application.state.automation_worker.run_once()
    assert client.get("/api/cases").json()["total"] == 1
    operations = client.get("/api/operations")
    assert operations.status_code == 200, operations.text
    assert operations.json()["signals"][0]["status"] == "ready"
    assert "Azure" in operations.json()["signals"][0]["detail"]
    system = client.get(f"/api/systems/cases/{case_id}")
    assert system.status_code == 200, system.text
    assert system.json()["thread"]["id"] == message["thread_id"]


def test_automatic_delivery_and_system_views_survive_restart_without_duplicates(settings):
    app = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(app) as client:
        message, payload = send(client)
        app.state.automation_worker.run_once()
        case_id = linked(client, message)
        assert app.state.agent_worker.run_once()
        app.state.automation_worker.run_once()
        case = client.get(f"/api/systems/cases/{case_id}").json()
        assert case["case"]["status"] == "closed"
        assert all(len(case[key]) == 1 for key in ("runs", "outbox", "packages", "notes"))
        assert case["runs"][0]["checkpoint"]["trigger"] == "mail.received"
        assert "lease_token" not in case["runs"][0]
        thread = client.get(f"/api/mail/threads/{message['thread_id']}").json()
        assert thread["deliveries"][0]["id"] == case["outbox"][0]["id"]
    restarted = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(restarted) as client:
        assert client.post("/api/mail/messages", json=payload).status_code == 202
        restarted.state.automation_worker.run_once()
        assert not restarted.state.agent_worker.run_once()
        assert len(client.get(f"/api/cases/{case_id}/runs").json()) == 1


def test_approval_automatically_resumes_exact_response_once(settings):
    app = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(app) as client:
        with app.state.sessions() as session, session.begin():
            config = session.get(ClientConfiguration, "DEMO-NORTH")
            config.settings = {**config.settings, "default_review_mode": "review_required"}
        message, _ = send(client)
        app.state.automation_worker.run_once()
        case_id = linked(client, message)
        app.state.agent_worker.run_once()
        state = client.get(f"/api/cases/{case_id}/workflow").json()
        assert not state["drafts"][-1]["sent"]
        assert case_id in client.get("/api/operations").json()["review_case_ids"]
        _, payload = approve(client, {"id": case_id}, state["drafts"][-1]["id"])
        assert client.post(f"/api/cases/{case_id}/reviews", json=payload).status_code == 201
        app.state.automation_worker.run_once()
        app.state.agent_worker.run_once()
        app.state.automation_worker.run_once()
        case = client.get(f"/api/systems/cases/{case_id}").json()
        assert case["case"]["status"] == "closed"
        assert len(case["runs"]) == 2 and len(case["outbox"]) == 1
        assert case["outbox"][0]["draft_id"] == state["drafts"][-1]["id"]
        assert case_id not in client.get("/api/operations").json()["review_case_ids"]


def test_same_thread_reply_and_committed_input_recovery_are_idempotent(client, application):
    message, _ = send(client, "DEMO-01")
    application.state.automation_worker.run_once()
    case_id = linked(client, message)
    original = client.get(f"/api/cases/{case_id}").json()
    reply, payload = send(client, "name-proof", message["thread_id"])
    worker = application.state.automation_worker
    # Simulate a process ending after the input commits but before acknowledgment.
    original_mark = worker.mark_received
    worker.mark_received = lambda *_: None
    worker.run_once()
    version = client.get(f"/api/cases/{case_id}").json()["revision"]
    worker.mark_received = original_mark
    worker.run_once()
    worker.run_once()
    after = client.get(f"/api/cases/{case_id}").json()
    assert after["revision"] == version > original["revision"]
    assert after["original_received_at"] == original["original_received_at"]
    assert client.post("/api/mail/messages", json=payload).json()["id"] == reply["id"]
    assert linked(client, reply) == case_id
    assert len(client.get(f"/api/cases/{case_id}/workflow").json()["contacts"]) == 1
    with application.state.sessions() as session:
        assert session.get(MailMessage, reply["id"]).status == "processed"
        assert len(list(session.scalars(select(AutomationSignal)))) == 2


def test_invalid_templates_and_cross_thread_replies_are_rejected(client):
    message, payload = send(client, "DEMO-01")
    assert (
        client.post("/api/mail/messages", json={**payload, "template_key": "DEMO-02"}).status_code
        == 409
    )
    assert (
        client.post(
            "/api/mail/messages", json={"request_id": str(uuid4()), "template_key": "unknown"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/mail/messages",
            json={
                "request_id": str(uuid4()),
                "template_key": "eft-outgoing_refund",
                "thread_id": message["thread_id"],
            },
        ).status_code
        == 422
    )


def test_pending_messages_are_received_after_a_restart(settings):
    with TestClient(create_app(settings, start_worker=False)) as client:
        message, _ = send(client)
    app = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(app) as client:
        app.state.automation_worker.run_once()
        app.state.agent_worker.run_once()
        assert client.get(f"/api/cases/{linked(client, message)}").json()["status"] == "closed"


def test_stopped_agent_does_not_restart_when_another_email_arrives(settings):
    app = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(app) as client:
        message, _ = send(client)
        app.state.automation_worker.run_once()
        case_id = linked(client, message)
        run = client.get(f"/api/cases/{case_id}/runs").json()[0]
        assert client.post(f"/api/runs/{run['id']}/stop").status_code == 200
        send(client, "schedule-copy", message["thread_id"])
        app.state.automation_worker.run_once()
        assert len(client.get(f"/api/cases/{case_id}/runs").json()) == 1
        assert not app.state.agent_worker.run_once()
        thread = client.get(f"/api/mail/threads/{message['thread_id']}").json()
        assert thread["messages"][-1]["status"] == "received"
        assert "stopped" in thread["signals"][-1]["detail"]
        revision = client.get(f"/api/cases/{case_id}").json()["revision"]
        resume = {"request_id": str(uuid4()), "expected_revision": revision}
        result = client.post(f"/api/automation/cases/{case_id}/resume", json=resume)
        assert result.status_code == 202, result.text
        # A stale scheduling read must not erase the operator request's retry identity.
        app.state.automation_worker.defer(result.json()["id"], "Case changed.", reset_input=True)
        assert (
            client.post(f"/api/automation/cases/{case_id}/resume", json=resume).status_code == 202
        )
        app.state.automation_worker.run_once()
        thread = client.get(f"/api/mail/threads/{message['thread_id']}").json()
        assert thread["messages"][-1]["status"] == "processed"
        runs = client.get(f"/api/cases/{case_id}/runs").json()
        assert len(runs) == 2 and runs[-1]["case_revision"] > revision
        assert len(runs[-1]["checkpoint"]["trigger_ids"]) == 2
        assert app.state.agent_worker.run_once()
        assert client.get(f"/api/cases/{case_id}").json()["status"] == "closed"
        assert (
            client.post(f"/api/automation/cases/{case_id}/resume", json=resume).json()["id"]
            == result.json()["id"]
        )
        app.state.automation_worker.run_once()
        assert len(client.get(f"/api/cases/{case_id}/runs").json()) == 2
        assert (
            client.get(f"/api/mail/threads/{message['thread_id']}").json()["reply_templates"] == []
        )


def test_evidence_arriving_with_approval_is_applied_before_continuation(settings):
    app = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(app) as client:
        with app.state.sessions() as session, session.begin():
            config = session.get(ClientConfiguration, "DEMO-NORTH")
            config.settings = {**config.settings, "default_review_mode": "review_required"}
        message, _ = send(client)
        app.state.automation_worker.run_once()
        case_id = linked(client, message)
        app.state.agent_worker.run_once()
        state = client.get(f"/api/cases/{case_id}/workflow").json()
        approve(client, {"id": case_id}, state["drafts"][-1]["id"])
        send(client, "schedule-copy", message["thread_id"])
        app.state.automation_worker.run_once()
        state = client.get(f"/api/cases/{case_id}/workflow").json()
        assert not state["drafts"][-1]["current"]
        assert not state["drafts"][-1]["approved"]
        runs = client.get(f"/api/cases/{case_id}/runs").json()
        assert len(runs) == 2 and len(runs[-1]["checkpoint"]["trigger_ids"]) == 2
        assert not client.get(f"/api/cases/{case_id}/artifacts").json()["outbox"]
