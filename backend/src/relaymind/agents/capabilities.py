"""Narrow, deterministic capability help; never answers factual recall requests.

Only whole-message questions about memory capabilities are handled here. Requests
for remembered facts, changes or actions continue through the existing workflow.
"""
import re

_MEMORY_QUESTIONS = {
    'can you remember things', 'can you remembers things', 'do you remember things',
    'can you remember', 'do you have memory', 'can you remember things across sessions',
    'can you remember things between sessions', 'how does your memory work',
    'how do you remember things', 'what can you remember',
}

MEMORY_CAPABILITY_ANSWER = (
    'Yes. I save messages in your conversations and can use recent messages and '
    'sourced historical summaries when preparing a plan. Saved conversations remain '
    'available after a backend restart.\n\n'
    'I only access records permitted for your account and project. Conversation history '
    'is not an approved decision, and I do not automatically turn everything you say '
    'into permanent knowledge. My planning context is bounded, so I may not retrieve '
    'every older detail.\n\n'
    'You can reopen a saved conversation to read its messages. For project work, ask '
    '“What changed from the original plan? Cite the approved decisions.”'
)


def capability_answer(request: str) -> str | None:
    normalized = re.sub(r'[^a-z0-9\s]', '', request.lower())
    normalized = ' '.join(normalized.split())
    if normalized in {'hi', 'hello', 'hey', 'hi there', 'hello there', 'good morning', 'good evening'}:
        return ('Hello! I can help you work through the current project using its approved '
                'decisions and evidence. Ask about what changed, affected work, or a proposed '
                'plan. Business changes need your approval. What would you like to explore?')
    return MEMORY_CAPABILITY_ANSWER if normalized in _MEMORY_QUESTIONS else None
