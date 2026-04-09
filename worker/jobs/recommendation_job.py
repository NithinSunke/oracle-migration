from __future__ import annotations

from backend.app.schemas.migration import MigrationCreate
from backend.app.services.recommendation_service import recommendation_service


def run_recommendation_job(payload: dict) -> dict[str, str | int]:
    request = MigrationCreate(**payload)
    recommendation = recommendation_service.create(request)
    return {
        "request_id": recommendation.request_id,
        "recommended_approach": recommendation.recommended_approach,
        "score": recommendation.score,
        "confidence": recommendation.confidence,
        "rules_version": recommendation.rules_version,
    }
