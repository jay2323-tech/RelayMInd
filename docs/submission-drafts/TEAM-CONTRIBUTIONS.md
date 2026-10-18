# Team contributions and AI assistance

RelayMind was developed by **Jayanth Krishna** and **Kanak Garg**, with extensive AI coding assistance. The team split responsibility between graph/platform engineering and agent memory/coordination. Jayanth worked with **Claude Code (Anthropic)**, and Kanak worked with **Codex (OpenAI)**, following the original division of work.

## Jayanth Krishna — Graph and platform design, working with Claude Code

Jayanth's design and development responsibility covered the platform that supplies trusted graph context to the agents and controls supported business changes:

- **Graph infrastructure:** FalkorDB connectivity, server-controlled tenant graph selection, and project/session access boundaries.
- **Decision memory:** Approved decisions, their source evidence, supersession, conflicts and historical records.
- **Tasks and impact:** Task identities and immutable versions, dependency relationships, affected-work queries and evidence retrieval.
- **APIs and safeguards:** Session/run integration, proposed actions, explicit human approval, idempotency and stale-version checks.
- **Platform interface:** The application shell, evidence inspection and action-approval views in the original interface split.

Jayanth used Claude Code to help translate these requirements into graph queries, backend services, APIs, interface components, tests and technical documentation. Claude also assisted with debugging, platform integration and verification. Jayanth directed the work and reviewed the proposed behavior and implementation choices. He also coordinated product priorities and submission preparation; deployment completion is recorded separately once confirmed.

## Kanak Garg — Agent memory and coordination design, working with Codex

Kanak's design and development responsibility covered how agents retain context, exchange work and independently review proposals:

- **Conversation memory:** Persisting and retrieving messages in order, with conversation history available across sessions/process restarts within authorized access.
- **Episodic memory:** Recording historical episodes linked to supporting messages, while keeping remembered events distinct from current approved decisions.
- **Procedural memory:** Approved, versioned review procedures and retaining the procedure version used for a review.
- **Agent execution:** Planner proposals, validated read-only tool use and independent Reviewer checks against current graph records.
- **Coordination:** Persisted runs, handoffs and reviews, pause/resume behavior and the bounded correction workflow.
- **Agent interface:** Chat, conversation history and activity presentation in the original interface split.

Kanak used Codex to help implement and review the agent and memory components, persistence queries, provider adapters, coordination safeguards, tests and documentation. Codex assisted with debugging and integration, including evidence validation, affected-task coverage and handling provider failures. Kanak's responsibility was the agent-memory and coordination side of the agreed team design; AI assistance supported implementation within that area.

## Shared work

Both responsibility areas came together through shared schemas and tool contracts, synthetic fixtures, demonstration scenarios and integration between the agent engine and graph platform. Shared verification work covered stale decisions, evidence, access isolation, failure handling and selected concurrent-write scenarios. The team also shared responsibility for reviewing the final behavior and preparing the demonstration.

## How AI assistance is credited

Codex and Claude Code generated substantial portions of the implementation, tests and documentation. Human contribution includes design direction, requirements, coordination and review; it should not be read as a claim that either participant manually authored every file. The participants remain responsible for understanding and explaining the submitted system.

The pairing above describes the agreed team workstreams. Later integration assignments crossed the original boundaries—for example, Codex also worked on the chat-first frontend, while Claude extended backend workflows. These contributions remain credited to the relevant assistant in the historical development records.

The original ownership plan and assistant-specific development logs are retained in Git history after documentation cleanup. This document consolidates the agreed work split. Verification claims must refer to observed results, rather than implying that each participant personally ran every recorded test.
