# Case workspace UI refresh

The user supplied `aaa.png` as the visual reference and requested a detailed case page plus a separate sender-mailbox webpage. This update keeps app version `0.9.0` and schema `0006`.

## Delivered interface

- Full-width Case dashboard with no navigation sidebar, a compact header, live case search, status cards and filters. Click a row to enter the case; the breadcrumb returns to the dashboard.
- Direct case addresses at `/cases/{id}` with a case summary, original receipt, Eastern workday age, routing and restrictions.
- Three-column case layout: correspondence/context, recorded agent activity, and the current response with versioned review controls.
- Expandable evidence, real saved receipt references, links to system workspaces, and read-only replay of recorded steps.
- Current-version approval, evidence-validated editing, return with feedback, and automatic continuation through the existing APIs.
- Case tabs for loan/client facts, concerns, routing/aging, and CCT, ILS, OnBase, secure mail and recovery.
- Independent mailbox at `http://127.0.0.1:5176`, with its own entry, frontend server, startup script and build. Neither interface links to the other. The desk has no sender/mailbox route. Original threads and automatic triggers are retained.

The UI uses the actual case data and existing validation results. Wireframe sample names, payoff amounts and simulated-environment labels were not inserted into the app. Source documents, original records, credentials, business rules and Azure model integration were retained.

## Earlier validation

These checks were recorded for the first wireframe refresh. The dashboard and independent mailbox follow-up is recorded in [UI-DASHBOARD](UI-DASHBOARD.md).

- TypeScript and production build passed.
- All 13 desktop Edge tests passed, including original review and restart/recovery tests.
- Updated mailbox coverage verifies separate sender-to-case navigation, worklist search/direct links/reload, automatic delivery, saved system records, replay without new runs, validated editing, exact-version approval and same-thread evidence resumption.
- The additional focused review check passed: Return → new draft → validated edit → exact-version approval, with automatic continuation and one final delivery. Result: `.local/desk-review-check.log`.
- Read-only visual checks used the normal workspace's 10 existing cases and 5 runs, with no browser errors. Screenshots at 1536 × 1024 are retained in `.local/desk-visual/`.
- Browser automation used isolated databases and the explicit test-only provider. This UI refresh did not require new Azure model calls; the five-family live Azure evidence remains in PH-10.

Integrated browser log: `.local/desk-browser-checks.log`. Presenter instructions: [Case workspace guide](../Case_Workspace_Guide.md) and [Mailbox demo runbook](../Mailbox_Demo_Runbook.md).

The earlier PH-05/business-acceptance gaps remain unchanged. The existing Phase 9 runtime archive predates both the mailbox and this UI refresh; the packaging allowlist now includes the new guide for future builds.
