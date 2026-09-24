# Demo 5: ambiguous EFT request (two clarification rounds, no funds movement)

**Scenario key:** `DEMO-05` · **Client:** Northstar Residential Servicing (`DEMO-NORTH`, v2, automatic review) · **Runbook:** [Demo_Runbook §5](../../plan/Demo_Runbook.md)

A borrower gets her annual escrow statement, which shows a surplus refund by check and a lower monthly payment. She asks her servicer "Can you change this to an EFT instead?" and doesn't say which "this" she means. The agent must:

1. Confirm the sender is the borrower of record and the authorized recipient.
2. Recognize that the purpose is unknown, **ask which of three things she means** (a refund to her, automatic monthly payments, or a line-of-credit draw) and change nothing.
3. When she replies **in the same conversation** that she means the escrow refund, resume the **same case** and ask for exactly what a refund by electronic transfer needs: a signed Electronic Refund Authorization, and a voided check or bank letter.
4. Leave the case **waiting for the borrower**. No money moves. The demo has no funds-movement tool, and the agent must not hand the borrower's next step to a specialist.

Two borrower emails and two agent runs are involved. The presenter's only action is to send the prepared reply. Everything in this pack is fictional: people, company, county, insurer, loan and addresses. The escrow statement is a servicer document, so it carries no printed "synthetic" label and no demonstration footer. Its provenance marker is in the PDF metadata.

## Cast

| Who | File |
|---|---|
| **Danielle R. Foster**, borrower, Westerville OH | [people/danielle-r-foster.md](people/danielle-r-foster.md) |
| **Northstar Residential Servicing, LLC**, servicer: the three EFT meanings and what each one needs | [organization/northstar-eft-procedure.md](organization/northstar-eft-procedure.md) |
| Linden County Treasurer and Cardinal Shield Insurance Company | Appear only as payees on the escrow statement |

## Contents

| Path | What it is |
|---|---|
| [correspondence/README.md](correspondence/README.md) | The full thread in readable form: both emails from Danielle, both letters from Northstar and the servicing notes |
| `correspondence/01-inbound-request.eml` | Danielle's request (Mon Sep 21 2026, 10:30 ET) with the escrow statement attached |
| `correspondence/02-outbound-response.eml` | The clarification letter the agent sent in the live run |
| `correspondence/03-inbound-reply.eml` | Her reply: she means the escrow refund |
| `correspondence/04-outbound-response.eml` | The authorization request the agent sent after her reply |
| `correspondence/05-servicing-notes.txt` | The two ILS Standout Comments, one per delivery |
| `documents/annual-escrow-account-disclosure-statement.pdf` | Northstar's two-page escrow statement (the initial email's attachment) |
| `documents/borrower-reply-eft-clarification.pdf` | Her reply as filed on the case (inbox printout) |
| `documents/indexed-package-1-inq-email-reply.pdf`, `…-2-…` | OnBase packages for the two letters |
| `rehearsal/live-run-results.json` | Steps, tool order, token usage and checks for the captured API and Mailbox rehearsals |

The source of truth for this data is `data/fixtures/v1/DEMO-05.json` (the request and statement), `data/presenter/v1/DEMO-05.json` (the prepared reply) and `data/fixtures/v1/clients.json`. The PDFs come from `backend/app/documents.py` (`render_escrow_analysis` and `render_email_printout`), and the letters from `backend/app/response_validation.py` (`eft_letter`). The three reply texts are in `backend/app/mail_templates.py` (`EFT_REPLIES`). The captured files were generated with `scripts/build_usecase_pack.py --scenario DEMO-05 --out usecases/demo-5-eft-clarification --mailbox <run> --api <run>`.

## Key facts (all reconcile)

| | |
|---|---|
| Loan | 0099000005, 15-year fixed at 3.500%, note date June 14, 2019, $165,000.00 original; unpaid principal $96,854.49 after 86 payments; matures July 1, 2034 |
| Escrow statement | September 10, 2026; disbursements $4,600.80 a year → escrow $383.40 a month (was $424.00) |
| Monthly payment | $1,603.56 → **$1,562.96** from November 1, 2026 (principal and interest $1,179.56 unchanged) |
| Surplus | Projected low balance $1,253.07 − cushion $766.80 (two months) = **$486.27**, refunded by check within 30 days |
| Case receipt | Monday, September 21, 2026, 10:30 a.m. ET (fixed evaluation clock: September 22, 2026, noon ET) |
| Purpose | Unknown at intake (`eft_intent: null`) → `outgoing_refund` after her reply |
| Authorization | None on file (`refund_authorization: null`); still required at the end |

These facts are checked by `backend/tests/test_demo5_eft.py`. The tests confirm that the statement adds up, that the email quotes it, that the balance follows from the note terms, and that the only 10-digit number on the statement is this loan's own.

## Expected flow and outcome

1. **Mailbox → Drafts → "EFT instead of checks – loan ending 0005" → Send.** (Diagnostics: **Load DEMO-05 → Start agent**.)
2. **Run 1** (8–9 calls): `observe_case → knowledge_search → apply_plan → prepare_response → send_response → index_response → record_final_note → finish_run`. The case is **waiting for borrower**, with 1 delivery, 1 package and 1 note.
3. **Mailbox → the conversation → Reply.** The Payment type choice opens on **Refund**, with her prepared reply; **Mortgage payment** and **Line-of-credit draw** show the other two replies. **Send.** The reply continues the same case.
4. **Run 2** (8–9 calls): the same tool order. The case is still **waiting for borrower**, now with 2 deliveries, 2 packages and 2 notes. `eft_authorization_required` remains; no handoff and no task.
5. **Letters.**
   - **Clarification.** Gives the receipt date and the loan ending in 0005, and explains the three meanings in plain words, using her own figures: the $486.27 refund from the September 10 statement, and the $1,562.96 payment from November 1. It asks which one she means and says nothing has changed and no money will move without her verified written authorization.
   - **Authorization request.** Restates her request (the $486.27 refund to her bank account). It lists the two items, says how to send them without typing the account number into an email, and says no money will move until both are received and verified.
   - Both end with the Northstar signature, a reference block and the required notice.
6. **The other two branches** (not captured live; covered by tests). If she replies *Mortgage payment*, the letter asks for an ACH debit authorization plus bank proof, and tells her to keep paying as usual until the start date is confirmed. If she replies *Line-of-credit draw*, it notes that loan 0005 is a fixed-rate mortgage, asks which line she means, and asks for a signed draw request plus bank proof.

## What changed in this rework

| Area | Before | After |
|---|---|---|
| Persona | Jordan Illustrative, `jordan.illustrative@example.com`, "Can you change this to an EFT transfer?" with no context | Danielle R. Foster, whose escrow statement gives "this" two plausible meanings (the refund check or her payment); a realistic email and subject; address, phone, loan terms and escrow figures in the servicing record |
| Attachment | "Copy of the EFT inquiry", a generic sheet repeating the email | Northstar's Annual Escrow Account Disclosure Statement (payment change, disbursements, cushion, surplus and refund notice) |
| Replies | "My EFT request concerns an outgoing refund. I have not supplied signed authorization…" | Three natural replies (refund, monthly payment, line-of-credit draw) in her voice |
| Reply on the case | "Borrower clarification of EFT intent" on the generic SYNTHETIC sheet | "Borrower reply – EFT clarification": an inbox printout of the actual reply text |
| Letters | `Additional information is required to proceed.` plus rule text | A clarification letter explaining the three meanings, and a purpose-specific authorization request (refund, ACH debit or draw) that never says money has moved or will move before authorization |
| Agent end state | Sometimes asked for an unneeded "Supervisory review" handoff, leaving the case `waiting_on_department` | A server guard in `cct.handoff` refuses a handoff while all remaining work is borrower-pending and contact is permitted (`handoff_not_required`), and the system prompt says to finish `waiting_for_input` without one |

## Live rehearsal results (September 24, 2026, `gpt-5.6-sol`)

Each rehearsal used an isolated backend, a fresh database and real Azure calls (`python -m app.workflow_evaluation --live [--mailbox] --scenario DEMO-05`).

| Rehearsal | Result | Run 1: calls / time / tokens | Run 2: calls / time / tokens |
|---|---|---|---|
| New letters, no guard, API | **failed**: after the authorization request the model called `request_handoff` ("Supervisory review"), so the case ended `waiting_on_department` | 9 / 42.9 s / 58.1k | 9 / 32.5 s / 67.7k |
| Server guard only, API | passed | 9 / 34.0 s / 57.9k | 8 / 29.5 s / 57.9k |
| Server guard only, Mailbox | passed; the model tried the handoff, got `handoff_not_required` and finished correctly | 9 / 32.4 s / 57.9k | 9 / 31.8 s / 70.9k |
| Guard + prompt line, API | passed | 9 / 32.2 s / 58.0k | 9 / 32.6 s / 66.9k |
| Guard + prompt line, Mailbox | passed; no handoff attempt | 8 / 27.5 s / 50.5k | 8 / 28.9 s / 61.7k |
| **Final, API** (captured) | **passed**, all 11 checks; no rejected calls | 8 / 27.6 s / 50.3k | 8 / 29.8 s / 57.7k |
| **Final, Mailbox** (captured) | **passed**, all 15 checks; both runs triggered by email; no rejected calls | 8 / 28.5 s / 50.4k | 8 / 27.2 s / 61.9k |

Because the system prompt changed (`phase8-v3`), all five demos were re-run live on the Mailbox path (`--scenario all`), and all passed:

| Demo | End state | Calls per run | Tokens per run |
|---|---|---|---|
| DEMO-01 name change | waiting on department | 9, 14 | 61.0k, 129.2k |
| DEMO-02 amortization | closed | 10 | 61.4k |
| DEMO-03 tax | closed | 6, 5, 6 | 37.1k, 31.0k, 36.1k |
| DEMO-04 bankruptcy | transferred | 6, 7, 6, 2 | 36.2k, 53.4k, 44.5k, 10.2k |
| DEMO-05 EFT | waiting for borrower | 9, 8 | 58.0k, 61.7k |

Notes:

- **The richer letter nudged the model toward a handoff**, as the plan warned (§2.3). Pre-rework DEMO-05 runs did this occasionally too; with the new letters it happened in 2 of 3 runs before the prompt line. The server guard makes the wrong end state impossible, and the prompt line removes the wasted call.
- **The reference-block bug found live.** The first captured rehearsal showed "Request: Refund by electronic transfer" twice, because the agent had also claimed `eft_intent`. This is fixed and covered by `test_claimed_purpose_is_listed_once`, and the pack was re-captured afterwards.
- **An occasional rejected first draft** ("Evidence does not establish the claimed eft purpose"): in some runs the agent first claims a purpose before one is known. The same happened before the rework, and the validator is right to reject it. It did not occur in the captured runs.
- **Terminal key overrides `.env`.** Unset an exported `AZURE_OPENAI_API_KEY` if runs fail with `azure_http_401`.
