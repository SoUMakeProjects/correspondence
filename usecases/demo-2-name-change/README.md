# Demo 2: legal name change (missing evidence and same-case resumption)

**Scenario key:** `DEMO-01` · **Client:** Northstar Residential Servicing (`DEMO-NORTH`, v2) · **Runbook:** [Demo_Runbook §2](../../plan/Demo_Runbook.md#2-missing-information-and-same-case-resumption-name-change)

A borrower who recently married emails her servicer to change the name on her mortgage. She attaches a signed and dated request but no legal proof of the change. The agent must:

1. Confirm the sender is the borrower of record and the authorized recipient.
2. Check the evidence against Northstar's procedure, find that the legal document is missing and **ask for it without changing anything**.
3. When she replies with a certified marriage record **in the same conversation**, resume the **same case**. Open one name-update task, carry out the update in ILS and read back the result.
4. Confirm the new name in writing, then index and note both letters.
5. Hand the case to a supervisor, because no approved classification exists for this request. The case stays **waiting on department** and is **not** closed.

Two borrower emails and two agent runs are involved. The presenter's only action is to send the prepared reply. Everything in this pack is fictional: people, company, court, loan and addresses. The borrower's letter carries no printed "synthetic" label; its provenance marker is in the PDF metadata. The marriage record also has the metadata marker. In addition, it prints one discreet footer line saying it is a demonstration record and not an official document, because it imitates a government record.

## Cast

| Who | File |
|---|---|
| **Lauren E. Castellano** (formerly Whitaker), borrower, Upper Arlington OH | [people/lauren-e-castellano.md](people/lauren-e-castellano.md) |
| **Northstar Residential Servicing, LLC**, servicer: the name-change procedure | [organization/northstar-name-change-procedure.md](organization/northstar-name-change-procedure.md) |
| Daniel R. Castellano (spouse, not on the loan) and the fictional Probate Court of Linden County, Ohio | Appear only on the marriage record |

## Contents

| Path | What it is |
|---|---|
| [correspondence/README.md](correspondence/README.md) | The full thread in readable form: both emails from Lauren, both letters from Northstar, and the servicing notes |
| `correspondence/01-inbound-request.eml` | Lauren's request (Thu Sep 17 2026, 10:30 ET) with her signed letter attached |
| `correspondence/02-outbound-information-request.eml` | The information request the agent sent in the live run |
| `correspondence/03-inbound-reply.eml` | Her reply, with the certified marriage record attached |
| `correspondence/04-outbound-confirmation.eml` | The confirmation the agent sent after the ILS update |
| `correspondence/05-servicing-notes.txt` | The two ILS Standout Comments, one per delivery |
| `documents/signed-name-change-request.pdf` | Her one-page signed and dated letter to Northstar (the initial email's attachment) |
| `documents/certified-copy-of-marriage-record.pdf` | Certified copy of the marriage record (the reply's attachment) |
| `documents/indexed-package-1-information-request.pdf` | OnBase package for the first letter |
| `documents/indexed-package-2-name-change-confirmation.pdf` | OnBase package for the confirmation |
| `rehearsal/live-run-results.json` | Steps, tool order, token usage and checks for both live rehearsals (API and Mailbox paths) |

The source of truth for all of this data is `data/fixtures/v1/DEMO-01.json` (the initial request), `data/presenter/v1/DEMO-01.json` (the reply's evidence) and `data/fixtures/v1/clients.json`. The PDFs come from `backend/app/documents.py` (`render_name_change_request` and `render_marriage_record`), and the letters from `backend/app/response_validation.py` (`name_change_letter`). The reply text is in `backend/app/mail_templates.py`. Regenerate the library with `from app.documents import build_documents; build_documents()`, then run `python -m app.cli check-data`.

## Key facts (all reconcile)

| | |
|---|---|
| Loan | 0099000001, 30-year fixed, note date June 11, 2021, unpaid principal $187,450.00 |
| Name on the loan | Lauren E. Whitaker → **Lauren E. Castellano** |
| Signed request | Dated September 16, 2026; states the current and new names and the reason (marriage) |
| Legal document | Certified copy of marriage record, Probate Court of Linden County, Ohio; license 2026-ML-01873; married August 22, 2026; recorded August 27; certified September 8 |
| Case receipt | September 17, 2026, 10:30 a.m. ET (fixed evaluation clock: September 22, 2026, noon ET) |
| Update | One `demo_profile_name_update` task; completed September 22, 2026; reference `DEMO-NAME-<action id>` |

These facts are checked by `backend/tests/test_demo2_name_change.py`. The tests confirm that the request, the certificate, the task result and the loan record agree on both names, that the dates are in order, and that the certificate contains no 10-digit number that mail intake would mistake for a conflicting loan.

## Expected flow and outcome

1. **Mailbox → Drafts → "Name change request – loan ending 0001" → Send.** (Diagnostics: **Load DEMO-01 → Start agent**.)
2. **Run 1** (8–9 calls): `observe_case → knowledge_search → (document_read) → apply_plan → prepare_response → send_response → index_response → record_final_note → finish_run`. The case is **waiting for borrower**, with 1 delivery, 1 package and 1 note. Nothing on the loan has changed.
3. **Mailbox → the conversation → Reply** (the marriage-record reply opens prepared) **→ Send.** The reply continues the same case.
4. **Run 2** (13 calls): `observe_case → knowledge_search → document_read → create_task → update_name → task_read → apply_plan → prepare_response → send_response → index_response → record_final_note → request_handoff → finish_run`.
5. **Result:** name updated in ILS; **exactly 1 task, 2 deliveries, 2 packages, 2 notes**; the first letter is kept unchanged. The case is **Waiting on department** with `classification_mapping_missing` and a current handoff.
6. **Letters.** The first letter is addressed to Lauren E. Whitaker. It gives the receipt date and the loan ending in 0001, confirms that the signed request dated September 16 is on file, asks only for the legal document (with acceptable examples), gives reply and postal options, and says nothing has changed yet. The second letter is addressed to Lauren E. Castellano. It confirms the new and previous names and the completion date, says the loan terms are unchanged, and notes that the deed and insurance are separate records. Both letters end with the Northstar signature, a reference block and the required notice.

## What changed in this rework

| Area | Before | After |
|---|---|---|
| Persona | "Avery Sample → Avery Example", `avery.sample@example.com`, one-line email | Lauren E. Whitaker → Lauren E. Castellano after her marriage, a realistic email and reply, with address, phone and loan details in the servicing record |
| Signed request PDF | Generic "SYNTHETIC – DEMONSTRATION ONLY" metadata sheet | Her own signed and dated letter to Northstar, with pen-style signature; provenance in PDF metadata |
| Legal document PDF | Two sentences on a generic sheet | Certified copy of a marriage record from a fictional probate court, with both parties, license, dates and certifying clerk |
| Information request | `Additional information is required to proceed.` plus raw concern and rule text | A signed letter that names the missing item and acceptable documents, gives how to send it and says nothing has changed yet |
| Confirmation | `Our response to your correspondence follows.` plus `Current legal name: …` and `Completed action reference: …` | A signed letter confirming the new and previous names and the date, with what the change does and does not cover and a reference block |
| Agent end state | The model had to infer the classification handoff | The system prompt names it; the server also rejects `finish_run(waiting_for_input)` without the handoff (`handoff_required`), so the case cannot be left `records_incomplete` with no owner |
| Tokens | Every call resent the full letter bodies | Rendered bodies are no longer sent to the model (it never writes prose), which offsets the longer letters |

## Live rehearsal results (September 23, 2026, `gpt-5.6-sol`)

Each rehearsal used an isolated backend, a fresh database and real Azure calls (`python -m app.workflow_evaluation --live [--mailbox] --scenario DEMO-01`).

| Rehearsal | Result | Run 1: calls / time / tokens | Run 2: calls / time / tokens |
|---|---|---|---|
| Generic letters (for comparison), API path | passed | 9 / 32.6 s / 74.4k | 13 / 50.5 s / 133.8k |
| New letters, before the prompt/guard fix, API path (2 runs) | **failed**: the model skipped `request_handoff`, leaving the case `records_incomplete` | 9 / 33–34 s / 75k | 12 / 45–51 s / 124k |
| **After rework, API path** | **passed**, all 10 checks | 8 / 30.4 s / 63.4k | 13 / 48.5 s / 130.3k |
| **After rework, Mailbox path** | **passed**, all 14 checks; both runs triggered by email | 9 / 31.3 s / 74.7k | 13 / 46.6 s / 139.7k |

DEMO-02 (amortization) was re-run live after these changes and still passes (closed, completion verified).

Notes:

- **The richer confirmation letter changed the model's behaviour.** With the generic body, the model went on to request the classification handoff. With a letter that reads as finished, it stopped after the note, twice in a row. Two fixes now prevent this: an explicit sentence in the system prompt, and a server-side check in `verified_outcome` that rejects the pause until the handoff exists.
- **Run 2 was close to the old token budget.** It uses about 130–140k tokens. That was 87–93% of the old 150k-per-run limit (`AGENT_MAX_TOTAL_TOKENS`), and the comparison run with generic letters already used 134k. The default is now **250k**, which leaves room for several extra steps. Each of the 13 calls resends the full case observation, which is about 18–22k characters. The loan context appears in it up to three times: the loan, the servicing record and the mail-reply evidence. If a run ever hits the limit, it pauses with `max_total_tokens` and **Resume agent** continues it.
- **Later de-duplication (September 24).** The model now receives a compact observation that sends the loan context and client configuration once (`backend/app/model_view.py`). Re-measured live: run 1 took 9 calls and 61k tokens; run 2 took 13 calls and 110–116k tokens, down from 130–140k. Both the API and Mailbox paths passed.
- **Latency** is about 3.5–4 s per model call. Two borrower emails make the demo about 80 s of agent time in total.
- **Terminal key overrides `.env`.** As in Demo 1, unset an exported `AZURE_OPENAI_API_KEY` if runs fail with `azure_http_401`.
