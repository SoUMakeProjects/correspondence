import type { SystemCase } from "./api/client";
import {
  clientName,
  displayLabel,
  displayText,
  displayValue,
} from "./presentation";

type Row = Record<string, unknown>;
export const label = (value: unknown) => {
  const text = displayLabel(value);
  return text ? text[0].toUpperCase() + text.slice(1) : "Not recorded";
};
export const when = (value: unknown) =>
  value
    ? new Intl.DateTimeFormat("en-US", {
        timeZone: "America/New_York",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }).format(new Date(String(value)))
    : "Not recorded";

export function CaseIdentity({ data }: { data: SystemCase }) {
  return (
    <div className="system-case-identity">
      <div>
        <span className="eyebrow">
          {data.case.ccid} · {clientName(data.case.client_code)}
        </span>
        <h2>{data.case.subject}</h2>
        <p>
          {data.case.borrower_display_name} <span>·</span> Loan{" "}
          {data.case.loan_identifier}
        </p>
      </div>
      <span className={`status-pill ${data.case.status}`}>
        {label(data.case.status)}
      </span>
      {!data.thread && (
        <a
          className="text-button"
          href="/?workspace=classic"
          onClick={() =>
            localStorage.setItem("correspondence.selectedCase", data.case.id)
          }
        >
          Open earlier case controls
        </a>
      )}
    </div>
  );
}

export function Facts({ values }: { values: Row }) {
  return (
    <dl className="system-facts">
      {Object.entries(values)
        .filter(
          ([key, value]) =>
            ![
              "synthetic",
              "simulated",
              "borrower_email",
              "result_source",
            ].includes(key) &&
            value !== null &&
            typeof value !== "object",
        )
        .map(([key, value]) => (
          <div key={key}>
            <dt>{label(key)}</dt>
            <dd>
              {typeof value === "boolean"
                ? value
                  ? "Yes"
                  : "No"
                : key.endsWith("_minor") && typeof value === "number"
                  ? new Intl.NumberFormat("en-US", {
                      style: "currency",
                      currency: "USD",
                    }).format(value / 100)
                  : displayValue(value)}
            </dd>
          </div>
        ))}
    </dl>
  );
}

export { default as CctView } from "./systems/CctView";

export { default as IlsView } from "./systems/IlsView";

export { default as OnbaseView, packageUrl } from "./systems/OnbaseView";

export function SecureMailView({ data }: { data: SystemCase }) {
  return (
    <section aria-label="Secure mail workspace" className="system-panel">
      <CaseIdentity data={data} />
      <div className="system-section">
        <h3>Delivery history</h3>
        {!data.outbox.length && (
          <p className="empty-copy">
            Responses appear here after delivery. Any required approval is
            completed during response review.
          </p>
        )}
        {[...data.outbox].reverse().map((entry) => {
          const content = entry.sent_content as Row;
          return (
            <article className="mail-card" key={String(entry.id)}>
              <div className="card-title">
                <h4>Response version {String(content.draft_version)}</h4>
                <span className="status-pill">{label(entry.status)}</span>
              </div>
              <p>
                From: {String(content.sender)}
                <br />
                To: {String(content.recipient)}
              </p>
              <time>{when(entry.created_at)} · Eastern time</time>
              <pre className="response-preview">
                {displayText(content.body)}
              </pre>
              {((content.attachments as Row[]) ?? []).map((a) => (
                <span className="attachment-chip" key={String(a.evidence_id)}>
                  PDF · {displayValue(a.title)}
                </span>
              ))}
              <details>
                <summary>Delivery receipt</summary>
                <p className="artifact-reference">
                  {String(entry.delivery_reference)}
                </p>
                <p>Draft: {String(entry.draft_id)}</p>
              </details>
            </article>
          );
        })}
      </div>
    </section>
  );
}
