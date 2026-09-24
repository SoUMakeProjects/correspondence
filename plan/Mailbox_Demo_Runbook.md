# Mailbox demo runbook

Use the desk at **http://127.0.0.1:5173** and the separate sender mailbox at **http://127.0.0.1:5176**. The presenter starts each demo by sending a prepared email. Open the resulting case in the desk to see correspondence, agent activity and the response together. No Outlook or SMTP setup is needed. The existing Azure settings in `.env` power the agent.

The [case workspace guide](Case_Workspace_Guide.md) explains the redesigned interface. In the instructions below, **ILS**, **OnBase** and **Secure mail** are under the case's **System workspaces** tab. **Review queue** refers to the **Needs review** filter on the case dashboard; response review controls are in the case's right-hand panel.

## Before presenting

In the correspondence app, type **admin** in Username to open the dashboard as **Admin — Reviewer**. The **SSO login** button is below the field. The current tab stays signed in through refresh. **Sign out** returns to the login screen. The separate Mailbox opens directly.

The first visit and **Reset mailbox** start with empty Inbox, Sent Items and Deleted Items, plus the five requests in **Drafts**. Open a draft to send a demo. Refreshing or reopening the mailbox preserves its contents and picks up later replies. Only Reset starts a new mailbox session. Reset is shared with the desk: it deletes every case, agent run and saved document, and the desk returns to an empty dashboard. The desk's **Reset workspace** (account menu) does the same.

For a free-form walkthrough, choose **New mail**. It opens a blank email without a template selector. Azure classifies the entered email and uploaded PDF text using existing loan records. Unknown loan/sender details go to **Incoming requests needing review** on the desk dashboard. See [custom request examples and limits](Mailbox_UI_Guide.md#send-a-custom-request). Click a draft or delivered attachment to open its document preview.

The standalone page is named **Mailbox**. Its light layout has folders, a message list and a reading pane sized for laptop screens. **Drafts** contains the five prepared requests and supports selection and attachment filtering; **New mail** opens a blank email. **Sent Items** contains requests and **Inbox** contains replies. See [the mailbox interface guide](Mailbox_UI_Guide.md).

Start the backend with `scripts/start-backend.ps1`, the desk with `scripts/start-frontend.ps1`, and the mailbox with `scripts/start-mailbox.ps1` in three terminals. Open both frontend addresses manually in separate tabs. Neither interface links to the other. Open **Setup & status** and check that Azure is configured. Restart the backend after changing `.env`. Sending mail makes live Azure calls.

Give the agreed verbal disclosure before presenting: borrower data and business-system connections are local demonstration records. The model calls are live. The workspaces show actual saved changes within this application. No real borrower receives a message.

Business aging uses Monday–Friday in US Eastern time, with weekday holidays counted and receipt day as day zero. Case receipt dates and the evaluation instant (22 September 2026, noon Eastern) remain fixed for repeatable scenarios. The mailbox separately displays the actual email timestamp.

## Start any of the five demos

1. Open the separate **Mailbox** at `http://127.0.0.1:5176` and open **Drafts**.
2. Open the relevant prepared request. The sender, subject, body and attachments are ready for that scenario. The bankruptcy request uses the authorized representative. There is no template dropdown.
3. Click **Send**. The server saves the email, creates a fresh linked case and starts the agent automatically.
4. Switch to the desk tab. The new case appears on the **Case dashboard** automatically; click its row to open it. Enable **Follow agent** to keep the latest activity in view. In **System workspaces**, following switches to the system being used. Model response times vary; the activity reflects the saved run.
5. When the agent waits for a human, supply the relevant reply, specialist result or approval as described below. That action automatically queues continuation.

All draft fields except To are editable, and every attachment can be removed. For the five repeatable flows below, send the prepared initial draft unchanged. Edits to its sender, subject, body or prepared attachment selection go through free-form Azure classification using the actual email and selected files. Such requests do not offer prepared demo follow-ups. PDFs and images can be added and previewed.

The unchanged template selects the starting request and evidence. The live model chooses the next tools based on that evidence and the saved results. It must pass the business checks before a system action can complete.

## What to show on each screen

| Screen | Show the audience |
| --- | --- |
| Sender mailbox (port 5176) | The original request, conversation, servicing replies and prepared borrower follow-up. Open this address manually in its own tab. |
| Case dashboard (port 5173) | Incoming cases, current status and filters. Click a row to open its detailed workspace. |
| CCT | The case number, request, owner, assessment, timeline and current status. |
| ILS | Loan facts, specialist tasks/results, supported name changes and final servicing notes. |
| OnBase | Source documents and the actual combined response PDF with case/loan references. |
| Secure mail | The saved recipient, response, attachment snapshot and delivery receipt. The same response returns to the mailbox. |
| Review queue | The current response version or handoff requiring a human decision. |
| Agent activity | The middle case panel shows tool steps, evidence references and saved receipts. Replay walks through that history without starting a new run. Detailed recovery controls are under System workspaces → Agent activity. |

Clicking a workspace name turns off screen following so you can inspect it. The agent continues on the server. Check **Follow agent** to follow again. Reloading or closing the browser does not restart the case or stop processing.

## DEMO-01: Name change

Send **Name change request – loan ending 0001** from Lauren Whitaker. Her signed and dated request letter is attached. The borrower profile, both documents and a captured live thread are in [the use-case pack](../usecases/demo-2-name-change/README.md). The agent finds that legal proof of the change is missing. It sends a signed letter asking only for that document, saves the response and leaves CCT waiting for the borrower. Nothing on the loan changes.

In the same mailbox conversation, click **Reply**. The reply with the certified marriage record opens directly; inspect its attachment and send. The new email automatically continues the case. Show the supporting document in OnBase, the single matching task and saved name update in ILS, and the confirmation delivery in secure mail. If review is requested, approve the current response in Review queue.

Expected result: the name on the loan becomes Lauren E. Castellano, with one task and two deliveries (the information request and the signed confirmation). The agent records a classification handoff; CCT remains **Waiting on department** because an approved classification is still missing. Explain that this remaining decision belongs to a supervisor.

## DEMO-02: Amortization schedule

Send **Amortization schedule request – loan ending 0002** from Marcus Delgado. No additional human action is needed. The borrower profile, documents and a captured live thread are in [the use-case pack](../usecases/demo-1-amortization/README.md). The agent checks the available schedule, delivers it, creates the OnBase package, records the ILS note and closes the CCT case.

Show the response in the mailbox, open the combined PDF in OnBase, and compare its attachment with secure mail.

Expected result: **Closed**, with one delivery, one package and one final note.

## DEMO-03: Tax inquiry

Send **Property tax bill – loan ending 0003** from Priya Raman. Her township's fourth-quarter tax bill is attached. The borrower profile, the bill, all response versions and a captured live thread are in [the use-case pack](../usecases/demo-3-tax-inquiry/README.md). The agent reconciles the bill with the servicing tax line, reads the existing Tax Team task and prepares a letter that requires review, because Harbor Point reviews every letter. Show that no delivery exists yet.

Go to **ILS**, inspect **Specialist result to record** and click **Record specialist result**. Wait for the agent to create a current response automatically. The earlier draft is now outdated.

In **Review queue**, inspect the current response. Optionally use **Edit the supported response** to make a supported change. Approve the current version. The agent automatically sends that version, saves the package and note, and closes CCT.

Expected result: **Closed**, with the existing task reused and one approved delivery. The letter confirms receipt and the October 27 scheduled escrow payment, says it has not been paid yet and asks the borrower not to pay it herself. This demo does not execute a tax payment.

## DEMO-04: Bankruptcy and credit-reporting conflict

Send the bankruptcy template from its prepared representative address. The agent detects conflicting facts, preserves the contact restriction and requests specialist involvement.

In **ILS**, review and record the prepared specialist determination. The agent automatically reads it and updates the handoff. In ILS or **Review queue**, act as the receiving specialist: review the current handoff, enter the receiving identity and acknowledge receipt. The agent automatically verifies the acknowledgment.

Expected result: **Transferred**, with the existing specialist task reused and unresolved concerns retained. The normal evaluated sequence does not send a borrower response. Any proposed response remains subject to recipient and review checks.

## DEMO-05: Unclear EFT request

Send **EFT instead of checks – loan ending 0005** from Danielle Foster, with her escrow statement attached. The borrower profile, the statement, both letters and a captured live thread are in [the use-case pack](../usecases/demo-5-eft-clarification/README.md). The agent sends a letter explaining the three possible meanings (refund, automatic payments, line-of-credit draw), asks which one she means, saves the request and waits.

In the same mailbox conversation, click **Reply**, keep **Refund** under **Payment type** (her reply asks for the $486.27 refund by direct deposit), and send. The agent automatically reads the answer and asks for a signed Electronic Refund Authorization and a voided check or bank letter.

Expected result: **Waiting for borrower**, with both requests retained. No money moves. The other Payment type choices distinguish a mortgage payment from a line-of-credit draw; the refund path is the rehearsed presentation sequence.

## Replay and recovery

Send another initial template for a fresh independent case. Use **Reply** to continue an existing case. A new message on the same loan is not assumed to belong to an earlier case; the stored conversation link makes the connection. A closed conversation no longer offers workflow replies.

If mail is saved but processing waits, read the conversation notice and **Agent activity**. Missing Azure configuration leaves the work queued. A provider failure, uncertain action or run limit requires the indicated recovery; these are not automatically retried forever.

**Stop agent** is an operator override. It stays stopped even when another email arrives. **Resume agent** processes any queued mail before starting a linked continuation. For an uncertain action, use **Check persisted results** and resolve the reported issue first. Completed deliveries are retained.

After a power interruption, the worker recovers saved work once its prior lease expires (up to about 150 seconds with default settings). A long outage may exhaust the old run's time budget; inspect the result and resume explicitly if needed.

Earlier cases and deliberate failure variations are available at **Diagnostics workspace** (`/?workspace=classic`, enabled by starting the frontend with `VITE_ENABLE_DIAGNOSTICS=true`). Those earlier cases retain their manual controls. The [earlier runbook](Demo_Runbook.md) describes them.

## Verification and limits

Run `scripts/check.ps1 -Browser` for offline regression checks. Run `scripts/test-mailbox.ps1` for an isolated live Azure evaluation of all five email-triggered demos. The latter records actual automatic runs and checks the resulting system records; it does not call the manual run-start endpoint.

See [Phase 10 evidence](checkpoints/PH-10.md) for recorded results. The [flow guide](Demo_Flows_and_System_Connections.md) explains each system connection in more detail. The existing Phase 9 runtime archive predates this extension; launch the current workspace for this presentation. The previously recorded PH-05 and business-acceptance gaps remain in [follow-up work](Follow_ups.md).
