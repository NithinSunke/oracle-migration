from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from backend.app.schemas.migration import OracleConnectionConfig


DataPumpOperation = Literal["EXPORT", "IMPORT"]
DataPumpScope = Literal["FULL", "SCHEMA"]
DataPumpJobStatus = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "PLANNED"]
DataPumpExecutionBackend = Literal["auto", "cli", "db_api"]
DataPumpResolvedBackend = Literal["cli", "db_api"]
DataPumpStorageType = Literal["LOCAL_FS", "OCI_OBJECT_STORAGE"]


class SchemaRemap(BaseModel):
    source_schema: str = Field(min_length=1)
    target_schema: str = Field(min_length=1)


class DataPumpJobOptions(BaseModel):
    class ObjectStorageConfig(BaseModel):
        credential_name: str = Field(min_length=1)
        region: str = Field(min_length=1)
        namespace: str = Field(min_length=1)
        bucket: str = Field(min_length=1)
        object_prefix: str | None = None

    directory_object: str = Field(min_length=1)
    dump_file: str = Field(min_length=1)
    log_file: str | None = None
    storage_type: DataPumpStorageType = "LOCAL_FS"
    object_storage: ObjectStorageConfig | None = None
    transfer_dump_files: bool = False
    parallel: int = Field(default=1, ge=1, le=32)
    schemas: list[str] = Field(default_factory=list)
    exclude_statistics: bool = False
    compression_enabled: bool = False
    table_exists_action: Literal["SKIP", "APPEND", "TRUNCATE", "REPLACE"] = "SKIP"
    remap_schemas: list[SchemaRemap] = Field(default_factory=list)


class DataPumpCommandPreview(BaseModel):
    backend: DataPumpResolvedBackend = "cli"
    executable: str
    command_line: str
    parameter_lines: list[str] = Field(default_factory=list)


class DataPumpJobCreate(BaseModel):
    job_id: str = Field(default_factory=lambda: f"DPT-{uuid4().hex[:12].upper()}")
    request_id: str | None = None
    job_name: str | None = None
    operation: DataPumpOperation
    scope: DataPumpScope
    dry_run: bool = False
    source_connection: OracleConnectionConfig | None = None
    target_connection: OracleConnectionConfig | None = None
    options: DataPumpJobOptions

    @model_validator(mode="after")
    def validate_payload(self) -> "DataPumpJobCreate":
        if self.scope == "SCHEMA" and not self.options.schemas:
            raise ValueError("Provide at least one schema when the Data Pump scope is SCHEMA.")

        if self.operation == "IMPORT" and self.target_connection is None:
            raise ValueError("Target Oracle connection is required for Data Pump imports.")

        if self.operation == "EXPORT" and self.options.remap_schemas:
            raise ValueError("Schema remapping is only supported for Data Pump imports.")

        if self.operation == "EXPORT" and self.source_connection is None:
            raise ValueError("Source Oracle connection is required for Data Pump exports.")

        if self.operation == "IMPORT" and self.options.transfer_dump_files and self.source_connection is None:
            raise ValueError(
                "Source Oracle connection is required when import requests dump-file transfer from source to target."
            )

        if self.options.storage_type == "OCI_OBJECT_STORAGE" and self.options.object_storage is None:
            raise ValueError(
                "OCI Object Storage details are required when storage type is OCI_OBJECT_STORAGE."
            )

        if self.options.storage_type == "OCI_OBJECT_STORAGE" and self.options.transfer_dump_files:
            raise ValueError(
                "Dump-file transfer is not used when storage type is OCI_OBJECT_STORAGE because export/import should work directly against Object Storage."
            )

        if (
            self.operation == "IMPORT"
            and self.options.storage_type == "OCI_OBJECT_STORAGE"
            and self.options.object_storage is not None
            and self.options.object_storage.object_prefix is not None
            and self.options.object_storage.object_prefix.strip()
        ):
            raise ValueError(
                "Direct OCI Object Storage imports require the dump object to be stored without a nested object prefix. "
                "Use a flat object name at the bucket root, or clear Object Prefix before importing."
            )

        return self

    def to_runtime_payload(self) -> dict[str, object]:
        payload = self.model_dump(mode="json")
        if self.source_connection is not None:
            payload["source_connection"] = self.source_connection.to_runtime_payload()
        if self.target_connection is not None:
            payload["target_connection"] = self.target_connection.to_runtime_payload()
        return payload

    def to_storage_payload(self) -> dict[str, object]:
        payload = self.model_dump(mode="json")
        if self.source_connection is not None:
            payload["source_connection"] = self.source_connection.to_storage_payload()
        if self.target_connection is not None:
            payload["target_connection"] = self.target_connection.to_storage_payload()
        return payload


class DataPumpJobRecord(BaseModel):
    job_id: str
    request_id: str | None = None
    task_id: str | None = None
    job_name: str | None = None
    operation: DataPumpOperation
    scope: DataPumpScope
    status: DataPumpJobStatus
    dry_run: bool
    source_connection: dict | None = None
    target_connection: dict | None = None
    options: DataPumpJobOptions
    command_preview: DataPumpCommandPreview | None = None
    output_excerpt: list[str] = Field(default_factory=list)
    output_log: list[str] = Field(default_factory=list)
    oracle_log_lines: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None


class DataPumpJobListResponse(BaseModel):
    items: list[DataPumpJobRecord]
    total: int


class DataPumpJobPurgeResponse(BaseModel):
    purged_job_ids: list[str] = Field(default_factory=list)
    purged_count: int = 0
    skipped_active_job_ids: list[str] = Field(default_factory=list)
    skipped_active_count: int = 0


class DataPumpCapabilitiesResponse(BaseModel):
    execution_enabled: bool
    actual_run_ready: bool
    execution_backend: DataPumpExecutionBackend
    resolved_backend: DataPumpResolvedBackend | None = None
    cli_available: bool = False
    db_api_available: bool = False
    expdp_path: str
    impdp_path: str
    work_dir: str
    blockers: list[str] = Field(default_factory=list)
    note: str
