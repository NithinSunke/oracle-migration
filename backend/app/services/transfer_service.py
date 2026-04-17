from __future__ import annotations

from datetime import datetime, timezone
from backend.app.core.config import settings

from backend.app.adapters.oracle import (
    OracleDataPumpAdapter,
    OracleDataPumpError,
    OracleDataPumpExecutionDisabledError,
    OracleDataPumpExecutionFailedError,
)
from backend.app.schemas.transfer import (
    DataPumpCapabilitiesResponse,
    DataPumpConnectivityDiagnosticsRequest,
    DataPumpConnectivityDiagnosticsResponse,
    DataPumpJobCreate,
    DataPumpJobListResponse,
    DataPumpJobPurgeResponse,
    DataPumpJobRecord,
)
from backend.app.services.persistence_service import persistence_service
from backend.app.workers.celery_app import celery_app


class DataPumpTransferService:
    task_name = "transfer.datapump.execute"

    def __init__(self, adapter: OracleDataPumpAdapter | None = None) -> None:
        self._adapter = adapter or OracleDataPumpAdapter()

    def create_job(self, request: DataPumpJobCreate) -> DataPumpJobRecord:
        return self._queue_job(request)

    def _queue_job(
        self,
        request: DataPumpJobCreate,
        *,
        retry_of_job_id: str | None = None,
    ) -> DataPumpJobRecord:
        if (
            request.operation == "IMPORT"
            and request.options.transfer_dump_files
            and not request.dry_run
        ):
            raise ValueError(
                "Automatic dump-file transfer from source to target is not implemented yet. "
                "Leave 'Transfer dump file from source to target before import' unchecked when the dump file is already available on the target side."
            )

        if not request.dry_run:
            try:
                self._adapter.ensure_execution_ready(request)
            except OracleDataPumpExecutionDisabledError as exc:
                raise ValueError(str(exc)) from exc

        record = persistence_service.create_datapump_job(
            request,
            retry_of_job_id=retry_of_job_id,
        )
        job = celery_app.send_task(
            self.task_name,
            kwargs={
                "job_id": request.job_id,
                "payload": request.to_runtime_payload(),
            },
        )
        return persistence_service.update_datapump_job(
            request.job_id,
            task_id=job.id,
        )

    def retry_job(self, job_id: str) -> DataPumpJobRecord:
        existing = persistence_service.get_datapump_job(job_id)
        if existing is None:
            raise ValueError(f"Data Pump job '{job_id}' was not found.")
        if existing.status != "FAILED":
            raise ValueError("Only failed Data Pump jobs can be retried.")

        request = DataPumpJobCreate(
            request_id=existing.request_id,
            job_name=(existing.job_name or existing.job_id) + " retry",
            operation=existing.operation,
            scope=existing.scope,
            dry_run=existing.dry_run,
            source_connection=existing.source_connection,
            target_connection=existing.target_connection,
            options=existing.options,
        )
        return self._queue_job(request, retry_of_job_id=existing.job_id)

    def get_job(self, job_id: str) -> DataPumpJobRecord | None:
        return persistence_service.get_datapump_job(job_id)

    def list_jobs(self, limit: int = 25) -> DataPumpJobListResponse:
        items = persistence_service.list_datapump_jobs(limit=limit)
        return DataPumpJobListResponse(items=items, total=len(items))

    def purge_jobs(self) -> DataPumpJobPurgeResponse:
        purged_job_ids, skipped_active_job_ids, preserved_recent_count = (
            persistence_service.purge_datapump_jobs()
        )
        return DataPumpJobPurgeResponse(
            purged_job_ids=purged_job_ids,
            purged_count=len(purged_job_ids),
            preserved_recent_count=preserved_recent_count,
            skipped_active_job_ids=skipped_active_job_ids,
            skipped_active_count=len(skipped_active_job_ids),
        )

    def get_capabilities(self) -> DataPumpCapabilitiesResponse:
        runtime = self._adapter.get_runtime_capabilities()
        if runtime["actual_run_ready"]:
            if runtime["resolved_backend"] == "db_api":
                note = (
                    "Live Data Pump execution is ready through DBMS_DATAPUMP. "
                    "The worker will submit jobs through the Oracle connection instead of local expdp/impdp binaries. "
                    "Direct OCI Object Storage import actual-runs require a CLI impdp backend in the worker runtime."
                )
            else:
                note = (
                    "Live Data Pump execution is ready through the local expdp/impdp runtime in this worker."
                )
        else:
            note = (
                "Live Data Pump execution is not ready in this runtime yet. Customers can still switch between dry-run and actual-run in the UI, but actual-run requests are blocked until at least one execution backend is available."
            )
        return DataPumpCapabilitiesResponse(
            execution_enabled=settings.datapump_enabled,
            actual_run_ready=bool(runtime["actual_run_ready"]),
            execution_backend=runtime["execution_backend"],
            resolved_backend=runtime["resolved_backend"],
            cli_available=bool(runtime["cli_available"]),
            db_api_available=bool(runtime["db_api_available"]),
            expdp_path=settings.datapump_expdp_path,
            impdp_path=settings.datapump_impdp_path,
            work_dir=settings.datapump_work_dir,
            blockers=list(runtime["blockers"]),
            note=note,
        )

    def run_connectivity_diagnostics(
        self,
        request: DataPumpConnectivityDiagnosticsRequest,
    ) -> DataPumpConnectivityDiagnosticsResponse:
        return self._adapter.run_connectivity_diagnostics(
            source_connection=request.source_connection,
            target_connection=request.target_connection,
            object_storage=request.object_storage,
        )

    def run_job(self, job_id: str, payload: dict[str, object]) -> DataPumpJobRecord:
        started_at = datetime.now(timezone.utc)
        persistence_service.update_datapump_job(
            job_id,
            status="RUNNING",
            started_at=started_at,
        )
        request = DataPumpJobCreate(**payload)

        try:
            result_payload = self._adapter.execute_job(request)
        except OracleDataPumpExecutionFailedError as exc:
            result_payload = dict(exc.result_payload)
            failure_analysis = self._adapter.analyze_failure(result_payload)
            if failure_analysis is not None:
                result_payload["failure_analysis"] = failure_analysis.model_dump(mode="json")
            return persistence_service.update_datapump_job(
                job_id,
                status="FAILED",
                result_payload=result_payload,
                error_message=str(exc),
                completed_at=datetime.now(timezone.utc),
            )
        except OracleDataPumpError as exc:
            result_payload = {
                "output_excerpt": [str(exc)],
                "output_log": [str(exc)],
                "oracle_log_lines": [],
                "artifact_paths": [],
            }
            failure_analysis = self._adapter.analyze_failure(result_payload)
            if failure_analysis is not None:
                result_payload["failure_analysis"] = failure_analysis.model_dump(mode="json")
            return persistence_service.update_datapump_job(
                job_id,
                status="FAILED",
                result_payload=result_payload,
                error_message=str(exc),
                completed_at=datetime.now(timezone.utc),
            )

        completed_status = "PLANNED" if request.dry_run else "SUCCEEDED"
        return persistence_service.update_datapump_job(
            job_id,
            status=completed_status,
            result_payload=result_payload,
            completed_at=datetime.now(timezone.utc),
            error_message=None,
        )


datapump_transfer_service = DataPumpTransferService()
