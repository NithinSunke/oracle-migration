from __future__ import annotations

from uuid import uuid4

from celery.result import AsyncResult

from backend.app.core.config import settings
from backend.app.schemas.job import (
    RecommendationJobCreateResponse,
    RecommendationJobStatusResponse,
)
from backend.app.schemas.migration import MigrationCreate
from backend.app.services.persistence_service import persistence_service
from backend.app.workers.celery_app import celery_app

_EAGER_JOB_CACHE: dict[str, RecommendationJobStatusResponse] = {}


class RecommendationJobService:
    task_name = "recommendation.generate"

    def create(self, request: MigrationCreate) -> RecommendationJobCreateResponse:
        request_record = persistence_service.save_migration_request(request)
        payload = request.to_runtime_payload()

        if settings.task_always_eager:
            from backend.app.workers.recommendation_tasks import generate_recommendation

            task_id = str(uuid4())
            try:
                result_payload = generate_recommendation.run(payload=payload)
                status = "SUCCESS"
                error = None
            except Exception as exc:
                result_payload = None
                status = "FAILURE"
                error = str(exc)

            _EAGER_JOB_CACHE[task_id] = RecommendationJobStatusResponse(
                task_id=task_id,
                request_id=request_record.request_id,
                status=status,
                result=result_payload,
                error=error,
            )
        else:
            job = celery_app.send_task(
                self.task_name,
                kwargs={"payload": payload},
            )
            task_id = job.id

        return RecommendationJobCreateResponse(
            task_id=task_id,
            request_id=request_record.request_id,
            status="queued",
            status_url=f"/api/v1/recommendations/jobs/{task_id}",
        )

    def get_status(self, task_id: str) -> RecommendationJobStatusResponse:
        if settings.task_always_eager:
            cached = _EAGER_JOB_CACHE.get(task_id)
            if cached is not None:
                return cached
            return RecommendationJobStatusResponse(
                task_id=task_id,
                request_id=None,
                status="PENDING",
                result=None,
                error=None,
            )

        job = AsyncResult(task_id, app=celery_app)
        payload = job.result if isinstance(job.result, dict) else None
        error = None if job.successful() or job.result is None else str(job.result)
        request_id = None
        if isinstance(payload, dict):
            request_id = payload.get("request_id")

        return RecommendationJobStatusResponse(
            task_id=task_id,
            request_id=request_id,
            status=job.state,
            result=payload,
            error=error,
        )


recommendation_job_service = RecommendationJobService()
