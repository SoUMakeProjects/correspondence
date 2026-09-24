# Demo 1: amortization schedule request (automatic completion)

**Scenario key:** `DEMO-02` · **Client:** Northstar Residential Servicing (`DEMO-NORTH`, v2) · **Runbook:** [Demo_Runbook §1](../../plan/Demo_Runbook.md#1-automatic-completion-amortization)

A long-standing borrower emails his servicer asking for a current amortization schedule. The agent must:

1. Confirm the sender is the borrower of record and the authorized recipient.
2. Retrieve the correct schedule from the document system and check it.
3. Email a proper letter with the schedule attached.
4. Index the sent package, record a servicing note, and close the case, with each step verified.

No human needs to act. Everything in this pack is fictional: people, company, loan and addresses. The PDFs carry a machine-readable provenance marker in their metadata rather than printed "synthetic" labels.

## Cast

| Who | File |
|---|---|
| **Marcus J. Delgado**, borrower, Westfield NJ | [people/marcus-j-delgado.md](people/marcus-j-delgado.md) |
| **Patricia L. Owens**, unrelated borrower whose schedule is misfiled in the `wrong_loan` variant | [people/patricia-l-owens.md](people/patricia-l-owens.md) |
| **Northstar Residential Servicing, LLC**, servicer | [organization/northstar-residential-servicing.md](organization/northstar-residential-servicing.md) |

## Contents

| Path | What it is |
|---|---|
| [correspondence/README.md](correspondence/README.md) | The full thread in readable form: inbound email, outbound letter, servicing note |
| `correspondence/01-inbound-request.eml` | Marcus's email (Fri Sep 18 2026, 10:30 ET), openable in any mail client |
| `correspondence/02-outbound-response.eml` | The letter the agent actually sent in the live run, with the PDF attached |
| `correspondence/03-servicing-note.txt` | The ILS Standout Comment recorded after delivery |
| `documents/loan-amortization-schedule.pdf` | The 8-page schedule held in OnBase: letterhead, loan terms, summary, annual table, 283-row schedule |
| `documents/sent-attachment-loan-amortization-schedule.pdf` | The exact bytes delivered to Marcus (same SHA-256 as the library file) |
| `documents/indexed-correspondence-package.pdf` | The OnBase package: cover page with the original request and sent response, followed by the attachment |
| `documents/variant-wrong-loan-schedule.pdf` | `wrong_loan` variant: Patricia Owens's schedule (loan 0099000099) misfiled on this case |
| `documents/variant-unreadable-schedule.pdf` | `unreadable_document` variant: a deliberately truncated PDF |
| `rehearsal/live-run-results.json` | Step timings, tool order, token usage and run summaries from the live rehearsal |

The source of truth for all of this data is `data/fixtures/v1/DEMO-02.json` and `data/fixtures/v1/clients.json`. The PDFs come from `backend/app/documents.py` (`render_amortization`), and the letter from `backend/app/response_validation.py` (`fulfillment_letter`). Regenerate the library with `from app.documents import build_documents; build_documents()`, then run `python -m app.cli check-data`.

## Key facts (all reconcile)

| | |
|---|---|
| Loan | 0099000002, 30-year fixed, 4.250%, note date March 27, 2020, original principal $312,000.00 |
| Unpaid principal | $274,025.39 after payment #77 (Sep 1, 2026) |
| Remaining | 283 payments (#78 to #360) of $1,534.85; final payment $1,536.56 on April 1, 2050 |
| Remaining interest | $160,338.87; total of remaining payments $434,364.26 |
| Escrow | Excluded from the schedule; the letter says so |

These figures are checked by `backend/tests/test_demo1_amortization.py`. The tests confirm that the principal amounts sum exactly to the balance, the balance reaches $0.00 on the maturity date, and the payment amount matches the note.

## Expected flow and outcome

1. **Mailbox → Send** (or diagnostics: **Load DEMO-02 → Start agent**, Automatic, no recovery test).
2. The agent's tool calls: `observe_case → knowledge_search → document_read → apply_plan → prepare_response → send_response → index_response → record_final_note → close_case → finish_run`.
3. **Result:** case **closed**; exactly **1 delivery, 1 indexed package, 1 final note**; the completion check is valid. Reloading does not start another run.
4. **Letter:** addressed to Marcus. It mentions the receipt date, the loan ending in 0002, the 283 payments from October 1, 2026, the $1,534.85 payment at 4.250%, the April 1, 2050 payoff date, the escrow/payoff caveat and the Customer Care contact. It ends with the Northstar signature, a reference block and the required borrower notice. Every value comes from persisted records; the model contributes only structured choices.

## Live rehearsal results (September 23, 2026)

Each run used an isolated backend, a fresh database and real Azure calls.

| Run | Model | Result | Calls / steps | Time | Tokens (prompt / completion) |
|---|---|---|---|---|---|
| Before rework, API path | gpt-6-sol (+ `reasoning_effort=none`) | closed, 1/1/1 | 10 / 10 | 36.3 s | 62,194 / 415 |
| Before rework, Mailbox path | gpt-6-sol (+ `reasoning_effort=none`) | closed, 1/1/1 | 10 / 10 | 37.2 s | about 62.7k total |
| **After rework, API path** | **gpt-5.6-sol** | **closed, 1/1/1, completion valid** | 10 / 10 | **35.0 s** | 74,259 / 676 |
| **After rework, Mailbox path** | **gpt-5.6-sol** | **closed, 1/1/1, completion valid**; case created 0.6 s after sending | 10 / 10 | **35.2 s** | 74,495 / 675 |
| After rework, `wrong_loan` variant | gpt-5.6-sol | nothing sent; department handoff (`wrong_loan`, `required_attachment_missing`) | 5 / 5 | 20.3 s | about 31.3k total |

Notes:

- **About 20% more tokens after the rework** (62.6k to 75k). The richer loan record, the longer email and the longer letter are resent to the model on each of the 10 calls. That is still well inside the budget of 28 calls, 300 s and 150k tokens (the token budget is now 250k). The completion side is small, about 68 tokens per call. After the later observation de-duplication (`backend/app/model_view.py`, September 24), a run takes about **61k tokens** (10 calls) on both the API and Mailbox paths.
- **Latency** is about 3.5 s per model call and dominates the run. The simulator and validation work is negligible, under 50 ms per step.
- **`gpt-6-sol` fails without the setting.** It rejects function tools on `/chat/completions` unless `reasoning_effort` is `none`, so every run failed at step 0 with `azure_http_400`. The app now supports `AZURE_OPENAI_REASONING_EFFORT`. `gpt-5.6-sol` works without it.
- **Terminal key overrides `.env`.** An `AZURE_OPENAI_API_KEY` exported in the terminal takes precedence over `.env`, and a stale one produces `azure_http_401` at step 0.
