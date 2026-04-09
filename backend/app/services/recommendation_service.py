from pathlib import Path

from backend.app.schemas.migration import MigrationCreate
from backend.app.schemas.recommendation import RecommendationResponse
from backend.app.rule_engine import RecommendationEngine
from backend.app.services.oracle_metadata_service import oracle_metadata_service
from backend.app.services.persistence_service import persistence_service


class RecommendationService:
    def __init__(self) -> None:
        config_path = Path(__file__).resolve().parents[3] / "config" / "migration-rules.example.json"
        self._engine = RecommendationEngine(config_path)

    def create(self, request: MigrationCreate) -> RecommendationResponse:
        enriched_request, metadata_summary = oracle_metadata_service.enrich_request(request)
        recommendation = self._engine.recommend(enriched_request)

        manual_review_flags = list(recommendation.manual_review_flags)
        if metadata_summary is not None and metadata_summary.status == "FAILED":
            manual_review_flags.append(
                "Oracle metadata collection failed; recommendation was generated from submitted inputs only."
            )

        recommendation = recommendation.model_copy(
            update={
                "manual_review_flags": list(dict.fromkeys(manual_review_flags)),
                "metadata_enrichment": metadata_summary,
            }
        )
        return persistence_service.save_recommendation(
            enriched_request,
            recommendation,
            source_metadata=metadata_summary.source if metadata_summary else None,
        )

    def get(self, request_id: str) -> RecommendationResponse | None:
        return persistence_service.get_latest_recommendation(request_id)


recommendation_service = RecommendationService()
