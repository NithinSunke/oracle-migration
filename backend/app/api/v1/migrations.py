from fastapi import APIRouter, HTTPException, status

from backend.app.schemas.migration import MigrationCreate, MigrationRecord
from backend.app.services.migration_service import migration_service

router = APIRouter()


@router.post("", response_model=MigrationRecord, status_code=status.HTTP_201_CREATED)
async def create_migration(request: MigrationCreate) -> MigrationRecord:
    return migration_service.create(request)


@router.get("/{request_id}", response_model=MigrationRecord)
async def get_migration(request_id: str) -> MigrationRecord:
    migration = migration_service.get(request_id)
    if migration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Migration request '{request_id}' was not found.",
        )
    return migration
