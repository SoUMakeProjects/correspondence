"""Persisted failure/recovery acceptance. Deterministic model, real services and effects."""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_phase4 import act, prepare
from test_phase6 import TestModel, load, start_run

from app.db import utcnow
from app.main import create_app
from app.models import ActionReceipt, AgentRun, CaseEvent, CorrespondenceCase, Evidence


def current(client, case):
    return client.get(f"/api/cases/{case['id']}").json()


def recovery(client, case):
    return client.get(f"/api/cases/{case['id']}/recovery").json()


def mutate(client, case, path, **fields):
    payload = {
        "request_id": str(uuid4()),
        "expected_revision": current(client, case)["revision"],
        **fields,
    }
    response = client.post(f"/api/cases/{case['id']}/recovery/{path}", json=payload)
    assert response.status_code == 200, response.text
    assert (
        client.post(f"/api/cases/{case['id']}/recovery/{path}", json=payload).json()
        == response.json()
    )
    return response.json()


@pytest.mark.parametrize(
    "fault,first_outcome",
    [
        ("index_failure", "not_applied"),
        ("lost_send_response", "applied"),
        ("unknown_send_status", "unknown"),
    ],
)
def test_partial_failure_reconciles_and_resumes_without_resending(settings, fault, first_outcome):
    app = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(app) as client:
        case = load(client)
        run = start_run(client, case, fault=fault)
        app.state.agent_worker.run_once()
        saved = client.get(f"/api/cases/{case['id']}/artifacts").json()
        assert len(saved["outbox"]) == 1 and not saved["packages"]
        paused = client.get(f"/api/runs/{run['id']}").json()
        assert paused["status"] == "waiting_for_input"
        assert paused["checkpoint"]["fault"]["consumed"]
        info = recovery(client, case)
        assert info["actions"][0]["outcome"] == first_outcome
        if fault == "unknown_send_status":
            assert mutate(client, case, "check")["blocked"]
            assert (
                client.post(
                    f"/api/cases/{case['id']}/runs",
                    json={"expected_revision": current(client, case)["revision"]},
                ).status_code
                == 409
            )
            mutate(client, case, "restore-status", action_id=info["actions"][0]["id"])
        assert not mutate(client, case, "check")["blocked"]
        resumed = start_run(client, current(client, case), resume_from=run["id"])
        app.state.agent_worker.run_once()
        assert client.get(f"/api/runs/{resumed['id']}").json()["status"] == "completed"
        after = client.get(f"/api/cases/{case['id']}/artifacts").json()
        assert after["outbox"] == saved["outbox"]
        assert len(after["packages"]) == len(after["notes"]) == 1
        assert current(client, case)["original_received_at"] == case["original_received_at"]


@pytest.mark.parametrize(
    "window,fault",
    [("before_send", "none"), ("after_send", "none"), ("after_send", "lost_send_response")],
)
def test_crash_between_effect_and_checkpoint_recovers_same_run(
    settings, monkeypatch, window, fault
):
    import app.agent_tools as tool_module

    original = tool_module.dispatch

    class SimulatedProcessLoss(BaseException):
        pass

    def crash(*args, **kwargs):
        if args[4].command.operation == "csp.send":
            if window == "after_send":
                original(*args, **kwargs)
            raise SimulatedProcessLoss()
        return original(*args, **kwargs)

    app = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(app) as client:
        case = load(client)
        run = start_run(client, case, fault=fault)
        monkeypatch.setattr(tool_module, "dispatch", crash)
        with pytest.raises(SimulatedProcessLoss):
            app.state.agent_worker.run_once()
        crashed = client.get(f"/api/runs/{run['id']}").json()
        assert crashed["status"] == "running"
        assert not app.state.agent_worker.run_once()  # A still-valid lease cannot be stolen.
        with app.state.sessions() as session, session.begin():
            session.get(AgentRun, run["id"]).lease_expires_at = utcnow() - timedelta(seconds=1)
        monkeypatch.setattr(tool_module, "dispatch", original)
        app.state.agent_worker.run_once()
        recovered = client.get(f"/api/runs/{run['id']}").json()
        assert recovered["status"] == "completed", recovered
        assert recovered["checkpoint"]["recovery_count"] == 1
        assert recovered["checkpoint"]["started_at"] == crashed["checkpoint"]["started_at"]
        assert recovered["checkpoint"]["model_calls"] > crashed["checkpoint"]["model_calls"]
        assert (
            recovered["checkpoint"]["history"][: len(crashed["checkpoint"]["history"])]
            == crashed["checkpoint"]["history"]
        )
        artifacts = client.get(f"/api/cases/{case['id']}/artifacts").json()
        assert all(len(artifacts[k]) == 1 for k in ("outbox", "packages", "notes"))
        assert len(client.get(f"/api/cases/{case['id']}/runs").json()) == 1


def test_recovery_does_not_reset_limits_or_unstop_a_presenter(settings):
    from app.repository import claim_next_run

    app = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(app) as client:
        case = load(client)
        run = start_run(client, case)
        with app.state.sessions() as session:
            claimed = claim_next_run(session, "interrupted")
            claimed.checkpoint = {
                **claimed.checkpoint,
                "model_calls": settings.agent_max_model_calls,
            }
            claimed.lease_expires_at = utcnow() - timedelta(seconds=1)
            session.commit()
        app.state.agent_worker.run_once()
        recovered = client.get(f"/api/runs/{run['id']}").json()
        assert recovered["checkpoint"]["reason"] == "max_model_calls"
        assert recovered["checkpoint"]["model_calls"] == settings.agent_max_model_calls
        stopped = start_run(client, current(client, case))
        client.post(f"/api/runs/{stopped['id']}/stop")
        assert not app.state.agent_worker.run_once()
        assert client.get(f"/api/runs/{stopped['id']}").json()["status"] == "stopped"


def test_unknown_or_damaged_evidence_is_never_marked_applied(settings):
    app = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(app) as client:
        case = load(client)
        start_run(client, case, fault="lost_send_response")
        app.state.agent_worker.run_once()
        with app.state.sessions() as session, session.begin():
            action = session.scalar(
                select(ActionReceipt).where(
                    ActionReceipt.case_id == case["id"], ActionReceipt.status == "uncertain"
                )
            )
            action.result = {**action.result, "effect_hash": "0" * 64}
        assert mutate(client, case, "check")["blocked"]
        assert recovery(client, case)["actions"][0]["outcome"] == "unknown"
        assert current(client, case)["status"] != "closed"


def test_recovery_controls_scope_revision_and_active_worker(client, application):
    first, other = load(client), load(client)
    draft = prepare(client, first)
    action, _ = act(
        client,
        first,
        "csp.send",
        failure_mode="after_write_response_lost",
        expected="uncertain",
        draft_id=draft,
    )
    response = client.post(
        f"/api/cases/{other['id']}/recovery/restore-status",
        json={
            "request_id": str(uuid4()),
            "expected_revision": other["revision"],
            "action_id": action["action_id"],
        },
    )
    assert response.status_code == 404
    stale = client.post(
        f"/api/cases/{first['id']}/recovery/check",
        json={"request_id": str(uuid4()), "expected_revision": 1},
    )
    assert stale.status_code == 409
    with application.state.sessions() as session, session.begin():
        session.add(
            AgentRun(
                case_id=first["id"],
                case_revision=current(client, first)["revision"],
                status="queued",
            )
        )
    response = client.post(
        f"/api/cases/{first['id']}/recovery/check",
        json={"request_id": str(uuid4()), "expected_revision": current(client, first)["revision"]},
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "run_active"


def test_summary_reconciles_receipts_and_export_omits_user_text(settings):
    app = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(app) as client:
        case = load(client)
        run = start_run(client, case)
        app.state.agent_worker.run_once()
        marker = "HISTORICAL-123456789-SOURCE-SECRET"
        with app.state.sessions() as session, session.begin():
            row = session.get(CorrespondenceCase, case["id"])
            row.correspondence_text = marker
            row.owner = marker
            evidence = session.scalar(select(Evidence).where(Evidence.case_id == case["id"]))
            evidence.title = marker
            session.add(
                CaseEvent(
                    case_id=case["id"],
                    kind="input.received",
                    actor=marker,
                    payload={"text": marker},
                )
            )
        summary = client.get(f"/api/runs/{run['id']}/summary")
        assert summary.status_code == 200, summary.text
        assert summary.json()["completed_actions"] == 6
        assert (
            summary.json()["model_calls"]
            == client.get(f"/api/runs/{run['id']}").json()["checkpoint"]["model_calls"]
        )
        exported = client.get(f"/api/runs/{run['id']}/export")
        assert exported.status_code == 200, exported.text
        assert marker not in exported.text
        assert case["loan_identifier"] not in exported.text
        assert "attachment;" in exported.headers["content-disposition"]
        data = exported.json()
        assert len(data["outbox"]) == len(data["packages"]) == len(data["notes"]) == 1
        assert data["outbox"][0]["draft_id"] == data["drafts"][0]["id"]
        assert data["run"]["completed_actions"] == summary.json()["completed_actions"]


def test_fresh_instance_preserves_prior_run_and_artifacts(settings):
    app = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(app) as client:
        first = load(client)
        run = start_run(client, first)
        app.state.agent_worker.run_once()
        before = client.get(f"/api/cases/{first['id']}/artifacts").json()
        fresh = load(client)
        assert fresh["id"] != first["id"] and fresh["simulation_id"] != first["simulation_id"]
        assert client.get(f"/api/cases/{fresh['id']}/runs").json() == []
        assert client.get(f"/api/runs/{run['id']}").json()["status"] == "completed"
        assert client.get(f"/api/cases/{first['id']}/artifacts").json() == before


def test_graceful_server_shutdown_requeues_without_losing_history(settings):
    from test_phase6 import choice

    app = None

    class ShutdownModel(TestModel):
        def choose(self, observation, history, timeout):
            if observation and observation["saved"]["outbox"]:
                app.state.agent_worker.halt.set()
                return choice("index_response", draft_id=observation["saved"]["drafts"][-1]["id"])
            return super().choose(observation, history, timeout)

    app = create_app(settings, agent_model=ShutdownModel(), start_worker=False)
    with TestClient(app) as client:
        case = load(client)
        run = start_run(client, case)
        app.state.agent_worker.run_once()
        suspended = client.get(f"/api/runs/{run['id']}").json()
        assert suspended["status"] == "queued" and suspended["checkpoint"]["recovery_pending"]
    restarted = create_app(settings, agent_model=TestModel(), start_worker=False)
    with TestClient(restarted) as client:
        restarted.state.agent_worker.run_once()
        recovered = client.get(f"/api/runs/{run['id']}").json()
        assert recovered["status"] == "completed"
        assert (
            recovered["checkpoint"]["history"][: len(suspended["checkpoint"]["history"])]
            == suspended["checkpoint"]["history"]
        )
        assert len(client.get(f"/api/cases/{case['id']}/artifacts").json()["outbox"]) == 1


def test_lost_task_result_reuses_verified_task(settings):
    from test_phase3 import load as load_case
    from test_phase6 import choice
    from test_phase7 import supply

    class TaskModel(TestModel):
        def choose(self, observation, history, timeout):
            if observation is None:
                return choice("observe_case")
            return choice("create_task", task_type="demo_profile_name_update")

    app = create_app(settings, agent_model=TaskModel(), start_worker=False)
    with TestClient(app) as client:
        case = load_case(client, "DEMO-01")
        supply(client, case, "name_legal_document")
        run = start_run(client, current(client, case), fault="lost_task_response")
        app.state.agent_worker.run_once()
        assert (
            client.get(f"/api/runs/{run['id']}").json()["checkpoint"]["reason"]
            == "reconciliation_required"
        )
        tasks = client.get(f"/api/cases/{case['id']}/tasks").json()
        assert len(tasks) == 1
        assert not mutate(client, case, "check")["blocked"]
        result, _ = act(client, case, "ils.create_task", task_type="demo_profile_name_update")
        assert result["reference"]["id"] == tasks[0]["id"]
        assert len(client.get(f"/api/cases/{case['id']}/tasks").json()) == 1
