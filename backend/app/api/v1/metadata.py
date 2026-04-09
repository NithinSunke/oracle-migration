from fastapi import APIRouter, File, HTTPException, UploadFile, status

from backend.app.schemas.migration import MigrationCreate
from backend.app.schemas.oracle import (
    MetadataEnrichmentSummary,
    MigrationCompatibilityAssessment,
)
from backend.app.services.oracle_html_import_service import oracle_html_import_service
from backend.app.services.oracle_metadata_service import oracle_metadata_service

router = APIRouter()


@router.post("/test", response_model=MetadataEnrichmentSummary)
async def test_source_metadata_connection(
    request: MigrationCreate,
) -> MetadataEnrichmentSummary:
    return oracle_metadata_service.collect_source_metadata(request)


@router.post("/import-html", response_model=MetadataEnrichmentSummary)
async def import_source_metadata_html(
    file: UploadFile = File(...),
) -> MetadataEnrichmentSummary:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select an Oracle source metadata HTML file to upload.",
        )

    filename = file.filename.lower()
    if not filename.endswith((".html", ".htm")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .html or .htm source metadata reports are supported.",
        )

    content = await file.read()
    return oracle_html_import_service.import_html(content, file.filename)


@router.post("/validate-migration", response_model=MigrationCompatibilityAssessment)
async def validate_source_to_target_migration(
    request: MigrationCreate,
) -> MigrationCompatibilityAssessment:
    return oracle_metadata_service.validate_source_to_target(request)
