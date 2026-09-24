# Demo 4: credit reporting dispute after a Chapter 13 dismissal (counsel only, specialist handoff)

**Scenario key:** `DEMO-04` · **Client:** Harbor Point Mortgage Services (`DEMO-HARBOR`, v2, review required) · **Runbook:** [Demo_Runbook §4](../../plan/Demo_Runbook.md#4-specialist-handoff-conflicting-bankruptcy-evidence)

A consumer-bankruptcy attorney emails the servicer on behalf of her client. His Chapter 13 case was **dismissed without a discharge**, but his credit report shows the mortgage as **discharged in bankruptcy**, and the servicer's own bankruptcy marker says the same thing. She attaches the court's dismissal order and her client's signed authorization, disputes the reporting and asks for a written response. The agent must:

1. Honor **representative-only** contact: everything goes to counsel, nothing to the borrower's address.
2. Recognize the conflict (court order: dismissed; servicing import: discharged) and **reuse the existing Bankruptcy Team task** instead of deciding it or opening a new one.
3. Draft a written **acknowledgment of the dispute to counsel**, and wait for human review (Harbor Point reviews every letter). The acknowledgment confirms receipt, counsel-only contact, the referral and the response date. It states **no** credit reporting outcome, correction or liability.
4. After approval, send, index and note the acknowledgment, then **hand off to Compliance** with an internal routing note.
5. When the Bankruptcy Team result is recorded in ILS, reassess and record a **current** handoff that cites the determination. Send **no further letter**: Compliance owns the written response.
6. When Compliance acknowledges the handoff, finish **transferred**, not closed.

There is one attorney email, one human review and four agent runs. The other human steps are recording the Bankruptcy Team result in ILS and acknowledging the handoff as the Compliance recipient. Everything in this pack is fictional: people, law firm, court, district, case number and loan. No document carries a printed "synthetic" label; provenance markers are in the PDF metadata. The court order, because it imitates a federal court record, also prints one discreet footer line saying it is a demonstration record and not an official court record.

## The letter decision

The plan left open whether DEMO-04 should send counsel a letter at all. The original flow sent nothing and only recorded the handoff. **Decision: send one acknowledgment, and nothing else.**

- **Why a letter.** A written dispute from counsel that asks for a written response gets a prompt written acknowledgment in real servicing practice. A case that silently waits on Compliance for weeks leaves the attorney with no confirmation that the dispute arrived, no confirmation that her client will not be contacted and no response date. The assessment already supports this: before the Bankruptcy Team result, both concerns are *pending department*, and an `interim_acknowledgment` passes validation. (A `referral` does not: it needs a *referred* disposition, which exists only after the determination.)
- **Why only one.** Once the Bankruptcy Team has ruled, the substantive answer depends on Compliance's credit reporting review, which is outside the correspondence desk's authority. A second "status update" letter would add a second review cycle and would risk reading like a decision on the dispute.
- **How it is kept narrow.** The letter is rendered deterministically from checked records (`bankruptcy_letter` in `backend/app/response_validation.py`). It never mentions a reporting outcome, a correction, accuracy or liability. It states the bankruptcy status only if the draft carries a validated `bankruptcy_status` claim backed by the supported Bankruptcy Team result. That happens only if the letter is (re)drafted after the determination, for example because the determination was recorded before the first draft was approved. Server rules enforce the rest:

| Rule | Where | Code |
|---|---|---|
| Recipient must be the verified representative | existing recipient check | `wrong_recipient` |
| No information request to counsel (nothing is needed from her) | `validate_response` | `unsupported_information_request` |
| No attachments (counsel's own documents are not sent back; the Bankruptcy Team memo is internal) | `validate_response` | `irrelevant_attachment` |
| Only one letter: after the acknowledgment is sent, any new version is rejected | `validate_response` | `acknowledgment_already_sent` |
| The case cannot wait on Compliance until the acknowledgment is sent (unless contact is blocked) | `verified_outcome` | `acknowledgment_not_sent` |
| After Compliance acknowledges, the run must finish *transferred*, not keep waiting | `verified_outcome` | `handoff_acknowledged` |
| `bankruptcy_status` needs the supported specialist result; the court order alone is not enough | existing claim check | `unsupported_claim` |

## Cast

| Who | File |
|---|---|
| **Gregory P. Lindqvist**, borrower, Ashby Mill DE, and **Monica A. Ferrante**, his attorney (Ferrante & Hale, LLC) | [people/gregory-p-lindqvist-and-counsel.md](people/gregory-p-lindqvist-and-counsel.md) |
| **Harbor Point Mortgage Services, LLC**, servicer: the dispute procedure, representation rule and review gate | [organization/harbor-point-bankruptcy-disputes.md](organization/harbor-point-bankruptcy-disputes.md) |
| Hon. Eleanor V. Marsh (judge) and Thomas R. Keating (Chapter 13 trustee) | Appear only on the court order |
| Andre K. Whitcombe, Harbor Point Bankruptcy Team | Appears only in the ILS task result and the internal memo |

## Contents

| Path | What it is |
|---|---|
| [correspondence/README.md](correspondence/README.md) | The thread in readable form: counsel's email, the acknowledgment and the servicing note |
| `correspondence/01-inbound-request.eml` | Monica's email (Mon Sep 21 2026, 9:12 ET) with the court order and the authorization attached |
| `correspondence/02-outbound-response.eml` | The approved acknowledgment as delivered to counsel in the live Mailbox run |
| `correspondence/03-servicing-notes.txt` | The ILS Standout Comment for the delivery |
| `correspondence/04-handoff-routing-notes.txt` | Both CCT handoffs to Compliance with their routing notes; the second with Compliance's acknowledgment |
| `documents/order-dismissing-chapter-13-case-no-24-10382.pdf` | The court's dismissal order with a docket excerpt (email attachment) |
| `documents/authorization-to-communicate-through-counsel.pdf` | The borrower's signed authorization on the law firm's letterhead (email attachment) |
| `documents/bankruptcy-status-determination-bk-rev-260922-004.pdf` | The internal Bankruptcy Team memo (recorded in ILS; never sent) |
| `documents/indexed-package-1-inq-email-reply.pdf` | OnBase package for the acknowledgment |
| `rehearsal/live-run-results.json` | Steps, tool order, token usage and checks for the API and Mailbox rehearsals |

The source of truth for this data is `data/fixtures/v1/DEMO-04.json` (the email, both documents and the pending task), `data/presenter/v1/DEMO-04.json` (the Bankruptcy Team determination) and `data/fixtures/v1/clients.json` (Harbor Point). The PDFs come from `backend/app/documents.py` (`render_court_order`, `render_representation_letter`, `render_bankruptcy_memo`), the letter from `backend/app/response_validation.py` (`bankruptcy_letter`) and the routing notes from `backend/app/simulators/cct.py` (`routing_note`). The captured files were generated with `scripts/build_usecase_pack.py --scenario DEMO-04 --out usecases/demo-4-bankruptcy-dispute --mailbox <run> --api <run>`.

## Key facts (all reconcile)

| | |
|---|---|
| Loan | 0099000004, 30-year fixed at 4.250%, note date May 24, 2019, $185,000.00 original; unpaid principal $159,082.65 after 87 payments; current |
| Bankruptcy case | Chapter 13 No. 24-10382, United States Bankruptcy Court for the District of Brandywine; filed February 12, 2024; plan confirmed May 8, 2024 |
| Court record | Order dismissing the case entered **July 14, 2026** (Docket No. 88) on the trustee's motion; **no discharge** |
| Servicing marker | "Discharged", from the August 3, 2026 bankruptcy data import (unverified) |
| Representation | Monica A. Ferrante, Ferrante & Hale, LLC, `monica.ferrante@ferrantehale.example.com`; authorization signed September 18, 2026; representative-only contact |
| Case receipt | Monday, September 21, 2026, 9:12 a.m. ET (fixed evaluation clock: September 22, 2026, noon ET) |
| Response due | October 21, 2026 (30 days from receipt), stated in the acknowledgment and the routing note |
| Route | Compliance (RULE-04: alleged credit reporting error); no approved classification mapping (GAP-08), so closure stays blocked |
| Bankruptcy Team | Existing task `demo_bankruptcy_status_review`, reused; result `BK-REV-260922-004` confirms "dismissed without discharge" and corrects the servicing marker. The memo says it does **not** decide the credit reporting |

These facts are checked by `backend/tests/test_demo4_bankruptcy.py`. The tests check that the court order, the servicing record, the authorization, the task and the determination agree. They check the dates are in order (petition, confirmation, motion, hearing, dismissal, import, authorization, email), that the loan balance follows from the note terms, and that no document or email carries a 10-digit number other than the loan's own, which mail intake would treat as a conflicting loan.

## Expected flow and outcome

1. **Mailbox → Drafts → "Credit reporting dispute – Chapter 13 dismissal – loan ending 0004" → Send.** The sender is counsel. (Diagnostics: **Load DEMO-04 → Start agent**.)
2. **Run 1** (6–7 calls): `observe_case → knowledge_search → task_read → apply_plan → prepare_response → (request_handoff) → finish_run`. The acknowledgment pauses at **Review required**; nothing has been sent.
3. **Review queue → Approve this version.** Check that it goes to counsel, attaches nothing and states no outcome.
4. **Run 2** (7 calls): `observe_case → task_read → send_response → index_response → record_final_note → request_handoff → finish_run`. The case is **waiting on department** (Compliance). The acknowledgment appears in the Mailbox conversation.
5. **ILS → Bankruptcy status review → Record specialist result.** The earlier handoff becomes out of date.
6. **Run 3** (6 calls): `observe_case → task_read → knowledge_search → apply_plan → request_handoff → finish_run`. It records a current handoff that cites `BK-REV-260922-004`. No second letter.
7. **Response panel or ILS → Specialist handoffs → Acknowledge specialist receipt** (acting as Compliance).
8. **Run 4** (2 calls): `observe_case → finish_run(transferred)`.
9. **Result:** **Transferred** (not closed), with exactly **1 task (reused), 1 delivery (to counsel), 1 package, 1 note and 2 handoffs** (the first out of date, the second acknowledged). The classification exception and both concerns stay tracked, and the completion check still fails. That is intended.

## What changed in this rework

| Area | Before | After |
|---|---|---|
| Persona | "Taylor Fiction", `taylor.fiction@example.com`; "Demo Legal Representative" at `counsel.demo@example.com`; a two-sentence email written as the borrower but sent from counsel | Gregory P. Lindqvist, whose Chapter 13 case was dismissed. Monica A. Ferrante of Ferrante & Hale, LLC writes a realistic dispute email with the case number, the dismissal date and both documents attached. The servicing record adds address, phone, loan terms, the bankruptcy case fields and the import date of the wrong marker |
| Court record | Generic "SYNTHETIC – DEMONSTRATION ONLY" sheet, "Fictional case DEMO-BK-004" | A captioned *Order Dismissing Chapter 13 Case* (case No. 24-10382, judge's signature, entered-on-docket footer) with a docket excerpt; provenance in the PDF metadata and a demonstration footer |
| Authorization | Generic sheet, "Synthetic representation authorization" | A signed authorization on the law firm's letterhead, signed by the borrower and accepted by counsel |
| Specialist result | `DEMO-BK-RESULT-004`, generic sheet | `BK-REV-260922-004`: an internal Bankruptcy Team memo and ILS result (reviewer, time, docket entry, previous marker, and "credit reporting not determined here; referred to Compliance") |
| Letter | None | One reviewed acknowledgment to counsel, which cannot state an outcome (see *The letter decision*) |
| Handoff | Route and owner only | An internal **routing note** on every handoff, and Compliance's **acknowledgment note** when it accepts. Shown in the handoff card, and kept out of the model's view |
| Agent end state | Handoff, then wait | The acknowledgment must be sent before waiting (`acknowledgment_not_sent`). After Compliance accepts, the run must finish transferred (`handoff_acknowledged`). Prompt `phase8-v4` |
| Diagnostic representative input | `delegate.demo@example.com`, "Synthetic representative authorization" | Elena M. Ruiz of Brightpath Housing Counseling: a realistic signed *Third-Party Authorization* rendered on the agency's letterhead |

## Live rehearsal results (September 24, 2026, `gpt-5.6-sol`, prompt `phase8-v4`)

Each rehearsal used an isolated backend, a fresh database and real Azure calls (`python -m app.workflow_evaluation --live [--mailbox] --scenario DEMO-04`).

| Rehearsal | Result | Run 1: calls / time / tokens | Run 2 | Run 3 | Run 4 |
|---|---|---|---|---|---|
| API path, rehearsal 1 (prompt before the final transferred line) | **passed**, 14 checks | 6 calls | 7 | 6 | 3 |
| API path, rehearsal 2 (captured in this pack) | **passed**, all 15 checks | 7 / 28.8 s / 51.8k | 7 / 28.0 s / 59.5k | 6 / 31.7 s / 55.2k | 2 / 6.3 s / 12.0k |
| **Mailbox path** (captured in this pack) | **passed**, all 19 checks; every run triggered automatically | 6 / 23.8 s / 41.7k | 7 / 26.2 s / 49.3k | 6 / 21.2 s / 55.0k | 2 / 9.4 s / 12.0k |

After the prompt change, all five demos were re-run live on the Mailbox path (`--scenario all`). DEMO-01 to DEMO-04 passed in one pass. DEMO-05 hit a provider `azure_http_500` on its first call and passed on an immediate re-run. The live custom-mail evaluation (`python -m app.custom_mail_evaluation --live`) also passed all seven samples, including the free-form bankruptcy email.

Notes:

- **One behaviour fix came from rehearsal.** In an earlier Mailbox rehearsal the model finished the last run as *waiting for input* after Compliance had acknowledged. The case status was still *transferred*, but the run outcome was wrong. The prompt line now says to finish *transferred* once the handoff is acknowledged, and `verified_outcome` rejects *waiting_for_input* in that state (`handoff_acknowledged`). The check `final_run_transferred` was added to the evaluator.
- **Provider errors.** Several attempts failed with `azure_http_500` at different steps, including the first call of a run. The requests were 30–60k tokens, well inside limits. Each failed attempt passed when re-run a minute later. These failures are retained under `.local/mailbox-evaluations/`.
- **Tokens** are about 160–170k per rehearsal across four runs, well inside the 250k per-run budget.
- **Terminal key overrides `.env`.** As in the other demos, unset an exported `AZURE_OPENAI_API_KEY` if runs fail with `azure_http_401`.
