import { useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import type { AgentRun, Artifacts, Case, RunFault } from "./api/client";
import CaseWorkflow from "./CaseWorkflow";
import RunRecovery from "./RunRecovery";
import { displayLabel as readable, displayText } from "./presentation";

type Step = {
  step: number;
  tool: string;
  status: string;
  code: string;
  message: string;
  reference?: { kind: string; id: string };
};
type Checkpoint = {
  phase?: string;
  reason?: string;
  steps?: number;
  model_calls?: number;
  current_tool?: string;
  stop_requested?: boolean;
  history?: Step[];
  usage?: { total_tokens?: number };
  summary?: {
    pending_work?: {
      concern_id: string;
      reason: string;
      owner: string;
      resume_requirement: string;
    }[];
  };
};
const active = (run?: AgentRun) =>
  !!run && ["queued", "running"].includes(run.status);
const date = (value: string) =>
  new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
// Desk-only wording: readable names instead of raw tool and status values.
const deskStatus: Record<string, string> = {
  ok: "Completed",
  simulated_complete: "Completed",
  queued: "Queued",
  running: "Running",
  waiting_for_review: "Awaiting review",
  waiting_for_input: "Awaiting input",
  awaiting_review: "Awaiting review",
  completed: "Completed",
  failed: "Needs attention",
  stopped: "Stopped",
  sent: "Sent",
  delivered: "Delivered",
  document_attached: "Document attached",
  final_resolution: "Final resolution",
  information_request: "Information request",
  interim_acknowledgment: "Interim acknowledgment",
  referral: "Referral",
};
const sentence = (value: unknown) => {
  const text = readable(value);
  return text ? text[0].toUpperCase() + text.slice(1) : text;
};
const reasons: Record<string, string> = {
  max_steps:
    "The tool step limit was reached. Inspect the saved actions before continuing.",
  max_model_calls: "The model call limit was reached.",
  max_total_tokens: "The model usage limit was reached.",
  max_seconds: "The run time limit was reached.",
  repeated_tool_error:
    "The same tool error occurred three times. Review the result below.",
  repeated_read_without_progress:
    "The agent repeated the same read without making progress. Inspect the retained evidence and results.",
  reconciliation_required:
    "An action result is uncertain. Inspect and reconcile it before starting again.",
  write_failed:
    "The action failed before completion. Resume to complete the remaining work; prior deliveries are retained.",
  model_configuration_changed:
    "The model configuration changed while this run was interrupted. Start a new linked run to use the current configuration.",
  interrupted_run_inspect_actions:
    "The worker was interrupted. Inspect its saved actions before starting again.",
  presenter_stop:
    "Stopped at a safe boundary. Already completed actions are retained.",
  review_required: "Review the prepared response below, then resume the agent.",
  verified_handoff:
    "The specialist acknowledged receipt. The case remains transferred with its concerns tracked.",
  azure_connection_or_timeout:
    "Azure could not be reached or the request timed out. Saved actions are retained.",
  verified_outcome:
    "The result was checked against the saved case and records.",
};

export default function AgentWorkspace({
  item,
  available,
  onCaseUpdated,
  automatic = false,
  desk = false,
  toolName,
  onShowTimeline,
}: {
  item: Case;
  available: boolean;
  onCaseUpdated: (item: Case) => void;
  automatic?: boolean;
  /** Render inside the Correspondence Desk: readable labels, no duplicate step list. */
  desk?: boolean;
  toolName?: (tool: string) => string;
  onShowTimeline?: () => void;
}) {
  const status = (value: unknown) =>
    desk ? (deskStatus[String(value)] ?? sentence(value)) : readable(value);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [artifacts, setArtifacts] = useState<Artifacts | null>(null);
  const [mode, setMode] = useState<"automatic" | "review_required">(
    "automatic",
  );
  const [chosen, setChosen] = useState<string | null>(null);
  const [fault, setFault] = useState<RunFault>("none");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const currentItem = useRef(item);
  currentItem.current = item;
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const [history, saved, current] = await Promise.all([
          api.runs(item.id, controller.signal),
          api.artifacts(item.id, controller.signal),
          api.case(item.id, controller.signal),
        ]);
        if (controller.signal.aborted) return;
        setRuns(history);
        setArtifacts(saved);
        setLoaded(true);
        setError("");
        if (current.revision > currentItem.current.revision)
          onCaseUpdated(current);
        timer = setTimeout(
          () => void poll(),
          history.some(active) ? 1200 : 5000,
        );
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(
            reason instanceof Error
              ? reason.message
              : "Run history could not be loaded.",
          );
          timer = setTimeout(() => void poll(), 5000);
        }
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [item.id, refresh, onCaseUpdated]);

  const latest = runs.at(-1);
  const selected = runs.find((run) => run.id === chosen) ?? latest;
  const checkpoint = (selected?.checkpoint ?? {}) as Checkpoint;
  const running = runs.some(active);
  async function start(resume = false) {
    setBusy(true);
    setError("");
    try {
      if (automatic && resume) {
        await api.resumeProcessing(item.id, item.revision);
        if (mounted.current) setRefresh((n) => n + 1);
        return;
      }
      const run =
        resume && latest
          ? await api.resumeRun(item.id, item.revision, latest.id)
          : await api.startRun(item.id, item.revision, mode, fault);
      if (!mounted.current) return;
      setRuns((previous) => [...previous, run]);
      setChosen(run.id);
      setRefresh((n) => n + 1);
    } catch (reason) {
      if (mounted.current)
        setError(
          reason instanceof Error ? reason.message : "The run could not start.",
        );
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  async function stop() {
    const run = runs.find(active);
    if (!run) return;
    setBusy(true);
    setError("");
    try {
      const stopped = await api.stopRun(run.id);
      if (!mounted.current) return;
      setRuns((previous) =>
        previous.map((r) => (r.id === stopped.id ? stopped : r)),
      );
      setRefresh((n) => n + 1);
    } catch (reason) {
      if (mounted.current)
        setError(
          reason instanceof Error ? reason.message : "The stop request failed.",
        );
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <section className="agent-workspace" aria-label="AI agent workspace">
      <div className="agent-heading">
        <div>
          <span className="eyebrow">CASE AUTOMATION</span>
          <h3>Agent workspace</h3>
          <p>
            Review evidence, prepare a response, and complete permitted case
            actions.
          </p>
        </div>
        <span className="status-pill">
          {running
            ? "Agent active"
            : item.status === "closed"
              ? "Case closed"
              : "Ready to inspect"}
        </span>
      </div>
      {automatic && (
        <p className="automation-notice">
          Mail, approvals, and specialist results trigger processing
          automatically.
        </p>
      )}
      <div className="agent-controls">
        {!automatic && (
          <>
            <label>
              Run preference
              <select
                aria-label="Agent run preference"
                value={mode}
                disabled={running || busy}
                onChange={(e) => setMode(e.target.value as typeof mode)}
              >
                <option value="automatic">Automatic where permitted</option>
                <option value="review_required">Require response review</option>
              </select>
            </label>
            <button
              className="primary-button"
              disabled={
                !loaded ||
                !available ||
                running ||
                busy ||
                item.status === "closed"
              }
              onClick={() => void start()}
            >
              Start agent
            </button>
          </>
        )}
        {latest &&
          (!automatic ||
            ["failed", "stopped"].includes(latest.status) ||
            [
              "reconciliation_required",
              "max_steps",
              "max_model_calls",
              "max_total_tokens",
              "max_seconds",
              "model_configuration_changed",
              "repeated_tool_error",
              "repeated_read_without_progress",
              "interrupted_run_inspect_actions",
              "write_failed",
            ].includes(String((latest.checkpoint as Checkpoint).reason))) &&
          [
            "waiting_for_input",
            "waiting_for_review",
            "failed",
            "stopped",
          ].includes(latest.status) && (
            <button
              className="primary-button"
              disabled={
                !available || running || busy || item.status === "closed"
              }
              onClick={() => void start(true)}
            >
              Resume agent
            </button>
          )}
        <button
          className="secondary-button"
          disabled={
            !running ||
            busy ||
            !!(latest?.checkpoint as Checkpoint)?.stop_requested
          }
          onClick={() => void stop()}
        >
          Stop agent
        </button>
      </div>
      {!automatic && (
        <details className="advanced-controls">
          <summary>
            Advanced controls
            {fault !== "none" ? " · Recovery test selected" : ""}
          </summary>
          <label>
            Recovery test
            <select
              aria-label="Recovery test"
              value={fault}
              disabled={running || busy}
              onChange={(event) => setFault(event.target.value as RunFault)}
            >
              <option value="none">None</option>
              <option value="index_failure">
                Indexing failure after delivery
              </option>
              <option value="lost_send_response">
                Send result unavailable
              </option>
              <option value="unknown_send_status">
                Send result and status unavailable
              </option>
              <option value="lost_task_response">
                New task result unavailable
              </option>
            </select>
          </label>
          <p className="workflow-hint">
            Applies once to the next new run. Resuming does not introduce
            another failure.
          </p>
        </details>
      )}
      {!available && (
        <p className="setup-note">
          {desk
            ? "The agent connection needs attention. Check the backend Azure settings."
            : "The agent connection needs attention. Check Setup & status for details."}
        </p>
      )}
      {error && (
        <p role="alert" className="alert error">
          {error}
        </p>
      )}
      {selected ? (
        <div className="agent-run">
          <label>
            Run history
            <select
              aria-label="Run history"
              value={selected.id}
              onChange={(e) => setChosen(e.target.value)}
            >
              {[...runs].reverse().map((run) => (
                <option key={run.id} value={run.id}>
                  {date(run.created_at)} · {status(run.status)} ·{" "}
                  {run.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          <div className="run-summary" role="status">
            <strong>Agent · {status(selected.status)}</strong>
            <span>
              {checkpoint.stop_requested && active(selected)
                ? "Stop requested; waiting for the current call to finish."
                : automatic && checkpoint.reason === "review_required"
                  ? desk
                    ? "Review the current response in the Case workspace. Approval continues processing automatically."
                    : "Review the current response in Review queue. Approval continues processing automatically."
                  : (reasons[checkpoint.reason ?? ""] ??
                    (desk ? sentence : readable)(
                      checkpoint.reason ?? checkpoint.phase,
                    ))}
            </span>
            <small>
              {checkpoint.steps ?? 0} tool steps · {checkpoint.model_calls ?? 0}{" "}
              model calls ·{" "}
              {(checkpoint.usage?.total_tokens ?? 0).toLocaleString()} reported
              tokens
            </small>
          </div>
          <details>
            <summary>Run details</summary>
            <dl className="run-metadata">
              <dt>Model source</dt>
              <dd>
                {selected.model_configuration.source === "live_azure"
                  ? "Azure Foundry"
                  : "Test provider"}
              </dd>
              <dt>Run</dt>
              <dd>{selected.id}</dd>
              <dt>Configuration</dt>
              <dd>{String(selected.model_configuration.configuration_id)}</dd>
              <dt>Protocol</dt>
              <dd>{String(selected.model_configuration.protocol)}</dd>
              <dt>Tool contract</dt>
              <dd>{String(selected.model_configuration.tool_contract)}</dd>
            </dl>
          </details>
          {!!checkpoint.summary?.pending_work?.length && (
            <div className="pending-work">
              <h4>Pending work</h4>
              {checkpoint.summary.pending_work.map((pending) => (
                <p key={pending.concern_id}>
                  <strong>{readable(pending.owner)}</strong>:{" "}
                  {displayText(pending.resume_requirement || pending.reason)}
                </p>
              ))}
            </div>
          )}
          {desk && onShowTimeline ? (
            <p className="agent-steps-link">
              {(checkpoint.history ?? []).length} recorded steps are shown in
              the agent activity timeline.{" "}
              <button className="text-button" onClick={onShowTimeline}>
                View steps in the Case workspace
              </button>
            </p>
          ) : (
            <ol className="agent-steps" aria-label="Agent tool activity">
              {(checkpoint.history ?? []).map((step) => (
                <li key={step.step}>
                  <span className={`step-marker ${step.status}`}>
                    {step.step}
                  </span>
                  <div>
                    <strong>
                      {toolName ? toolName(step.tool) : readable(step.tool)}
                    </strong>
                    <span>
                      {status(step.status)} · {displayText(step.message)}
                    </span>
                    {step.reference && (
                      <small>
                        {step.reference.kind}: {step.reference.id}
                      </small>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      ) : (
        <p className="empty-agent">
          {automatic
            ? "Waiting for the next mail or case event."
            : "No runs yet. Start the agent to assess the case and take the next permitted action."}
        </p>
      )}
      {selected && (
        <RunRecovery
          key={selected.id}
          item={item}
          run={selected}
          running={running || busy}
          onChanged={() => setRefresh((n) => n + 1)}
        />
      )}
      {/* In the desk, Run summary and recovery is the last section. Case
          inputs and saved records remain in the classic diagnostics view; the
          desk shows them in its response panel and system workspaces. */}
      {!automatic && !desk && (
        <CaseWorkflow
          key={item.id}
          item={item}
          running={running || busy}
          onChanged={() => setRefresh((n) => n + 1)}
        />
      )}
      {!desk && (
        <section
          className="artifact-workspace"
          aria-label="Saved response and records"
        >
          <h3>Saved response and records</h3>
          {!artifacts?.drafts.length && (
            <p className="empty-agent">No response has been prepared.</p>
          )}
          {artifacts?.drafts.map((draft) => (
            <details key={String(draft.id)} open>
              <summary>
                Response v{String(draft.version)} ·{" "}
                {desk
                  ? status(draft.response_type)
                  : readable(draft.response_type)}
              </summary>
              <p>
                <strong>Recipient:</strong> {String(draft.recipient)}
              </p>
              <pre className="response-preview">{displayText(draft.body)}</pre>
            </details>
          ))}
          {!!artifacts?.outbox.length && (
            <div>
              <h4>Outbox</h4>
              {artifacts.outbox.map((entry) => (
                <p key={String(entry.id)}>
                  <strong>{status(entry.status)}</strong>
                  <br />
                  <span className="artifact-reference">
                    {String(entry.delivery_reference)}
                  </span>
                </p>
              ))}
            </div>
          )}
          {!!artifacts?.packages.length && (
            <div>
              <h4>Indexed packages</h4>
              {artifacts.packages.map((entry) => (
                <p key={String(entry.id)}>
                  <a
                    className="text-button"
                    target="_blank"
                    rel="noreferrer"
                    href={`/api/simulations/${item.simulation_id}/cases/${item.id}/packages/${String(entry.id)}/file?${new URLSearchParams({ loan_identifier: item.loan_identifier, client_code: item.client_code })}`}
                  >
                    Open combined response PDF
                  </a>
                  <br />
                  <span className="artifact-reference">{String(entry.id)}</span>
                </p>
              ))}
            </div>
          )}
          {!!artifacts?.notes.length && (
            <div>
              <h4>Final notes</h4>
              {artifacts.notes.map((entry) => (
                <pre className="response-preview" key={String(entry.id)}>
                  {displayText(entry.content)}
                </pre>
              ))}
            </div>
          )}
        </section>
      )}
    </section>
  );
}
