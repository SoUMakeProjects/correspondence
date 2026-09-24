# Desktop demo runbook

**Earlier diagnostic workflow:** use the [mailbox demo runbook](Mailbox_Demo_Runbook.md) for the current presentation. This guide's manual case-loading and Start/Resume actions are available at `http://127.0.0.1:5173/?workspace=classic` when the frontend is started with `VITE_ENABLE_DIAGNOSTICS=true` (for example `VITE_ENABLE_DIAGNOSTICS=true npm --prefix frontend run dev`). The previously packaged Phase 9 archive retains this earlier interface.

Release: `0.9.0`, local synthetic MVP. Use Microsoft Edge on a desktop. All model runs make real Azure requests; all company-system effects remain local simulations. Cases use a fixed evaluation instant of 22 September 2026, noon US Eastern. The aging calendar is Eastern Monday–Friday, including weekday holidays, with original receipt as day zero.

## Prepare the workspace

From the application root, run `scripts/setup.ps1`, fill the three Azure settings in `.env`, then run `scripts/start-backend.ps1` and `scripts/start-frontend.ps1` in separate terminals. Open **http://127.0.0.1:5173** and inspect **Setup & status**. Complete configuration enables the live agent; the recorded connection-check timestamp is available after explicitly running `scripts/test-azure.ps1`.

The backend is port 8000. For a separate rehearsal alongside an existing workspace, use a newly extracted demo bundle and the environment overrides below. These variables apply to those terminals only. Do not edit a running workspace's database.

```powershell
# Backend terminal in the extracted bundle
$env:APP_PORT = '8023'
$env:APP_CORS_ORIGINS = 'http://127.0.0.1:5175'
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1

# Frontend terminal in that same bundle
$env:APP_PORT = '8023'
npm.cmd --prefix frontend run dev -- --port 5175
```

Open **http://127.0.0.1:5175** for that rehearsal. On standard ports, run the standard scripts without overrides. If a port is occupied, stop the server you started in its own terminal or choose an unused port; do not terminate an unidentified process.

Select **New case**, choose the **Case type** for the demo below, keep **Initial request**, and click **Create case**. The picker shows request titles; DEMO-01 through DEMO-05 below are reference names for the five flows. Each creation keeps earlier cases available. **Starting evidence → Follow-up received** creates a new instance with prepared evidence. To advance an existing case, use **Review and case inputs → Receive input**, followed by **Resume agent**. Give the synthetic-data disclaimer verbally before presenting; repeated demo labels are omitted from the working screens.

## 1. Automatic completion: amortization

Borrower **Marcus J. Delgado** (marcus.j.delgado@outlook.com) asks Northstar Residential Servicing for a current amortization schedule on loan 0099000002. The persona, the 8-page schedule and a captured live thread are in [`usecases/demo-1-amortization/`](../usecases/demo-1-amortization/README.md).

1. Load **DEMO-02** with **Initial request**. Inspect the actual schedule PDF (283 remaining payments, $1,534.85 P&I, maturity April 1, 2050), client, recipient and evidence.
2. Keep **Automatic where permitted** and **Recovery test: None**. Click **Start agent**.
3. Observe evidence reads, preparation and the simulated send/index/note actions. Tool order may vary with model decisions.
4. At **Case closed**, inspect **Saved response and records**, open the indexed PDF, and inspect **Run summary and recovery**.
5. Download evidence and reload the browser. The same case/run and one delivery remain; reload does not start a run.

Expected: exactly one delivery, one indexed package, one final note and verified closure. The response is a signed letter to Marcus with the schedule attached, the escrow/payoff caveat and the Northstar notice. A generated draft alone is not completion.

Measured on September 23, 2026 with `gpt-5.6-sol`: 10 model calls, about 35 s and about 61k tokens per run, in both the API and the Mailbox paths (75k before the September 24 observation de-duplication). If a run fails immediately with `azure_http_401`, check for an `AZURE_OPENAI_API_KEY` exported in the terminal; it overrides `.env`. If it fails with `azure_http_400` on a reasoning deployment, set `AZURE_OPENAI_REASONING_EFFORT=none`. On macOS/Linux, run `../.venv/bin/python -m app.cli serve` from `backend/`.

## 2. Missing information and same-case resumption: name change

Borrower **Lauren E. Whitaker** (lauren.whitaker@outlook.com) married in August and asks Northstar to change the name on loan 0099000001 to **Lauren E. Castellano**. She attaches a signed and dated request but no legal proof. The persona, both documents and a captured live thread are in [`usecases/demo-2-name-change/`](../usecases/demo-2-name-change/README.md).

1. Load **DEMO-01** with **Initial request** and start the agent.
2. The response requests the missing legal evidence; the case waits for the borrower. Inspect that specific request and its recorded delivery.
3. Under **Review and case inputs**, receive **Supply legal name-change document** on this case, then **Resume agent**. If review is required, inspect and approve the current version before resuming.
4. Inspect the completed name task, supported name-update confirmation, both sent versions and their packages/notes.

Expected: one task and a verified update; two retained response deliveries. The first is a letter asking only for the legal document; the second is a signed confirmation of the new name. Both end with the Northstar notice. The agent then requests the classification handoff. The case remains **waiting on department** because the source taxonomy lacks an approved operational classification for this name workflow. The supervisory handoff is intentional and must not be presented as closure.

Measured on September 23, 2026 with `gpt-5.6-sol`: run 1 took 9 model calls, about 32–36 s and about 61k tokens. Run 2 took 13 calls, about 43–50 s and 110–116k tokens, in both the API and the Mailbox paths (130–140k before the September 24 observation de-duplication). That is well inside the 250k per-run token budget. If a run still pauses with `max_total_tokens`, click **Resume agent**.

An alternative missing-document demo is DEMO-02 with **Missing document**. Receive the correct amortization document on that same case and resume.

## 3. Human review and changed evidence: tax inquiry

Borrower **Priya S. Raman** (priya.raman@outlook.com), a first-time homeowner in Wrenfield Township, PA, attaches her 2026 fourth-quarter real estate tax bill ($2,350.00, due October 30, 2026) and asks Harbor Point Mortgage Services whether it has the bill and whether escrow will pay it before the due date. The persona, the bill, all three response versions and a captured live thread are in [`usecases/demo-3-tax-inquiry/`](../usecases/demo-3-tax-inquiry/README.md).

1. Load **DEMO-03** and start. Its client (Harbor Point) requires review, even if the run preference says automatic.
2. At the review pause, receive **Supply Tax Team result**. The old draft becomes stale. Resume for a current draft.
3. Inspect **Response to review**. Scheduled payment must remain distinct from paid. Optionally use **Return for changes** with a note, then **Edit the supported response** and save a validated revision.
4. Approve the current version and resume. Inspect the exact approved version in the delivery and combined PDF.

Expected: current-version approval, one existing tax task, one delivery/package/note and closure. The letter confirms the bill was received on September 18, 2026 and that the installment is scheduled to be paid from escrow on October 27, 2026, before the due date. It says the installment **has not been paid yet** and asks the borrower not to pay it herself, and it ends with the Harbor Point notice. An unsupported claim such as changing scheduled to paid is rejected. New material evidence invalidates an earlier approval. This fixture covers receipt and scheduling of a combined municipal/county/school real estate tax bill; school-tax/TAR estimate branches remain open.

Measured on September 24, 2026 with `gpt-5.6-sol`: three runs of 5–7, 5–7 and 6 model calls, about 20–32 s each and about 110–130k tokens in total, in both the API and the Mailbox paths.

## 4. Specialist handoff: conflicting bankruptcy evidence

1. Load **DEMO-04**, inspect the contradiction and representative restriction, and start.
2. Inspect the recorded handoff. Receive **Supply bankruptcy specialist determination** and resume.
3. Inspect the current handoff and acknowledge receipt as the signed-in reviewer, **Admin**. Resume once more.

Expected: the existing task is reused, supplied determination is inspected, restrictions stay enforced and the case becomes **transferred**. No borrower message is needed to establish the handoff. Transfer does not resolve every concern or mean closed. Do not claim this fixture implements all bankruptcy response rules.

## 5. Clarification: EFT intent

Borrower **Danielle R. Foster** (danielle.foster@outlook.com) attaches Northstar's annual escrow statement, which shows a $486.27 surplus refund by check and a new $1,562.96 payment from November 1. She asks "Can you change this to an EFT instead?" without saying which one she means. The persona, the statement, both letters and a captured live thread are in [`usecases/demo-5-eft-clarification/`](../usecases/demo-5-eft-clarification/README.md).

Load **DEMO-05** and start. The first letter explains the three things an electronic transfer could mean (a refund, automatic monthly payments, a line-of-credit draw) and asks which one. After it is sent, receive **Clarify the EFT purpose**, choose **Outgoing refund**, and resume. Inspect the resulting request for a signed Electronic Refund Authorization and a voided check or bank letter.

Expected: the case stays **waiting for borrower**; consent is still missing. Both letters say no money will move until the authorization is received and verified. Incoming payment and draw options produce their own requests (an ACH debit authorization, or a draw request). There is no funds-movement tool, and a handoff is refused while the borrower owns the next step (`handoff_not_required`).

Measured on September 24, 2026 with `gpt-5.6-sol` (prompt `phase8-v3`): 8–9 model calls per run, about 28–33 s and 50–67k tokens, in both the API and the Mailbox paths.

## 6. Partial failure and recovery

1. Load a fresh **DEMO-02**, open **Advanced controls → Recovery test**, choose **Indexing failure after delivery**, and start.
2. Inspect the saved delivery and failed index receipt. The case must not be closed. Click **Resume agent**.
3. Verify one retained delivery, successful indexing/final note and closure.

For uncertainty, load another DEMO-02 with **Send result and status unavailable**. At the pause, use **Check persisted results**: it remains blocked. Use **Restore status access**, then **Check persisted results** again. Only after verification succeeds, resume. The original send is reused; there must still be one delivery.

The lost-send-result and lost-new-task-result options demonstrate the same receipt verification without a status outage. Faults fire once at the matching action of a new run; a workflow that never reaches that action will not trigger the fault. Resume adds no new fault.

## Stop, restart and replay

**Stop agent** stops at a safe action boundary and stays stopped until explicitly resumed. Completed effects remain. Ctrl+C stops a server; restart it with the same data directory to retain cases and PDFs. Graceful shutdown requeues active work. A hard exit/power loss waits for the prior lease to expire before recovery: model request timeout plus 90 seconds, normally 150 seconds.

Elapsed time includes outage waits. A long interruption may exhaust the saved run's time budget; inspect its result and use **Resume agent** to start a linked budget. Never clear the database to resolve an uncertain effect. If configuration changes during interruption, inspect the saved run and explicitly resume using the current settings.

For another demo, load a fresh scenario or run `scripts/seed-demo.ps1 -Fresh`. Keep `.local` to retain history. Exports are text-free reference manifests of selected-run metrics and current case references; actual response PDFs are opened separately. See [handover](Handover.md) for troubleshooting and measured limits, and [follow-up work](Follow_ups.md) for the remaining scope.
