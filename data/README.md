# Synthetic fixtures and curated knowledge

Version 1 supplies Phase 2 evidence for the five planned cases. Every borrower name, loan/CCID, contact, amount, date, document, and specialist result is invented. All email addresses use `example.com`, `outlook.com` or the fictional servicer domains. The original Office files under `docs/` are reference material and are never served as case attachments.

## Starting scenarios

| Scenario | Initial evidence | Additional starting variants |
| --- | --- | --- |
| DEMO-01 | Lauren E. Whitaker's Northstar loan: her signed and dated letter asking to change her name to Lauren E. Castellano after marriage; the legal document is missing and no update is recorded. See the [use-case pack](../usecases/demo-2-name-change/README.md) | `followup`: certified copy of her marriage record and a completed name-update result supplied |
| DEMO-02 | Marcus J. Delgado's Northstar 30-year fixed loan: an 8-page amortization schedule with the remaining 283 installments, reconciled to the note terms to the cent. See the [use-case pack](../usecases/demo-1-amortization/README.md) | `missing_document`, `unreadable_document`, `wrong_loan` |
| DEMO-03 | Priya S. Raman's Harbor Point escrowed loan: her Wrenfield Township 2026 fourth-quarter real estate tax bill ($2,350.00, due October 30, 2026), reconciled with the servicing tax line; payment scheduled from escrow for October 27; existing pending Tax Team task; no disbursement. See the [use-case pack](../usecases/demo-3-tax-inquiry/README.md) | `followup`: the Tax Team result `TAX-REV-260922-003` reconfirms the schedule; payment remains unpaid |
| DEMO-04 | Dismissal document conflicts with an unverified discharge marker; representative restriction and pending specialist task | `followup`: supplied specialist determination reconciles the status; communication restriction remains |
| DEMO-05 | Danielle R. Foster's Northstar 15-year fixed loan: “Can you change this to an EFT instead?” with her annual escrow statement attached ($486.27 surplus refund by check; new $1,562.96 payment from November 1); purpose not established. See the [use-case pack](../usecases/demo-5-eft-clarification/README.md) | `followup`: her reply asking for the refund by direct deposit (outgoing refund); signed refund authorization and bank proof still absent |

All variants start at a fixed evaluation clock of **22 September 2026, noon America/New_York**. Original receipt timestamps retain their instants in UTC. Client configuration is copied into each instance's servicing evidence: Northstar Residential Servicing (`DEMO-NORTH`) uses an automatic-demo preference, Harbor Point Mortgage Services (`DEMO-HARBOR`, client version 2, notice `harbor-servicing-notice`) uses a review-required preference. The runtime enforces those rules and binds review to current response/evidence versions.

`fixtures/v1/` contains initial case inputs and the two fictional client configurations. `presenter/v1/` contains prepared follow-up facts. Initial loads never merge those follow-ups. Choosing `followup` creates a fresh instance with supplied starting evidence; it does not execute a servicing action or resume the original instance.

Expected dispositions and assessment criteria are stored separately in [the evaluation file](../backend/tests/expectations/v1/scenario_outcomes.json). Application imports, public evidence, knowledge searches, and document generation do not read this file. Fixtures supply evidence; live workflow/recovery evaluations demonstrate the selected business outcomes separately.

## Documents

[The document manifest](documents/v1/manifest.json) contains **18 references** across 12 starting-state combinations: 15 readable PDFs, 1 deliberately truncated PDF, and 2 missing references. Readable files include identity metadata. Most print synthetic labels. The DEMO-02 schedule and the DEMO-01 signed request are formatted as real-world documents and carry their synthetic provenance in the PDF keywords metadata instead. The DEMO-01 marriage record also carries the metadata marker and prints a single footer line stating that it is a demonstration record and not an official document. The wrong-loan PDF declares loan `0099000099` and a different borrower (Patricia L. Owens) so validation exercises can detect the mismatch. It is available for inspection and is not a valid attachment for the selected case.

Generated PDFs are versioned under `documents/v1/`. Loading a scenario copies only its selected documents into the local application store with unique evidence IDs and recorded SHA-256 hashes. Download routes validate the case/evidence relationship, storage boundary, hash, and PDF readability. A failed seed transaction rolls back its records and removes only the files it created.

## Source reconciliation and curation

| Artifact | Contents |
| --- | --- |
| [Taxonomy](knowledge/taxonomy.v1.json) | 149 original Work Type/Class/Sub Class combinations; 144 distinct subclass labels. Parent identities are retained; demo families are separate. |
| [Source manifest](knowledge/source_manifest.v1.json) | Physical rows 2–528 of `Extracted Data`, with category, disposition, review flags, and derived-item references. No raw subcategory/body text or credential values. |
| [Reconciliation report](knowledge/reconciliation.v1.json) | All 527 entries across 16 categories; source-file hashes, counts, and repeated-label/body groups. The Summary sheet's 525 is retained as historical metadata, not the true row count. |
| [Curated content](knowledge/curated.v1.json) | 16 scoped demo items: guidance, response templates, and fictional disclosures (including the Northstar borrower notice used by client configuration v2). Each records provenance, version, applicability, prerequisites, placeholders, owner, and limitations. |
| [Source registry](knowledge/source_registry.v1.json) | Original file/sample paths and interpretation references. Source PDFs referenced by the historical samples were not supplied. |

The manifest classifies **5 rows as curated, 10 as excluded, and 512 as requiring review**. Row 474 is excluded before text classification because it contains credentials; rows 475–483 contain production sender/contact configuration and are also excluded. The 14 repeated category/subcategory groups remain identifiable without copying their raw labels into runtime content. Short fragments, known heading/body conflicts, merged topics, and repeated bodies are marked for review.

Seventeen curated items do not mean seventeen fully approved source rows. Some items derive from samples or explicit BRD corrections, and a limited reconstructed principle may reference a row whose remaining text still requires review. In particular, tax row 292 and EFT row 229 are not imported wholesale. No production bankruptcy disclosure or company contact instructions are approved here. Both client disclosures are explicitly authored for the synthetic demo.

Only `curated_demo` knowledge items matching the requested scenario/client are searchable. Manifest rows and unresolved text are never draft sources. Changing a runtime knowledge item's status to `requires_review` immediately removes it from retrieval; startup does not overwrite that decision. Phase 3 enforces evidence prerequisites and validates structured response candidates. The desktop response editor and Azure agent use the same validation services.

Business rules are configured in [policies/phase3.v1.json](policies/phase3.v1.json). This file records procedure inputs, required documents and supported taxonomy references, separately from the evaluation-only expected outcomes. Current assessments are computed from each instance's persisted facts and actual files; recording an assessment preserves those inputs and the policy version. Existing Phase 2 instances can be assessed without reseeding them.

## Load and maintain

From the workspace root:

```powershell
# Reuse the initial five-instance set, creating it if absent.
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\seed-demo.ps1

# Create another set without deleting earlier records.
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\seed-demo.ps1 -Fresh

# Inspect one deliberate exception or a prepared follow-up.
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\seed-demo.ps1 -Scenario DEMO-02 -Variant wrong_loan -Fresh
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\seed-demo.ps1 -Scenario DEMO-01 -Variant followup -Fresh

# Explicit offline rebuild after reviewed source/fixture edits.
.\.venv\Scripts\python.exe -m app.cli rebuild-data
.\.venv\Scripts\python.exe -m app.cli check-data
```

Normal startup uses the sanitized artifacts and does not read Office source contents. Rebuild reads the two explicit workbook paths; it exports metadata and reviewed rewrites, never a raw-response dump or credential quarantine. Keep immutable versions once used for a demo baseline. A changed fixture with a reused seed request ID is rejected; create a fresh instance. Existing instances retain their own evidence copies and client snapshots. Reference installation adds missing versioned records and preserves existing decisions. A client fixture with a higher version (Northstar is now v2) replaces the stored configuration; earlier cases keep their v1 snapshot and report a configuration refresh; changing curated content requires a new version and corresponding versioned-contract migration, not silently overwriting an approved item.

Fixture generation and loading make no model calls. Starting an agent or an explicit live evaluation calls Azure; all messages and servicing changes remain local simulations with synthetic data.
