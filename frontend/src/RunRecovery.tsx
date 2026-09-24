import { useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import type { AgentRun, Case, RunSummary } from "./api/client";
import { displayLabel as readable } from "./presentation";

export default function RunRecovery({
  item,
  run,
  running,
  onChanged,
}: {
  item: Case;
  run: AgentRun;
  running: boolean;
  onChanged: () => void;
}) {
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    api
      .runSummary(run.id, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setSummary(data);
          setError("");
        }
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "Summary is unavailable.",
          );
      });
    return () => controller.abort();
  }, [run.id, run.updated_at, item.revision, refresh]);
  async function mutate(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await action();
      if (alive.current) {
        setSummary(null);
        setNotice(
          (result as { blocked?: boolean }).blocked
            ? "The result is still unknown. Resolve the status or evidence problem before continuing."
            : message,
        );
        setRefresh((n) => n + 1);
        onChanged();
      }
    } catch (reason) {
      if (alive.current)
        setError(
          reason instanceof Error ? reason.message : "Recovery check failed.",
        );
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  return (
    <section className="run-recovery" aria-label="Run summary and recovery">
      <div className="recovery-heading">
        <h3>Run summary and recovery</h3>
        <a className="text-button" href={`/api/runs/${run.id}/export`} download>
          Download evidence
        </a>
      </div>
      {error && (
        <p className="alert error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="alert success" role="status">
          {notice}
        </p>
      )}
      {summary?.run_id === run.id && (
        <>
          <dl className="run-metrics">
            <div>
              <dt>Completed actions</dt>
              <dd>{summary.completed_actions}</dd>
            </div>
            <div>
              <dt>Failed / rejected actions</dt>
              <dd>{summary.failed_actions}</dd>
            </div>
            <div>
              <dt>Case interventions to date</dt>
              <dd>{summary.case_interventions_through_run}</dd>
            </div>
            <div>
              <dt>Elapsed, including recovery waits</dt>
              <dd>{summary.elapsed_seconds.toFixed(1)} s</dd>
            </div>
            <div>
              <dt>Model calls / reported tokens</dt>
              <dd>
                {summary.model_calls} /{" "}
                {summary.reported_tokens.toLocaleString()}
              </dd>
            </div>
            <div>
              <dt>Recovered checkpoints</dt>
              <dd>{summary.recovery_count}</dd>
            </div>
          </dl>
          {!summary.usage_complete && (
            <p className="workflow-hint">
              Usage reporting is incomplete for an interrupted or failed model
              call. Reported tokens may undercount that call.
            </p>
          )}
          <p>
            Current case:{" "}
            <strong>{readable(summary.current_case_status)}</strong> ·{" "}
            {summary.pending_concerns} pending concerns
          </p>
          {summary.resumed_from && (
            <p className="workflow-hint">
              Continues run {summary.resumed_from.slice(0, 8)}. Earlier actions
              remain in run history.
            </p>
          )}
          {!!summary.recovery.actions.length && (
            <div className="recovery-actions">
              <h4>
                {summary.recovery.blocked
                  ? "Check uncertain actions before continuing"
                  : "Earlier failed actions"}
              </h4>
              <p className="workflow-hint">
                A failed action with no committed result can be attempted again.
                An applied action is reused after verification. Unknown results
                keep further writes blocked.
              </p>
              {summary.recovery.actions.map((action) => (
                <div className="recovery-action" key={String(action.id)}>
                  <strong>{readable(action.operation)}</strong>
                  <span>
                    {readable(action.status)} · {readable(action.outcome)}
                  </span>
                  {Boolean(action.can_restore_status) && (
                    <button
                      className="secondary-button"
                      disabled={
                        running ||
                        busy ||
                        summary.recovery.revision !== item.revision
                      }
                      onClick={() =>
                        void mutate(
                          () =>
                            api.restoreStatus(
                              item.id,
                              item.revision,
                              String(action.id),
                            ),
                          "Status access restored. Check the persisted result before resuming.",
                        )
                      }
                    >
                      Restore status access
                    </button>
                  )}
                </div>
              ))}
              <button
                className="secondary-button"
                disabled={
                  running ||
                  busy ||
                  !summary.recovery.blocked ||
                  summary.recovery.revision !== item.revision
                }
                onClick={() =>
                  void mutate(
                    () => api.checkRecovery(item.id, item.revision),
                    "Persisted results verified. Resume the agent to complete the remaining work.",
                  )
                }
              >
                Check persisted results
              </button>
            </div>
          )}
          <details>
            <summary>Action receipts for this run</summary>
            <ul className="receipt-list">
              {summary.actions.map((action) => (
                <li key={String(action.id)}>
                  {readable(action.operation)} · {readable(action.status)} ·{" "}
                  {readable(action.outcome)}
                  <small>{String(action.id)}</small>
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  );
}
