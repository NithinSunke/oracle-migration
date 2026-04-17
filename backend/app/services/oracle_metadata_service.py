from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from backend.app.adapters.oracle import OracleClientError, OracleMetadataAdapter
from backend.app.core.config import settings
from backend.app.schemas.migration import MigrationCreate, OracleConnectionConfig
from backend.app.schemas.oracle import (
    MetadataEnrichmentSummary,
    MigrationCompatibilityAssessment,
    MigrationCompatibilityCheck,
    MigrationRemediationPack,
    MigrationRemediationScript,
    MigrationReadinessCategory,
    MigrationReadinessFactor,
    MigrationReadinessSummary,
    OracleSourceMetadata,
    OracleTablespaceInventoryEntry,
    OracleTargetMetadata,
    OracleUserInventoryEntry,
)


class OracleMetadataService:
    def __init__(self, adapter: OracleMetadataAdapter | None = None) -> None:
        self._adapter = adapter or OracleMetadataAdapter()

    def enrich_request(
        self,
        request: MigrationCreate,
    ) -> tuple[MigrationCreate, MetadataEnrichmentSummary | None]:
        options = request.metadata_collection
        if request.source_metadata is not None:
            prefer_collected_values = (
                options.prefer_collected_values if options is not None else True
            )
            enriched_request, applied_fields = self._apply_source_metadata(
                request=request,
                metadata=request.source_metadata,
                prefer_collected_values=prefer_collected_values,
            )
            return enriched_request, MetadataEnrichmentSummary(
                status="COLLECTED",
                source=request.source_metadata,
                collected_fields=self._collect_field_names(request.source_metadata),
                applied_fields=applied_fields,
                errors=[],
                notes=[
                    "Recommendation used pre-collected source metadata supplied in the request."
                ],
            )

        if options is None or not options.enabled:
            return request, None

        connection = options.source_connection
        if connection is None or not connection.has_secret():
            return request, MetadataEnrichmentSummary(
                status="FAILED",
                source=None,
                collected_fields=[],
                applied_fields=[],
                errors=[
                    "Source metadata collection was requested without a complete Oracle source connection."
                ],
                notes=[
                    "Recommendation used submitted inputs only because Oracle metadata could not be collected."
                ],
            )

        try:
            metadata_summary = self._adapter.collect_source_metadata(connection)
        except OracleClientError as exc:
            return request, MetadataEnrichmentSummary(
                status="FAILED",
                source=None,
                collected_fields=[],
                applied_fields=[],
                errors=[str(exc)],
                notes=[
                    "Recommendation used submitted inputs only because Oracle metadata collection failed."
                ],
            )

        enriched_request, applied_fields = self._apply_source_metadata(
            request=request,
            metadata=metadata_summary.source,
            prefer_collected_values=options.prefer_collected_values,
        )
        metadata_summary = metadata_summary.model_copy(
            update={"applied_fields": applied_fields}
        )
        return enriched_request, metadata_summary

    def collect_source_metadata(self, request: MigrationCreate) -> MetadataEnrichmentSummary:
        enriched_request, metadata_summary = self.enrich_request(request)
        if metadata_summary is None:
            return MetadataEnrichmentSummary(
                status="FAILED",
                source=None,
                collected_fields=[],
                applied_fields=[],
                errors=["Oracle metadata collection is not enabled for this request."],
                notes=[],
            )
        if metadata_summary.source is None:
            return metadata_summary
        if metadata_summary.applied_fields:
            return metadata_summary

        _, applied_fields = self._apply_source_metadata(
            request=request,
            metadata=metadata_summary.source,
            prefer_collected_values=request.metadata_collection.prefer_collected_values
            if request.metadata_collection is not None
            else True,
        )
        return metadata_summary.model_copy(update={"applied_fields": applied_fields})

    def validate_source_to_target(
        self,
        request: MigrationCreate,
    ) -> MigrationCompatibilityAssessment:
        options = request.metadata_collection
        if options is None or not options.enabled:
            return MigrationCompatibilityAssessment(
                status="FAILED",
                summary="Enable source and target metadata collection before validating migration feasibility.",
                blockers=[
                    "Source and target connection validation requires metadata collection to be enabled."
                ],
            )

        source_connection = options.source_connection
        target_connection = options.target_connection
        blockers: list[str] = []

        if source_connection is None or not source_connection.has_secret():
            blockers.append("A complete source Oracle connection is required.")
        if target_connection is None or not target_connection.has_secret():
            blockers.append("A complete target Oracle connection is required.")

        if blockers:
            return MigrationCompatibilityAssessment(
                status="FAILED",
                summary="Source-to-target validation could not start because one or both Oracle connections are incomplete.",
                source_connection_status=(
                    "NOT_PROVIDED" if source_connection is None else "FAILED"
                ),
                target_connection_status=(
                    "NOT_PROVIDED" if target_connection is None else "FAILED"
                ),
                blockers=blockers,
            )

        source_connection, target_connection = self._normalize_validation_connection_modes(
            source_connection,
            target_connection,
        )

        try:
            source_summary = self._adapter.collect_source_metadata(source_connection)
        except OracleClientError as exc:
            return MigrationCompatibilityAssessment(
                status="FAILED",
                summary="The source Oracle connection could not be validated.",
                source_connection_status="FAILED",
                target_connection_status="NOT_PROVIDED",
                blockers=[str(exc)],
            )

        try:
            target_metadata = self._adapter.collect_target_metadata(target_connection)
        except OracleClientError as exc:
            return MigrationCompatibilityAssessment(
                status="FAILED",
                summary="The target Oracle connection could not be validated.",
                source_connection_status="CONNECTED",
                target_connection_status="FAILED",
                source=source_summary.source,
                blockers=[str(exc)],
                notes=source_summary.notes,
            )

        return self._build_feasibility_assessment(
            request=request,
            source=source_summary.source,
            target=target_metadata,
            target_connection=target_connection,
            source_notes=source_summary.notes,
            source_errors=source_summary.errors,
        )

    def _build_feasibility_assessment(
        self,
        request: MigrationCreate,
        source: OracleSourceMetadata | None,
        target: OracleTargetMetadata | None,
        target_connection: OracleConnectionConfig,
        source_notes: list[str] | None = None,
        source_errors: list[str] | None = None,
    ) -> MigrationCompatibilityAssessment:
        if source is None or target is None:
            return MigrationCompatibilityAssessment(
                status="FAILED",
                summary="Migration validation could not complete because source or target metadata is unavailable.",
                source_connection_status="CONNECTED" if source is not None else "FAILED",
                target_connection_status="CONNECTED" if target is not None else "FAILED",
                blockers=["Required source or target metadata was not collected."],
                notes=list(source_notes or []),
            )

        checks: list[MigrationCompatibilityCheck] = []
        warnings: list[str] = []
        blockers: list[str] = []

        checks.append(
            MigrationCompatibilityCheck(
                code="SOURCE_CONNECTION",
                label="Source connection",
                status="PASS",
                message="The application connected to the source Oracle database successfully.",
                source_value=source.db_name or source.host_name,
            )
        )
        checks.append(
            MigrationCompatibilityCheck(
                code="TARGET_CONNECTION",
                label="Target connection",
                status="PASS",
                message="The application connected to the target Oracle database successfully.",
                target_value=target.db_name or target.host_name,
            )
        )
        runtime_checks, runtime_warnings = self._build_runtime_readiness_checks(
            source_connection=request.metadata_collection.source_connection
            if request.metadata_collection is not None
            else None,
            target_connection=target_connection,
        )
        checks.extend(runtime_checks)
        warnings.extend(runtime_warnings)

        source_major = self._extract_major_version(source.oracle_version)
        target_major = self._extract_major_version(target.oracle_version)
        if source_major is None or target_major is None:
            checks.append(
                MigrationCompatibilityCheck(
                    code="VERSION_CHECK",
                    label="Oracle version compatibility",
                    status="WARN",
                    message="Oracle versions could not be compared automatically. Review source and target software levels manually.",
                    source_value=source.oracle_version,
                    target_value=target.oracle_version,
                )
            )
            warnings.append(
                "Oracle source and target versions should be reviewed manually because the app could not parse one of the version values."
            )
        elif target_major < source_major:
            message = (
                "Target Oracle version is lower than the source version. Direct migration is not supported until the target is upgraded."
            )
            checks.append(
                MigrationCompatibilityCheck(
                    code="VERSION_CHECK",
                    label="Oracle version compatibility",
                    status="FAIL",
                    message=message,
                    source_value=source.oracle_version,
                    target_value=target.oracle_version,
                )
            )
            blockers.append(message)
        else:
            checks.append(
                MigrationCompatibilityCheck(
                    code="VERSION_CHECK",
                    label="Oracle version compatibility",
                    status="PASS",
                    message="Target Oracle version is equal to or higher than the source version.",
                    source_value=source.oracle_version,
                    target_value=target.oracle_version,
                )
            )

        target_role = (target.database_role or "").upper()
        if target_role and target_role != "PRIMARY":
            message = (
                "Target database role is not PRIMARY. Use a writable primary target or adjust the landing architecture before migration."
            )
            checks.append(
                MigrationCompatibilityCheck(
                    code="TARGET_ROLE",
                    label="Target database role",
                    status="FAIL",
                    message=message,
                    target_value=target.database_role,
                )
            )
            blockers.append(message)
        else:
            checks.append(
                MigrationCompatibilityCheck(
                    code="TARGET_ROLE",
                    label="Target database role",
                    status="PASS",
                    message="Target database is writable for migration cutover.",
                    target_value=target.database_role or "PRIMARY",
                )
            )

        source_platform = (source.platform or "").strip().lower()
        target_platform = (target.platform or "").strip().lower()
        same_endian = self._normalize_text(source.endianness) == self._normalize_text(
            target.endianness
        )
        request_same_endian = request.target.same_endian
        if source_platform and target_platform and source_platform == target_platform:
            checks.append(
                MigrationCompatibilityCheck(
                    code="PLATFORM_CHECK",
                    label="Platform and endian compatibility",
                    status="PASS",
                    message="Source and target platforms match.",
                    source_value=source.platform,
                    target_value=target.platform,
                )
            )
        elif same_endian or request_same_endian:
            message = (
                "Source and target platforms differ, but endian compatibility suggests logical migration tools such as Data Pump or GoldenGate remain feasible."
            )
            checks.append(
                MigrationCompatibilityCheck(
                    code="PLATFORM_CHECK",
                    label="Platform and endian compatibility",
                    status="WARN",
                    message=message,
                    source_value=source.platform,
                    target_value=target.platform,
                )
            )
            warnings.append(message)
        else:
            message = (
                "Source and target platforms differ and endian compatibility is not confirmed. Logical migration is still possible, but physical approaches such as RMAN duplicate or backup/restore are unlikely to work directly."
            )
            checks.append(
                MigrationCompatibilityCheck(
                    code="PLATFORM_CHECK",
                    label="Platform and endian compatibility",
                    status="WARN",
                    message=message,
                    source_value=source.platform,
                    target_value=target.platform,
                )
            )
            warnings.append(message)

        source_charset = self._normalize_text(source.character_set)
        target_charset = self._normalize_text(target.character_set)
        if source_charset and target_charset and source_charset == target_charset:
            checks.append(
                MigrationCompatibilityCheck(
                    code="CHARSET_CHECK",
                    label="Character set compatibility",
                    status="PASS",
                    message="Source and target database character sets match.",
                    source_value=source.character_set,
                    target_value=target.character_set,
                )
            )
        elif source_charset and target_charset and target_charset == "AL32UTF8":
            message = (
                "Target character set is AL32UTF8 and differs from the source. Migration is usually feasible, but charset conversion validation is required."
            )
            checks.append(
                MigrationCompatibilityCheck(
                    code="CHARSET_CHECK",
                    label="Character set compatibility",
                    status="WARN",
                    message=message,
                    source_value=source.character_set,
                    target_value=target.character_set,
                )
            )
            warnings.append(message)
        else:
            message = (
                "Source and target character sets differ. Validate datatype and data-conversion impact before migration."
            )
            checks.append(
                MigrationCompatibilityCheck(
                    code="CHARSET_CHECK",
                    label="Character set compatibility",
                    status="WARN",
                    message=message,
                    source_value=source.character_set,
                    target_value=target.character_set,
                )
            )
            warnings.append(message)

        if source.tde_enabled and not target.tde_enabled:
            message = (
                "Source uses TDE while target TDE is not detected. Wallet and encryption setup must be completed before migration."
            )
            checks.append(
                MigrationCompatibilityCheck(
                    code="TDE_CHECK",
                    label="Encryption readiness",
                    status="WARN",
                    message=message,
                    source_value="Enabled",
                    target_value="Disabled or not detected",
                )
            )
            warnings.append(message)
        else:
            checks.append(
                MigrationCompatibilityCheck(
                    code="TDE_CHECK",
                    label="Encryption readiness",
                    status="PASS",
                    message="Encryption settings do not block the migration path at this stage.",
                    source_value="Enabled" if source.tde_enabled else "Disabled",
                    target_value="Enabled" if target.tde_enabled else "Disabled",
                )
            )

        if source.deployment_type != target.deployment_type:
            message = (
                f"Source deployment type is {source.deployment_type or 'unknown'} while target is {target.deployment_type or 'unknown'}. Conversion planning is required."
            )
            checks.append(
                MigrationCompatibilityCheck(
                    code="DEPLOYMENT_CHECK",
                    label="CDB and non-CDB alignment",
                    status="WARN",
                    message=message,
                    source_value=source.deployment_type,
                    target_value=target.deployment_type,
                )
            )
            warnings.append(message)
        else:
            checks.append(
                MigrationCompatibilityCheck(
                    code="DEPLOYMENT_CHECK",
                    label="CDB and non-CDB alignment",
                    status="PASS",
                    message="Source and target deployment models match.",
                    source_value=source.deployment_type,
                    target_value=target.deployment_type,
                )
            )

        if source_errors:
            warnings.append(
                "Some source metadata queries were partial, so the migration verdict should be reviewed together with the detailed discovery report."
            )

        directory_checks, directory_warnings = self._build_directory_object_checks(
            target_connection=target_connection,
        )
        checks.extend(directory_checks)
        warnings.extend(directory_warnings)

        (
            prerequisite_checks,
            prerequisite_blockers,
            prerequisite_warnings,
        ) = self._build_schema_prerequisite_checks(
            request=request,
            source=source,
            target_connection=target_connection,
        )
        checks.extend(prerequisite_checks)
        blockers.extend(prerequisite_blockers)
        warnings.extend(prerequisite_warnings)

        if blockers:
            status = "NOT_MIGRATABLE"
            summary = "The current source and target combination is not migration-ready. Resolve the blockers before planning execution."
        elif warnings:
            status = "CONDITIONALLY_MIGRATABLE"
            summary = "The source and target can be migrated, but there are compatibility warnings that require DBA review and execution planning."
        else:
            status = "MIGRATABLE"
            summary = "The source and target databases passed the core compatibility checks and are suitable for migration planning."

        deduplicated_blockers = list(dict.fromkeys(blockers))
        deduplicated_warnings = list(dict.fromkeys(warnings))
        readiness = self._build_readiness_summary(
            request=request,
            checks=checks,
            blockers=deduplicated_blockers,
            warnings=deduplicated_warnings,
        )
        remediation_pack, remediation_notes = self._build_remediation_pack(
            request=request,
            source=source,
            target_connection=target_connection,
            checks=checks,
        )

        return MigrationCompatibilityAssessment(
            status=status,
            summary=summary,
            source_connection_status="CONNECTED",
            target_connection_status="CONNECTED",
            source=source,
            target=target,
            checks=checks,
            remediation_pack=remediation_pack,
            blockers=deduplicated_blockers,
            warnings=deduplicated_warnings,
            readiness=readiness,
            notes=list(
                dict.fromkeys(
                    (source_notes or []) + (source_errors or []) + remediation_notes
                )
            ),
        )

    def _build_schema_prerequisite_checks(
        self,
        *,
        request: MigrationCreate,
        source: OracleSourceMetadata,
        target_connection: OracleConnectionConfig,
    ) -> tuple[list[MigrationCompatibilityCheck], list[str], list[str]]:
        if request.scope.migration_scope != "SCHEMA":
            return [], [], []

        schema_names = self._normalize_names(request.scope.schema_names)
        if not schema_names:
            message = (
                "Schema migration validation needs explicit schema names. Provide the schema list so the app can verify target prerequisites."
            )
            return (
                [
                    MigrationCompatibilityCheck(
                        code="SCHEMA_SCOPE_INPUT",
                        label="Schema prerequisite input",
                        status="FAIL",
                        message=message,
                        source_value=None,
                        target_value=None,
                    )
                ],
                [message],
                [],
            )

        source_users = {
            item.username.strip().upper(): item
            for item in source.database_users
            if item.username.strip()
        }
        source_owners = {
            item.owner.strip().upper(): item
            for item in source.schema_inventory
            if item.owner.strip()
        }
        section_schema_names = {
            self._row_value(row, "CUSTOM_USER")
            or self._row_value(row, "USERNAME")
            or self._row_value(row, "OWNER")
            or self._row_value(row, "SCHEMA")
            for row in [
                *self._section_rows(source, "database_users"),
                *self._section_rows(source, "schema_inventory"),
            ]
        }
        section_schema_names = {name for name in section_schema_names if name}
        source_tablespaces = {
            item.tablespace_name.strip().upper(): item
            for item in source.tablespaces
            if item.tablespace_name.strip()
        }

        checks: list[MigrationCompatibilityCheck] = []
        blockers: list[str] = []
        warnings: list[str] = []

        requested_source_users: dict[str, OracleUserInventoryEntry | None] = {}
        for schema_name in schema_names:
            source_user = source_users.get(schema_name)
            requested_source_users[schema_name] = source_user
            if (
                source_user is not None
                or schema_name in source_owners
                or schema_name in section_schema_names
            ):
                continue

            has_structured_source_inventory = bool(source.database_users or source.schema_inventory)
            if has_structured_source_inventory:
                message = (
                    f"Schema '{schema_name}' was requested for schema migration, but it was not found in the collected source metadata."
                )
                status = "FAIL"
            else:
                message = (
                    f"Schema '{schema_name}' was requested for schema migration, but it was not visible in the collected source metadata snapshot. "
                    "Verify the source connection or refresh the metadata from the correct PDB before cutover."
                )
                status = "WARN"

            checks.append(
                MigrationCompatibilityCheck(
                    code=f"SOURCE_SCHEMA_{schema_name}",
                    label=f"Source schema {schema_name}",
                    status=status,
                    message=message,
                    source_value=schema_name,
                    target_value=None,
                )
            )
            if status == "FAIL":
                blockers.append(message)
            else:
                warnings.append(message)

        required_tablespace_names: list[str] = []
        for schema_name, source_user in requested_source_users.items():
            if source_user is None:
                continue
            if source_user.default_tablespace:
                required_tablespace_names.append(source_user.default_tablespace)
            if source_user.temporary_tablespace:
                required_tablespace_names.append(source_user.temporary_tablespace)

        try:
            target_users = {
                item.username.strip().upper(): item
                for item in self._adapter.lookup_target_users(target_connection, schema_names)
                if item.username.strip()
            }
            target_tablespaces = {
                item.tablespace_name.strip().upper(): item
                for item in self._adapter.lookup_target_tablespaces(
                    target_connection,
                    required_tablespace_names,
                )
                if item.tablespace_name.strip()
            }
        except OracleClientError as exc:
            message = (
                "Target prerequisite lookup could not verify schema and tablespace readiness. "
                f"Oracle reported: {exc}"
            )
            return (
                [
                    MigrationCompatibilityCheck(
                        code="TARGET_PREREQ_LOOKUP",
                        label="Target schema prerequisite lookup",
                        status="WARN",
                        message=message,
                        source_value=", ".join(schema_names),
                        target_value=None,
                    )
                ],
                [],
                [message],
            )

        for tablespace_name in self._normalize_names(required_tablespace_names):
            source_tablespace = source_tablespaces.get(tablespace_name)
            if tablespace_name in target_tablespaces:
                checks.append(
                    MigrationCompatibilityCheck(
                        code=f"TARGET_TABLESPACE_{tablespace_name}",
                        label=f"Target tablespace {tablespace_name}",
                        status="PASS",
                        message="Required tablespace already exists on the target.",
                        source_value=tablespace_name,
                        target_value=tablespace_name,
                    )
                )
                continue

            ddl = self._tablespace_ddl(source_tablespace, tablespace_name)
            message = (
                f"Required source tablespace '{tablespace_name}' does not exist on the target. Create it before running the schema migration."
            )
            checks.append(
                MigrationCompatibilityCheck(
                    code=f"TARGET_TABLESPACE_{tablespace_name}",
                    label=f"Target tablespace {tablespace_name}",
                    status="FAIL",
                    message=message,
                    source_value=tablespace_name,
                    target_value="Missing",
                    remediation_sql=ddl,
                )
            )
            blockers.append(message)

        return checks, blockers, warnings

    def _build_runtime_readiness_checks(
        self,
        *,
        source_connection: OracleConnectionConfig | None,
        target_connection: OracleConnectionConfig,
    ) -> tuple[list[MigrationCompatibilityCheck], list[str]]:
        checks = [
            MigrationCompatibilityCheck(
                code="NETWORK_REACHABILITY",
                label="Network reachability",
                status="PASS",
                message="Source and target Oracle endpoints were reachable from the application runtime during validation.",
                source_value=(
                    f"{source_connection.host}:{source_connection.port}"
                    if source_connection is not None
                    else None
                ),
                target_value=f"{target_connection.host}:{target_connection.port}",
            )
        ]
        warnings: list[str] = []

        thick_mode_requested = (
            (source_connection.mode == "thick" if source_connection is not None else False)
            or target_connection.mode == "thick"
        )
        wallet_paths = [
            path.strip()
            for path in [
                source_connection.wallet_location if source_connection is not None else None,
                target_connection.wallet_location,
            ]
            if path is not None and path.strip()
        ]

        oracle_client_dir = Path(settings.oracle_client_lib_dir).expanduser()
        if thick_mode_requested and not oracle_client_dir.exists():
            wallet_check = MigrationCompatibilityCheck(
                code="WALLET_CERT_READINESS",
                label="Wallet and certificate readiness",
                status="FAIL",
                message="Oracle Thick mode was requested, but the Oracle client library directory is not available in the runtime.",
                source_value=str(oracle_client_dir),
                target_value=None,
            )
        elif wallet_paths:
            unreadable_wallets = [
                wallet_path
                for wallet_path in wallet_paths
                if not Path(wallet_path).expanduser().exists()
                or not Path(wallet_path).expanduser().is_dir()
            ]
            if unreadable_wallets:
                wallet_check = MigrationCompatibilityCheck(
                    code="WALLET_CERT_READINESS",
                    label="Wallet and certificate readiness",
                    status="WARN",
                    message="A wallet or certificate directory was configured, but at least one configured path is unavailable in the runtime. Review the mounted wallet path before rehearsal or cutover.",
                    source_value=", ".join(wallet_paths),
                    target_value="Missing path",
                )
                warnings.append(wallet_check.message)
            else:
                wallet_check = MigrationCompatibilityCheck(
                    code="WALLET_CERT_READINESS",
                    label="Wallet and certificate readiness",
                    status="PASS",
                    message="Configured wallet and certificate directories are present in the runtime.",
                    source_value=", ".join(wallet_paths),
                    target_value="Readable",
                )
        else:
            wallet_check = MigrationCompatibilityCheck(
                code="WALLET_CERT_READINESS",
                label="Wallet and certificate readiness",
                status="PASS",
                message="No custom wallet or certificate directory was required for the validated Oracle connection path.",
                source_value=(
                    "Thick mode without wallet path"
                    if thick_mode_requested
                    else "Default runtime path"
                ),
                target_value="Ready",
            )

        checks.append(wallet_check)
        return checks, warnings

    def _build_directory_object_checks(
        self,
        *,
        target_connection: OracleConnectionConfig,
    ) -> tuple[list[MigrationCompatibilityCheck], list[str]]:
        try:
            directories = self._adapter.lookup_target_directories(
                target_connection,
                ["DATA_PUMP_DIR"],
            )
        except OracleClientError as exc:
            message = (
                "Target Data Pump directory object readiness could not be verified. "
                f"Oracle reported: {exc}"
            )
            return (
                [
                    MigrationCompatibilityCheck(
                        code="TARGET_DATAPUMP_DIRECTORY",
                        label="Target directory object readiness",
                        status="WARN",
                        message=message,
                        source_value="DATA_PUMP_DIR",
                        target_value="Unknown",
                    )
                ],
                [message],
            )

        directory_path = directories.get("DATA_PUMP_DIR")
        if directory_path:
            return (
                [
                    MigrationCompatibilityCheck(
                        code="TARGET_DATAPUMP_DIRECTORY",
                        label="Target directory object readiness",
                        status="PASS",
                        message="The target DATA_PUMP_DIR directory object exists and can be used for Data Pump logs or staging.",
                        source_value="DATA_PUMP_DIR",
                        target_value=directory_path,
                    )
                ],
                [],
            )

        message = (
            "The target DATA_PUMP_DIR directory object was not found. Create a usable directory object before execution steps that rely on server-side Data Pump logs or files."
        )
        return (
            [
                MigrationCompatibilityCheck(
                    code="TARGET_DATAPUMP_DIRECTORY",
                    label="Target directory object readiness",
                    status="WARN",
                    message=message,
                    source_value="DATA_PUMP_DIR",
                    target_value="Missing",
                    remediation_sql=(
                        "CREATE OR REPLACE DIRECTORY DATA_PUMP_DIR AS '<target_server_path>';\n"
                        "GRANT READ, WRITE ON DIRECTORY DATA_PUMP_DIR TO SYSTEM;"
                    ),
                )
            ],
            [message],
        )

    def _build_readiness_summary(
        self,
        *,
        request: MigrationCreate,
        checks: list[MigrationCompatibilityCheck],
        blockers: list[str],
        warnings: list[str],
    ) -> MigrationReadinessSummary:
        compatibility_factors = [
            self._factor_from_check(
                code="VERSION_READINESS",
                label="Version compatibility",
                weight=20,
                check=self._find_check(checks, "VERSION_CHECK"),
                warn_score=60,
                fail_score=0,
                default_observation="Version compatibility was not collected during validation.",
            ),
            self._factor_from_check(
                code="CHARSET_READINESS",
                label="Character set compatibility",
                weight=15,
                check=self._find_check(checks, "CHARSET_CHECK"),
                warn_score=75,
                fail_score=35,
                default_observation="Character set compatibility was not collected during validation.",
            ),
            self._factor_from_check(
                code="TDE_READINESS",
                label="TDE alignment",
                weight=10,
                check=self._find_check(checks, "TDE_CHECK"),
                warn_score=35,
                fail_score=15,
                default_observation="TDE readiness was not collected during validation.",
            ),
        ]
        execution_factors = [
            self._factor_from_check(
                code="NETWORK_READINESS",
                label="Network reachability",
                weight=10,
                check=self._find_check(checks, "NETWORK_REACHABILITY"),
                warn_score=50,
                fail_score=0,
                default_observation="Network reachability was not validated.",
            ),
            self._factor_from_check(
                code="WALLET_CERT_PATH_READY",
                label="Wallet and certificate readiness",
                weight=5,
                check=self._find_check(checks, "WALLET_CERT_READINESS"),
                warn_score=60,
                fail_score=20,
                info_score=90,
                default_observation="Wallet and certificate readiness was not validated.",
            ),
            self._factor_from_check(
                code="DIRECTORY_OBJECT_READY",
                label="Directory object readiness",
                weight=10,
                check=self._find_check(checks, "TARGET_DATAPUMP_DIRECTORY"),
                warn_score=45,
                fail_score=20,
                default_observation="Target directory object readiness was not validated.",
            ),
        ]
        target_factors = [
            self._tablespace_readiness_factor(request=request, checks=checks),
        ]

        categories = [
            self._build_readiness_category(
                key="compatibility",
                label="Compatibility",
                weight=45,
                factors=compatibility_factors,
            ),
            self._build_readiness_category(
                key="execution_path",
                label="Execution Path",
                weight=25,
                factors=execution_factors,
            ),
            self._build_readiness_category(
                key="target_readiness",
                label="Target Readiness",
                weight=30,
                factors=target_factors,
            ),
        ]

        overall_score = self._weighted_category_score(categories)
        if blockers or overall_score < 50:
            verdict = "BLOCKED"
            summary = (
                "Critical migration prerequisites are still missing. Resolve the blocking checks before scheduling rehearsal or cutover."
            )
        elif warnings or overall_score < 85:
            verdict = "REVIEW"
            summary = (
                "Core validation passed, but DBA review is still needed to close compatibility or execution-readiness gaps."
            )
        else:
            verdict = "READY"
            summary = (
                "The current source and target pair is operationally ready for migration planning based on the checks collected so far."
            )

        return MigrationReadinessSummary(
            overall_score=overall_score,
            verdict=verdict,
            summary=summary,
            categories=categories,
        )

    def _tablespace_readiness_factor(
        self,
        *,
        request: MigrationCreate,
        checks: list[MigrationCompatibilityCheck],
    ) -> MigrationReadinessFactor:
        if request.scope.migration_scope != "SCHEMA":
            return MigrationReadinessFactor(
                code="TABLESPACE_READINESS",
                label="Tablespace readiness",
                weight=20,
                status="INFO",
                score=100,
                observation="Dedicated source-schema tablespace checks are required only for schema-scoped migration requests.",
                source_value=request.scope.migration_scope,
                target_value="Not required",
            )

        relevant_checks = self._find_checks_by_prefix(checks, "TARGET_TABLESPACE_")
        if not relevant_checks:
            return MigrationReadinessFactor(
                code="TABLESPACE_READINESS",
                label="Tablespace readiness",
                weight=20,
                status="INFO",
                score=70,
                observation="Schema-scoped tablespace readiness could not be fully derived from the collected metadata. Review target tablespaces manually.",
                source_value="Schema scope",
                target_value="Unknown",
            )

        score = round(
            sum(
                self._score_for_status(
                    check.status,
                    warn_score=65,
                    fail_score=0,
                    info_score=85,
                )
                for check in relevant_checks
            )
            / len(relevant_checks)
        )
        status = self._aggregate_status(relevant_checks)
        return MigrationReadinessFactor(
            code="TABLESPACE_READINESS",
            label="Tablespace readiness",
            weight=20,
            status=status,
            score=score,
            observation=(
                "Required source schema tablespaces already exist on the target."
                if status == "PASS"
                else "Some required schema tablespaces still need target-side preparation before execution."
            ),
            source_value=", ".join(check.source_value or "" for check in relevant_checks if check.source_value),
            target_value=(
                "Ready"
                if status == "PASS"
                else ", ".join(check.target_value or "" for check in relevant_checks if check.target_value)
            ),
        )

    @staticmethod
    def _build_readiness_category(
        *,
        key: str,
        label: str,
        weight: int,
        factors: list[MigrationReadinessFactor],
    ) -> MigrationReadinessCategory:
        total_weight = sum(factor.weight for factor in factors) or 1
        score = round(
            sum(factor.score * factor.weight for factor in factors) / total_weight
        )
        return MigrationReadinessCategory(
            key=key,
            label=label,
            weight=weight,
            score=score,
            factors=factors,
        )

    @staticmethod
    def _weighted_category_score(
        categories: list[MigrationReadinessCategory],
    ) -> int:
        total_weight = sum(category.weight for category in categories) or 1
        return round(
            sum(category.score * category.weight for category in categories)
            / total_weight
        )

    @staticmethod
    def _find_check(
        checks: list[MigrationCompatibilityCheck],
        code: str,
    ) -> MigrationCompatibilityCheck | None:
        for check in checks:
            if check.code == code:
                return check
        return None

    @staticmethod
    def _find_checks_by_prefix(
        checks: list[MigrationCompatibilityCheck],
        prefix: str,
    ) -> list[MigrationCompatibilityCheck]:
        return [check for check in checks if check.code.startswith(prefix)]

    @staticmethod
    def _factor_from_check(
        *,
        code: str,
        label: str,
        weight: int,
        check: MigrationCompatibilityCheck | None,
        warn_score: int,
        fail_score: int,
        default_observation: str,
        info_score: int = 85,
    ) -> MigrationReadinessFactor:
        if check is None:
            return MigrationReadinessFactor(
                code=code,
                label=label,
                weight=weight,
                status="INFO",
                score=70,
                observation=default_observation,
                source_value=None,
                target_value=None,
            )

        return MigrationReadinessFactor(
            code=code,
            label=label,
            weight=weight,
            status=check.status,
            score=OracleMetadataService._score_for_status(
                check.status,
                warn_score=warn_score,
                fail_score=fail_score,
                info_score=info_score,
            ),
            observation=check.message,
            source_value=check.source_value,
            target_value=check.target_value,
        )

    @staticmethod
    def _score_for_status(
        status: str,
        *,
        warn_score: int,
        fail_score: int,
        info_score: int,
    ) -> int:
        if status == "PASS":
            return 100
        if status == "WARN":
            return warn_score
        if status == "FAIL":
            return fail_score
        return info_score

    @staticmethod
    def _aggregate_status(
        checks: list[MigrationCompatibilityCheck],
    ) -> str:
        statuses = {check.status for check in checks}
        if "FAIL" in statuses:
            return "FAIL"
        if "WARN" in statuses:
            return "WARN"
        if "INFO" in statuses:
            return "INFO"
        return "PASS"

    @staticmethod
    def _normalize_validation_connection_modes(
        source_connection: OracleConnectionConfig,
        target_connection: OracleConnectionConfig,
    ) -> tuple[OracleConnectionConfig, OracleConnectionConfig]:
        if source_connection.mode != "thick" and target_connection.mode != "thick":
            return source_connection, target_connection

        normalized_wallet_location = (
            (target_connection.wallet_location or "").strip()
            or (source_connection.wallet_location or "").strip()
            or None
        )
        return (
            source_connection.model_copy(
                update={
                    "mode": "thick",
                    "wallet_location": normalized_wallet_location,
                }
            ),
            target_connection.model_copy(
                update={
                    "mode": "thick",
                    "wallet_location": normalized_wallet_location,
                }
            ),
        )

    def _create_user_ddl(
        self,
        schema_name: str,
        source_user: OracleUserInventoryEntry | None,
    ) -> str:
        clauses = [f'CREATE USER "{schema_name}" IDENTIFIED BY "<change_me>"']
        if source_user is not None and source_user.default_tablespace:
            clauses.append(
                f'DEFAULT TABLESPACE "{source_user.default_tablespace.strip().upper()}"'
            )
        if source_user is not None and source_user.temporary_tablespace:
            clauses.append(
                f'TEMPORARY TABLESPACE "{source_user.temporary_tablespace.strip().upper()}"'
            )
        if source_user is not None and source_user.default_tablespace:
            clauses.append(
                f'QUOTA UNLIMITED ON "{source_user.default_tablespace.strip().upper()}"'
            )
        return "\n".join(clauses) + ";"

    def _alter_user_tablespace_ddl(
        self,
        schema_name: str,
        source_user: OracleUserInventoryEntry | None,
    ) -> str | None:
        if source_user is None:
            return None

        clauses = [f'ALTER USER "{schema_name}"']
        if source_user.default_tablespace:
            clauses.append(
                f'DEFAULT TABLESPACE "{source_user.default_tablespace.strip().upper()}"'
            )
        if source_user.temporary_tablespace:
            clauses.append(
                f'TEMPORARY TABLESPACE "{source_user.temporary_tablespace.strip().upper()}"'
            )
        if len(clauses) == 1:
            return None
        return "\n".join(clauses) + ";"

    def _tablespace_ddl(
        self,
        source_tablespace: OracleTablespaceInventoryEntry | None,
        tablespace_name: str,
    ) -> str:
        tablespace_kind = (
            "TEMPORARY TABLESPACE"
            if self._normalize_text(source_tablespace.contents if source_tablespace else None)
            == "TEMPORARY"
            else "TABLESPACE"
        )
        datafile_keyword = "TEMPFILE" if tablespace_kind == "TEMPORARY TABLESPACE" else "DATAFILE"
        bigfile_prefix = "BIGFILE " if source_tablespace and source_tablespace.bigfile else ""
        return (
            f"CREATE {bigfile_prefix}{tablespace_kind} \"{tablespace_name}\"\n"
            f"  {datafile_keyword} SIZE 1G\n"
            "  AUTOEXTEND ON NEXT 256M MAXSIZE UNLIMITED;"
        )

    @staticmethod
    def _format_user_tablespaces(user: OracleUserInventoryEntry | None) -> str | None:
        if user is None:
            return None
        details: list[str] = []
        if user.default_tablespace:
            details.append(f"default={user.default_tablespace}")
        if user.temporary_tablespace:
            details.append(f"temp={user.temporary_tablespace}")
        return ", ".join(details) or user.username

    def _build_remediation_pack(
        self,
        *,
        request: MigrationCreate,
        source: OracleSourceMetadata,
        target_connection: OracleConnectionConfig,
        checks: list[MigrationCompatibilityCheck],
    ) -> tuple[MigrationRemediationPack | None, list[str]]:
        scripts: list[MigrationRemediationScript] = []
        notes: list[str] = []
        seen_codes: set[str] = set()

        for check in checks:
            if not check.remediation_sql:
                continue
            script = self._script_from_check(check)
            if script.code in seen_codes:
                continue
            scripts.append(script)
            seen_codes.add(script.code)

        try:
            for script in self._build_profile_remediation_scripts(
                request=request,
                source=source,
                target_connection=target_connection,
            ):
                if script.code not in seen_codes:
                    scripts.append(script)
                    seen_codes.add(script.code)

            for script in self._build_role_remediation_scripts(
                request=request,
                source=source,
                target_connection=target_connection,
            ):
                if script.code not in seen_codes:
                    scripts.append(script)
                    seen_codes.add(script.code)

            for script in self._build_directory_grant_remediation_scripts(
                request=request,
                source=source,
                target_connection=target_connection,
            ):
                if script.code not in seen_codes:
                    scripts.append(script)
                    seen_codes.add(script.code)

            for script in self._build_acl_remediation_scripts(
                request=request,
                source=source,
                target_connection=target_connection,
            ):
                if script.code not in seen_codes:
                    scripts.append(script)
                    seen_codes.add(script.code)

            object_storage_script = self._build_object_storage_credential_script(
                source=source,
                target_connection=target_connection,
            )
            if object_storage_script is not None and object_storage_script.code not in seen_codes:
                scripts.append(object_storage_script)
                seen_codes.add(object_storage_script.code)
        except OracleClientError as exc:
            notes.append(
                "SQL remediation pack generation was partial because an additional target lookup failed: "
                f"{exc}"
            )

        if not scripts:
            return None, notes

        summary = (
            f"{len(scripts)} remediation script"
            f"{'' if len(scripts) == 1 else 's'} generated for target-side preparation."
        )
        combined_sql = self._combine_remediation_scripts(scripts)
        return (
            MigrationRemediationPack(
                summary=summary,
                scripts=scripts,
                combined_sql=combined_sql,
            ),
            notes,
        )

    def _script_from_check(
        self,
        check: MigrationCompatibilityCheck,
    ) -> MigrationRemediationScript:
        return MigrationRemediationScript(
            code=check.code,
            label=check.label,
            category=self._category_from_check(check),
            status="READY",
            summary=check.message,
            sql=check.remediation_sql or "",
        )

    @staticmethod
    def _category_from_check(check: MigrationCompatibilityCheck) -> str:
        if check.code.startswith("TARGET_TABLESPACE_"):
            return "TABLESPACE"
        if check.code.startswith("TARGET_SCHEMA_"):
            return "USER"
        if check.code.startswith("TARGET_DATAPUMP_DIRECTORY"):
            return "DIRECTORY"
        return "DIRECTORY"

    def _build_profile_remediation_scripts(
        self,
        *,
        request: MigrationCreate,
        source: OracleSourceMetadata,
        target_connection: OracleConnectionConfig,
    ) -> list[MigrationRemediationScript]:
        schema_names = self._target_schema_names(request, source)
        if not schema_names:
            return []

        source_users = {
            user.username.strip().upper(): user
            for user in source.database_users
            if user.username.strip()
        }
        required_profiles = self._normalize_names(
            [
                source_users[schema_name].profile
                for schema_name in schema_names
                if schema_name in source_users
                and source_users[schema_name].profile
                and self._normalize_text(source_users[schema_name].profile) != "DEFAULT"
            ]
        )
        if not required_profiles:
            return []

        target_profiles = self._adapter.lookup_target_profiles(
            target_connection,
            required_profiles,
        )
        profile_rows = self._section_rows_by_key(source, "profile_definitions")

        scripts: list[MigrationRemediationScript] = []
        for profile_name in required_profiles:
            if profile_name in target_profiles:
                continue
            sql = self._profile_ddl(profile_name, profile_rows.get(profile_name, []))
            scripts.append(
                MigrationRemediationScript(
                    code=f"MISSING_PROFILE_{profile_name}",
                    label=f"Create profile {profile_name}",
                    category="PROFILE",
                    status="READY",
                    summary=(
                        f"Profile '{profile_name}' is referenced by the source schema metadata "
                        "but was not found on the target."
                    ),
                    sql=sql,
                )
            )
        return scripts

    def _build_role_remediation_scripts(
        self,
        *,
        request: MigrationCreate,
        source: OracleSourceMetadata,
        target_connection: OracleConnectionConfig,
    ) -> list[MigrationRemediationScript]:
        schema_names = set(self._target_schema_names(request, source))
        if not schema_names:
            return []

        role_grant_rows = self._section_rows(source, "schema_role_grants")
        required_roles = self._normalize_names(
            [
                self._row_value(row, "GRANTED_ROLE")
                for row in role_grant_rows
                if self._row_value(row, "GRANTEE") in schema_names
            ]
        )
        if not required_roles:
            return []

        target_roles = self._adapter.lookup_target_roles(target_connection, required_roles)
        role_sys_priv_rows = self._section_rows_by_key(source, "role_sys_privs")
        role_object_priv_rows = self._section_rows_by_key(source, "role_object_privs")
        role_role_rows = self._section_rows_by_key(source, "role_granted_roles")

        scripts: list[MigrationRemediationScript] = []
        for role_name in required_roles:
            if role_name in target_roles:
                continue
            scripts.append(
                MigrationRemediationScript(
                    code=f"MISSING_ROLE_{role_name}",
                    label=f"Create role {role_name}",
                    category="ROLE",
                    status="READY",
                    summary=(
                        f"Role '{role_name}' is granted to a source schema but does not exist "
                        "on the target."
                    ),
                    sql=self._role_ddl(
                        role_name,
                        role_sys_priv_rows.get(role_name, []),
                        role_object_priv_rows.get(role_name, []),
                        role_role_rows.get(role_name, []),
                    ),
                )
            )
        return scripts

    def _build_directory_grant_remediation_scripts(
        self,
        *,
        request: MigrationCreate,
        source: OracleSourceMetadata,
        target_connection: OracleConnectionConfig,
    ) -> list[MigrationRemediationScript]:
        grant_requirements = self._directory_grant_requirements(request, source, target_connection)
        if not grant_requirements:
            return []

        directory_names = sorted({directory for directory, _, _ in grant_requirements})
        grantees = sorted({grantee for _, grantee, _ in grant_requirements})
        existing = self._adapter.lookup_target_directory_privileges(
            target_connection,
            directory_names,
            grantees,
        )

        grouped_missing: dict[tuple[str, str], list[str]] = defaultdict(list)
        for requirement in grant_requirements:
            if requirement in existing:
                continue
            grouped_missing[(requirement[0], requirement[1])].append(requirement[2])

        scripts: list[MigrationRemediationScript] = []
        for (directory_name, grantee), privileges in sorted(grouped_missing.items()):
            privileges = sorted(set(privileges))
            sql = "\n".join(
                f'GRANT {privilege} ON DIRECTORY "{directory_name}" TO "{grantee}";'
                for privilege in privileges
            )
            scripts.append(
                MigrationRemediationScript(
                    code=f"DIRECTORY_GRANT_{directory_name}_{grantee}",
                    label=f"Grant directory access on {directory_name} to {grantee}",
                    category="DIRECTORY_GRANT",
                    status="READY",
                    summary=(
                        f"Target directory grants for '{directory_name}' are missing for "
                        f"grantee '{grantee}'."
                    ),
                    sql=sql,
                )
            )
        return scripts

    def _build_acl_remediation_scripts(
        self,
        *,
        request: MigrationCreate,
        source: OracleSourceMetadata,
        target_connection: OracleConnectionConfig,
    ) -> list[MigrationRemediationScript]:
        acl_entries = self._source_acl_requirements(request, source)
        if not acl_entries:
            return []

        existing = self._adapter.lookup_target_network_acl_entries(
            target_connection,
            [entry[0] for entry in acl_entries],
            [entry[3] for entry in acl_entries],
        )

        grouped_missing: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
        for host, lower_port, upper_port, principal, privilege in acl_entries:
            key = (
                host,
                lower_port,
                upper_port,
                principal,
            )
            if (host, lower_port, upper_port, principal, privilege) in existing:
                continue
            grouped_missing[key].append(privilege)

        scripts: list[MigrationRemediationScript] = []
        for (host, lower_port, upper_port, principal), privileges in sorted(
            grouped_missing.items()
        ):
            privileges = sorted(set(privileges))
            scripts.append(
                MigrationRemediationScript(
                    code=(
                        "ACL_"
                        + re.sub(r"[^A-Z0-9_]+", "_", f"{host}_{principal}_{lower_port}_{upper_port}".upper())
                    ),
                    label=f"Append ACL for {principal} on {host}",
                    category="ACL",
                    status="READY",
                    summary=(
                        f"Target ACL entries for principal '{principal}' and host '{host}' "
                        "do not fully match the source."
                    ),
                    sql=self._acl_ddl(host, lower_port, upper_port, principal, privileges),
                )
            )
        return scripts

    def _build_object_storage_credential_script(
        self,
        *,
        source: OracleSourceMetadata,
        target_connection: OracleConnectionConfig,
    ) -> MigrationRemediationScript | None:
        if not self._source_uses_object_storage(source):
            return None

        credential_name = "MIGRATION_OBJECTSTORE_CRED"
        existing_credentials = self._adapter.lookup_target_credentials(
            target_connection,
            [credential_name],
        )
        if credential_name in existing_credentials:
            return None

        return MigrationRemediationScript(
            code="OBJECT_STORAGE_CREDENTIAL_TEMPLATE",
            label="Create object storage credential",
            category="OBJECT_STORAGE_CREDENTIAL",
            status="OPTIONAL",
            summary=(
                "Source metadata indicates Object Storage access patterns. Create a target-side "
                "credential before running Data Pump with object storage URIs."
            ),
            sql=(
                "BEGIN\n"
                "  DBMS_CREDENTIAL.CREATE_CREDENTIAL(\n"
                f"    credential_name => '{credential_name}',\n"
                "    username => '<oci_username_or_swift_user>',\n"
                "    password => '<oci_auth_token_or_secret>'\n"
                "  );\n"
                "END;\n"
                "/"
            ),
        )

    def _directory_grant_requirements(
        self,
        request: MigrationCreate,
        source: OracleSourceMetadata,
        target_connection: OracleConnectionConfig,
    ) -> set[tuple[str, str, str]]:
        requirements: set[tuple[str, str, str]] = set()
        schema_names = set(self._target_schema_names(request, source))

        for row in self._section_rows(source, "external_tables"):
            owner = self._row_value(row, "OWNER")
            directory_name = self._row_value(row, "DEFAULT_DIRECTORY_NAME")
            if not directory_name or (schema_names and owner not in schema_names):
                continue
            requirements.add((directory_name, owner, "READ"))
            requirements.add((directory_name, owner, "WRITE"))

        runtime_grantee = self._normalize_text(target_connection.username)
        if runtime_grantee:
            requirements.add(("DATA_PUMP_DIR", runtime_grantee, "READ"))
            requirements.add(("DATA_PUMP_DIR", runtime_grantee, "WRITE"))

        return requirements

    def _source_acl_requirements(
        self,
        request: MigrationCreate,
        source: OracleSourceMetadata,
    ) -> set[tuple[str, str, str, str, str]]:
        schema_names = set(self._target_schema_names(request, source))
        if not schema_names:
            schema_names = {
                user.username.strip().upper()
                for user in source.database_users
                if user.username.strip()
            }

        acl_entries: set[tuple[str, str, str, str, str]] = set()
        for row in self._section_rows(source, "network_acls"):
            principal = self._row_value(row, "PRINCIPAL")
            host = row.get("HOST", "").strip()
            privilege = self._row_value(row, "PRIVILEGE").lower()
            if not host or not principal or not privilege:
                continue
            if schema_names and principal not in schema_names:
                continue
            acl_entries.add(
                (
                    host,
                    self._row_value(row, "LOWER_PORT"),
                    self._row_value(row, "UPPER_PORT"),
                    principal,
                    privilege,
                )
            )
        return acl_entries

    def _profile_ddl(
        self,
        profile_name: str,
        rows: list[dict[str, str]],
    ) -> str:
        limits = [
            f"  {self._row_value(row, 'RESOURCE_NAME')} {self._row_value(row, 'LIMIT')}"
            for row in rows
            if self._row_value(row, "RESOURCE_NAME") and self._row_value(row, "LIMIT")
        ]
        if not limits:
            limits = ["  SESSIONS_PER_USER UNLIMITED"]
        return f'CREATE PROFILE "{profile_name}" LIMIT\n' + "\n".join(limits) + ";"

    def _role_ddl(
        self,
        role_name: str,
        sys_priv_rows: list[dict[str, str]],
        object_priv_rows: list[dict[str, str]],
        role_grant_rows: list[dict[str, str]],
    ) -> str:
        statements = [f'CREATE ROLE "{role_name}";']

        for row in role_grant_rows:
            granted_role = self._row_value(row, "GRANTED_ROLE")
            if not granted_role:
                continue
            suffix = " WITH ADMIN OPTION" if self._row_value(row, "ADMIN_OPTION") == "YES" else ""
            statements.append(f'GRANT "{granted_role}" TO "{role_name}"{suffix};')

        for row in sys_priv_rows:
            privilege = self._row_value(row, "PRIVILEGE")
            if not privilege:
                continue
            suffix = " WITH ADMIN OPTION" if self._row_value(row, "ADMIN_OPTION") == "YES" else ""
            statements.append(f'GRANT {privilege} TO "{role_name}"{suffix};')

        for row in object_priv_rows:
            privilege = self._row_value(row, "PRIVILEGE")
            owner = self._row_value(row, "OWNER")
            table_name = self._row_value(row, "TABLE_NAME")
            if not privilege or not owner or not table_name:
                continue
            suffix = " WITH GRANT OPTION" if self._row_value(row, "GRANTABLE") == "YES" else ""
            statements.append(
                f'GRANT {privilege} ON "{owner}"."{table_name}" TO "{role_name}"{suffix};'
            )

        return "\n".join(statements)

    def _acl_ddl(
        self,
        host: str,
        lower_port: str,
        upper_port: str,
        principal: str,
        privileges: list[str],
    ) -> str:
        port_lines: list[str] = []
        if lower_port:
            port_lines.append(f"    lower_port => {lower_port},")
        if upper_port:
            port_lines.append(f"    upper_port => {upper_port},")

        privilege_list = ", ".join(f"'{privilege}'" for privilege in privileges)
        port_block = "\n".join(port_lines)
        if port_block:
            port_block += "\n"

        return (
            "BEGIN\n"
            "  DBMS_NETWORK_ACL_ADMIN.APPEND_HOST_ACE(\n"
            f"    host => '{host}',\n"
            f"{port_block}"
            "    ace  => xs$ace_type(\n"
            f"              privilege_list => xs$name_list({privilege_list}),\n"
            f"              principal_name => '{principal}',\n"
            "              principal_type => xs_acl.ptype_db\n"
            "            )\n"
            "  );\n"
            "END;\n"
            "/"
        )

    def _combine_remediation_scripts(
        self,
        scripts: list[MigrationRemediationScript],
    ) -> str:
        return "\n\n".join(
            [
                f"-- {script.label}\n-- {script.summary}\n{script.sql}"
                for script in scripts
            ]
        )

    def _target_schema_names(
        self,
        request: MigrationCreate,
        source: OracleSourceMetadata,
    ) -> list[str]:
        names = self._normalize_names(request.scope.schema_names)
        if names:
            return names
        return [
            user.username.strip().upper()
            for user in source.database_users
            if user.username.strip()
        ]

    @staticmethod
    def _row_value(row: dict[str, str], key: str) -> str:
        return row.get(key, "").strip().upper()

    def _section_rows(
        self,
        source: OracleSourceMetadata,
        section_key: str,
    ) -> list[dict[str, str]]:
        for section in source.discovery_sections:
            if section.key == section_key:
                return section.rows
        return []

    def _section_rows_by_key(
        self,
        source: OracleSourceMetadata,
        section_key: str,
        name_key: str | None = None,
    ) -> dict[str, list[dict[str, str]]]:
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        rows = self._section_rows(source, section_key)
        if not rows:
            return grouped

        if name_key is None:
            name_key = "PROFILE" if section_key == "profile_definitions" else "ROLE"

        for row in rows:
            key = self._row_value(row, name_key)
            if key:
                grouped[key].append(row)
        return grouped

    def _source_uses_object_storage(self, source: OracleSourceMetadata) -> bool:
        for row in self._section_rows(source, "network_acls"):
            host = row.get("HOST", "").strip().lower()
            if "objectstorage." in host:
                return True
        return False

    def _apply_source_metadata(
        self,
        request: MigrationCreate,
        metadata: OracleSourceMetadata | None,
        prefer_collected_values: bool,
    ) -> tuple[MigrationCreate, list[str]]:
        if metadata is None:
            return request, []

        source_updates: dict[str, object] = {}
        applied_fields: list[str] = []
        metadata_payload = metadata.model_dump(
            exclude_none=True,
            exclude={
                "collected_at",
                "inventory_summary",
                "schema_inventory",
                "db_name",
                "host_name",
                "edition",
                "endianness",
                "nchar_character_set",
                "pdbs",
                "database_users",
                "tablespaces",
                "invalid_objects_by_schema",
                "discovery_summary",
                "discovery_sections",
            },
        )
        current_source = request.source.model_dump()

        for field_name, metadata_value in metadata_payload.items():
            current_value = current_source.get(field_name)
            should_apply = prefer_collected_values or self._is_missing_value(current_value)
            if should_apply and metadata_value is not None and current_value != metadata_value:
                source_updates[field_name] = metadata_value
                applied_fields.append(field_name)

        if not source_updates:
            return request, applied_fields

        return (
            request.model_copy(
                update={
                    "source": request.source.model_copy(update=source_updates),
                }
            ),
            applied_fields,
        )

    @staticmethod
    def _extract_major_version(value: str | None) -> int | None:
        if value is None:
            return None
        match = re.search(r"(\d+)", value)
        if match is None:
            return None
        return int(match.group(1))

    @staticmethod
    def _normalize_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @staticmethod
    def _is_missing_value(value: object) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        return False

    @staticmethod
    def _collect_field_names(metadata: OracleSourceMetadata) -> list[str]:
        fields: list[str] = []
        for field_name, value in metadata.model_dump(exclude={"collected_at"}).items():
            if value is None:
                continue
            if isinstance(value, list) and not value:
                continue
            fields.append(field_name)
        return fields

    @staticmethod
    def _normalize_names(values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            cleaned = value.strip().upper()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized


oracle_metadata_service = OracleMetadataService()
