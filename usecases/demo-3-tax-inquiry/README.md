# Demo 3: property tax bill and scheduled escrow payment (human review)

**Scenario key:** `DEMO-03` · **Client:** Harbor Point Mortgage Services (`DEMO-HARBOR`, v2, review required) · **Runbook:** [Demo_Runbook §3](../../plan/Demo_Runbook.md#3-human-review-and-changed-evidence-tax-inquiry)

A first-time homeowner emails her servicer a copy of her township's fourth-quarter real estate tax bill. She asks whether the servicer has the bill and whether escrow will pay it before the due date. The agent must:

1. Confirm the sender is the borrower of record and the authorized recipient.
2. Reconcile the attached bill with the servicing tax line (payee, amount, due date), and reuse the **existing** Tax Team task instead of opening a new one.
3. Draft a letter that answers both questions: the bill was received, and the payment is **scheduled**, not paid. Then **stop for human review**, because Harbor Point requires review of every letter.
4. When the Tax Team result is recorded in ILS, treat the first draft as **stale** and prepare a current version that cites the review.
5. After the reviewer optionally edits and then approves **that exact version**, send it, index it, note it and **close** the case.

There is one borrower email and three agent runs. The human steps are recording the Tax Team result and reviewing the letter. Everything in this pack is fictional: people, company, township, county, school district, parcel and loan. The tax bill carries no printed "synthetic" label; its provenance marker is in the PDF metadata. Because it imitates a government record, it also prints one discreet footer line saying it is a demonstration record and not an official tax bill.

## Cast

| Who | File |
|---|---|
| **Priya S. Raman**, borrower, Wrenfield PA | [people/priya-s-raman.md](people/priya-s-raman.md) |
| **Harbor Point Mortgage Services, LLC**, servicer: the tax-inquiry procedure and review gate | [organization/harbor-point-mortgage-services.md](organization/harbor-point-mortgage-services.md) |
| Wrenfield Township Tax Collector (Denise M. Kowalczyk), Juniper County and the Wrenfield Area School District | Appear only on the tax bill |
| Marisol Vega, Harbor Point Tax Team | Appears only in the ILS task result |

## Contents

| Path | What it is |
|---|---|
| [correspondence/README.md](correspondence/README.md) | The thread in readable form: Priya's email, the letter, the three response versions with their review, and the servicing note |
| `correspondence/01-inbound-request.eml` | Priya's email (Sat Sep 19 2026, 10:30 ET) with the tax bill attached |
| `correspondence/02-outbound-response.eml` | The approved letter as delivered in the live Mailbox run |
| `correspondence/03-servicing-notes.txt` | The ILS Standout Comment for the delivery |
| `correspondence/drafts/draft-v1.txt` … `v3.txt` | All three response versions: v1 (stale after the Tax Team result), v2 (current, prepared by the agent) and v3 (the reviewer's validated edit, approved and sent) |
| `documents/2026-real-estate-tax-bill-4th-quarter-installment.pdf` | The township tax bill (the email's attachment) |
| `documents/indexed-package-1-inq-email-reply.pdf` | OnBase package for the letter |
| `rehearsal/live-run-results.json` | Steps, tool order, token usage and checks for the API and Mailbox rehearsals |

The source of truth for this data is `data/fixtures/v1/DEMO-03.json` (the email, bill and pending task), `data/presenter/v1/DEMO-03.json` (the Tax Team result) and `data/fixtures/v1/clients.json` (Harbor Point). The PDF comes from `backend/app/documents.py` (`render_tax_bill`) and the letter from `backend/app/response_validation.py` (`tax_letter`). The captured files were generated with `scripts/build_usecase_pack.py --scenario DEMO-03 --out usecases/demo-3-tax-inquiry --mailbox <run> --api <run>`.

## Key facts (all reconcile)

| | |
|---|---|
| Loan | 0099000003, 30-year fixed at 6.250%, note date April 17, 2026, $218,000.00 original; unpaid principal $217,166.15 after four payments |
| Escrow | $898.33 a month; balance $3,184.66, which covers the installment |
| Bill | Wrenfield Township Tax Collector, bill 2026-RE-04417, parcel 34-12-071-400; 2026 4th quarter (4 of 4); **$2,350.00 due October 30, 2026** |
| Levies | County 9.60 + township 5.60 + school district 24.80 = 40.00 mills on $235,000.00 = $9,400.00 a year = 4 × $2,350.00 |
| Servicer received the bill | September 18, 2026 (mortgage company copy) |
| Case receipt | Saturday, September 19, 2026, 10:30 a.m. ET (fixed evaluation clock: September 22, 2026, noon ET) |
| Payment status | **Scheduled** from escrow for **October 27, 2026**; not paid, no disbursement date or payment reference |
| Tax Team | Existing task `demo_tax_schedule_review`, reused; result `TAX-REV-260922-003` confirms "scheduled", paid at: none |

These facts are checked by `backend/tests/test_demo3_tax.py`. The tests confirm that the bill, the servicing tax line, the task and the prepared result agree. They also check that the levies add up to the installment and the annual tax, that the dates are in order (issued, received, emailed, scheduled, due), that the loan balance follows from the note terms, and that the bill contains no 10-digit number that mail intake would mistake for a conflicting loan.

## Expected flow and outcome

1. **Mailbox → Drafts → "Property tax bill – loan ending 0003" → Send.** (Diagnostics: **Load DEMO-03 → Start agent**.)
2. **Run 1** (5–7 calls): `observe_case → knowledge_search → task_read → (document_read) → apply_plan → prepare_response → finish_run`. The case pauses at **Review required**. No delivery exists yet.
3. **ILS → Tax payment schedule review → Record specialist result.** The draft from run 1 becomes stale, and **Run 2** (5–7 calls) prepares a current version that cites the Tax Team review, then pauses for review again.
4. **Review queue.** Optionally use **Edit the supported response**, for example to add the due date as a claim. The edit is validated and saved as a new version that needs its own approval. Then **Approve this version**.
5. **Run 3** (6 calls): `observe_case → send_response → index_response → record_final_note → close_case → finish_run`.
6. **Result:** **Closed**, with exactly **1 task (reused), 1 delivery, 1 package and 1 note**; the stale version was never sent.
7. **The letter** is addressed to Priya S. Raman. It gives the date her email was received and the loan ending in 0003, and confirms that the bill ($2,350.00) was received on September 18, 2026. It says the installment is scheduled to be paid from escrow on October 27, before the October 30 due date, states plainly that it **has not been paid yet**, and asks her not to pay it herself. It tells her where the payment will appear once it is made. It ends with the Harbor Point Customer Care contact, the signature, a reference block (loan, bill, amount, due date, received date, scheduled date, status "Scheduled (not yet paid)", Tax Team reference) and the Harbor Point notice.

## What changed in this rework

| Area | Before | After |
|---|---|---|
| Client | "Harbor Demo Servicing", `harbor@example.com`, signature "Synthetic correspondence only", disclosure "this is synthetic demonstration correspondence" | Harbor Point Mortgage Services v2: realistic sender, Customer Care phone and hours, mailing address, signature and the `harbor-servicing-notice` |
| Persona | Casey Demo, `casey.demo@example.com`, a two-sentence email | Priya S. Raman, a first-time homeowner whose first escrowed tax bill just arrived; a realistic email and subject; address, phone, loan terms and escrow figures in the servicing record |
| Tax bill PDF | Generic "SYNTHETIC – DEMONSTRATION ONLY" sheet reading "This is a synthetic bill…" | A township real estate tax bill: bill number, parcel/block/lot, billing period, levy table, penalty amount, a "mortgage company copy sent" marker and a remittance stub; provenance in the PDF metadata and a demonstration footer |
| Letter | `Our response to your correspondence follows.` plus raw concern text, `Tax bill received: 2026-09-18T14:30:00Z.` and `Tax payment status: scheduled.` | A signed letter that answers both questions in long-form dates, says "it has not been paid yet" and "please do not pay this installment yourself", and ends with a formatted reference block and the Harbor Point notice |
| Tax Team result | `DEMO-TAX-REVIEW-003`, status and date only | `TAX-REV-260922-003`, with the reviewer, the review time and a routing note; the ILS view labels the fields in plain words ("Confirmed payment status", "Scheduled disbursement date", "Disbursed: Not yet disbursed") |
| Review edit | Re-rendered the same generic text | The edit goes through structured claims. The re-validated rendering is stored, and it is what gets approved and sent (checked by a test) |

## Live rehearsal results (September 24, 2026, `gpt-5.6-sol`)

Each rehearsal used an isolated backend, a fresh database and real Azure calls (`python -m app.workflow_evaluation --live [--mailbox] --scenario DEMO-03`).

| Rehearsal | Result | Run 1: calls / time / tokens | Run 2 | Run 3 |
|---|---|---|---|---|
| API path, rehearsal 1 | **passed**, all 12 checks | 7 / 31.7 s / 45.1k | 7 / 30.1 s / 50.5k | 6 / 20.5 s / 35.8k |
| API path, rehearsal 2 | **passed**, all 12 checks | 6 / 22.8 s / 37.0k | 5 / 18.5 s / 30.9k | 6 / 21.3 s / 35.9k |
| **Mailbox path** (captured in this pack) | **passed**, all 16 checks; every run triggered automatically | 7 / 25.9 s / 47.0k | 5 / 20.0 s / 32.1k | 6 / 21.1 s / 36.1k |

The first attempt of the day failed before any step with `azure_connection_or_timeout` (a 60-second provider timeout on the first call). The immediate retry passed. DEMO-02 was re-run live after the shared letter-helper refactor and still passes (closed, 10 calls, 60.6k tokens).

Notes:

- **One wasted call per draft in some runs.** In API rehearsal 1, both drafting runs first tried to claim `tax_paid_at` (to say "not paid") and were rejected with "Evidence does not establish the claimed tax payment disbursed", then succeeded without that claim. Pre-rework rehearsals show the same pattern (1–3 rejections per rehearsal), so this is not caused by the new letter. The validator is right to reject it: the letter already states "not yet paid" from `tax_status = scheduled`. A one-line prompt hint could save the call, but the plan requires re-running all demos after any prompt change, so it is left for the next prompt revision.
- **The reviewer edit was a no-op in these runs.** The evaluator adds the due date as a claim only if it is missing, and the agent already claimed it. Version 3 therefore re-validated identical claims, but it still needed and received its own approval. The unit test `test_review_path_invalidates_edits_and_closes_with_the_rendered_letter` covers an edit that does change the letter (it adds "Due date: October 30, 2026"). The live check recorded as `reviewer_edit_rendered` has been renamed `due_date_in_letter` to say what it verifies.
- **Tokens** are about 110–130k per rehearsal across three runs, well inside the 250k per-run budget.
- **Terminal key overrides `.env`.** As in the other demos, unset an exported `AZURE_OPENAI_API_KEY` if runs fail with `azure_http_401`.
