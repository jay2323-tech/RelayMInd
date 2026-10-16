from __future__ import annotations

from typing import Literal
from pydantic import Field, field_validator
from relaymind.contracts.models import StrictModel


class EpisodeRecord(StrictModel):
    """Pydantic model representing an episodic memory record."""
    id: str = Field(description="Episode UUID string (stable operation ID)")
    project_id: str = Field(description="Associated project identifier")
    source_message_id: str = Field(description="Supporting source message UUID")
    summary: str = Field(min_length=1, max_length=16000, description="Summary of what happened")
    occurred_at: int = Field(description="UTC epoch milliseconds when the event occurred")
    created_at: int = Field(description="UTC epoch milliseconds when episode was recorded")
    recorded_by: str = Field(description="Server-side identity (user_id) that recorded the episode")
    status: Literal["recorded"] = Field(default="recorded", description="Status of the episode")

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Summary must not be blank or whitespace-only.")
        if len(stripped) > 16000:
            raise ValueError("Summary must not exceed 16000 characters.")
        return stripped
