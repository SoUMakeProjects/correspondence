import copy
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import func, select
from test_phase3 import candidate_for, change_context, load, report

from app.main import create_app
from app.models import (
    IndexedPackage,
    OutboxEntry,
    ResponseDraft,
    ReviewDecision,
    SpecialistTask,
)
from app.repository import fingerprint


def endpoint(case):
    return f"/api/simulations/{case['simulation_id']}/cases/{case['id']}/tools"


def read(client, case, operation, **arguments):
    result = client.post(
        endpoint(case),
        json={
            "loan_identifier": case["loan_identifier"],
            "client_code": case["client_code"],
            "command": {"operation": operation, **arguments},
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "ok", result.text
    return result.json()["data"]


def action_request(client, case, operation, **arguments):
    current = client.get(f"/api/cases/{case['id']}").json()
    assessment = report(client, case)
    return {
        "loan_identifier": case["loan_identifier"],
        "client_code": case["client_code"],
        "command": {
            "operation": operation,
            "action_id": str(uuid4()),
            "expected_revision": current["revision"],
            "evidence_versions": assessment["evidence_versions"],
            "input_hash": assessment["input_hash"],
            **arguments,
        },
    }


def act(client, case, operation, failure_mode="none", expected="simulated_complete", **arguments):
    payload = action_request(client, case, operation, **arguments)
    payload["failure_mode"] = failure_mode
    result = client.post(endpoint(case), json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == expected, result.text
    return result.json(), payload


def prepare(client, case, response_type="final_resolution"):
    act(client, case, "cct.apply_plan")
    current = client.get(f"/api/cases/{case['id']}").json()
    candidate = candidate_for(client, current, response_type)
    candidate["case_revision"] = current["content_revision"]
    result, _ = act(client, case, "csp.prepare", candidate=candidate)
    return result["reference"]["id"]


def complete(client, case, draft_id):
    sent, payload = act(client, case, "csp.send", draft_id=draft_id)
    indexed, _ = act(client, case, "onbase.index", draft_id=draft_id)
    note, _ = act(client, case, "ils.final_note", draft_id=draft_id)
    closed, _ = act(client, case, "cct.close", draft_id=draft_id)
    return sent, indexed, note, closed, payload


def test_all_four_systems_produce_retrievable_content(client, application):
    case = load(client)
    draft_id = prepare(client, case)
    sent, indexed, note, closed, _ = complete(client, case, draft_id)
    assert closed["data"]["case"]["status"] == "closed"
    assert closed["data"]["case"]["content_revision"] < closed["data"]["case"]["revision"]
    outbox = read(client, case, "csp.status", reference_id=sent["reference"]["id"])["outbox"]
    snapshot = outbox["sent_content"]
    assert snapshot["recipient"] == "marcus.j.delgado@outlook.com"
    assert snapshot["sender"] == "correspondence@northstarresidential.com"
    assert "Enclosure: Loan Amortization Schedule" in snapshot["body"]
    assert snapshot["body"].startswith("Dear Marcus J. Delgado,")
    assert len(snapshot["attachments"]) == 1 and outbox["status"] == "sent"
    package = read(client, case, "onbase.retrieve", reference_id=indexed["reference"]["id"])
    fields = package["package"]["index_fields"]
    assert fields["sherman_id"] == "0099000002" and fields["ccid"] == case["ccid"]
    assert fields["correspondence_type"] == "INQ Email Reply"
    response = client.get(package["file_url"])
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    pdf = PdfReader(BytesIO(response.content))
    text = "\n".join(p.extract_text() for p in pdf.pages)
    assert len(pdf.pages) >= 2
    assert "0099000002" in text and "DEMO-CC-002" in text and "10/01/2026" in text
    assert note["data"]["note"]["department"] == "Servicing"
    assert note["data"]["note"]["note_type"] == "INQ Email Reply"
    assert note["data"]["note"]["details"]["standout_comment"]
    assert client.get(f"/api/cases/{case['id']}/completion-check").json()["valid"]
    for operation in [
        "cct.read",
        "cct.worklist",
        "cct.related",
        "cct.history",
        "ils.read",
        "ils.history",
        "ils.tasks",
        "onbase.search",
        "onbase.validate",
        "csp.outbox",
        "csp.drafts",
        "rules.assess",
        "knowledge.search",
        "review.read",
    ]:
        assert isinstance(read(client, case, operation), dict)
    history = read(client, case, "ils.history")
    assert history["history"][0]["operation"] == "ils.final_note"
    with application.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(OutboxEntry)) == 1


def test_send_retries_changed_payloads_and_concurrent_attempts(client, application):
    case = load(client)
    draft_id = prepare(client, case)
    payload = action_request(client, case, "csp.send", draft_id=draft_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(endpoint(case), json=payload), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json() == responses[1].json()
    changed = copy.deepcopy(payload)
    changed["command"]["draft_id"] = str(uuid4())
    assert client.post(endpoint(case), json=changed).status_code == 409
    reused, _ = act(client, case, "csp.send", draft_id=draft_id)
    assert reused["data"]["reused"]
    with application.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(OutboxEntry)) == 1


def test_lost_send_response_survives_restart_and_requires_reconciliation(
    client, application, settings
):
    case = load(client)
    draft_id = prepare(client, case)
    uncertain, payload = act(
        client,
        case,
        "csp.send",
        draft_id=draft_id,
        failure_mode="after_write_response_lost",
        expected="uncertain",
    )
    assert uncertain["reference"] is None
    assert client.post(endpoint(case), json=payload).json() == uncertain
    rejected, _ = act(client, case, "csp.send", draft_id=draft_id, expected="rejected")
    assert rejected["code"] == "reconciliation_required"
    with TestClient(create_app(settings)) as restarted:
        assert (
            read(restarted, case, "action.status", reference_id=uncertain["action_id"])["action"][
                "status"
            ]
            == "uncertain"
        )
        assert not restarted.get(f"/api/cases/{case['id']}/completion-check").json()["valid"]
        result, _ = act(restarted, case, "action.reconcile", reference_id=uncertain["action_id"])
        assert result["data"]["action"]["status"] == "simulated_complete"
        assert restarted.post(endpoint(case), json=payload).json()["status"] == "simulated_complete"
        act(restarted, case, "onbase.index", draft_id=draft_id)
        act(restarted, case, "ils.final_note", draft_id=draft_id)
        act(restarted, case, "cct.close", draft_id=draft_id)
    with application.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(OutboxEntry)) == 1


@pytest.mark.parametrize("operation", ["onbase.index", "ils.final_note"])
def test_failed_records_keep_case_incomplete_and_retry_does_not_resend(client, operation):
    case = load(client)
    draft_id = prepare(client, case)
    act(client, case, "csp.send", draft_id=draft_id)
    failed, payload = act(
        client, case, operation, draft_id=draft_id, failure_mode="before_write", expected="failed"
    )
    assert client.post(endpoint(case), json=payload).json() == failed
    assert client.get(f"/api/cases/{case['id']}").json()["status"] == "records_incomplete"
    act(client, case, "cct.close", draft_id=draft_id, expected="rejected")
    act(client, case, "onbase.index", draft_id=draft_id)
    act(client, case, "ils.final_note", draft_id=draft_id)
    act(client, case, "cct.close", draft_id=draft_id)
    assert len(read(client, case, "csp.outbox")["outbox"]) == 1


def test_review_setting_cannot_be_bypassed_by_dispatcher(client, application):
    case = load(client, "DEMO-03")
    draft_id = prepare(client, case)
    waiting, _ = act(client, case, "csp.send", draft_id=draft_id, expected="awaiting_review")
    assert waiting["code"] == "review_required"
    assert read(client, case, "csp.outbox")["outbox"] == []
    with application.state.sessions() as session, session.begin():
        draft = session.get(ResponseDraft, draft_id)
        decision = ReviewDecision(
            case_id=case["id"],
            draft_id=draft.id,
            draft_version=draft.version,
            case_revision=draft.case_revision,
            actor="test reviewer",
            decision="approve",
            note="Synthetic test review",
            content_hash=fingerprint(
                {
                    "candidate": draft.validation["candidate"],
                    "input_hash": draft.validation["input_hash"],
                }
            ),
        )
        session.add(decision)
    complete(client, case, draft_id)


@pytest.mark.parametrize("variant", ["missing_document", "wrong_loan", "unreadable_document"])
def test_document_exceptions_cannot_be_sent(client, variant):
    case = load(client, variant=variant)
    act(client, case, "cct.apply_plan")
    current = client.get(f"/api/cases/{case['id']}").json()
    result, _ = act(
        client, case, "csp.prepare", candidate=candidate_for(client, current), expected="rejected"
    )
    assert result["code"] == "response_invalid"
    assert read(client, case, "csp.outbox")["outbox"] == []


def test_scope_registry_and_foreign_references(client):
    first, second = load(client), load(client, "DEMO-03")
    registry = client.get("/api/simulator/tools").json()
    assert registry and all(t["simulated"] for t in registry)
    assert {t["system"] for t in registry} == {
        "cct",
        "ils",
        "onbase",
        "csp",
        "rules",
        "knowledge",
        "review",
        "action",
    }
    assert not any(
        word in t["name"] for t in registry for word in ["live", "smtp", "production", "azure"]
    )
    payload = {
        "loan_identifier": first["loan_identifier"],
        "client_code": first["client_code"],
        "command": {"operation": "cct.read"},
    }
    assert client.post(endpoint(second), json=payload).status_code == 404
    bad_path = endpoint(first).replace(first["simulation_id"], second["simulation_id"])
    assert client.post(bad_path, json=payload).status_code == 404
    foreign = client.get(f"/api/cases/{second['id']}/evidence").json()[0]["id"]
    payload["command"] = {"operation": "onbase.retrieve", "reference_id": foreign}
    assert client.post(endpoint(first), json=payload).status_code == 404
    payload["command"] = {"operation": "smtp.send"}
    assert client.post(endpoint(first), json=payload).status_code == 422


def test_interim_delivery_retains_pending_work(client):
    case = load(client, "DEMO-01")
    draft_id = prepare(client, case, "information_request")
    act(client, case, "csp.send", draft_id=draft_id)
    act(client, case, "onbase.index", draft_id=draft_id)
    act(client, case, "ils.final_note", draft_id=draft_id)
    result, _ = act(client, case, "cct.close", draft_id=draft_id, expected="rejected")
    assert result["code"] == "completion_blocked"
    current = client.get(f"/api/cases/{case['id']}").json()
    assert current["status"] == "waiting_for_borrower"
    assert all(
        p["owner"] and p["next_review_at"] and p["resume_requirement"]
        for p in current["pending_work"]
    )


def test_name_update_task_is_authorized_idempotent_and_has_history(client, application):
    case = load(client, "DEMO-01", "followup")
    # Retain the supplied legal document but remove the future result to exercise actual execution.
    with application.state.sessions() as session, session.begin():
        task = session.scalar(select(SpecialistTask).where(SpecialistTask.case_id == case["id"]))
        session.delete(task)
    change_context(
        application,
        case,
        {"current_legal_name": "Lauren E. Whitaker", "profile_update_result": None},
    )
    task, payload = act(
        client,
        case,
        "ils.create_task",
        task_type="demo_profile_name_update",
        failure_mode="after_write_response_lost",
        expected="uncertain",
    )
    assert client.post(endpoint(case), json=payload).json() == task
    act(client, case, "action.reconcile", reference_id=task["action_id"])
    reused, _ = act(client, case, "ils.create_task", task_type="demo_profile_name_update")
    assert reused["data"]["reused"]
    task_id = reused["reference"]["id"]
    act(client, case, "ils.update_name", task_id=task_id)
    loan = read(client, case, "ils.read")["loan"]
    assert loan["context"]["current_legal_name"] == "Lauren E. Castellano"
    assert read(client, case, "ils.task", reference_id=task_id)["task"]["status"] == "completed"
    assert len(read(client, case, "ils.tasks")["tasks"]) == 1
    assert {h["operation"] for h in read(client, case, "ils.history")["history"]} == {
        "ils.create_task",
        "ils.update_name",
    }
    assert report(client, case)["tasks"][0]["result_supported"]


def test_missing_prerequisites_and_task_absence_are_not_write_authority(client):
    case = load(client, "DEMO-01")
    result, _ = act(
        client, case, "ils.create_task", task_type="demo_profile_name_update", expected="rejected"
    )
    assert result["code"] == "update_not_authorized"
    tax = load(client, "DEMO-03")
    task, _ = act(client, tax, "ils.create_task", task_type="demo_tax_schedule_review")
    assert task["data"]["reused"]
    result, _ = act(
        client,
        case,
        "ils.create_task",
        task_type="demo_bankruptcy_status_review",
        expected="rejected",
    )
    assert result["code"] == "distinct_action_not_authorized"


def test_stale_inputs_and_tampered_archives_block_actions(client, application, settings):
    case = load(client)
    payload = action_request(client, case, "cct.apply_plan")
    payload["command"]["evidence_versions"] = {}
    response = client.post(endpoint(case), json=payload).json()
    assert response["code"] == "stale_evidence" and response["status"] == "rejected"
    draft_id = prepare(client, case)
    act(client, case, "csp.send", draft_id=draft_id)
    indexed, _ = act(client, case, "onbase.index", draft_id=draft_id)
    act(client, case, "ils.final_note", draft_id=draft_id)
    with application.state.sessions() as session:
        package = session.get(IndexedPackage, indexed["reference"]["id"])
        (settings.data_dir / "documents" / package.index_fields["pdf_storage_key"]).write_bytes(
            b"tampered"
        )
    act(client, case, "cct.close", draft_id=draft_id, expected="rejected")
    package = read(client, case, "onbase.retrieve", reference_id=indexed["reference"]["id"])
    assert client.get(package["file_url"]).status_code == 409


def test_partial_file_failure_rolls_back_database_and_new_artifacts(
    client, application, settings, monkeypatch
):
    from app.simulators.common import Context

    case = load(client)
    draft_id = prepare(client, case)
    act(client, case, "csp.send", draft_id=draft_id)
    before = set((settings.data_dir / "documents").iterdir())
    original = Context.write_file

    def fail_manifest(ctx, filename, content):
        if filename.endswith(".json"):
            raise OSError("Injected storage failure after creating the PDF")
        return original(ctx, filename, content)

    with monkeypatch.context() as patch:
        patch.setattr(Context, "write_file", fail_manifest)
        act(client, case, "onbase.index", draft_id=draft_id, expected="failed")
    assert set((settings.data_dir / "documents").iterdir()) == before
    with application.state.sessions() as session:
        assert session.scalar(select(func.count()).select_from(IndexedPackage)) == 0
    act(client, case, "onbase.index", draft_id=draft_id)


def test_uncertain_index_requires_verification_of_retained_pdf(client, application, settings):
    case = load(client)
    draft_id = prepare(client, case)
    act(client, case, "csp.send", draft_id=draft_id)
    result, payload = act(
        client,
        case,
        "onbase.index",
        draft_id=draft_id,
        failure_mode="after_write_response_lost",
        expected="uncertain",
    )
    with application.state.sessions() as session:
        package = session.scalar(select(IndexedPackage).where(IndexedPackage.case_id == case["id"]))
        path = settings.data_dir / "documents" / package.index_fields["pdf_storage_key"]
        original = path.read_bytes()
    path.write_bytes(b"damaged")
    act(client, case, "action.reconcile", reference_id=result["action_id"], expected="rejected")
    assert (
        read(client, case, "action.status", reference_id=result["action_id"])["action"]["status"]
        == "uncertain"
    )
    path.write_bytes(original)
    act(client, case, "action.reconcile", reference_id=result["action_id"])
    assert client.post(endpoint(case), json=payload).json()["status"] == "simulated_complete"
    assert len(read(client, case, "onbase.search")["packages"]) == 1


def test_azure_status_is_bound_to_current_configuration_and_never_calls_model(client, settings):
    import json

    from app.azure_probe import configuration_fingerprint, last_check

    record = {
        "status": "passed",
        "checked_at": "2026-09-22T10:00:00Z",
        "configuration_fingerprint": configuration_fingerprint(settings),
    }
    (settings.data_dir / "azure-live-check.json").write_text(json.dumps(record))
    assert last_check(settings)["status"] == "passed"
    changed = settings.model_copy(update={"azure_openai_deployment": "another-deployment"})
    assert last_check(changed) is None
    assert client.get("/api/config").json()["model_calls_enabled"] is False
