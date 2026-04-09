from fastapi import APIRouter

from backend.app.core.config import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "backend",
        "version": settings.app_version,
        "environment": settings.app_env,
    }
