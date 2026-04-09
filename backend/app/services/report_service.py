from __future__ import annotations

import json

from backend.app.schemas.report import RecommendationReport, ReportSummary
from backend.app.services.persistence_service import persistence_service


class ReportService:
    def get(self, request_id: str) -> RecommendationReport | None:
        migration = persistence_service.get_migration_request(request_id)
        recommendation = persistence_service.get_latest_recommendation(request_id)
        if migration is None or recommendation is None:
            return None

        return RecommendationReport(
            report_id=f"report-{request_id}",
            request_id=request_id,
            summary=ReportSummary(
                request_id=request_id,
                recommended_approach=recommendation.recommended_approach,
                confidence=recommendation.confidence,
                score=recommendation.score,
                rules_version=recommendation.rules_version,
                why=recommendation.why,
            ),
            migration=migration,
            recommendation=recommendation,
        )

    def render_json(self, request_id: str) -> str | None:
        report = self.get(request_id)
        if report is None:
            return None
        return json.dumps(report.model_dump(mode="json"), indent=2)


report_service = ReportService()
