# Correspondence Desk: UI improvement suggestions

**Scope:** the Correspondence Desk at `:5173`: login, case dashboard, case workspace and its tabs.
**Out of scope:** the Mailbox at `:5176`. None of these suggestions change it (see [Mailbox guardrails](#mailbox-guardrails)).
**Target hardware:** 13-inch laptops, used for daily work and for live demos.

## How this review was done

- I read all Desk source files: `src/desk/*`, `src/auth/*`, `desk.css`, `login.css`, `operations.css`, and the shared components the Desk reuses (`SystemViews`, `CaseAssessment`, `AgentWorkspace`, `CaseWorkflow`, `styles.css`).
- I ran the backend, using the browser-test fake agent and a temporary database, and the Desk frontend. I sent the 5 prepared demo emails plus 1 unknown-sender email, which gave realistic data: 4 cases needing review and 1 intake review.
- I took screenshots of every screen, tab, dialog and the search dropdown at two usable viewport sizes:
  - **1280 × 640**: a Windows 13" laptop at 1920×1080 with the default 150% scaling, after the browser toolbar and taskbar.
  - **1440 × 790**: a MacBook Air 13" at its default resolution, after the browser toolbar and menu bar.
- No application files were changed. The only additions are this document and `frontend/node_modules`, which was installed to run the app.

> **Design target.** Treat **1280 × 620** as the size that *must* work, and 1440 × 800 as the size that *should look great*. Presenters often zoom the browser to 110–125% so a room can read it, which makes the usable area even smaller.

---

## Summary: the 5 changes that matter most for a demo

| # | Problem seen on a 13" screen | Fix |
|---|---|---|
| 1 | **Approve and send** is off-screen when a case opens: y≈957px at 1280×640 and y≈998px at 1440×790. The presenter has to scroll the whole page, and the Agent activity panel also scrolls on its own inside it. | Make the case workspace fill the viewport height. Each column scrolls on its own, and the review actions stay fixed at the bottom of the Response panel. |
| 2 | The header area above the columns (topbar, breadcrumb, case header, tabs) takes about 260px, roughly 40% of a 640px screen. | Shrink the topbar to about 52px and merge the breadcrumb, case header and tabs into about 100px. |
| 3 | The text size drops as the screen gets smaller. Under the `@media (max-width: 1330px)` rule, which applies to every 13" laptop, the action buttons shrink to 10px. The stylesheet also has 62 declarations of 8–11px text. | Set a minimum of 12px for metadata and 13–14px for body text. Change the 1330px breakpoint to rearrange the layout instead of shrinking text. |
| 4 | The response letter is a large, saturated green chat bubble (`--bubble-out: #d9fdd3`). It is the biggest thing on the screen and looks like a messaging app rather than regulated borrower correspondence. | Show the draft as a white letter on paper and keep green for accents. The borrower message can stay a light chat bubble. |
| 5 | On the dashboard at 1280×640, only **2 case rows** are visible above the fold. When an intake review is waiting, **none** are visible. | Compact the page heading, combine the stat tiles and filter tabs, make table rows shorter, and show intake reviews as a slim alert strip. |

Also fix this quick bug: **the search icon in the top bar never appears.** In `desk.css`, `.desk-global-search > svg` and `> input` both use `z-index: 2`, and the input comes later in the HTML, so it covers the icon. Setting `z-index: 3; pointer-events: none` on the svg fixes it.

---

## 1. Case workspace: make it fit one screen (P0)

### What happens now (1280 × 640)

```
┌ topbar 68px ────────────────────────────────────────────────────────┐
│ breadcrumb + Follow agent                         ~31px             │
│ DEMO-CC-002 [Under review]      Received | Age | Routing | Restr.   │ ~80px
│ tabs                                               ~46px + 22 gap   │
├──────────────┬────────────────────────┬─────────────────────────────┤  ← content starts at y≈260
│ Correspond.  │ Agent activity         │ Response draft (green)      │
│              │  step 1 (140px min)    │                             │
│              │  step 2                │                             │  ← fold (640)
│ Case context │  (own scroll, 550px)   │  coverage / attachments     │
│              │                        │  [Approve and send] y≈957   │
└──────────────┴────────────────────────┴─────────────────────────────┘
```

### What to do instead

```
┌ topbar 52px: brand · search · agent status · avatar ▾ ──────────────┐
│ ← DEMO-CC-002 [Under review]  Riley Example · Loan …02 · Northstar   │ ~56px
│   Age 2/20 ▰▱▱  ·  Route Inquiry  ·  No restrictions   [tabs…]       │ ~40px
├──────────────┬────────────────────────┬─────────────────────────────┤  ← content starts at y≈150
│ Correspond.  │ Agent activity [Follow]│ Response draft  v1 ▾  ●      │
│  (scrolls)   │  (scrolls)             │  letter (scrolls)           │
│              │                        │                             │
│              │                        ├─────────────────────────────┤
│              │                        │ [Approve and send] Edit Ret.│  ← always visible
└──────────────┴────────────────────────┴─────────────────────────────┘
```

**Implementation notes**

- `.desk-case` should become a flex column with `height: calc(100dvh - var(--topbar-h))` when the Case workspace tab is open. `.case-workspace-grid` then gets `flex: 1; min-height: 0`, and each column gets `overflow: auto`.
- In `.response-card`, make the card a flex column. The letter area is `flex: 1; overflow: auto`, and `.response-review-controls` stays at the bottom, either by being the last flex item or with `position: sticky; bottom: 0` plus a top border and shadow.
- Remove `.activity-scroll { max-height: max(550px, calc(100vh - 327px)) }`. With a 640px viewport it resolves to 550px, which gives two nested scroll areas. Let the column scroll area handle scrolling.
- Keep the other tabs (Loan & client, Concerns and so on) as normal scrolling pages.
- **Fallback below about 1180px wide, or when zoomed:** switch to 2 columns. Correspondence and Activity share the left column as sub-tabs, and the Response panel stays on the right. The current 3-column grid only gets narrower and never rearranges, so at 125% zoom each column is about 280px wide and cramped.

### Compress the header (`CaseDetail.tsx`, `desk.css`)

- **Merge the breadcrumb into the title row.** Put a `←` back button before the CCID and remove the separate `.case-breadcrumb` row. This saves about 31px.
- **Move Follow agent** into the Agent activity card header, next to Replay, where it applies.
- **Replace the 4-column facts block** (`.case-header-facts`, 48% width, 10–11px text) with one line of chips: `Age 2 of 20 ▰▱▱ · Route: Inquiry · Restrictions: None`.
- **Hide duplicate text.** Routing currently shows "Inquiry / Inquiry": `route` and `assessment` are both "Inquiry". Hide the second line when it matches the first.
- **Label the two receipt dates clearly.** The header shows *Received Sep 18, 10:30 AM* (original receipt), but the correspondence card shows *Received Sep 23, 12:02 PM* (email timestamp). During a demo this looks like a bug. Label them "Original receipt" and "Email received", or only show the second one when it differs.
- Put the tabs on the same row as the facts, or directly below at about 40px high. Reduce `margin-bottom: 22px` to about 12px.

---

## 2. Agent activity timeline: more steps per screen (P0/P1)

This timeline is the main thing people watch in the demo, but only about 2.5 steps fit on screen.

- **Shrink each step.** `.desk-timeline > li` has `min-height: 140px` and about 39px of vertical padding. Aim for 64–80px per completed step, with the title and system on one line and the result underneath.
- **Remove the receipt column** (`.action-receipt`, 78px wide, with **8px** labels and a striped background). Show it instead as an inline chip after the title, such as `✓ Confirmed · CB60F280`, at 11–12px. Clicking it still opens the system. This gives the step content about 90px more width.
- **Show each timestamp once.** It currently appears in both the title and the receipt. All demo steps are also stamped `12:02:46 PM`, so drop the seconds and show the time only when it changes from the previous step.
- **Hide generic result text.** "Operation completed." adds little. Show the result line only when it says something specific; the full text is still available under the details toggle.
- **Pin the outcome at the top.** The most important information ("Awaiting human review. Next: review the current draft…") is at the bottom of the scroll and hidden when the case opens. Show a one-line status banner at the top of the activity card, and ideally repeat it as a "Next step" chip in the case header.
- **Make the live state obvious**, since this is the most impressive moment in the demo:
  - pulse the current step's dot (motion is already disabled when reduced motion is on);
  - show "Agent working · step 3 of ~6" in the card header;
  - briefly highlight a new step when it arrives.
  Today the running step is only a pale green background with a small dotted spinner.
- The step footer ("Activity is linked to saved system records.") is 9px. Either remove it or raise it to 12px.

---

## 3. Response panel: read like a letter, act like a review tool (P0/P1)

- **Use a white paper letter instead of the green bubble.** Replace `.response-paper { background: var(--bubble-out) }` with a white surface, a thin border, a soft shadow and a slightly larger body size (13–14px). If you want to keep the "outgoing message" idea, use a 3px accent bar on the left instead of filling the whole panel. The large green block is visually loud and makes the draft harder to read, especially on a projector.
- **Raise the letter's text sizes.** The letterhead, date, recipient and signature (`.letter-mark`, `time`, `.letter-recipient`, `footer`) are all 10px. Make them 12px, and the body 13–14px.
- **Tidy the panel header.** The title, version dropdown and 9px status badge wrap onto a second line at 1280px wide.
  - Show the version dropdown only when there is more than one version; otherwise show plain "v1".
  - Make the badge at least 11px.
- **Make the action bar clearly ranked.** Under the 1330px rule, Approve, Edit and Return become 10px text with 7px padding. Give all three a 36px minimum height and 13px text:
  - **Approve and send**: primary button, full weight;
  - **Edit draft**: secondary button;
  - **Return**: plain text-style button.
  - Expand "Reviewer & notes" automatically when a note has been typed, and use 12px text for its toggle.
- **Concern coverage** uses 10px text with 9px sub-labels and 13px icons. Make them 12/11px with 16px icons. This list proves the agent covered everything, so it should be easy to read.
- Hide the "0 attachments" line when there are none, or show a muted "No attachments". The same applies to the left column's "0 attachments" heading.
- The findings section (`.response-findings`) is amber 10px text. Make it an amber callout box, because validation findings are something the reviewer must see.

---

## 4. Left column: correspondence and context (P1)

- The **Case context card repeats the header** (borrower, loan and client all appear again). In the workspace tab, either remove it (it is already on the Loan & client tab) or reduce it to a collapsible "More details" section. That leaves the column for the email and its attachments.
- **Email addresses break in the middle of words**, for example `correspondence@servicing.exampl` / `e.com`, because of `overflow-wrap: anywhere`. Use `text-overflow: ellipsis` with a `title` tooltip, or allow line breaks only after `@` and `.`.
- The address block (`From`/`To`/`Received`) is 11px with 10px sub-lines. Set a 12px minimum.
- The borrower message bubble has `min-height: 150px`, which leaves empty space for short emails such as DEMO-02's one sentence. Remove the minimum height.
- Show attachments as compact chips (icon, name, "PDF · v1"). Open a preview when the name is clicked and download when the arrow is clicked; today both open a new tab.

---

## 5. Dashboard (P0/P1)

What fits above the fold at 1280×640: the page title, 4 tiles and 2 rows. With an intake review waiting, it is 0 rows.

- **Shorten the page heading.** Remove the "CORRESPONDENCE OPERATIONS" label, which is 10px letter-spaced text above a heading that already says the same thing. Either remove the subtitle or put it on the same line as the title and "Live updates" badge. This saves about 60px.
- **Stop showing the same thing twice.** The 4 stat tiles and the 5 filter tabs are the same filters with the same counts.
  - Option A: keep the tiles and make them compact (about 64px high), then remove the filter tabs, adding "All" as a small reset link.
  - Option B: remove the tiles and make the filter tabs larger, with the count as a big number.
  - Either way, **"Open cases (5)" and "All cases (5)" both appear** at the moment, which looks redundant.
- **Make rows shorter.** They are currently 77px (18px padding plus 2-line cells). Aim for about 52–56px: CCID and subject on one line, borrower and loan on one line. That fits about 8 rows on a 13" screen instead of about 5.
- **Add the columns a reviewer needs to prioritise:**
  - **Age**: "2 / 20 workdays" with a mini bar that turns amber and then red. It is the service-level measure, and it is currently only visible inside a case.
  - **Next action**: "Review draft", "Waiting on borrower", "Specialist task".
  - Show received date and time together ("Sep 18, 10:30 AM").
  - Sort by default with *Needs review* first, then by age.
- **Make the incoming request review compact** (`IntakeReviews.tsx`). The inline card uses its own style (18px heading, pure-black text, uneven buttons) and pushes the table off-screen. Show it instead as a slim amber strip: "1 incoming request needs identity review · Question about my account · stranger@unknown.example **[Review]**". Open the form in a side drawer or dialog, not inline. The form also needs spacing and grouping; it currently uses 14px labels, a raw `<pre>` block and full-width controls.
- **Make new cases noticeable.** The key demo moment is sending an email in the Mailbox tab and switching to the Desk. When a case appears:
  - highlight the new row briefly;
  - show a short toast such as "New request · DEMO-CC-006 · Riley Example".
  Right now a row just appears silently.
- **Consider removing the footer bar** ("Listening for incoming correspondence…", "Business calendar…"). The "Live updates" badge already says the same, and 11px footer text is mostly unread.

---

## 6. Top bar (P1)

- Reduce the height from 68px to about 52px. On a 640px-tall screen, 16px is worth saving.
- **Replace the settings icon with an agent status chip**, such as `● Agent connected` (green) or `● Agent not configured` (amber), which opens the Setup & status dialog. This shows the audience that the Azure agent is live. The current sliders icon is unclear.
- Put Sign out in a menu under the avatar and name, which removes one bordered button from the bar.
- Remove "SERVICING OPERATIONS" (`.desk-environment`, 9px). It is already hidden below 1330px, so 13" users never see it.
- Search results: the dropdown (430px) is wider than the input (330px) and hangs past its right edge. Match the widths, add each case's status badge, highlight the matched text, and support ↑/↓ and Enter.

---

## 7. Make the reused "Classic" screens match the Desk (P1)

The **Routing & aging**, **System workspaces** (CCT, ILS, OnBase, Secure mail, Agent activity) tabs and the **Edit draft** dialog reuse components that are styled by `styles.css` and `operations.css`, which use the old sage and olive palette. So inside the teal Desk:

- the Edit dialog's primary buttons are dark sage `#214b3d`;
- values in Routing & aging are olive (`#4c5a3c`-ish), and labels use `Title Case Everything` ("Ready For Response", "Required For This Client");
- status pills are 9px with olive text (`.status-pill`), and labels are 9px letter-spaced (`.eyebrow`);
- the system panels repeat the case identity block (CCID, subject, borrower, status) that is already in the case header.

**Fix:** add a *bridge* block in `desk.css`, scoped under `.desk-theme`, that points the Classic class names (`.primary-button`, `.secondary-button`, `.status-pill`, `.eyebrow`, `.system-panel`, `.system-facts`, `.run-metrics`, `.alert`, `.workflow-*`, `.review-workspace` …) at the Desk tokens. This changes neither the Classic app (`?workspace=classic`) nor the Mailbox. Also hide `.system-case-identity` inside `.desk-systems`.

**Wording in the reused screens.** These are labels, not data:

- Raw tool and enum names are shown to users: "observe case", "apply plan", "send response", "ok", "final resolution", "document attached", "waiting for review". The Desk already has readable names for these in `ActivityTimeline.tsx` (`tools` map), and they can be reused in `AgentWorkspace.tsx`.
- The text "Review the current response in **Review queue**" (in `AgentWorkspace.tsx` and `SystemViews.tsx`) points to a screen the Desk doesn't have. Change it to "in the Case workspace".
- The **Agent activity** system tab mostly repeats the main timeline. Consider showing only the run summary and recovery panel there, and linking back to the timeline for the steps.
- The **CCT** tab includes the full Business assessment again, which is the same content as the Routing & aging tab. Show it in one place only.

---

## 8. Typography, colour and contrast (P0/P1)

**Font stack.** `.desk-theme` uses `"Segoe UI", Arial, sans-serif`. On a MacBook this falls back to Arial, which looks dated. Use:

```css
font-family: "Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system,
  BlinkMacSystemFont, "Inter", Roboto, sans-serif;
```

Also add `font-variant-numeric: tabular-nums` to CCIDs, loan numbers, times, ages and counts so numbers line up in the table and timeline.

**Type scale** (make these CSS variables and use them everywhere):

| Role | Now | Suggested |
|---|---|---|
| Tiny labels (receipt, footer, badges) | 8–10px | **11px** minimum, and use it rarely |
| Metadata, table secondary text, timestamps | 10–11px | **12px** |
| Body, table primary text, timeline text | 12px | **13px** |
| Letter body, borrower message | 12–14px | **14px** |
| Card titles | 13–15px | **15px** |
| Page / case title | 22–29px | **22–24px** |

**Contrast.** I measured these ratios against WCAG AA, which requires 4.5:1 for normal text:

| Pair | Ratio | Where it's used |
|---|---|---|
| `--accent #00a884` text on white | **3.03** ❌ | CCID links, tab labels, "CCT" system links, text buttons |
| white text on `--accent` button | **3.03** ❌ | Approve and send, SSO login |
| `--subtle #8696a0` on white | **3.05** ❌ | timestamps, icons, "5 cases" |
| `--accent` on `--accent-weak` | **2.73** ❌ | selected filter tab, following button |
| `--accent-hover #008069` on white | 4.89 ✅ | — |
| `--muted #54656f` on white | 6.06 ✅ | — |

**Fix:**

- Add `--accent-text: #008069` (or darker, `#00705c`) and use it for all accent-coloured **text**.
- Use `#008069` as the primary button background, with `#006a57` on hover.
- Keep `#00a884` only for dots, bars, icons and focus rings.
- Darken `--subtle` to about `#6b7a84` (roughly 4.5:1).

Projectors and laptop screens in bright rooms make low-contrast green text fade, so this also matters for the demo, not just for accessibility.

**Pure-black text.** `IntakeReviews`, the Classic screens and dialog bodies use default `#000`. Use `var(--ink)` everywhere.

---

## 9. Dialogs (P1)

- **Edit supported response** (`.desk-edit-dialog`): at 640px high the dialog is about 550px tall with a long form, and Save sits at the bottom of the scroll. Add a fixed dialog footer (Cancel / Save new version). Lay out the fact rows as a tidy grid; label, dropdown and value currently misalign. Make the "Acting reviewer" field read-only text instead of an editable-looking input, since it is always the signed-in reviewer (Admin).
- **Return for changes**: the disabled primary button (`opacity: .46`) looks washed out and unclear. Add a hint ("Add feedback to continue") or a character counter, and a Cancel button.
- **Setup & status**: show each missing field as a row with an ⚠ icon, and show a green "All set" state when everything is configured.

---

## 10. Login (P2)

- It looks clean. However, typing `admin` signs you in straight away (the `onChange` handler calls `onSignIn`), so the **SSO login** button is never clicked. In a demo, typing and then clicking SSO looks more deliberate. Consider signing in only on Enter or a button click. This is a behaviour change, so check it with whoever owns the demo script.
- Add a single line under the card, such as "Borrower correspondence · AI-assisted review". It gives the audience context on the first screen.

---

## 11. Motion and polish (P2)

- Keep the existing entrance animations (`desk-rise`) and the reduced-motion handling.
- Add the live-step pulse, new-row highlight and toast described above. These add the most impact for the demo.
- Case polling runs every 1.5s (`useDeskData(read, 1500, true)`). Make sure re-renders don't reset scroll positions or collapse the open `<details>` sections once the columns scroll independently.
- Add skeleton states for the case workspace too (three column outlines). It currently shows the plain text "Opening case…".

---

## Suggested order of work

1. **Quick wins (about half a day):** search icon z-index, contrast tokens (`--accent-text`, button background, `--subtle`), font stack and tabular numbers, a 12px minimum for the smallest text, and changing the 1330px breakpoint so it stops shrinking text. Also: hide the duplicate "Inquiry / Inquiry" routing line and the "0 attachments" line.
2. **Case workspace fits one screen (1–2 days):** full-height layout, independently scrolling columns, fixed action bar, compact header, compact timeline, white letter.
3. **Dashboard density (1 day):** shorter heading, combined tiles and tabs, 56px rows, Age and Next action columns, intake strip and drawer, new-case highlight and toast.
4. **Classic bridge and wording (1 day):** token bridge in `.desk-theme`, hide the repeated identity block, human-readable labels, "Review queue" wording.
5. **Polish:** dialogs, top bar agent status chip, live-run animation, case skeleton, 2-column fallback below about 1180px.

Check each step at **1280×620, 1366×680 and 1440×800**, at both 100% and 125% browser zoom. The existing Playwright setup can take these screenshots automatically.

---

## Mailbox guardrails

The Mailbox only loads `src/mailbox/mailbox.css`. It does **not** load `desk.css`, `styles.css`, `operations.css` or `login.css`, so every CSS change above is safe for it. The following files **are shared with the Mailbox and should not be changed**, or only changed with care:

- `src/desk/SenderMailboxPage.tsx`: this is the Mailbox page, even though it lives in the `desk/` folder.
- `src/desk/useDeskData.ts`, `src/api/client.ts`, `src/presentation.ts`: shared data and formatting helpers.
- `src/Mailbox.tsx`, `src/mailbox/**`, `mailbox/main.tsx`, `vite.mailbox.config.ts`.

Keep all new styles scoped under `.desk-theme` or `.correspondence-login`. Do not add new rules to `:root` or `body` in `styles.css`.
