from fastapi import APIRouter, Query

from backend.app.schemas.history import HistoryListResponse
from backend.app.services.history_service import history_service

router = APIRouter()


@router.get("", response_model=HistoryListResponse)
async def list_history(limit: int = Query(default=50, ge=1, le=200)) -> HistoryListResponse:
    return history_service.list(limit=limit)
