import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { Assessment, Case, Validation } from "./api/client";
import { displayLabel as readable, displayText } from "./presentation";

export default function CaseAssessment({
  item,
  onRecorded,
  readOnly = false,
}: {
  item: Case;
  onRecorded: () => void;
  readOnly?: boolean;
}) {
  const [report, setReport] = useState<Assessment | null>(null);
  const [completion, setCompletion] = useState<Validation | null>(null);
  const [historyCount, setHistoryCount] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setReport(null);
    setCompletion(null);
    setError("");
    Promise.all([
      api.assessment(item.id, controller.signal),
      api.completion(item.id, controller.signal),
      api.assessmentHistory(item.id, controller.signal),
    ])
      .then(([assessment, checked, history]) => {
        if (controller.signal.aborted) return;
        setReport(assessment);
        setCompletion(checked);
        setHistoryCount(history.length);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "Assessment could not be loaded.",
          );
      });
    return () => controller.abort();
  }, [item.id, item.revision]);

  async function record() {
    setBusy(true);
    setError("");
    try {
      await api.recordAssessment(item.id, item.revision);
      onRecorded();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Assessment could not be recorded.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="case-assessment" aria-label="Business assessment">
      <div className="assessment-heading">
        <div>
          <h3>Business assessment</h3>
          <p className="resource-note">
            Recommended handling based on case evidence and business rules.
          </p>
        </div>
        {!readOnly && (
          <button
            className="secondary-button"
            disabled={!report || busy}
            onClick={record}
          >
            {busy ? "Recording…" : "Record assessment"}
          </button>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
      {!report && !error && <p role="status">Checking business rules…</p>}
      {report && (
        <>
          <dl className="assessment-facts">
            <div>
              <dt>Recommended handling</dt>
              <dd>{readable(report.disposition)}</dd>
            </div>
            <div>
              <dt>Route</dt>
              <dd>{report.routing.route ?? "Requires review"}</dd>
            </div>
            <div>
              <dt>Age from original receipt</dt>
              <dd>
                {report.routing.aging.workdays === null
                  ? "Clock exception"
                  : `${report.routing.aging.workdays} Eastern workdays`}
              </dd>
            </div>
            <div>
              <dt>Response review</dt>
              <dd>
                {report.review_required
                  ? "Required for this client"
                  : "Automatic processing permitted"}
              </dd>
            </div>
          </dl>
          <p>{displayText(report.routing.reason)}</p>
          <p className="resource-note">{report.routing.aging.reason}</p>
          <p>
            <strong>Recipient:</strong>{" "}
            {report.authorized_recipient ?? "Requires verification"}
          </p>
          <ul className="assessment-actions">
            {report.permitted_actions.map((action) => (
              <li key={action}>{displayText(action)}</li>
            ))}
          </ul>
          <h4>Concern dispositions</h4>
          <ul className="resource-list">
            {report.concerns.map((concern) => (
              <li key={concern.concern_id}>
                <strong>{concern.description}</strong>
                <span>
                  {readable(concern.disposition)} ·{" "}
                  {displayText(concern.reason)}
                </span>
                {concern.owner && (
                  <span>
                    Owner: {readable(concern.owner)} · Next review:{" "}
                    {new Date(concern.next_review_at!).toLocaleString("en-US", {
                      timeZone: "America/New_York",
                      timeZoneName: "short",
                    })}
                  </span>
                )}
                {concern.resume_requirement && (
                  <span>
                    To resume: {displayText(concern.resume_requirement)}
                  </span>
                )}
              </li>
            ))}
          </ul>
          {report.findings.length > 0 && (
            <details open className="assessment-findings">
              <summary>
                Exceptions and prerequisites ({report.findings.length})
              </summary>
              <ul>
                {report.findings.map((finding, index) => (
                  <li key={`${finding.code}-${index}`}>
                    <strong>{readable(finding.code)}</strong>:{" "}
                    {displayText(finding.message)}
                    <small>
                      {finding.rule}
                      {finding.blocks?.length
                        ? ` · Blocks ${finding.blocks.map(readable).join(", ")}`
                        : ""}
                    </small>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {completion && (
            <details className="assessment-findings">
              <summary>
                Completion check:{" "}
                {completion.valid
                  ? "Prerequisites met"
                  : "Prerequisites outstanding"}
              </summary>
              <ul>
                {completion.findings.map((finding, index) => (
                  <li key={`${finding.code}-${index}`}>
                    {displayText(finding.message)}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <details className="assessment-findings">
            <summary>
              Decision evidence · {historyCount} recorded{" "}
              {historyCount === 1 ? "assessment" : "assessments"}
            </summary>
            <p>
              Rule: {report.routing.rule} · Policy: {report.policy_version} ·
              Case revision: {report.case_revision}
            </p>
            <p>
              Eastern receipt date:{" "}
              {report.routing.aging.received_eastern_date ?? "Invalid"} ·
              Evaluation date:{" "}
              {report.routing.aging.evaluation_eastern_date ?? "Invalid"}
            </p>
            <p>Calendar: {report.routing.aging.calendar_version}</p>
            <p>
              Classification:{" "}
              {report.classification
                ? [
                    report.classification.work_type,
                    report.classification.class_name,
                    report.classification.subclass,
                  ].join(" / ")
                : "Mapping requires review"}
            </p>
            <p className="resource-note">
              Input fingerprint: {report.input_hash}
            </p>
          </details>
        </>
      )}
    </section>
  );
}
