import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Assessment, SystemCase, Workflow } from "../api/client";
import CaseWorkflow from "../CaseWorkflow";
import { packageUrl } from "../SystemViews";
import { clientName, displayText, displayValue } from "../presentation";
import DeskIcon from "./DeskIcon";
import { dateTime, isActive, shortTime, titleCase } from "./deskFormat";
import type { DeskDraft, Row } from "./deskFormat";
import { REVIEWER } from "../auth/reviewer";

export default function ResponsePanel({
  data,
  workflow,
  assessment,
  onChanged,
}: {
  data: SystemCase;
  workflow: Workflow;
  assessment: Assessment;
  onChanged: () => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const actor = REVIEWER.name;
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const hasNote = !!note.trim();
  useEffect(() => {
    if (hasNote) setNotesOpen(true);
  }, [hasNote]);
  const editDialog = useRef<HTMLDialogElement>(null);
  const returnDialog = useRef<HTMLDialogElement>(null);
  const drafts = workflow.drafts as DeskDraft[];
  const draft = drafts.find((d) => d.id === selected) ?? drafts.at(-1);
  const running = data.runs.some(isActive);
  const current = !!draft?.current && draft.id === drafts.at(-1)?.id;
  const canReview =
    !!draft &&
    current &&
    !draft.sent &&
    !running &&
    data.case.status !== "closed";
  const label = !draft
    ? "Not drafted"
    : draft.sent
      ? "Delivered"
      : !current
        ? "Earlier version"
        : draft.approved
          ? "Approved"
          : draft.returned
            ? "Returned"
            : draft.review_required
              ? "Awaiting review"
              : "Ready to send";
  const rawDraft = data.drafts.find((d) => d.id === draft?.id);
  const delivery = data.outbox.find((entry) => entry.draft_id === draft?.id);
  const archived = data.packages.find(
    (record) => (record.index_fields as Row).draft_id === draft?.id,
  );
  const attachments = delivery
    ? (((delivery.sent_content as Row).attachments as Row[]) ?? []).map(
        (attachment) => ({
          id: String(attachment.evidence_id),
          title: attachment.title,
        }),
      )
    : (draft?.candidate.attachment_ids
        .map((id) => data.evidence.find((e) => e.id === id))
        .filter((e) => !!e) ?? []);
  async function review(decision: "approve" | "return") {
    if (!draft || !canReview || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api.review(data.case.id, {
        request_id: crypto.randomUUID(),
        expected_case_revision: data.case.revision,
        draft_id: draft.id,
        draft_version: draft.version,
        decision,
        actor,
        note,
      });
      returnDialog.current?.close();
      // The note belongs to this decision; don't carry it to the next version.
      setNote("");
      setNotesOpen(false);
      setNotice(
        decision === "approve"
          ? data.thread
            ? "Approved. The agent will continue delivery automatically."
            : "This response version is approved."
          : "Returned with your feedback. The agent will prepare a revision.",
      );
      onChanged();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The decision could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  }
  function edit() {
    setEditing(true);
    editDialog.current?.showModal();
  }
  const attachmentList = (
    <div className="response-attachments">
      {!attachments.length ? (
        <span className="desk-muted">
          <DeskIcon name="link" size={14} /> No attachments
        </span>
      ) : (
        <>
          <h3>
            <DeskIcon name="link" size={14} /> Attachments ({attachments.length}
            )
          </h3>
          {attachments.map((attachment) => {
            const href = draft?.sent
              ? archived
                ? packageUrl(data, archived.id)
                : undefined
              : `/api/cases/${data.case.id}/evidence/${attachment.id}/file`;
            return (
              <div className="desk-file-chip" key={String(attachment.id)}>
                <DeskIcon name="file" size={16} />
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  title={`Preview ${displayValue(attachment.title)}`}
                >
                  {displayValue(attachment.title)}
                  <small>
                    {draft?.sent
                      ? archived
                        ? "Sent response package"
                        : "Delivery recorded · awaiting archive"
                      : "PDF"}
                  </small>
                </a>
                {href && (
                  <a
                    className="desk-file-download"
                    href={href}
                    download
                    aria-label={`Download ${displayValue(attachment.title)}`}
                    title="Download"
                  >
                    <DeskIcon name="download" size={15} />
                  </a>
                )}
              </div>
            );
          })}
        </>
      )}
    </div>
  );
  const handoff = !!workflow.handoffs.length && (
    <div className="desk-inline-handoff">
      <CaseWorkflow
        item={data.case}
        running={running}
        onChanged={onChanged}
        automatic={!!data.thread}
        section="handoff"
      />
    </div>
  );
  return (
    <section
      className="desk-card response-card"
      aria-label="Response draft and review"
    >
      <header className="desk-card-heading">
        <h2>Response draft</h2>
        {draft &&
          (drafts.length > 1 ? (
            <select
              className="draft-version"
              aria-label="Response version"
              value={draft.id}
              onChange={(e) => {
                setSelected(e.target.value);
                setError("");
                setNotice("");
              }}
            >
              {[...drafts].reverse().map((d) => (
                <option key={d.id} value={d.id}>
                  Version {d.version}
                </option>
              ))}
            </select>
          ) : (
            <span className="draft-version-label">v{draft.version}</span>
          ))}
        <span
          className={`desk-badge ${draft?.sent ? "good" : draft?.review_required && current && !draft.approved ? "amber" : "blue"}`}
        >
          <i />
          {label}
        </span>
      </header>
      {error && (
        <p className="desk-alert" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="desk-notice" role="status">
          {notice}
        </p>
      )}
      {draft ? (
        <>
          <div className="response-body">
            <div className="response-paper-wrap">
              <article className="response-paper" aria-label="Response letter">
                <div className="letter-mark">
                  <span>{clientName(data.case.client_code)}</span>
                  {!!rawDraft?.created_at && (
                    <time>{dateTime(rawDraft.created_at)}</time>
                  )}
                </div>
                <p className="letter-recipient">To: {draft.recipient}</p>
                <p className="letter-subject">
                  Re: {data.case.subject}
                  <small>Loan {data.case.loan_identifier}</small>
                </p>
                <div className="letter-body">{displayText(draft.body)}</div>
                <footer>
                  Correspondence Services
                  <span>{clientName(data.case.client_code)}</span>
                </footer>
              </article>
            </div>
            {!!draft.findings.length && !draft.sent && (
              <details className="response-findings" open>
                <summary>
                  <DeskIcon name="shield" size={15} /> Validation findings (
                  {draft.findings.length})
                </summary>
                {draft.findings.map((finding, i) => (
                  <p key={i}>{displayText(finding.message)}</p>
                ))}
              </details>
            )}
            <div className="response-coverage">
              <h3>Concern coverage</h3>
              <ul>
                {draft.candidate.concerns.map((concern) => (
                  <li key={concern.concern_id}>
                    <span
                      className={
                        concern.disposition === "resolved"
                          ? "coverage-check"
                          : "coverage-wait"
                      }
                    >
                      <DeskIcon
                        name={
                          concern.disposition === "resolved" ? "check" : "clock"
                        }
                        size={12}
                      />
                    </span>
                    <span>
                      {assessment.concerns.find(
                        (c) => c.concern_id === concern.concern_id,
                      )?.description ?? titleCase(concern.concern_id)}
                      <small>{titleCase(concern.disposition)}</small>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            {attachmentList}
            {draft.sent && delivery && (
              <div className="response-delivered">
                <DeskIcon name="check" size={15} />
                <span>
                  Delivered {dateTime(delivery.created_at)} at{" "}
                  {shortTime(delivery.created_at)} ET
                </span>
              </div>
            )}
            {!current && !draft.sent && (
              <p className="desk-panel-note">
                This version is outdated. Select the latest response to review
                current evidence.
              </p>
            )}
            {handoff}
          </div>
          {current && !draft.sent && (
            <div className="response-review-controls">
              <details
                className="reviewer-options"
                open={notesOpen}
                onToggle={(e) => setNotesOpen(e.currentTarget.open)}
              >
                <summary>Reviewer &amp; notes</summary>
                <p className="reviewer-line">
                  Reviewer <strong>{actor}</strong>
                </p>
                <label>
                  Review note
                  <textarea
                    aria-label="Review note"
                    value={note}
                    disabled={busy}
                    onChange={(e) => setNote(e.target.value)}
                    maxLength={4000}
                  />
                </label>
              </details>
              <div className="response-action-bar">
                <button
                  className="desk-button primary"
                  disabled={
                    !canReview || busy || draft.approved || !actor.trim()
                  }
                  onClick={() => void review("approve")}
                >
                  {busy
                    ? "Saving…"
                    : data.thread
                      ? "Approve and send"
                      : "Approve this version"}
                </button>
                <button
                  className="desk-button"
                  disabled={!canReview || busy}
                  onClick={edit}
                >
                  <DeskIcon name="edit" size={14} />
                  Edit draft
                </button>
                <button
                  className="desk-button quiet"
                  disabled={!canReview || busy}
                  onClick={() => returnDialog.current?.showModal()}
                >
                  Return
                </button>
              </div>
              {running && (
                <p className="desk-panel-note">
                  The agent is processing. Review actions become available at a
                  pause.
                </p>
              )}
            </div>
          )}
        </>
      ) : (
        <div className="response-body">
          <div className="response-awaiting">
            <span className="desk-icon-tile">
              <DeskIcon name="edit" size={30} />
            </span>
            <h3>
              {running
                ? "A response is taking shape"
                : "No response drafted yet"}
            </h3>
            <p>
              {running
                ? "The agent is reviewing the request and supporting evidence. Its draft will appear here."
                : "The current case may be awaiting evidence or a specialist decision."}
            </p>
          </div>
          {handoff}
        </div>
      )}
      <dialog
        className="desk-dialog desk-edit-dialog"
        ref={editDialog}
        onClose={() => setEditing(false)}
      >
        <header>
          <h2>Edit supported response</h2>
          <button
            className="desk-icon-button"
            aria-label="Close draft editor"
            onClick={() => editDialog.current?.close()}
          >
            <DeskIcon name="close" />
          </button>
        </header>
        {editing && (
          <div className="desk-dialog-body">
            <CaseWorkflow
              key={draft?.id}
              item={data.case}
              running={running}
              section="review"
              editorOnly
              automatic={!!data.thread}
              onCancel={() => editDialog.current?.close()}
              onChanged={() => {
                setSelected(null);
                onChanged();
                editDialog.current?.close();
              }}
            />
          </div>
        )}
      </dialog>
      <dialog className="desk-dialog" ref={returnDialog}>
        <header>
          <h2>Return response for changes</h2>
          <button
            className="desk-icon-button"
            aria-label="Close return dialog"
            disabled={busy}
            onClick={() => returnDialog.current?.close()}
          >
            <DeskIcon name="close" />
          </button>
        </header>
        <div className="desk-dialog-body">
          <p>
            Explain what the agent should reconsider before preparing a new
            version.
          </p>
          <label>
            Review feedback
            <textarea
              aria-label="Return feedback"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={4000}
              disabled={busy}
            />
          </label>
          <p className="desk-field-hint" aria-live="polite">
            {note.trim()
              ? `${note.trim().length} / 4000 characters`
              : "Add feedback to continue."}
          </p>
          {error && (
            <p className="desk-alert" role="alert">
              {error}
            </p>
          )}
        </div>
        <footer className="desk-dialog-footer">
          <button
            className="desk-button quiet"
            disabled={busy}
            onClick={() => returnDialog.current?.close()}
          >
            Cancel
          </button>
          <button
            className="desk-button primary"
            disabled={!canReview || busy || !note.trim() || !actor.trim()}
            onClick={() => void review("return")}
          >
            Return for changes
          </button>
        </footer>
      </dialog>
    </section>
  );
}
