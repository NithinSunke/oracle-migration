from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


JobState = Literal["PENDING", "STARTED", "SUCCESS", "FAILURE", "RETRY"]


class RecommendationJobCreateResponse(BaseModel):
    task_id: str
    request_id: str
    status: Literal["queued"]
    status_url: str


class RecommendationJobStatusResponse(BaseModel):
    task_id: str
    request_id: str | None = None
    status: JobState
    result: dict[str, Any] | None = None
    error: str | None = None
