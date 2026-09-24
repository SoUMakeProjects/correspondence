import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { Case, Evidence, Knowledge, Task } from "./api/client";
import {
  displayLabel as factLabel,
  displayValue,
  displayText,
  isOperationalGuidance,
} from "./presentation";

export default function CaseResources({ item }: { item: Case }) {
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [knowledge, setKnowledge] = useState<Knowledge[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setEvidence([]);
    setKnowledge([]);
    setTasks([]);
    setError("");
    Promise.all([
      api.evidence(item.id, controller.signal),
      api.tasks(item.id, controller.signal),
      api.simulation(item.simulation_id, controller.signal),
    ])
      .then(async ([documents, taskRows, inspection]) => {
        if (controller.signal.aborted) return;
        setEvidence(documents);
        setTasks(taskRows);
        if (inspection.simulation.scenario_key.startsWith("DEMO-")) {
          const guidance = await api.knowledge(
            inspection.simulation.scenario_key,
            item.client_code,
            controller.signal,
          );
          if (!controller.signal.aborted)
            setKnowledge(guidance.filter(isOperationalGuidance));
        }
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            "Case resources could not be loaded. Refresh the worklist to retry.",
          );
      });
    return () => controller.abort();
  }, [item.id, item.simulation_id, item.client_code]);

  if (!evidence.length && !knowledge.length && !tasks.length && !error)
    return null;
  return (
    <section className="case-resources" aria-label="Case evidence and guidance">
      {error && <p role="alert">{error}</p>}
      <div>
        <h3>Supporting evidence</h3>
        <p className="resource-note">
          Documents and servicing records linked to this case.
        </p>
        <ul className="resource-list">
          {evidence.map((document) => {
            const availability = document.details.availability;
            const isRecord = document.details.kind === "record";
            const loan = String(document.details.loan_identifier ?? "");
            const wrongLoan = loan !== item.loan_identifier;
            const facts = document.details.facts as
              Record<string, unknown> | undefined;
            return (
              <li key={document.id}>
                <strong>{factLabel(document.title)}</strong>
                <span>
                  Loan {loan}
                  {wrongLoan ? " · Different loan" : ""}
                </span>
                {isRecord ? (
                  <details>
                    <summary>View servicing facts</summary>
                    <dl className="resource-facts">
                      {Object.entries(facts ?? {})
                        .filter(
                          ([key, value]) =>
                            ![
                              "synthetic",
                              "simulated",
                              "result_source",
                            ].includes(key) &&
                            (value === null || typeof value !== "object"),
                        )
                        .map(([key, value]) => (
                          <div key={key}>
                            <dt>{factLabel(key)}</dt>
                            <dd>
                              {value === null
                                ? "Not recorded"
                                : displayValue(value)}
                            </dd>
                          </div>
                        ))}
                    </dl>
                  </details>
                ) : availability === "available" ? (
                  <a
                    href={`/api/cases/${item.id}/evidence/${document.id}/file`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open PDF{wrongLoan ? " for inspection" : ""}
                  </a>
                ) : (
                  <span className="resource-warning">
                    {availability === "missing"
                      ? "Document missing"
                      : "Unreadable attachment"}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
        {tasks.length > 0 && (
          <>
            <h3>Specialist tasks</h3>
            <ul className="resource-list">
              {tasks.map((task) => (
                <li key={task.id}>
                  <strong>{factLabel(task.task_type)}</strong>
                  <span>
                    {factLabel(task.owner)} · {factLabel(task.status)}
                  </span>
                  <span>
                    {displayText(
                      task.pending_reason ??
                        "A specialist result is available.",
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
      <div>
        <h3>Guidance and templates</h3>
        <p className="resource-note">
          Applicable guidance for this request and client.
        </p>
        {knowledge.map((item) => (
          <details className="knowledge-item" key={item.id}>
            <summary>
              {item.title}
              <span>{item.kind}</span>
            </summary>
            <div className="knowledge-content">
              <p>{displayText(item.content)}</p>
              <p className="resource-note">
                {item.source_references.join(" · ")} · Version {item.version}
              </p>
              {displayText(item.limitations.join(" ")) && (
                <p className="resource-note">
                  {displayText(item.limitations.join(" "))}
                </p>
              )}
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}
