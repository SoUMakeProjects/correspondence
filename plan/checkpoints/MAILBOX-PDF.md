# Mailbox PDF attachments and conversation layout

The later [laptop mailbox update](MAILBOX-LAPTOP.md) replaces the refresh-reset behavior, template selectors and message status labels described in this historical checkpoint.

## Delivered behavior

- Fixed the live preview failure by replacing the stale backend process, which lacked the attachment endpoints. PDF pages render inside the mailbox popup. Temporary loading failures offer **Try again**.
- Added PDF uploads to custom messages, prepared templates and replies. The composer supports previewing and removing added files, and keeps them when reopening the draft or changing its template.
- Enforced five additional files per message, 5 MB per file, 1–50 pages, and PDF-only content. Invalid files, password-protected PDFs and attempts to reuse an upload in another message are rejected.
- Migration `0007` stores upload metadata, extracted text and hashes. Sending preserves the original bytes and links uploaded evidence to the case. The existing prepared attachments remain included.
- Azure custom classification receives uploaded PDF text. Uploaded content remains unverified correspondence; it cannot supply approved legal or banking facts. Scans can be previewed, but OCR is outside this implementation.
- Conversations show the newest message first, with white cards, sender details, timestamps, collapse controls and available reply actions. The layout follows `outlook-inbox.png` using a light theme.

## Runtime verification

The backend at `127.0.0.1:8000` and mailbox proxy at `127.0.0.1:5176` now report schema `0007`. The database was backed up before restart. Hashes and row counts confirm all 24 existing record tables, 12 cases, 8 runs and 30 document files were preserved. The only new table is `mail_attachments`.

All five prepared attachment previews rendered real page content through the actual mailbox address in desktop Edge, including when the browser requested a dark color scheme. No browser errors occurred. Evidence: `.local/mailbox-update-validation/running-mailbox.json`, `running-mailbox-pdf-preview.png` and `after.json`.

## Checks

Backend checks cover file validation, content integrity, persistence across restart, idempotent sends, duplicate/cross-message binding, custom PDF classification, conflicting loan identities, template/reply evidence linking, scans and migration preservation. Browser checks cover add/remove/preview, saved drafts, custom sending, reply uploads, newest-first cards and preview retry.

The backend regression suite passed after updating the expected migration table list and rerunning that check. All eight desktop mailbox checks passed across the full run and the corrected retry-test rerun. The retry test keeps the simulated service failure active through React's development effect restart. Both production builds, Python lint/format, OpenAPI and generated API type checks passed.

A live Azure request in an isolated database passed all nine checks. Its email body only asked the agent to read the PDF; the actual amortization request and loan identifier were in the uploaded document. The agent classified it correctly, completed in ten steps, sent the schedule to the recognized recipient, and saved one delivery, one package and one servicing note. Both the uploaded and delivered PDFs were verified. Report: `.local/mailbox-update-validation/live-b997a2b3-57f3-49bb-8886-a2800efa0a74/results.json`.

See [the mailbox guide](../Mailbox_UI_Guide.md) for usage and limits.
