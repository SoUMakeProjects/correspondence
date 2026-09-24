"""Workflow acceptance against persisted services, without Azure calls."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from test_phase3 import candidate_for, change_context, load
from test_phase4 import act, complete, prepare, read

from app.models import AgentRun, SpecialistTask


def current(client, case):
    return client.get(f"/api/cases/{case['id']}").json()


def workflow(client, case):
    return client.get(f"/api/cases/{case['id']}/workflow").json()


def supply(client, case, kind, **values):
    payload = {
        "request_id": str(uuid4()),
        "expected_revision": current(client, case)["revision"],
        "kind": kind,
        **values,
    }
    result = client.post(f"/api/cases/{case['id']}/inputs", json=payload)
    assert result.status_code == 200, result.text
    return result.json(), payload


def approve(client, case, draft_id, decision="approve"):
    draft = next(d for d in workflow(client, case)["drafts"] if d["id"] == draft_id)
    payload = {
        "request_id": str(uuid4()),
        "expected_case_revision": current(client, case)["revision"],
        "draft_id": draft_id,
        "draft_version": draft["version"],
        "decision": decision,
        "actor": "Demo reviewing presenter",
        "note": "Checked evidence and scheduled-payment wording.",
    }
    result = client.post(f"/api/cases/{case['id']}/reviews", json=payload)
    assert result.status_code == 201, result.text
    return result.json(), payload


def new_response(client, case, response_type="final_resolution"):
    act(client, case, "cct.apply_plan")
    item = current(client, case)
    candidate = candidate_for(client, item, response_type)
    candidate["version"] = len(workflow(client, case)["drafts"]) + 1
    candidate["case_revision"] = item["content_revision"]
    if item["family"] == "profile_change" and response_type == "final_resolution":
        record = next(
            e
            for e in client.get(f"/api/cases/{case['id']}/evidence").json()
            if e["details"]["kind"] == "record"
        )
        task = read(client, case, "ils.tasks")["tasks"][0]
        candidate["claims"] = [
            {
                "field": "current_legal_name",
                "value": record["details"]["facts"]["current_legal_name"],
                "evidence_id": record["id"],
            },
            {
                "field": "task_completed",
                "value": task["result"]["reference"],
                "evidence_id": task["id"],
            },
        ]
    result, _ = act(client, case, "csp.prepare", candidate=candidate)
    return result["reference"]["id"]


def test_name_input_resumes_same_case_and_preserves_sent_interim(client, application):
    case = load(client, "DEMO-01")
    initial = prepare(client, case, "information_request")
    for operation in ("csp.send", "onbase.index", "ils.final_note"):
        act(client, case, operation, draft_id=initial)
    old_artifacts = client.get(f"/api/cases/{case['id']}/artifacts").json()
    updated, payload = supply(client, case, "name_legal_document")
    assert updated["id"] == case["id"]
    assert updated["original_received_at"] == case["original_received_at"]
    assert client.post(f"/api/cases/{case['id']}/inputs", json=payload).json() == updated
    assert not workflow(client, case)["drafts"][0]["current"]
    task, _ = act(client, case, "ils.create_task", task_type="demo_profile_name_update")
    same, _ = act(client, case, "ils.create_task", task_type="demo_profile_name_update")
    assert task["reference"] == same["reference"]
    act(client, case, "ils.update_name", task_id=task["reference"]["id"])
    final = new_response(client, case)
    for operation in ("csp.send", "onbase.index", "ils.final_note"):
        act(client, case, operation, draft_id=final)
    act(client, case, "cct.close", expected="rejected", draft_id=final)
    act(client, case, "cct.handoff")
    artifacts = client.get(f"/api/cases/{case['id']}/artifacts").json()
    assert artifacts["outbox"][0] == old_artifacts["outbox"][0]
    assert len(artifacts["outbox"]) == len(artifacts["drafts"]) == 2
    assert "Lauren E. Castellano" in artifacts["drafts"][-1]["body"]
    assert current(client, case)["status"] == "waiting_on_department"
    assert any(
        f["code"] == "classification_mapping_missing"
        for f in client.get(f"/api/cases/{case['id']}/assessment").json()["findings"]
    )
    with application.state.sessions() as session:
        assert (
            len(
                session.scalars(
                    select(SpecialistTask).where(SpecialistTask.case_id == case["id"])
                ).all()
            )
            == 1
        )


def test_review_return_edit_approve_binds_exact_version(client):
    case = load(client, "DEMO-03")
    draft_id = prepare(client, case)
    act(client, case, "csp.send", expected="awaiting_review", draft_id=draft_id)
    approve(client, case, draft_id, "return")
    draft = workflow(client, case)["drafts"][-1]
    assert draft["returned"] and not draft["approved"]
    candidate = draft["candidate"]
    edit = {
        key: candidate[key] for key in ("response_type", "concerns", "claims", "attachment_ids")
    }
    edit.update(
        request_id=str(uuid4()),
        expected_revision=current(client, case)["revision"],
        draft_id=draft_id,
        draft_version=1,
    )
    response = client.post(f"/api/cases/{case['id']}/draft-edits", json=edit)
    assert response.status_code == 200, response.text
    newer = response.json()["resource"]["id"]
    assert client.post(f"/api/cases/{case['id']}/draft-edits", json=edit).json() == response.json()
    assert len(workflow(client, case)["drafts"]) == 2
    act(client, case, "csp.send", expected="rejected", draft_id=draft_id)
    act(client, case, "csp.send", expected="awaiting_review", draft_id=newer)
    review, payload = approve(client, case, newer)
    assert client.post(f"/api/cases/{case['id']}/reviews", json=payload).json() == review
    assert workflow(client, case)["drafts"][-1]["approved"]
    complete(client, case, newer)
    body = workflow(client, case)["drafts"][-1]["body"]
    assert "Payment status: Scheduled (not yet paid)" in body and "has not been paid yet" in body
    assert "Payment status: Paid" not in body and "has been paid" not in body


def test_new_specialist_input_invalidates_approval_without_duplicate_task(client):
    case = load(client, "DEMO-03")
    draft_id = prepare(client, case)
    approve(client, case, draft_id)
    previous_tasks = read(client, case, "ils.tasks")["tasks"]
    supply(client, case, "tax_specialist_result")
    tasks = read(client, case, "ils.tasks")["tasks"]
    assert len(tasks) == 1 and tasks[0]["id"] == previous_tasks[0]["id"]
    assert tasks[0]["result"]["confirmed_status"] == "scheduled"
    assert not workflow(client, case)["drafts"][-1]["approved"]
    act(client, case, "csp.send", expected="rejected", draft_id=draft_id)
    latest = new_response(client, case)
    approve(client, case, latest)
    complete(client, case, latest)


def test_handoff_requires_current_acknowledgment_and_never_closes(client):
    case = load(client, "DEMO-04")
    act(client, case, "cct.apply_plan")
    requested, _ = act(client, case, "cct.handoff")
    handoff_id = requested["reference"]["id"]
    assert current(client, case)["status"] == "waiting_on_department"
    acknowledgment = {
        "request_id": str(uuid4()),
        "expected_revision": current(client, case)["revision"],
        "handoff_id": handoff_id,
        "actor": "Demo Compliance recipient",
    }
    response = client.post(f"/api/cases/{case['id']}/handoff-acknowledgments", json=acknowledgment)
    assert response.status_code == 200, response.text
    assert current(client, case)["status"] == "transferred"
    assert response.json()["acknowledged_by"] == "Demo Compliance recipient"
    supply(client, case, "bankruptcy_specialist_result")
    stale = {
        **acknowledgment,
        "request_id": str(uuid4()),
        "expected_revision": current(client, case)["revision"],
    }
    assert (
        client.post(f"/api/cases/{case['id']}/handoff-acknowledgments", json=stale).status_code
        == 409
    )
    assessment = client.get(f"/api/cases/{case['id']}/assessment").json()
    assert any(f["code"] == "classification_mapping_missing" for f in assessment["findings"])
    assert assessment["authorized_recipient"] == "monica.ferrante@ferrantehale.example.com"
    assert assessment["concerns"][0]["disposition"] == "referred"
    assert not client.get(f"/api/cases/{case['id']}/completion-check").json()["valid"]


@pytest.mark.parametrize("intent", ["incoming_payment", "outgoing_refund", "heloc_draw"])
def test_eft_clarification_selects_specific_pending_requirement(client, intent):
    case = load(client, "DEMO-05")
    supply(client, case, "eft_clarification", eft_intent=intent)
    assessment = client.get(f"/api/cases/{case['id']}/assessment").json()
    assert intent.replace("_", " ") in assessment["concerns"][0]["resume_requirement"]
    assert all(c["disposition"] == "pending_borrower" for c in assessment["concerns"])
    assert not client.get(f"/api/cases/{case['id']}/artifacts").json()["outbox"]


def test_authority_variant_and_representative_destination(client):
    case = load(client)
    supply(client, case, "authority_missing")
    report = client.get(f"/api/cases/{case['id']}/assessment").json()
    assert any(f["code"] == "requester_authority_missing" for f in report["findings"])
    supply(client, case, "authorized_representative")
    draft = new_response(client, case)
    complete(client, case, draft)
    saved = client.get(f"/api/cases/{case['id']}/artifacts").json()
    assert (
        saved["outbox"][0]["sent_content"]["recipient"]
        == "elena.ruiz@brightpathhousing.example.org"
    )


def test_representative_input_cannot_reverse_cease_and_desist(client, application):
    case = load(client)
    change_context(application, case, {"communication_restriction": "cease_and_desist"})
    result = client.post(
        f"/api/cases/{case['id']}/inputs",
        json={
            "request_id": str(uuid4()),
            "expected_revision": current(client, case)["revision"],
            "kind": "authorized_representative",
        },
    )
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "cease_and_desist"


def test_additional_concern_and_unrelated_contact_do_not_resolve_prior_work(client):
    case = load(client)
    supply(client, case, "additional_concern", text="Investigate a separate statement discrepancy.")
    supply(client, case, "unrelated_contact", text="Thank you for explaining office hours.")
    assessment = client.get(f"/api/cases/{case['id']}/assessment").json()
    assert len(assessment["concerns"]) == 2
    assert {c["disposition"] for c in assessment["concerns"]} == {"resolved", "pending_department"}
    assert not client.get(f"/api/cases/{case['id']}/completion-check").json()["valid"]
    assert len(workflow(client, case)["contacts"]) == 2


def test_assignment_variant_preserves_original_clock(client):
    case = load(client)
    supply(client, case, "assignment_exception")
    assessment = client.get(f"/api/cases/{case['id']}/assessment").json()
    assert assessment["disposition"] == "review_exception"
    assert any(f["code"] == "assignment_conflict" for f in assessment["findings"])
    supply(client, case, "resolve_assignment")
    assessment = client.get(f"/api/cases/{case['id']}/assessment").json()
    assert not any(f["code"] == "assignment_conflict" for f in assessment["findings"])
    assert current(client, case)["original_received_at"] == case["original_received_at"]


def test_inputs_blocked_during_active_run_and_wrong_family(client, application):
    case = load(client)
    payload = {"request_id": str(uuid4()), "expected_revision": 1, "kind": "name_legal_document"}
    assert client.post(f"/api/cases/{case['id']}/inputs", json=payload).status_code == 422
    with application.state.sessions() as session, session.begin():
        session.add(AgentRun(case_id=case["id"], case_revision=1, status="queued"))
    payload["kind"] = "amortization_document"
    assert client.post(f"/api/cases/{case['id']}/inputs", json=payload).status_code == 409


def test_review_mode_stays_on_draft_when_sent_manually(settings):
    from fastapi.testclient import TestClient
    from test_phase6 import TestModel, start_run

    from app.main import create_app

    app = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(app) as client:
        case = load(client)
        start_run(client, case, mode="review_required")
        app.state.agent_worker.run_once()
        draft = workflow(client, case)["drafts"][-1]
        assert draft["review_required"]
        act(client, case, "csp.send", expected="awaiting_review", draft_id=draft["id"])
        approve(client, case, draft["id"])
        complete(client, case, draft["id"])


def test_invalid_reviewer_fact_is_rejected_atomically(client):
    case = load(client, "DEMO-03")
    draft_id = prepare(client, case)
    original = workflow(client, case)["drafts"][-1]
    revision = current(client, case)["revision"]
    candidate = original["candidate"]
    record = next(
        e
        for e in client.get(f"/api/cases/{case['id']}/evidence").json()
        if e["details"]["kind"] == "record"
    )
    response = client.post(
        f"/api/cases/{case['id']}/draft-edits",
        json={
            "request_id": str(uuid4()),
            "expected_revision": revision,
            "draft_id": draft_id,
            "draft_version": original["version"],
            **{k: candidate[k] for k in ("response_type", "concerns", "attachment_ids")},
            "claims": [{"field": "tax_status", "value": "paid", "evidence_id": record["id"]}],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "response_invalid"
    assert workflow(client, case)["drafts"] == [original]
    assert current(client, case)["revision"] == revision


def test_case_references_and_input_identity_cannot_cross_cases(client, application):
    from test_phase6 import TestModel

    first, second = load(client, "DEMO-04"), load(client, "DEMO-04")
    result, payload = supply(client, first, "bankruptcy_specialist_result")
    assert client.post(f"/api/cases/{second['id']}/inputs", json=payload).status_code == 409
    draft_id = new_response(client, first, "referral")
    review = client.post(
        f"/api/cases/{second['id']}/reviews",
        json={
            "expected_case_revision": second["revision"],
            "draft_id": draft_id,
            "draft_version": 1,
            "decision": "approve",
        },
    )
    assert review.status_code == 409
    handoff, _ = act(client, first, "cct.handoff")
    ack = client.post(
        f"/api/cases/{second['id']}/handoff-acknowledgments",
        json={
            "request_id": str(uuid4()),
            "expected_revision": second["revision"],
            "handoff_id": handoff["reference"]["id"],
        },
    )
    assert ack.status_code == 404
    application.state.agent_worker.model = TestModel()
    with application.state.sessions() as session, session.begin():
        previous = AgentRun(
            case_id=first["id"], case_revision=result["revision"], status="waiting_for_input"
        )
        session.add(previous)
        session.flush()
        run_id = previous.id
    response = client.post(
        f"/api/cases/{second['id']}/runs",
        json={"expected_revision": second["revision"], "resume_from": run_id},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "run_not_resumable"


def test_no_work_allows_only_administrative_handoff(client, application):
    case = load(client, "DEMO-01", "followup")
    change_context(
        application,
        case,
        {
            "routing": {
                "assessment": "inquiry",
                "channel": "email",
                "queue": "Inquiry",
                "special_routes": [
                    {
                        "route": "Legal",
                        "rule": "RULE-08",
                        "reason": "Active legal restriction",
                        "restrictions": ["no_work"],
                    }
                ],
            }
        },
    )
    act(client, case, "cct.apply_plan")
    candidate = candidate_for(client, current(client, case))
    act(client, case, "csp.prepare", expected="rejected", candidate=candidate)
    task = read(client, case, "ils.tasks")["tasks"][0]
    act(client, case, "ils.update_name", expected="rejected", task_id=task["id"])
    handoff, _ = act(client, case, "cct.handoff")
    assert handoff["data"]["handoff"]["restrictions"] == ["no_work"]
    saved = client.get(f"/api/cases/{case['id']}/artifacts").json()
    assert not saved["outbox"] and not saved["drafts"]
    assert not client.get(f"/api/cases/{case['id']}/completion-check").json()["valid"]


def test_paused_agent_resumes_new_input_then_exact_approved_draft(settings):
    from fastapi.testclient import TestClient
    from test_phase6 import TestModel, choice, start_run

    from app.main import create_app

    class ResumingModel(TestModel):
        def choose(self, observation, history, timeout):
            if observation is None:
                return choice("observe_case")
            if not observation["plan_current"]:
                return choice("apply_plan")
            drafts = observation["saved"]["drafts"]
            if not drafts or not drafts[-1]["current"]:
                document = next(
                    e
                    for e in observation["evidence"]
                    if e["details"].get("key") == "amortization"
                    and e["details"].get("availability") == "available"
                )
                return choice(
                    "prepare_response",
                    response_type="final_resolution",
                    attachment_ids=[document["id"]],
                    claims=[
                        {
                            "field": "document_attached",
                            "value": document["title"],
                            "evidence_id": document["id"],
                        }
                    ],
                    concerns=[
                        {k: c[k] for k in ("concern_id", "disposition")}
                        for c in observation["assessment"]["concerns"]
                    ],
                )
            draft = drafts[-1]
            for resource, tool in (
                ("outbox", "send_response"),
                ("packages", "index_response"),
                ("notes", "record_final_note"),
            ):
                if not any(
                    (r.get("draft_id") or r.get("details", {}).get("draft_id")) == draft["id"]
                    for r in observation["saved"][resource]
                ):
                    return choice(tool, draft_id=draft["id"])
            if observation["case"]["status"] != "closed":
                return choice("close_case", draft_id=draft["id"])
            return choice("finish_run", outcome="completed")

    app = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(app) as client:
        case = load(client, "DEMO-02", "missing_document")
        initial = start_run(client, case)
        app.state.agent_worker.run_once()
        assert client.get(f"/api/runs/{initial['id']}").json()["status"] == "waiting_for_input"
        interim = client.get(f"/api/cases/{case['id']}/artifacts").json()["outbox"][0]
        supply(client, case, "amortization_document")
        app.state.agent_worker.model = ResumingModel()
        resumed = start_run(client, current(client, case), resume_from=initial["id"])
        assert resumed["checkpoint"]["resumed_from"] == initial["id"]
        app.state.agent_worker.run_once()
        assert client.get(f"/api/runs/{resumed['id']}").json()["status"] == "completed"
        saved = client.get(f"/api/cases/{case['id']}/artifacts").json()
        assert len(saved["outbox"]) == 2 and saved["outbox"][0] == interim
        assert current(client, case)["original_received_at"] == case["original_received_at"]

        case = load(client)
        paused = start_run(client, case, mode="review_required")
        app.state.agent_worker.run_once()
        draft = workflow(client, case)["drafts"][-1]
        approve(client, case, draft["id"])
        resumed = start_run(
            client, current(client, case), resume_from=paused["id"], mode="automatic"
        )
        assert resumed["checkpoint"]["mode"] == "review_required"
        app.state.agent_worker.run_once()
        assert client.get(f"/api/runs/{resumed['id']}").json()["status"] == "completed"
        saved = client.get(f"/api/cases/{case['id']}/artifacts").json()
        assert len(saved["drafts"]) == 1 and saved["outbox"][0]["draft_id"] == draft["id"]
