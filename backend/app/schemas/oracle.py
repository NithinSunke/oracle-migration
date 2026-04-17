from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class OracleObjectInventorySummary(BaseModel):
    schema_count: int = Field(default=0, ge=0)
    total_objects: int = Field(default=0, ge=0)
    total_tables: int = Field(default=0, ge=0)
    total_indexes: int = Field(default=0, ge=0)
    total_views: int = Field(default=0, ge=0)
    total_materialized_views: int = Field(default=0, ge=0)
    total_sequences: int = Field(default=0, ge=0)
    total_procedures: int = Field(default=0, ge=0)
    total_functions: int = Field(default=0, ge=0)
    total_packages: int = Field(default=0, ge=0)
    total_triggers: int = Field(default=0, ge=0)
    invalid_object_count: int = Field(default=0, ge=0)


class OraclePdbInventoryEntry(BaseModel):
    name: str
    con_id: int = Field(ge=0)
    open_mode: str | None = None
    open_time: datetime | None = None
    service_names: list[str] = Field(default_factory=list)
    total_size_gb: float | None = Field(default=None, ge=0)


class OracleUserInventoryEntry(BaseModel):
    container_name: str
    container_type: Literal["CDB_ROOT", "PDB", "NON_CDB"] = "PDB"
    con_id: int = Field(ge=0)
    username: str
    user_type: str
    oracle_maintained: bool = False
    account_status: str | None = None
    created: datetime | None = None
    expiry_date: datetime | None = None
    profile: str | None = None
    password_versions: str | None = None
    default_tablespace: str | None = None
    temporary_tablespace: str | None = None


class OracleTablespaceInventoryEntry(BaseModel):
    container_name: str
    container_type: Literal["CDB_ROOT", "PDB", "NON_CDB"] = "PDB"
    con_id: int = Field(ge=0)
    tablespace_name: str
    contents: str | None = None
    extent_management: str | None = None
    segment_space_management: str | None = None
    bigfile: bool | None = None
    status: str | None = None
    block_size: int | None = Field(default=None, ge=0)
    used_mb: float | None = Field(default=None, ge=0)
    free_mb: float | None = Field(default=None, ge=0)
    total_mb: float | None = Field(default=None, ge=0)
    pct_free: float | None = None
    max_size_mb: float | None = Field(default=None, ge=0)
    encrypted: bool | None = None


class OracleInvalidObjectOwnerSummary(BaseModel):
    container_name: str
    container_type: Literal["CDB_ROOT", "PDB"] = "PDB"
    con_id: int = Field(ge=0)
    owner: str
    invalid_object_count: int = Field(default=0, ge=0)


class OracleDiscoverySummaryItem(BaseModel):
    key_point: str
    key_value: str
    observation: str


class OracleDiscoverySection(BaseModel):
    key: str
    title: str
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, str]] = Field(default_factory=list)
    row_count: int = Field(default=0, ge=0)
    truncated: bool = False


class OracleSchemaDependencyIssue(BaseModel):
    code: str
    label: str
    status: Literal["CLEAR", "REVIEW", "HIGH_RISK"]
    object_count: int = Field(default=0, ge=0)
    observation: str
    recommended_action: str | None = None
    object_names: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    section_keys: list[str] = Field(default_factory=list)


class OracleSchemaDependencyAnalysis(BaseModel):
    analysis_version: int = Field(default=1, ge=1)
    status: Literal["CLEAR", "REVIEW", "HIGH_RISK"]
    summary: str
    high_risk_count: int = Field(default=0, ge=0)
    review_count: int = Field(default=0, ge=0)
    clear_count: int = Field(default=0, ge=0)
    issues: list[OracleSchemaDependencyIssue] = Field(default_factory=list)


class OracleSchemaInventoryEntry(BaseModel):
    container_name: str = "UNKNOWN"
    container_type: Literal["CDB_ROOT", "PDB", "NON_CDB"] = "NON_CDB"
    con_id: int = Field(default=0, ge=0)
    owner: str
    object_count: int = Field(default=0, ge=0)
    table_count: int = Field(default=0, ge=0)
    index_count: int = Field(default=0, ge=0)
    view_count: int = Field(default=0, ge=0)
    materialized_view_count: int = Field(default=0, ge=0)
    sequence_count: int = Field(default=0, ge=0)
    procedure_count: int = Field(default=0, ge=0)
    function_count: int = Field(default=0, ge=0)
    package_count: int = Field(default=0, ge=0)
    trigger_count: int = Field(default=0, ge=0)
    invalid_object_count: int = Field(default=0, ge=0)


class OracleSourceMetadata(BaseModel):
    db_name: str | None = None
    host_name: str | None = None
    edition: str | None = None
    endianness: str | None = None
    oracle_version: str | None = None
    deployment_type: Literal["NON_CDB", "CDB_PDB"] | None = None
    database_size_gb: float | None = Field(default=None, ge=0)
    archivelog_enabled: bool | None = None
    platform: str | None = None
    rac_enabled: bool | None = None
    tde_enabled: bool | None = None
    character_set: str | None = None
    nchar_character_set: str | None = None
    inventory_summary: OracleObjectInventorySummary | None = None
    schema_inventory: list[OracleSchemaInventoryEntry] = Field(default_factory=list)
    pdbs: list[OraclePdbInventoryEntry] = Field(default_factory=list)
    database_users: list[OracleUserInventoryEntry] = Field(default_factory=list)
    tablespaces: list[OracleTablespaceInventoryEntry] = Field(default_factory=list)
    invalid_objects_by_schema: list[OracleInvalidObjectOwnerSummary] = Field(default_factory=list)
    discovery_summary: list[OracleDiscoverySummaryItem] = Field(default_factory=list)
    discovery_sections: list[OracleDiscoverySection] = Field(default_factory=list)
    dependency_analysis: OracleSchemaDependencyAnalysis | None = None
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class OracleTargetMetadata(BaseModel):
    db_name: str | None = None
    db_unique_name: str | None = None
    global_name: str | None = None
    host_name: str | None = None
    edition: str | None = None
    endianness: str | None = None
    oracle_version: str | None = None
    deployment_type: Literal["NON_CDB", "CDB_PDB"] | None = None
    database_role: str | None = None
    open_mode: str | None = None
    database_size_gb: float | None = Field(default=None, ge=0)
    archivelog_enabled: bool | None = None
    platform: str | None = None
    rac_enabled: bool | None = None
    tde_enabled: bool | None = None
    character_set: str | None = None
    nchar_character_set: str | None = None
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class MetadataEnrichmentSummary(BaseModel):
    status: Literal["COLLECTED", "PARTIAL", "FAILED"]
    source: OracleSourceMetadata | None = None
    collected_fields: list[str] = Field(default_factory=list)
    applied_fields: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MigrationCompatibilityCheck(BaseModel):
    code: str
    label: str
    status: Literal["PASS", "WARN", "FAIL", "INFO"]
    message: str
    source_value: str | None = None
    target_value: str | None = None
    remediation_sql: str | None = None


class MigrationRemediationScript(BaseModel):
    code: str
    label: str
    category: Literal[
        "USER",
        "TABLESPACE",
        "DIRECTORY",
        "DIRECTORY_GRANT",
        "PROFILE",
        "ROLE",
        "ACL",
        "OBJECT_STORAGE_CREDENTIAL",
    ]
    status: Literal["READY", "OPTIONAL"]
    summary: str
    sql: str


class MigrationRemediationPack(BaseModel):
    pack_version: int = Field(default=1, ge=1)
    summary: str
    scripts: list[MigrationRemediationScript] = Field(default_factory=list)
    combined_sql: str = ""


class MigrationReadinessFactor(BaseModel):
    code: str
    label: str
    weight: int = Field(ge=0, le=100)
    status: Literal["PASS", "WARN", "FAIL", "INFO"]
    score: int = Field(ge=0, le=100)
    observation: str
    source_value: str | None = None
    target_value: str | None = None


class MigrationReadinessCategory(BaseModel):
    key: str
    label: str
    weight: int = Field(ge=0, le=100)
    score: int = Field(ge=0, le=100)
    factors: list[MigrationReadinessFactor] = Field(default_factory=list)


class MigrationReadinessSummary(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    verdict: Literal["READY", "REVIEW", "BLOCKED"]
    summary: str
    categories: list[MigrationReadinessCategory] = Field(default_factory=list)


class MigrationCompatibilityAssessment(BaseModel):
    status: Literal[
        "MIGRATABLE",
        "CONDITIONALLY_MIGRATABLE",
        "NOT_MIGRATABLE",
        "FAILED",
    ]
    summary: str
    source_connection_status: Literal["CONNECTED", "FAILED", "NOT_PROVIDED"] = (
        "NOT_PROVIDED"
    )
    target_connection_status: Literal["CONNECTED", "FAILED", "NOT_PROVIDED"] = (
        "NOT_PROVIDED"
    )
    source: OracleSourceMetadata | None = None
    target: OracleTargetMetadata | None = None
    checks: list[MigrationCompatibilityCheck] = Field(default_factory=list)
    remediation_pack: MigrationRemediationPack | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    readiness: MigrationReadinessSummary | None = None
    notes: list[str] = Field(default_factory=list)
    validated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
