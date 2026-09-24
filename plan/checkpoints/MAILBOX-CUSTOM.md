# Mailbox reset, custom email intake and document previews

The later [laptop mailbox update](MAILBOX-LAPTOP.md) replaces the refresh-reset behavior, template selectors and message status labels described in this historical checkpoint.

Implemented for the desktop mailbox at `http://127.0.0.1:5176` and case dashboard at `http://127.0.0.1:5173`.

## Delivered behavior

- A fresh mailbox load and **Reset mailbox** restore five prepared drafts and empty message folders. Case records, agent runs and delivery artifacts remain saved. Old-session deliveries cannot refill the reset mailbox.
- Favorites removed. Multiple session drafts supported. From, To and Subject have consistent styling without decorative address dropdowns.
- **Custom** allows editable From, Subject and Body. The backend fixes the recipient and validates the envelope. Retries use the same message identity and cannot create duplicate cases.
- The deployed Azure model classifies custom text through a strict tool contract. Exact request quotes and classification usage are retained. The server verifies loan and sender matches against the existing local servicing records.
- Case creation retains the actual email and only imports existing records. No name-change proof, signed request or EFT authorization is generated from an email claim.
- Missing/conflicting loan or sender identity enters the dashboard's intake-review queue. A recorded reviewer decision continues processing automatically. Provider failures stop visibly and offer an explicit retry.
- Prepared and delivered PDFs open in an accessible modal with download and Escape/close controls. Delivered previews use the immutable sent copy. Previewing a draft has no case-creation side effect.
- PDF pages render inside the app with PDF.js, avoiding blank native PDF frames. The browser test checks rendered page pixels and captures the actual document.
- PDF.js 6.3.289 is recorded in the npm lockfile; local setup now requires Node 22.13 or newer.
- The desk and mailbox retain independent addresses without cross-app links.

## Validation

- Backend regression suite passed, including 15 custom-mail tests and the existing 12 mailbox tests. Checks cover classification, independent topic/loan matching, identity review, idempotency, provider failure, envelope validation and immutable PDF retrieval.
- Both production builds passed. Desktop Edge checks cover reset while approval is pending, automatic responses, human approval, same-thread replies, custom composition, intake review and previews. A saved-draft notification that could cover Send was fixed during browser testing.
- Seven live Azure samples passed in an isolated workspace: all five request families, unknown identity, and an embedded instruction attempting to change the delivery recipient.
- Live schedule and embedded-instruction cases completed with one delivery, package and servicing note, plus a readable preview PDF. Name-change and EFT requests waited for missing input; tax waited for review; bankruptcy waited for specialist input; unknown identity stayed in intake review.

Live report: `.local/custom-mail-evaluations/ae9cebe4-b5d3-46a8-9e66-99310cfeec3b/results.json`. Re-run explicitly with `.\.venv\Scripts\python.exe -m app.custom_mail_evaluation --live`.

Screenshots: `.local/mailbox-custom/custom-compose.png` and `.local/mailbox-custom/document-preview.png`.

The original validation used an isolated backend; the presentation server was still an older process and lacked the preview routes. The subsequent PDF attachment update restarted the presentation server and upgraded it to schema `0007`. All 12 cases, 8 runs, 24 existing record tables and 30 retained files were verified unchanged. All five prepared attachments rendered through the actual mailbox address. See [the PDF attachment checkpoint](MAILBOX-PDF.md).

## Current scope

Custom emails use the app's five existing baseline loan records. Unknown loans require review; this change does not add a production loan-system connection. Other/multiple topics need procedure review. Custom messages start new conversations. The subsequent PDF update adds uploads to custom messages, templates and replies. Prepared demo follow-ups cannot supply invented proof or specialist outcomes to custom cases. Existing business approval and evidence requirements still apply.

See [the mailbox guide](../Mailbox_UI_Guide.md) for the presenter flow, examples and reset behavior.
