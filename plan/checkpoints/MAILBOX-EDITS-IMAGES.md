# Editable drafts and PDF/image attachments

## What changed

- Every prepared request, reply and custom draft allows editing From, Subject and Body. To stays fixed. Edits and attachment removals survive refresh.
- Draft rows use compact spacing and show no message body. Open a draft to read or edit it.
- Every composer attachment has a visible Remove icon, including prepared files.
- Uploads accept PDF, PNG, JPEG, GIF and WebP. The server verifies the actual bytes. The existing size/count limits still apply, without the static limit sentence in the composer.
- The same light preview popup displays PDFs and images. Downloads keep the original format.
- Edited initial drafts use Azure classification of the actual email and selected attachments. Unchanged drafts preserve the five prepared demo flows. Edited requests do not expose prepared follow-ups; see the mailbox guide.
- Edited replies preserve the actual text. Changed EFT wording is classified before applying its intent. Sender, loan and request mismatches pause processing. Removed prepared proof is not silently imported.
- Image uploads remain unverified case evidence. There is no image interpretation or OCR. Extractable PDF text is available to intake.
- Migration 0008 adds the attachment media type and preserves older PDF uploads.

## Validation

- Backend regression suite, including upload validity, immutable previews, field validation, edited intake, reply removal, EFT meaning, and migration preservation.
- Mailbox browser coverage includes all five editable drafts, compact lists, edits/removals across refresh and send, image preview/removal/download, and existing PDF, reset, filtering, reply and approval flows. Thirteen browser cases passed across the suite and the image test recheck. The initial image test used a malformed test fixture; replacing it with a generated valid PNG resolved the failure.
- Production frontend build and API type generation pass.
- Live Azure edited-draft check completed classification and agent processing, sent the correct schedule, saved one delivery/package/note, retained the uploaded image and excluded removed prepared files. Evidence: `.local/mailbox-edit-validation/live-0500605e-5bea-4746-844a-e7df8f96f6da/results.json`.
- Runtime database backup and comparison confirm that 13 existing cases, 9 runs, and 33 files survived the update unchanged. Evidence: `.local/mailbox-edit-validation/before.json` and `after.json`.
- The running mailbox on port 5176 renders its PDFs and preserves drafts across refresh without browser errors. Screenshots are saved under `.local/mailbox-edit-validation/screenshots/`.
