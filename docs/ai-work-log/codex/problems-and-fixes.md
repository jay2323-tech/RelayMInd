# Problems encountered and how they were handled

Historical setup incidents are retrospective from session command outputs. Reproduction
is described without credentials, private data or machine-wide repair instructions.

## P01 - Existing GitHub repository contained a separate initial README

**Observed:** unrelated local and remote histories; README add/add conflict on merge.
**Cause:** local scaffold and GitHub-created title commit started independently.
**Fix:** merged histories, kept detailed local README and preserved remote ancestry.
**Effect/evidence:** push succeeded; original GitHub history was not force-replaced.
**Prevention:** fetch and inspect before a first push into an existing repository.

## P02 - npm could not write the user's cache

**Observed:** npm install failed with EPERM under ~/.npm/_cacache.
**Cause:** default cache was outside the writable sandbox; npm also reported ownership
advice. We did not establish that a machine-wide ownership repair was needed.
**Fix:** used a task-specific writable /private/tmp/relaymind-npm-cache.
**Effect/evidence:** installation and frontend build completed without altering the
user's global cache permissions.

## P03 - Docker daemon unavailable and image not downloaded

**Observed:** missing Docker socket first; no RelayMind containers; pull took time.
**Cause:** Docker Desktop was not running initially, then the image was absent locally.
**Fix:** started Docker Desktop and ran docker compose up -d with required execution
permission. User later supplied successful image/volume/container startup output.
**Effect/evidence:** authenticated graph check eventually passed on both laptops.
**Lesson:** a Running container and a successful application connection are separate checks.

## P04 - First graph check failed on an empty key

**Observed:** Invalid graph operation on empty key from GRAPH.RO_QUERY RETURN 1.
**Cause:** graph key did not yet exist; read-only query could not initialize it.
**Fix:** use GRAPH.QUERY RETURN 1 for initialization, then verify GRAPH.RO_QUERY.
**Effect/evidence:** live authenticated check passed for both fixed demo graph mappings.
**Scope:** initializes empty graph keys, not conversations or agent state.

## P05 - Teammate ZIP folder and Windows setup confusion

**Reported:** docker compose could not find configuration; git status was run outside
Git metadata. Screenshots showed nested RelayMInd-main directories.
**Cause:** commands were executed in an outer ZIP/download folder.
**Resolution:** locate repository root containing compose.yaml/backend/README, use the
correct Git checkout, fetch/merge main, and use .venv\Scripts\python.exe on Windows.
**Evidence boundary:** teammate screenshots later showed clean feature branch, successful
merge and PASS connection output. Codex did not remotely inspect her filesystem.

## P06 - Episode retry idempotency had a check/create race

**Observed by source review:** separate existence query and CREATE without serialization.
Two calls could both observe absence. Existing serial retry tests did not cover it.
**Fix:** shared RLock wraps complete memory write functions, including conversation
sequence allocation. Preserve existing retry/conflict checks.
**Effect/evidence:** parallel identical retry checks pass against real local FalkorDB.
**Remaining:** processes do not share a Python lock. Multi-process uniqueness is pending.

## P07 - Same-tenant test did not exercise its claimed boundary

**Observed by source review:** second user lacked project access, so the helper denied
before evaluating private source-session access.
**Fix:** test-only access entry grants the peer the same graph/project. Assert source
citation denial and empty episode retrieval while keeping production mapping unchanged.
**Effect/evidence:** new unit case actually reaches the source visibility logic.
**Remaining:** real authentication and additional live peer cases belong to integration QA.

## P08 - Two assistants could overwrite each other's files

**Risk addressed before edits:** Claude works on Jk while Codex covers teammate side.
**Fix:** managed isolated checkout and feat/agent-memory-engine branch; ownership-specific
files and explicit PlatformBridge/UI prop contract. No subagents used.
**Effect/evidence:** delivery committed/pushed separately in draft PR #4; original Jk
checkout was not changed by these implementation commands.

## P09 - Model credentials were not configured

**Observed:** checks for presence of local Gemini/Groq API keys/model IDs returned absent.
**Handling:** adapters and wire checks added; database tests use clearly labeled model
and platform doubles. Documented live-model integration as pending.
**Effect:** orchestration could be verified without fabricating a live model result.
**Next:** enter server-side credentials/model IDs locally, connect real bridge and run
live grounding scenarios. Never paste credential values into logs or documentation.

## P10 - Existing Starlette/httpx deprecation warning

**Observed:** test suite warns about httpx in Starlette TestClient.
**Status:** unresolved compatibility cleanup. The observed 52 checks passed.
**Handling:** recorded rather than suppressing or mislabeling it as a failure.
**Next:** platform owner can update the supported test-client dependency and lockfile
when expanding HTTP verification.

## P11 - Workspace filesystem and localhost access restrictions

**Observed:** managed worktree writes or localhost/Docker socket access denied inside
sandbox. These are execution-environment limits, not database defects.
**Fix:** requested scoped execution permission and reran authorized commands.
**Effect:** code authored in isolated checkout and real DB checks executed successfully.
**Lesson:** distinguish an operation-permitted error from connection refused or query errors.
