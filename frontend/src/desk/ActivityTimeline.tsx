import { useEffect, useRef, useState } from "react";
import type { AgentRun, SystemCase } from "../api/client";
import { displayText } from "../presentation";
import DeskIcon from "./DeskIcon";
import type { IconName } from "./DeskIcon";
import { dateTime, isActive, shortTime, titleCase } from "./deskFormat";
import type { Row } from "./deskFormat";

export type SystemName = "cct" | "ils" | "onbase" | "secure" | "agent";
type Step = {
  step: number;
  tool: string;
  status: string;
  code: string;
  message: string;
  action_id?: string;
  reference?: { id: string; kind: string };
};
const tools: Record<
  string,
  {
    title: string;
    system: string;
    view: SystemName;
    detail: string;
    icon: IconName;
  }
> = {
  observe_case: {
    title: "Inspect correspondence",
    system: "CCT",
    view: "cct",
    detail: "Read the request and current case evidence",
    icon: "mail",
  },
  servicing_read: {
    title: "Retrieve loan record",
    system: "ILS",
    view: "ils",
    detail: "Check loan details and servicing facts",
    icon: "search",
  },
  task_read: {
    title: "Review specialist task",
    system: "ILS",
    view: "ils",
    detail: "Inspect the responsible team's findings",
    icon: "worklist",
  },
  document_read: {
    title: "Retrieve supporting documents",
    system: "OnBase",
    view: "onbase",
    detail: "Check documents and supporting records",
    icon: "file",
  },
  knowledge_search: {
    title: "Check servicing guidance",
    system: "Guidance",
    view: "cct",
    detail: "Find the applicable handling requirements",
    icon: "search",
  },
  apply_plan: {
    title: "Apply routing and aging rules",
    system: "CCT",
    view: "cct",
    detail: "Record work type, concerns and next steps",
    icon: "worklist",
  },
  prepare_response: {
    title: "Draft response",
    system: "AI agent",
    view: "secure",
    detail: "Prepare a response supported by evidence",
    icon: "edit",
  },
  send_response: {
    title: "Deliver approved response",
    system: "Secure mail",
    view: "secure",
    detail: "Save the delivery and attachment receipt",
    icon: "send",
  },
  index_response: {
    title: "Archive correspondence",
    system: "OnBase",
    view: "onbase",
    detail: "Index the response and sent documents",
    icon: "file",
  },
  record_final_note: {
    title: "Record servicing note",
    system: "ILS",
    view: "ils",
    detail: "Retain the outcome in the servicing history",
    icon: "edit",
  },
  close_case: {
    title: "Complete correspondence",
    system: "CCT",
    view: "cct",
    detail: "Verify completion and close the case",
    icon: "check",
  },
  create_task: {
    title: "Create specialist task",
    system: "ILS",
    view: "ils",
    detail: "Assign the required specialist work",
    icon: "cases",
  },
  update_name: {
    title: "Update legal name",
    system: "ILS",
    view: "ils",
    detail: "Apply the supported servicing update",
    icon: "user",
  },
  request_handoff: {
    title: "Request specialist handoff",
    system: "CCT",
    view: "cct",
    detail: "Refer unresolved work to its responsible team",
    icon: "arrow",
  },
  finish_run: {
    title: "Verify the case outcome",
    system: "AI agent",
    view: "cct",
    detail: "Check saved results and remaining work",
    icon: "shield",
  },
};
export const systemForTool = (name: string): SystemName =>
  tools[name]?.view ?? "agent";
/** Readable title for an agent tool name, shared with reused system screens. */
export const toolTitle = (name: string) =>
  tools[name]?.title ?? titleCase(name);

// Result lines that add nothing beyond the step title; still shown under details.
const genericResults = new Set([
  "",
  "Operation completed.",
  "Completed",
  "Completed.",
  "ok",
]);

/** One-line description of where the latest run stands and what comes next. */
export function runOutcome(data: SystemCase, run?: AgentRun) {
  const running = isActive(run);
  const label = running
    ? "Agent is processing"
    : run?.status === "waiting_for_review"
      ? "Awaiting human review"
      : data.case.status === "closed"
        ? "Correspondence complete"
        : data.case.status === "transferred"
          ? "Specialist handoff confirmed"
          : run?.status === "stopped"
            ? "Processing stopped"
            : run?.status === "failed"
              ? "Processing needs attention"
              : run
                ? "Awaiting the next input"
                : "Waiting for processing";
  const next = running
    ? "The agent is checking evidence and saved results."
    : run?.status === "waiting_for_review"
      ? "Review the current draft and approve or return it."
      : data.case.status === "closed"
        ? "Delivery, document package and servicing note are recorded."
        : data.case.status === "waiting_for_borrower"
          ? "The borrower replies in the sender mailbox."
          : data.case.status === "waiting_on_department"
            ? "Review the specialist task in ILS."
            : run
              ? "Saved work remains available for inspection."
              : "Incoming mail starts processing automatically.";
  const short = running
    ? "Agent working"
    : run?.status === "waiting_for_review"
      ? "Review draft"
      : data.case.status === "closed"
        ? "Complete"
        : data.case.status === "transferred"
          ? "With specialist"
          : data.case.status === "waiting_for_borrower"
            ? "Waiting on borrower"
            : data.case.status === "waiting_on_department"
              ? "Specialist task"
              : run?.status === "failed" || run?.status === "stopped"
                ? "Check run"
                : "Awaiting input";
  const tone = running
    ? "blue"
    : run?.status === "waiting_for_review" ||
        run?.status === "failed" ||
        run?.status === "stopped"
      ? "amber"
      : data.case.status === "closed" || data.case.status === "transferred"
        ? "good"
        : "neutral";
  return { label, next, short, tone, running };
}

export default function ActivityTimeline({
  data,
  onSystem,
}: {
  data: SystemCase;
  onSystem: (system: SystemName) => void;
}) {
  const [chosenRun, setChosenRun] = useState<string | null>(null);
  const [replay, setReplay] = useState<number | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const run =
    data.runs.find((item) => item.id === chosenRun) ?? data.runs.at(-1);
  const steps = (run?.checkpoint.history ?? []) as Step[];
  const running = isActive(run);
  // Steps present when the run was first shown do not flash; later ones do.
  const seen = useRef<{ run?: string; count: number }>({ count: -1 });
  if (seen.current.run !== run?.id)
    seen.current = { run: run?.id, count: steps.length };
  useEffect(() => {
    setReplay(null);
  }, [run?.id]);
  useEffect(() => {
    if (replay === null) return;
    const timer = setTimeout(
      () => setReplay(replay >= steps.length ? null : replay + 1),
      1100,
    );
    return () => clearTimeout(timer);
  }, [replay, steps.length]);
  useEffect(() => {
    const pane = end.current?.parentElement;
    // Keep the newest step in view while the agent is working.
    if (running && pane)
      pane.scrollTo({ top: pane.scrollHeight, behavior: "smooth" });
  }, [running, steps.length, run?.checkpoint.current_tool]);
  const visible = replay === null ? steps : steps.slice(0, replay);
  const outcome = runOutcome(data, run);
  let previousTime = "";
  return (
    <section
      className="desk-card activity-card"
      aria-label="Agent activity timeline"
    >
      <header className="desk-card-heading">
        <h2>Agent activity</h2>
        {(replay !== null || running || !run) && (
          <span
            className={`desk-badge ${running ? "good live" : "neutral"}`}
            aria-live="polite"
          >
            <i />
            {replay !== null
              ? "Replay"
              : running
                ? `Agent working · step ${steps.length + 1}`
                : "Ready"}
          </span>
        )}
        <div className="activity-actions">
          <button
            className="desk-button small"
            disabled={!steps.length || running}
            onClick={() => setReplay(replay === null ? 0 : null)}
          >
            <DeskIcon name={replay === null ? "follow" : "pause"} size={14} />
            {replay === null ? "Replay" : "Stop replay"}
          </button>
        </div>
      </header>
      {replay === null && (
        <div
          className={`activity-outcome ${outcome.tone}`}
          role="status"
          aria-label="Run outcome"
        >
          {running ? (
            <i className="desk-spinner" />
          ) : (
            <DeskIcon
              name={data.case.status === "closed" ? "check" : "clock"}
              size={16}
            />
          )}
          <span>
            <strong>{outcome.label}.</strong> Next: {outcome.next}
          </span>
        </div>
      )}
      {data.runs.length > 1 && (
        <div className="activity-run-select">
          <label>
            Run history
            <select
              aria-label="Activity run history"
              value={run?.id ?? ""}
              onChange={(e) => {
                setChosenRun(e.target.value);
                setReplay(null);
              }}
            >
              {[...data.runs].reverse().map((item, i) => (
                <option value={item.id} key={item.id}>
                  {i === 0 ? "Latest · " : ""}
                  {shortTime(item.created_at)} · {titleCase(item.status)}
                </option>
              ))}
            </select>
          </label>
          {chosenRun && chosenRun !== data.runs.at(-1)?.id && (
            <button
              className="desk-text-button"
              onClick={() => setChosenRun(null)}
            >
              Follow latest
            </button>
          )}
        </div>
      )}
      <div className="activity-scroll">
        <ol className="desk-timeline">
          {visible.map((step, index) => {
            const info = tools[step.tool] ?? {
              title: titleCase(step.tool),
              system: "AI agent",
              view: "agent" as const,
              detail: "Inspect the recorded action result",
              icon: "follow" as const,
            };
            const event = data.events.find(
              (e) =>
                e.run_id === run?.id &&
                e.kind === "agent.tool_result" &&
                (e.payload as Row).step === step.step,
            );
            const planned = data.events.find(
              (e) =>
                e.run_id === run?.id &&
                e.kind === "agent.tool_planned" &&
                (e.payload as Row).action_id === step.action_id,
            );
            const context = ((planned?.payload as Row)?.evidence_versions ??
              {}) as Record<string, number>;
            const succeeded = ["ok", "simulated_complete"].includes(
              step.status,
            );
            const result = displayText(step.message);
            const time = event ? shortTime(event.created_at) : "";
            const showTime = !!time && time !== previousTime;
            if (time) previousTime = time;
            const receipt = succeeded
              ? step.reference
                ? "Confirmed"
                : "Checked"
              : step.status === "awaiting_review"
                ? "Review"
                : "Attention";
            return (
              <li
                key={`${run?.id}-${step.step}`}
                className={`${succeeded ? "done" : "attention"} ${replay === null && index >= seen.current.count ? "fresh" : ""}`}
              >
                <span className="timeline-dot" />
                <span className="timeline-icon">
                  <DeskIcon name={info.icon} size={17} />
                </span>
                <div className="timeline-content">
                  <div className="timeline-step-title">
                    <h3>
                      {index + 1}. {info.title}
                    </h3>
                    <button
                      className={`action-receipt ${succeeded ? "" : "attention"}`}
                      onClick={() => onSystem(info.view)}
                      aria-label={`Inspect result for ${info.title}`}
                      title={`Open ${info.system}`}
                    >
                      {succeeded ? (
                        <DeskIcon name="check" size={12} />
                      ) : (
                        <DeskIcon name="clock" size={12} />
                      )}
                      {receipt}
                      {step.reference && (
                        <span>
                          · {step.reference.id.slice(0, 8).toUpperCase()}
                        </span>
                      )}
                    </button>
                    {showTime && <time>{time}</time>}
                  </div>
                  <p className="timeline-system">
                    <button onClick={() => onSystem(info.view)}>
                      {info.system}
                    </button>
                    <span />
                    {info.detail}
                  </p>
                  {!genericResults.has(result) && (
                    <p className="timeline-result">{result}</p>
                  )}
                  <details className="timeline-evidence">
                    <summary>
                      {Object.keys(context).length
                        ? `Evidence in context (${Object.keys(context).length})`
                        : "Action details"}
                    </summary>
                    <div>
                      {Object.entries(context).map(([id, version]) => {
                        const evidence = data.evidence.find((e) => e.id === id);
                        const task = data.tasks.find((t) => t.id === id);
                        return evidence &&
                          evidence.version === version &&
                          (evidence.details as Row).kind !== "record" &&
                          (evidence.details as Row).availability ===
                            "available" ? (
                          <a
                            key={id}
                            href={`/api/cases/${data.case.id}/evidence/${id}/file`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {titleCase(evidence.title)} · v{version}
                          </a>
                        ) : (
                          <span key={id}>
                            {evidence
                              ? titleCase(evidence.title)
                              : task
                                ? titleCase(task.task_type)
                                : `Record ${id.slice(0, 8)}`}{" "}
                            · v{version}
                          </span>
                        );
                      })}
                      <span>
                        Result: {titleCase(step.code)}
                        {genericResults.has(result) && result
                          ? ` · ${result}`
                          : ""}
                      </span>
                      {event && (
                        <span>Recorded {dateTime(event.created_at, true)}</span>
                      )}
                      {step.action_id && (
                        <span>Action reference: {step.action_id}</span>
                      )}
                    </div>
                  </details>
                </div>
              </li>
            );
          })}
          {running && replay === null && (
            <li className="current fresh">
              <span className="timeline-dot" />
              <span className="timeline-icon">
                <DeskIcon name="follow" size={17} />
              </span>
              <div className="timeline-content">
                <div className="timeline-step-title">
                  <h3>
                    {steps.length + 1}.{" "}
                    {run?.checkpoint.phase === "executing_tool"
                      ? (tools[String(run.checkpoint.current_tool)]?.title ??
                        "Performing case action")
                      : "Considering the next action"}
                  </h3>
                  <span className="desk-badge blue">
                    <i className="desk-spinner" /> In progress
                  </span>
                </div>
                <p className="timeline-result">
                  The agent is checking the current evidence and saved results.
                </p>
              </div>
            </li>
          )}
        </ol>
        {!run && (
          <p className="desk-panel-note">
            Incoming mail starts processing automatically.
          </p>
        )}
        <div ref={end} />
      </div>
      <footer className="activity-footer">
        <button className="desk-text-button" onClick={() => onSystem("agent")}>
          Run details and recovery <DeskIcon name="chevron" size={12} />
        </button>
      </footer>
    </section>
  );
}
