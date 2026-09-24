# Detailed case workspace

Open **http://127.0.0.1:5173** and type **admin** in Username. The dashboard opens immediately as **Admin — Reviewer**. The **SSO login** button sits below the username field. This MVP uses a local browser session without a password or an external identity provider. There is one fixed profile, with no registration or role creation. Refresh keeps the current tab signed in; **Sign out** returns to the login screen. The separate Mailbox has no login requirement.

Custom emails also create cases after Azure classifies the request and verifies a matching local loan record. Unknown or conflicting identities appear in **Incoming requests needing review** on the dashboard. Review the email, select the verified loan and request type, add a note, and confirm identity/authority to continue automatically. Reviewer identity is fixed to Admin and recorded with the decision. A failed model connection can be retried there. Response approvals still use the case's existing review panel.

Only **Reset mailbox** restores the separate mailbox's five drafts and clears its visible messages. Refreshing or reopening the mailbox preserves its drafts, conversations and folder choices. **Reset workspace** in the account menu (above Sign out) deletes every case and resets the mailbox; **Reset mailbox** in the mailbox does the same for the desk. See [the mailbox guide](Mailbox_UI_Guide.md).

The desktop interface follows the supplied case-screen wireframe. It uses the existing saved cases, live agent activity, documents and review decisions.

## Two independent addresses

- **Correspondence desk:** http://127.0.0.1:5173
- **Sender mailbox:** http://127.0.0.1:5176
- The standalone page is named **Mailbox** and follows the supplied Outlook reference. See [Mailbox interface](Mailbox_UI_Guide.md) for its toolbar, folders, drafts and reply flow.

Start the backend with `scripts/start-backend.ps1`, the desk with `scripts/start-frontend.ps1`, and the mailbox with `scripts/start-mailbox.ps1`, each in its own terminal. Open the two addresses manually in separate tabs; neither interface links to the other. The mailbox has its own frontend server and build, and both use the same backend.

The desk home page is the **Case dashboard**. The presenter sends a prepared email from the mailbox, and its case appears automatically on the dashboard without refreshing. Click anywhere on a case row, or use its case-number link with the keyboard, to open it. There is no app sidebar. A case has its own `/cases/{id}` address, so reload and direct links reopen it. Use **Case dashboard** above the case or the desk brand in the header to return home.

## The case screen

The header shows the saved case number, borrower, loan, client, status, original receipt, Eastern workday age, routing and contact restrictions.

| Area | What it shows and does |
| --- | --- |
| Left: Borrower correspondence | The received request, sender/recipient, original email or selected reply, and available PDF attachments. |
| Left: Case context | Borrower, loan, client, case type, owner and receipt channel. Only recorded facts are shown. |
| Middle: Agent activity | Actual tool steps, timestamps and saved results. Evidence can be expanded. Receipt buttons open the relevant system workspace. |
| Right: Response draft | The selected response version, readable letter, concern coverage and attachments. Delivered attachments open their saved response package. |

**Approve and send** approves the exact current version and lets the server continue delivery automatically. **Edit draft** opens the existing evidence-validated editor; saving produces a new response version. **Return** requires feedback and queues a revision. Review actions are unavailable while the agent is running, after sending, or when viewing an outdated version.

The response version selector also lets the presenter inspect earlier drafts. Reviewing an earlier draft does not authorize it for delivery. The backend retains its original validation and approval rules.

## Tabs and navigation

- **Case workspace:** the three columns together. The header strip shows age, route, restrictions and original receipt; **More details** under the correspondence shows property, case type, owner and channel.
- **System workspaces:** CCT (including the business assessment, concerns and routing/aging), ILS (loan and servicing facts), OnBase, Secure mail and Agent activity, which ends with **Run summary and recovery**.

The dashboard shows open cases, cases needing review, cases being processed by an agent, and completed cases (closed or transferred). Click a summary card or a filter to narrow the table. **Needs review** is the review queue. The top search finds case numbers, loan numbers, borrowers, clients and request subjects. Incoming requests and status changes update automatically.

Sending and replying happen only in the independent mailbox at port 5176. The desk shows saved correspondence inside each case. There is no mailbox route, sender button or mailbox link in the desk.

## Live activity and replay

While the agent is working, the middle panel scrolls automatically to keep the newest step in view, and its badge shows the current step. Choose a system under **System workspaces** to inspect it; processing continues on the server either way.

**Replay** steps through a completed or paused run's recorded history. It does not invoke the model, send messages or repeat system actions. The display identifies replay separately from a live run.

The five business flows, automatic triggers, human decisions and unresolved business-policy limits are unchanged. Continue with the [mailbox runbook](Mailbox_Demo_Runbook.md) for the presentation sequence.
