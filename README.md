# RelayMind

Agents that remember decisions and hand off work with evidence.

A two-person FalkorDB Graph Hacks project, separate from the personal Workbuddy
project. Primary track: **Agent Memory and Coordination**.

## Current status

Conversation and sourced episode persistence, approved procedure versions, and a
Planner–Reviewer engine are implemented in this branch. Handoffs and reviews persist
in FalkorDB; one correction round and decision freshness checks are enforced.
Gemini/Groq adapters are available but require server-side keys and explicit model
IDs. Database workflow checks use a labeled scripted model; live LLM grounding is
not yet verified.

The interface has reusable chat/history/activity components. API/app integration,
real platform decision tools, production identity and task approval are pending.
Read docs/agent-platform-integration.md before wiring the engine. The default app
still displays an unconnected development workspace honestly.

## Prerequisites

Python 3.11+, Node 20.19+ or 22.12+ (Node 24 works), npm, Docker with Compose.
Run commands from the repository root unless stated otherwise.

## Local setup

```sh
cp .env.example .env
# Edit .env and set a local FALKORDB_PASSWORD.
docker compose up -d
python3 -m venv .venv
.venv/bin/python -m pip install -e './backend[dev]'
```

Backend (terminal 1):

```sh
.venv/bin/python -m uvicorn relaymind.main:app --reload --env-file .env
```

Frontend (terminal 2):

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Backend docs: http://127.0.0.1:8000/docs.
Vite forwards /api requests to the backend. The backend health indicator reports
process connectivity only; no database or model call occurs.

```sh
.venv/bin/python -m pytest backend/tests
cd frontend
npm run build
```

Backend exact installed versions are recorded in backend/requirements.lock.txt;
frontend exact versions in package-lock.json. The backend lock excludes the local editable package. To reproduce it, install
`backend/requirements.lock.txt`, then install the backend in editable mode.
Pin a tested FalkorDB image digest before the demo. `docker compose down` preserves
the named data volume; `docker compose down -v` deletes it and must not be used as
a routine stop command.

## Team and design

Read AGENTS.md and docs/team-ownership.md. The agent-engine teammate owns the engine,
conversation/episode/procedure memory, handoffs and chat/activity UI. The platform
teammate owns graph infrastructure, semantic decisions, tools, APIs, authorization
and evidence/actions UI. See docs/contracts.md before changing shared interfaces.

Detailed guide: docs/agent-engine-learning-and-build-guide.pdf.
Start with docs/implementation-plan.md and its first persisted-message milestone.

## Submission preparation

Provide a public repository, graph model and essential queries, reproducible setup,
working video, chosen tracks and honest AI-assistance disclosure.
Repository: https://github.com/jay2323-tech/RelayMInd
Never commit .env or real private data.

## Graph foundation (Jk)

After starting Docker Desktop and `docker compose up -d`, verify the database with:

```sh
.venv/bin/python scripts/check_graph.py
```

The foundation includes fixed local-demo graph access and a session ownership
query. It does not implement login. Conversation persistence is available in memory/conversations.py. See
`docs/conversation-memory-integration.md` before building the conversation module.
