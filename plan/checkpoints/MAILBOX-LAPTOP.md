# Laptop mailbox, draft controls and persistent refresh

The later [editable drafts and image attachment update](MAILBOX-EDITS-IMAGES.md) extends the attachment and draft behavior described here.

## Changes

- Drafts has individual selection, Select all, and an attachment filter. Search and filtering limit the selected rows. Delete and Undo work for selected drafts.
- Removed the direction and delivery status labels from conversation cards. Sender, recipient, timestamp and actual reply controls remain.
- Adjusted Segoe UI sizes, pane widths, line spacing and composer layout for 13-inch laptop displays. Body text is 14 px and conversation headings are 18 px. Send stays visible at common scaled desktop sizes. The theme remains light.
- New mail opens a blank custom email. The five prepared requests are available only in Drafts. There are no template dropdowns in new messages or drafts. Evidence replies open directly; EFT replies expose the functional Payment type choices as radio buttons.
- Browser storage preserves drafts, uploaded PDF references, conversations, folder assignments, flags, read state, the selected folder and the open composer. Refreshing and reopening the page keep the mailbox. An empty Drafts folder stays empty after refresh.
- Only Reset mailbox restores five demo drafts and empty message folders. It preserves server cases and documents. Reset synchronizes across mailbox tabs, and callbacks from an earlier session cannot re-add its conversations.
- The desk, mailbox and browser-test Vite servers now use separate dependency caches. This prevents one server from invalidating another's dynamically loaded PDF module.

## Checks

Desktop browser checks cover draft selection/filter/delete/undo, empty-folder refresh, blank composition, saved custom fields and PDF attachments, pending conversations across refresh, automatic replies, cross-tab reset and retained case history. Layouts are checked at 1280×720, 1366×768 and 1100×650.

All 11 mailbox browser checks passed across the full run and the PDF/EFT rechecks after separating the development caches. Both production builds and code-format checks passed. PDF previews render actual page pixels, including uploaded and delivered files; the EFT reply keeps its payment choice across refresh.

The agent and business workflow are unchanged. Browser automation uses the existing isolated test backend; no presentation cases are created for these checks.

The actual mailbox at `http://127.0.0.1:5176` was also checked in desktop Edge: a prepared PDF rendered real page content, custom draft text survived refresh, Reset restored exactly five drafts, no template dropdowns appeared, and there were no browser errors. Report and screenshots: `.local/mailbox-laptop/running-mailbox.json`, `running-drafts.png`, and `running-new-mail.png`.

See [the mailbox guide](../Mailbox_UI_Guide.md) for the current presenter flow.
