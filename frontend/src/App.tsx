import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "./api/client";
import type { Case, CaseEvent, Configuration, Scenario } from "./api/client";
import CaseResources from "./CaseResources";
import CaseAssessment from "./CaseAssessment";
import AgentWorkspace from "./AgentWorkspace";
import { REVIEWER } from "./auth/reviewer";
import {
  clientName,
  displayLabel,
  displayText,
  displayValue,
} from "./presentation";

type IconName =
  | "mail"
  | "grid"
  | "plus"
  | "arrow"
  | "check"
  | "clock"
  | "refresh"
  | "settings"
  | "close";
const paths: Record<IconName, string> = {
  mail: "M3 5h18v14H3z M3 5l9 7 9-7",
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  plus: "M12 5v14 M5 12h14",
  arrow: "M5 12h14 M13 6l6 6l-6 6",
  check: "M5 12l4 4 10-10",
  clock: "M12 7v5l3 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  refresh: "M20 7v5h-5 M20 12a8 8 0 1 0-2 6 M20 7l-3-3",
  settings: "M4 7h16 M4 17h16 M8 4v6 M16 14v6",
  close: "M6 6l12 12 M6 18L18 6",
};
function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
const labels: Record<string, string> = {
  document_request: "Document request",
  profile_change: "Profile change",
  tax_payment: "Tax payment",
  credit_reporting: "Credit reporting",
  loan_servicing: "Loan servicing",
  queued: "Queued",
  under_review: "Under review",
};
function label(value: string) {
  return labels[value] ?? displayLabel(value);
}
function readableActor(value: string) {
  return displayLabel(value);
}
function eastern(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));
}
function errorMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}

const PAGE_SIZE = 10;
const workflowEvents: Record<string, string> = {
  "input.received": "New case input received",
  "response.reviewed": "Response reviewed",
  "response.edited": "Response revised",
  "handoff.acknowledged": "Specialist receipt acknowledged",
  "recovery.checked": "Persisted results checked",
  "recovery.status_restored": "Status access restored",
};
function workflowDetail(event: CaseEvent) {
  if (event.kind === "recovery.checked")
    return "Saved action receipts were checked against their results.";
  if (event.kind === "recovery.status_restored")
    return "The saved result is available for verification before resuming.";
  if (event.kind === "input.received") return displayText(event.payload.text);
  if (event.kind === "response.reviewed")
    return `Version ${event.payload.version}: ${event.payload.decision} · ${event.payload.note}`;
  if (event.kind === "response.edited")
    return `Version ${event.payload.version} requires a new review.`;
  return `${event.payload.route} · ${displayLabel(event.payload.owner)} · transferred`;
}

export default function App({ onSignOut }: { onSignOut: () => void }) {
  const [configuration, setConfiguration] = useState<Configuration | null>(
    null,
  );
  const [rows, setCases] = useState<Case[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    localStorage.getItem("correspondence.selectedCase"),
  );
  const [selected, setSelected] = useState<Case | null>(null);
  const [events, setEvents] = useState<CaseEvent[]>([]);
  const [owner, setOwner] = useState("");
  const [revision, setRefreshRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] =
    useState<Scenario["scenario_id"]>("DEMO-02");
  const [variant, setVariant] = useState<Scenario["variants"][number]>("base");
  const dialog = useRef<HTMLDialogElement>(null);
  const intakeDialog = useRef<HTMLDialogElement>(null);
  const newCaseButton = useRef<HTMLButtonElement>(null);
  const settingsButton = useRef<HTMLButtonElement>(null);
  const selectedIdentity = useRef(selectedId);
  selectedIdentity.current = selectedId;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    Promise.all([
      api.cases(page * PAGE_SIZE, PAGE_SIZE, controller.signal),
      api.configuration(controller.signal),
      api.scenarios(controller.signal),
    ])
      .then(([list, config, scenarioRows]) => {
        setCases(list.items);
        setTotal(list.total);
        setConfiguration(config);
        setScenarios(scenarioRows);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(errorMessage(reason));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [page, revision]);

  useEffect(() => {
    const controller = new AbortController();
    setSelected((previous) => (previous?.id === selectedId ? previous : null));
    setEvents([]);
    if (selectedId) {
      Promise.all([
        api.case(selectedId, controller.signal),
        api.events(selectedId, controller.signal),
      ])
        .then(([item, history]) => {
          setSelected(item);
          setOwner(displayValue(item.owner));
          setEvents(history.items);
        })
        .catch((reason: unknown) => {
          if (!controller.signal.aborted) setError(errorMessage(reason));
        });
    }
    return () => controller.abort();
  }, [selectedId, revision]);

  useEffect(() => {
    if (selectedId)
      localStorage.setItem("correspondence.selectedCase", selectedId);
    else localStorage.removeItem("correspondence.selectedCase");
  }, [selectedId]);

  const updateFromAgent = useCallback((item: Case) => {
    if (selectedIdentity.current !== item.id) return;
    setSelected((previous) =>
      previous?.id === item.id && item.revision >= previous.revision
        ? item
        : previous,
    );
    setCases((previous) =>
      previous.map((row) =>
        row.id === item.id && item.revision >= row.revision ? item : row,
      ),
    );
    api
      .events(item.id)
      .then((history) => {
        if (selectedIdentity.current === item.id) setEvents(history.items);
      })
      .catch(() => undefined);
  }, []);

  function refreshWorkspace() {
    setError("");
    setNotice("");
    setRefreshRevision((value) => value + 1);
  }

  async function createCase() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const item = await api.loadScenario(scenarioId, variant);
      setPage(0);
      setSelectedId(item.id);
      setRefreshRevision((value) => value + 1);
      setNotice("Case created and ready for review.");
      intakeDialog.current?.close();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  async function saveCase(event?: FormEvent, status?: Case["status"]) {
    event?.preventDefault();
    if (!selected) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const updated = await api.update(selected.id, {
        mutation_id: crypto.randomUUID(),
        expected_revision: selected.revision,
        ...(status ? { status } : { owner: owner.trim() }),
      });
      if (selectedIdentity.current === updated.id) {
        setSelected(updated);
        setOwner(displayValue(updated.owner));
      }
      setCases((previous) =>
        previous.map((row) => (row.id === updated.id ? updated : row)),
      );
      setRefreshRevision((value) => value + 1);
      setNotice(
        "Case updated. The change is recorded in its activity history.",
      );
    } catch (reason) {
      setError(errorMessage(reason));
      if (reason instanceof ApiError && reason.code === "stale_revision")
        setRefreshRevision((value) => value + 1);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="Correspondence home">
          <span className="brand-mark">
            <Icon name="mail" size={23} />
          </span>
          <span>
            Correspondence
            <span className="brand-caption">SERVICING WORKSPACE</span>
          </span>
        </a>
        <div className="nav-label">WORKSPACE</div>
        <div className="nav-item active">
          <Icon name="grid" />
          <span>Worklist</span>
          <span className="nav-count">{total}</span>
        </div>
        <button
          ref={settingsButton}
          className="nav-item"
          onClick={() => dialog.current?.showModal()}
        >
          <Icon name="settings" />
          Setup & status
        </button>
      </aside>
      <div className="main-layout">
        <header className="topbar">
          <div>
            Workspace <span className="slash">/</span> <strong>Worklist</strong>
          </div>
          <div className="topbar-right">
            <Icon name="clock" size={15} />
            Mon–Fri · Eastern time
            <span>
              {REVIEWER.name} · {REVIEWER.role}
            </span>
            <button className="desk-sign-out" onClick={onSignOut}>
              Sign out
            </button>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">BORROWER CORRESPONDENCE</div>
              <h1>Correspondence</h1>
              <p>
                Review incoming requests and keep every change connected to its
                case.
              </p>
            </div>
            <button
              className="primary-button"
              ref={newCaseButton}
              disabled={busy || !scenarios.length}
              onClick={() => intakeDialog.current?.showModal()}
            >
              <Icon name="plus" />
              New case
            </button>
          </div>
          {error && (
            <div className="alert error" role="alert">
              {error}
              <button onClick={refreshWorkspace}>Retry</button>
            </div>
          )}
          {notice && (
            <div className="alert success" role="status">
              {notice}
            </div>
          )}
          <div className="summary-row">
            <div>
              <span>Total cases</span>
              <strong>{total.toString().padStart(2, "0")}</strong>
            </div>
            <div>
              <span>Worklist order</span>
              <strong className="summary-word">Oldest received first</strong>
            </div>
            <div>
              <span>Agent connection</span>
              <strong className="summary-word">
                {configuration?.model_connection_verified
                  ? "Verified"
                  : configuration?.azure_configuration_complete
                    ? "Configured"
                    : "Setup pending"}
                <span className="small-dot" />
              </strong>
            </div>
          </div>
          <section
            className="worklist-panel"
            aria-label="Correspondence worklist"
          >
            <div className="panel-heading">
              <h2>
                Worklist <span>{total}</span>
              </h2>
              <div className="panel-tools">
                <span>Oldest received first · Eastern time</span>
                <button
                  className="icon-button"
                  aria-label="Refresh worklist"
                  disabled={loading}
                  onClick={refreshWorkspace}
                >
                  <Icon name="refresh" />
                </button>
              </div>
            </div>
            {loading && rows.length === 0 ? (
              <div className="empty-state" role="status">
                Loading your workspace…
              </div>
            ) : rows.length === 0 ? (
              <div className="empty-state">
                <span className="empty-icon">
                  <Icon name="mail" size={29} />
                </span>
                <h3>Your worklist is ready.</h3>
                <p>Select New case to add a request and begin reviewing it.</p>
              </div>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Request / correspondence</th>
                      <th>Borrower / loan</th>
                      <th>Received</th>
                      <th>Owner</th>
                      <th>Status</th>
                      <th>
                        <span className="sr-only">Open</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((item) => (
                      <tr
                        key={item.id}
                        className={selectedId === item.id ? "selected-row" : ""}
                      >
                        <td>
                          <button
                            className="case-link"
                            onClick={() => setSelectedId(item.id)}
                          >
                            {item.subject}
                          </button>
                          <span className="cell-subtitle">
                            {item.ccid} <span>·</span> {label(item.family)}
                          </span>
                        </td>
                        <td>
                          <strong className="cell-name">
                            {item.borrower_display_name}
                          </strong>
                          <span className="cell-subtitle mono">
                            {item.loan_identifier}
                          </span>
                        </td>
                        <td className="date-cell">
                          {eastern(item.original_received_at)}
                        </td>
                        <td>{displayValue(item.owner)}</td>
                        <td>
                          <span className={`status-pill ${item.status}`}>
                            {label(item.status)}
                          </span>
                        </td>
                        <td>
                          <button
                            className="icon-button"
                            aria-label={`Open ${item.ccid}`}
                            onClick={() => setSelectedId(item.id)}
                          >
                            <Icon name="arrow" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="table-footer">
              <span>
                {total
                  ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} of ${total} cases`
                  : "0 cases"}
                <span className="footer-divider">|</span>Changes saved
              </span>
              {total > PAGE_SIZE && (
                <div className="pagination">
                  <button
                    disabled={page === 0 || loading}
                    onClick={() => setPage((value) => value - 1)}
                  >
                    Previous
                  </button>
                  <button
                    disabled={(page + 1) * PAGE_SIZE >= total || loading}
                    onClick={() => setPage((value) => value + 1)}
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          </section>
          {selectedId && (
            <section className="case-panel" aria-label="Selected case">
              <div className="panel-heading">
                <h2>Case details</h2>
                <button
                  className="icon-button"
                  aria-label="Close case details"
                  onClick={() => setSelectedId(null)}
                >
                  <Icon name="close" />
                </button>
              </div>
              {!selected ? (
                <div className="empty-state" role="status">
                  Loading case…
                </div>
              ) : (
                <div className="case-content">
                  <div>
                    <div className="eyebrow">
                      {selected.ccid} · REVISION {selected.revision}
                    </div>
                    <h3>{selected.subject}</h3>
                    <p className="request-body">
                      {displayText(selected.correspondence_text)}
                    </p>
                    <dl className="detail-grid">
                      <div>
                        <dt>Loan identifier</dt>
                        <dd className="mono">{selected.loan_identifier}</dd>
                      </div>
                      <div>
                        <dt>Client</dt>
                        <dd>{clientName(selected.client_code)}</dd>
                      </div>
                      <div>
                        <dt>Original receipt</dt>
                        <dd>{eastern(selected.original_received_at)}</dd>
                      </div>
                      <div>
                        <dt>Balance</dt>
                        <dd>
                          {new Intl.NumberFormat("en-US", {
                            style: "currency",
                            currency: selected.currency,
                          }).format(selected.balance_minor / 100)}
                        </dd>
                      </div>
                    </dl>
                    <form
                      onSubmit={(event) => void saveCase(event)}
                      className="owner-form"
                    >
                      <label htmlFor="case-owner">Assigned owner</label>
                      <div>
                        <input
                          id="case-owner"
                          maxLength={120}
                          value={owner}
                          onChange={(event) => setOwner(event.target.value)}
                          required
                        />
                        <button
                          className="secondary-button"
                          disabled={
                            busy ||
                            !owner.trim() ||
                            owner === displayValue(selected.owner)
                          }
                        >
                          Save owner
                        </button>
                      </div>
                    </form>
                    <button
                      className="secondary-button review-button"
                      disabled={
                        busy ||
                        !["queued", "under_review"].includes(selected.status)
                      }
                      onClick={() =>
                        void saveCase(
                          undefined,
                          selected.status === "queued"
                            ? "under_review"
                            : "queued",
                        )
                      }
                    >
                      {selected.status === "queued"
                        ? "Move to review"
                        : "Return to queue"}
                      <Icon name="arrow" size={16} />
                    </button>
                  </div>
                  <div className="activity-panel">
                    <h3>Activity history</h3>
                    <p>Updates and actions recorded for this case.</p>
                    <ol className="activity-list">
                      {events.map((event) => (
                        <li key={event.sequence}>
                          <span className="activity-dot" />
                          <strong>
                            {workflowEvents[event.kind]
                              ? workflowEvents[event.kind]
                              : event.kind === "case.created"
                                ? "Case created"
                                : event.kind === "rules.assessed"
                                  ? "Business assessment recorded"
                                  : event.kind === "simulator.action"
                                    ? "Case action"
                                    : event.kind === "action.reconciled"
                                      ? "Action reconciled"
                                      : event.kind.startsWith("agent.")
                                        ? label(
                                            event.kind.replace(
                                              "agent.",
                                              "Agent ",
                                            ),
                                          )
                                        : "Case updated"}
                          </strong>
                          <time>{eastern(event.created_at)}</time>
                          <span>
                            {workflowEvents[event.kind]
                              ? workflowDetail(event)
                              : event.kind === "case.created"
                                ? event.payload.source === "versioned_fixture"
                                  ? "Case and supporting evidence received."
                                  : "Case saved."
                                : event.kind === "rules.assessed"
                                  ? `Route: ${event.payload.route ?? "Requires review"} · ${label(String(event.payload.disposition))}`
                                  : event.kind === "simulator.action" ||
                                      event.kind === "action.reconciled"
                                    ? `${displayLabel(event.payload.operation)} · ${label(String(event.payload.status ?? "reconciled"))}`
                                    : event.kind.startsWith("agent.")
                                      ? label(
                                          String(
                                            event.payload.tool ??
                                              event.payload.reason ??
                                              event.payload.status ??
                                              event.payload.source ??
                                              "Agent activity",
                                          ),
                                        )
                                      : Object.entries(
                                          (event.payload.after ?? {}) as Record<
                                            string,
                                            string
                                          >,
                                        )
                                          .map(
                                            ([key, value]) =>
                                              `${label(key)}: ${label(value)}`,
                                          )
                                          .join(" · ")}
                          </span>
                          <small>
                            Event {event.sequence} ·{" "}
                            {readableActor(event.actor)}
                          </small>
                        </li>
                      ))}
                    </ol>
                  </div>
                </div>
              )}
              {selected && (
                <AgentWorkspace
                  key={selected.id}
                  item={selected}
                  available={!!configuration?.agent_available}
                  onCaseUpdated={updateFromAgent}
                />
              )}
              {selected && (
                <CaseAssessment
                  key={`${selected.id}:${revision}`}
                  item={selected}
                  onRecorded={refreshWorkspace}
                />
              )}
              {selected && <CaseResources item={selected} />}
            </section>
          )}
          <footer className="page-footer">
            <span>Correspondence workspace</span>
            <span>v0.9.0</span>
          </footer>
        </main>
      </div>
      <dialog
        ref={intakeDialog}
        className="settings-dialog intake-dialog"
        aria-labelledby="new-case-title"
        onClose={() => newCaseButton.current?.focus()}
        onCancel={(event) => {
          if (busy) event.preventDefault();
        }}
      >
        <div className="panel-heading">
          <h2 id="new-case-title">New case</h2>
          <button
            className="icon-button"
            aria-label="Close new case"
            disabled={busy}
            onClick={() => intakeDialog.current?.close()}
          >
            <Icon name="close" />
          </button>
        </div>
        <form
          className="intake-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!busy) void createCase();
          }}
        >
          <p>Choose a request and its available evidence.</p>
          <label htmlFor="case-type">Case type</label>
          <select
            id="case-type"
            value={scenarioId}
            disabled={busy}
            onChange={(event) => {
              setScenarioId(event.target.value as Scenario["scenario_id"]);
              setVariant("base");
            }}
          >
            {scenarios.map((scenario) => (
              <option key={scenario.scenario_id} value={scenario.scenario_id}>
                {scenario.title}
              </option>
            ))}
          </select>
          <label htmlFor="case-evidence">Starting evidence</label>
          <select
            id="case-evidence"
            value={variant}
            disabled={busy}
            onChange={(event) =>
              setVariant(event.target.value as Scenario["variants"][number])
            }
          >
            {scenarios
              .find((scenario) => scenario.scenario_id === scenarioId)
              ?.variants.map((value) => (
                <option key={value} value={value}>
                  {value === "base"
                    ? "Initial request"
                    : value === "followup"
                      ? "Follow-up received"
                      : label(value)}
                </option>
              ))}
          </select>
          {error && (
            <p className="alert error" role="alert">
              {error}
            </p>
          )}
          <div className="intake-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={busy}
              onClick={() => intakeDialog.current?.close()}
            >
              Cancel
            </button>
            <button
              className="primary-button"
              disabled={busy || !scenarios.length}
            >
              {busy ? "Creating…" : "Create case"}
            </button>
          </div>
        </form>
      </dialog>
      <dialog
        ref={dialog}
        className="settings-dialog"
        onClose={() => settingsButton.current?.focus()}
      >
        <div className="panel-heading">
          <h2>Setup & status</h2>
          <button
            className="icon-button"
            aria-label="Close setup"
            onClick={() => dialog.current?.close()}
          >
            <Icon name="close" />
          </button>
        </div>
        <div className="settings-content">
          <h3>Workspace connections</h3>
          <div className="setup-status">
            <span className="dot" />
            {configuration
              ? "Application API connected"
              : "Application API unavailable"}
          </div>
          <h4>Azure Foundry / Azure OpenAI</h4>
          <p>
            {configuration?.model_connection_verified &&
            configuration.azure_last_live_check
              ? `Connection verified ${eastern(configuration.azure_last_live_check)}.`
              : configuration?.azure_configuration_complete
                ? "Configured. A connection check has not yet been recorded for these settings."
                : "Add your Azure deployment settings to the server .env file to enable the agent."}
          </p>
          {configuration?.missing_fields.length ? (
            <ul>
              {configuration.missing_fields.map((field) => (
                <li key={field}>
                  <code>{field}</code>
                </li>
              ))}
            </ul>
          ) : null}
          <p className="setup-note">
            Client review requirements apply even when automatic mode is
            selected.
          </p>
          <a
            className="text-button"
            href="/docs"
            target="_blank"
            rel="noreferrer"
          >
            API documentation <Icon name="arrow" size={16} />
          </a>
        </div>
      </dialog>
    </div>
  );
}
