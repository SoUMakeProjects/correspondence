"""Shared demo reset: both apps return to the base state after setup."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_mailbox import linked, send
from test_phase6 import TestModel

from app.main import create_app
from app.models import (
    ClientConfiguration,
    CorrespondenceCase,
    KnowledgeItem,
    MailMessage,
    TaxonomyEntry,
)


def test_reset_clears_cases_mail_and_documents_but_keeps_catalogs(settings):
    app = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(app) as client:
        assert client.get("/api/workspace/reset").json()["generation"] == "initial"
        message, _ = send(client)
        app.state.automation_worker.run_once()
        case_id = linked(client, message)
        assert app.state.agent_worker.run_once()
        assert client.get(f"/api/systems/cases/{case_id}").json()["case"]["status"] == "closed"
        documents = settings.data_dir / "documents"
        assert any(documents.iterdir())
        with app.state.sessions() as session:
            catalogs = [
                session.scalar(select(func.count()).select_from(model))
                for model in (TaxonomyEntry, ClientConfiguration, KnowledgeItem)
            ]

        result = client.post("/api/workspace/reset")
        assert result.status_code == 200, result.text
        generation = result.json()["generation"]
        assert generation != "initial" and result.json()["reset_at"]
        assert client.get("/api/workspace/reset").json()["generation"] == generation

        assert client.get("/api/cases").json()["total"] == 0
        operations = client.get("/api/operations").json()
        assert operations["cases"] == [] and operations["signals"] == []
        assert client.get(f"/api/mail/threads/{message['thread_id']}").status_code == 404
        assert not any(documents.iterdir())
        with app.state.sessions() as session:
            assert session.scalar(select(func.count()).select_from(MailMessage)) == 0
            assert session.scalar(select(func.count()).select_from(CorrespondenceCase)) == 0
            assert [
                session.scalar(select(func.count()).select_from(model))
                for model in (TaxonomyEntry, ClientConfiguration, KnowledgeItem)
            ] == catalogs

        # The workspace works normally after a reset.
        again, _ = send(client)
        app.state.automation_worker.run_once()
        assert linked(client, again)
        assert client.get("/api/cases").json()["total"] == 1


def test_reset_generation_survives_restart(settings):
    with TestClient(create_app(settings, start_worker=False)) as client:
        generation = client.post("/api/workspace/reset").json()["generation"]
    with TestClient(create_app(settings, start_worker=False)) as client:
        assert client.get("/api/workspace/reset").json()["generation"] == generation
