from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HistoryItem(BaseModel):
    request_id: str
    created_at: datetime
    status: str
    migration_scope: str
    source_version: str | None = None
    target_version: str | None = None
    database_size_gb: float | None = None
    recommended_approach: str | None = None
    confidence: str | None = None
    score: int | None = None
    rules_version: str | None = None
    recommendation_generated_at: datetime | None = None


class HistoryListResponse(BaseModel):
    items: list[HistoryItem]
    total: int
