from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil

from sqlalchemy import select

from backend.app.core.database import session_scope
from backend.app.core.config import settings
from backend.app.models.persistence import (
    DataPumpJobModel,
    MigrationRequestModel,
    RecommendationAuditModel,
    RecommendationResultModel,
)
from backend.app.schemas.history import HistoryItem
from backend.app.schemas.migration import MigrationCreate, MigrationRecord
from backend.app.schemas.oracle import (
    MigrationCompatibilityAssessment,
    OracleSourceMetadata,
    OracleTargetMetadata,
)
from backend.app.schemas.recommendation import RecommendationResponse
from backend.app.schemas.transfer import (
    DataPumpCommandPreview,
    DataPumpJobCreate,
    DataPumpJobRecord,
)


class PersistenceService:
    @staticmethod
    def _normalize_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def save_migration_request(
        self,
        request: MigrationCreate,
        source_metadata: OracleSourceMetadata | None = None,
        target_metadata: OracleTargetMetadata | None = None,
        migration_validation: MigrationCompatibilityAssessment | None = None,
    ) -> MigrationRecord:
        payload = request.to_storage_payload()
        source_metadata_payload = (
            source_metadata.model_dump(mode="json", exclude_none=True)
            if source_metadata is not None
            else (
                request.source_metadata.model_dump(mode="json", exclude_none=True)
                if request.source_metadata is not None
                else None
            )
        )
        target_metadata_payload = (
            target_metadata.model_dump(mode="json", exclude_none=True)
            if target_metadata is not None
            else (
                request.target_metadata.model_dump(mode="json", exclude_none=True)
                if request.target_metadata is not None
                else None
            )
        )
        validation_payload = (
            migration_validation.model_dump(mode="json", exclude_none=True)
            if migration_validation is not None
            else (
                request.migration_validation.model_dump(mode="json", exclude_none=True)
                if request.migration_validation is not None
                else None
            )
        )

        with session_scope() as session:
            record = session.get(MigrationRequestModel, request.request_id)
            if record is None:
                record = MigrationRequestModel(
                    request_id=request.request_id,
                    source_payload=payload["source"],
                    target_payload=payload["target"],
                    scope_payload=payload["scope"],
                    business_payload=payload["business"],
                    connectivity_payload=payload["connectivity"],
                    features_payload=payload["features"],
                    metadata_collection_payload=payload.get("metadata_collection", {}),
                    source_metadata_payload=source_metadata_payload or {},
                    target_metadata_payload=target_metadata_payload or {},
                    migration_validation_payload=validation_payload or {},
                    status="submitted",
                )
                session.add(record)
            else:
                record.source_payload = payload["source"]
                record.target_payload = payload["target"]
                record.scope_payload = payload["scope"]
                record.business_payload = payload["business"]
                record.connectivity_payload = payload["connectivity"]
                record.features_payload = payload["features"]
                record.metadata_collection_payload = payload.get("metadata_collection", {})
                if source_metadata_payload is not None:
                    record.source_metadata_payload = source_metadata_payload
                if target_metadata_payload is not None:
                    record.target_metadata_payload = target_metadata_payload
                if validation_payload is not None:
                    record.migration_validation_payload = validation_payload
                record.status = "submitted"
            session.flush()

            return MigrationRecord(
                request_id=record.request_id,
                source=record.source_payload,
                target=record.target_payload,
                scope=record.scope_payload,
                business=record.business_payload,
                connectivity=record.connectivity_payload,
                features=record.features_payload,
                metadata_collection=record.metadata_collection_payload or None,
                source_metadata=record.source_metadata_payload or None,
                target_metadata=record.target_metadata_payload or None,
                migration_validation=record.migration_validation_payload or None,
                created_at=self._normalize_utc(record.created_at),
                status=record.status,
            )

    def get_migration_request(self, request_id: str) -> MigrationRecord | None:
        with session_scope() as session:
            record = session.get(MigrationRequestModel, request_id)
            if record is None:
                return None

            return MigrationRecord(
                request_id=record.request_id,
                source=record.source_payload,
                target=record.target_payload,
                scope=record.scope_payload,
                business=record.business_payload,
                connectivity=record.connectivity_payload,
                features=record.features_payload,
                metadata_collection=record.metadata_collection_payload or None,
                source_metadata=record.source_metadata_payload or None,
                target_metadata=record.target_metadata_payload or None,
                migration_validation=record.migration_validation_payload or None,
                created_at=self._normalize_utc(record.created_at),
                status=record.status,
            )

    def save_recommendation(
        self,
        request: MigrationCreate,
        recommendation: RecommendationResponse,
        source_metadata: OracleSourceMetadata | None = None,
        target_metadata: OracleTargetMetadata | None = None,
        migration_validation: MigrationCompatibilityAssessment | None = None,
    ) -> RecommendationResponse:
        request_record = self.save_migration_request(
            request,
            source_metadata=source_metadata,
            target_metadata=target_metadata,
            migration_validation=migration_validation,
        )
        request_payload = request.to_storage_payload()
        response_payload = recommendation.model_dump(mode="json")

        with session_scope() as session:
            result = RecommendationResultModel(
                request_id=request_record.request_id,
                recommended_approach=recommendation.recommended_approach,
                confidence=recommendation.confidence,
                score=recommendation.score,
                rules_version=recommendation.rules_version,
                request_payload=request_payload,
                response_payload=response_payload,
                generated_at=recommendation.generated_at,
            )
            session.add(result)
            session.flush()

            audit = RecommendationAuditModel(
                request_id=request_record.request_id,
                recommendation_id=result.recommendation_id,
                recommended_approach=recommendation.recommended_approach,
                score=recommendation.score,
                rules_version=recommendation.rules_version,
                request_payload=request_payload,
                evaluation_payload=response_payload,
            )
            session.add(audit)

        return RecommendationResponse(**response_payload)

    def get_latest_recommendation(self, request_id: str) -> RecommendationResponse | None:
        with session_scope() as session:
            stmt = (
                select(RecommendationResultModel)
                .where(RecommendationResultModel.request_id == request_id)
                .order_by(RecommendationResultModel.generated_at.desc())
            )
            result = session.execute(stmt).scalars().first()
            if result is None:
                return None

            return RecommendationResponse(**result.response_payload)

    def list_history(self, limit: int = 50) -> list[HistoryItem]:
        with session_scope() as session:
            stmt = (
                select(MigrationRequestModel)
                .order_by(MigrationRequestModel.created_at.desc())
                .limit(limit)
            )
            requests = session.execute(stmt).scalars().all()
            items: list[HistoryItem] = []

            for request in requests:
                recommendation_stmt = (
                    select(RecommendationResultModel)
                    .where(RecommendationResultModel.request_id == request.request_id)
                    .order_by(RecommendationResultModel.generated_at.desc())
                )
                latest_recommendation = session.execute(recommendation_stmt).scalars().first()

                items.append(
                    HistoryItem(
                        request_id=request.request_id,
                        created_at=self._normalize_utc(request.created_at),
                        status=request.status,
                        migration_scope=str(
                            request.scope_payload.get("migration_scope", "UNKNOWN")
                        ),
                        source_version=request.source_payload.get("oracle_version"),
                        target_version=request.target_payload.get("oracle_version"),
                        database_size_gb=request.source_payload.get("database_size_gb"),
                        recommended_approach=(
                            latest_recommendation.recommended_approach
                            if latest_recommendation is not None
                            else None
                        ),
                        confidence=(
                            latest_recommendation.confidence
                            if latest_recommendation is not None
                            else None
                        ),
                        score=(
                            latest_recommendation.score
                            if latest_recommendation is not None
                            else None
                        ),
                        rules_version=(
                            latest_recommendation.rules_version
                            if latest_recommendation is not None
                            else None
                        ),
                        recommendation_generated_at=(
                            self._normalize_utc(latest_recommendation.generated_at)
                            if latest_recommendation is not None
                            else None
                        ),
                    )
                )

            return items

    def create_datapump_job(self, request: DataPumpJobCreate) -> DataPumpJobRecord:
        payload = request.to_storage_payload()

        with session_scope() as session:
            record = DataPumpJobModel(
                job_id=request.job_id,
                request_id=request.request_id,
                job_name=request.job_name,
                operation=request.operation,
                scope=request.scope,
                status="QUEUED",
                dry_run=request.dry_run,
                source_connection_payload=payload.get("source_connection") or {},
                target_connection_payload=payload.get("target_connection") or {},
                options_payload=payload["options"],
                result_payload={},
            )
            session.add(record)
            session.flush()
            return self._to_datapump_job_record(record)

    def update_datapump_job(
        self,
        job_id: str,
        *,
        task_id: str | None = None,
        status: str | None = None,
        result_payload: dict | None = None,
        error_message: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> DataPumpJobRecord:
        with session_scope() as session:
            record = session.get(DataPumpJobModel, job_id)
            if record is None:
                raise ValueError(f"Data Pump job '{job_id}' was not found.")

            if task_id is not None:
                record.task_id = task_id
            if status is not None:
                record.status = status
            if result_payload is not None:
                record.result_payload = result_payload
            if error_message is not None or status is not None:
                record.error_message = error_message
            if started_at is not None:
                record.started_at = started_at
            if completed_at is not None:
                record.completed_at = completed_at

            session.flush()
            return self._to_datapump_job_record(record)

    def get_datapump_job(self, job_id: str) -> DataPumpJobRecord | None:
        with session_scope() as session:
            record = session.get(DataPumpJobModel, job_id)
            if record is None:
                return None
            return self._to_datapump_job_record(record)

    def list_datapump_jobs(self, limit: int = 25) -> list[DataPumpJobRecord]:
        with session_scope() as session:
            stmt = (
                select(DataPumpJobModel)
                .order_by(DataPumpJobModel.created_at.desc())
                .limit(limit)
            )
            rows = session.execute(stmt).scalars().all()
            return [self._to_datapump_job_record(row) for row in rows]

    def purge_datapump_jobs(self) -> tuple[list[str], list[str]]:
        purged_job_ids: list[str] = []
        skipped_active_job_ids: list[str] = []

        with session_scope() as session:
            stmt = select(DataPumpJobModel).order_by(DataPumpJobModel.created_at.desc())
            rows = session.execute(stmt).scalars().all()

            for record in rows:
                if record.status in {"QUEUED", "RUNNING"}:
                    skipped_active_job_ids.append(record.job_id)
                    continue

                purged_job_ids.append(record.job_id)
                session.delete(record)

            session.flush()

        for job_id in purged_job_ids:
            self._cleanup_datapump_work_dir(job_id)

        return purged_job_ids, skipped_active_job_ids

    def _cleanup_datapump_work_dir(self, job_id: str) -> None:
        work_root = Path(settings.datapump_work_dir).resolve()
        candidate = (work_root / job_id).resolve()

        try:
            candidate.relative_to(work_root)
        except ValueError:
            return

        if candidate.exists():
            shutil.rmtree(candidate, ignore_errors=True)

    def _to_datapump_job_record(self, record: DataPumpJobModel) -> DataPumpJobRecord:
        command_preview_payload = record.result_payload.get("command_preview")
        command_preview = (
            DataPumpCommandPreview(**command_preview_payload)
            if command_preview_payload
            else None
        )
        return DataPumpJobRecord(
            job_id=record.job_id,
            request_id=record.request_id,
            task_id=record.task_id,
            job_name=record.job_name,
            operation=record.operation,
            scope=record.scope,
            status=record.status,
            dry_run=record.dry_run,
            source_connection=record.source_connection_payload,
            target_connection=record.target_connection_payload or None,
            options=record.options_payload,
            command_preview=command_preview,
            output_excerpt=record.result_payload.get("output_excerpt", []),
            output_log=record.result_payload.get(
                "output_log",
                record.result_payload.get("output_excerpt", []),
            ),
            oracle_log_lines=record.result_payload.get("oracle_log_lines", []),
            artifact_paths=record.result_payload.get("artifact_paths", []),
            error_message=record.error_message,
            created_at=self._normalize_utc(record.created_at),
            started_at=(
                self._normalize_utc(record.started_at)
                if record.started_at is not None
                else None
            ),
            completed_at=(
                self._normalize_utc(record.completed_at)
                if record.completed_at is not None
                else None
            ),
        )


persistence_service = PersistenceService()
