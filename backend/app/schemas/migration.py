from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, SecretStr

from backend.app.schemas.oracle import (
    MigrationCompatibilityAssessment,
    OracleSourceMetadata,
    OracleTargetMetadata,
)


class SourceDetails(BaseModel):
    oracle_version: str | None = None
    deployment_type: str | None = None
    platform: str | None = None
    storage_type: str | None = None
    database_size_gb: float | None = Field(default=None, ge=0)
    largest_table_gb: float | None = Field(default=None, ge=0)
    daily_change_rate_gb: float | None = Field(default=None, ge=0)
    peak_redo_mb_per_sec: float | None = Field(default=None, ge=0)
    character_set: str | None = None
    tde_enabled: bool = False
    rac_enabled: bool = False
    dataguard_enabled: bool = False
    archivelog_enabled: bool = False


class TargetDetails(BaseModel):
    oracle_version: str | None = None
    deployment_type: str | None = None
    platform: str | None = None
    storage_type: str | None = None
    target_is_exadata: bool = False
    same_endian: bool = True


class ScopeDetails(BaseModel):
    migration_scope: Literal["FULL_DATABASE", "SCHEMA", "TABLE", "SUBSET"] = (
        "FULL_DATABASE"
    )
    schema_count: int | None = Field(default=None, ge=0)
    schema_names: list[str] = Field(default_factory=list)
    need_schema_remap: bool = False
    need_tablespace_remap: bool = False
    need_reorg: bool = False
    subset_only: bool = False


class BusinessDetails(BaseModel):
    downtime_window_minutes: int = Field(ge=0)
    fallback_required: bool = False
    near_zero_downtime_required: bool = False
    regulated_workload: bool = False


class ConnectivityDetails(BaseModel):
    network_bandwidth_mbps: int | None = Field(default=None, ge=0)
    direct_host_connectivity: bool = False
    shared_storage_available: bool = False


class FeatureDetails(BaseModel):
    need_version_upgrade: bool = False
    need_cross_platform_move: bool = False
    need_non_cdb_to_pdb_conversion: bool = False
    goldengate_license_available: bool = False
    zdm_supported_target: bool = False


class OracleConnectionConfig(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(default=1521, ge=1, le=65535)
    service_name: str = Field(min_length=1)
    username: str = Field(min_length=1)
    password: SecretStr | None = None
    password_configured: bool = False
    mode: Literal["thin", "thick"] = "thin"
    sysdba: bool = False
    wallet_location: str | None = None

    def has_secret(self) -> bool:
        if self.password is None:
            return False
        return bool(self.password.get_secret_value())

    def to_runtime_payload(self) -> dict[str, object]:
        return {
            "host": self.host,
            "port": self.port,
            "service_name": self.service_name,
            "username": self.username,
            "password": self.password.get_secret_value() if self.password else None,
            "password_configured": self.password_configured or self.has_secret(),
            "mode": self.mode,
            "sysdba": self.sysdba,
            "wallet_location": self.wallet_location,
        }

    def to_storage_payload(self) -> dict[str, object]:
        return {
            "host": self.host,
            "port": self.port,
            "service_name": self.service_name,
            "username": self.username,
            "password": None,
            "password_configured": self.password_configured or self.has_secret(),
            "mode": self.mode,
            "sysdba": self.sysdba,
            "wallet_location": self.wallet_location,
        }


class MetadataCollectionOptions(BaseModel):
    enabled: bool = False
    prefer_collected_values: bool = True
    source_connection: OracleConnectionConfig | None = None
    target_connection: OracleConnectionConfig | None = None

    def to_runtime_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "enabled": self.enabled,
            "prefer_collected_values": self.prefer_collected_values,
        }
        if self.source_connection is not None:
            payload["source_connection"] = self.source_connection.to_runtime_payload()
        if self.target_connection is not None:
            payload["target_connection"] = self.target_connection.to_runtime_payload()
        return payload

    def to_storage_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "enabled": self.enabled,
            "prefer_collected_values": self.prefer_collected_values,
        }
        if self.source_connection is not None:
            payload["source_connection"] = self.source_connection.to_storage_payload()
        if self.target_connection is not None:
            payload["target_connection"] = self.target_connection.to_storage_payload()
        return payload


class MigrationCreate(BaseModel):
    request_id: str = Field(default_factory=lambda: f"MIG-{uuid4().hex[:12].upper()}")
    source: SourceDetails
    target: TargetDetails
    scope: ScopeDetails
    business: BusinessDetails
    connectivity: ConnectivityDetails
    features: FeatureDetails
    metadata_collection: MetadataCollectionOptions | None = None
    source_metadata: OracleSourceMetadata | None = None
    target_metadata: OracleTargetMetadata | None = None
    migration_validation: MigrationCompatibilityAssessment | None = None

    def to_runtime_payload(self) -> dict[str, object]:
        payload = self.model_dump(mode="json", exclude_none=True)
        if self.metadata_collection is not None:
            payload["metadata_collection"] = self.metadata_collection.to_runtime_payload()
        return payload

    def to_storage_payload(self) -> dict[str, object]:
        payload = self.model_dump(mode="json", exclude_none=True)
        if self.metadata_collection is not None:
            payload["metadata_collection"] = self.metadata_collection.to_storage_payload()
        return payload


class MigrationRecord(MigrationCreate):
    source_metadata: OracleSourceMetadata | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    status: Literal["draft", "submitted"] = "submitted"
