"""Server-created identity snapshot for one agent job.

This is an engine boundary contract, not a browser request schema or a membership
resolver. The API must first verify the user's company/project/session access.
"""
from pydantic import ConfigDict, Field, field_validator

from relaymind.contracts.models import StrictModel, TrustedContext


class _FrozenTrustedContext(TrustedContext):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentJobScope(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: str = Field(min_length=1, max_length=200)
    user_id: str = Field(min_length=1, max_length=200)
    company_id: str = Field(min_length=1, max_length=200)
    project_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)

    @field_validator("tenant_id", "user_id", "company_id", "project_id", "session_id")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("Scope IDs must be nonblank and have no edge whitespace")
        return value

    def trusted_context(self) -> TrustedContext:
        return _FrozenTrustedContext(tenant_id=self.tenant_id, user_id=self.user_id)
