from fastapi import APIRouter, HTTPException, status

from backend.app.schemas.job import (
    RecommendationJobCreateResponse,
    RecommendationJobStatusResponse,
)
from backend.app.schemas.migration import MigrationCreate
from backend.app.schemas.recommendation import RecommendationResponse
from backend.app.services.job_service import recommendation_job_service
from backend.app.services.recommendation_service import recommendation_service

router = APIRouter()


@router.post("", response_model=RecommendationResponse, status_code=status.HTTP_201_CREATED)
async def create_recommendation(
    request: MigrationCreate,
) -> RecommendationResponse:
    return recommendation_service.create(request)


@router.post(
    "/jobs",
    response_model=RecommendationJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_recommendation_job(
    request: MigrationCreate,
) -> RecommendationJobCreateResponse:
    return recommendation_job_service.create(request)


@router.get("/jobs/{task_id}", response_model=RecommendationJobStatusResponse)
async def get_recommendation_job_status(task_id: str) -> RecommendationJobStatusResponse:
    return recommendation_job_service.get_status(task_id)


@router.get("/{request_id}", response_model=RecommendationResponse)
async def get_recommendation(request_id: str) -> RecommendationResponse:
    recommendation = recommendation_service.get(request_id)
    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recommendation for '{request_id}' was not found.",
        )
    return recommendation
