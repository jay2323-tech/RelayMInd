# Demo script (~3–4 minutes)

All data is synthetic. Use real model runs; if the provider fails live, say so, click **Ask again**,
and keep the backup recording ready. Never present a scripted/fixture run as a live one.

## Before recording

```sh
docker compose up -d
.venv/bin/python scripts/reset_northstar_platform.py --yes-reset-launch-01
.venv/bin/python scripts/seed_northstar.py --stage before-change
.venv/bin/python scripts/reset_adventureworks.py --yes-reset-aw-qh-17
.venv/bin/python scripts/seed_adventureworks.py --stage before-change
# backend + frontend running (README quick start); browser at http://127.0.0.1:5173
```

## 1. Memory + coordination — Northstar (≈2 min)

1. Sign in as `northstar.lead`. Point out: identity badge comes from the server session.
2. New conversation → switch on **Pause after the Planner saves its handoff** → click the suggestion
   "Continue launch preparation. What changed, and what should we do next?"
3. Relay Track: Memory → Planner glows (real events) → **paused at Handoff r1**. Plan cites `decision-01`.
4. Click `decision-01` → Evidence: current, sourced, with history.
5. Change the decision (terminal): `scripts/seed_northstar.py` → decision-02 SUPERSEDES decision-01.
6. Click **Resume · recheck decisions** → Reviewer: *needs revision* (decisions changed) → Planner r2
   addresses task-01/task-02 → **Reviewer accepted** (seal). Say: the Reviewer reloaded the handoff
   from FalkorDB, not the Planner's memory.
7. Inspector → **Why changed** (remembered vs current) → **Evidence** decision graph v1 → v2.
8. **Actions** → Propose pause task-01 → **Approve change** → v1 → v2.

## 2. Company isolation (≈20 s)

Sign out → sign in as `harbor.lead`: different company graph, Northstar sessions/decisions invisible.

## 3. Manufacturing change during execution — AdventureWorks (≈1 min)

1. Sign in as `aw.quality` → Inspector **Actions**: hold QH-17 v1, exposed AW-O101 (open) and AW-O102
   (shipped → QA review, no hold), AW-O105 **unknown traceability, not safe**.
2. Apply the expanded notice: `scripts/seed_adventureworks.py --stage after-change` → reload.
3. Impact recomputed by graph traversal: hold v2 (v1 superseded), **AW-O103 now exposed**.
4. Propose hold AW-O103 → **Approve change** → "AW-O103 is now on hold (v2)". Mention: a hold proposed
   under v1 would now be rejected as stale.

## Close (≈10 s)

"Current truth is a graph property (SUPERSEDES), impact is a traversal, and every change waits for a
human approval that re-checks the graph." Show README / graph-model page.
