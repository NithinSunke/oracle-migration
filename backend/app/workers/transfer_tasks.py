from __future__ import annotations

from backend.app.services.transfer_service import datapump_transfer_service
from backend.app.workers.celery_app import celery_app


@celery_app.task(name="transfer.datapump.execute")
def execute_datapump_job(job_id: str, payload: dict) -> dict[str, object]:
    record = datapump_transfer_service.run_job(job_id, payload)
    return {
        "job_id": record.job_id,
        "status": record.status,
        "error_message": record.error_message,
    }
