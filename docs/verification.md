# Scaffold verification

Verified during scaffold setup on October 15, 2026:

- Backend foundation checks: 2 passed (liveness and rejection of unknown plan fields).
- Frontend TypeScript check and Vite production build: passed.
- Installed npm dependency audit: 0 reported vulnerabilities at installation time.
- Live GET /api/health: returned scaffold liveness response.
- Same request through Vite proxy: passed.
- Docker Compose configuration: validated.
- Docker runtime: not verified because the daemon was not running.
- .env, .venv, node_modules and dist are ignored by Git.

No memory, graph queries, agents, authentication, or actions are implemented or
verified yet. The installed Starlette test client emits an httpx deprecation warning;
the current two foundation checks pass. Revisit the supported test-client dependency
when expanding HTTP tests. No model provider has been selected.

## Jk graph foundation

- Seven backend checks pass: foundation schemas/liveness and demo access policy.
- Access checks use test doubles; live session authorization query is not yet verified.
- Docker Desktop started; initial FalkorDB image download remains in progress.
- Live connection check returned connection refused while the image was downloading.
- No conversation writes, session creation, authentication or agents implemented.

## Live connection verified

The initial check failed because GRAPH.RO_QUERY cannot initialize an absent graph
key. The check now uses GRAPH.QUERY RETURN 1 to initialize each fixed demo graph,
then verifies GRAPH.RO_QUERY RETURN 1. Executed successfully against the running
local Docker database. Authentication and both graph queries passed; no message,
session, agent or cross-tenant data isolation behavior is proven by this check.

## Pinned FalkorDB image (2026-10-16)

- Image: `falkordb/falkordb@sha256:b0bdcac2cbaff989e77cb0610439b7a9289e86de033ccbbd4368b66fb680ae7a`
  (was `latest` on 2026-10-16; manifest list with `linux/amd64` and `linux/arm64`, checked against Docker Hub).
- `MODULE LIST` on Jayanth's Mac: graph module version `42201` (FalkorDB 4.22.1);
  module args `MAX_QUEUED_QUERIES 25`, `TIMEOUT 1000` (ms), `RESULTSET_SIZE 10000`.
- Compatibility checks C-1..C-3 and atomicity tests AT-1..AT-4 (memory-design.md §6–7): **not run yet.**
