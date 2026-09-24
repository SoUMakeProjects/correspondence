# Mailbox reference refresh

Historical checkpoint for the first mailbox refresh. The newer [reset and custom-intake checkpoint](MAILBOX-CUSTOM.md) replaces the Favorites, single persistent draft and Refresh behavior described below.

The standalone mailbox now follows the supplied `outlook.png` reference and is named **Mailbox** in the blue header and browser tab. Its address remains `http://127.0.0.1:5176`.

## Delivered

- Segoe UI typography, Outlook-style blue header, search field, compact Home/View/Help ribbon and command buttons.
- Favorites and folders on the left, dated message previews in the middle, and a reading pane with sender details, conversation messages and attachments on the right.
- New mail split button with the five starting templates, an inline composer, saved draft reopening, Send and Discard.
- Inbox for incoming servicing responses and Sent Items for outgoing requests and replies. Both use actual saved mail and delivery records.
- Search, read/unread, message selection, flags, pins, archive, reversible delete, move, junk, sweep, print and display controls.
- Folder/read/flag/pin choices and the current draft persist in this browser. These presentation controls do not delete server case history and do not synchronize between browsers.
- A dedicated mailbox stylesheet and icon set. The case dashboard remains separate, with no links between the two interfaces.

## Validation

- TypeScript and both production builds passed. The desk's built assets are unchanged by the mailbox styling.
- Four desktop Edge mailbox tests passed: the new folder/draft/search/display workflow and the three existing automatic-delivery, human-review and same-thread reply flows.
- A final focused folder test also passed after refining Undo to preserve later flag/read changes. A separate read-only connection check verified that Refresh reloads templates after a failed request without sending a message.
- The workflow checks use isolated databases and the test provider. They verify automatic case creation, saved system records, exact-version approval and continued processing after replies. No new Azure calls were required for this interface change.
- Read-only visual checks at 1380 × 775 and 1280 × 800 found no browser errors or horizontal overflow. Computed font is Segoe UI and browser title is Mailbox. Screenshots are retained in `.local/mailbox-reference/`.
- Formatting checks passed. Startup and presenter guides use the current New mail and Send labels.

See [Mailbox interface](../Mailbox_UI_Guide.md) for operation and [the demo runbook](../Mailbox_Demo_Runbook.md) for the five scenarios.
