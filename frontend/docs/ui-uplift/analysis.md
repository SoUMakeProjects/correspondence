# Correspondence Desk — UI Audit & Findings

> Persistent working notes for the UI uplift. Safe to re-read after context compaction.
> Last updated: 2026-09-23

## Scope & constraints (READ FIRST)

- **Goal:** uplift the *main* Correspondence app to a professional yet modern look.
- **The "main app" = the Desk app** (`src/desk/*`), which is what loads by default
  (see `src/auth/CorrespondenceApp.tsx` — default render is `<DeskApp>`; `<App>` only
  renders behind `?workspace=classic`).
- **DO NOT TOUCH THE MAILBOX.** The user considers `src/mailbox/*` + `src/Mailbox.tsx`
  + `src/mailbox/mailbox.css` finished. Excluded from all changes.
  - Caveat: the Desk *reuses* mailbox styles inside the "sender page" / operations
    surfaces via `operations.css` `.mailbox*` rules. Changing shared tokens must not
    regress the borrower mailbox. Keep mailbox visuals byte-identical.

## Architecture map

Four UIs share this repo, each with its own visual language:

| Surface | Entry | Stylesheet | Palette | In scope? |
|---|---|---|---|---|
| Login | `src/auth/CorrespondenceApp.tsx` | `src/auth/login.css` | Navy + blue `#1853bd` | Yes (part of Desk flow) |
| **Desk (default)** | `src/desk/DeskApp.tsx`, `src/desk/CaseDetail.tsx` | `src/desk/desk.css` + `src/operations.css` | Navy/blue, 5 CSS vars | **Primary target** |
| Classic (`?workspace=classic`) | `src/App.tsx` | `src/styles.css` | Sage green `#214b3d` | Legacy — confirm w/ user |
| Mailbox (borrower) | `src/Mailbox.tsx` | `src/mailbox/mailbox.css` | Outlook blue `#0f6cbd` | **OFF-LIMITS** |

Desk sub-components: `CaseDetail.tsx`, `ActivityTimeline.tsx` (419 lines),
`ResponsePanel.tsx` (423), `IntakeReviews.tsx`, `SenderMailboxPage.tsx`,
`DeskIcon.tsx`, `deskFormat.ts`, `useDeskData.ts`. Also reused by Desk:
`AgentWorkspace.tsx`, `CaseAssessment.tsx`, `SystemViews.tsx`, `CaseResources.tsx`.

Data layer: `src/api/client.ts` (+ generated `schema.d.ts`). Stack: React 19 + Vite 7,
plain CSS (no CSS framework, no CSS-in-JS), hand-rolled SVG icon path maps.

## What is already good (keep / build on these)

- Case **activity timeline** — `desk.css:875` (`.desk-timeline`), dotted connector, per-step icons.
- **"Paper receipt"** stripe motif — `desk.css:989` (`.action-receipt`, repeating diagonal gradient).
- **Letter-style response card** — `desk.css:1121` (`.response-paper`, `.letter-*`).
- `focus-visible` rings on every surface; `prefers-reduced-motion` honored everywhere.
- Sensible empty/loading copy and states.
- Desk already has a (tiny) token seed: `desk.css:2-6` (`--ink`, `--muted`, `--line`, `--blue`, `--pale-blue`).

## Findings (Desk-focused), highest impact first

### 1. No real design system — raw hex everywhere
- Only `desk.css:2-6` defines tokens (5 vars). `operations.css`, `login.css` use raw hex
  with hundreds of one-off colors.
- **4 button systems**: `.desk-button`/`.desk-button.primary` (4px radius, `desk.css:205`),
  `.primary-button`/`.secondary-button` (Classic), `.login-submit` (6px, `login.css:142`),
  mailbox `.mail-new` (off-limits). Different heights/radii/hovers.
- Cards at multiple radii: `.desk-card` 6px (`desk.css:314`) vs `.system-panel`/`.mailbox` 10px (`operations.css:88`).
- Inconsistent page max-widths: Desk `1680` (`desk.css:202`) vs operations `1720` (`operations.css:9`) vs Classic `1510`.
- **Action:** promote one token layer (color / space / radius / shadow / type) scoped under
  `.desk-theme` (and login) and consume it. Unlocks consistency + future dark mode.

### 2. Typography too small in places
- 8–9px carrying real info: action-receipt labels 8px (`desk.css:1006-1015`), th 9px,
  overline 9px (`desk.css:359`), timeline times 10px (`desk.css:930`), many 10–11px labels.
- **Action:** floor metadata ~11px, body ~12–13px; use weight/color for hierarchy, not shrinking.
- Base font is `13px` on `.desk-theme` (`desk.css:9`) — acceptable for data density; keep,
  but review the smallest tiers.

### 3. Contrast likely fails WCAG AA on muted text
- `.desk-worklist td small #7f91a1` on white (`desk.css:534`), `#7a8c98` overline,
  various `#718...`/`#80909e` labels on white.
- `.desk-badge.amber { background:#ffdf9e; color:#674711 }` (`desk.css:301`) — fully
  saturated, no border while good/blue/neutral are soft+bordered; it shouts louder than its priority.
- **Action:** darken muted token one step; give amber the same soft treatment as siblings.

### 4. Depth is essentially invisible
- Shadows ~1–6% alpha: `.desk-card box-shadow 0 2px 5px #223e4410` (`desk.css:318`);
  borders sit a hair off the `#eef3f0` background.
- **Action:** define a 2–3 step elevation scale (subtle / raised / overlay) and apply to
  cards, popovers, dialogs (`desk.css:1434`), sticky topbar (`desk.css:60`).

### 5. Responsiveness gaps
- Desk **case workspace** is a rigid 3-col grid `minmax(235..) minmax(330..) minmax(285..)`
  (`desk.css:739`). Only breakpoint at 1330px (`desk.css:1579`) *shrinks* cols; never stacks.
  Below ~1200px the timeline + response panel get cramped; no mobile path (Classic has 720px, Desk doesn't).
- **Action:** collapse to 2-col then 1-col below defined breakpoints; make cards flow.

### 6. Reads a bit "templated"
- Dashboard = stat tiles + filter tabs + table — competent but generic enterprise.
- **Action:** make the existing paper-receipt / letter motifs the signature; tighten to one
  confident accent + one type pairing; echo the motif in empty states + response preview.

### 7. Smaller items
- **Loading = plain text** ("Opening case…", `CaseDetail.tsx:84`). Add skeleton rows for worklist/timeline.
- **Icons duplicated & divergent:** `mail/settings/close/check/clock/arrow` defined in BOTH
  `App.tsx:26` and `DeskIcon.tsx:28` with different path data → same icon renders differently
  across Classic vs Desk. Consolidate to one icon module (Desk uses `DeskIcon`).
- **No dark mode** (blocked by #1; free once tokens exist). (Do NOT add dark mode to mailbox.)
- **Motion minimal** — only 0.16s color transitions. Add subtle hover lift on rows/cards +
  panel/dialog entrance fade (already gated by reduced-motion).
- Filter tab / stat-tile selected states are subtle; could use stronger affordance.

## Verification notes for later
- After any token change, diff-check the borrower mailbox at `?...` (Mailbox app) and the
  operations `.mailbox*`/`.mail-card*` reused rules in `operations.css` — must be unchanged.
- Check the 1330px and a new ~1024px / ~768px breakpoint for the Desk case workspace.
- Re-run `npm run build` (tsc + vite + mailbox vite) to ensure nothing breaks.
