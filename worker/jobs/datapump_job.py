from __future__ import annotations

from backend.app.schemas.transfer import DataPumpJobCreate
from backend.app.services.transfer_service import datapump_transfer_service


def run_datapump_job(job_id: str, payload: dict[str, object]) -> dict[str, object]:
    request = DataPumpJobCreate(**payload)
    record = datapump_transfer_service.run_job(job_id, request.model_dump(mode="json"))
    return {
        "job_id": record.job_id,
        "status": record.status,
        "error_message": record.error_message,
    }
