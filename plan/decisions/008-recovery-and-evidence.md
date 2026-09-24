# Decision 008: Recovery and evidence reporting

Date: 22 September 2026. Status: implemented for PH-08. Application version `0.8.0`; checkpoint version `8`; schema remains `0005`.

## Recovery owns the original run

Graceful worker shutdown requeues its active run with recovery intent. A hard exit leaves its lease to expire. The next worker claims the run atomically with a new fencing token, verifies saved effects and reconstructs any tool result committed before its checkpoint. It preserves run identity, original start, tool history, model calls and reported usage. A valid lease cannot be stolen and an old token cannot commit another action.

Normal leases last the configured model request timeout plus 90 seconds (150 seconds by default). The elapsed run budget includes interruption and lease waits; recovery never grants a fresh budget. Limits use the stricter saved/current setting. If the budget is exhausted, or the saved model source/configuration has changed, recovery pauses. An explicit resume creates a linked run using current settings and the retained case records. Presenter stop remains stopped until explicitly resumed. A model request interrupted before its usage checkpoint marks totals incomplete.

This is local SQLite recovery. The two-second lease and forced process exit in `backend/tests/recovery_server.py` are test-only. Neither is available through application configuration or a model tool.

## Receipts distinguish applied, not applied and unknown

The status service reports three outcomes. Failed/rejected/awaiting-review receipts have no committed effect; confirmed receipts are applied. An uncertain effect must match its scoped persisted resource/hash and, for delivery/archive records, its retained files. Missing, altered or unavailable evidence remains unknown. Recovery never treats unknown as proof that nothing happened.

Automatic worker recovery reconciles verifiable uncertain effects under its new lease before continuing. Presenter **Check persisted results** uses the same verification. Ordinary writes remain blocked while any effect is unresolved. Reconciliation retains the original receipt and records an audit event. Retry of a verified effect reuses existing delivery/task/archive records; only missing work is performed.

The desktop exposes single-use simulated faults for indexing failure, lost send result, lost send result with unavailable status, and lost new-task result. The selected fault is stored on a new run and consumed in the same transaction as its matching receipt. Resume introduces no additional fault. A fault not reached by the chosen workflow remains unused. **Restore simulator status access** only restores the recognized synthetic status outage; it cannot change an effect or approve corrupted evidence.

Recovery controls require the current case revision and an idempotent presenter request. Active workers, foreign action references, conflicting request reuse and stale state are rejected. Existing draft version, review, payload hash and closure guards remain enforced.

## Metrics and export scope

The summary counts distinct completed effects belonging to the selected run and separately shows failed/rejected actions and reconciliation actions. Interventions cover the case's inputs, reviews, edits, acknowledgments, recovery controls, stops and owner/status changes through the run's end. Routine starts/resumes are excluded. Pending concerns and current case status reflect the case now, including later changes. These scopes are labeled in the UI and API.

Reported model tokens are retained provider usage, with an incomplete flag where appropriate; they are not a billing estimate. Elapsed time includes recovery waits and is not active CPU time. Presenter reconciliation updates the original receipt's status, so historical run summaries reflect its currently verified outcome.

The downloadable JSON is an allowlisted reference manifest: selected-run metrics plus current case record IDs, versions, hashes, statuses, relationships and controlled intervention types. It excludes prose, borrower names, servicing identifiers, provider values, file paths and presenter-entered text. Only a hexadecimal model-configuration fingerprint is retained. It is not a historical point-in-time snapshot, a full response export or a PDF bundle. Actual synthetic response packages remain available through the scoped artifact viewer.

Fresh scenario instances retain their predecessors' records and histories. No purge, reset-in-place operation, production retention rule or schema migration is introduced. Desktop reconnect continues to poll persisted APIs; SSE transport remains deferred.

## Verification and remaining work

See [PH-08 evidence](../checkpoints/PH-08.md) for service tests, actual process-exit/browser reconstruction and live Azure partial-failure runs. Offline deterministic model checks are labeled separately from live inference. PH-09 retains integrated acceptance, clean-start rehearsal and handover. The standalone PH-05 manual prepare/execute workflow remains partial; mobile remains deferred.
