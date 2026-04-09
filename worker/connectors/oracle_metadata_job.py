from __future__ import annotations

from backend.app.schemas.migration import MigrationCreate
from backend.app.services.oracle_metadata_service import oracle_metadata_service


def run_oracle_metadata_job(payload: dict) -> dict[str, object]:
    request = MigrationCreate(**payload)
    result = oracle_metadata_service.collect_source_metadata(request)
    return result.model_dump(mode="json")
