"""API v1 package."""

from fastapi import APIRouter

from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.health import router as health_router
from backend.app.api.v1.history import router as history_router
from backend.app.api.v1.metadata import router as metadata_router
from backend.app.api.v1.migrations import router as migrations_router
from backend.app.api.v1.recommendations import router as recommendations_router
from backend.app.api.v1.reports import router as reports_router
from backend.app.api.v1.transfers import router as transfers_router

router = APIRouter()
router.include_router(auth_router, prefix="/auth", tags=["auth"])
router.include_router(health_router, tags=["health"])
router.include_router(history_router, prefix="/history", tags=["history"])
router.include_router(metadata_router, prefix="/metadata", tags=["metadata"])
router.include_router(migrations_router, prefix="/migrations", tags=["migrations"])
router.include_router(
    recommendations_router,
    prefix="/recommendations",
    tags=["recommendations"],
)
router.include_router(reports_router, prefix="/reports", tags=["reports"])
router.include_router(transfers_router, prefix="/transfers", tags=["transfers"])
