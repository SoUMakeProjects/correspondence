# Case dashboard and independent mailbox

## Requested behavior

The app opens at a case dashboard. Clicking a case opens its detailed workspace. The app has no sidebar. The mailbox uses a separate address, with no links between the two interfaces.

## Delivered

- Desk: `http://127.0.0.1:5173/`. Full-width dashboard with status cards, search, filters and clickable rows. Case-number links also work with the keyboard and can open in a new tab.
- Case details: `/cases/{id}`. The breadcrumb returns to the dashboard. Direct addresses, refresh and browser back work. Correspondence, agent activity, reviews and system records remain available inside each case.
- Mailbox: `http://127.0.0.1:5176/`. Independent HTML entry, Vite server and build; start it with `scripts/start-mailbox.ps1`. Both frontends use the existing backend.
- Removed the desk sidebar, presenter links, sender route, case-to-mailbox links and mailbox-to-case links. Open the two addresses manually in separate tabs.
- `npm.cmd --prefix frontend run build` builds the desk into `frontend/dist` and the mailbox into `frontend/dist-mailbox`. Startup guides and the runtime packaging allowlist include the new entry and script.
- Sending a predefined email still starts processing on the server. Cases and status changes appear automatically on the open dashboard. Replies, specialist results and approval continue processing through the existing APIs.

## Validation

- TypeScript and both production builds passed.
- All 13 desktop Edge tests passed, including the existing review and restart/recovery coverage (3.8 minutes).
- Desktop browser checks cover mail sent from the separate origin appearing on an already-open dashboard, row and keyboard navigation, search, filters, browser back, direct case links and refresh. They also check that neither interface links to the other and that the removed sender route no longer opens a mailbox.
- Mailbox regression checks passed for automatic delivery and shared system records, read-only replay, return/edit/current-version approval, and same-thread evidence invalidating an earlier draft.
- Read-only visual checks at 1536 × 1024 and 1280 × 900 found no browser errors or horizontal overflow. The inspected workspace had 11 existing cases and 7 runs; no mail or case changes were made by this visual check. Screenshots are in `.local/desk-visual/`.
- Browser workflow checks use isolated databases and the explicit test provider. No new Azure calls were needed for this UI change. Earlier five-demo live Azure evidence remains in PH-10.

App version, backend schema, business rules, credentials and existing case history are unchanged. The earlier business acceptance gaps still apply.
