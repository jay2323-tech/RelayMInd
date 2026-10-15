from __future__ import annotations

from typing import Literal
from pydantic import Field
from relaymind.contracts.models import StrictModel


class SessionRecord(StrictModel):
    """Pydantic model representing a conversation session record."""
    id: str = Field(description="Session UUID string")
    project_id: str = Field(description="Associated project identifier")
    owner_id: str = Field(description="Server-side identity (user_id) that owns the session")
    created_at: int = Field(description="UTC epoch milliseconds when the session was created")


class MessageRecord(StrictModel):
    """Pydantic model representing a message within a session."""
    id: str = Field(description="Message UUID (also operation ID)")
    session_id: str = Field(description="Session UUID this message belongs to")
    role: Literal["user", "assistant"] = Field(description="Origin of the message")
    content: str = Field(description="Message text (1-16000 characters)")
    created_at: int = Field(description="UTC epoch milliseconds when the message was stored")
    seq: int = Field(ge=1, description="Monotonically increasing sequence number within the session")
