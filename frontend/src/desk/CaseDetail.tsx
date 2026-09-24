import { useCallback, useState } from "react";
import { api } from "../api/client";
import type { Configuration, SystemCase, ThreadDetail } from "../api/client";
import AgentWorkspace from "../AgentWorkspace";
import { CctView, IlsView, OnbaseView, SecureMailView } from "../SystemViews";
import {
  clientName,
  displayText,
  displayValue,
} from "../presentation";
import ActivityTimeline, { toolTitle } from "./ActivityTimeline";
import type { SystemName } from "./ActivityTimeline";
import ResponsePanel from "./ResponsePanel";
import DeskIcon from "./DeskIcon";
import type { IconName } from "./DeskIcon";
import {
  ageTone,
  caseStatus,
  dateTime,
  fact,
  shortDateTime,
  titleCase,
} from "./deskFormat";
import type { Row } from "./deskFormat";
import { useDeskData } from "./useDeskData";

type Tab = "workspace" | "systems";
const systems: { id: SystemName; title: string; icon: IconName }[] = [
  { id: "cct", title: "CCT", icon: "cases" },
  { id: "ils", title: "ILS", icon: "loan" },
  { id: "onbase", title: "OnBase", icon: "file" },
  { id: "secure", title: "Secure mail", icon: "send" },
  { id: "agent", title: "Agent activity", icon: "follow" },
];

export default function CaseDetail({
  id,
  config,
  onBack,
}: {
  id: string;
  config: Configuration | null;
  onBack: () => void;
}) {
  const [tab, setTab] = useState<Tab>("workspace");
  const [system, setSystem] = useState<SystemName>("cct");
  const [pane, setPane] = useState<"correspondence" | "activity">(
    "correspondence",
  );
  const [refresh, setRefresh] = useState(0);
  const refreshAll = useCallback(() => setRefresh((value) => value + 1), []);
  const read = useCallback(
    async (signal: AbortSignal) => {
      const [data, assessment, workflow] = await Promise.all([
        api.systemCase(id, signal),
        api.assessment(id, signal),
        api.workflow(id, signal),
      ]);
      const thread = data.thread
        ? await api.mailThread(data.thread.id, signal)
        : null;
      return { data, assessment, workflow, thread };
    },
    [id, refresh],
  );
  const state = useDeskData(read, 1500, true);
  function openSystem(value: SystemName) {
    setSystem(value);
    setTab("systems");
  }
  if (!state.value)
    return state.error ? (
      <div className="desk-loading">
        <DeskIcon name="cases" size={28} />
        <h2>Case unavailable</h2>
        <p>{state.error}</p>
        <button className="desk-button" onClick={onBack}>
          Back to dashboard
        </button>
      </div>
    ) : (
      <section
        className="desk-case fit"
        aria-label="Opening case"
        aria-busy="true"
      >
        <div className="case-skeleton-header">
          <span className="desk-skeleton mid" />
          <span className="desk-skeleton narrow" />
        </div>
        <div className="case-workspace-grid case-skeleton">
          {[0, 1, 2].map((column) => (
            <div className="desk-card" key={column}>
              <span className="desk-skeleton wide" />
              <span className="desk-skeleton mid" />
              <span className="desk-skeleton wide" />
              <span className="desk-skeleton narrow" />
            </div>
          ))}
        </div>
        <span className="desk-sr-only">Opening case…</span>
      </section>
    );
  const { data, assessment, workflow, thread } = state.value;
  const item = data.case;
  const age = assessment.routing.aging.workdays ?? null;
  const latestDraft = workflow.drafts.at(-1);
  const reviewing =
    !!latestDraft &&
    latestDraft.current &&
    !latestDraft.sent &&
    latestDraft.review_required &&
    !latestDraft.approved;
  const restrictions = [
    ...new Set([
      ...assessment.routing.restrictions,
      ...((data.loan.context as Row).communication_restriction &&
      (data.loan.context as Row).communication_restriction !== "none"
        ? [String((data.loan.context as Row).communication_restriction)]
        : []),
    ]),
  ];
  const route = assessment.routing.route ?? "Awaiting assessment";
  const routeDetail = titleCase(assessment.routing.assessment);
  return (
    <section
      className={`desk-case ${tab === "workspace" ? "fit" : ""}`}
      aria-label="Detailed case workspace"
    >
      <header className="desk-case-header">
        <button
          className="case-back"
          aria-label="Case dashboard"
          title="Back to case dashboard"
          onClick={onBack}
        >
          <DeskIcon
            name="arrow"
            size={18}
            style={{ transform: "scaleX(-1)" }}
          />
        </button>
        <h1>{item.ccid}</h1>
        <span
          className={`desk-badge case-status ${reviewing ? "amber" : item.status === "closed" ? "good" : "neutral"}`}
        >
          {reviewing ? "Under review" : caseStatus(item.status)}
        </span>
        <p className="case-identity">
          <span>{item.borrower_display_name}</span>
          <span>Loan {item.loan_identifier}</span>
          <span>{clientName(item.client_code)}</span>
        </p>
      </header>
      <div className="case-tabs-row">
        <nav className="case-tabs" aria-label="Case sections">
          {(
            [
              ["workspace", "Case workspace"],
              ["systems", "System workspaces"],
            ] as [Tab, string][]
          ).map(([value, label]) => (
            <button
              key={value}
              className={tab === value ? "selected" : ""}
              aria-current={tab === value ? "page" : undefined}
              onClick={() => setTab(value)}
            >
              {label}
            </button>
          ))}
        </nav>
        <dl className="case-header-facts">
          <div
            className={`case-age ${ageTone(age)}`}
            title="Eastern Monday–Friday workdays from original receipt"
          >
            <dt>Age</dt>
            <dd>
              {age === null ? (
                "Needs review"
              ) : (
                <>
                  {age} of 20
                  <span className="case-age-track" aria-hidden="true">
                    <i
                      style={{
                        width: `${Math.max(4, Math.min(100, age * 5))}%`,
                      }}
                    />
                  </span>
                </>
              )}
            </dd>
          </div>
          <div
            title={
              routeDetail.toLowerCase() !== route.toLowerCase()
                ? `${route} · ${routeDetail}`
                : route
            }
          >
            <dt>Route</dt>
            <dd>
              {route}
              {routeDetail.toLowerCase() !== route.toLowerCase() &&
                assessment.routing.assessment && (
                  <small> · {routeDetail}</small>
                )}
            </dd>
          </div>
          <div>
            <dt>Restrictions</dt>
            <dd>
              {restrictions.length
                ? restrictions.map(titleCase).join(", ")
                : "None"}
            </dd>
          </div>
          <div title={`${dateTime(item.original_received_at)} ET`}>
            <dt>Original receipt</dt>
            <dd>{shortDateTime(item.original_received_at)}</dd>
          </div>
        </dl>
      </div>
      {state.error && (
        <p className="desk-alert" role="alert">
          Connection interrupted: {state.error}. Showing the last received
          records.
        </p>
      )}
      {tab === "workspace" && (
        <div className="case-workspace-grid" data-pane={pane}>
          <div
            className="case-pane-switch"
            role="tablist"
            aria-label="Left column"
          >
            {(
              [
                ["correspondence", "Correspondence"],
                ["activity", "Agent activity"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                role="tab"
                aria-selected={pane === value}
                className={pane === value ? "selected" : ""}
                onClick={() => setPane(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="case-column case-source-column">
            <Correspondence data={data} thread={thread} />
            <details className="desk-card case-context-more">
              <summary>
                More details
                <span className="desk-muted">
                  Property, case type, owner and channel
                </span>
              </summary>
              <CaseContextList data={data} compact />
            </details>
          </div>
          <div className="case-column case-activity-column">
            <ActivityTimeline
              data={data}
              onSystem={openSystem}
            />
          </div>
          <div className="case-column case-response-column">
            <ResponsePanel
              data={data}
              assessment={assessment}
              workflow={workflow}
              onChanged={refreshAll}
            />
          </div>
        </div>
      )}
      {tab === "systems" && (
        <div className="desk-systems">
          <nav aria-label="System workspaces" className="system-tabs">
            {systems.map((entry) => (
              <button
                key={entry.id}
                className={system === entry.id ? "selected" : ""}
                onClick={() => {
                  setSystem(entry.id);
                }}
              >
                <DeskIcon name={entry.icon} />
                {entry.title}
              </button>
            ))}
          </nav>
          {system === "cct" && (
            <CctView
              data={data}
              assessment={assessment}
              refresh={refreshAll}
              onOpenSystem={setSystem}
            />
          )}
          {system === "ils" && (
            <IlsView data={data} refresh={refreshAll} onOpenSystem={setSystem} />
          )}
          {system === "onbase" && (
            <OnbaseView
              data={data}
              assessment={assessment}
              onOpenSystem={setSystem}
            />
          )}
          {system === "secure" && <SecureMailView data={data} />}
          {system === "agent" && (
            <div className="desk-card desk-agent-details">
              <AgentWorkspace
                item={item}
                available={!!config?.agent_available}
                onCaseUpdated={refreshAll}
                automatic={!!data.thread}
                desk
                toolName={toolTitle}
                onShowTimeline={() => setTab("workspace")}
              />
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function Correspondence({
  data,
  thread,
}: {
  data: SystemCase;
  thread: ThreadDetail | null;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const original = thread?.messages[0];
  const message =
    thread?.messages.find((entry) => entry.id === selected) ?? original;
  const context = data.loan.context as Row;
  const attachments = message
    ? message.attachments
        .map((a) => data.evidence.find((e) => e.id === a.evidence_id))
        .filter((e) => !!e)
    : data.evidence.filter(
        (e) =>
          (e.details as Row).kind !== "record" &&
          (e.details as Row).availability === "available",
      );
  const from =
    message?.sender ??
    fact(context.borrower_email ?? context.authorized_recipient);
  const to = message?.recipient ?? "Correspondence Services";
  const received = message?.created_at ?? data.case.original_received_at;
  return (
    <section
      className="desk-card correspondence-card"
      aria-label="Borrower correspondence"
    >
      <header className="desk-card-heading">
        <h2>Borrower correspondence</h2>
        <DeskIcon name="mail" size={17} />
      </header>
      <div className="correspondence-content">
        {!!thread && thread.messages.length > 1 && (
          <select
            className="correspondence-select"
            aria-label="Correspondence message"
            value={message?.id}
            onChange={(e) => setSelected(e.target.value)}
          >
            {thread.messages.map((entry, i) => (
              <option value={entry.id} key={entry.id}>
                {i === 0 ? "Original request" : `Reply ${i}`} ·{" "}
                {shortDateTime(entry.created_at)}
              </option>
            ))}
          </select>
        )}
        <div className="correspondence-envelope">
          <h3>{message?.subject ?? data.case.subject}</h3>
          <dl>
            <div>
              <dt>From</dt>
              <dd title={from}>{from}</dd>
            </div>
            <div>
              <dt>To</dt>
              <dd title={to}>{to}</dd>
            </div>
            <div>
              <dt>{message ? "Email received" : "Received"}</dt>
              <dd
                title={`${dateTime(received)} ${dateTime(received, true)} ET`}
              >
                {shortDateTime(received)} ET
              </dd>
            </div>
          </dl>
        </div>
        <div className="borrower-message">
          {displayText(message?.body ?? data.case.correspondence_text)}
        </div>
        <div className="source-attachments">
          {attachments.length ? (
            <h3>Attachments ({attachments.length})</h3>
          ) : (
            <p className="desk-muted">No attachments</p>
          )}
          {attachments.map((e) => {
            const href = `/api/cases/${data.case.id}/evidence/${e.id}/file`;
            return (
              <div className="desk-file-chip" key={String(e.id)}>
                <DeskIcon name="file" size={16} />
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  title={`Preview ${displayValue(e.title)}`}
                >
                  {displayValue(e.title)}
                  <small>PDF · v{String(e.version)}</small>
                </a>
                <a
                  className="desk-file-download"
                  href={href}
                  download
                  aria-label={`Download ${displayValue(e.title)}`}
                  title="Download"
                >
                  <DeskIcon name="download" size={15} />
                </a>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function contextValues(data: SystemCase, compact = false) {
  const context = data.loan.context as Row;
  const values: { icon: IconName; name: string; value: string }[] = [
    ...(compact
      ? []
      : [
          {
            icon: "user" as const,
            name: "Borrower",
            value: data.case.borrower_display_name,
          },
          {
            icon: "loan" as const,
            name: "Loan number",
            value: data.case.loan_identifier,
          },
        ]),
    ...(context.property_address
      ? [
          {
            icon: "home" as const,
            name: "Property",
            value: String(context.property_address),
          },
        ]
      : []),
    ...(compact
      ? []
      : [
          {
            icon: "client" as const,
            name: "Client",
            value: clientName(data.case.client_code),
          },
        ]),
    { icon: "file", name: "Case type", value: titleCase(data.case.family) },
    { icon: "user", name: "Owner", value: displayValue(data.case.owner) },
    {
      icon: "mail",
      name: "Received channel",
      value: data.thread ? "Email (Mailbox)" : "Correspondence intake",
    },
  ];
  return values;
}

function CaseContextList({
  data,
  compact = false,
}: {
  data: SystemCase;
  compact?: boolean;
}) {
  return (
    <dl className="case-context-list">
      {contextValues(data, compact).map((entry) => (
        <div key={entry.name}>
          <DeskIcon name={entry.icon} size={16} />
          <dt>{entry.name}</dt>
          <dd>{entry.value}</dd>
        </div>
      ))}
    </dl>
  );
}
