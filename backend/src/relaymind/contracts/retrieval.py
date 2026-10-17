"""Additive read-search contract. Context and graph are never model arguments."""
from typing import Literal
from pydantic import Field, field_validator, model_validator
from relaymind.contracts.models import StrictModel


class SearchArguments(StrictModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Search must be nonblank")
        return value.strip()


class SearchHit(StrictModel):
    evidence_id: str
    source_id: str
    title: str
    excerpt: str = Field(max_length=800)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SearchResult(StrictModel):
    status: Literal["found", "not_found"]
    query: str
    project_id: str
    searched: Literal["authorized_project_sources"] = "authorized_project_sources"
    method: Literal["all_terms_substring_v1"] = "all_terms_substring_v1"
    hits: list[SearchHit] = Field(max_length=10)
    has_more: bool
    checked_at: int
    message: str

    @model_validator(mode="after")
    def coherent_result(self):
        if (self.status == "found") != bool(self.hits):
            raise ValueError("Search status must agree with retrieved hits")
        if self.has_more and not self.hits:
            raise ValueError("Empty results cannot have more hits")
        return self


class EvidenceVersion(StrictModel):
    """Saved evidence-view snapshot; state remains unknown without typed authority."""
    evidence_id: str
    source_id: str
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    version_id: str | None = None
    state: Literal["current", "historical", "conflicting", "unknown"]
