"""Uploaded bytes survive sending and restart, and reach intake without gaining authority."""

from io import BytesIO
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import MetaData
from test_custom_mail import IntakeModel, custom
from test_mailbox import linked

from app.db import make_engine
from app.main import create_app
from app.migrations import migration_config
from app.models import MailAttachment


def pdf(text="Please email the amortization schedule for loan 0099000002."):
    output = BytesIO()
    canvas = Canvas(output, invariant=1)
    canvas.drawString(48, 700, text)
    canvas.showPage()
    canvas.save()
    return output.getvalue()


def upload(client, content=None, filename="Request.pdf", identity=None):
    return client.post(
        "/api/mail/attachments",
        params={"filename": filename, "request_id": identity or str(uuid4())},
        headers={"Content-Type": "application/pdf"},
        content=pdf() if content is None else content,
    )


def test_uploaded_pdf_survives_send_and_restart_and_checks_integrity(settings):
    app = create_app(settings, start_worker=False)
    raw, identity = pdf(), str(uuid4())
    with TestClient(app) as client:
        result = upload(client, raw, identity=identity)
        assert result.status_code == 201, result.text
        assert result.json()["page_count"] == 1
        assert result.json()["size_bytes"] == len(raw)
        assert upload(client, raw, identity=identity).json() == result.json()
        assert upload(client, pdf("Different request"), identity=identity).status_code == 409
        message, payload = custom(client, attachment_ids=[identity])
        assert client.post("/api/mail/messages", json=payload).json() == message
        url = f"/api/mail/messages/{message['id']}/attachments/0"
        preview = client.get(url)
        assert preview.headers["content-type"] == "application/pdf"
        assert preview.content == raw
        reused = client.post("/api/mail/messages", json={**payload, "request_id": str(uuid4())})
        assert reused.status_code == 409
    restarted = create_app(settings, start_worker=False)
    with TestClient(restarted) as client:
        assert client.get(url).content == raw
        with restarted.state.sessions() as session:
            row = session.get(MailAttachment, identity)
            (settings.data_dir / "documents" / row.storage_key).write_bytes(pdf("Altered"))
        assert client.get(url).status_code == 409
        assert client.get(f"/api/mail/attachments/{identity}/file").status_code == 409


@pytest.mark.parametrize(
    "filename", ["request.txt", "request.png", "../request.pdf", "C:\\request.pdf"]
)
def test_only_pdf_filenames_are_accepted(client, filename):
    assert upload(client, filename=filename).status_code == 422


def test_invalid_encrypted_large_and_excessive_page_files_are_rejected(client):
    assert upload(client, b"not a PDF").status_code == 422
    assert upload(client, b"%PDF-1.7\ntruncated").status_code == 422
    assert upload(client, b"%PDF-" + b"a" * (5 * 1024 * 1024)).status_code == 413
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("password")
    output = BytesIO()
    writer.write(output)
    assert upload(client, output.getvalue()).json()["error"]["code"] == "pdf_encrypted"
    writer = PdfWriter()
    for _ in range(51):
        writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    assert upload(client, output.getvalue()).json()["error"]["code"] == "pdf_page_limit"
    assert (
        client.post(
            "/api/mail/attachments",
            params={"filename": "Request.pdf", "request_id": str(uuid4())},
            headers={"Content-Type": "text/plain"},
            content=pdf(),
        ).status_code
        == 422
    )


def test_attachment_selection_is_atomic_and_bounded(client):
    identity = upload(client).json()["id"]
    base = {"template_key": "DEMO-02", "request_id": str(uuid4())}
    for ids, status in [
        ([identity, identity], 422),
        ([identity, str(uuid4())], 404),
        ([identity] * 6, 422),
    ]:
        assert (
            client.post("/api/mail/messages", json={**base, "attachment_ids": ids}).status_code
            == status
        )
    # Failed sends did not consume the valid upload or commit a partial message.
    assert (
        client.post("/api/mail/messages", json={**base, "attachment_ids": [identity]}).status_code
        == 202
    )


def test_custom_classifier_reads_pdf_and_imports_unverified_evidence(settings):
    class PdfModel(IntakeModel):
        def classify(self, message, timeout):
            assert message["body"] == "Please see my attached request."
            assert "loan 0099000002" in message["attachments"][0]["text"]
            self.changes["concern_quotes"] = [message["attachments"][0]["text"].strip()]
            return super().classify(message, timeout)

    model = PdfModel()
    app = create_app(settings, agent_model=model, start_worker=False)
    with TestClient(app) as client:
        identity = upload(client).json()["id"]
        message, _ = custom(
            client, body="Please see my attached request.", attachment_ids=[identity]
        )
        app.state.automation_worker.run_once()
        case_id = linked(client, message)
        state = client.get(f"/api/systems/cases/{case_id}").json()
        evidence = [e for e in state["evidence"] if e["details"].get("origin") == "mail_upload"]
        assert len(evidence) == 1 and evidence[0]["details"]["facts"] == {}
        assert "amortization schedule" in evidence[0]["details"]["extracted_text"]
        thread = client.get(f"/api/mail/threads/{message['thread_id']}").json()
        assert thread["messages"][0]["attachments"][0]["evidence_id"] == evidence[0]["id"]
        app.state.automation_worker.run_once()
        assert app.state.agent_worker.run_once()
        assert client.get(f"/api/cases/{case_id}").json()["status"] == "closed"
        assert model.calls == 1


def test_conflicting_loan_inside_pdf_requires_identity_review(settings):
    app = create_app(settings, agent_model=IntakeModel(), start_worker=False)
    with TestClient(app) as client:
        identity = upload(client, pdf("Loan 0099000001 belongs to another borrower.")).json()["id"]
        message, _ = custom(client, attachment_ids=[identity])
        app.state.automation_worker.run_once()
        assert linked(client, message) is None
        reviews = client.get("/api/mail/intake-reviews").json()["reviews"]
        assert len(reviews) == 1 and "conflicting" in reviews[0]["detail"]


def test_templates_and_replies_import_uploads_once_and_keep_prepared_attachments(
    client, application
):
    first_id = upload(client, pdf("My additional name-change correspondence.")).json()["id"]
    first = client.post(
        "/api/mail/messages",
        json={"request_id": str(uuid4()), "template_key": "DEMO-01", "attachment_ids": [first_id]},
    ).json()
    assert first["attachments"][-1]["upload_id"] == first_id
    assert len(first["attachments"]) > 1
    application.state.automation_worker.run_once()
    case_id = linked(client, first)
    second_id = upload(client, pdf("More information for this case.")).json()["id"]
    result = client.post(
        "/api/mail/messages",
        json={
            "request_id": str(uuid4()),
            "template_key": "name-proof",
            "thread_id": first["thread_id"],
            "attachment_ids": [second_id],
        },
    )
    assert result.status_code == 202, result.text
    application.state.automation_worker.run_once()
    application.state.automation_worker.run_once()
    state = client.get(f"/api/systems/cases/{case_id}").json()
    assert len([e for e in state["evidence"] if e["details"].get("origin") == "mail_upload"]) == 2
    assert len(client.get(f"/api/mail/threads/{first['thread_id']}").json()["messages"]) == 2


def test_pdf_without_text_can_be_uploaded_and_opened_as_case_evidence(client, application):
    # A valid page with no extractable text follows the same path as scanned PDFs.
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    identity = upload(client, output.getvalue()).json()["id"]
    response = client.post(
        "/api/mail/messages",
        json={"request_id": str(uuid4()), "template_key": "DEMO-02", "attachment_ids": [identity]},
    )
    application.state.automation_worker.run_once()
    thread = client.get(f"/api/mail/threads/{response.json()['thread_id']}").json()
    evidence_id = thread["messages"][0]["attachments"][-1]["evidence_id"]
    case_id = thread["thread"]["case_id"]
    preview = client.get(f"/api/cases/{case_id}/evidence/{evidence_id}/file")
    assert preview.status_code == 200, preview.text
    assert preview.content == output.getvalue()


def test_0006_upgrade_preserves_existing_mail(settings):
    engine = make_engine(settings.database_url)
    config = migration_config()
    identity = str(uuid4())
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0006")
        metadata = MetaData()
        metadata.reflect(bind=connection)
        timestamp = "2026-09-23T14:00:00.000000+00:00"
        connection.execute(
            metadata.tables["mail_threads"]
            .insert()
            .values(
                id=identity, template_key="DEMO-02", subject="Retained mail", created_at=timestamp
            )
        )
        connection.execute(
            metadata.tables["mail_messages"]
            .insert()
            .values(
                id=identity,
                thread_id=identity,
                template_key="DEMO-02",
                sender="marcus.j.delgado@outlook.com",
                recipient="correspondence@servicing.example.com",
                subject="Retained mail",
                body="Retain my request",
                attachments=[],
                request_hash="0" * 64,
                status="processed",
                created_at=timestamp,
            )
        )
    engine.dispose()
    with TestClient(create_app(settings, start_worker=False)) as client:
        assert client.get("/api/health").json()["schema_revision"] == "0009"
        assert (
            client.get(f"/api/mail/threads/{identity}").json()["messages"][0]["body"]
            == "Retain my request"
        )
        assert upload(client).status_code == 201
