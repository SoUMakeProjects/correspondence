"""Editable prepared mail and image attachments reach the real intake/evidence paths."""

from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_custom_mail import IntakeModel, custom
from test_mailbox import linked, send

from app.main import create_app


def picture(format="PNG"):
    output = BytesIO()
    Image.new("RGB", (240, 120), "#3377aa").save(output, format=format)
    return output.getvalue()


@pytest.mark.parametrize(
    "extension,format,mime",
    [
        ("png", "PNG", "image/png"),
        ("jpg", "JPEG", "image/jpeg"),
        ("gif", "GIF", "image/gif"),
        ("webp", "WEBP", "image/webp"),
    ],
)
def test_images_survive_send_restart_and_case_preview(settings, extension, format, mime):
    app = create_app(settings, agent_model=IntakeModel(), start_worker=False)
    raw, identity = picture(format), str(uuid4())
    with TestClient(app) as client:
        response = client.post(
            "/api/mail/attachments",
            params={"request_id": identity, "filename": f"Supporting image.{extension}"},
            headers={"Content-Type": mime},
            content=raw,
        )
        assert response.status_code == 201, response.text
        assert response.json()["media_type"] == mime
        assert response.json()["page_count"] == 0
        message, _ = custom(client, attachment_ids=[identity])
        app.state.automation_worker.run_once()
        case_id = linked(client, message)
        state = client.get(f"/api/systems/cases/{case_id}").json()
        evidence = next(e for e in state["evidence"] if e["details"].get("origin") == "mail_upload")
        assert evidence["details"]["facts"] == {}
        assert evidence["details"]["extracted_text"] == ""
        urls = [
            f"/api/mail/attachments/{identity}/file",
            f"/api/mail/messages/{message['id']}/attachments/0",
            f"/api/cases/{case_id}/evidence/{evidence['id']}/file",
        ]
        for url in urls:
            preview = client.get(url)
            assert preview.status_code == 200, preview.text
            assert preview.headers["content-type"] == mime
            assert preview.content == raw
    with TestClient(create_app(settings, start_worker=False)) as client:
        assert client.get(urls[1]).content == raw


@pytest.mark.parametrize(
    "filename,mime,content",
    [
        ("bad.png", "image/png", b"bad image"),
        ("renamed.png", "image/png", picture("JPEG")),
        ("script.svg", "image/svg+xml", b"<svg/>"),
        ("request.html", "text/html", b"<html/>"),
        ("large.png", "image/png", picture() + b"x" * (5 * 1024 * 1024)),
    ],
    ids=["damaged", "renamed", "svg", "html", "oversized"],
)
def test_images_are_validated_from_bytes(client, filename, mime, content):
    result = client.post(
        "/api/mail/attachments",
        params={"request_id": str(uuid4()), "filename": filename},
        headers={"Content-Type": mime},
        content=content,
    )
    assert result.status_code in {413, 422}


def test_edited_prepared_draft_uses_actual_fields_and_selected_files(settings):
    model = IntakeModel("name_change", requested_name="Lauren E. Castellano")
    app = create_app(settings, agent_model=model, start_worker=False)
    with TestClient(app) as client:
        template = next(
            t for t in client.get("/api/mail/templates").json() if t["key"] == "DEMO-01"
        )
        payload = {
            "request_id": str(uuid4()),
            "template_key": "DEMO-01",
            "sender": template["sender"],
            "subject": "Please update my name",
            "body": "Please change my name to Lauren E. Castellano. I will supply the proof later.",
            "excluded_attachment_keys": [a["key"] for a in template["attachments"]],
        }
        response = client.post("/api/mail/messages", json=payload)
        assert response.status_code == 202, response.text
        message = response.json()
        assert message["attachments"] == []
        assert client.post("/api/mail/messages", json=payload).json() == message
        app.state.automation_worker.run_once()
        case_id = linked(client, message)
        state = client.get(f"/api/systems/cases/{case_id}").json()
        assert state["case"]["subject"] == payload["subject"]
        assert state["case"]["correspondence_text"] == payload["body"]
        assert model.calls == 1
        assert not any(
            e["details"].get("key") in payload["excluded_attachment_keys"]
            for e in state["evidence"]
        )
        assert (
            client.get(f"/api/mail/threads/{message['thread_id']}").json()["reply_templates"] == []
        )


def test_selected_prepared_files_are_classified_and_retained_when_edited(settings):
    class SelectedModel(IntakeModel):
        def classify(self, message, timeout):
            assert message["attachments"]
            assert all(a["text"] for a in message["attachments"])
            return super().classify(message, timeout)

    app = create_app(settings, agent_model=SelectedModel("name_change"), start_worker=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/mail/messages",
            json={
                "request_id": str(uuid4()),
                "template_key": "DEMO-01",
                "subject": "Please review the attached name request",
            },
        )
        message = response.json()
        app.state.automation_worker.run_once()
        case_id = linked(client, message)
        state = client.get(f"/api/systems/cases/{case_id}").json()
        evidence = [e for e in state["evidence"] if e["details"].get("origin") == "mail_upload"]
        assert len(evidence) == len(message["attachments"])
        assert all(e["details"]["facts"] == {} for e in evidence)


def test_changed_sender_requires_review_and_can_be_resolved(settings):
    app = create_app(settings, agent_model=IntakeModel(), start_worker=False)
    with TestClient(app) as client:
        message = client.post(
            "/api/mail/messages",
            json={
                "request_id": str(uuid4()),
                "template_key": "DEMO-02",
                "sender": "new.sender@example.com",
                "body": "Please send the schedule for loan 0099000002.",
            },
        ).json()
        app.state.automation_worker.run_once()
        assert linked(client, message) is None
        reviews = client.get("/api/mail/intake-reviews").json()["reviews"]
        assert reviews[0]["message"]["sender"] == "new.sender@example.com"
        response = client.post(
            f"/api/mail/intake/{reviews[0]['signal_id']}/resolve",
            json={
                "request_id": str(uuid4()),
                "loan_identifier": "0099000002",
                "request_type": "amortization",
                "actor": "Reviewer",
                "note": "Verified authority for this borrower.",
                "identity_verified": True,
            },
        )
        assert response.status_code == 200, response.text
        app.state.automation_worker.run_once()
        assert linked(client, message)


def test_removed_reply_proof_is_not_silently_reintroduced(client, application):
    initial, _ = send(client, "DEMO-01")
    application.state.automation_worker.run_once()
    case_id = linked(client, initial)
    response = client.post(
        "/api/mail/messages",
        json={
            "request_id": str(uuid4()),
            "template_key": "name-proof",
            "thread_id": initial["thread_id"],
            "excluded_attachment_keys": ["legal-document"],
        },
    )
    assert response.status_code == 202, response.text
    application.state.automation_worker.run_once()
    state = client.get(f"/api/systems/cases/{case_id}").json()
    assert not any(
        e["details"].get("key") == "legal-document" and e["storage_key"] for e in state["evidence"]
    )
    assert any(e["details"].get("origin") == "mail_reply" for e in state["evidence"])


@pytest.mark.parametrize(
    "changes",
    [
        {"sender": "invalid"},
        {"subject": ""},
        {"body": " "},
        {"excluded_attachment_keys": ["unknown"]},
        {"recipient": "different@example.com"},
    ],
)
def test_prepared_fields_are_validated_and_recipient_is_fixed(client, changes):
    response = client.post(
        "/api/mail/messages",
        json={"request_id": str(uuid4()), "template_key": "DEMO-01", **changes},
    )
    assert response.status_code == 422


def test_edited_eft_reply_uses_actual_body_instead_of_original_option(settings):
    model = IntakeModel("eft", eft_intent="incoming_payment")
    # Keep runs queued while examining intake. No provider is invoked by this model.
    app = create_app(settings, agent_model=model, start_worker=False)
    with TestClient(app) as client:
        initial, _ = send(client, "DEMO-05")
        app.state.automation_worker.run_once()
        case_id = linked(client, initial)
        # Finish the queued initial run so the reply can be received.
        app.state.agent_worker.run_once()
        body = "My EFT request is an incoming payment for loan 0099000005, not a refund."
        message = client.post(
            "/api/mail/messages",
            json={
                "request_id": str(uuid4()),
                "template_key": "eft-outgoing_refund",
                "thread_id": initial["thread_id"],
                "body": body,
                "subject": "Re: Payment clarification",
            },
        )
        assert message.status_code == 202, message.text
        app.state.automation_worker.run_once()
        state = client.get(f"/api/systems/cases/{case_id}").json()
        assert state["loan"]["context"]["eft_intent"] == "incoming_payment"
        reply = next(e for e in state["evidence"] if e["details"].get("origin") == "mail_reply")
        assert reply["details"]["extracted_text"] == body
        assert reply["details"]["facts"] == {}
        assert model.calls == 1


def test_migration_preserves_preexisting_pdf_upload(settings):
    import hashlib

    from alembic import command
    from sqlalchemy import MetaData
    from test_mail_attachments import pdf

    from app.db import make_engine
    from app.migrations import migration_config

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "documents").mkdir(exist_ok=True)
    content, identity = pdf(), str(uuid4())
    (settings.data_dir / "documents" / "retained.pdf").write_bytes(content)
    engine = make_engine(settings.database_url)
    config = migration_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0007")
        tables = MetaData()
        tables.reflect(bind=connection)
        connection.execute(
            tables.tables["mail_attachments"]
            .insert()
            .values(
                id=identity,
                created_at="2026-09-23T14:00:00.000000+00:00",
                filename="retained.pdf",
                storage_key="retained.pdf",
                content_sha256=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
                page_count=1,
                extracted_text="Retained request",
            )
        )
    engine.dispose()
    with TestClient(create_app(settings, start_worker=False)) as client:
        assert client.get("/api/health").json()["schema_revision"] == "0008"
        response = client.get(f"/api/mail/attachments/{identity}/file")
        assert response.headers["content-type"] == "application/pdf"
        assert response.content == content
