# RelayMind

Agents that remember decisions and hand off work with evidence.

A two-person FalkorDB Graph Hacks project focused on Agent Memory and Coordination.
This is separate from the personal Workbuddy project.

## Core workflow

A Planner retrieves current decisions and relevant history, creates a sourced plan,
and persists a structured handoff. A Reviewer independently checks that plan against
current decisions, source evidence, and a versioned review procedure. One correction
round is allowed. Proposed task changes require approval.

## Ownership

- Agent-engine owner: Planner, Reviewer, conversation memory, episodic memory,
  procedural memory, persisted handoffs, chat/history/activity frontend.
- Platform owner: FalkorDB setup, shared schema, semantic memory, decision
  supersession, graph tools, APIs, authorization, action approval, evidence frontend.

## Guide

See docs/agent-engine-learning-and-build-guide.pdf for the detailed learning and
implementation plan.

## Status

Planning folder created. Application implementation has not started here.
