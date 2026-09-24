# Local demo handover

Application `0.9.0`; current schema `0007`; synthetic fixture version `1`; business rules `demo-rules-1.0`; agent tool contract `7` and recovery checkpoint `8`. The current workspace includes the Phase 10 built-in mailbox extension and PDF uploads. The existing Phase 9 runtime archive uses schema `0005` and predates those extensions. PH-05's standalone manual workflow and the required gaps listed in [follow-up work](Follow_ups.md) remain open.

## What works

The current UI opens at a full-width case dashboard with no sidebar. Click any row to enter the case. Each case has a detailed three-column page with correspondence, agent activity and the response/review panel. Sending and replying use an independent frontend at `http://127.0.0.1:5176`. Neither interface links to the other. See [the case workspace guide](Case_Workspace_Guide.md) and [UI refresh evidence](checkpoints/UI-REFRESH.md) for the updated navigation and checks.

The Azure agent reads case evidence and scoped curated guidance, prepares validated responses and chooses permitted actions through four local simulators. Amortization and reviewed tax cases close after delivery, indexing and notes. Name-change, conflicting bankruptcy and EFT cases demonstrate evidence resumption, actual task results, acknowledged transfer or specific pending requirements as appropriate. Review binds to a current draft/evidence version. Recovery verifies prior effects before resuming and preserves sent artifacts.

The independent mailbox provides five starting templates. The desk provides automatic case intake and continuation, detailed CCT, ILS, OnBase and secure-mail views, and a Needs review filter. **Follow agent** tracks actual tool activity. Replies, specialist results, approvals and handoff acknowledgment automatically queue further work. The server works independently of the browser. Use [the mailbox runbook](Mailbox_Demo_Runbook.md) for presentation and [Phase 10 evidence](checkpoints/PH-10.md) for validation. Earlier loading, input and failure controls remain in the diagnostics workspace.

## Setup and data ownership

Use Python 3.12+ and Node 22.13+ for Vite and PDF.js. Run `scripts/setup.ps1`, configure `.env`, then run `scripts/start-backend.ps1`, `scripts/start-frontend.ps1` and `scripts/start-mailbox.ps1` in three terminals. Setup uses locked application dependencies and preserves an existing `.env`. The runtime archive supplies only the placeholder example and has a `PACKAGE_MANIFEST.json` of file hashes.

Backend defaults to `127.0.0.1:8000`; desk to `127.0.0.1:5173`; mailbox to `127.0.0.1:5176`. Both frontends proxy to the same backend. `npm.cmd --prefix frontend run build` produces `frontend/dist` for the desk and `frontend/dist-mailbox` for the mailbox. The backend reads the resource's Azure OpenAI v1 URL, deployment name and key. It creates no Azure resources. Configuration values remain server-side. Restart after changing them. Mailbox sends, automatic continuations, diagnostic starts and explicit live scripts make billable model calls; offline regression checks do not. The built-in mailbox requires no separate credentials.

Default `.local` holds the SQLite database, evidence copies and generated packages. Keeping that directory preserves work. Fresh instances create new case/simulation IDs; they do not erase prior data. To copy the local demo with its history, stop its servers and copy the complete data directory so database references and PDF files stay together. Copy credentials separately only when intentionally configuring the destination. No retention/purge policy is implemented.

The runtime bundle excludes private Office sources, source-path registry, existing `.env`, databases, live evaluation artifacts and development tests. Normal setup/start/build/seed and live helper scripts work from the bundle. Source reconciliation (`check-data`/`rebuild-data`) and the complete engineering suite require the original workspace and its source files. Do not interpret missing-source errors in the bundle as a runtime failure.

## Troubleshooting

| Symptom | Action and expected result |
| --- | --- |
| Agent unavailable | Check that all three Azure values are set on the backend, restart it, then inspect Setup & status. The deployment name is the Azure deployment identifier. Use the HTTPS inference URL ending `/openai/v1/`. |
| Mail saved but not processed | Inspect the conversation notice and Agent activity. Missing Azure configuration leaves work queued. An explicit stop needs explicit Resume; failed or uncertain runs need their indicated recovery. Pending mail is applied before continuation. |
| Azure authentication/deployment error | Correct the configured key, endpoint or deployment; restart and explicitly run `scripts/test-azure.ps1`. Error codes are controlled; provider response bodies and keys are not printed. |
| `azure_connection_or_timeout` | Inspect retained effects and usage, verify network/service availability, then resume. Never assume a failed request rolled back earlier simulator actions. |
| Review pause | Inspect and approve the current version, or return/edit it. Supply missing evidence on the same case and regenerate a current draft. Automatic preference cannot remove a client review requirement. |
| Uncertain result / blocked write | Use Check persisted results. For the synthetic status outage, restore status access and check again. Corrupt/missing artifacts remain blocked; no button can bless them as complete. |
| Restart appears idle | Wait for the old lease to expire, normally up to 150 seconds from its latest renewal. The same run recovers if limits/configuration permit. |
| Time/step/token limit reached | Inspect the run and remaining work, then explicitly resume for a new linked budget. Reported usage may be incomplete after an interrupted model call. |
| Stale revision / active-run conflict | Let the current mutation/run finish, refresh the case and repeat only the intended action. The server rejects stale concurrent changes. |
| Case waits instead of closing | Read the pending concern or handoff. Missing authority, consent, specialist evidence or taxonomy prevents closure intentionally. Transfer and pending are valid demo outcomes. |
| Port already in use | Keep the existing server if it is the intended workspace; otherwise stop the server you own or use the documented alternate ports in the runbook. |
| Missing/wrong/unreadable PDF | These are named test variants. Supply the correct document on the existing case, then resume. Download and send checks enforce case/file identity. |

## Verification and measurements

Final check commands from the original workspace:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1 -Browser
# Explicit live calls, isolated from normal cases:
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-workflow.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-recovery.ps1
# Build a fresh runtime archive after the guides and source are final:
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\package-demo.ps1
```

The exact final results, model-call totals, PDF inspection and clean-instance startup timings are recorded in the original workspace's Phase 9 checkpoint and acceptance ledger. These are local observations on Windows, Python 3.14, Node 25.2.1, desktop Edge and an AMD Ryzen 5 7535U (6 cores, 12 logical processors, approximately 14.8 GiB RAM). They are not production SLAs. The Azure configuration is identified by a redacted fingerprint, not resource/deployment secrets.

Default agent limits are 28 tool steps, 28 model requests, 300 elapsed seconds, 250,000 reported tokens, 1,600 completion tokens per request and a 100,000-character context bound. The reported-token threshold is checked after the request and can be exceeded by that final request. Hard-crash lease waits count against elapsed time. Backend work persists independently of browser refresh; the desktop polls active runs approximately every 1.2 seconds and idle history every 5 seconds.

Remaining required and deferred behavior is listed in [follow-up work](Follow_ups.md). No production, legal, client-policy or business-owner signoff is supplied by this handover.

## Recorded Phase 9 results

The original workspace passed 166 backend tests, all 10 desktop Edge tests, lint/format, API contract/type freshness, source/fixture reconciliation and the frontend build. The five-family live evaluation passed 11 runs; the recovery evaluation passed four runs. Together these used **112 model requests and 777,179 reported tokens**. The separate fresh-bundle browser demonstration used **10 requests and 62,538 reported tokens**. These are recorded provider totals, not a billing estimate.

The six delivered response packages (seven PDF pages including the schedule) passed identity, client, disclosure, artifact/hash and readable-layout review. No unsupported material claim or duplicate write remained in the evaluated delivered results. Some model draft proposals were rejected and corrected before delivery; those receipts remain in the evidence. Wording polish is tracked separately.

| Local observation | Recorded measurement |
| --- | --- |
| Fresh bundle backend ready, including PowerShell launcher | 14.56 seconds |
| Frontend development server ready | 5.54 seconds |
| Backend restart with six retained cases | 11.74 seconds |
| Browser workspace first render | 735 ms |
| Browser reload to retained closed case | 316 ms |
| Worklist API, 10 consecutive local reads | 9-14 ms; median 11 ms |
| Fifteen workflow/recovery runs | 12.22-75.73 seconds per run; median 30.87 seconds |
| Fresh-bundle automatic case, click to closed UI | 53.86 seconds |

These are one-machine observations, with a small read sample and the configured Azure deployment. They exclude dependency-download time and human review/input waits. Multi-stage cases use several runs; the per-run timing is not total case resolution time. Server startup, network traffic and model latency vary.

The clean install began with zero cases. Running seed twice retained five cases. The browser created one additional case and completed it. Reload and actual backend restart preserved its one run, one delivery, one indexed package and one note. The installed bundle built and ran without the private source documents. The original workspace's eight cases and credential file were retained separately.

Acceptance disposition: 26 of 30 required items pass within the recorded scope, four remain partial (AC-03, AC-04, AC-16, AC-45); three planned partial items pass their selected subsets, and 19 deferred items remain unexecuted. PH-05's standalone manual workflow is still open. See [follow-up work](Follow_ups.md).
