from __future__ import annotations

from typing import Any

from backend.app.schemas.migration import MigrationCreate


def normalize_request(request: MigrationCreate) -> dict[str, Any]:
    return request.model_dump(mode="python", exclude={"metadata_collection"})
