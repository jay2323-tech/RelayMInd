# Agent engine — teammate side

engine.py: Planner/Reviewer orchestration with persisted handoffs and one correction.
loop.py: validated, bounded read-tool execution.
providers.py: Gemini/Groq adapters and retryable-error fallback.

Start with docs/agent-platform-integration.md. The real model API is not exercised
until you configure server-side keys and explicit model IDs. Scripted models exist
only in tests. Claude implements PlatformBridge and HTTP/UI integration on Jk.
