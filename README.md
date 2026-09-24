# Correspondence workspace

To share the complete source and relevant documentation, run `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\package-source.ps1`. It creates a verified ZIP in `.local/releases/`. See [setup and source sharing](plan/Source_Sharing_Guide.md) for the package contents, source-workbook redactions and instructions for another machine.

The **Mailbox** opens with five demo requests in Drafts and empty message folders. **Reset mailbox** restores that state and also clears every case in the desk. The desk has a matching **Reset workspace** in its account menu, above Sign out. Either button resets both apps. Choose **New mail** to write a blank email; open the five prepared demos directly from **Drafts**, without a template dropdown. Edit any draft except its fixed To address. Add PDFs or images to messages and remove any attachment; both formats open in a popup preview. Draft rows hide body text until opened. Azure classifies custom email and uploaded PDF text, processes supported requests against the local loan records, and sends identity exceptions for review. Conversations show the newest message first in a light layout. Refreshing or reopening the mailbox preserves its contents; only **Reset mailbox** starts over. Drafts supports selection and attachment filtering, and the light typography fits 13-inch laptop screens. See the [current mailbox guide](plan/Mailbox_UI_Guide.md).

Run `.\.venv\Scripts\python.exe -m app.custom_mail_evaluation --live` to check all five custom request families, missing identity and an embedded instruction against Azure in an isolated workspace.

The correspondence desk opens with a login screen. Type **admin** in Username to enter the full-width **Case dashboard** as **Admin — Reviewer**. The **SSO login** button is below the field. This is the local MVP login, with one fixed profile and no registration or role creation. Refresh keeps the current tab signed in; **Sign out** returns to login. Click any case row to enter its detailed three-column workspace: borrower correspondence and context, agent activity with saved receipts, and the current response with review controls. Send a predefined request from the separate **Mailbox** to start one of five demos. Replies, specialist results and approvals continue the Azure agent automatically.

**Desk:** http://127.0.0.1:5173 · **Mailbox:** http://127.0.0.1:5176. See the [case workspace guide](plan/Case_Workspace_Guide.md) for the new layout and navigation.

Start with the [mailbox runbook](plan/Mailbox_Demo_Runbook.md), [plain-English demo flows](plan/Demo_Flows_and_System_Connections.md), and [handover guide](plan/Handover.md). [Phase 10 evidence](plan/checkpoints/PH-10.md) covers the mailbox extension. The [earlier runbook](plan/Demo_Runbook.md) remains available for diagnostics. Four required business items and the standalone PH-05 manual workflow remain partial; see [remaining work](plan/Follow_ups.md). The existing Phase 9 runtime archive predates the mailbox extension.

## Start locally on Windows

Prerequisites: Python 3.12 or newer and Node 22.13 or newer for Vite and PDF.js. This implementation was checked with Python 3.14 and Node 25.2.1.

From the workspace root, install the locked dependencies and create the database:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Start the backend in one terminal:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1
```

Start the desk in a second terminal:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1
```

Start the mailbox in a third terminal:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-mailbox.ps1
```

Open the desk at **http://127.0.0.1:5173** and the mailbox at **http://127.0.0.1:5176** in separate tabs. There are no links between these interfaces. The API runs at **http://127.0.0.1:8000**; interactive contracts are at **http://127.0.0.1:8000/docs**. Stop each server with Ctrl+C. These scripts run in the current terminals and do not open additional windows.

Open the separate **Mailbox** at `http://127.0.0.1:5176`, open a prepared request in **Drafts**, and click **Send**. This is the demo trigger. **New mail** opens a blank email. Switch to the desk tab and click the new case in the dashboard; it appears without refreshing. The server creates the case and starts the agent automatically. No Outlook or SMTP credentials are needed. Azure calls are live; the business-system records and deliveries are local to this app.

For follow-up evidence, use **Reply** in the same sender conversation. Specialist results are recorded under **Case → System workspaces → ILS**. Select **Needs review** on the dashboard and open a case to approve, edit or return its current response in the right panel. Existing diagnostic controls remain at `/?workspace=classic`, outside the presentation navigation. This workspace is off by default: start the frontend with `VITE_ENABLE_DIAGNOSTICS=true` to use it (the browser tests do this automatically). Only mailbox-linked cases receive automatic event processing.

To load five diagnostic cases from PowerShell (these do not trigger mailbox processing):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\seed-demo.ps1
```

Running that command again reuses its initial cases. Add `-Fresh` to create another set while preserving history. Load an individual variant with, for example, `-Scenario DEMO-02 -Variant wrong_loan -Fresh`. Available scenarios and variant behavior are documented in [the data guide](data/README.md).

## Azure Foundry configuration

The root `.env` contains your Azure settings. [.env.example](.env.example) documents the fields; `.env` is ignored and setup preserves it. Credentials stay on the backend.

| Variable | Value to provide |
| --- | --- |
| `AZURE_OPENAI_BASE_URL` | Your deployed resource's HTTPS OpenAI v1 base URL, for example `https://YOUR-RESOURCE.openai.azure.com/openai/v1/`. Use the inference endpoint, not the Azure portal or project-management URL. |
| `AZURE_OPENAI_DEPLOYMENT` | The deployment name you chose in Azure; it may differ from the underlying model name. |
| `AZURE_OPENAI_API_KEY` | An API key for that resource. This value stays server-side. |
| `AZURE_OPENAI_TIMEOUT_SECONDS` | Request timeout in seconds; defaults to 60. |
| `AZURE_OPENAI_LIVE_TESTS_ENABLED` | Explicit live-test opt-in metadata. Sending mailbox messages and automatic continuations make real Azure calls regardless of this flag. The live helper scripts authorize their own calls. |

This configuration uses the Azure OpenAI **v1** endpoint convention. It does not need a dated `api-version` setting. Resource-group membership alone does not provide an inference URL or deployment name. No resources are created in your Azure subscription.

Restart the backend after editing `.env`. **Setup & status** reports configuration completeness without displaying credentials. The diagnostics workspace also shows the last successful connection-check timestamp. Sending a mailbox template starts a live run. If configuration is missing, mail stays saved and pending until configuration is completed and the backend restarts.

Run `scripts/test-azure.ps1` explicitly to make up to two live Azure requests using an isolated synthetic case and a read-only simulator tool. The helper verifies that the deployed model calls the tool and uses its returned facts. Its redacted report is saved to `.local/azure-live-check.json`. Normal checks do not call Azure. The Phase 4 live check passed on 22 September 2026.

References checked on 22 September 2026: [OpenAI SDK libraries](https://developers.openai.com/api/docs/libraries) and [Microsoft's Azure OpenAI endpoint/deployment guidance](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/switching-endpoints?view=foundry-classic).

## Run the Azure agent

1. In the **Mailbox** at `http://127.0.0.1:5176`, send the amortization-schedule template (**DEMO-02**).
2. Open its case in the desk. The agent activity timeline keeps the newest step in view while it runs; switch to **System workspaces** to inspect the connected systems.
3. The agent checks the loan and schedule, sends the response, indexes the package, records the servicing note and closes the case.
4. Under **System workspaces**, inspect the delivery in **Secure mail**, the combined PDF in **OnBase**, and the note in **ILS**. The response also returns to the sender mailbox.
5. Refreshing the case address reloads the same records. **System workspaces → Agent activity → Stop agent** pauses processing at a safe boundary; recovery controls can explicitly resume it.

The agent obeys client review requirements. Select **Needs review** on the dashboard and open a case and inspect its right-hand response panel. **Approve and send** approves the current version; **Return** supplies feedback; **Edit draft** opens the validated response editor. Approval automatically continues processing. New evidence invalidates earlier approval. People supply evidence and make required decisions; the agent performs the subsequent system actions.

### Five-family walkthrough

| Case | Presenter action | Expected result |
| --- | --- | --- |
| DEMO-01 — Name change | Send Lauren Whitaker's initial email (signed request attached); after the information request, reply with **Provide legal name-change document** (certified marriage record). See the [use-case pack](usecases/demo-2-name-change/README.md). | The agent continues the same case, records the name update and sends a signed confirmation, then hands off for the classification decision (**Waiting on department**). |
| DEMO-02 — Amortization | Send the initial email. | Automatic delivery, indexing, note and closure; no further presenter action. |
| DEMO-03 — Tax inquiry | Send Priya Raman's email (township tax bill attached); record the Tax Team result in ILS, then review/edit and approve the current response. See the [use-case pack](usecases/demo-3-tax-inquiry/README.md). | The agent reuses the existing task and sends only the current approved Harbor Point letter: the bill is received and the payment is scheduled for October 27, but it has not been paid yet. |
| DEMO-04 — Bankruptcy conflict | Send the representative's email; record the determination in ILS and acknowledge the current handoff. | Automatic reassessment and verified transfer; contact restrictions and unresolved concerns remain. |
| DEMO-05 — EFT ambiguity | Send Danielle Foster's email (escrow statement attached); after the clarification letter, reply with Payment type **Refund**. See the [use-case pack](usecases/demo-5-eft-clarification/README.md). | The first letter explains the three meanings of EFT; the follow-up asks for a signed Electronic Refund Authorization and a voided check or bank letter. The case waits for the borrower; no funds move. |

Diagnostic input controls also cover authority, representative authorization, assignment conflicts and separate concerns. Original receipt times, earlier runs and sent artifacts remain on the same case. The fixture's business evaluation date is fixed; the mailbox separately records the actual time an email is sent.

Run `scripts/test-mailbox.ps1` for all five live Azure mailbox evaluations in an isolated database. The evaluator sends templates, records relevant human actions and waits for automatic runs. It never calls the manual start/resume endpoint. Evidence is retained under `.local/mailbox-evaluations/`; `.local/mailbox-live-latest.json` points to the report.

Run `scripts/test-workflow.ps1` for real Azure evaluations of all five families in a fresh isolated database, or add `-Scenario DEMO-04` for one family. The evaluator performs explicit simulated presenter interventions and checks persisted outcomes. Reports, databases and generated PDFs remain under `.local/workflow-evaluations/`; `.local/phase7-live-latest.json` points to the last completed evaluation. These calls are separate from the offline regression suite. A provider failure is recorded visibly; inspect its report before starting another run.

`scripts/test-agent.ps1` runs three real Azure evaluations in a fresh isolated database: complete document request, missing document and an embedded instruction attempting recipient substitution/false closure. Results and actual artifacts are retained under `.local/agent-evaluations/`; `.local/phase6-live-latest.json` points to the latest report. The accepted evaluation used 28 model calls and 138,740 reported tokens. These calls are separate from normal offline checks.

Optional limits in `.env.example`: `AGENT_MAX_STEPS=28`, `AGENT_MAX_MODEL_CALLS=28`, `AGENT_MAX_SECONDS=300`, `AGENT_MAX_TOTAL_TOKENS=250000`, `AGENT_MAX_COMPLETION_TOKENS=1600`, `AGENT_MAX_CONTEXT_CHARACTERS=100000`. Omitted values use these defaults. The token threshold is checked on reported usage after a request, so that request can exceed it; no further action runs after the limit. Credentials and deployment configuration never enter the run display. Stops, provider errors, repeated failures and uncertain actions retain their checkpoints. Interrupted workers reconstruct their saved state after the previous lease expires. Run time and usage limits continue from the original start.

## Recover a run and inspect its evidence

For deliberate failure demonstrations, open **Diagnostics workspace → Agent workspace → Advanced controls** and choose a **Recovery test** before starting a fresh diagnostic run. The selected fault fires once at its matching operation; it has no effect if that operation is never reached. Resume does not inject another fault. Normal mailbox cases expose recovery in **Agent activity** when it is needed.

| Demonstration | Presenter steps | Verified behavior |
| --- | --- | --- |
| Indexing failure after delivery | Load DEMO-02, select the failure, start, then resume after the pause. | The existing delivery is retained; indexing, final notes and closure finish without resending. |
| Send result unavailable | Start a fresh DEMO-02 with this fault; use **Check persisted results**, then resume. | The saved delivery is independently verified and reused. |
| Send result and status unavailable | Start a fresh DEMO-02; check the result, restore status access, check again, then resume. | Unknown results block further writes. Restoring access does not mark a delivery complete; its original receipt and artifacts must verify. |
| New task result unavailable | Use a DEMO-01 case with the legal document supplied and this fault; check the result before resuming. | The committed task is reused instead of creating another. |

**Run summary and recovery** reports distinct completed actions and failures for the selected run, case interventions through that run, current pending concerns, elapsed time, reported model usage and worker recoveries. Routine run launches are excluded from intervention counts. Elapsed time includes interruption/lease waits. A request interrupted before its usage was saved is labeled incomplete; reported tokens are not a billing estimate.

**Download evidence** saves a JSON manifest of selected-run metrics and current case record references, versions, hashes and statuses. It deliberately omits correspondence, response/loan-note text, names, servicing identifiers, file paths, presenter text and Azure secrets. It is a reference manifest at export time, not a historical case snapshot or PDF bundle. Actual synthetic responses/PDFs remain available in **Saved response and records**.

A graceful backend stop saves active work for the same run to resume on startup. After a hard exit or power loss, recovery waits for the old worker lease to expire (request timeout plus 90 seconds, **150 seconds with the default timeout**). It reconciles verifiable saved effects before the next model action. Original start time, history and usage remain; recovery cannot reset limits. A long outage can therefore reach the run time limit and pause. **Resume agent** then starts a linked run with a new budget and retains earlier results. A changed model configuration also requires a linked run. A presenter **Stop agent** stays stopped until explicitly resumed.

Run the two live Azure recovery evaluations in an isolated database:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-recovery.ps1
```

Reports and actual artifacts remain under `.local/recovery-evaluations/`; `.local/phase8-live-latest.json` points to the latest completed report. The Phase 8 accepted evaluation covered indexing failure and unavailable send status in four runs, with **24 model calls and 129,461 reported tokens**, and exactly one delivery per case. Offline browser tests separately exercise a real process exit immediately after a committed send and recovery of the same run.

## What is implemented

- Create/list/read synthetic cases with loan context, original receipt, family, owner, revision, and queue/review state.
- Atomic owner/status changes with optimistic revision checks and stable mutation receipts. Retrying the same mutation does not duplicate its event; conflicting reuse is rejected.
- Timezone-aware UTC timestamps with microseconds, leading-zero string identifiers, and exact integer monetary minor units.
- SQLite migrations, foreign keys, uniqueness constraints, transaction rollback, case-scoped event cursors, and persisted worker lease/fencing primitives.
- Database records for later evidence, knowledge, tasks, drafts, approvals, outbox entries, indexed packages, and notes.
- OpenAPI contracts and generated frontend types, health/configuration checks, and a desktop case dashboard.
- Five scenario fixtures, two fictional client configurations, prepared follow-up inputs, and 12 scenario/variant combinations. Expected business outcomes are stored separately under backend tests.
- Fifteen readable synthetic PDFs, one deliberately unreadable file, and two missing-file references. Downloads enforce case scope and recorded content hashes.
- All 149 parent-qualified taxonomy combinations and a metadata-only manifest of all 527 source rows. Fifteen selected demo guidance/template/disclosure items support structured search by scenario, client, kind, and text.

- Exact Eastern workday aging, special-route precedence, assignment exceptions, role/recipient/client checks, task reuse, scenario prerequisites and concern dispositions.
- Versioned assessment reports with immutable inputs and audit history. Select a demo case and use **Record assessment** to retain the current decision evidence.
- Structured response validation checks citations against facts, actual attachment files, all concerns and evidence versions. The completion gate requires matching persisted delivery, archive, final-note and approval records.

- A genuine model-driven tool loop, scoped evidence retrieval, bounded execution, safe cancellation, run-linked receipts and persisted desktop activity/results.
- Same-run worker recovery, receipt verification, single-use demonstration faults, run summaries and sanitized evidence manifests.
- Four scoped simulators with typed commands/results, stable action identities, status queries and independent reconciliation of uncertain writes.
- Actual local delivery snapshots and sent attachment copies, combined indexed PDFs with Sherman ID/CCID, Servicing/INQ Email Reply final notes, loan/task histories and gated case closure.

Run start, safe stop and explicit resume are implemented. Current draft review, validated edits, evidence receipt and specialist acknowledgment use atomic, revision-checked, idempotent services. The local presenter identity is a demo actor, not production authentication.

With the backend running, `scripts/demo-simulators.ps1` still demonstrates the same API with deterministic development commands. It does not use the model. Phase 5 is partial: response viewers and the reviewer editor are available; a standalone manual prepare/execute workflow remains open. Desktop agent runs execute through the model.

Response preflight validates a controlled rendering of structured claims and concern dispositions. Arbitrary added prose fails validation. Production policy gaps and unsupported classification mappings remain explicit. See the [business-rule decisions](plan/decisions/003-business-rules.md) and [simulator contracts](plan/decisions/004-simulated-systems.md).

## API and persistence

| Endpoint | Current behavior |
| --- | --- |
| `GET /api/health` | Database connectivity and migration revision. |
| `GET /api/config` | Redacted configuration/capability status. |
| `POST /api/simulations` | Create a synthetic simulation container. |
| `GET /api/simulations/{id}` | Inspect persisted record counts. |
| `GET /api/cases` | Paginated worklist ordered by original receipt. |
| `POST /api/cases` | Atomically create simulation/loan/case/event records; optional existing simulation ID. |
| `GET /api/cases/{id}` | Read the persisted case and loan context. |
| `PATCH /api/cases/{id}` | Update owner or queue/review status using expected revision and mutation ID. |
| `GET /api/cases/{id}/events?after=0` | Read persisted events after a cursor; the desktop polls saved state across reconnects. |
| `GET /api/cases/{id}/evidence` | Read case-scoped evidence references, document availability, metadata, and synthetic facts. |
| `GET /api/cases/{id}/actions` | Read persisted local action receipts. |
| `GET /api/cases/{id}/runs`, `GET /api/runs/{id}` | Read persisted live-model configuration, checkpoints, tool results, usage and pending work. |
| `POST /api/cases/{id}/runs` | Start a bounded live Azure run; optional `resume_from` links a paused, failed or stopped run on the same case and preserves its review mode. Optional `fault` selects a single-use synthetic failure. Duplicate active starts are rejected. |
| `GET /api/runs/{id}/summary`, `GET /api/runs/{id}/export` | Read scoped demo metrics or download the sanitized JSON reference manifest. |
| `GET /api/cases/{id}/recovery` | Inspect failed/uncertain receipts and verification outcomes. |
| `POST /api/cases/{id}/recovery/check` | Verify and reconcile persisted effects; unresolved uncertainty keeps writes blocked. |
| `POST /api/cases/{id}/recovery/restore-status` | Restore the synthetic status-outage fixture only; original result verification remains required. |
| `POST /api/runs/{id}/stop` | Request cancellation before the next action; in-flight actions retain their results. |
| `GET /api/cases/{id}/artifacts` | Read actual prepared responses, outbox entries, indexed packages and final notes. |
| `GET /api/cases/{id}/workflow` | Current/stale/sent/approved draft state, review history, input choices, pending work and handoff acknowledgment. |
| `POST /api/cases/{id}/inputs` | Receive a typed synthetic evidence/result/concern input on the same case; invalidate affected drafts and approvals. |
| `POST /api/cases/{id}/reviews` | Approve or return the current unsent draft with exact version/evidence binding and presenter identity. |
| `POST /api/cases/{id}/draft-edits` | Validate edited claims, concern dispositions and attachments; create a new response version. |
| `POST /api/cases/{id}/handoff-acknowledgments` | Record the recipient's acknowledgment of the current scoped handoff and mark the case transferred. |
| `GET /api/scenarios`, `POST /api/scenarios/{id}/instances` | Inspect the five scenarios and load a chosen starting-evidence variant with a stable request ID. |
| `GET /api/cases/{id}/evidence/{evidence_id}/file` | Open the actual PDF; missing/unreadable/changed files return structured errors. Wrong-loan fixtures remain inspectable and explicitly identifiable. |
| `GET /api/cases/{id}/tasks`, `GET /api/cases/{id}/concerns` | Inspect scoped synthetic tasks and unresolved concerns. |
| `GET /api/knowledge?scenario_id=DEMO-01&client_code=DEMO-NORTH` | Retrieve only applicable `curated_demo` content; optional `q` and `kind` filters. |
| `GET /api/taxonomy`, `GET /api/reference/summary`, `GET /api/clients` | Inspect classification references, reconciliation counts, and fictional client settings. |
| `GET /api/cases/{id}/assessment` | Compute current routing, authority, prerequisites, concern plans and file checks. |
| `GET/POST /api/cases/{id}/assessments` | Inspect/record immutable assessment evidence; POST requires a request ID and expected revision. |
| `POST /api/cases/{id}/validate-response` | Validate a structured response candidate; returns findings and the checked rendering without saving or sending it. |
| `GET /api/cases/{id}/completion-check` | Explain outstanding completion prerequisites against actual persisted records; does not close the case. |
| `GET /api/simulator/tools` | Inspect enabled simulated operations and their typed parameter schemas. |
| `POST /api/simulations/{simulation_id}/cases/{case_id}/tools` | Execute a scoped typed command. Writes require action ID, revision, evidence versions and input hash. |
| `GET /api/simulations/{simulation_id}/cases/{case_id}/packages/{package_id}/file?loan_identifier=…&client_code=…` | Retrieve the verified combined PDF within the complete case/loan/client scope. |

The full schema is in [backend/openapi.json](backend/openapi.json). Request validation errors omit submitted input values. Case updates and their receipts/events share a transaction; stale revisions and data conflicts return structured `409` errors.

Runtime data goes into `.local/correspondence.sqlite3`; loaded documents are copied into `.local/documents/`. `APP_DATA_DIR` can point to another local data directory. Migrations and reference-catalog installation run on startup and can be run separately with `.\.venv\Scripts\python.exe -m app.cli migrate`. Schema `0005` adds specialist handoffs and preserves existing records. Repeated startup preserves cases, evidence, history, and existing reference decisions.

The backend starts one local agent worker. Persisted leases serialize execution across workers, and the simulator checks lease ownership and cancellation before writing. An expired interrupted run reconstructs its saved checkpoint and reconciles verifiable effects under a new lease. Still-unknown outcomes pause visibly; action idempotency and independent verification guard further writes. Phase 8 requires no additional database migration; schema remains `0005`.

## Checks

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -Browser
```

Backend checks include an actual server-process restart, Phase 1 migration preservation, rollback and idempotency, time/amount preservation, configuration redaction, worker lease fencing, fixture isolation, document access, and curated-content filtering. Data checks reconcile the original workbook counts with the exported artifacts. Browser checks use installed Microsoft Edge in headless desktop mode; mobile support is deferred at the user's request. They start isolated servers on ports **8011/5174**, plus **8022** for the process-recovery tests, and store synthetic test data under `.local/`. They do not call Azure or use the normal workspace database. Keep those test ports available. The hard-exit test uses an explicitly labeled deterministic model and a two-second test-only lease; normal/live worker leases are unchanged.

After changing API schemas, regenerate both the snapshot and frontend types:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\export-contract.ps1
```

The check command verifies backend lint/formatting, the OpenAPI snapshot, and generated frontend type freshness, then typechecks/builds the frontend and runs the relevant tests. Generated frontend types come from the checked OpenAPI snapshot; do not edit them manually.

## Repository layout and project records

- `docs/`: the user's original source documents and samples.
- `plan/`: [BRD](plan/Business_Requirements_Document.md), [coding plan](plan/Coding_Plan_and_Checkpoints.md), decisions, checkpoint records, and acceptance ledger.
- `backend/`: API, typed contracts, domain/repository foundation, migration, and tests.
- `data/`: versioned synthetic fixtures/PDFs, presenter follow-ups, source metadata, and curated content. See [data maintenance](data/README.md).
- `frontend/`: case dashboard, detailed workspace, independent mailbox entry, generated API types, styles, and browser checks.
- `scripts/`: setup, server startup, checks, and contract generation.
- `.local/`: ignored runtime/test artifacts; `.venv/` and `node_modules/` are also ignored.

Phase evidence is recorded in [PH-01](plan/checkpoints/PH-01.md), [PH-02](plan/checkpoints/PH-02.md), [PH-03](plan/checkpoints/PH-03.md), [PH-04](plan/checkpoints/PH-04.md), [PH-06](plan/checkpoints/PH-06.md), [PH-07](plan/checkpoints/PH-07.md) and [PH-08](plan/checkpoints/PH-08.md). PH-05 remains partial; PH-09 acceptance and handover results are in [PH-09](plan/checkpoints/PH-09.md). Broader BRD acceptance is tracked separately in [the acceptance ledger](plan/acceptance_results.md); engineering checks do not imply that all 52 business scenarios have been implemented.

## Build the runtime bundle

Run `scripts/package-demo.ps1` to create a new timestamped ZIP under `.local/releases/`; `.local/phase9-package.json` records its path and SHA-256. The bundle contains application source, migration files, locked dependencies, synthetic fixtures and presenter guides. It excludes the original Office documents, their source-path registry, `.env`, existing runtime data and development tests. Its [package README](plan/Package_Readme.md) describes fresh setup. Full source reconciliation and engineering checks remain available from this original workspace.
