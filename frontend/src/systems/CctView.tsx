import { useMemo, useState } from "react";
import type { Assessment, SystemCase } from "../api/client";
import CaseAssessment from "../CaseAssessment";
import { displayText } from "../presentation";
import DeskIcon from "../desk/DeskIcon";
import type { IconName } from "../desk/DeskIcon";
import { systemForTool, toolTitle } from "../desk/ActivityTimeline";
import type { SystemName } from "../desk/ActivityTimeline";
import {
  actorName,
  calendarDate,
  clock,
  instant,
  sentence,
  refLabel,
} from "./format";
import type { Row } from "./format";
import "./systems.css";

type Props = {
  data: SystemCase;
  assessment?: Assessment;
  refresh: () => void;
  onOpenSystem?: (system: SystemName) => void;
};

const SYSTEM_NAMES: Record<SystemName, string> = {
  cct: "CCT",
  ils: "ILS",
  onbase: "OnBase",
  secure: "Secure mail",
  agent: "AI agent",
};

export default function CctView({
  data,
  assessment,
  refresh,
  onOpenSystem,
}: Props) {
  return (
    <section aria-label="CCT case tracker" className="system-panel sx-panel">
      <CaseProgress data={data} unmapped={unmapped(assessment)} />
      <ClosureChecklist data={data} onOpenSystem={onOpenSystem} />
      <div className="sx-columns">
        <div className="sx-stack">
          <EmailCard data={data} />
          <CaseRecord data={data} assessment={assessment} />
        </div>
        <CaseTimeline data={data} />
      </div>
      <div className="sx-card sx-assessment">
        <CaseAssessment item={data.case} onRecorded={refresh} readOnly />
      </div>
    </section>
  );
}

/* ─── Progress ────────────────────────────────────────────────────────── */

type StepState = "done" | "current" | "paused" | "exception" | "todo";

const unmapped = (assessment?: Assessment) =>
  !!assessment?.findings.some((f) => f.code === "classification_mapping_missing");

function CaseProgress({
  data,
  unmapped,
}: {
  data: SystemCase;
  unmapped: boolean;
}) {
  const status = data.case.status;
  const sent = data.outbox.filter((o) => o.status === "sent");
  const pending = (data.case.pending_work ?? []) as Row[];
  const paused = [
    "waiting_for_borrower",
    "waiting_on_department",
    "under_review",
    "awaiting_review",
    "records_incomplete",
    "assignment_exception",
  ].includes(status);
  const routed = data.events.some(
    (e) => (e.payload as Row)?.operation === "cct.apply_plan",
  );
  const final =
    status === "transferred"
      ? { label: "Transferred", done: true }
      : { label: "Closed", done: status === "closed" };
  const steps: { label: string; done: boolean; detail?: string }[] = [
    {
      label: "Received",
      done: true,
      detail: calendarDate(String(data.case.original_received_at).slice(0, 10)),
    },
    {
      label: "Classified",
      done: !!data.case.classification,
      detail: data.case.classification
        ? String((data.case.classification as Row).work_type ?? "")
        : undefined,
    },
    {
      label: "Assessed & routed",
      done: routed || sent.length > 0,
      detail: (data.case.routing as Row | null)?.route as string | undefined,
    },
    {
      label: "Response sent",
      done: sent.length > 0,
      detail: sent.length
        ? `${sent.length} ${sent.length === 1 ? "delivery" : "deliveries"}`
        : data.drafts.length
          ? "Draft prepared"
          : undefined,
    },
    {
      label: "Records complete",
      done: data.packages.length > 0 && data.notes.length > 0,
      detail:
        data.packages.length || data.notes.length
          ? `${data.packages.length} package · ${data.notes.length} note`
          : undefined,
    },
    { label: final.label, done: final.done },
  ];
  const current = steps.findIndex((s) => !s.done);
  const reason = pending
    .map((p) => String(p.resume_requirement ?? p.reason ?? ""))
    .find(Boolean);
  return (
    <div className="sx-progress-wrap">
      <ol className="sx-progress" aria-label="Case progress">
        {steps.map((step, index) => {
          let state: StepState = step.done ? "done" : "todo";
          if (index === current)
            state =
              index === 1 && unmapped
                ? "exception"
                : paused
                  ? "paused"
                  : "current";
          return (
            <li key={step.label} className={`sx-step ${state}`}>
              <span className="sx-step-dot" aria-hidden="true">
                {state === "done" ? (
                  <DeskIcon name="check" size={12} />
                ) : state === "paused" ? (
                  <DeskIcon name="clock" size={12} />
                ) : state === "exception" ? (
                  "!"
                ) : (
                  index + 1
                )}
              </span>
              <strong>{step.label}</strong>
              <small>
                {state === "exception"
                  ? "No approved classification"
                  : state === "paused"
                    ? statusLabel(status)
                    : step.detail || (state === "current" ? "In progress" : "")}
              </small>
            </li>
          );
        })}
      </ol>
      {paused && reason && (
        <p className="sx-progress-note">
          <DeskIcon name="clock" size={14} />
          <span>
            <strong>{statusLabel(status)}.</strong> {displayText(reason)}
          </span>
        </p>
      )}
    </div>
  );
}

const statusLabel = (status: string) =>
  ({
    waiting_for_borrower: "Waiting for borrower",
    waiting_on_department: "Waiting on specialist department",
    under_review: "Awaiting human review",
    awaiting_review: "Awaiting human review",
    records_incomplete: "Records incomplete",
    assignment_exception: "Assignment exception",
  })[status] ?? sentence(status);

/* ─── Closure checklist ───────────────────────────────────────────────── */

function ClosureChecklist({
  data,
  onOpenSystem,
}: {
  data: SystemCase;
  onOpenSystem?: (system: SystemName) => void;
}) {
  const delivery = [...data.outbox].reverse().find((o) => o.status === "sent");
  const pkg = data.packages.at(-1);
  const note = data.notes.at(-1);
  const closed = data.case.status === "closed";
  const transferred = data.case.status === "transferred";
  const items: {
    label: string;
    done: boolean;
    reference?: string;
    detail: string;
    system: SystemName;
    icon: IconName;
  }[] = [
    {
      label: "Response delivered",
      done: !!delivery,
      reference: delivery ? refLabel("outbox", delivery.id) : undefined,
      detail: delivery
        ? `To ${String((delivery.sent_content as Row)?.recipient ?? "")}`
        : "No delivery recorded yet",
      system: "secure",
      icon: "send",
    },
    {
      label: "Package indexed in OnBase",
      done: !!pkg,
      reference: pkg ? refLabel("package", pkg.id) : undefined,
      detail: pkg
        ? `${String((pkg.index_fields as Row)?.correspondence_type ?? "")} · ${String((pkg.index_fields as Row)?.page_count ?? "")} pages`
        : "Indexed after delivery",
      system: "onbase",
      icon: "file",
    },
    {
      label: "Final servicing note in ILS",
      done: !!note,
      reference: note ? refLabel("note", note.id) : undefined,
      detail: note
        ? `${String(note.department)} · ${String(note.note_type)}`
        : "Recorded after indexing",
      system: "ils",
      icon: "edit",
    },
    {
      label: transferred ? "Transferred in CCT" : "Case closed in CCT",
      done: closed || transferred,
      detail: closed
        ? `Closed ${instant(data.case.updated_at, false)}`
        : transferred
          ? "Specialist handoff acknowledged"
          : "Closes only when the items above verify",
      system: "cct",
      icon: "check",
    },
  ];
  const complete = items.filter((i) => i.done).length;
  return (
    <section className="sx-checklist" aria-label="Closure checklist">
      <header>
        <h3>Closure checklist</h3>
        <span
          className={`desk-badge ${complete === items.length ? "good" : "neutral"}`}
        >
          {complete} of {items.length} verified
        </span>
      </header>
      <ul>
        {items.map((item) => (
          <li key={item.label} className={item.done ? "done" : "todo"}>
            <span className="sx-check" aria-hidden="true">
              {item.done ? (
                <DeskIcon name="check" size={13} />
              ) : (
                <DeskIcon name={item.icon} size={13} />
              )}
            </span>
            <div>
              <strong>{item.label}</strong>
              <small>{item.detail}</small>
              {item.reference && (
                <code className="sx-ref" title={item.reference}>
                  {item.reference}
                </code>
              )}
            </div>
            {onOpenSystem && item.system !== "cct" && (
              <button
                className="text-button sx-open"
                onClick={() => onOpenSystem(item.system)}
              >
                Open {SYSTEM_NAMES[item.system]}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/* ─── Correspondence and case record ──────────────────────────────────── */

export function Paragraphs({ text }: { text: string }) {
  return (
    <div className="sx-letter">
      {displayText(text)
        .split(/\n\s*\n/)
        .map((block, index) => (
          <p key={index}>
            {block.split("\n").map((line, i, lines) => (
              <span key={i}>
                {line}
                {i < lines.length - 1 && <br />}
              </span>
            ))}
          </p>
        ))}
    </div>
  );
}

function EmailCard({ data }: { data: SystemCase }) {
  const mail = data.events.find((e) => e.kind === "mail.received");
  const from = mail
    ? String(mail.actor)
    : String((data.loan.context as Row)?.authorized_recipient ?? "");
  const channel = String(
    ((data.case.routing as Row | null)?.inputs as Row | undefined)?.channel ??
      "email",
  );
  return (
    <article className="sx-card" aria-label="Correspondence">
      <header className="sx-card-head">
        <h3>Correspondence</h3>
        <span className="desk-badge neutral">{sentence(channel)}</span>
      </header>
      <dl className="sx-mail-head">
        <div>
          <dt>From</dt>
          <dd>
            {data.case.borrower_display_name} &lt;{from}&gt;
          </dd>
        </div>
        <div>
          <dt>Subject</dt>
          <dd>{data.case.subject}</dd>
        </div>
        <div>
          <dt>Received</dt>
          <dd>{instant(data.case.original_received_at)}</dd>
        </div>
      </dl>
      <Paragraphs text={data.case.correspondence_text} />
      {data.thread && (
        <p className="sx-hint">
          <DeskIcon name="mail" size={13} /> Replies, approvals and specialist
          results continue this case automatically.
        </p>
      )}
    </article>
  );
}

function CaseRecord({
  data,
  assessment,
}: {
  data: SystemCase;
  assessment?: Assessment;
}) {
  const c = data.case.classification as Row | null;
  const routing = (assessment?.routing ?? data.case.routing) as Row | null;
  const inputs = (routing?.inputs ?? {}) as Row;
  const aging = (routing?.aging ?? {}) as Row;
  const age = typeof aging.workdays === "number" ? aging.workdays : null;
  const dispute = routing?.assessment === "dispute";
  return (
    <article className="sx-card" aria-label="Case record">
      <header className="sx-card-head">
        <h3>Case record</h3>
        <code className="sx-ref">{data.case.ccid}</code>
      </header>
      <div className="sx-breadcrumb" title={c ? String(c.id ?? "") : undefined}>
        <span className="sx-mini-label">Classification</span>
        {c ? (
          <p>
            {[c.work_type, c.class_name, c.subclass]
              .filter(Boolean)
              .map((part, i) => (
                <span key={i}>
                  {i > 0 && <DeskIcon name="chevron" size={11} />}
                  {String(part)}
                </span>
              ))}
          </p>
        ) : unmapped(assessment) ? (
          <p className="sx-warn">
            No approved classification for this request. The case stays with a
            supervisor until one is assigned.
          </p>
        ) : (
          <p className="sx-muted">Awaiting classification</p>
        )}
      </div>
      <dl className="sx-grid-facts">
        <div>
          <dt>Owner</dt>
          <dd>{actorName(data.case.owner)}</dd>
        </div>
        <div>
          <dt>Queue / team</dt>
          <dd>
            {String(inputs.queue ?? routing?.route ?? "Not routed")}
            {inputs.assigned_team && inputs.assigned_team !== inputs.queue
              ? ` · ${String(inputs.assigned_team)}`
              : ""}
          </dd>
        </div>
        <div title={String(routing?.reason ?? "")}>
          <dt>Route</dt>
          <dd>
            {String(routing?.route ?? "Requires review")}
            {routing?.rule ? (
              <small className="sx-muted"> · {String(routing.rule)}</small>
            ) : null}
          </dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{statusLabel(data.case.status)}</dd>
        </div>
      </dl>
      <div className="sx-aging" aria-label="Aging">
        <div className="sx-aging-head">
          <span className="sx-mini-label">Aging</span>
          <strong>
            {age === null ? "Clock exception" : `Workday ${age} of 20`}
          </strong>
        </div>
        <div className="sx-aging-bar" aria-hidden="true">
          {Array.from({ length: 20 }, (_, i) => (
            <i
              key={i}
              className={
                age !== null && i < age
                  ? age >= 15
                    ? "late"
                    : age >= 10
                      ? "warn"
                      : "used"
                  : ""
              }
            />
          ))}
        </div>
        <small className="sx-muted">
          Eastern Monday–Friday workdays from receipt on{" "}
          {aging.received_eastern_date
            ? calendarDate(aging.received_eastern_date)
            : "the original date"}
          .{" "}
          {dispute
            ? "The 20-workday dispute limit applies."
            : "The 20-workday dispute limit does not apply to this inquiry."}
        </small>
      </div>
    </article>
  );
}

/* ─── Timeline ────────────────────────────────────────────────────────── */

type Tag = "mail" | "agent" | "system" | "people";
type Entry = {
  key: string;
  at: string;
  title: string;
  detail?: string;
  actor: string;
  tags: Tag[];
  icon: IconName;
  tone: "good" | "warn" | "bad" | "neutral" | "run";
  system?: string;
  duration?: string;
  reference?: string;
  tool?: string;
  start?: string;
};

const OPERATION_TITLES: Record<string, string> = {
  "cct.apply_plan": "CCT plan recorded",
  "cct.close": "CCT case closed",
  "cct.handoff": "CCT handoff recorded",
  "csp.prepare": "Response draft saved",
  "csp.send": "Response delivered",
  "onbase.index": "OnBase package indexed",
  "ils.final_note": "ILS note recorded",
  "ils.task": "ILS task recorded",
  "ils.update": "ILS record updated",
};

function buildEntries(data: SystemCase): Entry[] {
  const events = [...data.events].sort(
    (a, b) => Number(a.sequence) - Number(b.sequence),
  );
  const entries: Entry[] = [];
  const open: Entry[] = [];
  let run = 0;
  for (const event of events) {
    const p = (event.payload ?? {}) as Row;
    const at = String(event.created_at);
    const actor = actorName(event.actor);
    switch (event.kind) {
      case "case.created":
        entries.push({
          key: `e${event.sequence}`,
          at,
          title: "Case created",
          detail: "Assigned a CCID and added to the servicing worklist",
          actor,
          tags: [],
          icon: "cases",
          tone: "neutral",
        });
        break;
      case "mail.received":
        entries.push({
          key: `e${event.sequence}`,
          at,
          title: "Email received",
          detail: String(p.subject ?? ""),
          actor: String(event.actor),
          tags: ["mail"],
          icon: "mail",
          tone: "neutral",
        });
        break;
      case "agent.queued":
        run += 1;
        entries.push({
          key: `e${event.sequence}`,
          at,
          title: `Agent run ${run} started`,
          detail: p.resumed_from
            ? "Resumed from the previous run"
            : `${sentence(p.mode ?? "automatic")} mode`,
          actor,
          tags: ["agent"],
          icon: "follow",
          tone: "run",
        });
        break;
      case "agent.tool_planned": {
        const tool = String(p.tool);
        const entry: Entry = {
          key: `e${event.sequence}`,
          at,
          title: toolTitle(tool),
          actor,
          tags: ["agent"],
          icon: "follow",
          tone: "neutral",
          system: SYSTEM_NAMES[systemForTool(tool)],
          tool,
          start: at,
        };
        entries.push(entry);
        open.push(entry);
        break;
      }
      case "simulator.action": {
        const target = open.at(-1);
        const operation = String(p.operation ?? "");
        if (target) {
          target.tags = [...new Set([...target.tags, "system" as Tag])];
          target.detail = OPERATION_TITLES[operation] ?? sentence(operation);
          target.icon = "check";
        }
        break;
      }
      case "agent.tool_result": {
        const tool = String(p.tool);
        let index = -1;
        for (let i = open.length - 1; i >= 0; i--)
          if (open[i].tool === tool) {
            index = i;
            break;
          }
        const target = index >= 0 ? open.splice(index, 1)[0] : undefined;
        if (!target) break;
        const status = String(p.status ?? "");
        const ok = ["ok", "simulated_complete"].includes(status);
        target.tone = ok ? "good" : status === "rejected" ? "bad" : "warn";
        if (!target.detail || !ok) target.detail = displayText(p.message);
        const start = new Date(target.start ?? at).valueOf();
        const ms = new Date(at).valueOf() - start;
        if (ms >= 0) target.duration = ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
        const reference = p.reference as Row | null;
        if (reference?.id)
          target.reference = refLabel(reference.kind, reference.id);
        break;
      }
      case "agent.finished":
        entries.push({
          key: `e${event.sequence}`,
          at,
          title: `Agent run ${run || ""} finished`.replace("  ", " "),
          detail: `${sentence(p.status)} · ${sentence(p.reason)}`,
          actor,
          tags: ["agent"],
          icon: p.status === "completed" ? "check" : "clock",
          tone: "run",
        });
        break;
      case "agent.started":
        break;
      default:
        entries.push({
          key: `e${event.sequence}`,
          at,
          title:
            (
              {
                "input.received": "Evidence received",
                "response.reviewed": "Response reviewed",
                "handoff.acknowledged": "Specialist receipt acknowledged",
              } as Record<string, string>
            )[String(event.kind)] ??
            sentence(String(event.kind).replaceAll(".", " ")),
          detail: p.operation
            ? `${OPERATION_TITLES[String(p.operation)] ?? sentence(p.operation)} · ${sentence(p.status)}`
            : undefined,
          actor,
          tags: ["people"],
          icon: "user",
          tone: "neutral",
        });
    }
  }
  return entries;
}

const FILTERS: [Tag | "all", string][] = [
  ["all", "All"],
  ["mail", "Mail"],
  ["agent", "AI agent"],
  ["system", "System actions"],
  ["people", "People"],
];

function CaseTimeline({ data }: { data: SystemCase }) {
  const [filter, setFilter] = useState<Tag | "all">("all");
  const [newestFirst, setNewestFirst] = useState(true);
  const entries = useMemo(() => buildEntries(data), [data]);
  const shown = entries.filter((e) => filter === "all" || e.tags.includes(filter));
  const ordered = newestFirst ? [...shown].reverse() : shown;
  return (
    <article className="sx-card sx-timeline-card" aria-label="Case timeline">
      <header className="sx-card-head">
        <h3>Case timeline</h3>
        <button
          className="text-button"
          onClick={() => setNewestFirst(!newestFirst)}
        >
          {newestFirst ? "Newest first" : "Oldest first"}
        </button>
      </header>
      <div className="sx-chips" role="group" aria-label="Timeline filter">
        {FILTERS.map(([value, text]) => {
          const count =
            value === "all"
              ? entries.length
              : entries.filter((e) => e.tags.includes(value)).length;
          return (
            <button
              key={value}
              className={filter === value ? "selected" : ""}
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
              disabled={!count}
            >
              {text} <span>{count}</span>
            </button>
          );
        })}
      </div>
      <ol className="sx-timeline">
        {ordered.map((e) => (
          <li key={e.key} className={`tone-${e.tone}`}>
            <span className="sx-tl-icon" aria-hidden="true">
              <DeskIcon name={e.icon} size={13} />
            </span>
            <div>
              <div className="sx-tl-title">
                <strong>{e.title}</strong>
                {e.system && <span className="sx-sys">{e.system}</span>}
              </div>
              {e.detail && <p>{e.detail}</p>}
              <small>
                {clock(e.at)} · {e.actor}
                {e.duration ? ` · ${e.duration}` : ""}
                {e.reference ? (
                  <>
                    {" · "}
                    <code className="sx-ref">{e.reference}</code>
                  </>
                ) : null}
              </small>
            </div>
          </li>
        ))}
        {!ordered.length && <li className="sx-empty">No events of this type.</li>}
      </ol>
    </article>
  );
}
