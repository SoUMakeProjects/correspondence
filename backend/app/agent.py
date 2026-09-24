"""Bounded local agent worker with persisted checkpoints and lease-fenced writes."""

import threading
import time
from collections import Counter
from datetime import datetime
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select, text

from app.agent_contracts import TOOLS
from app.agent_model import AzureModel, ModelError
from app.agent_tools import execute, observe, verified_outcome
from app.azure_probe import configuration_fingerprint
from app.db import utcnow
from app.domain import DomainError
from app.models import ActionReceipt, AgentRun, AutomationSignal, CaseEvent
from app.recovery import recover_worker
from app.repository import claim_next_run, fingerprint, renew_lease, require_case

ACTIVE = {"queued", "running"}


def event(session, run, kind, payload):
    session.add(
        CaseEvent(
            case_id=run.case_id,
            run_id=run.id,
            kind=kind,
            actor="azure_agent"
            if run.model_configuration.get("source") == "live_azure"
            else "test_double",
            payload=payload,
        )
    )


def start(session, settings, case_id, payload, source="live_azure", *, trigger_id=None):
    session.execute(text("BEGIN IMMEDIATE"))
    if trigger_id:
        trigger = session.get(AutomationSignal, trigger_id)
        if trigger.run_id:
            return session.get(AgentRun, trigger.run_id)
        if trigger.case_id != case_id or trigger.status != "ready":
            raise DomainError(409, "trigger_not_ready", "The event is not ready for processing.")
        # Recheck under the run-creation lock: mail can arrive after dispatch's read.
        if session.scalar(
            select(AutomationSignal.id).where(
                AutomationSignal.thread_id == trigger.thread_id,
                AutomationSignal.status.in_(["pending", "blocked"]),
            )
        ):
            raise DomainError(
                409, "mail_pending", "Incoming mail must be processed before continuation."
            )
    case = require_case(session, case_id)
    if source == "live_azure" and settings.missing_azure_fields:
        raise DomainError(
            409,
            "azure_not_configured",
            "Complete the Azure environment values before starting a model run.",
        )
    if case.revision != payload.expected_revision:
        raise DomainError(409, "stale_revision", "The case changed. Refresh before starting.")
    if case.status == "closed":
        raise DomainError(
            409, "case_closed", "This case is already closed. Inspect its saved results."
        )
    if session.scalar(
        select(AgentRun.id).where(AgentRun.case_id == case_id, AgentRun.status.in_(ACTIVE))
    ):
        raise DomainError(409, "run_active", "This case already has a queued or running agent.")
    if session.scalar(
        select(ActionReceipt.id).where(
            ActionReceipt.case_id == case_id, ActionReceipt.status.in_(["uncertain", "in_progress"])
        )
    ):
        raise DomainError(
            409,
            "reconciliation_required",
            "Reconcile the outstanding action before starting a new run.",
        )
    observe(session, settings.data_dir, case_id)
    mode = payload.mode
    if payload.resume_from:
        previous = session.get(AgentRun, str(payload.resume_from))
        if (
            not previous
            or previous.case_id != case_id
            or previous.status
            not in {"waiting_for_input", "waiting_for_review", "failed", "stopped"}
        ):
            raise DomainError(409, "run_not_resumable", "Select a paused run from this case.")
        mode = previous.checkpoint.get("mode", mode)
    run = AgentRun(
        case_id=case_id,
        case_revision=case.revision,
        status="queued",
        checkpoint={
            "version": 8,
            "phase": "queued",
            "mode": mode,
            "resumed_from": str(payload.resume_from) if payload.resume_from else None,
            "steps": 0,
            "model_calls": 0,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "stop_requested": False,
            "history": [],
            "fault": {"kind": payload.fault, "consumed": False},
        },
        model_configuration={
            "provider": "azure_openai",
            "source": source,
            "configuration_id": configuration_fingerprint(settings)
            if source == "live_azure"
            else "test-only",
            "protocol": "chat_completions_v1",
            "prompt_version": "phase8-v3",
            "tool_contract": 7,
            "limits": {
                key: getattr(settings, "agent_" + key)
                for key in (
                    "max_steps",
                    "max_seconds",
                    "max_model_calls",
                    "max_total_tokens",
                    "max_completion_tokens",
                    "max_context_characters",
                )
            },
        },
    )
    session.add(run)
    session.flush()
    if trigger_id:
        triggers = list(
            session.scalars(
                select(AutomationSignal).where(
                    AutomationSignal.case_id == case_id,
                    AutomationSignal.status == "ready",
                )
            )
        )
        run.checkpoint = {
            **run.checkpoint,
            "trigger_ids": [t.id for t in triggers],
            "trigger": trigger.kind,
        }
        for signal in triggers:
            signal.run_id, signal.status = run.id, "queued"
            signal.detail = "Agent run started automatically."
    event(
        session,
        run,
        "agent.queued",
        {
            "source": source,
            "mode": mode,
            "resumed_from": str(payload.resume_from) if payload.resume_from else None,
            "configuration_id": run.model_configuration["configuration_id"],
            "fault": payload.fault,
        },
    )
    session.commit()
    return run


def request_stop(session, run_id):
    session.execute(text("BEGIN IMMEDIATE"))
    run = session.get(AgentRun, run_id)
    if not run:
        raise DomainError(404, "run_not_found", "This run was not found.")
    if run.status in ACTIVE:
        run.checkpoint = {**run.checkpoint, "stop_requested": True}
        if run.status == "queued":
            run.status = "stopped"
            run.checkpoint = {**run.checkpoint, "phase": "stopped", "reason": "presenter_stop"}
        run.updated_at = utcnow()
        event(
            session,
            run,
            "agent.stop_requested",
            {"message": "Stop requested; an already-started action can finish before stopping."},
        )
    session.commit()
    return run


class AgentWorker:
    def __init__(self, settings, sessions, model=None):
        self.settings, self.sessions = settings, sessions
        self.model = model or AzureModel(settings)
        self.identity = "local-agent-" + str(uuid4())
        self.halt = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.lease_seconds = settings.azure_openai_timeout_seconds + 90

    def launch(self):
        self.thread = threading.Thread(target=self.loop, name="correspondence-agent", daemon=True)
        self.thread.start()

    def shutdown(self):
        self.halt.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=self.settings.azure_openai_timeout_seconds + 5)

    def loop(self):
        while not self.halt.is_set():
            if not self.run_once():
                self.wake.wait(0.5)
                self.wake.clear()

    def save(self, run_id, token, changes=None, status=None, kind=None, payload=None):
        with self.sessions() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            if not renew_lease(session, run_id, token, self.lease_seconds):
                session.rollback()
                raise DomainError(409, "lease_lost", "The worker no longer owns this run.")
            run = session.get(AgentRun, run_id)
            run.checkpoint = {**run.checkpoint, **(changes or {})}
            if status:
                run.status = status
                run.lease_expires_at = None
                run.checkpoint = {**run.checkpoint, "phase": status}
            if kind:
                event(session, run, kind, payload or {})
            session.commit()
            return dict(run.checkpoint)

    def suspend(self, run_id, token):
        self.save(
            run_id,
            token,
            {"recovery_pending": True},
            "queued",
            "agent.suspended",
            {"reason": "server_shutdown"},
        )

    def finish(self, run_id, token, status, reason, summary=None):
        with self.sessions() as session:
            started_at = session.get(AgentRun, run_id).checkpoint.get("started_at")
        elapsed = (
            max(0, (utcnow() - datetime.fromisoformat(started_at)).total_seconds())
            if started_at
            else 0
        )
        self.save(
            run_id,
            token,
            {
                "reason": reason,
                "finished_at": utcnow().isoformat(),
                "elapsed_seconds": round(elapsed, 2),
                "summary": summary or {},
            },
            status,
            "agent.finished",
            {"status": status, "reason": reason, "summary": summary or {}},
        )

    def run_once(self):
        with self.sessions() as session:
            run = claim_next_run(session, self.identity, self.lease_seconds)
            if run is None:
                session.commit()
                return False
            run_id, case_id, token = run.id, run.case_id, run.lease_token
            recovered = run.checkpoint.get("reconciliation_required")
            configuration = dict(run.model_configuration)
            session.commit()
        try:
            if configuration.get("source") != self.model.source or (
                self.model.source == "live_azure"
                and configuration.get("configuration_id")
                != configuration_fingerprint(self.settings)
            ):
                self.finish(run_id, token, "waiting_for_input", "model_configuration_changed")
                return True
            with self.sessions() as session:
                stopped = session.get(AgentRun, run_id).checkpoint.get("stop_requested")
            if stopped:
                self.finish(run_id, token, "stopped", "presenter_stop")
            elif recovered and not recover_worker(self, run_id, case_id, token):
                self.finish(run_id, token, "waiting_for_input", "reconciliation_required")
            else:
                self.process(run_id, case_id, token)
        except DomainError as exc:
            if exc.code != "lease_lost":
                self.safe_fail(run_id, token, exc.code)
        except Exception:
            self.safe_fail(run_id, token, "worker_error_inspect_actions")
        return True

    def safe_fail(self, run_id, token, reason):
        try:
            self.finish(run_id, token, "failed", reason)
        except DomainError:
            pass

    def process(self, run_id, case_id, token):
        with self.sessions() as session:
            run = session.get(AgentRun, run_id)
            existing = dict(run.checkpoint)
            limits = {
                k: min(v, getattr(self.settings, "agent_" + k))
                for k, v in run.model_configuration["limits"].items()
            }
        started_at = existing.get("started_at") or utcnow().isoformat()
        started = time.monotonic() - max(
            0, (utcnow() - datetime.fromisoformat(started_at)).total_seconds()
        )
        history = list(existing.get("history", []))
        observation, failures = (
            None,
            Counter(h["code"] for h in history if h["status"] in {"failed", "rejected"}),
        )
        retrieved = {}
        reads = Counter()
        checkpoint = self.save(
            run_id,
            token,
            {"started_at": started_at, "finished_at": None},
            kind="agent.continued" if existing.get("started_at") else "agent.started",
            payload={"source": self.model.source},
        )
        while True:
            checkpoint = self.save(run_id, token)
            elapsed = time.monotonic() - started
            reason = None
            if checkpoint.get("stop_requested") or self.halt.is_set():
                if checkpoint.get("stop_requested"):
                    self.finish(run_id, token, "stopped", "presenter_stop")
                else:
                    self.suspend(run_id, token)
                return
            for limit, used in (
                ("max_steps", checkpoint["steps"]),
                ("max_model_calls", checkpoint["model_calls"]),
                ("max_seconds", elapsed),
                ("max_total_tokens", checkpoint["usage"]["total_tokens"]),
            ):
                if used >= limits[limit]:
                    reason = limit
                    break
            if reason:
                self.finish(run_id, token, "waiting_for_input", reason)
                return
            checkpoint = self.save(
                run_id,
                token,
                {
                    "phase": "choosing_tool",
                    "elapsed_seconds": round(elapsed, 2),
                    "model_calls": checkpoint["model_calls"] + 1,
                },
            )
            try:
                choice = self.model.choose(observation, history, limits["max_seconds"] - elapsed)
            except ModelError as exc:
                self.finish(run_id, token, "failed", str(exc))
                return
            usage = {
                key: checkpoint["usage"][key] + choice.usage.get(key, 0)
                for key in checkpoint["usage"]
            }
            checkpoint = self.save(run_id, token, {"usage": usage})
            # Cancellation and usage/time limits are checked again BEFORE any model-chosen effect.
            if checkpoint.get("stop_requested") or self.halt.is_set():
                continue
            if (
                usage["total_tokens"] >= limits["max_total_tokens"]
                or time.monotonic() - started >= limits["max_seconds"]
            ):
                continue
            name = choice.name if choice.name in TOOLS else "unavailable_tool"
            action_id = str(uuid4())
            result = None
            try:
                if choice.name not in TOOLS:
                    raise DomainError(
                        422, "tool_not_allowed", "Choose one of the enabled application tools."
                    )
                contract, operation, _ = TOOLS[choice.name]
                arguments = contract.model_validate_json(choice.arguments).model_dump(mode="json")
                self.save(
                    run_id,
                    token,
                    {
                        "phase": "executing_tool",
                        "current_tool": name,
                        "planned_action_id": action_id,
                    },
                    kind="agent.tool_planned",
                    payload={
                        "tool": name,
                        "arguments_hash": fingerprint(arguments),
                        "action_id": action_id,
                        "evidence_versions": observation["assessment"]["evidence_versions"]
                        if observation
                        else {},
                    },
                )
                if name == "finish_run":
                    with self.sessions() as session:
                        summary = verified_outcome(
                            session,
                            self.settings.data_dir,
                            session.get(AgentRun, run_id),
                            arguments["outcome"],
                        )
                    final_step = {
                        "step": checkpoint["steps"] + 1,
                        "tool": name,
                        "status": "ok",
                        "code": "verified_outcome",
                        "message": "The final outcome was verified against persisted records.",
                    }
                    history.append(final_step)
                    self.save(
                        run_id,
                        token,
                        {"steps": len(history), "history": history},
                        kind="agent.tool_result",
                        payload=final_step,
                    )
                    self.finish(
                        run_id,
                        token,
                        "completed"
                        if arguments["outcome"] == "transferred"
                        else arguments["outcome"],
                        "verified_handoff"
                        if arguments["outcome"] == "transferred"
                        else "verified_outcome",
                        summary,
                    )
                    return
                if name == "observe_case":
                    result = {
                        "status": "ok",
                        "code": "observed",
                        "message": "Current scoped evidence and saved results inspected.",
                    }
                else:
                    result = execute(
                        self.sessions,
                        self.settings.data_dir,
                        case_id,
                        operation,
                        arguments,
                        observation,
                        action_id,
                        run_id,
                        token,
                    )
                if name in {"knowledge_search", "document_read", "task_read"}:
                    retrieved[name + ":" + fingerprint(arguments)] = result.get("data", {})
                with self.sessions() as session:
                    observation = observe(session, self.settings.data_dir, case_id)
                    observation["run_mode"] = checkpoint["mode"]
                observation["retrieved_data"] = list(retrieved.values())
            except ValidationError:
                result = {
                    "status": "rejected",
                    "code": "invalid_tool_arguments",
                    "message": "Arguments must exactly match the enabled tool schema; scope, versions and credentials cannot be supplied.",
                }
            except DomainError as exc:
                if exc.code == "lease_lost":
                    raise
                result = {"status": "rejected", "code": exc.code, "message": exc.message}
            public = {
                "step": checkpoint["steps"] + 1,
                "tool": name,
                **{
                    key: result[key]
                    for key in ("status", "code", "message", "action_id", "reference")
                    if key in result
                },
            }
            history.append(public)
            checkpoint = self.save(
                run_id,
                token,
                {
                    "phase": "tool_finished",
                    "steps": len(history),
                    "history": history,
                    "planned_action_id": None,
                    "evidence_versions": observation["assessment"]["evidence_versions"]
                    if observation
                    else {},
                    "input_hash": observation["assessment"]["input_hash"] if observation else None,
                },
                kind="agent.tool_result",
                payload=public,
            )
            if (
                result["status"] in {"uncertain", "in_progress"}
                or result["code"] == "reconciliation_required"
            ):
                self.finish(run_id, token, "waiting_for_input", "reconciliation_required")
                return
            if result["status"] == "awaiting_review":
                self.finish(run_id, token, "waiting_for_review", "review_required")
                return
            if result["status"] == "failed" and result["code"] == "write_failed":
                self.finish(run_id, token, "waiting_for_input", "write_failed")
                return
            if result["status"] in {"failed", "rejected"}:
                failures[result["code"]] += 1
                if failures[result["code"]] >= 3:
                    self.finish(run_id, token, "waiting_for_input", "repeated_tool_error")
                    return
            if (
                name in {"observe_case", "knowledge_search", "document_read", "task_read"}
                and observation
                and result["status"] == "ok"
            ):
                read_key = (
                    name,
                    fingerprint(arguments),
                    observation["assessment"]["input_hash"],
                    observation["case"]["revision"],
                )
                reads[read_key] += 1
                if reads[read_key] >= 3:
                    self.finish(
                        run_id, token, "waiting_for_input", "repeated_read_without_progress"
                    )
                    return
