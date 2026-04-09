from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.schemas.oracle import MetadataEnrichmentSummary


class RankedApproach(BaseModel):
    approach: str
    score: int = Field(ge=0, le=100)
    reason: str


class SecondaryOption(BaseModel):
    approach: str
    score: int = Field(ge=0, le=100)
    why: list[str]


class RecommendationResponse(BaseModel):
    request_id: str
    recommended_approach: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    score: int = Field(ge=0, le=100)
    why: list[str]
    companion_tools: list[str]
    prerequisites: list[str]
    risk_flags: list[str]
    secondary_option: SecondaryOption | None = None
    rejected_approaches: list[RankedApproach]
    manual_review_flags: list[str]
    rules_version: str
    metadata_enrichment: MetadataEnrichmentSummary | None = None
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
