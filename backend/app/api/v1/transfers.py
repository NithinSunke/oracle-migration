from fastapi import APIRouter, HTTPException, Query, status

from backend.app.schemas.transfer import (
    DataPumpCapabilitiesResponse,
    DataPumpConnectivityDiagnosticsRequest,
    DataPumpConnectivityDiagnosticsResponse,
    DataPumpJobCreate,
    DataPumpJobListResponse,
    DataPumpJobPurgeResponse,
    DataPumpJobRecord,
)
from backend.app.services.transfer_service import datapump_transfer_service

router = APIRouter()


@router.get("/datapump/capabilities", response_model=DataPumpCapabilitiesResponse)
async def get_datapump_capabilities() -> DataPumpCapabilitiesResponse:
    return datapump_transfer_service.get_capabilities()


@router.post(
    "/datapump/diagnostics",
    response_model=DataPumpConnectivityDiagnosticsResponse,
)
async def run_datapump_connectivity_diagnostics(
    request: DataPumpConnectivityDiagnosticsRequest,
) -> DataPumpConnectivityDiagnosticsResponse:
    return datapump_transfer_service.run_connectivity_diagnostics(request)


@router.post(
    "/datapump/jobs",
    response_model=DataPumpJobRecord,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_datapump_job(request: DataPumpJobCreate) -> DataPumpJobRecord:
    try:
        return datapump_transfer_service.create_job(request)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error


@router.get("/datapump/jobs", response_model=DataPumpJobListResponse)
async def list_datapump_jobs(
    limit: int = Query(default=25, ge=1, le=100),
) -> DataPumpJobListResponse:
    return datapump_transfer_service.list_jobs(limit=limit)


@router.delete("/datapump/jobs/history", response_model=DataPumpJobPurgeResponse)
async def purge_datapump_job_history() -> DataPumpJobPurgeResponse:
    return datapump_transfer_service.purge_jobs()


@router.get("/datapump/jobs/{job_id}", response_model=DataPumpJobRecord)
async def get_datapump_job(job_id: str) -> DataPumpJobRecord:
    record = datapump_transfer_service.get_job(job_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Data Pump job '{job_id}' was not found.",
        )
    return record


@router.post("/datapump/jobs/{job_id}/retry", response_model=DataPumpJobRecord)
async def retry_datapump_job(job_id: str) -> DataPumpJobRecord:
    try:
        return datapump_transfer_service.retry_job(job_id)
    except ValueError as error:
        detail = str(error)
        status_code = status.HTTP_404_NOT_FOUND if "was not found" in detail else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=detail) from error
