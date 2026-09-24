# Remaining work and policy decisions

Release baseline: `0.9.0`. This register preserves unfinished scope; it does not change the BRD's required/partial/deferred classifications.

| Priority | Work | Completion evidence needed |
| --- | --- | --- |
| 1 | Finish PH-05 standalone manual prepare/execute workflow. Result viewers and the reviewer editor are present; agent-led execution is implemented. | Presenter completes DEMO-02 using only the supported manual preparation/execution controls. |
| 1 | AC-04: manual correction of a wrong classification with history and multiple concerns. | A current authorized correction changes the full parent-qualified taxonomy identity, preserves both concerns, invalidates affected drafts and records who changed it. |
| 1 | AC-03: complete manager reassignment for Chat/Call/Credit Reporting. Rules detect the manager route; general owner edits are not a dedicated manager handoff. | End-to-end manager receipt/assignment and history across the named channels, preserving original receipt. |
| 1 | AC-16: school-tax/TAR and estimate-update variants. Current live fixture covers town-tax receipt and scheduled-versus-paid review. | Authoritative scenario facts, distinct TAR/estimate/schedule claims, and validated responses for school and town branches. |
| 1 | AC-45: correction of invalid aging inputs. Intake rejects malformed timestamps and rules retain an exception; no general correction UI exists. | Authorized input correction produces a recorded recalculation without fallback dates or resetting the receipt anchor. |
| 2 | Resolve operational taxonomy gaps for name-change and bankruptcy cases. | Business-approved mappings; until then retain the visible supervisory handoff instead of inventing a classification. |
| 2 | Curate additional source content beyond the 15 selected items. | Owners review incomplete/conflicting source material; exclusions and provenance remain explicit. All 527 source rows are accounted for, not all approved. |
| 2 | Polish response presentation. Current validated output is readable but repeats some concern labels and uses raw ISO timestamps in places. | Improve phrasing/date formatting while retaining cited facts, disclosures, version checks and concern coverage. |
| 2 | Extend the three partial and 19 deferred BRD scenarios only with their own evidence and policies. | Dedicated fixtures and acceptance results; generic handoff is not substantive completion. |
| 3 | Mobile support and SSE transport if requested. | Mobile UX verification and durable event-cursor reconnect tests. Current desktop uses persisted API polling. |
| Separate scope | Real company integrations, production roles/authentication, secure operations, deployment, backup/retention, operational monitoring and broader scale. | Agreed architecture, policy ownership and integration acceptance. Current presenter identities are synthetic labels, not authenticated roles. |

Open source-policy decisions include client sender/disclosure/contact configurations, specialist precedence and task eligibility in uncurated topics, commercial versus consumer credit capability, definitive bankruptcy/legal language, and production records/indexing/retention rules. Current client values and disclosures are fictional demo settings. No production signoff is inferred from an engineering checkpoint.

The release handover may be complete while the original broader MVP definition still has unchecked items. Required acceptance items with incomplete behavior remain **partial**, not passed or silently deferred. Subsequent work should close the priority-1 gaps before claiming all originally required workflows are implemented.
