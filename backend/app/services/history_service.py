from backend.app.schemas.history import HistoryListResponse
from backend.app.services.persistence_service import persistence_service


class HistoryService:
    def list(self, limit: int = 50) -> HistoryListResponse:
        items = persistence_service.list_history(limit=limit)
        return HistoryListResponse(items=items, total=len(items))


history_service = HistoryService()
