import { useRef, useState } from "react";
import { REVIEWER } from "../auth/reviewer";
import { api } from "../api/client";
import type { IntakeReview, IntakeReviews as ReviewData } from "../api/client";
import type { components } from "../api/schema";
import DeskIcon from "./DeskIcon";
import { useDeskData } from "./useDeskData";

export default function IntakeReviews() {
  const data = useDeskData(api.intakeReviews);
  if (data.error)
    return (
      <p className="desk-error" role="alert">
        Intake review queue: {data.error}
      </p>
    );
  if (!data.value?.reviews.length) return null;
  const count = data.value.reviews.length;
  return (
    <section
      className="desk-intake-reviews"
      aria-label="Incoming requests needing review"
    >
      <h2 className="desk-sr-only">Incoming requests needing review</h2>
      {data.value.reviews.map((item) => (
        <Review
          key={item.signal_id}
          item={item}
          loans={data.value!.loans}
          count={count}
        />
      ))}
    </section>
  );
}

function Review({
  item,
  loans,
  count,
}: {
  item: IntakeReview;
  loans: ReviewData["loans"];
  count: number;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Unable to continue.",
      );
      setBusy(false);
    }
  }
  return (
    <article className="desk-intake-strip">
      <span className="desk-intake-icon" aria-hidden="true">
        <DeskIcon name="shield" size={16} />
      </span>
      <p>
        <strong>
          {count === 1
            ? "1 incoming request needs identity review"
            : "Incoming request needs identity review"}
        </strong>
        <span title={item.message.subject}>{item.message.subject}</span>
        <span title={item.message.sender}>{item.message.sender}</span>
      </p>
      <button
        className="desk-button quiet small"
        disabled={busy}
        onClick={() => void act(() => api.retryIntake(item.signal_id))}
      >
        Retry classification
      </button>
      <button
        className="desk-button primary small"
        disabled={busy}
        onClick={() => dialog.current?.showModal()}
      >
        Review request
      </button>
      {error && !dialog.current?.open && (
        <p className="desk-intake-error" role="alert">
          {error}
        </p>
      )}
      <dialog className="desk-dialog desk-intake-dialog" ref={dialog}>
        <header>
          <h2>Review incoming request</h2>
          <button
            className="desk-icon-button"
            aria-label="Close request review"
            disabled={busy}
            onClick={() => dialog.current?.close()}
          >
            <DeskIcon name="close" />
          </button>
        </header>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const values = new FormData(event.currentTarget);
            void act(() =>
              api.resolveIntake(item.signal_id, {
                request_id: crypto.randomUUID(),
                loan_identifier: String(values.get("loan")),
                request_type: String(
                  values.get("type"),
                ) as components["schemas"]["IntakeResolution"]["request_type"],
                actor: REVIEWER.name,
                note: String(values.get("note")),
                identity_verified: true,
              }),
            );
          }}
        >
          <div className="desk-dialog-body">
            <section className="desk-intake-message" aria-label="Request">
              <h3>{item.message.subject}</h3>
              <p className="desk-muted">From {item.message.sender}</p>
              <blockquote>{item.message.body}</blockquote>
              {item.detail && <p className="desk-field-hint">{item.detail}</p>}
            </section>
            <fieldset className="desk-intake-fields">
              <legend>Match the request</legend>
              <label>
                Verified loan
                <select
                  aria-label="Verified loan"
                  name="loan"
                  required
                  defaultValue=""
                >
                  <option value="" disabled>
                    Select a loan
                  </option>
                  {loans.map((loan) => (
                    <option key={loan.id} value={loan.id}>
                      {loan.id} · {loan.borrower} · {loan.recipient}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Request type
                <select
                  name="type"
                  defaultValue={item.classification?.request_type ?? "other"}
                >
                  {Object.entries({
                    name_change: "Name change",
                    amortization: "Amortization schedule",
                    tax: "Tax",
                    bankruptcy: "Bankruptcy",
                    eft: "EFT",
                    other: "Other / multiple topics",
                  }).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="desk-readonly-field">
                Reviewer
                <input name="actor" value={REVIEWER.name} readOnly />
              </label>
            </fieldset>
            <label className="desk-intake-note">
              Review note
              <textarea name="note" required minLength={10} maxLength={2000} />
            </label>
            <label className="desk-intake-check">
              <input type="checkbox" required />I verified the sender's
              identity, authority and selected loan.
            </label>
            <p className="desk-field-hint">
              Responses use the recipient held in servicing records.
            </p>
            {error && (
              <p className="desk-alert" role="alert">
                {error}
              </p>
            )}
          </div>
          <footer className="desk-dialog-footer">
            <button
              type="button"
              className="desk-button quiet"
              disabled={busy}
              onClick={() => dialog.current?.close()}
            >
              Cancel
            </button>
            <button className="desk-button primary" disabled={busy}>
              Confirm and continue
            </button>
          </footer>
        </form>
      </dialog>
    </article>
  );
}
