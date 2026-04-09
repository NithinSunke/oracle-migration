from __future__ import annotations

import re

from backend.app.adapters.oracle import OracleClientError, OracleMetadataAdapter
from backend.app.schemas.migration import MigrationCreate, OracleConnectionConfig
from backend.app.schemas.oracle import (
    MetadataEnrichmentSummary,
    MigrationCompatibilityAssessment,
    MigrationCompatibilityCheck,
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

        return MigrationCompatibilityAssessment(
            status=status,
            summary=summary,
            source_connection_status="CONNECTED",
            target_connection_status="CONNECTED",
            source=source,
            target=target,
            checks=checks,
            blockers=list(dict.fromkeys(blockers)),
            warnings=list(dict.fromkeys(warnings)),
            notes=list(dict.fromkeys((source_notes or []) + (source_errors or []))),
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
            if source_user is not None or schema_name in source_owners:
                continue

            message = (
                f"Schema '{schema_name}' was requested for schema migration, but it was not found in the collected source metadata."
            )
            checks.append(
                MigrationCompatibilityCheck(
                    code=f"SOURCE_SCHEMA_{schema_name}",
                    label=f"Source schema {schema_name}",
                    status="FAIL",
                    message=message,
                    source_value=schema_name,
                    target_value=None,
                )
            )
            blockers.append(message)

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

        for schema_name in schema_names:
            target_user = target_users.get(schema_name)
            source_user = requested_source_users.get(schema_name)
            if target_user is None:
                ddl = self._create_user_ddl(schema_name, source_user)
                message = (
                    f"Schema '{schema_name}' does not exist on the target. This is acceptable if the import will create the user from the dump metadata; pre-create it only when you want to control the target definition ahead of time."
                )
                checks.append(
                    MigrationCompatibilityCheck(
                        code=f"TARGET_SCHEMA_{schema_name}",
                        label=f"Target schema {schema_name}",
                        status="INFO",
                        message=message,
                        source_value=schema_name,
                        target_value="Missing",
                        remediation_sql=ddl,
                    )
                )
                continue

            if (
                source_user is not None
                and (
                    self._normalize_text(source_user.default_tablespace)
                    != self._normalize_text(target_user.default_tablespace)
                    or self._normalize_text(source_user.temporary_tablespace)
                    != self._normalize_text(target_user.temporary_tablespace)
                )
            ):
                ddl = self._alter_user_tablespace_ddl(schema_name, source_user)
                message = (
                    f"Schema '{schema_name}' exists on the target, but its default or temporary tablespace does not match the source metadata."
                )
                checks.append(
                    MigrationCompatibilityCheck(
                        code=f"TARGET_SCHEMA_{schema_name}",
                        label=f"Target schema {schema_name}",
                        status="WARN",
                        message=message,
                        source_value=self._format_user_tablespaces(source_user),
                        target_value=self._format_user_tablespaces(target_user),
                        remediation_sql=ddl,
                    )
                )
                warnings.append(message)
                continue

            checks.append(
                MigrationCompatibilityCheck(
                    code=f"TARGET_SCHEMA_{schema_name}",
                    label=f"Target schema {schema_name}",
                    status="PASS",
                    message="Schema already exists on the target.",
                    source_value=schema_name,
                    target_value=schema_name,
                )
            )

        return checks, blockers, warnings

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
