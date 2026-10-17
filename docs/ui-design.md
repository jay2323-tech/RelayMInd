# RelayMind UI design spec — "Glass Relay"

Current visual direction (17 October, Jayanth): flat charcoal background, no visible
gradients or animated background blobs. Preserve clear liquid and frosted glass;
use neutral translucent fills, rim highlights and restrained shadows. This direction
supersedes the aurora/gradient styling below; existing workflow and truthful-state
requirements still apply. Active styles are tokens.css, glass.css and motion.css;
the older src/styles.css is not imported by main.tsx.

Version 1 · 2026-10-17 · Owner: platform (app shell, evidence, actions). Chat, history and
activity components belong to the agent-engine side; restyle them through props/CSS or agree
changes with their owner first (AGENTS.md, docs/team-ownership.md).

This document is the single reference for building the RelayMind agent interface in 1.5–2 days:
the concept, design principles, the Laws of UX applied as concrete rules, design tokens, the
liquid-glass recipe, every component, every agent animation and the data that drives it,
accessibility and performance limits, a build plan, a QA checklist, and a copy-paste prompt for
design/code assistants.

Reference for laws: https://lawsofux.com/ (30 laws; names used verbatim below).

---

## 0. The non-negotiable rule: motion tells the truth

RelayMind's whole pitch is *trustworthy* memory and handoffs. The UI must never imply work that
did not happen (AGENTS.md: "no simulated agent execution").

1. **Every agent animation is driven by a persisted event** from `GET /runs/{id}`
   (`run.events`, `run.status`, `handoffs`, `result`). No timed fake steps, no invented progress %.
2. While waiting for the next event, show an **indeterminate** state (breathing glow), never a
   bar that fills on its own.
3. Fixture or test data, if ever shown, carries a visible `TEST FIXTURE` chip.
4. Failures are first-class: a failed run animates to a clear failed state with the sanitized
   reason (`run.error`), never silently resets.

---

## 1. Concept

**"Glass Relay"**: a calm, dark, aurora-lit workspace where frosted glass panels float over a slow
moving gradient. A horizontal **Relay Track** across the top shows the baton passing between
agents: *Memory → Planner → Handoff → Reviewer → You*. Below it, the conversation and the
persisted plan sit in the centre; an **Inspector** on the right holds Evidence, Why-changed and
Actions. Decisions appear as a tiny living graph where superseded nodes dim and a glowing
`SUPERSEDES` edge points to the current one.

Mood words: *calm, precise, luminous, trustworthy, alive (but quiet)*.
Anti-mood: *casino, sci-fi HUD noise, glitter, cartoon robots*.

Signature moments (Peak-End Rule):
- **Peak:** a decision changes while a run is paused; on Resume, a ripple travels from the new
  decision node along the track and the Reviewer stamps `needs revision`, then the revised plan
  slides in.
- **End:** the final review lands as a soft green **seal**, and an approved task change shows
  `v1 → v2` with the version chip flipping.

---

## 2. Design principles

| # | Principle | Meaning in RelayMind |
|---|---|---|
| P1 | **Truthful motion** | Animate only real state changes (section 0). |
| P2 | **Provenance everywhere** | Every claim has a clickable source chip; evidence is one click away. |
| P3 | **Calm by default, vivid on change** | 90% of the screen is still; colour and motion are reserved for state changes and the user's next action. |
| P4 | **History visible, truth obvious** | Superseded items stay visible but dimmed; current items are bright. Never hide history, never confuse it with truth. |
| P5 | **Human gate is sacred** | Approve/Reject is the most deliberate interaction on the page: big, explicit, never auto-triggered. |
| P6 | **Depth means hierarchy** | Glass layers express importance (background < panels < focused card < modal), not decoration. |
| P7 | **Fast feels smart** | Respond under 400 ms to every click, even if the agent itself takes 20 s. |

---

## 3. Laws of UX applied as rules

Each law becomes a rule you can check in review.

| Law | Rule for RelayMind |
|---|---|
| **Aesthetic-Usability Effect** | Polish matters because judges forgive less in ugly tools: consistent radii, aligned 8 px grid, one icon set, no default browser controls visible. |
| **Doherty Threshold** | Every click gets visual feedback in < 100 ms (pressed state) and a meaningful response in < 400 ms (optimistic message bubble, skeleton plan card, "queued" track state). Agent work itself is shown as indeterminate, not blocking. |
| **Fitts's Law** | Primary actions (Send, Resume, Approve) are ≥ 44 px tall, sit at the end of the user's reading path, and are never tiny text links. Destructive or rare actions (Reject) are smaller and further away from Approve. |
| **Hick's Law** | At any moment show at most one primary action per zone (Send *or* Resume *or* Approve). The Inspector uses 3 tabs, not 3 stacked panels. |
| **Choice Overload** | Suggested prompts: max 3 chips. Affected tasks show one proposed action each ("Propose pause"), not a menu. |
| **Miller's Law / Working Memory** | The Relay Track has 5 stations (≤ 7). Activity log shows the latest 5 events expanded, older ones collapsed. |
| **Chunking** | Plan = summary + numbered steps + uncertainties + review, each a visually distinct chunk. Long IDs are chunked as chips (`decision-02`), not inline prose. |
| **Cognitive Load** | One accent colour per meaning (section 4.2). No more than 2 font weights per card. Hide technical IDs behind chips with tooltips. |
| **Tesler's Law** | Complexity of versioning (SUPERSEDES, TaskVersion, stale checks) lives in the system; the UI shows only *current / superseded / stale* and a reason sentence. |
| **Jakob's Law** | Chat layout behaves like familiar assistants: input at bottom, newest message at bottom, Enter to send, Shift+Enter for newline, history list on the left. |
| **Mental Model** | The relay metaphor maps 1:1 to the architecture (Planner hands a baton to an independent Reviewer). Labels use domain words: *decision, source, handoff, review, approve*. |
| **Law of Common Region** | Each concern lives in its own glass panel; related controls sit inside the same panel boundary (e.g. Resume lives inside the Relay Track, not in a random toolbar). |
| **Law of Proximity** | A citation chip sits directly next to the sentence it supports; a review issue sits directly under the step it criticises. |
| **Law of Similarity** | All evidence chips share one shape; colour encodes kind (decision, source, task, episode). Same kind = same look everywhere. |
| **Law of Uniform Connectedness** | Decision chain nodes are joined by a visible line with an arrow labelled SUPERSEDES; track stations are joined by the relay line the baton travels on. |
| **Law of Prägnanz** | Simple geometric forms: circles for agents, rounded rectangles for panels, pills for chips. No intricate illustrations. |
| **Von Restorff Effect** | Exactly one thing is visually unique per state: the paused baton (amber), a conflict banner (striped amber), the Approve button (solid accent). Never two competing highlights. |
| **Serial Position Effect** | Put the most important things first and last: the Relay Track first (top), the Approve gate last (bottom of Inspector Actions). |
| **Goal-Gradient Effect** | Track stations fill as the run advances (real events only), so users see the run approaching "You approve". |
| **Zeigarnik Effect** | Paused or awaiting-approval items keep a gentle unfinished marker (open ring) in history and tab badges until resolved. |
| **Peak-End Rule** | Design the decision-change ripple (peak) and the accepted seal plus version flip (end) with the most care (section 7). |
| **Selective Attention** | Agent status changes are announced in one place (track + live region). No blinking elsewhere; background motion is slow and low-contrast. |
| **Flow** | No modal interruptions during a run; evidence opens in the Inspector beside the plan, so the user never loses context. |
| **Paradox of the Active User** | No tutorial wall. Empty states teach by doing: a ghost suggestion "Continue launch preparation. What changed?" and a one-line hint. |
| **Postel's Law** | Accept messy input (trailing spaces, pasted multi-line text); output strict, consistent formatting (IDs as chips, statuses as fixed labels). |
| **Occam's Razor** | If a visual effect does not express state or hierarchy, remove it. |
| **Pareto Principle** | Spend 80% of polish on the 20% seen in the demo: Relay Track, plan card, why-changed, approval. |
| **Parkinson's Law** | Timebox the build (section 11). Glass effects get a fixed budget; stop at "good" and move to the next feature. |
| **Cognitive Bias** | Avoid automation bias: an `accepted` review is shown as *"Reviewer accepted"*, not "Verified", and the approval step still requires the human. |

---

## 4. Design tokens

Define all tokens as CSS custom properties in `frontend/src/styles/tokens.css`.

### 4.1 Colour (dark-first)

```css
:root {
  /* canvas */
  --bg-0: #070b14;            /* deepest */
  --bg-1: #0b1222;
  --aurora-a: #1fb6a6;        /* teal */
  --aurora-b: #5b6cff;        /* indigo */
  --aurora-c: #b46cff;        /* violet, sparingly */

  /* glass */
  --glass-fill: rgba(255,255,255,0.06);
  --glass-fill-strong: rgba(255,255,255,0.10);
  --glass-stroke: rgba(255,255,255,0.14);
  --glass-highlight: rgba(255,255,255,0.35);
  --glass-shadow: 0 10px 40px rgba(0,0,0,0.45);
  --glass-blur: 22px;
  --glass-saturate: 160%;

  /* text (on glass, all ≥ 4.5:1 against the scrimmed panel) */
  --text-1: #eef3fb;
  --text-2: #b9c4d6;
  --text-3: #8592a8;          /* captions only, ≥ 12px */

  /* meaning (one meaning per colour) */
  --accent: #2ee6c5;          /* primary action, current truth, live agent */
  --planner: #6ea8ff;         /* Planner agent */
  --reviewer: #c08bff;        /* Reviewer agent */
  --memory: #2ee6c5;          /* FalkorDB memory reads */
  --ok: #47d18c;              /* accepted, applied */
  --warn: #ffb547;            /* paused, needs revision, stale, conflict */
  --danger: #ff6b7a;          /* failed, blocked, reject */
  --superseded: #6b7689;      /* history (dimmed, never red) */

  /* evidence kinds */
  --chip-decision: #2ee6c5;
  --chip-source: #6ea8ff;
  --chip-task: #ffd166;
  --chip-episode: #c08bff;    /* history: always shows "historical" label */
}
```

A light theme is optional (stretch); if built, swap canvas to `#eef2f8`, glass fill to
`rgba(255,255,255,0.55)`, text to `#0f1a2b`, and keep meaning colours (darkened 15%).

### 4.2 Colour rules
- `--accent` is reserved for: primary button, current decision, live agent glow. Nothing else.
- Superseded = grey + 60% opacity + small "superseded by X" chip. Never red (history is not an error).
- Status colours appear as a 3 px left edge or a dot, plus a text label (never colour alone).

### 4.3 Typography
- Font: **Inter** (UI) + **JetBrains Mono** (IDs, chips). Load from Google Fonts.
- Scale (px / line-height): 12/16 caption · 14/22 body · 16/24 body-lg · 20/28 h3 · 28/34 h2 · 44/48 hero.
- Weights: 400 body, 600 headings/labels. Letter-spacing −0.02em on ≥ 28 px.
- Numbers in version chips use `font-variant-numeric: tabular-nums`.

### 4.4 Space, radius, elevation
- 8 px grid (4 px half-steps for chips). Panel padding 24 px desktop, 16 px mobile.
- Radius: chips 999 px · buttons 12 px · cards 18 px · panels 24 px.
- Elevation (glass depth): L0 canvas · L1 panels (blur 22) · L2 focused card (blur 28, stroke brighter) · L3 popover/toast (blur 32, strong fill).

### 4.5 Motion tokens

```css
:root {
  --t-instant: 90ms;    /* press feedback */
  --t-fast: 160ms;      /* hover, chip select */
  --t-base: 240ms;      /* panel/tab change */
  --t-slow: 420ms;      /* baton travel between stations */
  --t-peak: 900ms;      /* decision-change ripple, accepted seal */
  --ease-out: cubic-bezier(.2,.8,.2,1);
  --ease-in-out: cubic-bezier(.65,0,.35,1);
  --ease-spring: cubic-bezier(.34,1.56,.64,1);   /* only for the seal and version flip */
}
```

---

## 5. The liquid-glass recipe

### 5.1 Base frosted panel (all browsers that support backdrop-filter)

```css
.glass {
  position: relative;
  background: linear-gradient(180deg, var(--glass-fill-strong), var(--glass-fill));
  border: 1px solid var(--glass-stroke);
  border-radius: 24px;
  box-shadow: var(--glass-shadow), inset 0 1px 0 var(--glass-highlight);
  backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(var(--glass-saturate));
  isolation: isolate;
}
/* specular sheen: a soft diagonal highlight, static */
.glass::before {
  content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  background: linear-gradient(135deg, rgba(255,255,255,.18), transparent 40%);
  mix-blend-mode: soft-light;
}
/* grain to kill banding on gradients */
.glass::after {
  content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
  background-image: url("/noise.png"); opacity: .05; mix-blend-mode: overlay;
}
/* readable text: a scrim inside text-heavy cards */
.glass--text { background: linear-gradient(180deg, rgba(10,16,30,.72), rgba(10,16,30,.60)); }
```

### 5.2 "Liquid" edge refraction (Chromium only, progressive enhancement)

Use an SVG displacement filter on a thin rim only (not the whole panel) so text stays crisp.

```html
<svg width="0" height="0" style="position:absolute">
  <filter id="liquid" x="0" y="0" width="100%" height="100%">
    <feTurbulence type="fractalNoise" baseFrequency="0.008 0.012" numOctaves="2" seed="7" result="noise"/>
    <feDisplacementMap in="SourceGraphic" in2="noise" scale="18" xChannelSelector="R" yChannelSelector="G"/>
  </filter>
</svg>
```
```css
@supports (backdrop-filter: url(#liquid)) {
  .glass--liquid { backdrop-filter: url(#liquid) blur(18px) saturate(170%); }
}
```
Apply `.glass--liquid` only to: the Relay Track bar and the floating composer. Everything else is
plain `.glass`.

### 5.3 Pointer light (optional, desktop only)
A radial highlight following the cursor inside the Relay Track and primary buttons:
`background: radial-gradient(240px circle at var(--mx) var(--my), rgba(255,255,255,.10), transparent 60%)`,
with `--mx/--my` updated on `pointermove` (throttled with requestAnimationFrame). Disabled for
reduced motion and touch.

### 5.4 Background aurora
Three large blurred blobs (`--aurora-a/b/c`, opacity .35, `filter: blur(80px)`) drifting with a
60–90 s `transform` loop, behind everything, on a single fixed layer. Paused when the tab is
hidden and under `prefers-reduced-motion`.

### 5.5 Glass guard-rails
- Max **6** simultaneously visible backdrop-filtered layers. Lists inside panels are NOT glass.
- Never blur under scrolling content; the panel is glass, its scrolling body is a flat scrim.
- Text contrast is checked against the scrim colour, not the aurora.
- `@media (prefers-reduced-transparency: reduce)` → replace glass with solid `#121a2b` panels.
- No `backdrop-filter` support → fallback solid panels with the same radius and stroke.

---

## 6. Layout

### 6.1 Desktop (≥ 1200 px)

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Top bar: RelayMind · project launch-01 · identity chip · backend dot     │
├──────────────────────────────────────────────────────────────────────────┤
│ RELAY TRACK  (Memory)──(Planner)──(Handoff)──(Reviewer)──(You)  [Resume] │
├───────────┬────────────────────────────────────┬─────────────────────────┤
│ Sessions  │  Conversation                      │  Inspector (tabs)       │
│ rail      │  ─ messages                        │  [Evidence][Why][Act 2] │
│ (240px,   │  ─ Plan card (persisted handoff)   │                         │
│ collapsi- │  ─ Review seal                     │  Decision graph mini    │
│ ble)      │                                    │  Selected evidence      │
│           │  Composer (floating glass)         │  ...                    │
└───────────┴────────────────────────────────────┴─────────────────────────┘
```
Grid: `grid-template-columns: 240px minmax(520px, 1fr) 400px; gap: 20px; padding: 20px`.
The Relay Track spans the full width (sticky at top, height 112 px).

### 6.2 Tablet (760–1199 px)
Sessions rail collapses to an icon button + drawer. Inspector becomes a right drawer opened by
clicking any chip or the tab badges in the top bar.

### 6.3 Mobile (< 760 px)
Single column: Track (compact, 72 px, icons only) → Conversation → Plan. Inspector is a bottom
sheet (60% height) opened by chips. 16 px gutters. No horizontal scroll.

---

## 7. Agent animation system

### 7.1 State machine (derived from real data)

The track derives one state from the polled `RunView`:

| Track state | Derived from | Visual |
|---|---|---|
| `idle` | no run selected | stations outlined, baton parked at Memory, no glow |
| `queued` | `job.state == queued` | Memory station breathing (indeterminate) |
| `planning` | `run.status == planning` | Planner orb active (blue glow pulse 1.6 s), baton at Planner |
| `tool:<name>` | latest event `Read <tool>` | a light pulse travels Planner → Memory and back (420 ms); Memory node flashes the tool label (e.g. `fetch_evidence`) |
| `handoff_saved` | event `Saved handoff <id>` | baton drops onto Handoff station; station shows handoff chip `r1` |
| `paused` | `run.status == paused` | baton frozen on Handoff with amber ring; open-ring Zeigarnik marker; Resume button appears inside the track |
| `resumed` | event `Resumed saved handoff…` | a sweep (scan line) passes over Memory → Handoff ("rechecking current decisions") |
| `reviewing` | `awaiting_review` + job running | baton travels Handoff → Reviewer; Reviewer orb violet pulse |
| `needs_revision` | event `Review needs_revision` | Reviewer stamps amber "needs revision" badge, baton bounces back to Planner (ease-spring, small) |
| `completed` | `run.status == completed` | Reviewer → You: green seal lands (scale .6→1, 900 ms spring), You station lights |
| `blocked` | `run.status == blocked` | red edge on the station where it stopped + reason text |
| `failed` | `run.status == failed` | track desaturates, red dot at the failing station, sanitized `run.error` shown, "Try again" button |

Station for a failure is inferred from the error prefix (`planning:`, `review:`,
`independent_review:`); unknown → Planner.

### 7.2 Event parsing rules
Events are strings from the engine. Map with prefix rules, never by guessing content:
- `Retrieved approved decisions and procedure` → Memory read pulse.
- `Read <tool>` → tool pulse with label `<tool>`.
- `Saved handoff <id>` → handoff chip `r1`/`r2` (suffix of id).
- `Paused at saved handoff…` → paused. `Resumed saved handoff…` → resumed sweep.
- `Review <status>` / `Final review <status>` → reviewer stamp.
- Anything else → generic activity line, no special animation.
When several new events arrive in one poll, play them **sequentially** with 420 ms spacing (they
happened; we only replay them in order), capped at 2.5 s total; beyond that, jump to the final state.

### 7.3 Decision-change ripple (peak moment)
Trigger: Why-changed returns `decisions_changed: true` for the selected run, or the current
decision set changes between polls.
1. In the Inspector decision graph, the old node dims to `--superseded` (240 ms).
2. A new node scales in (ease-spring) with the `SUPERSEDES` edge drawing from new to old (420 ms, stroke-dashoffset).
3. A ring ripple (accent, 900 ms) emits from the new node; simultaneously the Relay Track's Memory station flashes.
4. Why-changed tab badge gets a dot until opened.

### 7.4 Approval moment (end)
- Click Approve → button shows pressed state (90 ms) → spinner inside button (no layout shift).
- `applied`: version chip flips `v1 → v2` (rotateX 180°, 420 ms), task row slides to "Recorded outcomes" with a green check.
- `stale` / `blocked_by_conflict`: row shakes 6 px twice (240 ms), amber chip, the exact `result` sentence shown. Never a green check.

### 7.5 Ambient motion budget
- At most one looping animation in the viewport at a time (the active station glow). Aurora excluded (very slow).
- No looping motion when idle except aurora.

### 7.6 Reduced motion
`@media (prefers-reduced-motion: reduce)`: no travel, no ripple, no flip, no aurora drift. State
changes become instant colour/label changes with 160 ms opacity fades. All information is still
present as text.

---

## 8. Component catalogue

All new presentation components live in `frontend/src/ui/` (owned by platform). Existing
components keep their props contracts.

| Component | Purpose | Data / props | Notes |
|---|---|---|---|
| `GlassPanel` | Base container | `level 1-3`, `liquid?`, `text?` | Implements section 5. |
| `AuroraBackground` | Canvas | none | Fixed, pauses when hidden. |
| `TopBar` | Brand, project, identity, backend status | `/api/identity`, health | Identity chip reads "local demo identity". |
| `RelayTrack` | Signature agent visual | `RunView`, `onPause`, `onResume` | Section 7. Contains the only Resume/Pause buttons. |
| `AgentOrb` | Planner / Reviewer / Memory / You station | `role`, `state` | Circle 56 px, glow per role colour. |
| `Baton` | Moving token | `station`, `state` | 14 px pill; amber when paused. |
| `ToolPulse` | Tool call particle | `tool` | Travels along an SVG path; label fades after 1.2 s. |
| `SessionRail` | Conversation history | wraps `ConversationHistory` props | Unfinished runs show open ring. |
| `ChatStream` | Messages | wraps `ChatPanel` data | Assistant summaries render IDs as chips (regex `/\b(decision|source|task)-\w+/`). |
| `Composer` | Floating glass input | `onSend`, `pauseAfterPlan` toggle | Enter send, Shift+Enter newline, 3 suggestion chips when empty. |
| `PlanCard` | Persisted handoff | `handoffs`, `run.result` | Header "Handoff r2 · persisted"; steps numbered; uncertainties as soft list. |
| `ReviewSeal` | Review outcome | `review.status`, `procedure` | accepted = green seal; needs_revision = amber stamp; blocked = red. Text: "Reviewer accepted · procedure launch-review v1". |
| `EvidenceChip` | Clickable ID | `id`, `kind?` | Mono font, colour by kind; tooltip shows kind + first 80 chars. |
| `Inspector` | Right panel with tabs | `tab`, badges | Tabs: Evidence · Why changed · Actions (badge = pending count). |
| `DecisionGraph` | Mini graph of the selected topic | `history: Decision[]` | SVG, nodes left→right by version; SUPERSEDES arrows; current node accent. |
| `EvidenceView` | Selected evidence | `/evidence/{id}` | Episode shows "historical, not current" banner. Task shows version timeline. |
| `WhyChangedView` | Comparison | wraps `WhyChangedPanel` data | Two columns "Remembered" vs "Current", plans below. |
| `ActionGate` | Human approval | affected, actions | Approve is the only solid button in the Inspector. |
| `ConflictBanner` | Conflicting decisions | `conflicts[]` | Striped amber, "Requires human resolution; agents will not choose." |
| `Toast` | Transient feedback | message, tone | L3 glass, bottom-centre, 4 s, aria-live polite. |
| `Skeleton` | Loading | shape | Shimmer ≤ 1.2 s loop; replaced as soon as data arrives. |

---

## 9. Content and microcopy

- Voice: precise, plain, calm. Verbs first: "Resume run", "Propose pause", "Approve change".
- Status labels (fixed): Queued · Planning · Handoff saved · Paused · Reviewing · Needs revision · Completed · Blocked · Failed.
- Never say "AI verified". Say "Reviewer accepted". Never say "done" for a proposal: "Proposed — waiting for your approval".
- Empty states:
  - Conversation: "Ask about the launch. RelayMind remembers decisions across sessions." + chip "Continue launch preparation. What changed?"
  - Evidence: "Click any ID to see its source."
  - Actions: "No change needs your approval."
- Errors: "Planning stopped: the model returned an invalid response. Nothing was saved as a plan. Try again." (from `run.error`, never raw stack traces).

---

## 10. Accessibility and performance

Accessibility (WCAG 2.2 AA):
- Text contrast ≥ 4.5:1 on scrims; large text ≥ 3:1. Check every glass panel with the aurora at its brightest.
- Focus ring: 2 px `--accent` + 2 px offset, visible on glass.
- Relay Track has `role="status"` text mirror: "Planner saved handoff r1. Paused." (aria-live polite).
- All chips are buttons with accessible names (`decision-02, decision, current`).
- Keyboard: Tab order TopBar → Track → Conversation → Composer → Inspector; `Esc` closes drawers; Enter sends.
- Colour never alone: every status has an icon + label.
- Respect `prefers-reduced-motion` and `prefers-reduced-transparency`.

Performance:
- 60 fps target on a mid laptop. Animate only `transform` and `opacity` (and SVG stroke-dashoffset).
- ≤ 6 backdrop-filter layers visible; aurora is one layer with `will-change: transform`.
- Polling stays at 1.5 s while a job is active; stop when settled (already implemented).
- No animation library required. Optional: `motion@11` for spring sequencing if CSS becomes awkward. No other new runtime dependencies.
- Bundle budget: + ≤ 40 kB gzip over current.

---

## 11. Build plan (1.5–2 days)

| Block | Time | Deliverable | Done when |
|---|---|---|---|
| A. Foundations | 2 h | `tokens.css`, fonts, `AuroraBackground`, `GlassPanel` (+ fallbacks) | Panels look correct in Chrome, Edge, Safari; reduced-transparency fallback works |
| B. Layout shell | 2 h | `TopBar`, 3-column grid, responsive drawers/sheet | No horizontal scroll at 360 px; Inspector tabs switch |
| C. Relay Track | 4 h | `RelayTrack`, `AgentOrb`, `Baton`, `ToolPulse`, state machine + event parser | Replaying a real run's events shows correct stations; reduced-motion shows text-only |
| D. Conversation & plan | 3 h | `ChatStream`, `Composer`, `PlanCard`, `ReviewSeal`, `EvidenceChip` | IDs become chips everywhere; seal shows real review |
| E. Inspector | 3 h | `DecisionGraph`, `EvidenceView`, `WhyChangedView`, `ConflictBanner` | Decision change produces the ripple; superseded nodes dimmed |
| F. Action gate | 2 h | `ActionGate`, version flip, stale/blocked states | Approve → v2 flip; stale shows amber with reason |
| G. Polish & QA | 3 h | microcopy, focus, contrast fixes, perf pass, demo rehearsal | Section 12 checklist passes |

Day 1: A, B, C (track is the riskiest and most visible). Day 2: D, E, F, G.
Cut order if late (Parkinson / Pareto): pointer light → liquid refraction → mobile sheet polish →
DecisionGraph animation (keep static) → light theme. Never cut: truthful states, Approve gate,
evidence chips, reduced-motion.

File structure:
```
frontend/src/
  styles/tokens.css  styles/glass.css  styles/motion.css
  ui/GlassPanel.tsx  ui/AuroraBackground.tsx  ui/TopBar.tsx
  ui/track/RelayTrack.tsx  ui/track/AgentOrb.tsx  ui/track/Baton.tsx  ui/track/ToolPulse.tsx
  ui/track/trackState.ts      # pure: RunView -> TrackState, events -> animation queue (unit-testable)
  ui/plan/PlanCard.tsx  ui/plan/ReviewSeal.tsx  ui/EvidenceChip.tsx
  ui/inspector/Inspector.tsx  ui/inspector/DecisionGraph.tsx  ui/inspector/EvidenceView.tsx
  ui/inspector/WhyChangedView.tsx  ui/inspector/ActionGate.tsx  ui/ConflictBanner.tsx
  ui/Toast.tsx  ui/Skeleton.tsx
```
`trackState.ts` must be a pure function with tests (feed real recorded `RunView` JSON from
`docs/verification.md` runs; no invented sequences).

---

## 12. QA checklist (before recording the demo)

- [ ] Every animated step corresponds to a real event in the polled run (spot-check 3 runs).
- [ ] Failed run shows the failing station and sanitized reason; no green anywhere.
- [ ] Pause → change decision → Resume shows: amber baton, recheck sweep, needs-revision stamp, revised plan, seal.
- [ ] Why-changed ripple plays once per change, not on every poll.
- [ ] Approve: v1→v2 flip; second click impossible; stale path shows amber reason.
- [ ] All chips open evidence; episode evidence labelled historical.
- [ ] Contrast ≥ 4.5:1 on all text (check with DevTools); focus visible on every control.
- [ ] Reduced motion and reduced transparency both usable.
- [ ] 360 px, 768 px, 1440 px layouts; no horizontal scroll.
- [ ] Chrome performance panel: no long tasks > 50 ms during track animation; ≤ 6 blur layers.
- [ ] `npm run build` passes; no console errors.

---

## 13. Do / Don't

Do: animate state changes; keep history visible but dim; one accent; big Approve; chips for IDs;
text mirror for every visual state.

Don't: fake progress bars; animate while idle; glass on scrolling lists; red for superseded
(history is not an error); auto-approve; hide model failures; more than one highlighted thing per state.

---

## 14. Copy-paste design prompt (for Claude / v0 / Figma AI)

> Design and build the frontend for **RelayMind**, a web app where two AI agents (Planner and an
> independent Reviewer) share long-term memory in a graph database, hand off work through a
> persisted handoff, and ask a human to approve task changes. Style: **"Glass Relay"**, a calm,
> dark, aurora-lit workspace with **liquid-glass frosted panels** (backdrop blur 22 px, saturate
> 160%, 1 px white-14% stroke, inner top highlight, soft diagonal sheen, subtle grain), Inter +
> JetBrains Mono, 8 px grid, radii 24/18/12/999, one teal accent `#2ee6c5`, Planner blue
> `#6ea8ff`, Reviewer violet `#c08bff`, warn amber `#ffb547`, danger `#ff6b7a`, superseded grey
> `#6b7689`.
>
> Layout: sticky full-width **Relay Track** at top showing five stations (Memory → Planner →
> Handoff → Reviewer → You) with a moving baton; left collapsible sessions rail; centre
> conversation with a persisted **Plan card** (summary, numbered steps with clickable evidence
> chips, uncertainties, review seal); right **Inspector** with tabs Evidence (mini decision graph
> with SUPERSEDES arrows, selected evidence), Why changed (remembered vs current decision, original
> vs latest plan), Actions (affected tasks, Propose pause, big Approve, smaller Reject, recorded
> outcomes with version chips v1→v2).
>
> Animations must reflect only real run events (planning, tool reads such as `fetch_evidence`,
> handoff saved, paused, resumed recheck, review needs_revision, final review accepted, failed);
> use an indeterminate glow while waiting, never fake progress. Peak moment: when a decision is
> superseded, the old node dims, a new node springs in with a drawn SUPERSEDES edge and a ripple.
> End moment: accepted review lands as a green seal; approved task flips v1→v2.
>
> Apply Laws of UX: Doherty Threshold (feedback < 400 ms), Fitts's Law (44 px primary targets),
> Hick's Law (one primary action per zone, tabs not stacks), Miller's Law (≤ 7 stations, 5 recent
> events), Common Region / Proximity / Similarity / Uniform Connectedness for grouping, Von
> Restorff for the single highlighted element per state, Peak-End Rule, Zeigarnik markers for
> unfinished runs, Jakob's Law chat conventions, Tesler's Law (hide versioning complexity behind
> current / superseded / stale labels). Support prefers-reduced-motion and
> prefers-reduced-transparency, WCAG AA contrast on glass, keyboard focus rings, responsive
> 360–1440 px, ≤ 6 blur layers, transform/opacity-only animation. React + TypeScript + Vite, CSS
> custom properties, no heavy UI libraries.

---

## 15. Data contract cheat-sheet (what the UI can rely on)

| UI need | Endpoint | Fields |
|---|---|---|
| Identity | `GET /api/identity` | `tenant_id, user_id, mode` |
| Sessions | `GET/POST /api/projects/launch-01/sessions` | `id, title, created_at` |
| Messages | `GET …/sessions/{sid}/messages` | `id, role, content, seq` |
| Start run | `POST …/sessions/{sid}/runs` | body `request, mode: run|plan_then_pause` → `run_id` |
| Poll run | `GET …/runs/{rid}` | `run.status, run.events[], run.error, run.result.review, handoffs[].plan, job.state` |
| Pause / Resume | `POST …/runs/{rid}/pause|resume` | — |
| Why changed | `GET …/runs/{rid}/changes?task_ids=` | `decisions_changed, changes[], original_plan, latest_plan` |
| Decisions | `GET /api/projects/launch-01/decisions` | `current[], conflicts[], conflicting[]` |
| Evidence | `GET …/evidence/{id}` | `kind, text, decision, history` |
| Affected tasks | `GET …/tasks/affected` | `task, superseded_decision_id, replaced_by` |
| Actions | `GET/POST …/actions`, `POST …/actions/{id}/approve|reject` | `status, result, applied_version_id` |

Run statuses: `planning, awaiting_review, paused, completed, needs_revision, blocked, failed`.
Action statuses: `proposed, applied, stale, blocked_by_conflict, rejected`.
