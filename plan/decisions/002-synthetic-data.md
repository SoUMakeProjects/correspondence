# Phase 2: Synthetic inputs and curated references

Date: 22 September 2026. Status: adopted for the authorized Phase 2 implementation.

| Decision | Implementation |
| --- | --- |
| Scope | Implement the five planned scenario inputs, deliberate evidence variants, reference catalogs, scoped inspection/retrieval, and seed commands. PH-03 and later workflows remain separate. |
| Data separation | Initial fixtures, presenter follow-ups, and evaluation expectations have separate directories. Initial case loading does not load future specialist results. Expected dispositions remain under backend tests and are never read by runtime services. |
| Client configuration | Two fictional clients use reserved `example.com` addresses, explicit synthetic disclosures, and distinct future review preferences. Each instance retains its client snapshot. No production signature/contact credentials are imported. |
| Knowledge import | Reconcile every physical workbook row into metadata. Exclude row 474 before text classification, exclude production sender/contact rows, and retain review flags without exporting raw response/subcategory content. Curated snippets are separately reviewed rewrites, with any partially used row's unresolved remainder still held for review. |
| Content status | `curated_demo` means usable for the synthetic MVP; it does not mean approved company policy. Missing legal disclosures, operational task mappings, and unsupported conclusions remain explicit limitations. Existing runtime review decisions survive catalog installation. |
| Reference identity | Retain all 149 original Work Type/Class/Sub Class triples. Do not collapse by subclass label or use family tags as operational taxonomy. |
| Retrieval | Structured SQLite records and scenario/client/kind/text filters are sufficient for 15 items. No vector database or model inference is required. |
| Documents | ReportLab generates labeled PDFs; pypdf validates readable content and metadata; PyMuPDF supports visual verification. Amount generation uses Decimal and integer minor units. Runtime files have unique IDs and recorded hashes. |
| Seed/reload | Stable request IDs reuse a prior load; a changed payload with the same ID is rejected. Fresh loads create isolated records/files and preserve prior history. Follow-up variants are supplied starting states, not claims that an agent executed an action. |
| Migration | Schema `0002` adds reference catalogs, evidence facts and seed identity. A populated Phase 1 database is preserved by the migration test. |
| Source preservation | Original documents and samples remain unchanged under `docs/`. Source-file hashes were compared before/after implementation. Root `.env` remains user-controlled. |

See [Phase 2 evidence](../checkpoints/PH-02.md) and [data maintenance](../../data/README.md).
