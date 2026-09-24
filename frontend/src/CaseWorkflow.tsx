import { useEffect, useRef, useState } from "react";
import { REVIEWER } from "./auth/reviewer";
import { api } from "./api/client";
import type {
  Case,
  CaseInput,
  DraftEdit,
  Evidence,
  Task,
  Workflow,
} from "./api/client";
import { displayLabel as readable, displayText } from "./presentation";

// Option labels read as sentences ("Final resolution"), not raw enum names.
const sentence = (value: unknown) => {
  const text = readable(value);
  return text ? text[0].toUpperCase() + text.slice(1) : text;
};

type Draft = {
  id: string;
  version: number;
  current: boolean;
  sent: boolean;
  approved: boolean;
  returned: boolean;
  review_required: boolean;
  recipient: string;
  body: string;
  candidate: Pick<
    DraftEdit,
    "response_type" | "claims" | "concerns" | "attachment_ids"
  >;
  findings: { message: string }[];
};
type Handoff = {
  id: string;
  route: string;
  owner: string;
  status: string;
  current: boolean;
  acknowledged_by: string | null;
  restrictions: string[];
  routing_note?: string | null;
  acknowledgment_note?: string | null;
};
const labels: Record<string, string> = {
  name_legal_document: "Supply legal name-change document",
  tax_specialist_result: "Supply Tax Team result",
  bankruptcy_specialist_result: "Supply bankruptcy specialist determination",
  eft_clarification: "Clarify the EFT purpose",
  amortization_document: "Supply correct amortization schedule",
  authority_missing: "Record missing requester authority",
  authorized_representative: "Supply representative authorization",
  assignment_exception: "Add a related case with conflicting ownership",
  resolve_assignment: "Reconcile related case owners",
  additional_concern: "Add a separate concern",
  unrelated_contact: "Record an unrelated later contact",
};
const claimFields: DraftEdit["claims"][number]["field"][] = [
  "loan_identifier",
  "tax_bill_received_at",
  "tax_amount_minor",
  "tax_due_date",
  "tax_scheduled_date",
  "tax_status",
  "tax_paid_at",
  "current_legal_name",
  "bankruptcy_status",
  "eft_intent",
  "task_completed",
  "document_attached",
];

export default function CaseWorkflow({
  item,
  running,
  onChanged,
  automatic = false,
  section = "all",
  editorOnly = false,
  onCancel,
}: {
  item: Case;
  running: boolean;
  onChanged: () => void;
  automatic?: boolean;
  section?: "all" | "review" | "handoff";
  editorOnly?: boolean;
  /** When set, the editor renders a dialog footer with Cancel beside Save. */
  onCancel?: () => void;
}) {
  const [data, setData] = useState<Workflow | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [kind, setKind] = useState<CaseInput["kind"]>("unrelated_contact");
  const [intent, setIntent] =
    useState<NonNullable<CaseInput["eft_intent"]>>("outgoing_refund");
  const [text, setText] = useState("");
  const actor = REVIEWER.name;
  const [note, setNote] = useState("");
  const [edit, setEdit] = useState<Draft["candidate"] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);
  const initialized = useRef(false);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api.workflow(item.id, controller.signal),
      api.evidence(item.id, controller.signal),
      api.tasks(item.id, controller.signal),
    ])
      .then(([workflow, records, taskRows]) => {
        if (controller.signal.aborted) return;
        setData(workflow);
        setEvidence(records);
        setTasks(taskRows);
        if (!initialized.current) {
          setKind(workflow.input_options[0] as CaseInput["kind"]);
          initialized.current = true;
        }
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "Workflow could not be loaded.",
          );
      });
    return () => controller.abort();
  }, [item.id, item.revision, refresh, running]);
  const draft = data?.drafts.at(-1) as Draft | undefined;
  useEffect(() => {
    const candidate = draft?.candidate;
    setEdit(
      candidate
        ? structuredClone({
            response_type: candidate.response_type,
            concerns: candidate.concerns,
            claims: candidate.claims,
            attachment_ids: candidate.attachment_ids,
          })
        : null,
    );
    setNote("");
  }, [draft?.id]); // A new version has a new editing basis.
  const locked = busy || running || item.status === "closed" || !actor.trim();
  async function mutate(action: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      if (alive.current) {
        setNotice(message);
        setRefresh((n) => n + 1);
        onChanged();
      }
    } catch (reason) {
      if (alive.current)
        setError(
          reason instanceof Error
            ? reason.message
            : "The action could not be completed.",
        );
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  function receive() {
    return mutate(
      () =>
        api.supplyInput(item.id, {
          request_id: crypto.randomUUID(),
          expected_revision: item.revision,
          actor,
          kind,
          text,
          eft_intent: kind === "eft_clarification" ? intent : null,
        }),
      automatic
        ? "Input saved. The agent will inspect it and continue automatically."
        : "Input saved to this case. Resume the agent to inspect it and continue.",
    );
  }
  function review(decision: "approve" | "return") {
    if (!draft) return;
    return mutate(
      () =>
        api.review(item.id, {
          request_id: crypto.randomUUID(),
          expected_case_revision: item.revision,
          actor,
          draft_id: draft.id,
          draft_version: draft.version,
          decision,
          note,
        }),
      decision === "approve"
        ? automatic
          ? "This response version is approved. Processing will continue automatically."
          : "This response version is approved. Resume the agent to execute its remaining actions."
        : automatic
          ? "Response returned. The agent will prepare a revision automatically."
          : "Response returned for changes. Edit the response or resume the agent for a revision.",
    );
  }
  function saveEdit() {
    if (!draft || !edit) return;
    return mutate(
      () =>
        api.editDraft(item.id, {
          request_id: crypto.randomUUID(),
          expected_revision: item.revision,
          actor,
          draft_id: draft.id,
          draft_version: draft.version,
          ...edit,
        }),
      "A new validated response version is saved. Review and approve this version before sending.",
    );
  }
  function claimValue(value: string, field: string) {
    return field === "tax_amount_minor" ? Number(value) : value;
  }
  return (
    <section className="case-workflow" aria-label="Review and case inputs">
      {!editorOnly && (
        <div className="workflow-heading">
          <h3>
            {section === "review"
              ? "Response review"
              : section === "handoff"
                ? "Specialist responsibility"
                : "Review and case inputs"}
          </h3>
          <p>
            {section === "review"
              ? "Check the response and supporting facts. Approval continues processing automatically."
              : section === "handoff"
                ? "Acknowledge responsibility for the current specialist referral."
                : "Supply the next item on this case, review a response, or acknowledge a specialist handoff."}
          </p>
        </div>
      )}
      <label className="reviewer-identity">
        Acting reviewer
        <input value={actor} readOnly maxLength={120} disabled={busy} />
      </label>
      {error && (
        <p className="alert error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="alert success" role="status">
          {notice}
        </p>
      )}
      {running && (
        <p className="workflow-hint">
          The agent is active. Stop it or wait for a pause before submitting
          changes.
        </p>
      )}
      {!editorOnly && !!data?.pending_work.length && (
        <div className="pending-work">
          <h4>Outstanding concerns</h4>
          {data.pending_work.map((pending) => (
            <p key={String(pending.concern_id)}>
              <strong>{readable(pending.owner)}</strong>:{" "}
              {displayText(pending.resume_requirement)}
              <br />
              {!!pending.next_review_at && (
                <small>
                  Next review:{" "}
                  {new Date(String(pending.next_review_at)).toLocaleString(
                    "en-US",
                    { timeZone: "America/New_York", timeZoneName: "short" },
                  )}
                </small>
              )}
            </p>
          ))}
        </div>
      )}
      {section === "all" && (
        <details className="workflow-inputs" open={item.status !== "closed"}>
          <summary>Receive evidence or a follow-up</summary>
          <div className="workflow-form">
            <label>
              Input to supply
              <select
                aria-label="Input to supply"
                value={kind}
                disabled={locked}
                onChange={(e) => setKind(e.target.value as CaseInput["kind"])}
              >
                {data?.input_options.map((option) => (
                  <option key={option} value={option}>
                    {labels[option] ?? sentence(option)}
                  </option>
                ))}
              </select>
            </label>
            {kind === "eft_clarification" && (
              <label>
                EFT purpose
                <select
                  aria-label="EFT purpose"
                  value={intent}
                  disabled={locked}
                  onChange={(e) => setIntent(e.target.value as typeof intent)}
                >
                  <option value="outgoing_refund">Outgoing refund</option>
                  <option value="incoming_payment">Incoming payment</option>
                  <option value="heloc_draw">HELOC draw</option>
                </select>
              </label>
            )}
            {["unrelated_contact", "additional_concern"].includes(kind) && (
              <label>
                Contact or concern
                <textarea
                  aria-label="Contact or concern"
                  maxLength={1500}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  disabled={locked}
                />
              </label>
            )}
            <button
              className="secondary-button"
              disabled={
                locked ||
                !data ||
                (["unrelated_contact", "additional_concern"].includes(kind) &&
                  !text.trim())
              }
              onClick={() => void receive()}
            >
              Receive input
            </button>
            <p className="workflow-hint">
              The case keeps its original receipt date, sent records and prior
              run history. New inputs require a current response and review.
            </p>
          </div>
        </details>
      )}
      {draft && section !== "handoff" && (
        <div className="review-workspace">
          {!editorOnly && (
            <>
              <h4>Response review · version {draft.version}</h4>
              <p>
                <strong>
                  {draft.sent
                    ? "Sent response retained"
                    : !draft.current
                      ? "Inputs changed — prepare a current response"
                      : draft.approved
                        ? "Approved current version"
                        : draft.returned
                          ? "Returned for changes"
                          : draft.review_required
                            ? "Review required"
                            : "Available for review"}
                </strong>
              </p>
              <p>Verified recipient: {draft.recipient}</p>
              <pre className="response-preview" aria-label="Response to review">
                {displayText(draft.body)}
              </pre>
            </>
          )}
          {!draft.current && (
            <p className="workflow-hint">
              {automatic
                ? "New evidence requires reassessment. This earlier version cannot be approved or sent."
                : "Resume the agent to reassess the new evidence. This earlier version cannot be approved or sent."}
            </p>
          )}
          {draft.current && !draft.sent && (
            <>
              {!editorOnly && (
                <>
                  <label>
                    Review note
                    <textarea
                      aria-label="Review note"
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      maxLength={4000}
                      disabled={locked}
                    />
                  </label>
                  <div className="workflow-actions">
                    <button
                      className="primary-button"
                      disabled={locked || draft.approved}
                      onClick={() => void review("approve")}
                    >
                      Approve this version
                    </button>
                    <button
                      className="secondary-button"
                      disabled={locked || !note.trim()}
                      onClick={() => void review("return")}
                    >
                      Return for changes
                    </button>
                  </div>
                </>
              )}
              <details open={editorOnly || undefined}>
                <summary>Edit the supported response</summary>
                {edit && (
                  <div className="response-editor">
                    <p className="workflow-hint">
                      Edit cited facts, concern dispositions and attachments.
                      Saving checks the evidence and creates a new version; the
                      validated text is rendered below in saved results.
                    </p>
                    <label>
                      Response purpose
                      <select
                        aria-label="Response purpose"
                        value={edit.response_type}
                        disabled={locked}
                        onChange={(e) =>
                          setEdit({
                            ...edit,
                            response_type: e.target
                              .value as DraftEdit["response_type"],
                          })
                        }
                      >
                        {[
                          "final_resolution",
                          "information_request",
                          "interim_acknowledgment",
                          "referral",
                        ].map((value) => (
                          <option key={value} value={value}>
                            {sentence(value)}
                          </option>
                        ))}
                      </select>
                    </label>
                    {edit.claims.map((claim, index) => (
                      <div className="claim-editor" key={index}>
                        <label>
                          Fact
                          <select
                            aria-label={`Claim ${index + 1} fact`}
                            value={claim.field}
                            disabled={locked}
                            onChange={(e) =>
                              setEdit({
                                ...edit,
                                claims: edit.claims.map((c, i) =>
                                  i === index
                                    ? {
                                        ...c,
                                        field: e.target.value as typeof c.field,
                                      }
                                    : c,
                                ),
                              })
                            }
                          >
                            {claimFields.map((field) => (
                              <option key={field} value={field}>
                                {sentence(field)}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Value
                          <input
                            aria-label={`Claim ${index + 1} value`}
                            value={String(claim.value ?? "")}
                            disabled={locked}
                            onChange={(e) =>
                              setEdit({
                                ...edit,
                                claims: edit.claims.map((c, i) =>
                                  i === index
                                    ? {
                                        ...c,
                                        value: claimValue(
                                          e.target.value,
                                          c.field,
                                        ),
                                      }
                                    : c,
                                ),
                              })
                            }
                          />
                        </label>
                        <label>
                          Supporting evidence
                          <select
                            aria-label={`Claim ${index + 1} evidence`}
                            value={claim.evidence_id}
                            disabled={locked}
                            onChange={(e) =>
                              setEdit({
                                ...edit,
                                claims: edit.claims.map((c, i) =>
                                  i === index
                                    ? { ...c, evidence_id: e.target.value }
                                    : c,
                                ),
                              })
                            }
                          >
                            {evidence.map((e) => (
                              <option key={e.id} value={e.id}>
                                {readable(e.title)} · v{e.version}
                              </option>
                            ))}
                            {tasks.map((task) => (
                              <option key={task.id} value={task.id}>
                                {readable(task.task_type)} · {task.status}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button
                          className="text-button"
                          aria-label={`Remove claim ${index + 1}`}
                          disabled={locked}
                          onClick={() =>
                            setEdit({
                              ...edit,
                              claims: edit.claims.filter((_, i) => i !== index),
                            })
                          }
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                    <button
                      className="text-button"
                      disabled={locked || !evidence.length}
                      onClick={() =>
                        setEdit({
                          ...edit,
                          claims: [
                            ...edit.claims,
                            {
                              field: "loan_identifier",
                              value: item.loan_identifier,
                              evidence_id:
                                evidence.find(
                                  (e) => e.details.kind === "record",
                                )?.id ?? evidence[0].id,
                            },
                          ],
                        })
                      }
                    >
                      Add cited fact
                    </button>
                    <fieldset disabled={locked}>
                      <legend>Attachments</legend>
                      {evidence
                        .filter((e) => e.details.kind !== "record")
                        .map((e) => (
                          <label className="checkbox-label" key={e.id}>
                            <input
                              type="checkbox"
                              checked={edit.attachment_ids.includes(e.id)}
                              onChange={(event) =>
                                setEdit({
                                  ...edit,
                                  attachment_ids: event.target.checked
                                    ? [...edit.attachment_ids, e.id]
                                    : edit.attachment_ids.filter(
                                        (id) => id !== e.id,
                                      ),
                                })
                              }
                            />
                            {readable(e.title)}
                          </label>
                        ))}
                    </fieldset>
                    {edit.concerns.map((concern, index) => (
                      <label key={concern.concern_id}>
                        Concern {index + 1} disposition
                        <select
                          aria-label={`Concern ${index + 1} disposition`}
                          value={concern.disposition}
                          disabled={locked}
                          onChange={(e) =>
                            setEdit({
                              ...edit,
                              concerns: edit.concerns.map((c, i) =>
                                i === index
                                  ? {
                                      ...c,
                                      disposition: e.target
                                        .value as typeof c.disposition,
                                    }
                                  : c,
                              ),
                            })
                          }
                        >
                          {[
                            "resolved",
                            "pending_borrower",
                            "pending_department",
                            "referred",
                          ].map((value) => (
                            <option key={value} value={value}>
                              {sentence(value)}
                            </option>
                          ))}
                        </select>
                      </label>
                    ))}
                    {onCancel ? (
                      <div className="workflow-dialog-footer">
                        <button
                          className="secondary-button"
                          type="button"
                          onClick={onCancel}
                        >
                          Cancel
                        </button>
                        <button
                          className="primary-button"
                          disabled={locked}
                          onClick={() => void saveEdit()}
                        >
                          Save validated revision
                        </button>
                      </div>
                    ) : (
                      <button
                        className="secondary-button"
                        disabled={locked}
                        onClick={() => void saveEdit()}
                      >
                        Save validated revision
                      </button>
                    )}
                  </div>
                )}
              </details>
            </>
          )}
        </div>
      )}
      {!!data?.handoffs.length && section !== "review" && (
        <div className="handoff-workspace">
          <h4>Specialist handoffs</h4>
          {(data.handoffs as Handoff[]).map((handoff) => (
            <div className="handoff-card" key={handoff.id}>
              <strong>
                {handoff.route} · {readable(handoff.owner)}
              </strong>
              <p>
                {handoff.current
                  ? readable(handoff.status)
                  : "Earlier handoff — inputs changed"}
                {handoff.acknowledged_by
                  ? ` by ${readable(handoff.acknowledged_by)}`
                  : ""}
              </p>
              {!!handoff.restrictions.length && (
                <p>
                  Restrictions: {handoff.restrictions.map(readable).join(", ")}
                </p>
              )}
              {!!handoff.routing_note && (
                <details className="handoff-note">
                  <summary>Routing note</summary>
                  <pre>{displayText(handoff.routing_note)}</pre>
                </details>
              )}
              {!!handoff.acknowledgment_note && (
                <p className="handoff-ack">{handoff.acknowledgment_note}</p>
              )}
              {handoff.current && handoff.status === "requested" && (
                <button
                  className="secondary-button"
                  disabled={locked}
                  onClick={() =>
                    void mutate(
                      () =>
                        api.acknowledge(item.id, {
                          request_id: crypto.randomUUID(),
                          expected_revision: item.revision,
                          actor,
                          handoff_id: handoff.id,
                        }),
                      "Specialist receipt acknowledged. The case is transferred and its concerns remain tracked.",
                    )
                  }
                >
                  Acknowledge specialist receipt
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {!editorOnly && !!data?.reviews.length && (
        <details>
          <summary>Review history · {data.reviews.length} decisions</summary>
          {data.reviews.map((review) => (
            <p key={String(review.id)}>
              Version {String(review.draft_version)} · {readable(review.actor)}{" "}
              · {String(review.decision)}
              <br />
              {String(review.note)}
            </p>
          ))}
        </details>
      )}
    </section>
  );
}
