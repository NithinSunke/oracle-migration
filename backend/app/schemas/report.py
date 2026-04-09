from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from backend.app.schemas.migration import MigrationRecord
from backend.app.schemas.recommendation import RecommendationResponse


class ReportSummary(BaseModel):
    request_id: str
    recommended_approach: str
    confidence: str
    score: int
    rules_version: str
    why: list[str]


class RecommendationReport(BaseModel):
    report_id: str
    request_id: str
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    format: str = "json"
    summary: ReportSummary
    migration: MigrationRecord
    recommendation: RecommendationResponse
