import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import type { Case } from "../api/client";
import { clientName } from "../presentation";
import DeskIcon from "./DeskIcon";
import CaseDetail from "./CaseDetail";
import IntakeReviews from "./IntakeReviews";
import {
  ageTone,
  caseStatus,
  isActive,
  shortDateTime,
  workdayAge,
} from "./deskFormat";
import { useDeskData } from "./useDeskData";
import { REVIEWER } from "../auth/reviewer";
import "../operations.css";
import "./desk.css";

type Filter = "all" | "open" | "review" | "working" | "completed";
type Toast = { id: string; ccid: string; borrower: string };

/** Wraps the matched part of `text` in <mark>. */
function highlight(text: string, query: string): ReactNode {
  const q = query.trim();
  const at = q ? text.toLowerCase().indexOf(q.toLowerCase()) : -1;
  if (at < 0) return text;
  return (
    <>
      {text.slice(0, at)}
      <mark>{text.slice(at, at + q.length)}</mark>
      {text.slice(at + q.length)}
    </>
  );
}

export default function DeskApp({ onSignOut }: { onSignOut: () => void }) {
  const [path, setPath] = useState(location.pathname);
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [activeResult, setActiveResult] = useState(0);
  const [filter, setFilter] = useState<Filter>("all");
  const [menuOpen, setMenuOpen] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const known = useRef<Set<string> | null>(null);
  const resetDialog = useRef<HTMLDialogElement>(null);
  const [resetBusy, setResetBusy] = useState(false);
  const [resetError, setResetError] = useState("");
  const [resetNotice, setResetNotice] = useState("");
  const operations = useDeskData(api.operations);
  const config = useDeskData(api.configuration, 10000);
  // The reset is shared with the Mailbox through the server: whichever app
  // resets, the generation changes and both return to their base state.
  const shared = useDeskData(api.resetState, 2000, true);
  const generation = shared.value?.generation;
  const seenGeneration = useRef<string | undefined>(undefined);
  function applyReset(message: string) {
    // Every case is gone: return to the dashboard, and announce any new
    // requests that arrive from now on.
    known.current = new Set();
    setToasts([]);
    setFresh(new Set());
    setQuery("");
    setFilter("all");
    setResetNotice(message);
    go("/");
  }
  useEffect(() => {
    if (!generation || seenGeneration.current === generation) return;
    const first = seenGeneration.current === undefined;
    seenGeneration.current = generation;
    if (!first)
      applyReset("The workspace was reset from the Mailbox. All cases were cleared.");
  }, [generation]);
  useEffect(() => {
    if (!resetNotice) return;
    const timer = setTimeout(() => setResetNotice(""), 6000);
    return () => clearTimeout(timer);
  }, [resetNotice]);
  async function resetWorkspace() {
    setResetBusy(true);
    setResetError("");
    try {
      const state = await api.resetWorkspace();
      seenGeneration.current = state.generation;
      resetDialog.current?.close();
      applyReset("Workspace reset. All cases were cleared and the Mailbox was reset.");
    } catch (reason) {
      setResetError(
        reason instanceof Error ? reason.message : "The reset could not be completed.",
      );
    } finally {
      setResetBusy(false);
    }
  }
  useEffect(() => {
    const back = () => {
      setPath(location.pathname);
      setSearchOpen(false);
    };
    addEventListener("popstate", back);
    return () => removeEventListener("popstate", back);
  }, []);
  const caseId = /^\/cases\/([^/]+)\/?$/.exec(path)?.[1];
  const dashboard = path === "/" || path === "/cases";
  useEffect(() => {
    document.title = `${caseId ? "Case workspace" : dashboard ? "Case dashboard" : "Page not found"} · Correspondence Desk`;
  }, [caseId, dashboard]);
  function go(next: string) {
    if (location.pathname !== next) history.pushState(null, "", next);
    setPath(next);
    setSearchOpen(false);
    setMenuOpen(false);
    window.scrollTo(0, 0);
  }
  const openCase = (id: string) => go(`/cases/${id}`);
  const cases = operations.value?.cases ?? [];
  // Announce and briefly highlight cases that arrive while the Desk is open.
  useEffect(() => {
    if (!operations.value) return;
    const ids = operations.value.cases.map((item) => item.id);
    if (known.current === null) {
      known.current = new Set(ids);
      return;
    }
    const added = operations.value.cases.filter(
      (item) => !known.current!.has(item.id),
    );
    if (!added.length) return;
    added.forEach((item) => known.current!.add(item.id));
    setToasts((current) => [
      ...current,
      ...added.map((item) => ({
        id: item.id,
        ccid: item.ccid,
        borrower: item.borrower_display_name,
      })),
    ]);
    setFresh((current) => new Set([...current, ...added.map((a) => a.id)]));
    // Not cleared on re-render: polling re-runs this effect every few seconds.
    setTimeout(() => {
      setToasts((current) =>
        current.filter((t) => !added.some((a) => a.id === t.id)),
      );
      setFresh(
        (current) =>
          new Set([...current].filter((id) => !added.some((a) => a.id === id))),
      );
    }, 6000);
  }, [operations.value]);
  const reviewIds = operations.value?.review_case_ids ?? [];
  const activeRuns = operations.value?.runs.filter(isActive) ?? [];
  const workingIds = new Set(activeRuns.map((run) => run.case_id));
  const loading = !operations.value && !operations.error;
  const complete = (item: Case) =>
    ["closed", "transferred"].includes(item.status);
  const matches = (item: Case) =>
    [
      item.ccid,
      item.subject,
      item.borrower_display_name,
      item.loan_identifier,
      clientName(item.client_code),
    ]
      .join(" ")
      .toLowerCase()
      .includes(query.trim().toLowerCase());
  const statusOf = (item: Case) =>
    reviewIds.includes(item.id)
      ? { label: "Needs review", tone: "amber" }
      : workingIds.has(item.id)
        ? { label: "Agent processing", tone: "blue" }
        : complete(item)
          ? { label: caseStatus(item.status), tone: "good" }
          : { label: caseStatus(item.status), tone: "neutral" };
  const nextAction = (item: Case) =>
    reviewIds.includes(item.id)
      ? "Review draft"
      : workingIds.has(item.id)
        ? "Agent working"
        : item.status === "closed"
          ? "None · complete"
          : item.status === "transferred"
            ? "None · transferred"
            : item.status === "waiting_for_borrower"
              ? "Waiting on borrower"
              : item.status === "waiting_on_department"
                ? "Specialist task"
                : "Check case";
  const filters: { value: Filter; label: string; count: number }[] = [
    { value: "all", label: "All cases", count: cases.length },
    {
      value: "review",
      label: "Needs review",
      count: reviewIds.length,
    },
    {
      value: "working",
      label: "Agent processing",
      count: workingIds.size,
    },
    {
      value: "open",
      label: "Open cases",
      count: cases.filter((c) => !complete(c)).length,
    },
    {
      value: "completed",
      label: "Completed",
      count: cases.filter(complete).length,
    },
  ];
  // Prefer the saved routing age (same clock as the case header).
  const caseAge = (item: Case) => {
    const saved = (item.routing?.aging as { workdays?: number | null })
      ?.workdays;
    return typeof saved === "number"
      ? saved
      : workdayAge(item.original_received_at);
  };
  const rank = (item: Case) =>
    reviewIds.includes(item.id)
      ? 0
      : workingIds.has(item.id)
        ? 1
        : complete(item)
          ? 3
          : 2;
  const visible = cases
    .filter(matches)
    .filter(
      (item) =>
        filter === "all" ||
        (filter === "open"
          ? !complete(item)
          : filter === "review"
            ? reviewIds.includes(item.id)
            : filter === "working"
              ? workingIds.has(item.id)
              : complete(item)),
    )
    .map((item) => ({ item, age: caseAge(item) }))
    .sort(
      (a, b) =>
        rank(a.item) - rank(b.item) ||
        (b.age ?? -1) - (a.age ?? -1) ||
        a.item.original_received_at.localeCompare(b.item.original_received_at),
    );
  const results = query.trim() ? cases.filter(matches).slice(0, 7) : [];
  return (
    <div className="desk-app desk-theme">
      <header className="desk-topbar">
        <a
          href="/"
          className="desk-title"
          aria-label="Correspondence Desk home"
          onClick={(e) => {
            e.preventDefault();
            go("/");
          }}
        >
          <span className="desk-brand-mark">
            <DeskIcon name="cases" size={18} />
          </span>
          Correspondence Desk
        </a>
        <div className="desk-global-search">
          <DeskIcon name="search" size={16} />
          <input
            aria-label="Search cases, loans or borrowers"
            placeholder="Search cases, loans or borrowers…"
            role="combobox"
            aria-expanded={searchOpen && !!query.trim() && !!caseId}
            aria-controls="desk-search-results"
            aria-activedescendant={
              searchOpen && results[activeResult]
                ? `desk-search-${results[activeResult].id}`
                : undefined
            }
            value={query}
            onFocus={() => setSearchOpen(true)}
            onChange={(e) => {
              setQuery(e.target.value);
              setSearchOpen(true);
              setActiveResult(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") setSearchOpen(false);
              if (caseId && searchOpen && results.length) {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setActiveResult((i) => (i + 1) % results.length);
                  return;
                }
                if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setActiveResult(
                    (i) => (i - 1 + results.length) % results.length,
                  );
                  return;
                }
                if (e.key === "Enter" && results[activeResult]) {
                  openCase(results[activeResult].id);
                  return;
                }
              }
              if (e.key === "Enter") {
                setFilter("all");
                go("/");
              }
            }}
          />
          {searchOpen && query.trim() && !!caseId && (
            <>
              <button
                className="search-dismiss"
                aria-label="Close search results"
                tabIndex={-1}
                onClick={() => setSearchOpen(false)}
              />
              <div
                className="desk-search-results"
                id="desk-search-results"
                role="listbox"
              >
                {results.map((item, index) => {
                  const status = statusOf(item);
                  return (
                    <button
                      key={item.id}
                      id={`desk-search-${item.id}`}
                      role="option"
                      aria-selected={index === activeResult}
                      className={index === activeResult ? "active" : ""}
                      onMouseEnter={() => setActiveResult(index)}
                      onClick={() => openCase(item.id)}
                    >
                      <strong>{highlight(item.ccid, query)}</strong>
                      <span className={`desk-badge ${status.tone}`}>
                        {status.label}
                      </span>
                      <span className="desk-search-sub">
                        {highlight(item.borrower_display_name, query)} ·{" "}
                        {highlight(item.subject, query)}
                      </span>
                    </button>
                  );
                })}
                {!results.length && <p>No matching cases.</p>}
              </div>
            </>
          )}
        </div>
        <div className="desk-profile-menu">
          <button
            className="desk-profile"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="desk-avatar">{REVIEWER.initials}</span>
            <span>
              {REVIEWER.name}
              <small>{REVIEWER.role}</small>
            </span>
            <DeskIcon
              name="chevron"
              size={14}
              style={{ transform: "rotate(90deg)" }}
            />
          </button>
          {menuOpen && (
            <>
              <button
                className="search-dismiss"
                aria-label="Close account menu"
                tabIndex={-1}
                onClick={() => setMenuOpen(false)}
              />
              <div
                className="desk-menu"
                role="menu"
                onKeyDown={(e) => e.key === "Escape" && setMenuOpen(false)}
              >
                <button
                  role="menuitem"
                  autoFocus
                  onClick={() => {
                    setMenuOpen(false);
                    setResetError("");
                    resetDialog.current?.showModal();
                  }}
                >
                  <DeskIcon name="refresh" size={15} /> Reset workspace
                </button>
                <button role="menuitem" onClick={onSignOut}>
                  <DeskIcon name="arrow" size={15} /> Sign out
                </button>
              </div>
            </>
          )}
        </div>
      </header>
      <main
        className={`desk-main ${dashboard ? "desk-dashboard" : ""} ${caseId ? "desk-main-case" : ""}`}
      >
        {operations.error && (
          <p className="desk-alert" role="alert">
            {operations.error}
          </p>
        )}
        {resetNotice && (
          <p className="desk-notice" role="status">
            {resetNotice}
          </p>
        )}
        {caseId ? (
          <CaseDetail
            key={caseId}
            id={caseId}
            config={config.value}
            onBack={() => go("/")}
          />
        ) : dashboard ? (
          <>
            <div className="desk-list-heading">
              <h1>Case dashboard</h1>
            </div>
            <IntakeReviews />
            <section className="desk-card desk-worklist" aria-label="Cases">
              <header className="desk-worklist-heading">
                <div
                  className="desk-filter-tabs"
                  role="group"
                  aria-label="Filter cases"
                >
                  {filters.map((item) => (
                    <button
                      key={item.value}
                      className={`${filter === item.value ? "selected" : ""} ${item.value}`}
                      aria-pressed={filter === item.value}
                      onClick={() => setFilter(item.value)}
                    >
                      <strong>{operations.value ? item.count : "—"}</strong>
                      {item.label}
                    </button>
                  ))}
                </div>
                <span className="desk-muted">
                  {visible.length} {visible.length === 1 ? "case" : "cases"}
                  {query.trim() && (
                    <>
                      {" "}
                      matching “{query.trim()}” ·{" "}
                      <button
                        className="desk-text-button"
                        onClick={() => setQuery("")}
                      >
                        Clear
                      </button>
                    </>
                  )}
                </span>
              </header>
              <div className="desk-table-scroll">
                <table aria-label="Case dashboard">
                  <thead>
                    <tr>
                      <th>Case / request</th>
                      <th>Borrower &amp; loan</th>
                      <th>Status</th>
                      <th>Next action</th>
                      <th>Age</th>
                      <th>Received</th>
                      <th aria-label="Open case" />
                    </tr>
                  </thead>
                  <tbody>
                    {loading &&
                      Array.from({ length: 6 }).map((_, i) => (
                        <tr key={`sk-${i}`} className="desk-skeleton-row">
                          <td>
                            <span className="desk-skeleton wide" />
                          </td>
                          <td>
                            <span className="desk-skeleton mid" />
                          </td>
                          <td>
                            <span className="desk-skeleton narrow" />
                          </td>
                          <td>
                            <span className="desk-skeleton narrow" />
                          </td>
                          <td>
                            <span className="desk-skeleton narrow" />
                          </td>
                          <td>
                            <span className="desk-skeleton narrow" />
                          </td>
                          <td />
                        </tr>
                      ))}
                    {visible.map(({ item, age }) => {
                      const status = statusOf(item);
                      return (
                        <tr
                          key={item.id}
                          className={`desk-case-row ${fresh.has(item.id) ? "fresh" : ""}`}
                          onClick={(e) => {
                            if (!(e.target as HTMLElement).closest("a, button"))
                              openCase(item.id);
                          }}
                        >
                          <td className="desk-case-cell">
                            <a
                              href={`/cases/${item.id}`}
                              title={item.subject}
                              onClick={(e) => {
                                if (
                                  e.metaKey ||
                                  e.ctrlKey ||
                                  e.shiftKey ||
                                  e.altKey
                                )
                                  return;
                                e.preventDefault();
                                openCase(item.id);
                              }}
                            >
                              <strong>{item.ccid}</strong>
                              <span>{item.subject}</span>
                            </a>
                          </td>
                          <td className="desk-borrower-cell">
                            <span>{item.borrower_display_name}</span>
                            <small>
                              Loan {item.loan_identifier} ·{" "}
                              {clientName(item.client_code)}
                            </small>
                          </td>
                          <td>
                            <span className={`desk-badge ${status.tone}`}>
                              {status.label}
                            </span>
                          </td>
                          <td className="desk-next-cell">{nextAction(item)}</td>
                          <td>
                            {age === null ? (
                              <span className="desk-muted">Needs review</span>
                            ) : (
                              <span
                                className={`desk-age ${complete(item) ? "done" : ageTone(age)}`}
                                title="Eastern Monday–Friday workdays from original receipt"
                              >
                                {age} / 20
                                <span aria-hidden="true">
                                  <i
                                    style={{
                                      width: `${Math.max(4, Math.min(100, age * 5))}%`,
                                    }}
                                  />
                                </span>
                              </span>
                            )}
                          </td>
                          <td className="desk-received-cell">
                            {shortDateTime(item.original_received_at)}
                          </td>
                          <td>
                            <DeskIcon name="chevron" size={16} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {!loading && !visible.length && (
                <div className="desk-empty">
                  <DeskIcon name="cases" size={30} />
                  <h3>
                    {operations.value
                      ? "No cases in this view"
                      : operations.error
                        ? "Cases are unavailable"
                        : "Loading cases…"}
                  </h3>
                  <p>
                    {query
                      ? "Try a different case number, borrower or loan."
                      : filter !== "all"
                        ? "Choose All cases to see the complete dashboard."
                        : "Incoming requests appear here automatically."}
                  </p>
                  {(query || filter !== "all") && (
                    <button
                      className="desk-button"
                      onClick={() => {
                        setQuery("");
                        setFilter("all");
                      }}
                    >
                      Clear filters
                    </button>
                  )}
                </div>
              )}
            </section>
          </>
        ) : (
          <div className="desk-empty">
            <h1>Page not found</h1>
            <p>Return to the dashboard to find your case.</p>
            <a
              href="/"
              className="desk-button"
              onClick={(e) => {
                e.preventDefault();
                go("/");
              }}
            >
              Case dashboard
            </a>
          </div>
        )}
      </main>
      <dialog className="desk-dialog desk-reset-dialog" ref={resetDialog}>
        <header>
          <h2>Reset workspace?</h2>
          <button
            className="desk-icon-button"
            aria-label="Close reset dialog"
            disabled={resetBusy}
            onClick={() => resetDialog.current?.close()}
          >
            <DeskIcon name="close" />
          </button>
        </header>
        <div className="desk-dialog-body">
          <p>
            This deletes every case, including its correspondence, agent
            activity, drafts and documents. The Mailbox is reset too, and its
            five prepared requests return to Drafts.
          </p>
          <p className="desk-field-hint">This cannot be undone.</p>
          {resetError && (
            <p className="desk-alert" role="alert">
              {resetError}
            </p>
          )}
        </div>
        <footer className="desk-dialog-footer">
          <button
            className="desk-button quiet"
            disabled={resetBusy}
            onClick={() => resetDialog.current?.close()}
          >
            Cancel
          </button>
          <button
            className="desk-button primary danger"
            disabled={resetBusy}
            onClick={() => void resetWorkspace()}
          >
            {resetBusy ? "Resetting…" : "Reset workspace"}
          </button>
        </footer>
      </dialog>
      <div className="desk-toasts" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <button
            key={toast.id}
            className="desk-toast"
            onClick={() => {
              setToasts((current) => current.filter((t) => t.id !== toast.id));
              openCase(toast.id);
            }}
          >
            <span className="desk-toast-icon">
              <DeskIcon name="mail" size={16} />
            </span>
            <span>
              <strong>New request</strong> · {toast.ccid} · {toast.borrower}
            </span>
            <DeskIcon name="chevron" size={14} />
          </button>
        ))}
      </div>
    </div>
  );
}
