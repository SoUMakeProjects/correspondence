# Correspondence Desk — UI Uplift Plan & Progress

> Persistent working notes. Update the Progress + Decisions sections as work proceeds.
> Companion to `analysis.md`. Last updated: 2026-09-23

## Objective
Uplift the **Desk app** (`src/desk/*`, `src/operations.css`, `src/auth/login.css`) to a
professional-yet-modern look. **Mailbox is off-limits** (`src/mailbox/*`, `src/Mailbox.tsx`,
`src/mailbox/mailbox.css`) and its visuals must not regress.

## Decisions (confirmed 2026-09-23)
- **Scope: Desk app only.** Classic `src/App.tsx`/`styles.css` left as-is. Mailbox off-limits.
- **Direction: "Modern indigo"** — cool neutral surfaces, indigo accent, more whitespace,
  larger radii (8–10px), soft elevation. Tokens:
  - bg `#f4f6fb`, surface `#ffffff`, ink `#0f1b2d`, muted(AA) `#5b6b82`,
    accent `#4257d1` (hover `#3446b8`), accent-weak `#eef1fd`, brand `#1e2a44`.
- **Workflow: dashboard first.** Uplift the case dashboard end-to-end for sign-off, then
  roll the token system across case detail / login / polish.

## Proposed token layer (direction-agnostic structure)
Scope tokens under `.desk-theme` (and mirror the few login needs) so the mailbox `:root`
is never touched. Concrete color values depend on the chosen direction; structure is fixed:

```
/* color */            /* space (4px base) */   /* radius */    /* elevation */
--surface / --surface-raised / --surface-sunk   --space-1..8    --r-sm/md/lg   --shadow-sm/md/lg
--ink / --ink-2 (muted, AA) / --ink-3 (subtle)   --type scale: 11/12/13/15/18/22/29 with clamp()
--line / --line-strong
--accent / --accent-hover / --accent-weak (pale bg)
--good / --amber / --info / --danger  (+ matching -weak bg + -border, all soft+bordered)
```

## Phased plan
1. **Tokens** — add token block to `desk.css`; no visual change yet (map existing values to tokens).
2. **Primitives** — unify button/badge/card/input on tokens; fix amber badge; elevation scale.
3. **Typography & contrast** — raise smallest tiers; darken muted; consistent type scale.
4. **Dashboard** (`DeskApp.tsx`) — stat tiles, filter tabs, worklist table polish; skeleton loading.
5. **Case detail** (`CaseDetail.tsx` + timeline/response) — header, tabs, 3-col grid responsiveness,
   timeline & response-paper polish (lean into signature motifs).
6. **Login** (`login.css`) — align with new tokens.
7. **Motion & polish** — hover lift, entrance fades (reduced-motion safe).
8. **Icons** — consolidate duplicated maps (optional cleanup).
9. **Verify** — mailbox unchanged; breakpoints; `npm run build`.

## Files in scope
- `src/desk/desk.css` (primary), `src/operations.css`, `src/auth/login.css`
- `src/desk/DeskApp.tsx`, `src/desk/CaseDetail.tsx`, `src/desk/ActivityTimeline.tsx`,
  `src/desk/ResponsePanel.tsx`, `src/desk/IntakeReviews.tsx`, `src/desk/DeskIcon.tsx`
- Possibly `src/App.tsx`/`src/styles.css` (only if Classic is in scope)

## Files OFF-LIMITS
- `src/Mailbox.tsx`, `src/mailbox/**` (incl. `mailbox.css`). Do not edit; do not regress via shared tokens.

## Progress log
- 2026-09-23: Audit complete (`analysis.md`). Awaiting direction decisions. No code changed yet.
- 2026-09-23: **Phases 1–4 (dashboard) implemented + verified live.** Changes, all in
  `src/desk/desk.css` (scoped `.desk-theme`/`.desk-*`) + `src/desk/DeskApp.tsx`:
  - Full Modern-indigo token block added at top of `desk.css` (color/semantic/radius/
    shadow/focus). Legacy `--blue`/`--pale-blue` kept as aliases → tokens.
  - Primitives on tokens: buttons (solid indigo primary, no gradient), badges (amber
    softened + bordered like siblings), cards (10px, `--shadow-sm`), inputs, icon tiles,
    dialog (`--r-lg`+`--shadow-lg`), alerts/notice, `.desk-error` now defined.
  - Dashboard: stat tiles (white/shadow/hover-lift, selected=accent), filter tabs,
    worklist th/td/hover, footer, empty/loading, IntakeReviews.
  - Skeleton loading rows for worklist (`.desk-skeleton`, reduced-motion safe) + DeskApp
    renders 6 skeleton rows while `!value && !error`.
  - Verified via live preview (port 5199, real backend, 13 cases): `.desk-app` bg #f4f6fb,
    stat #fff/#e5e9f2/10px/soft-shadow, good badge #e7f4ee/#1f7a4d/#c6e5d4, th #f7f8fc.
    `npm run typecheck` clean.
  - Mailbox regression: **none possible** — only `desk.css` + `DeskApp.tsx` touched;
    `operations.css`/`mailbox.css` untouched; all new rules scoped to `.desk-theme`/`.desk-*`.
  - NEXT (awaiting dashboard sign-off): roll tokens across CaseDetail/ActivityTimeline/
    ResponsePanel (phase 5), login (6), motion/icons (7–8), then `npm run build` + mailbox
    diff check (9). Known deferred: dashboard has no <~1024px responsive path (finding #5).
- 2026-09-23: **Dashboard signed off ("Roll it out"). Phases 5–7 + 9 complete.**
  - **Phase 5 (case detail)** — entire case-detail region of `desk.css` tokenized:
    breadcrumb, case header/facts/age-track, `.case-tabs`, correspondence envelope,
    context-card, timeline (spine `--accent-weak-border`, dots/icons indigo), action-receipt
    (paper stripe kept, cool-tinted), response-paper letter motif, coverage/reviewer/awaiting/
    delivered/findings, fact-list, concerns, system-tabs, secondary/text/workflow buttons,
    diagnostics, and all `.sender-page` overrides. Signature motifs preserved.
  - **Phase 6 (login)** — `src/auth/login.css` rewritten onto a scoped token block on
    `.correspondence-login` (mirrors desk Modern-indigo: brand `#1e2a44`, accent `#4257d1`,
    accent-weak `#eef1fd`, etc.). Added responsive stack (`@media max-width:720px` → single
    column) and reduced-motion-safe card entrance + submit hover lift. Verified live:
    submit bg `#4257d1`/r-sm, brand-mark `#1e2a44`, access-icon `#eef1fd`/`#4257d1`;
    card collapses to 1 col at 375px.
  - **Phase 7 (motion)** — dashboard sections (`.desk-dashboard > *`) + `.desk-case` get a
    subtle staggered `desk-rise` entrance; login submit lift. All under
    `@media (prefers-reduced-motion: no-preference)` and covered by the existing
    `.desk-theme *` reduce kill-switch.
  - **Phase 8 (icons)** — intentionally SKIPPED (optional cleanup; touches component logic,
    not worth the regression risk for a visual uplift).
  - **Phase 9 (verify)** — `npm run build` green: desk bundle (`dist/`, CSS 61.11 kB) +
    borrower mailbox bundle (`dist-mailbox/`, CSS 24.41 kB) build independently. Mailbox
    bundle does not import desk.css/login.css, so it is provably unaffected. `tsc -b` clean.
  - Files touched across the whole uplift: `src/desk/desk.css`, `src/desk/DeskApp.tsx`,
    `src/auth/login.css` only. `operations.css`, `mailbox.css`, `src/Mailbox.tsx`,
    `src/mailbox/**` untouched. **Modern-indigo uplift complete.**
- 2026-09-23: **DIRECTION PIVOT → full WhatsApp Web restyle** (user request). Two asks:
  (a) remove the login left intro panel; (b) make the whole UI take WhatsApp inspiration.
  User picked "Full WhatsApp restyle" via AskUserQuestion.
  - **Login**: removed `.login-introduction` section (JSX in `CorrespondenceApp.tsx` + all its
    CSS). Now a single centered card (`.login-shell` min 420px), brand centered above. Responsive
    `@media max-width:480px`. Tokens swapped to WhatsApp palette.
  - **Palette** (`.desk-theme` + `.correspondence-login` token blocks): bg `#f0f2f5`,
    surface `#fff`, sunk `#f6f7f9`, ink `#111b21`, muted `#54656f`, subtle `#8696a0`,
    line `#e9edef`, line-strong `#d1d7db`, accent `#00a884`, accent-hover `#008069`,
    accent-weak `#e7f8e3`, brand `#075e54`, info→link-blue `#027eb5`, focus `#8fd8c6`.
    New bubble tokens: `--bubble-in #fff`, `--bubble-out #d9fdd3`, `--bubble-line #e9edef`.
    Shadows re-tinted to `rgba(11,20,26,*)`. Re-tinted raw leftovers (input-hover, shimmer,
    timeline gradient, receipt stripes→green-neutral, dialog scrim `#0b141a66`).
  - **Chrome**: `.desk-topbar` solid gray `#f0f2f5` (dropped glassy blur/translucency),
    `.desk-global-search > input` → rounded pill (`border-radius:999px`) white field.
  - **Chat bubbles**: `.correspondence-content` gray backdrop + `.borrower-message` = white
    incoming bubble (tail top-left); `.response-paper-wrap` gray backdrop + `.response-paper`
    = green outgoing bubble (`#d9fdd3`, tail top-right); `.timeline-content` = subtle bubble
    (chat rows), removed the per-row `::after` divider. Verified live: borrower `#fff`/tl-3px,
    response `#d9fdd3`/tr-3px, topbar `#f0f2f5`.
  - **Verify**: `npm run build` green; mailbox bundle byte-identical (`index-CWbJ4ARg.css`
    unchanged hash, 24.41 kB). Still only `desk.css`, `DeskApp.tsx`, `login.css`,
    `CorrespondenceApp.tsx` touched. **WhatsApp restyle complete.**
