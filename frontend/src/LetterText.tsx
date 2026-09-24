import { displayRuns } from "./presentation";

/**
 * A plain-text letter body with server-computed emphasis spans rendered as <strong>.
 * No HTML is ever parsed; each run is a React text node. Keep the parent white-space: pre-wrap.
 */
export function LetterText({
  body,
  emphasis,
}: {
  body: unknown;
  emphasis?: unknown;
}) {
  return (
    <>
      {displayRuns(body, emphasis).map((run, index) =>
        run.bold ? (
          <strong className="letter-emphasis" key={index}>
            {run.text}
          </strong>
        ) : (
          run.text
        ),
      )}
    </>
  );
}
