import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { Assessment, SystemCase } from "../api/client";
import { clientName, displayValue } from "../presentation";
import DeskIcon from "../desk/DeskIcon";
import PdfPreview from "../mailbox/PdfPreview";
import type { SystemName } from "../desk/ActivityTimeline";
import { calendarDate, instant, refLabel, sentence, shortId } from "./format";
import type { Row } from "./format";
import "./systems.css";

export function packageUrl(data: SystemCase, identity: unknown) {
  return `/api/simulations/${data.case.simulation_id}/cases/${data.case.id}/packages/${String(identity)}/file?${new URLSearchParams({ loan_identifier: data.case.loan_identifier, client_code: data.case.client_code })}`;
}

type Props = {
  data: SystemCase;
  assessment?: Assessment;
  onOpenSystem?: (system: SystemName) => void;
};
type Preview = { title: string; url: string; key: string };

const KIND: Record<string, string> = {
  amortization_schedule: "Amortization schedule",
  document: "Supporting document",
  mail_attachment: "Email attachment",
};

const hash = (value: unknown) =>
  value ? String(value).slice(0, 12).toUpperCase() : "—";

function sourceLabel(e: Row) {
  const details = (e.details ?? {}) as Row;
  if (details.origin === "mail_upload" || e.source === "Email")
    return "Borrower email";
  if (String(e.source ?? "").startsWith("Presenter")) return "Supplied evidence";
  return "OnBase repository";
}

export default function OnbaseView({ data, assessment, onOpenSystem }: Props) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const documents = data.evidence.filter(
    (e) => (e.details as Row).kind !== "record",
  );
  const checks = new Map(
    (assessment?.attachments ?? []).map((a) => [a.evidence_id, a]),
  );
  // Every sent copy of each source document, for "used in" and the document trail.
  const usage = useMemo(() => {
    const map = new Map<
      string,
      { version: number; at: string; sha: string; outbox: string }[]
    >();
    for (const entry of data.outbox) {
      const content = (entry.sent_content ?? {}) as Row;
      for (const a of (content.attachments as Row[]) ?? []) {
        const list = map.get(String(a.evidence_id)) ?? [];
        list.push({
          version: Number(content.draft_version),
          at: String(entry.created_at),
          sha: String(a.sha256 ?? ""),
          outbox: String(entry.id),
        });
        map.set(String(a.evidence_id), list);
      }
    }
    return map;
  }, [data.outbox]);
  const exceptions = documents.filter((d) => {
    const check = checks.get(String(d.id));
    return (
      (d.details as Row).availability !== "available" ||
      (check && !check.valid)
    );
  }).length;
  const open = (next: Preview) =>
    setPreview(preview?.key === next.key ? null : next);

  return (
    <section
      aria-label="OnBase document workspace"
      className="system-panel sx-panel"
    >
      <div className="sx-loan-summary sx-onbase-summary">
        <div className="sx-loan-id">
          <span className="sx-mini-label">Sherman ID</span>
          <strong>{data.case.loan_identifier}</strong>
          <small>
            CCID {data.case.ccid} · {clientName(data.case.client_code)}
          </small>
        </div>
        <div className="sx-metric">
          <span className="sx-mini-label">Source documents</span>
          <strong>{documents.length}</strong>
        </div>
        <div className="sx-metric">
          <span className="sx-mini-label">Identity exceptions</span>
          <strong className={exceptions ? "sx-bad" : undefined}>
            {exceptions}
          </strong>
          <small>{exceptions ? "Not usable as attachments" : "All checks passed"}</small>
        </div>
        <div className="sx-metric">
          <span className="sx-mini-label">Indexed packages</span>
          <strong>{data.packages.length}</strong>
          <small>
            {data.packages.length
              ? `Last ${instant(data.packages.at(-1)?.created_at, false)}`
              : "Indexed after delivery"}
          </small>
        </div>
      </div>

      <div className={`sx-onbase-split ${preview ? "with-preview" : ""}`}>
        <div className="sx-stack">
          <article className="sx-card" aria-label="Source documents">
            <header className="sx-card-head">
              <h3>Source documents</h3>
              <span className="sx-muted sx-small">
                Retrieved for loan {data.case.loan_identifier}
              </span>
            </header>
            {!documents.length && (
              <p className="sx-empty">No documents are filed for this case.</p>
            )}
            <table className="sx-table sx-docs">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Sherman ID</th>
                  <th>Received</th>
                  <th>Identity checks</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {documents.map((document) => {
                  const details = document.details as Row;
                  const id = String(document.id);
                  const available = details.availability === "available";
                  const loanOk =
                    String(details.loan_identifier) ===
                    data.case.loan_identifier;
                  const clientOk =
                    String(details.client_code ?? data.case.client_code) ===
                    data.case.client_code;
                  const check = checks.get(id);
                  const url = `/api/cases/${data.case.id}/evidence/${id}/file`;
                  const used = usage.get(id) ?? [];
                  const title = displayValue(document.title);
                  return (
                    <tr
                      key={id}
                      className={preview?.key === id ? "selected" : undefined}
                    >
                      <td>
                        <div className="sx-doc-title">
                          <span className="sx-file">PDF</span>
                          <div>
                            <strong>{title}</strong>
                            <small>
                              {KIND[String(details.kind)] ?? sentence(details.kind)}{" "}
                              · v{String(document.version)} ·{" "}
                              {sourceLabel(document as Row)}
                            </small>
                            {used.map((u) => (
                              <small className="sx-used" key={u.outbox}>
                                <DeskIcon name="send" size={11} /> Attached to
                                response v{u.version} · delivered{" "}
                                {instant(u.at, false)}
                              </small>
                            ))}
                          </div>
                        </div>
                      </td>
                      <td>
                        <code className="sx-ref">
                          {String(details.loan_identifier)}
                        </code>
                      </td>
                      <td>
                        {calendarDate(
                          String(
                            document.effective_at ?? document.created_at,
                          ).slice(0, 10),
                        )}
                      </td>
                      <td>
                        <div className="sx-checks">
                          <Chip ok={loanOk}>
                            {loanOk
                              ? "Loan matches"
                              : `Loan ${String(details.loan_identifier)} ≠ ${data.case.loan_identifier}`}
                          </Chip>
                          <Chip ok={clientOk}>Client</Chip>
                          <Chip ok={available}>
                            {available ? "Readable" : sentence(details.availability)}
                          </Chip>
                        </div>
                        {check && !check.valid && (
                          <small className="sx-bad-text">{check.reason}</small>
                        )}
                      </td>
                      <td className="sx-actions">
                        {available && (
                          <>
                            <button
                              className="text-button"
                              onClick={() => open({ title, url, key: id })}
                            >
                              {preview?.key === id ? "Hide" : "Preview"}
                            </button>
                            <a
                              className="text-button"
                              href={url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Open PDF
                            </a>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </article>

          <article className="sx-card" aria-label="Correspondence packages">
            <header className="sx-card-head">
              <h3>Correspondence packages</h3>
              <span className="desk-badge neutral">{data.packages.length}</span>
            </header>
            {!data.packages.length && (
              <p className="sx-empty">
                The sent response and its attachments are indexed here as one
                combined PDF after delivery.
              </p>
            )}
            {[...data.packages].reverse().map((record) => {
              const f = (record.index_fields ?? {}) as Row;
              const outbox = data.outbox.find(
                (o) => String(o.id) === String(f.outbox_id),
              );
              const sent = (outbox?.sent_content ?? {}) as Row;
              const attachments = (sent.attachments as Row[]) ?? [];
              const key = String(record.id);
              const url = packageUrl(data, record.id);
              return (
                <div className="sx-package" key={key}>
                  <div className="sx-task-head">
                    <h4>Indexed response package</h4>
                    <code className="sx-ref">{refLabel("package", record.id)}</code>
                  </div>
                  <div className="sx-package-grid">
                    <dl className="sx-keywords" aria-label="Index keywords">
                      {(
                        [
                          ["Document Type", displayValue(f.document_type)],
                          ["Correspondence Type", f.correspondence_type],
                          ["Sherman ID", f.sherman_id],
                          ["CCID", f.ccid],
                          ["Client", clientName(String(f.client_code))],
                          ["Indexed", instant(record.created_at)],
                          ["Pages", f.page_count],
                          ["Response version", `v${String(f.draft_version)}`],
                        ] as [string, unknown][]
                      ).map(([k, v]) => (
                        <div key={k}>
                          <dt>{k}</dt>
                          <dd>{String(v ?? "—")}</dd>
                        </div>
                      ))}
                    </dl>
                    <div>
                      <span className="sx-mini-label">Package contents</span>
                      <ol className="sx-contents">
                        <li>
                          <DeskIcon name="mail" size={12} />
                          <span>
                            Cover: original correspondence and sent response
                          </span>
                        </li>
                        {attachments.map((a) => (
                          <li key={String(a.evidence_id)}>
                            <DeskIcon name="file" size={12} />
                            <span>Attachment: {displayValue(a.title)}</span>
                          </li>
                        ))}
                      </ol>
                      <span className="sx-mini-label sx-trail-label">
                        Document trail
                      </span>
                      <Trail
                        data={data}
                        record={record as Row}
                        attachments={attachments}
                        onOpenSystem={onOpenSystem}
                      />
                    </div>
                  </div>
                  <div className="workflow-actions">
                    <button
                      className="text-button"
                      onClick={() =>
                        open({ title: "Indexed response package", url, key })
                      }
                    >
                      {preview?.key === key ? "Hide preview" : "Preview package"}
                    </button>
                    <a
                      className="text-button"
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open combined response PDF
                    </a>
                  </div>
                </div>
              );
            })}
          </article>
        </div>
        {preview && (
          <aside className="sx-card sx-preview" aria-label="Document preview">
            <header className="sx-card-head">
              <h3>{preview.title}</h3>
              <button
                className="secondary-button"
                onClick={() => setPreview(null)}
              >
                Close preview
              </button>
            </header>
            <PdfPreview key={preview.url} url={preview.url} />
          </aside>
        )}
      </div>
    </section>
  );
}

function Chip({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <span className={`sx-chip ${ok ? "ok" : "bad"}`}>
      <DeskIcon name={ok ? "check" : "close"} size={10} />
      {children}
    </span>
  );
}

/** Source file → sent attachment → indexed package, with fingerprint checks. */
function Trail({
  data,
  record,
  attachments,
  onOpenSystem,
}: {
  data: SystemCase;
  record: Row;
  attachments: Row[];
  onOpenSystem?: (system: SystemName) => void;
}) {
  const f = (record.index_fields ?? {}) as Row;
  const nodes = attachments.map((a) => {
    const source = data.evidence.find(
      (e) => String(e.id) === String(a.evidence_id),
    );
    return {
      title: displayValue(a.title),
      source: source?.content_sha256,
      sent: a.sha256,
      match: !!source?.content_sha256 && source.content_sha256 === a.sha256,
    };
  });
  return (
    <ol className="sx-trail">
      {nodes.map((n) => (
        <li key={n.title}>
          <div>
            <strong>Source file</strong>
            <code className="sx-ref">{hash(n.source)}</code>
          </div>
          <span className={`sx-arrow ${n.match ? "ok" : "bad"}`}>
            {n.match ? "identical" : "differs"}
          </span>
          <div>
            <strong>
              <button
                className="text-button sx-inline-link"
                disabled={!onOpenSystem}
                onClick={() => onOpenSystem?.("secure")}
              >
                Sent attachment
              </button>
            </strong>
            <code className="sx-ref">{hash(n.sent)}</code>
          </div>
          <span className="sx-arrow ok">combined</span>
          <div>
            <strong>Indexed package</strong>
            <code className="sx-ref">{hash(f.pdf_sha256)}</code>
          </div>
        </li>
      ))}
      {!nodes.length && (
        <li className="sx-empty">No attachments; the package holds the response only.</li>
      )}
      <li className="sx-trail-foot">
        Delivery {refLabel("outbox", f.outbox_id)} · response body fingerprint{" "}
        {hash(f.body_sha256)} · package ID {shortId(record.id)}
      </li>
    </ol>
  );
}
