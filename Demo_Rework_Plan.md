# Remaining demo rework plan (DEMO-03, DEMO-04, DEMO-05)

This file records what was done to rework **Demo 1 (DEMO-02, amortization)** and **Demo 2 (DEMO-01, name change)**, and lists what the three remaining demos need to reach the same standard. The two finished demos are the reference implementations:

- [`usecases/demo-1-amortization/`](usecases/demo-1-amortization/README.md)
- [`usecases/demo-2-name-change/`](usecases/demo-2-name-change/README.md)

The remaining demos are listed in the recommended order: **tax inquiry**, then **EFT clarification**, then **bankruptcy / credit-reporting conflict**.

---

## 1. The pattern (what "reworked" means)

Each reworked demo gets all of the following. Treat this as the definition of done.

| # | Area | What to do | Where (Demo 1 / Demo 2 examples) |
|---|---|---|---|
| 1 | **Persona and story** | Replace placeholder people (`Casey Demo`, `Taylor Fiction`, `Jordan Illustrative`) with a believable borrower and a reason for writing. Give the loan context real address, phone, occupancy and loan-term keys that the UI already labels (`frontend/src/systems/format.ts`). Use `@outlook.com` or `@example.com` only (enforced by `ScenarioFixture.borrower_email` in `backend/app/fixture_contracts.py`). | `data/fixtures/v1/DEMO-02.json`, `DEMO-01.json` |
| 2 | **Correspondence text** | Write a realistic email (greeting, context, request, sign-off with phone) and a realistic email subject for `title` (it becomes the mailbox subject and the case-type picker entry, e.g. "… – loan ending 000X"). Write realistic reply templates too. | `correspondence_text`, `backend/app/mail_templates.py` |
| 3 | **Documents** | Add a dedicated renderer in `backend/app/documents.py` so each document looks like the real thing: servicer letterhead, the borrower's own signed letter, a government or court record, and so on. Leave out the printed "SYNTHETIC" banner. Put provenance in the PDF `keywords` via `_provenance()`, including `SYNTHETIC`, the loan number, the client code and the title (checked by `app.cli check-data`). Records that imitate government or court documents also get a one-line footer saying they are demonstration records and not official. **Never print another 10-digit number:** mail intake treats it as a conflicting loan (`mail_attachments.py`). | `render_amortization`, `render_name_change_request`, `render_marriage_record` |
| 4 | **Letters** | Add a deterministic letter renderer in `backend/app/response_validation.py`. Build every variable part from persisted records (case receipt, loan record, identity-checked evidence, completed task results, client configuration and validated claim lines). The model only chooses structure. Return `None` when prerequisites are missing so the generic checked rendering is used as a fallback. Chain it after the existing renderers (`fulfillment_letter(...) or name_change_letter(...) or …`). | `fulfillment_letter`, `name_change_letter`, `_reference_block` |
| 5 | **Letter anatomy** | Every letter has: "Dear <name>,"; a receipt sentence (date and loan ending); the substance; a caveat about what it does *not* mean; a contact paragraph with Customer Care phone and hours; "Thank you for choosing …"; "Sincerely," plus the client signature; a reference block (loan number plus claim lines renamed into plain labels); and the client's required notice. | See both letter functions |
| 6 | **Presenter follow-ups** | Make `data/presenter/v1/DEMO-0X.json` consistent with the new persona: document titles, facts and task results must match the loan context exactly, because the assessment compares them. | `data/presenter/v1/DEMO-01.json` |
| 7 | **Agent end state** | Run it live and check that the model still reaches the intended end state with the richer letter. Demo 2 showed that a "finished-sounding" letter can make the model skip a required step. If that happens, add a one-line instruction to `SYSTEM_PROMPT` (`backend/app/agent_contracts.py`) **and** a server guard in `verified_outcome` (`backend/app/agent_tools.py`). | `handoff_required` guard for `classification_mapping_missing` |
| 8 | **Tests** | Add `backend/tests/test_demoN_<topic>.py` covering: the fixture reconciles internally; the PDF contains the expected facts, no printed "SYNTHETIC", provenance in metadata and no stray 10-digit numbers; mail templates; each letter's key sentences; and the end-state guard. Update existing tests that assert the old names or emails. | `test_demo1_amortization.py`, `test_demo2_name_change.py` |
| 9 | **Regenerate and check** | From `backend/`, run `python -c "from app.documents import build_documents; build_documents()"`, then `python -m app.cli check-data`, `python -m app.cli check-openapi`, `ruff check . && ruff format --check .` and `pytest`. | |
| 10 | **Live rehearsal** | Run `python -m app.workflow_evaluation --live --scenario DEMO-0X` and the same with `--mailbox`. Unset any `AZURE_OPENAI_API_KEY` exported in the terminal first (`env -u AZURE_OPENAI_API_KEY …`), because it overrides `.env`. Record calls, time and tokens per run. Re-run DEMO-01 and DEMO-02 afterwards if the prompt, observation or shared letter code changed. | `.local/{workflow,mailbox}-evaluations/<id>/results.json` |
| 11 | **Use-case pack** | Create `usecases/demo-N-<topic>/` with: `README.md` (scenario, cast, contents, key facts, expected flow, a before/after table, live results and notes); `people/`; `organization/` (the procedure); `correspondence/` (`.eml` files with attachments, `README.md` with readable text, servicing notes); `documents/` (source PDFs and indexed packages); and `rehearsal/live-run-results.json`. | Both existing packs |
| 12 | **Docs** | Update `plan/Demo_Runbook.md`, `plan/Mailbox_Demo_Runbook.md`, `plan/Mailbox_UI_Guide.md` (the recognized-sender table), `data/README.md` (the scenario table) and `README.md` (the five-family walkthrough). | |
| 13 | **Evaluations** | Update the hard-coded senders and bodies in `backend/app/custom_mail_evaluation.py` and the checks in `backend/app/workflow_evaluation.py` (e.g. `counsel.demo@example.com`). | |

---

## 2. Cross-cutting work to do first

These affect more than one remaining demo. Doing them first avoids repeated work.

### 2.1 Rebrand the Harbor client (blocks DEMO-03 and DEMO-04)

**Done:** Harbor is now client **version 2**, "Harbor Point Mortgage Services" (`correspondence@harborpointmortgage.com`, (888) 555-0187, signature "Customer Care Team\nHarbor Point Mortgage Services", `review_required` kept). The new disclosure `harbor-servicing-notice` v1 is in `curated.v1.json` (the old `demo-disclosure-harbor` item is untouched; `reconciliation.v1.json` count is now 17). `clientName()` and the phrase replacements in `presentation.ts` are updated. `test_newer_client_version_supersedes_stored_configuration` is parametrized over both clients, and `test_harbor_keeps_review_gate_and_realistic_contact_details` was added.

DEMO-03 and DEMO-04 use `DEMO-HARBOR`, which still looks like a placeholder:

- `sender_email: harbor@example.com`
- `signature: "Harbor Demo Servicing | Synthetic correspondence only"`
- disclosure `demo-disclosure-harbor`: "this is synthetic demonstration correspondence…"

Follow what Demo 1 did for Northstar:

1. In `data/fixtures/v1/clients.json`, bump Harbor to **version 2**. Add `legal_name`, a realistic `sender_email` and `support_email`, `support_phone`, `support_hours`, `mailing_address`, `website` and a real signature (e.g. "Customer Care Team\nHarbor Point Mortgage Services"). Keep `default_review_mode: review_required`, because DEMO-03 depends on the review gate.
2. Add a curated disclosure such as `harbor-servicing-notice` to `data/knowledge/curated.v1.json` (a new key with `version 1`; don't edit the existing item). Point `disclosure_keys` at it.
3. Update `clientName()` in `frontend/src/presentation.ts` and the phrase replacements that strip the old Harbor disclosure and signature.
4. `install_catalogs` already upgrades a stored client when the fixture version is higher. Extend `test_newer_client_version_supersedes_stored_configuration` to cover Harbor.

### 2.2 Shared letter helpers

**Done:** `response_validation.py` now has `_salutation`, `_contact_paragraph(settings, lead)`, `_closing(client)`, `_disclosures(candidate, applicable)` and `_letter(parts)`; `_reference_block(lines, None, ...)` omits the added loan line. `fulfillment_letter`, `name_change_letter` and the generic rendering use them. Output was checked byte-identical against a snapshot of every letter rendered by the test suite (UUIDs normalised).

`name_change_letter` introduced `_reference_block`, plus contact and closing paragraphs built from client settings. Before writing three more letters, pull the shared parts into small helpers (`_salutation`, `_contact_paragraph(settings)`, `_closing(client)`, `_disclosures(candidate, applicable)`). Then each scenario function contains only its own paragraphs. Keep `fulfillment_letter` and `name_change_letter` output byte-identical: their tests assert exact sentences.

### 2.3 Token budget and observation size

- **Done:** the default `AGENT_MAX_TOTAL_TOKENS` is now **250,000** per run (was 150,000), in `backend/app/config.py`, `.env.example`, `README.md`, `plan/Handover.md` and `plan/decisions/006-agent-orchestration.md`. **Restart the backend** to pick it up. `.env` does not override it.
- **Done:** rendered letter bodies are no longer sent to the model in `observe()`.
- **Done:** the model now receives a compact view of the observation (`backend/app/model_view.py`, applied in `AzureModel.choose`). It references the known repeats with `{"$same_as": "<path>"}`: the client configuration inside the loan context, servicing-record and mail evidence facts that equal `loan.context`, and the case repeated in `related_cases`. It also omits storage keys, hashes and creation keys. Observations shrink by about 25%, and measured tokens per run fell 16–18% (DEMO-02: 74k → 61k; DEMO-01 run 2: 130–140k → 110–116k). A live mailbox run of all five demos passed.
- **Keep the view targeted.** A generic "reference any repeated value" pass cut 40%, but it also referenced the assessment's concerns and routing. In live DEMO-05 runs the model then requested an unnecessary handoff 4 times out of 4, compared with 0 out of 3 with the full observation. The assessment, case plan, handoffs and saved artifacts must stay verbatim. When the observation gains new sections for DEMO-03, DEMO-04 or DEMO-05, add explicit rules to `model_view`, not a generic pass, and re-run the affected demo live.

### 2.4 Generic document renderer and labels

- `render_document` in `documents.py` still prints "SYNTHETIC - DEMONSTRATION ONLY" and a fixture metadata table for every document without a dedicated renderer. It also prints "Morgan Example" / `DEMO-CC-099` for wrong-loan variants. After the three demos below, the only remaining users should be diagnostic variants.
- `presenter-input` documents created in `backend/app/workflow.py` (EFT clarification, representative authorization) are rendered with the generic sheet and hard-coded text such as `delegate.demo@example.com`. Each needs realistic facts and a renderer.
- `frontend/src/presentation.ts` maps several `Synthetic …` titles (court-status record, representation authorization, bankruptcy determination). When the titles change, remove the entries that are no longer used.

### 2.5 Reusable pack builder (optional but recommended)

**Done:** `scripts/build_usecase_pack.py --scenario DEMO-0X --out usecases/<pack> --mailbox <dir> [--api <dir>]` writes the `.eml` thread with attachments, the servicing notes, all response versions and reviews (when there is more than one draft), the source PDFs and indexed packages, the readable `correspondence/README.md` and `rehearsal/live-run-results.json`. The README, `people/` and `organization/` are still written by hand.

Demo 2's pack was generated with throwaway scripts that open the evaluation data directory, read run summaries, artifacts and package PDFs, and write `.eml` files. Moving that into `scripts/build_usecase_pack.py --scenario DEMO-0X --api <dir> --mailbox <dir>` would make the next three packs quick to build and consistent.

---

## 3. DEMO-03: tax bill receipt and scheduled payment (human review)

**Done (September 24, 2026).** Priya S. Raman, a Harbor Point escrowed loan, Wrenfield Township tax bill (`render_tax_bill`), `tax_letter`, a Tax Team result `TAX-REV-260922-003`, `backend/tests/test_demo3_tax.py`, ILS labels, evaluation checks, docs and the pack [`usecases/demo-3-tax-inquiry/`](usecases/demo-3-tax-inquiry/README.md). Live: 2 API and 1 Mailbox rehearsals passed (plus one provider timeout that passed on retry); DEMO-02 re-run passed. The pack's captured files were built with the new `scripts/build_usecase_pack.py` (§2.5). Open item: the agent sometimes first tries a `tax_paid_at` claim and is rejected (pre-existing, one wasted call); a prompt hint is deferred to the next prompt revision, because that requires re-running all demos.

**Today:** Casey Demo, `casey.demo@example.com`, Harbor client, "Example Township Tax Office". The email is two sentences, and the tax bill is a generic sheet reading "This is a synthetic bill…". The final letter reads:

```text
Our response to your correspondence follows.
Confirm the supported payment status and timing: Confirm bill receipt and the supported payment schedule. Scheduled payment does not mean disbursement.
Confirm receipt of the supplied tax bill: …
Tax bill received: 2026-09-18T14:30:00Z.
Tax payment status: scheduled.
Scheduled tax payment date: 2026-10-27.
Harbor Demo Servicing: this is synthetic demonstration correspondence. …
```

Note the raw ISO timestamps and the snake_case value leaking into the letter.

**Flow to keep:** the client requires review. The first draft is invalidated when the presenter records the Tax Team result in ILS. The reviewer optionally edits, then approves the current version. The agent sends, indexes, notes and **closes** the case. "Scheduled" must never become "paid".

**To do:**

1. **Persona.** An escrowed borrower, e.g. a first-time homeowner in a New Jersey or Pennsylvania township who received the 4th-quarter bill and wants to know whether escrow will pay it before the due date. Give a realistic email and subject ("Property tax bill – loan ending 0003"). Add address, phone and escrow fields to `loan_context` (keep `tax_*` keys and values consistent across bill, context and task).
2. **Tax bill PDF.** A municipal tax bill from a **fictional** township: bill number, parcel/block/lot (no 10-digit numbers), billing period, installment amount $2,350.00, due date October 30, 2026, remittance stub and a "mortgage company copy" marker. Add a demonstration footer line (government record).
3. **Letter** (`tax_letter`). Confirm the date the bill was received, written as a date (not an ISO instant). Confirm that the installment will be paid from escrow on **October 27, 2026**, before the October 30 due date. State clearly that **it has not been paid yet**, and that the borrower should not pay it separately to avoid a double payment. Say a disbursement confirmation will follow or will appear on the escrow statement. Add a reference block (loan number, tax period, amount, scheduled date, Tax Team review reference) and the Harbor notice.
4. **Review path.** The reviewer's **Edit** must still validate. Rendered-body equality (`unchecked_response_text`) means human edits go through structured claims. Confirm that `workflow.edit` still works with the richer letter and that the edited body matches the validated rendering.
5. **Specialist result.** Update `data/presenter/v1/DEMO-03.json` (reference, dates) to the new persona, and make sure the ILS "Record specialist result" UI shows sensible text.
6. **Tests.** Assert that "has not been paid" (or equivalent) appears, and that "paid" never appears as the status. Assert dates are shown in long form. Assert the unsupported `tax_status=paid` claim is still rejected (an existing test).
7. **Live rehearsal.** The evaluation must still record the stale-draft, edit and approve steps (`workflow_evaluation.py` `review(edit=True)` path). Expect about 3 runs.

## 4. DEMO-05: ambiguous EFT request (two clarification rounds)

**Done (September 24, 2026).** Danielle R. Foster (Northstar) with her annual escrow statement (`render_escrow_analysis`) replacing "Copy of the EFT inquiry"; three natural replies (`EFT_REPLIES` in `mail_templates.py`); the presenter/mail reply is filed as an inbox printout (`render_email_printout`, "Borrower reply – EFT clarification"); `eft_letter` (clarification plus refund / ACH debit / draw requests); `backend/tests/test_demo5_eft.py`; ILS labels; evaluation checks; docs; the pack [`usecases/demo-5-eft-clarification/`](usecases/demo-5-eft-clarification/README.md). Optional item 5 (attached blank form) was not done. **Agent end state:** with the richer letters the model requested an unneeded "Supervisory review" handoff after the authorization request (2 of 3 runs). This is fixed by a server guard in `cct.handoff` (`handoff_not_required` while all remaining work is borrower-pending and contact is permitted) and a prompt line (`phase8-v3`). All five demos were re-run live on the Mailbox path afterwards and passed.

**Today:** Jordan Illustrative, one-line email "Can you change this to an EFT transfer?…". There is a generic "Copy of the EFT inquiry" document, and the letters are "Additional information is required to proceed." plus rule text. The three clarification reply templates are machine-like ("My EFT request concerns an outgoing refund…").

**Flow to keep:** the agent asks what kind of transfer is meant. The borrower replies "refund". The agent asks for the signed refund authorization and verified bank instructions. The case stays **waiting for borrower**. **No funds movement tool exists**; keep it that way.

**To do:**

1. **Persona and story.** Give the ambiguous email a concrete cause, e.g. the borrower received an escrow-surplus refund check after the annual escrow analysis and asks "can you send this by EFT instead?". That makes "refund" the natural answer, while "payment" and "line-of-credit draw" remain plausible readings. Use a Northstar client (already rebranded).
2. **Request copy document.** Decide whether "Copy of the EFT inquiry" is still needed. If kept, render it as the actual email printout or the escrow analysis refund notice (fictional amounts, no 10-digit numbers).
3. **Letters** (`eft_letter`, two variants):
   - **Clarification request:** explain the three possibilities in plain words (a refund sent to you, setting up automatic mortgage payments, or a draw from a line of credit) and ask which one is meant.
   - **Authorization request** (after the "refund" reply): list what is needed. That is a signed and dated electronic refund authorization naming the account holder, plus bank routing and account details verified by a voided check or bank letter. Say how to send them securely, and that **no money will move until they are received and verified**. Also give the text for the "incoming payment" and "line-of-credit draw" branches, which the assessment already distinguishes.
4. **Reply templates.** Rewrite the three `eft-*` replies in `mail_templates.py` as natural borrower emails. Update the `eft_clarification` presenter-input document in `workflow.py` (title "Borrower clarification of EFT intent", generic render) to a realistic rendering of the reply.
5. **Optional:** attach a blank "Electronic Refund Authorization" form to the second letter. That needs a policy change: `required_documents` for DEMO-05 is empty, so today any attachment is rejected as `irrelevant_attachment`. Only do this if the form is added as a library document with its own key.
6. **Tests.** Each intent produces the right request. No letter says money has been or will be sent before authorization. The mailbox reply classification still works for edited replies (`mail_replies.py`).

## 5. DEMO-04: bankruptcy status conflict and credit reporting (specialist handoff)

**Today:** Taylor Fiction, a representative "Demo Legal Representative" at `counsel.demo@example.com`, Harbor client. The documents are "Synthetic court-status record", "Synthetic representation authorization" and "Synthetic bankruptcy specialist determination". The normal flow sends **no** borrower letter; it ends **transferred** after the specialist acknowledges the handoff.

**Flow to keep:** detect the conflict (court record says dismissed without discharge; servicing import says discharged). Keep **representative-only** contact. Reuse the existing Bankruptcy Team task. After the determination, record a current handoff, get the specialist's acknowledgment and verify it. The case status is **transferred**, not closed.

**This is the most sensitive demo.** Bankruptcy and credit-reporting wording has legal weight. Keep claims narrow and never state liability or reporting outcomes that the evidence doesn't establish.

**To do:**

1. **Persona.** A borrower whose Chapter 13 case was **dismissed** (not discharged), represented by a consumer-bankruptcy attorney at a fictional firm. The attorney's email becomes `authorized_recipient`. `representative_name` becomes a real-looking attorney and firm name. Update `test_phase2/3/7`, `workflow_evaluation.py` (line ~333) and `frontend/tests/e2e/phase3.spec.ts`, which assert `counsel.demo@example.com`. The borrower's own email stays blocked by the restriction.
2. **Documents.**
   - **Court record.** A docket-style "Order dismissing case" summary from a **fictional** bankruptcy court and district. Use a case number format such as `26-1XXXX` (no 10-digit numbers) and add a demonstration footer, because it imitates a federal court record.
   - **Representation authorization.** A signed letter on law-firm letterhead with the borrower's signature, naming the attorney and email.
   - **Specialist determination** (follow-up). An internal Bankruptcy Team memo. It is an internal record, not an outgoing attachment.
3. **Representative input.** The `authorized_representative` presenter input in `workflow.py` hard-codes `delegate.demo@example.com` and "Synthetic representative authorization". Make it consistent with the new persona or remove it if no demo uses it (`test_phase7` line ~218 does).
4. **Letter decision.** Decide whether to add an **acknowledgment letter to the attorney**: we received the dispute, it has been referred to our bankruptcy specialists, and we will respond within N business days. Check first whether the assessment supports `referral` or `interim_acknowledgment` at that point: today the initial `referral` candidate is rejected with `unsupported_referral`. If a letter is added, it must go only to the representative, carry the Harbor notice, and make **no** statement about credit-reporting corrections. If not, the rework is just the documents, handoff note text and persona.
5. **Handoff and ILS text.** Make the handoff summary and the specialist acknowledgment read like real internal routing notes. Check the ILS and CCT views and `IlsView.tsx` labels.
6. **Tests.** Contact restriction enforced (nothing sent to the borrower's email). Wrong-recipient drafts rejected. Determination cited only through the allowed evidence. End state is transferred, not closed.

---

## 6. Suggested order and rough effort

| Order | Work | Why | Effort |
|---|---|---|---|
| 1 | §2.1 Harbor rebrand, §2.2 letter helpers | Unblocks DEMO-03 and DEMO-04; stops copy-paste | ½ day |
| 2 | DEMO-03 tax | Same shape as Demo 1 plus the review gate | 1 day |
| 3 | DEMO-05 EFT | Same shape as Demo 2 (two borrower rounds); Northstar already done | 1 day |
| 4 | DEMO-04 bankruptcy | Most documents, most legal sensitivity, a letter decision to make | 1–1½ days |
| 5 | §2.3 observation de-duplication, §2.5 pack builder | Lower cost and faster packs; re-run all five live afterwards | ½ day |

After all five are done, run `scripts/test-mailbox.ps1` (or `python -m app.workflow_evaluation --live --mailbox --scenario all`) once for a full live pass, and refresh `plan/checkpoints/PH-10.md` and `plan/acceptance_results.md` with the new numbers.
