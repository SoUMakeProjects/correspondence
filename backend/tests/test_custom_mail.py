"""Free-form intake, safe record matching and real attachment delivery regressions."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_mailbox import linked, send
from test_phase6 import TestModel, choice

from app.agent_model import ModelError
from app.fixture_data import load_fixture
from app.main import create_app
from app.models import Evidence


class IntakeModel(TestModel):
    def __init__(self, request_type="amortization", **changes):
        self.request_type, self.changes, self.calls = request_type, changes, 0

    def classify(self, message, timeout):
        self.calls += 1
        return choice(
            "classify_mail",
            **{
                "request_type": self.request_type,
                "certain": True,
                "loan_identifiers": [],
                "concern_quotes": [message["body"]],
                "requested_name": None,
                "eft_intent": None,
                **self.changes,
            },
        )


def custom(client, **changes):
    payload = {
        "request_id": str(uuid4()),
        "template_key": "CUSTOM",
        "sender": "marcus.j.delgado@outlook.com",
        "subject": "My schedule please",
        "body": "Please email the amortization schedule for loan 0099000002.",
        **changes,
    }
    response = client.post("/api/mail/messages", json=payload)
    assert response.status_code == 202, response.text
    return response.json(), payload


def test_custom_schedule_is_classified_processed_and_idempotent(settings):
    model = IntakeModel()
    app = create_app(settings, agent_model=model, start_worker=False)
    with TestClient(app) as client:
        message, payload = custom(client)
        app.state.automation_worker.run_once()
        case_id = linked(client, message)
        assert app.state.agent_worker.run_once()
        assert client.post("/api/mail/messages", json=payload).json()["id"] == message["id"]
        app.state.automation_worker.run_once()
        assert not app.state.agent_worker.run_once()
        state = client.get(f"/api/systems/cases/{case_id}").json()
        assert state["case"]["status"] == "closed"
        assert state["case"]["subject"] == payload["subject"]
        assert state["case"]["correspondence_text"] == payload["body"]
        assert state["case"]["original_received_at"] == message["created_at"]
        assert len(state["outbox"]) == len(state["packages"]) == len(state["notes"]) == 1
        assert state["loan"]["context"]["mail_intake"]["concerns"] == [payload["body"]]
        assert model.calls == 1
        assert state["outbox"][0]["sent_content"]["recipient"] == "marcus.j.delgado@outlook.com"
        assert not client.get(f"/api/cases/{case_id}/workflow").json()["input_options"]


@pytest.mark.parametrize(
    "kind,scenario",
    [
        ("name_change", "DEMO-01"),
        ("amortization", "DEMO-02"),
        ("tax", "DEMO-03"),
        ("bankruptcy", "DEMO-04"),
        ("eft", "DEMO-05"),
    ],
)
def test_custom_topics_use_actual_mail_and_only_record_evidence(settings, kind, scenario):
    fixture = load_fixture(scenario)
    model = IntakeModel(kind)
    app = create_app(settings, agent_model=model, start_worker=False)
    with TestClient(app) as client:
        message, _ = custom(
            client,
            sender=fixture.loan_context["authorized_recipient"],
            body=f"My custom {kind} request for loan {fixture.loan_identifier}.",
        )
        app.state.automation_worker.run_once()
        case_id = linked(client, message)
        state = client.get(f"/api/systems/cases/{case_id}").json()
        assert state["case"]["loan_identifier"] == fixture.loan_identifier
        assert state["loan"]["context"]["mail_intake"]["request_type"] == kind
        assert not message["attachments"]
        assert not any(
            e["details"].get("key") in {"signed-request", "legal-document", "request-copy"}
            for e in state["evidence"]
        )
        if kind == "name_change":
            assert state["loan"]["context"]["requested_legal_name"] is None
            assessment = client.get(f"/api/cases/{case_id}/assessment").json()
            assert "name_change_evidence_missing" in {f["code"] for f in assessment["findings"]}


def test_topic_does_not_select_a_different_loan(settings):
    app = create_app(
        settings,
        agent_model=IntakeModel("name_change", requested_name="Riley Newname"),
        start_worker=False,
    )
    with TestClient(app) as client:
        message, _ = custom(
            client, body="For loan 0099000002 please change my name to Riley Newname."
        )
        app.state.automation_worker.run_once()
        state = client.get(f"/api/systems/cases/{linked(client, message)}").json()
        assert state["case"]["loan_identifier"] == "0099000002"
        assert state["loan"]["context"]["requested_legal_name"] == "Riley Newname"
        assert state["case"]["family"] == "profile_change"


@pytest.mark.parametrize(
    "changes",
    [
        {"sender": "unknown@example.com", "body": "Send my schedule."},
        {"sender": "unknown@example.com"},
        {"body": "Send schedule for loan 0099000099."},
        {"body": "Send schedules for loans 0099000001 and 0099000002."},
    ],
)
def test_identity_exceptions_are_visible_without_inventing_cases(settings, changes):
    app = create_app(settings, agent_model=IntakeModel(), start_worker=False)
    with TestClient(app) as client:
        message, _ = custom(client, **changes)
        app.state.automation_worker.run_once()
        assert linked(client, message) is None
        assert not client.get("/api/operations").json()["cases"]
        reviews = client.get("/api/mail/intake-reviews").json()["reviews"]
        assert len(reviews) == 1 and reviews[0]["message"]["status"] == "needs_attention"
        resolution = {
            "request_id": str(uuid4()),
            "loan_identifier": "0099000002",
            "request_type": "amortization",
            "actor": "Reviewer",
            "note": "Verified identity and the intended loan with the requester.",
            "identity_verified": True,
        }
        result = client.post(f"/api/mail/intake/{reviews[0]['signal_id']}/resolve", json=resolution)
        assert result.status_code == 200, result.text
        app.state.automation_worker.run_once()
        assert linked(client, message)
        assert not client.get("/api/mail/intake-reviews").json()["reviews"]
        app.state.agent_worker.run_once()
        state = client.get(f"/api/systems/cases/{linked(client, message)}").json()
        assert state["outbox"][0]["sent_content"]["recipient"] == "marcus.j.delgado@outlook.com"


def test_model_failure_is_bounded_and_retryable(settings):
    class Failing(IntakeModel):
        def classify(self, message, timeout):
            self.calls += 1
            raise ModelError("azure_connection_or_timeout")

    model = Failing()
    app = create_app(settings, agent_model=model, start_worker=False)
    with TestClient(app) as client:
        custom(client)
        for _ in range(3):
            app.state.automation_worker.run_once()
        assert model.calls == 1
        signal = client.get("/api/mail/intake-reviews").json()["reviews"][0]["signal_id"]
        assert client.post(f"/api/mail/intake/{signal}/retry").status_code == 200
        app.state.automation_worker.run_once()
        assert model.calls == 2


def test_ungrounded_model_output_is_rejected(settings):
    app = create_app(
        settings, agent_model=IntakeModel(concern_quotes=["invented request"]), start_worker=False
    )
    with TestClient(app) as client:
        message, _ = custom(client)
        app.state.automation_worker.run_once()
        assert not linked(client, message)
        assert (
            "invalid_mail_classification"
            in client.get("/api/mail/intake-reviews").json()["reviews"][0]["detail"]
        )


def test_custom_validation_and_fixed_recipient(client):
    for change in (
        {"sender": "bad"},
        {"sender": "a@b.com\nBcc:x@y.com"},
        {"subject": " "},
        {"body": ""},
        {"subject": "x\ny"},
        {"recipient": "x@y.com"},
        {"thread_id": str(uuid4())},
    ):
        response = client.post(
            "/api/mail/messages",
            json={
                "request_id": str(uuid4()),
                "template_key": "CUSTOM",
                "sender": "marcus.j.delgado@outlook.com",
                "subject": "Schedule",
                "body": "My schedule please",
                **change,
            },
        )
        assert response.status_code == 422
    message, payload = custom(client)
    assert message["recipient"] == "correspondence@servicing.example.com"
    assert client.post("/api/mail/messages", json={**payload, "body": "changed"}).status_code == 409


def test_previews_are_scoped_and_delivery_uses_immutable_copy(settings):
    app = create_app(settings, agent_model=IntakeModel(), start_worker=False)
    with TestClient(app) as client:
        response = client.get("/api/mail/templates/DEMO-01/attachments/signed-request")
        assert response.status_code == 200 and response.content.startswith(b"%PDF")
        assert client.get("/api/cases").json()["total"] == 0
        assert (
            client.get("/api/mail/templates/DEMO-02/attachments/signed-request").status_code == 404
        )
        response = client.get("/api/mail/templates/name-proof/attachments/legal-document")
        assert response.status_code == 200 and response.content.startswith(b"%PDF")
        initial, _ = send(client, "DEMO-01")
        assert client.get(f"/api/mail/messages/{initial['id']}/attachments/0").content.startswith(
            b"%PDF"
        )
        message, _ = custom(client)
        app.state.automation_worker.run_once()
        case_id = linked(client, message)
        # The first ready run may be the name-change request; process both.
        while app.state.agent_worker.run_once():
            pass
        state = client.get(f"/api/systems/cases/{case_id}").json()
        delivery = state["outbox"][0]["id"]
        url = f"/api/mail/deliveries/{delivery}/attachments/0"
        original = client.get(url)
        assert original.status_code == 200 and original.content.startswith(b"%PDF")
        with app.state.sessions() as session:
            evidence = next(
                e
                for e in session.scalars(select(Evidence).where(Evidence.case_id == case_id))
                if e.storage_key
            )
            (settings.data_dir / "documents" / evidence.storage_key).write_bytes(
                b"changed after delivery"
            )
        assert client.get(url).content == original.content
        assert client.get(f"/api/mail/deliveries/{delivery}/attachments/1").status_code == 404
