import { useState } from "react";
import { api } from "../api/client";
import type { CaseInput, SystemCase } from "../api/client";
import CaseWorkflow from "../CaseWorkflow";
import { clientName, displayText, displayValue } from "../presentation";
import DeskIcon from "../desk/DeskIcon";
import type { SystemName } from "../desk/ActivityTimeline";
import {
  actorName,
  calendarDate,
  fieldLabel,
  fieldValue,
  instant,
  money,
  refLabel,
  sentence,
} from "./format";
import type { Row } from "./format";
import "./systems.css";

type Props = {
  data: SystemCase;
  refresh: () => void;
  onOpenSystem?: (system: SystemName) => void;
};

const HIDDEN = new Set([
  "synthetic",
  "simulated",
  "result_source",
  "client_configuration",
  "mail_intake",
]);

const GROUPS: { title: string; keys: string[] }[] = [
  {
    title: "Borrower & contact",
    keys: [
      "current_legal_name",
      "requested_legal_name",
      "borrower_email",
      "borrower_phone",
      "mailing_address",
    ],
  },
  { title: "Property", keys: ["property_address", "occupancy"] },
  {
    title: "Loan terms",
    keys: [
      "product",
      "original_principal_minor",
      "note_date",
      "term_months",
      "annual_rate_basis_points",
      "principal_interest_minor",
      "maturity_date",
    ],
  },
  {
    title: "Payment status",
    keys: [
      "last_payment_received",
      "first_payment_date",
      "remaining_payments",
      "payment_method",
      "new_payment_minor",
      "new_payment_effective_date",
      "escrow_included",
    ],
  },
  {
    title: "Authorization & contact rules",
    keys: [
      "requester_role",
      "authorized_recipient",
      "representative_name",
      "representation_verified",
      "communication_restriction",
    ],
  },
  {
    title: "Tax & escrow",
    keys: [
      "escrow_monthly_deposit_minor",
      "escrow_balance_minor",
      "escrow_analysis_date",
      "escrow_surplus_minor",
      "escrow_refund_method",
      "tax_escrow_responsibility",
      "tax_period",
      "tax_payee",
      "tax_bill_number",
      "tax_parcel_id",
      "tax_amount_minor",
      "tax_bill_received_at",
      "tax_due_date",
      "tax_status",
      "tax_scheduled_date",
      "tax_paid_at",
      "tax_payment_reference",
      "tax_schedule_verified_by",
    ],
  },
  {
    title: "Bankruptcy",
    keys: [
      "servicing_bankruptcy_status",
      "servicing_status_source",
      "specialist_determination",
    ],
  },
  {
    title: "Payments & EFT",
    keys: [
      "eft_intent",
      "recurring_payment_enrollment",
      "refund_authorization",
      "draw_authorization",
    ],
  },
  { title: "Profile updates", keys: ["profile_update_result"] },
];

export default function IlsView({ data, refresh, onOpenSystem }: Props) {
  const context = (data.loan.context ?? {}) as Row;
  return (
    <section
      aria-label="ILS servicing workspace"
      className="system-panel sx-panel"
    >
      <LoanSummary data={data} context={context} />
      <Alerts data={data} context={context} />
      <div className="sx-columns sx-columns-ils">
        <LoanProfile context={context} />
        <div className="sx-stack">
          <Tasks data={data} refresh={refresh} />
          <Notes data={data} onOpenSystem={onOpenSystem} />
        </div>
      </div>
      <History data={data} />
      {!!data.handoffs.length && !!data.thread && (
        <div className="sx-card">
          <CaseWorkflow
            item={data.case}
            running={data.runs.some((r) =>
              ["queued", "running"].includes(r.status),
            )}
            onChanged={refresh}
            automatic
            section="handoff"
          />
        </div>
      )}
    </section>
  );
}

/* ─── Summary strip ───────────────────────────────────────────────────── */

function LoanSummary({ data, context }: { data: SystemCase; context: Row }) {
  const term = Number(context.term_months) || 0;
  const remaining = Number(context.remaining_payments) || 0;
  const made = term && remaining ? term - remaining : 0;
  const metrics: [string, string, string?][] = [
    ["Unpaid principal", money(Number(data.loan.balance_minor) || 0)],
  ];
  if (typeof context.principal_interest_minor === "number")
    metrics.push([
      "Monthly P&I",
      money(context.principal_interest_minor),
      context.escrow_included === false
        ? "Escrow billed separately"
        : undefined,
    ]);
  if (typeof context.annual_rate_basis_points === "number")
    metrics.push([
      "Interest rate",
      fieldValue("annual_rate_basis_points", context.annual_rate_basis_points),
      sentence(context.product ?? ""),
    ]);
  if (context.first_payment_date)
    metrics.push([
      "Next payment due",
      calendarDate(context.first_payment_date),
      remaining ? `${remaining} payments remaining` : undefined,
    ]);
  if (context.maturity_date)
    metrics.push(["Scheduled maturity", calendarDate(context.maturity_date)]);
  if (metrics.length === 1) {
    metrics.push(["Product", sentence(context.product ?? "")]);
    metrics.push(["Client", clientName(String(data.loan.client_code))]);
  }
  return (
    <div className="sx-loan-summary">
      <div className="sx-loan-id">
        <span className="sx-mini-label">Loan</span>
        <strong>{String(data.loan.loan_identifier)}</strong>
        <small>
          {String(data.loan.borrower_display_name)} ·{" "}
          {clientName(String(data.loan.client_code))}
        </small>
      </div>
      {metrics.map(([name, value, note]) => (
        <div key={name} className="sx-metric">
          <span className="sx-mini-label">{name}</span>
          <strong>{value}</strong>
          {note && <small>{note}</small>}
        </div>
      ))}
      {made > 0 && (
        <div className="sx-paydown" aria-label="Payment progress">
          <div className="sx-aging-head">
            <span className="sx-mini-label">Payment progress</span>
            <small>
              {made} of {term} payments made · {Math.round((made / term) * 100)}
              %
            </small>
          </div>
          <div className="sx-track">
            <i style={{ width: `${(made / term) * 100}%` }} />
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Alerts ──────────────────────────────────────────────────────────── */

function Alerts({ data, context }: { data: SystemCase; context: Row }) {
  const alerts: { tone: "danger" | "warn" | "info"; text: string }[] = [];
  const restriction = String(context.communication_restriction ?? "none");
  if (restriction !== "none")
    alerts.push({
      tone: "danger",
      text: `${sentence(restriction)} contact · correspond only with ${String(context.authorized_recipient ?? "the verified representative")}`,
    });
  if (context.representation_verified === false)
    alerts.push({ tone: "warn", text: "Representation not verified" });
  if (context.servicing_bankruptcy_status)
    alerts.push({
      tone: "warn",
      text: `Bankruptcy marker: ${sentence(context.servicing_bankruptcy_status)}${
        context.servicing_status_source
          ? ` (${sentence(context.servicing_status_source).toLowerCase()})`
          : ""
      }${context.specialist_determination ? "" : " · awaiting specialist determination"}`,
    });
  if (context.tax_status === "scheduled" && !context.tax_paid_at)
    alerts.push({
      tone: "info",
      text: `Tax payment scheduled ${calendarDate(context.tax_scheduled_date)}; not yet disbursed`,
    });
  const open = data.tasks.filter((t) => t.status !== "completed").length;
  if (open)
    alerts.push({
      tone: "info",
      text: `${open} open specialist task${open === 1 ? "" : "s"}`,
    });
  if (
    context.borrower_email &&
    context.authorized_recipient &&
    context.borrower_email !== context.authorized_recipient
  )
    alerts.push({
      tone: "info",
      text: `Responses go to ${String(context.authorized_recipient)}, not the borrower's email`,
    });
  if (!alerts.length)
    return (
      <p className="sx-alerts-clear">
        <DeskIcon name="shield" size={14} /> No warnings or contact restrictions
        on this loan.
      </p>
    );
  return (
    <ul className="sx-alerts" aria-label="Loan warnings">
      {alerts.map((a) => (
        <li key={a.text} className={`sx-alert ${a.tone}`}>
          <DeskIcon name={a.tone === "info" ? "help" : "shield"} size={13} />
          {a.text}
        </li>
      ))}
    </ul>
  );
}

/* ─── Profile ─────────────────────────────────────────────────────────── */

function LoanProfile({ context }: { context: Row }) {
  const used = new Set(GROUPS.flatMap((g) => g.keys));
  const other = Object.keys(context).filter(
    (k) =>
      !used.has(k) &&
      !HIDDEN.has(k) &&
      (context[k] === null || typeof context[k] !== "object"),
  );
  const groups = [
    ...GROUPS.map((g) => ({
      ...g,
      keys: g.keys.filter((k) => k in context && !HIDDEN.has(k)),
    })),
    { title: "Other servicing facts", keys: other },
  ].filter((g) => g.keys.length);
  return (
    <article className="sx-card" aria-label="Loan profile">
      <header className="sx-card-head">
        <h3>Loan profile</h3>
      </header>
      {groups.map((group) => (
        <section key={group.title} className="sx-group">
          <h4 className="sx-mini-label">{group.title}</h4>
          <dl className="sx-kv">
            {group.keys.map((key) => (
              <div key={key}>
                <dt>{fieldLabel(key)}</dt>
                <dd
                  className={
                    context[key] === null || context[key] === undefined
                      ? "sx-muted"
                      : undefined
                  }
                >
                  {fieldValue(key, context[key])}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </article>
  );
}

/* ─── Tasks ───────────────────────────────────────────────────────────── */

function Tasks({ data, refresh }: { data: SystemCase; refresh: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = data.runs.some((r) =>
    ["queued", "running"].includes(r.status),
  );
  const titles = new Map(
    data.evidence.map((e) => [String(e.id), displayValue(e.title)]),
  );
  async function record(kind: CaseInput["kind"], owner: string) {
    setBusy(true);
    setError("");
    try {
      await api.supplyInput(data.case.id, {
        request_id: crypto.randomUUID(),
        expected_revision: data.case.revision,
        kind,
        actor: displayValue(owner),
        text: "Specialist result received.",
      });
      refresh();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not record the result.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="sx-card" aria-label="Specialist tasks">
      <header className="sx-card-head">
        <h3>Specialist tasks</h3>
        <span className="desk-badge neutral">{data.tasks.length}</span>
      </header>
      {error && (
        <p role="alert" className="alert error">
          {error}
        </p>
      )}
      {!data.tasks.length && (
        <p className="sx-empty">
          No specialist tasks. A task is opened only when the request needs
          another team.
        </p>
      )}
      {data.tasks.map((task) => {
        const request = (task.request ?? {}) as Row;
        const result = (task.result ?? null) as Row | null;
        const done = task.status === "completed";
        const supplied = data.specialist_results.find(
          (r) => r.task_type === task.task_type,
        );
        const kind =
          task.task_type === "demo_tax_schedule_review"
            ? "tax_specialist_result"
            : "bankruptcy_specialist_result";
        const evidence = ((request.evidence_ids as string[]) ?? [])
          .map((id) => titles.get(String(id)))
          .filter(Boolean);
        return (
          <div className="sx-task" key={String(task.id)}>
            <div className="sx-task-head">
              <h4>{taskTitle(String(task.task_type))}</h4>
              <span className={`desk-badge ${done ? "good" : "amber"}`}>
                {sentence(task.status)}
              </span>
            </div>
            <ol className="sx-mini-track" aria-label="Task progress">
              <li className="done">Opened</li>
              <li className={done ? "done" : "current"}>
                {done ? "Worked" : "Pending"}
              </li>
              <li className={done ? "done" : ""}>Completed</li>
            </ol>
            <dl className="sx-kv compact">
              <div>
                <dt>Owner</dt>
                <dd>{actorName(task.owner)}</dd>
              </div>
              <div>
                <dt>Origin</dt>
                <dd>
                  {request.fixture_key ? (
                    <span className="sx-tag">Existing task reused</span>
                  ) : (
                    "Opened by AI agent"
                  )}
                </dd>
              </div>
              {!!task.pending_reason && (
                <div className="wide">
                  <dt>Pending reason</dt>
                  <dd>{displayText(task.pending_reason)}</dd>
                </div>
              )}
              {!!evidence.length && (
                <div className="wide">
                  <dt>Linked documents</dt>
                  <dd>{evidence.join(" · ")}</dd>
                </div>
              )}
              {result &&
                Object.entries(result)
                  .filter(
                    ([k, v]) =>
                      !HIDDEN.has(k) && (v === null || typeof v !== "object"),
                  )
                  .map(([k, v]) => (
                    <div key={k}>
                      <dt>{fieldLabel(k)}</dt>
                      <dd>{fieldValue(k, v)}</dd>
                    </div>
                  ))}
            </dl>
            {supplied && data.thread && !done && (
              <details className="sx-supplied" open>
                <summary>Specialist result ready to record</summary>
                <dl className="sx-kv compact">
                  {Object.entries((supplied.result ?? {}) as Row)
                    .filter(
                      ([k, v]) =>
                        !HIDDEN.has(k) && (v === null || typeof v !== "object"),
                    )
                    .map(([k, v]) => (
                      <div key={k}>
                        <dt>{fieldLabel(k)}</dt>
                        <dd>{fieldValue(k, v)}</dd>
                      </div>
                    ))}
                </dl>
                <button
                  className="primary-button"
                  disabled={busy || active || data.case.status === "closed"}
                  onClick={() => void record(kind, String(task.owner))}
                >
                  Record specialist result
                </button>
                <p className="workflow-hint">
                  Recording the result continues processing automatically.
                </p>
              </details>
            )}
          </div>
        );
      })}
    </article>
  );
}

const taskTitle = (type: string) =>
  ({
    demo_profile_name_update: "Legal name update",
    demo_tax_schedule_review: "Tax payment schedule review",
    demo_bankruptcy_status_review: "Bankruptcy status review",
  })[type] ?? sentence(type.replace(/^demo_/, ""));

/* ─── Notes ───────────────────────────────────────────────────────────── */

function Notes({
  data,
  onOpenSystem,
}: {
  data: SystemCase;
  onOpenSystem?: (system: SystemName) => void;
}) {
  return (
    <article className="sx-card" aria-label="Servicing notes">
      <header className="sx-card-head">
        <h3>Servicing notes</h3>
        <span className="desk-badge neutral">{data.notes.length}</span>
      </header>
      {!data.notes.length && (
        <p className="sx-empty">
          The final note is recorded after the response is delivered and
          indexed.
        </p>
      )}
      {[...data.notes].reverse().map((note) => {
        const details = (note.details ?? {}) as Row;
        // The stored comment starts with its header lines; show the letter body separately.
        const lines = String(note.content ?? "").split("\n");
        const bodyStart = lines.findIndex(
          (l, i) => i > 0 && !/^(To:|.*delivered:|Standout Comment)/.test(l),
        );
        const body = lines.slice(Math.max(bodyStart, 0)).join("\n");
        const preview = body.split("\n").filter(Boolean).slice(0, 2).join(" ");
        return (
          <div className="sx-note" key={String(note.id)}>
            <div className="sx-task-head">
              <h4>{String(note.note_type)}</h4>
              <span className="sx-muted">
                {instant(note.created_at, false)}
              </span>
            </div>
            <div className="sx-note-tags">
              {!!details.standout_comment && (
                <span className="sx-tag strong">Standout Comment</span>
              )}
              <span className="sx-tag">Dept: {String(note.department)}</span>
              {details.draft_version !== undefined && (
                <span className="sx-tag">
                  Response v{String(details.draft_version)}
                </span>
              )}
            </div>
            <dl className="sx-kv compact">
              <div>
                <dt>Sent to</dt>
                <dd>{String(details.recipient ?? "Not recorded")}</dd>
              </div>
              <div>
                <dt>Tracking update</dt>
                <dd>
                  {details.outbox_id ? (
                    <button
                      className="text-button sx-inline-link"
                      disabled={!onOpenSystem}
                      onClick={() => onOpenSystem?.("secure")}
                      title={String(details.tracking_update ?? "")}
                    >
                      Delivered · {refLabel("outbox", details.outbox_id)}
                    </button>
                  ) : (
                    displayText(details.tracking_update ?? "Not recorded")
                  )}
                </dd>
              </div>
            </dl>
            <p className="sx-note-preview">{displayText(preview)}</p>
            <details>
              <summary>Show full note</summary>
              <pre className="response-preview">
                {displayText(note.content)}
              </pre>
            </details>
          </div>
        );
      })}
    </article>
  );
}

/* ─── History ─────────────────────────────────────────────────────────── */

const OPERATION: Record<string, string> = {
  "ils.final_note": "Final servicing note recorded",
  "ils.update": "Servicing record updated",
  "ils.task": "Specialist task recorded",
  "ils.name_update": "Legal name updated",
};

function changes(before: Row, after: Row): string[] {
  const result: string[] = [];
  if (after?.note) result.push("Note added to the loan");
  for (const key of new Set([
    ...Object.keys(before ?? {}),
    ...Object.keys(after ?? {}),
  ])) {
    const a = before?.[key];
    const b = after?.[key];
    if (key === "note" || HIDDEN.has(key)) continue;
    if ((a && typeof a === "object") || (b && typeof b === "object")) continue;
    if (a !== b)
      result.push(
        `${fieldLabel(key)}: ${a === undefined ? "—" : fieldValue(key, a)} → ${fieldValue(key, b)}`,
      );
  }
  return result;
}

function History({ data }: { data: SystemCase }) {
  if (!data.history.length) return null;
  return (
    <article className="sx-card" aria-label="Servicing history">
      <header className="sx-card-head">
        <h3>Servicing history</h3>
        <span className="desk-badge neutral">
          {data.history.length}{" "}
          {data.history.length === 1 ? "update" : "updates"}
        </span>
      </header>
      <table className="sx-table">
        <thead>
          <tr>
            <th>When</th>
            <th>Action</th>
            <th>Change</th>
            <th>Reference</th>
          </tr>
        </thead>
        <tbody>
          {[...data.history].reverse().map((record) => {
            const list = changes(record.before as Row, record.after as Row);
            return (
              <tr key={String(record.id)}>
                <td>{instant(record.created_at, false)}</td>
                <td>
                  {OPERATION[String(record.operation)] ??
                    sentence(record.operation)}
                </td>
                <td>{list.length ? list.join("; ") : "—"}</td>
                <td>
                  <code className="sx-ref">
                    {refLabel("action", record.action_id)}
                  </code>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </article>
  );
}
