# Mailbox interface

Open **http://127.0.0.1:5176**. Start it with `scripts/start-mailbox.ps1`. The app and browser tab are named **Mailbox**. The desk is separately available at **http://127.0.0.1:5173**. Open both addresses yourself; neither interface links to the other.

The interface uses Segoe UI, a blue header, a compact toolbar, folders, a message list and a reading pane. Typography and spacing fit common 13-inch laptop displays, including 1280×720 and 1366×768. Conversations use white cards on a light background, with the newest message first. Each card shows the sender, recipient and time, without servicing/delivery labels. Available reply actions appear inside the card as well as in the toolbar.

## Fresh start and reset

The first visit in a browser starts an empty mailbox with **five prepared requests in Drafts**. Inbox, Sent Items, Deleted Items, Archive and Junk Email start empty. There is no Favorites section.

**Reset mailbox** asks for confirmation, then restores the same starting state. It clears this mailbox session's messages, drafts, folder assignments, flags, pins and read state. The reset is shared with the Correspondence Desk: it also deletes every case with its runs, drafts, deliveries and documents, and the desk returns to an empty dashboard. **Reset workspace** in the desk account menu does the same and clears this mailbox. Reference catalogs are kept.

**Refreshing or reopening the page preserves the mailbox.** Draft text, uploaded attachments, sent conversations, selected folder, read state, flags and folder assignments are saved in this browser. Automatic processing continues on the server; reopening the mailbox picks up later replies. Only **Reset mailbox** starts over. Reset also updates other mailbox tabs in the same browser. Use the case dashboard to inspect earlier work after a reset.

## Send a prepared request

1. Open **Drafts** and choose the relevant prepared request. The five demo templates are available only here. No template dropdown is shown.
2. Edit From, Subject and body as needed; To stays fixed. Use **Add attachment** for PDFs or images, and the **?** beside any attachment to remove it.
3. Click **Send**. The request moves to **Sent Items** and starts the agent automatically.
4. Switch to the desk tab. Open the new case on the dashboard.
5. Responses arrive in **Inbox** automatically.
6. For a prepared demo with an available follow-up, select its conversation and click **Reply**. The relevant evidence reply opens directly. For EFT clarification, choose the **Payment type** using the visible radio buttons, then send to continue the same case.

All drafts, including prepared requests and follow-up replies, are editable. The compact Drafts list shows subject, sender, time and an attachment indicator; the body appears only after you open the draft.

Closing the composer saves its draft. Multiple drafts are supported. **Discard** removes the open draft. A sent draft is removed from Drafts. Only **Reset mailbox** restores the five initial drafts.

Drafts has individual checkboxes, **Select all drafts**, and **Filter drafts → With attachments**. Selection applies to the visible search/filter results. **Delete** removes selected drafts; **Undo** restores them. Removing every draft and then refreshing leaves Drafts empty until you reset or write a new message.

### Editing prepared demos

Sending a prepared initial draft unchanged keeps its repeatable five-demo flow. If you change its sender, subject, body or remove a prepared attachment, Azure classifies the submitted message through the same intake used by New mail. The case keeps the actual email and selected files. The original scenario does not override your changes. These cases use their actual receipt time and do not offer prepared demo follow-ups.

Replies in unchanged demo conversations remain editable. The agent uses the submitted reply text and only the attached documents. A changed EFT reply is classified from its text. A sender mismatch, different loan or changed request pauses continuation for review instead of applying the original reply automatically.

## Send a custom request

Choose **New mail** to open a blank email immediately. Enter any valid From address, a subject and a body. To remains fixed at **correspondence@servicing.example.com**. New requests start new conversations. There is no template selector.

The Azure agent reads the actual subject, body and uploaded PDF text and classifies the request. It matches an explicit loan identifier against the app's servicing records, or uses a unique recognized sender when no loan identifier is supplied. It creates a case using that loan's records and the submitted email, then continues through the existing business checks and tools.

| Loan | Recognized sender | Useful request |
| --- | --- | --- |
| 0099000001 | lauren.whitaker@outlook.com | Name change |
| 0099000002 | marcus.j.delgado@outlook.com | Amortization schedule |
| 0099000003 | priya.raman@outlook.com | Tax inquiry |
| 0099000004 | monica.ferrante@ferrantehale.example.com (borrower's attorney) | Bankruptcy / credit reporting dispute |
| 0099000005 | danielle.foster@outlook.com | EFT clarification |

These are the current local servicing records. The topic does not choose the loan: a name-change request for loan 0092000000, for example, cannot silently become the prepared name-change loan.

Example: From **marcus.j.delgado@outlook.com**, subject **My mortgage schedule**, body **Please email the amortization schedule for loan 0099000002. Thank you.** The agent can retrieve the available schedule, send it, save the package and note, and close the case automatically.

An unknown loan, multiple conflicting loan identifiers or an unrecognized sender pauses intake. The case dashboard shows **Incoming requests needing review**. A reviewer can verify the intended loan and sender authority, record a note and choose **Confirm and continue**. The agent then resumes automatically. Replies still use the recipient held in servicing records. A provider failure offers **Retry classification**.

Unsupported or multiple topics require case review. Missing name-change evidence and ambiguous EFT instructions remain pending. Mentioning an attachment in the body does not create evidence. Custom intake uses existing local loan/document records; it does not access a new external ILS service. Prepared demo proof and specialist results cannot be used to fabricate evidence for a custom request.

## Add attachments

**Add attachment** is available in custom messages, prepared templates and follow-up replies. Choose up to **five additional PDFs**, each **5 MB or smaller** and **1–50 pages**. Other file types, damaged PDFs and password-protected PDFs are rejected. The server checks the file contents as well as the filename.

Click any attachment to preview it before sending. Use its **? / Remove** control to remove it, including prepared attachments. Closing, refreshing and reopening a draft keeps its edits, added files and removals. Removed files are excluded from the sent email and do not become new case evidence. Existing independent OnBase records are still available to the agent.

Sending retains the original file with the message and adds it to the linked case's document records. The agent can read up to 12,000 extracted text characters per PDF. Images and scanned PDFs can be uploaded and previewed, but image interpretation and OCR are not included. Their contents remain available for human review; the classifier receives image metadata and any extractable PDF text. Uploaded claims, signatures and authorizations still need the applicable business verification; uploading a file does not automatically approve a legal or banking change. Conflicting loan identifiers in a custom message or its PDFs require identity review.

## Document previews

Click an attachment in a draft or conversation to open its popup preview. Use **Download** to save it, **Close** to return to mail, or press **Escape**. Prepared and delivered PDFs open from their actual files. A delivered document uses the retained copy from the send, even if the current case evidence later changes. Previewing a draft does not create a case or invoke the agent.

PDF pages render inside the popup. Images fit the same light preview window, and Download preserves the original format. A temporary loading failure shows **Try again**, so you can retry without closing the preview.

## Other mail controls

- **Search** filters the current folder by subject, sender, recipient or body.
- **Inbox** counts unread responses; **Sent Items** contains submitted requests and replies.
- **Archive**, **Delete**, **Report → Mark as junk**, **Move to**, and **Undo** organize mail for this session.
- **Sweep** archives messages from the selected sender in the current folder.
- **Read / Unread**, filtering, **Flag** and **Pin** work on selected messages.
- **View** and **Settings** control the folder pane and spacing. Spacing remains a browser preference.
- Notifications show unread responses. Message headers collapse or expand the conversation. **Print conversation** opens the browser print dialog.
- Dates use US Eastern time. The five prepared scenarios retain their fixed business clock; custom requests use their actual receipt time and weekday rules.

See [the demo runbook](Mailbox_Demo_Runbook.md) for the five prepared scenarios.
