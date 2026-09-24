# Demo presenter guide

This guide is for the person presenting the correspondence demo. It explains:

- how to get ready,
- how to move around the two screens,
- what to click in each of the five demos,
- what to say to the audience at each step.

You do not need to know the code. If you follow this guide from top to bottom, every demo will work.

---

## Part 1. The idea in one minute

Say this at the start. It frames everything else.

> "A mortgage servicer receives thousands of emails from borrowers: *send me my schedule*, *change my name*, *did you get my tax bill*, and so on. A person normally reads each one, looks things up in four or five company systems, writes a letter, sends it, files it and closes the case.
>
> In this demo an AI agent does that work. It reads the email, checks the facts in the company systems, decides what to do next and does it. It is not allowed to guess. Every fact in a letter must come from a record, and the software checks each action before it happens. When a person must decide something, the agent stops and waits for them."

**Say this honestly, every time:**

> "The AI is real. It is a live Azure OpenAI model making real decisions. The borrowers, loans, documents and company systems are invented and run inside this app. No real person gets a message, and no real account changes."

---

## Part 2. Before you present

### 2.1 Start the app (about 5 minutes before)

Open three terminals in the project folder and run one command in each:

| Terminal | Command | What it starts |
|---|---|---|
| 1 | `powershell -File .\scripts\start-backend.ps1` | The server and the AI agent |
| 2 | `powershell -File .\scripts\start-frontend.ps1` | The **Desk** (the caseworker screen) |
| 3 | `powershell -File .\scripts\start-mailbox.ps1` | The **Mailbox** (the borrower's email) |

Then open two browser tabs, side by side if you can:

| Tab | Address | Who it represents |
|---|---|---|
| **Mailbox** | http://127.0.0.1:5176 | The borrower (or their lawyer) sending email |
| **Desk** | http://127.0.0.1:5173 | The servicing company's staff |

The two tabs are not linked to each other. You switch between them yourself.

### 2.2 Sign in to the Desk

On the Desk login screen, type **admin** in *Username* and press Enter. You are now **Admin — Reviewer**. There is no password.

### 2.3 Check the AI is connected

Open http://127.0.0.1:8000/api/config in a spare tab. It should show `"azure_configuration_complete": true` and an empty `missing_fields` list. It never shows the key itself. If it shows `false`, the `.env` file is missing Azure settings. Fix them and restart terminal 1.

### 2.4 Start clean

In the Mailbox, click **Reset mailbox**. You can also use **Reset workspace** in the Desk's account menu; they do the same thing. This:

- empties the Inbox and Sent Items,
- puts the five prepared emails back in **Drafts**,
- deletes every case on the Desk.

Do this before each full presentation, not between demos.

### 2.5 Golden rules while presenting

1. **Send the prepared drafts unchanged.** If you edit a prepared email, the app treats it as a brand-new free-form email, and the guided follow-up steps won't appear.
2. **Wait for the agent.** Each agent run takes about 20–40 seconds. The middle column on the Desk shows every step as it happens. Talk over it; don't click ahead.
3. **The activity column follows the agent by itself.** It scrolls to keep the newest step in view. You can open other tabs (for example **System workspaces**) at any time; the agent keeps working in the background.
4. **You never press "Start" or "Resume".** Sending an email, approving a letter, or recording a result automatically starts the next agent run.

---

## Part 3. A quick tour of the screens

Show this once, during the first demo.

### The Mailbox (port 5176)

It looks like a normal email program. **Drafts** holds the five prepared emails. **Sent Items** shows what the borrower sent. **Inbox** shows the servicer's replies. Click an attachment to preview it.

### The Desk (port 5173)

**Case dashboard.** A list of cases. A new case appears here by itself a few seconds after you send an email. The cards at the top filter the list. **Needs review** shows cases waiting for a human decision.

**Case screen.** Click any case row to open it. It has three columns:

| Column | What it shows | What to say |
|---|---|---|
| **Left:** Borrower correspondence | The email and its attachments, plus basic loan details | "This is what came in." |
| **Middle:** Agent activity | Every step the AI took, in order, with the result of each step | "This is the AI thinking and acting, step by step. Nothing is hidden." |
| **Right:** Response | The letter the AI prepared, and the buttons **Approve and send**, **Edit draft** and **Return** | "This is what will go out, and where a person approves it." |

**System workspaces tab.** The company systems the AI works with. Explain them in plain words:

| System | Say it like this |
|---|---|
| **CCT** (Customer Correspondence Tracker) | "The case file: what was asked, who owns it, and its status." |
| **ILS** (Integrated Loan Servicing) | "The loan system: loan facts, specialist tasks and the notes staff leave on an account." |
| **OnBase** | "The document store: incoming documents and a saved copy of every letter we sent." |
| **Secure mail** | "The system that actually sends the letter and keeps a receipt." |
| **Agent activity** | "The full history of the AI's runs, with time and cost." |

---

## Part 4. The five demos

Suggested order: simplest first, then each demo adds one new idea.

| # | Demo (Drafts subject) | New idea it shows | Human steps | Time |
|---|---|---|---|---|
| 1 | **Amortization schedule request – loan ending 0002** | Fully automatic, start to finish | None | 2–3 min |
| 2 | **Name change request – loan ending 0001** | Asks for missing proof, then continues the same case | Send one reply | 4–5 min |
| 3 | **Property tax bill – loan ending 0003** | Human review; new information makes an old draft out of date | Record result, approve | 5–6 min |
| 4 | **Credit reporting dispute – Chapter 13 dismissal – loan ending 0004** | Legally sensitive; lawyer-only contact; handing off to specialists | Approve, record result, accept handoff | 6–8 min |
| 5 | **EFT instead of checks – loan ending 0005** | An unclear question: the AI asks before acting, and no money moves | Send one reply | 4–5 min |

> Note: the internal case codes are different from this order (for example, the amortization demo is `DEMO-02`). You don't need to mention the codes.

---

### Demo 1 — Amortization schedule (fully automatic)

**The story.** Marcus J. Delgado has had his mortgage with *Northstar Residential Servicing* for years. He emails asking for a current amortization schedule: the list of his remaining monthly payments showing how much goes to interest and how much pays down the loan.

**The key message.**

> "For a simple, safe request, the AI does the whole job with no human involved. It still checks every step, and it only closes the case when everything is truly done."

**Steps**

1. **Mailbox → Drafts →** *Amortization schedule request – loan ending 0002* → **Send**.
   > "Marcus has just emailed us. Watch the Desk."
2. **Desk.** The case appears on the dashboard. Click the row.
3. Watch the middle column. Point out:
   - The AI **reads the case** first.
   - It **looks up guidance** for this kind of request.
   - It **fetches the schedule** from OnBase and checks it belongs to this loan.
   - It **prepares the letter**, **sends it**, **files it**, **writes a note** and **closes the case**.
   > "Notice it's four separate steps after writing the letter: send, file, note, close. Sending is not the same as done. The case only closes after the software confirms all four really happened."
4. Show the result:
   - **Right column:** the letter. It is addressed to Marcus and names his loan. It says the schedule is attached, and it explains that the schedule shows principal and interest only and is not a payoff quote.
   - **Mailbox → Inbox:** the same letter arrived, with the 8-page PDF schedule.
   - **System workspaces → OnBase:** the saved package, which is the original email, the reply and the attachment in one PDF.
   - **ILS:** the note recorded on the loan.
   - **CCT:** status **Closed**.

**Expected result:** **Closed**. One letter, one saved package, one note.

**Good things to say**

- "The AI never typed the letter freely. It chose *what* to say, and the app wrote it from the loan's actual records. That's why the dates and amounts are exactly right."
- "If the schedule were missing, unreadable or for a different loan, it would not send it." (Those versions exist in the Diagnostics workspace if anyone asks.)

---

### Demo 2 — Name change (asks for missing proof, then continues)

**The story.** Lauren E. Whitaker recently got married. She emails Northstar to change the name on her loan to **Lauren E. Castellano**. She attaches a signed, dated letter, but **not** the legal proof (a marriage record) that the company requires.

**The key message.**

> "The AI knows the rules. It won't change a legal name without proof. It asks for exactly what's missing, waits, and when the proof arrives it picks up the **same** case where it left off."

**Steps**

1. **Mailbox → Drafts →** *Name change request – loan ending 0001* → **Send**. Open the attachment first if you like: it's her signed letter.
2. **Desk.** Open the new case.
3. Watch run 1. The AI reads her letter and sees that the legal document is missing. It sends a letter asking only for that document.
   > "It did *not* change the name. It explained exactly what's needed, how to send it, and that nothing has changed yet."
4. Show the result:
   - **Right column:** the request letter. It asks for a marriage certificate, divorce decree or court order.
   - **CCT:** status **Waiting for borrower**.
   - **ILS:** the name on the loan is still *Whitaker*.
5. **Mailbox.** Open Lauren's conversation (you'll see Northstar's reply in the Inbox) → **Reply**. The prepared reply opens with a **certified marriage record** attached. Preview it if you like → **Send**.
   > "Lauren replies with the proof. We're not starting a new case; this reply belongs to the same conversation."
6. **Desk.** The same case continues by itself. Watch run 2. Point out:
   - The AI reads the marriage record.
   - It **opens one task** in ILS and **performs the name update**.
   - It then **reads back the result** before saying anything to Lauren.
   - It sends a **confirmation letter**.
   > "It only tells her the name is changed *after* the system confirms the change actually happened."
7. Show the result:
   - **ILS:** the name is now *Lauren E. Castellano*. The task shows as completed.
   - **Mailbox:** two letters in one conversation (the request, then the confirmation).
   - **CCT:** status **Waiting on department**, *not* Closed.

**Expected result:** name updated, one task, two letters, case **waiting on department**.

**Explain the last point clearly.** People always ask about this.

> "Why isn't it closed? Every case must be filed under an approved category, and this type of request has no approved category yet. The AI won't invent one. It hands the case to a supervisor to decide. The borrower's request is complete; the paperwork decision belongs to a person."

---

### Demo 3 — Property tax bill (human review and changing evidence)

**The story.** Priya S. Raman bought her first home in April. Her township just sent her the fourth-quarter property tax bill: **$2,350.00, due October 30, 2026**. Her taxes are supposed to be paid from her escrow account, but this is the first bill since closing, so she emails *Harbor Point Mortgage Services* to check: did you get the bill, and will you pay it on time?

Harbor Point is a stricter client. **Every letter must be approved by a person before it is sent.**

**The key message.**

> "Two things. First, the AI respects the client's rule that a human approves every letter. Second, if new information arrives while a letter is waiting for approval, the old draft becomes out of date and cannot be sent. You can only approve the current version."

**Steps**

1. **Mailbox → Drafts →** *Property tax bill – loan ending 0003* → **Send**. Preview the attached tax bill if you like.
2. **Desk.** Open the case. Watch run 1. The AI checks the bill against the tax information on the loan (same payee, amount and due date) and finds the **existing** Tax Team task. It prepares a letter, then **stops**.
   > "It stopped because Harbor Point requires approval. Nothing has been sent."
3. Show the first draft in the right column. **Do not approve it yet.**
4. Go to **System workspaces → ILS**. Find **Tax payment schedule review** → **Specialist result ready to record** → **Record specialist result**.
   > "Now the Tax Team finishes its review. That's new information."
5. Go back to the **Case workspace**. The first draft is now marked **outdated**. The AI automatically prepares a **new version** that mentions the Tax Team's review (run 2), and stops for review again.
   > "The old draft can't be approved any more. The software knows it was written before the new information arrived."
6. **Review the current letter** in the right column. Point out these sentences:
   - The bill was received on **September 18, 2026**.
   - It is **scheduled** to be paid from escrow on **October 27, 2026**, before the October 30 due date.
   - It **has not been paid yet**, and she should **not pay it herself**, to avoid paying twice.
   > "This is the key detail. *Scheduled* is not *paid*. The AI is not allowed to say 'paid', because nothing in the records shows a payment yet."
7. *(Optional)* Click **Edit draft** to show that a reviewer can change the letter, but only by choosing supported facts, not by typing anything they like. Saving creates a new version, which needs its own approval.
8. Click **Approve and send**. The AI automatically sends, files, notes and **closes** the case (run 3).

**Expected result:** **Closed**. One task (reused, not duplicated), one letter (the approved version only).

**Good things to say**

- "The approval is tied to one exact version. If anything changes afterwards, the approval no longer counts."
- "It reused the Tax Team's existing task instead of opening a duplicate."

---

### Demo 4 — Bankruptcy and credit reporting dispute (legally sensitive)

**The story.** Gregory P. Lindqvist filed for Chapter 13 bankruptcy in 2024. The court **dismissed** his case on **July 14, 2026**, **without a discharge**. But the servicer's records, and so his credit report, say **"discharged"**. That came from a wrong data import in August.

His attorney, **Monica A. Ferrante** of Ferrante & Hale, LLC, emails Harbor Point. She disputes the credit reporting and attaches the court order and Gregory's signed authorization. She asks for all contact to go to her, not to Gregory.

**The key message.**

> "This is the most sensitive case. Bankruptcy and credit-reporting wording has legal weight. Watch what the AI does *not* do: it doesn't decide who's right, it doesn't promise a correction, and it never contacts the borrower directly. It sends the lawyer a careful acknowledgment and hands the case to the right specialists."

**Steps**

1. **Mailbox → Drafts →** *Credit reporting dispute – Chapter 13 dismissal – loan ending 0004* → **Send**.
   > "Notice the sender is the lawyer, not the borrower."
2. **Desk.** Open the case. Point out the contact restriction shown in the case header: **representative only**.
3. Watch run 1. The AI sees the conflict (court order: *dismissed*; company records: *discharged*) and finds the **existing** Bankruptcy Team task. It prepares an **acknowledgment letter to the lawyer**, then stops for review (Harbor Point reviews every letter).
4. **Review the letter** in the right column. Read out what it does and doesn't say.
   - **It says:**
     - we received your dispute and documents on September 21, 2026;
     - we will contact only you, not your client;
     - we've referred it to our bankruptcy and credit reporting specialists;
     - you will get a written response **by October 21, 2026**.
   - **It does NOT say:**
     - that anything was corrected;
     - who is right;
     - anything about how the account is reported.

     It says plainly: *"It is not the result of our investigation."*
   > "A good human caseworker would write exactly this. Acknowledge fast, promise nothing you haven't checked."
5. Click **Approve and send**. Run 2 sends the letter **to the lawyer only**, files it, notes it and records a **handoff to Compliance**.
6. Show the handoff. **ILS → Specialist handoffs** (or the right column) → click **Routing note**.
   > "This is the internal note the Compliance team receives. Loan, borrower, what the court says, what our records say, that contact is lawyer-only, that we acknowledged, and the response deadline. They can act on it without reading the whole file."
7. **ILS → Bankruptcy status review → Record specialist result.**
   > "Now our Bankruptcy Team confirms: the case was dismissed, not discharged, and they've fixed our internal record. Credit reporting itself is still Compliance's job."
8. Run 3 runs automatically. The AI records a **new, current handoff** that includes the Bankruptcy Team's finding. It does **not** send a second letter.
   > "The written answer to the lawyer belongs to Compliance, so the AI doesn't send anything else."
9. Click **Acknowledge specialist receipt** on the current handoff (you're acting as Compliance). Run 4 confirms it, and the case becomes **Transferred**.

**Expected result:** **Transferred** (not Closed). One letter, sent only to the lawyer. One reused task. Two handoffs: the first out of date, the second accepted.

**Good things to say**

- "*Transferred* means 'a named team owns it now'. The dispute isn't resolved yet, and the app is honest about that."
- "Nothing went to Gregory's own email address. The software would reject it."
- "If the AI tried to send a second letter, attach documents, or ask the lawyer for more information, the software would refuse."

---

### Demo 5 — Unclear EFT request (asks first, no money moves)

**The story.** Danielle R. Foster gets her annual escrow statement from Northstar. It says two things:

- she has a **$486.27 surplus**, refunded **by check**;
- her monthly payment goes down to **$1,562.96** from November 1.

She emails: *"Can you change this to an EFT instead?"* EFT means electronic funds transfer. But change *what*? The refund? Her monthly payments? She doesn't say.

**The key message.**

> "When a request is unclear, the AI asks instead of guessing, especially when money is involved. And it can't move money at all. There is no tool for that."

**Steps**

1. **Mailbox → Drafts →** *EFT instead of checks – loan ending 0005* → **Send**. The escrow statement is attached.
2. **Desk.** Open the case. Watch run 1. The AI realises "EFT" could mean three different things, and sends a letter explaining them (Northstar doesn't require review, so it goes out automatically):
   - a **refund** sent to her bank account instead of a check,
   - **automatic monthly payments** from her bank account,
   - a **draw from a line of credit**.

   The letter asks which one she means. It also says nothing on her account has changed and no money will move yet.
3. **Mailbox.** Open her conversation → **Reply**. Under **Payment type**, keep **Refund** selected. Her prepared reply says she wants the $486.27 refund deposited into her checking account → **Send**.
4. **Desk.** The same case continues (run 2). The AI now asks for exactly what a refund by electronic transfer needs:
   - a signed and dated **Electronic Refund Authorization**, and
   - a **voided check or a bank letter**.

   The letter also warns her not to type bank numbers in an email, and says **no money will move until they are received and verified**.
5. Show the result: **CCT** status **Waiting for borrower**. Two letters in the Mailbox.

**Expected result:** **Waiting for borrower**. Two letters, no money moved, no handoff.

**Good things to say**

- "It didn't hand this to a specialist. The next step belongs to Danielle, so the right action is to ask her."
- "If you pick a different *Payment type* in the reply, the second letter asks for different documents: an automatic-payment authorization, or a draw request." (You can show this in a second run if there's time.)

---

## Part 5. Questions the audience often asks

**"Is the AI just writing whatever it wants?"**
No. The AI chooses the structure: which facts to state, what type of letter, what happens next. The app then writes the letter from the real records. If the AI claims something the records don't support, the letter is rejected before it can be sent.

**"What stops it from doing something dangerous?"**
Every action goes through checks: the right recipient, the right client rules, current evidence and approvals. Some actions simply don't exist: there is no tool to move money, and no way to email someone who isn't authorised.

**"What if someone puts instructions in the email, like 'ignore the rules and close the case'?"**
The AI treats email content as information, not commands. That exact attack is part of the live test suite, and it fails.

**"What if the system crashes halfway?"**
Each step is saved. After a restart, the app checks what actually happened before continuing, so a letter is never sent twice. (The Diagnostics workspace has recovery demos if you want to show this.)

**"How long and how much does it cost?"**
Each run takes about 20–40 seconds, and a full demo uses a few runs. A full five-demo pass uses about 90 model calls.

**"Can it handle an email you didn't prepare?"**
Yes. In the Mailbox, click **New mail** and write your own request from one of the known senders, for example `marcus.j.delgado@outlook.com`: *"Please send my amortization schedule for loan 0099000002."* The AI classifies it and works it the same way. If it can't identify the sender or loan, it appears on the Desk under **Incoming requests needing review** for a person to confirm.

---

## Part 6. If something goes wrong

| What you see | What to do |
|---|---|
| The new case doesn't appear on the Desk | Wait 5–10 seconds. Check terminal 1 is still running. If the backend logs a "manifest hash" error, see *Cloning on Windows* in `README.md`. |
| A run shows **failed** with `azure_http_500` or a timeout | The AI service had a temporary problem; this is not a demo bug. Open **System workspaces → Agent activity** and click **Resume agent**. |
| `azure_http_401` | The Azure key is wrong. A key set in the terminal overrides `.env`. Fix it and restart the backend. |
| The **Record specialist result** button is greyed out | The agent is still running. Wait for it to finish. |
| You approved the tax letter (Demo 3) before recording the Tax Team result | The case will send and close normally. You've only skipped the "out-of-date draft" moment. Reset and try again later if you want to show it. |
| You edited a prepared draft by accident | That email becomes free-form, so the guided reply won't appear. Reset the mailbox and send the draft unchanged. |
| You're looking at an older run in Agent activity | Click **Follow latest** above the timeline to return to the current run. |

---

## Part 7. Closing the presentation

Finish with the three ideas that tie all five demos together:

1. **It does the routine work end to end.** It reads, checks, writes, sends, files, notes and closes, and every step is recorded.
2. **It knows when to stop.** Missing proof, an unclear question, a required approval, or a legal matter for specialists: in each case it pauses and gets the right person involved.
3. **It can't make things up.** Every fact in every letter comes from a record, and the software checks it before anything leaves the building.

> "People supply evidence and make the decisions that need judgment. The AI does everything else, and it shows its work."

---

### Where to find more detail

- Step-by-step runbook: [`plan/Mailbox_Demo_Runbook.md`](plan/Mailbox_Demo_Runbook.md)
- How each demo connects to the systems: [`plan/Demo_Flows_and_System_Connections.md`](plan/Demo_Flows_and_System_Connections.md)
- Screen guide: [`plan/Case_Workspace_Guide.md`](plan/Case_Workspace_Guide.md)
- Full packs for each demo (people, documents, real letters from live runs): [`usecases/`](usecases/)
