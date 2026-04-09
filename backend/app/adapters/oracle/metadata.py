from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from backend.app.adapters.oracle.client import OracleDatabaseClient
from backend.app.schemas.migration import OracleConnectionConfig
from backend.app.schemas.oracle import (
    OracleDiscoverySection,
    OracleDiscoverySummaryItem,
    OracleInvalidObjectOwnerSummary,
    MetadataEnrichmentSummary,
    OracleObjectInventorySummary,
    OraclePdbInventoryEntry,
    OracleSchemaInventoryEntry,
    OracleSourceMetadata,
    OracleTablespaceInventoryEntry,
    OracleTargetMetadata,
    OracleUserInventoryEntry,
)

DEFAULT_DISCOVERY_ROW_LIMIT = 200


class OracleMetadataAdapter:
    def __init__(self, client_factory: Callable[[OracleConnectionConfig], OracleDatabaseClient] | None = None) -> None:
        self._client_factory = client_factory or OracleDatabaseClient

    @staticmethod
    def _non_default_dba_owner_filter(owner_column: str = "owner") -> str:
        return f"""
            {owner_column} <> 'PUBLIC'
            AND EXISTS (
                SELECT 1
                FROM dba_users u
                WHERE u.username = {owner_column}
                  AND u.oracle_maintained = 'N'
            )
        """

    @staticmethod
    def _non_default_cdb_owner_filter(
        owner_column: str = "owner",
        con_id_column: str = "con_id",
    ) -> str:
        return f"""
            {owner_column} <> 'PUBLIC'
            AND EXISTS (
                SELECT 1
                FROM cdb_users u
                WHERE u.con_id = {con_id_column}
                  AND u.username = {owner_column}
                  AND u.oracle_maintained = 'N'
            )
        """

    def collect_source_metadata(
        self,
        connection: OracleConnectionConfig,
    ) -> MetadataEnrichmentSummary:
        metadata = OracleSourceMetadata(collected_at=datetime.now(timezone.utc))
        collected_fields: list[str] = []
        errors: list[str] = []

        with self._client_factory(connection).connect() as oracle_connection:
            with oracle_connection.cursor() as cursor:
                metadata.db_name = self._query_scalar(
                    cursor,
                    "db_name",
                    "SELECT name FROM v$database",
                    errors,
                )
                metadata.host_name = self._query_scalar(
                    cursor,
                    "host_name",
                    "SELECT host_name FROM v$instance",
                    errors,
                )
                metadata.edition = self._query_scalar(
                    cursor,
                    "edition",
                    "SELECT banner_full FROM v$version WHERE banner_full LIKE 'Oracle Database %' FETCH FIRST 1 ROWS ONLY",
                    errors,
                )
                metadata.endianness = self._query_scalar(
                    cursor,
                    "endianness",
                    "SELECT endian_format FROM v$transportable_platform WHERE platform_name = (SELECT platform_name FROM v$database)",
                    errors,
                )
                metadata.oracle_version = self._query_scalar(
                    cursor,
                    "oracle_version",
                    "SELECT version FROM v$instance",
                    errors,
                )
                metadata.deployment_type = self._query_scalar(
                    cursor,
                    "deployment_type",
                    "SELECT CASE WHEN cdb = 'YES' THEN 'CDB_PDB' ELSE 'NON_CDB' END FROM v$database",
                    errors,
                )
                metadata.database_size_gb = self._query_scalar(
                    cursor,
                    "database_size_gb",
                    (
                        """
                        SELECT ROUND(SUM(bytes) / POWER(1024, 3), 2)
                        FROM (
                            SELECT bytes FROM cdb_data_files
                            UNION ALL
                            SELECT bytes FROM cdb_temp_files
                        )
                        """
                        if metadata.deployment_type == "CDB_PDB"
                        else """
                        SELECT ROUND(SUM(bytes) / POWER(1024, 3), 2)
                        FROM (
                            SELECT bytes FROM dba_data_files
                            UNION ALL
                            SELECT bytes FROM dba_temp_files
                        )
                        """
                    ),
                    errors,
                    transform=lambda value: float(value) if value is not None else None,
                )
                metadata.archivelog_enabled = self._query_scalar(
                    cursor,
                    "archivelog_enabled",
                    "SELECT CASE WHEN log_mode = 'ARCHIVELOG' THEN 1 ELSE 0 END FROM v$database",
                    errors,
                    transform=lambda value: bool(int(value)) if value is not None else None,
                )
                metadata.platform = self._query_scalar(
                    cursor,
                    "platform",
                    "SELECT platform_name FROM v$database",
                    errors,
                )
                metadata.rac_enabled = self._query_scalar(
                    cursor,
                    "rac_enabled",
                    "SELECT CASE WHEN COUNT(*) > 1 THEN 1 ELSE 0 END FROM gv$instance",
                    errors,
                    transform=lambda value: bool(int(value)) if value is not None else None,
                )
                metadata.tde_enabled = self._query_scalar(
                    cursor,
                    "tde_enabled",
                    """
                    SELECT CASE
                        WHEN UPPER(status) IN ('OPEN', 'OPEN_NO_MASTER_KEY', 'AUTOLOGIN') THEN 1
                        ELSE 0
                    END
                    FROM v$encryption_wallet
                    FETCH FIRST 1 ROWS ONLY
                    """,
                    errors,
                    transform=lambda value: bool(int(value)) if value is not None else None,
                )
                metadata.character_set = self._query_scalar(
                    cursor,
                    "character_set",
                    """
                    SELECT value
                    FROM nls_database_parameters
                    WHERE parameter = 'NLS_CHARACTERSET'
                    """,
                    errors,
                )
                metadata.nchar_character_set = self._query_scalar(
                    cursor,
                    "nchar_character_set",
                    """
                    SELECT value
                    FROM nls_database_parameters
                    WHERE parameter = 'NLS_NCHAR_CHARACTERSET'
                    """,
                    errors,
                )
                metadata.inventory_summary = self._query_inventory_summary(
                    cursor,
                    errors,
                    include_all_containers=metadata.deployment_type == "CDB_PDB",
                )
                if metadata.deployment_type == "CDB_PDB":
                    metadata.pdbs = self._query_pdb_inventory(cursor, errors)
                    metadata.database_users = self._query_cdb_users(cursor, errors)
                    metadata.tablespaces = self._query_cdb_tablespaces(cursor, errors)
                    metadata.invalid_objects_by_schema = self._query_cdb_invalid_objects_by_schema(
                        cursor,
                        errors,
                    )
                    metadata.schema_inventory = self._query_cdb_schema_inventory(cursor, errors)
                else:
                    metadata.database_users = self._query_dba_users(cursor, errors)
                    metadata.tablespaces = self._query_dba_tablespaces(cursor, errors)
                    metadata.schema_inventory = self._query_schema_inventory(cursor, errors)
                metadata.discovery_sections = self._query_discovery_sections(
                    cursor,
                    metadata,
                    errors,
                )
                metadata.discovery_summary = self._build_discovery_summary(metadata)

        for field_name, value in metadata.model_dump(exclude={"collected_at"}).items():
            if value is not None:
                if isinstance(value, list) and not value:
                    continue
                collected_fields.append(field_name)

        status = "COLLECTED" if not errors else "PARTIAL"
        notes = []
        if errors:
            notes.append(
                "Recommendation enrichment used available Oracle metadata and ignored fields that could not be queried."
            )

        return MetadataEnrichmentSummary(
            status=status,
            source=metadata,
            collected_fields=collected_fields,
            applied_fields=[],
            errors=errors,
            notes=notes,
        )

    def collect_target_metadata(
        self,
        connection: OracleConnectionConfig,
    ) -> OracleTargetMetadata:
        metadata = OracleTargetMetadata(collected_at=datetime.now(timezone.utc))
        errors: list[str] = []

        with self._client_factory(connection).connect() as oracle_connection:
            with oracle_connection.cursor() as cursor:
                metadata.db_name = self._query_scalar(
                    cursor,
                    "db_name",
                    "SELECT name FROM v$database",
                    errors,
                )
                metadata.db_unique_name = self._query_scalar(
                    cursor,
                    "db_unique_name",
                    "SELECT db_unique_name FROM v$database",
                    errors,
                )
                metadata.global_name = self._query_scalar(
                    cursor,
                    "global_name",
                    "SELECT global_name FROM global_name",
                    errors,
                )
                metadata.host_name = self._query_scalar(
                    cursor,
                    "host_name",
                    "SELECT host_name FROM v$instance",
                    errors,
                )
                metadata.edition = self._query_scalar(
                    cursor,
                    "edition",
                    "SELECT banner_full FROM v$version WHERE banner_full LIKE 'Oracle Database %' FETCH FIRST 1 ROWS ONLY",
                    errors,
                )
                metadata.endianness = self._query_scalar(
                    cursor,
                    "endianness",
                    "SELECT endian_format FROM v$transportable_platform WHERE platform_name = (SELECT platform_name FROM v$database)",
                    errors,
                )
                metadata.oracle_version = self._query_scalar(
                    cursor,
                    "oracle_version",
                    "SELECT version FROM v$instance",
                    errors,
                )
                metadata.deployment_type = self._query_scalar(
                    cursor,
                    "deployment_type",
                    "SELECT CASE WHEN cdb = 'YES' THEN 'CDB_PDB' ELSE 'NON_CDB' END FROM v$database",
                    errors,
                )
                metadata.database_role = self._query_scalar(
                    cursor,
                    "database_role",
                    "SELECT database_role FROM v$database",
                    errors,
                )
                metadata.open_mode = self._query_scalar(
                    cursor,
                    "open_mode",
                    "SELECT open_mode FROM v$database",
                    errors,
                )
                metadata.database_size_gb = self._query_scalar(
                    cursor,
                    "database_size_gb",
                    (
                        """
                        SELECT ROUND(SUM(bytes) / POWER(1024, 3), 2)
                        FROM (
                            SELECT bytes FROM cdb_data_files
                            UNION ALL
                            SELECT bytes FROM cdb_temp_files
                        )
                        """
                        if metadata.deployment_type == "CDB_PDB"
                        else """
                        SELECT ROUND(SUM(bytes) / POWER(1024, 3), 2)
                        FROM (
                            SELECT bytes FROM dba_data_files
                            UNION ALL
                            SELECT bytes FROM dba_temp_files
                        )
                        """
                    ),
                    errors,
                    transform=lambda value: float(value) if value is not None else None,
                )
                metadata.archivelog_enabled = self._query_scalar(
                    cursor,
                    "archivelog_enabled",
                    "SELECT CASE WHEN log_mode = 'ARCHIVELOG' THEN 1 ELSE 0 END FROM v$database",
                    errors,
                    transform=lambda value: bool(int(value)) if value is not None else None,
                )
                metadata.platform = self._query_scalar(
                    cursor,
                    "platform",
                    "SELECT platform_name FROM v$database",
                    errors,
                )
                metadata.rac_enabled = self._query_scalar(
                    cursor,
                    "rac_enabled",
                    "SELECT CASE WHEN COUNT(*) > 1 THEN 1 ELSE 0 END FROM gv$instance",
                    errors,
                    transform=lambda value: bool(int(value)) if value is not None else None,
                )
                metadata.tde_enabled = self._query_scalar(
                    cursor,
                    "tde_enabled",
                    """
                    SELECT CASE
                        WHEN UPPER(status) IN ('OPEN', 'OPEN_NO_MASTER_KEY', 'AUTOLOGIN') THEN 1
                        ELSE 0
                    END
                    FROM v$encryption_wallet
                    FETCH FIRST 1 ROWS ONLY
                    """,
                    errors,
                    transform=lambda value: bool(int(value)) if value is not None else None,
                )
                metadata.character_set = self._query_scalar(
                    cursor,
                    "character_set",
                    """
                    SELECT value
                    FROM nls_database_parameters
                    WHERE parameter = 'NLS_CHARACTERSET'
                    """,
                    errors,
                )
                metadata.nchar_character_set = self._query_scalar(
                    cursor,
                    "nchar_character_set",
                    """
                    SELECT value
                    FROM nls_database_parameters
                    WHERE parameter = 'NLS_NCHAR_CHARACTERSET'
                    """,
                    errors,
                )

        return metadata

    def lookup_target_users(
        self,
        connection: OracleConnectionConfig,
        usernames: list[str],
    ) -> list[OracleUserInventoryEntry]:
        normalized_usernames = self._normalize_names(usernames)
        if not normalized_usernames:
            return []

        with self._client_factory(connection).connect() as oracle_connection:
            with oracle_connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        SYS_CONTEXT('USERENV', 'DB_NAME') AS container_name,
                        username,
                        'Regular' AS user_type,
                        CASE WHEN oracle_maintained = 'Y' THEN 1 ELSE 0 END AS oracle_maintained,
                        account_status,
                        created,
                        expiry_date,
                        profile,
                        password_versions,
                        default_tablespace,
                        temporary_tablespace
                    FROM dba_users
                    WHERE username IN ({self._sql_name_list(normalized_usernames)})
                    ORDER BY username
                    """
                )
                rows = cursor.fetchall()

        return [
            OracleUserInventoryEntry(
                container_name=str(row[0]),
                container_type="NON_CDB",
                con_id=0,
                username=str(row[1]),
                user_type=str(row[2]),
                oracle_maintained=bool(int(row[3] or 0)),
                account_status=str(row[4]) if row[4] is not None else None,
                created=row[5],
                expiry_date=row[6],
                profile=str(row[7]) if row[7] is not None else None,
                password_versions=str(row[8]) if row[8] is not None else None,
                default_tablespace=str(row[9]) if row[9] is not None else None,
                temporary_tablespace=str(row[10]) if row[10] is not None else None,
            )
            for row in rows or []
        ]

    def lookup_target_tablespaces(
        self,
        connection: OracleConnectionConfig,
        tablespace_names: list[str],
    ) -> list[OracleTablespaceInventoryEntry]:
        normalized_names = self._normalize_names(tablespace_names)
        if not normalized_names:
            return []

        with self._client_factory(connection).connect() as oracle_connection:
            with oracle_connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        SYS_CONTEXT('USERENV', 'DB_NAME') AS container_name,
                        tablespace_name,
                        contents,
                        extent_management,
                        segment_space_management,
                        CASE WHEN bigfile = 'YES' THEN 1 ELSE 0 END AS bigfile,
                        status,
                        block_size
                    FROM dba_tablespaces
                    WHERE tablespace_name IN ({self._sql_name_list(normalized_names)})
                    ORDER BY tablespace_name
                    """
                )
                rows = cursor.fetchall()

        return [
            OracleTablespaceInventoryEntry(
                container_name=str(row[0]),
                container_type="NON_CDB",
                con_id=0,
                tablespace_name=str(row[1]),
                contents=str(row[2]) if row[2] is not None else None,
                extent_management=str(row[3]) if row[3] is not None else None,
                segment_space_management=str(row[4]) if row[4] is not None else None,
                bigfile=bool(int(row[5])) if row[5] is not None else None,
                status=str(row[6]) if row[6] is not None else None,
                block_size=int(row[7]) if row[7] is not None else None,
            )
            for row in rows or []
        ]

    @staticmethod
    def _query_scalar(
        cursor: object,
        field_name: str,
        query: str,
        errors: list[str],
        transform: Callable[[object], object] | None = None,
    ) -> object:
        try:
            cursor.execute(query)
            row = cursor.fetchone()
        except Exception:
            errors.append(f"{field_name} could not be collected from Oracle.")
            return None

        if not row:
            return None

        value = row[0]
        if transform is not None:
            try:
                return transform(value)
            except Exception:
                errors.append(f"{field_name} returned an unexpected Oracle value.")
                return None
        return value

    def _query_inventory_summary(
        self,
        cursor: object,
        errors: list[str],
        include_all_containers: bool = False,
    ) -> OracleObjectInventorySummary | None:
        owner_filter = (
            self._non_default_cdb_owner_filter(owner_column="owner", con_id_column="con_id")
            if include_all_containers
            else self._non_default_dba_owner_filter(owner_column="owner")
        )
        try:
            cursor.execute(
                f"""
                SELECT
                    COUNT(DISTINCT owner),
                    COUNT(*),
                    SUM(CASE WHEN object_type = 'TABLE' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN object_type = 'INDEX' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN object_type = 'VIEW' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN object_type = 'MATERIALIZED VIEW' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN object_type = 'SEQUENCE' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN object_type = 'PROCEDURE' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN object_type = 'FUNCTION' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN object_type = 'PACKAGE' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN object_type = 'TRIGGER' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN status <> 'VALID' THEN 1 ELSE 0 END)
                FROM {"cdb_objects" if include_all_containers else "dba_objects"}
                WHERE {owner_filter}
                {"AND con_id <> 2" if include_all_containers else ""}
                """
            )
            row = cursor.fetchone()
        except Exception:
            errors.append("inventory_summary could not be collected from Oracle.")
            return None

        if not row:
            return None

        return OracleObjectInventorySummary(
            schema_count=int(row[0] or 0),
            total_objects=int(row[1] or 0),
            total_tables=int(row[2] or 0),
            total_indexes=int(row[3] or 0),
            total_views=int(row[4] or 0),
            total_materialized_views=int(row[5] or 0),
            total_sequences=int(row[6] or 0),
            total_procedures=int(row[7] or 0),
            total_functions=int(row[8] or 0),
            total_packages=int(row[9] or 0),
            total_triggers=int(row[10] or 0),
            invalid_object_count=int(row[11] or 0),
        )

    def _query_pdb_inventory(
        self,
        cursor: object,
        errors: list[str],
    ) -> list[OraclePdbInventoryEntry]:
        service_names_by_pdb: dict[str, list[str]] = {}
        try:
            cursor.execute(
                """
                SELECT pdb, name
                FROM cdb_services
                WHERE pdb IS NOT NULL
                ORDER BY pdb, name
                """
            )
            for pdb_name, service_name in cursor.fetchall() or []:
                if pdb_name is None or service_name is None:
                    continue
                service_names_by_pdb.setdefault(str(pdb_name), []).append(str(service_name))
        except Exception:
            errors.append("pdb_services could not be collected from Oracle.")

        try:
            cursor.execute(
                """
                SELECT
                    con_id,
                    name,
                    open_mode,
                    open_time,
                    ROUND(total_size / POWER(1024, 3), 2)
                FROM v$pdbs
                WHERE name <> 'PDB$SEED'
                ORDER BY con_id
                """
            )
            rows = cursor.fetchall()
        except Exception:
            errors.append("pdb_inventory could not be collected from Oracle.")
            return []

        return [
            OraclePdbInventoryEntry(
                con_id=int(row[0] or 0),
                name=str(row[1]),
                open_mode=str(row[2]) if row[2] is not None else None,
                open_time=row[3],
                total_size_gb=float(row[4]) if row[4] is not None else None,
                service_names=service_names_by_pdb.get(str(row[1]), []),
            )
            for row in rows or []
        ]

    def _query_cdb_users(
        self,
        cursor: object,
        errors: list[str],
    ) -> list[OracleUserInventoryEntry]:
        try:
            cursor.execute(
                """
                SELECT
                    vc.name AS container_name,
                    u.con_id,
                    u.username,
                    CASE
                        WHEN u.oracle_maintained = 'Y' THEN 'Oracle Managed'
                        WHEN u.common = 'YES' THEN 'Common User'
                        ELSE 'Regular'
                    END AS user_type,
                    CASE WHEN u.oracle_maintained = 'Y' THEN 1 ELSE 0 END AS oracle_maintained,
                    u.account_status,
                    u.created,
                    u.expiry_date,
                    u.profile,
                    u.password_versions,
                    u.default_tablespace,
                    u.temporary_tablespace
                FROM cdb_users u
                JOIN v$containers vc ON vc.con_id = u.con_id
                WHERE vc.name <> 'PDB$SEED'
                  AND u.oracle_maintained = 'N'
                  AND u.username <> 'PUBLIC'
                ORDER BY u.con_id, u.username
                """
            )
            rows = cursor.fetchall()
        except Exception:
            errors.append("database_users could not be collected from Oracle.")
            return []

        users: list[OracleUserInventoryEntry] = []
        for row in rows or []:
            container_name = str(row[0])
            users.append(
                OracleUserInventoryEntry(
                    container_name=container_name,
                    container_type=self._container_type(container_name),
                    con_id=int(row[1] or 0),
                    username=str(row[2]),
                    user_type=str(row[3]),
                    oracle_maintained=bool(int(row[4] or 0)),
                    account_status=str(row[5]) if row[5] is not None else None,
                    created=row[6],
                    expiry_date=row[7],
                    profile=str(row[8]) if row[8] is not None else None,
                    password_versions=str(row[9]) if row[9] is not None else None,
                    default_tablespace=str(row[10]) if row[10] is not None else None,
                    temporary_tablespace=str(row[11]) if row[11] is not None else None,
                )
            )
        return users

    def _query_dba_users(
        self,
        cursor: object,
        errors: list[str],
    ) -> list[OracleUserInventoryEntry]:
        try:
            cursor.execute(
                """
                SELECT
                    SYS_CONTEXT('USERENV', 'DB_NAME') AS container_name,
                    username,
                    'Regular' AS user_type,
                    CASE WHEN oracle_maintained = 'Y' THEN 1 ELSE 0 END AS oracle_maintained,
                    account_status,
                    created,
                    expiry_date,
                    profile,
                    password_versions,
                    default_tablespace,
                    temporary_tablespace
                FROM dba_users
                WHERE oracle_maintained = 'N'
                  AND username <> 'PUBLIC'
                ORDER BY username
                """
            )
            rows = cursor.fetchall()
        except Exception:
            errors.append("database_users could not be collected from Oracle.")
            return []

        return [
            OracleUserInventoryEntry(
                container_name=str(row[0]),
                container_type="NON_CDB",
                con_id=0,
                username=str(row[1]),
                user_type=str(row[2]),
                oracle_maintained=bool(int(row[3] or 0)),
                account_status=str(row[4]) if row[4] is not None else None,
                created=row[5],
                expiry_date=row[6],
                profile=str(row[7]) if row[7] is not None else None,
                password_versions=str(row[8]) if row[8] is not None else None,
                default_tablespace=str(row[9]) if row[9] is not None else None,
                temporary_tablespace=str(row[10]) if row[10] is not None else None,
            )
            for row in rows or []
        ]

    def _query_cdb_tablespaces(
        self,
        cursor: object,
        errors: list[str],
    ) -> list[OracleTablespaceInventoryEntry]:
        try:
            cursor.execute(
                """
                SELECT
                    vc.name AS container_name,
                    t.con_id,
                    t.tablespace_name,
                    t.contents,
                    t.extent_management,
                    t.segment_space_management,
                    CASE WHEN t.bigfile = 'YES' THEN 1 ELSE 0 END AS bigfile,
                    t.status,
                    t.block_size,
                    ROUND((utm.used_space * t.block_size) / POWER(1024, 2), 2) AS used_mb,
                    ROUND(((utm.tablespace_size - utm.used_space) * t.block_size) / POWER(1024, 2), 2) AS free_mb,
                    ROUND((utm.tablespace_size * t.block_size) / POWER(1024, 2), 2) AS total_mb,
                    ROUND(100 - utm.used_percent, 2) AS pct_free,
                    COALESCE(df.max_size_mb, tf.max_size_mb) AS max_size_mb,
                    CASE WHEN ets.encryptionalg IS NOT NULL THEN 1 ELSE 0 END AS encrypted
                FROM cdb_tablespaces t
                JOIN v$containers vc
                    ON vc.con_id = t.con_id
                LEFT JOIN cdb_tablespace_usage_metrics utm
                    ON utm.con_id = t.con_id
                   AND utm.tablespace_name = t.tablespace_name
                LEFT JOIN (
                    SELECT con_id, tablespace_name, ROUND(SUM(maxbytes) / POWER(1024, 2), 2) AS max_size_mb
                    FROM cdb_data_files
                    GROUP BY con_id, tablespace_name
                ) df
                    ON df.con_id = t.con_id
                   AND df.tablespace_name = t.tablespace_name
                LEFT JOIN (
                    SELECT con_id, tablespace_name, ROUND(SUM(maxbytes) / POWER(1024, 2), 2) AS max_size_mb
                    FROM cdb_temp_files
                    GROUP BY con_id, tablespace_name
                ) tf
                    ON tf.con_id = t.con_id
                   AND tf.tablespace_name = t.tablespace_name
                LEFT JOIN (
                    SELECT vt.con_id, vt.name AS tablespace_name, MAX(ets.encryptionalg) AS encryptionalg
                    FROM v$tablespace vt
                    JOIN v$encrypted_tablespaces ets
                      ON ets.con_id = vt.con_id
                     AND ets.ts# = vt.ts#
                    GROUP BY vt.con_id, vt.name
                ) ets
                    ON ets.con_id = t.con_id
                   AND ets.tablespace_name = t.tablespace_name
                WHERE vc.name <> 'PDB$SEED'
                ORDER BY t.con_id, t.tablespace_name
                """
            )
            rows = cursor.fetchall()
        except Exception:
            errors.append("tablespaces could not be collected from Oracle.")
            return []

        tablespaces: list[OracleTablespaceInventoryEntry] = []
        for row in rows or []:
            container_name = str(row[0])
            tablespaces.append(
                OracleTablespaceInventoryEntry(
                    container_name=container_name,
                    container_type=self._container_type(container_name),
                    con_id=int(row[1] or 0),
                    tablespace_name=str(row[2]),
                    contents=str(row[3]) if row[3] is not None else None,
                    extent_management=str(row[4]) if row[4] is not None else None,
                    segment_space_management=str(row[5]) if row[5] is not None else None,
                    bigfile=bool(int(row[6])) if row[6] is not None else None,
                    status=str(row[7]) if row[7] is not None else None,
                    block_size=int(row[8]) if row[8] is not None else None,
                    used_mb=float(row[9]) if row[9] is not None else None,
                    free_mb=float(row[10]) if row[10] is not None else None,
                    total_mb=float(row[11]) if row[11] is not None else None,
                    pct_free=float(row[12]) if row[12] is not None else None,
                    max_size_mb=float(row[13]) if row[13] is not None else None,
                    encrypted=bool(int(row[14])) if row[14] is not None else None,
                )
            )
        return tablespaces

    def _query_dba_tablespaces(
        self,
        cursor: object,
        errors: list[str],
    ) -> list[OracleTablespaceInventoryEntry]:
        try:
            cursor.execute(
                """
                SELECT
                    SYS_CONTEXT('USERENV', 'DB_NAME') AS container_name,
                    tablespace_name,
                    contents,
                    extent_management,
                    segment_space_management,
                    CASE WHEN bigfile = 'YES' THEN 1 ELSE 0 END AS bigfile,
                    status,
                    block_size
                FROM dba_tablespaces
                ORDER BY tablespace_name
                """
            )
            rows = cursor.fetchall()
        except Exception:
            errors.append("tablespaces could not be collected from Oracle.")
            return []

        return [
            OracleTablespaceInventoryEntry(
                container_name=str(row[0]),
                container_type="NON_CDB",
                con_id=0,
                tablespace_name=str(row[1]),
                contents=str(row[2]) if row[2] is not None else None,
                extent_management=str(row[3]) if row[3] is not None else None,
                segment_space_management=str(row[4]) if row[4] is not None else None,
                bigfile=bool(int(row[5])) if row[5] is not None else None,
                status=str(row[6]) if row[6] is not None else None,
                block_size=int(row[7]) if row[7] is not None else None,
            )
            for row in rows or []
        ]

    def _query_cdb_invalid_objects_by_schema(
        self,
        cursor: object,
        errors: list[str],
    ) -> list[OracleInvalidObjectOwnerSummary]:
        owner_filter = self._non_default_cdb_owner_filter(
            owner_column="o.owner",
            con_id_column="o.con_id",
        )
        try:
            cursor.execute(
                f"""
                SELECT
                    vc.name AS container_name,
                    o.con_id,
                    o.owner,
                    COUNT(*) AS invalid_object_count
                FROM cdb_objects o
                JOIN v$containers vc ON vc.con_id = o.con_id
                WHERE vc.name <> 'PDB$SEED'
                  AND o.status <> 'VALID'
                  AND {owner_filter}
                GROUP BY vc.name, o.con_id, o.owner
                ORDER BY COUNT(*) DESC, vc.name, o.owner
                """
            )
            rows = cursor.fetchall()
        except Exception:
            errors.append("invalid_objects_by_schema could not be collected from Oracle.")
            return []

        summaries: list[OracleInvalidObjectOwnerSummary] = []
        for row in rows or []:
            container_name = str(row[0])
            summaries.append(
                OracleInvalidObjectOwnerSummary(
                    container_name=container_name,
                    container_type=self._container_type(container_name),
                    con_id=int(row[1] or 0),
                    owner=str(row[2]),
                    invalid_object_count=int(row[3] or 0),
                )
            )
        return summaries

    def _query_schema_inventory(
        self,
        cursor: object,
        errors: list[str],
    ) -> list[OracleSchemaInventoryEntry]:
        owner_filter = self._non_default_dba_owner_filter(owner_column="owner")
        try:
            cursor.execute(
                f"""
                SELECT
                    owner,
                    COUNT(*) AS object_count,
                    SUM(CASE WHEN object_type = 'TABLE' THEN 1 ELSE 0 END) AS table_count,
                    SUM(CASE WHEN object_type = 'INDEX' THEN 1 ELSE 0 END) AS index_count,
                    SUM(CASE WHEN object_type = 'VIEW' THEN 1 ELSE 0 END) AS view_count,
                    SUM(CASE WHEN object_type = 'MATERIALIZED VIEW' THEN 1 ELSE 0 END) AS materialized_view_count,
                    SUM(CASE WHEN object_type = 'SEQUENCE' THEN 1 ELSE 0 END) AS sequence_count,
                    SUM(CASE WHEN object_type = 'PROCEDURE' THEN 1 ELSE 0 END) AS procedure_count,
                    SUM(CASE WHEN object_type = 'FUNCTION' THEN 1 ELSE 0 END) AS function_count,
                    SUM(CASE WHEN object_type = 'PACKAGE' THEN 1 ELSE 0 END) AS package_count,
                    SUM(CASE WHEN object_type = 'TRIGGER' THEN 1 ELSE 0 END) AS trigger_count,
                    SUM(CASE WHEN status <> 'VALID' THEN 1 ELSE 0 END) AS invalid_object_count
                FROM dba_objects
                WHERE {owner_filter}
                GROUP BY owner
                ORDER BY COUNT(*) DESC, owner
                FETCH FIRST 25 ROWS ONLY
                """
            )
            rows = cursor.fetchall()
        except Exception:
            errors.append("schema_inventory could not be collected from Oracle.")
            return []

        inventory: list[OracleSchemaInventoryEntry] = []
        for row in rows or []:
            inventory.append(
                OracleSchemaInventoryEntry(
                    owner=str(row[0]),
                    object_count=int(row[1] or 0),
                    table_count=int(row[2] or 0),
                    index_count=int(row[3] or 0),
                    view_count=int(row[4] or 0),
                    materialized_view_count=int(row[5] or 0),
                    sequence_count=int(row[6] or 0),
                    procedure_count=int(row[7] or 0),
                    function_count=int(row[8] or 0),
                    package_count=int(row[9] or 0),
                    trigger_count=int(row[10] or 0),
                    invalid_object_count=int(row[11] or 0),
                )
            )
        return inventory

    def _query_cdb_schema_inventory(
        self,
        cursor: object,
        errors: list[str],
    ) -> list[OracleSchemaInventoryEntry]:
        owner_filter = self._non_default_cdb_owner_filter(
            owner_column="o.owner",
            con_id_column="o.con_id",
        )
        try:
            cursor.execute(
                f"""
                SELECT
                    vc.name AS container_name,
                    o.con_id,
                    o.owner,
                    COUNT(*) AS object_count,
                    SUM(CASE WHEN o.object_type = 'TABLE' THEN 1 ELSE 0 END) AS table_count,
                    SUM(CASE WHEN o.object_type = 'INDEX' THEN 1 ELSE 0 END) AS index_count,
                    SUM(CASE WHEN o.object_type = 'VIEW' THEN 1 ELSE 0 END) AS view_count,
                    SUM(CASE WHEN o.object_type = 'MATERIALIZED VIEW' THEN 1 ELSE 0 END) AS materialized_view_count,
                    SUM(CASE WHEN o.object_type = 'SEQUENCE' THEN 1 ELSE 0 END) AS sequence_count,
                    SUM(CASE WHEN o.object_type = 'PROCEDURE' THEN 1 ELSE 0 END) AS procedure_count,
                    SUM(CASE WHEN o.object_type = 'FUNCTION' THEN 1 ELSE 0 END) AS function_count,
                    SUM(CASE WHEN o.object_type = 'PACKAGE' THEN 1 ELSE 0 END) AS package_count,
                    SUM(CASE WHEN o.object_type = 'TRIGGER' THEN 1 ELSE 0 END) AS trigger_count,
                    SUM(CASE WHEN o.status <> 'VALID' THEN 1 ELSE 0 END) AS invalid_object_count
                FROM cdb_objects o
                JOIN v$containers vc ON vc.con_id = o.con_id
                WHERE vc.name <> 'PDB$SEED'
                  AND {owner_filter}
                GROUP BY vc.name, o.con_id, o.owner
                ORDER BY COUNT(*) DESC, vc.name, o.owner
                """
            )
            rows = cursor.fetchall()
        except Exception:
            errors.append("schema_inventory could not be collected from Oracle.")
            return []

        inventory: list[OracleSchemaInventoryEntry] = []
        for row in rows or []:
            container_name = str(row[0])
            inventory.append(
                OracleSchemaInventoryEntry(
                    container_name=container_name,
                    container_type=self._container_type(container_name),
                    con_id=int(row[1] or 0),
                    owner=str(row[2]),
                    object_count=int(row[3] or 0),
                    table_count=int(row[4] or 0),
                    index_count=int(row[5] or 0),
                    view_count=int(row[6] or 0),
                    materialized_view_count=int(row[7] or 0),
                    sequence_count=int(row[8] or 0),
                    procedure_count=int(row[9] or 0),
                    function_count=int(row[10] or 0),
                    package_count=int(row[11] or 0),
                    trigger_count=int(row[12] or 0),
                    invalid_object_count=int(row[13] or 0),
                )
            )
        return inventory

    def _query_discovery_sections(
        self,
        cursor: object,
        metadata: OracleSourceMetadata,
        errors: list[str],
    ) -> list[OracleDiscoverySection]:
        is_cdb = metadata.deployment_type == "CDB_PDB"
        custom_schema_owner_filter = (
            self._non_default_cdb_owner_filter(owner_column="owner", con_id_column="con_id")
            if is_cdb
            else self._non_default_dba_owner_filter(owner_column="owner")
        )
        lob_owner_filter = (
            self._non_default_cdb_owner_filter(owner_column="s.owner", con_id_column="s.con_id")
            if is_cdb
            else self._non_default_dba_owner_filter(owner_column="owner")
        )
        sections: list[OracleDiscoverySection | None] = [
            self._query_table_section(
                cursor,
                key="custom_schema_size",
                title="DB:Database Custom Schema Size",
                columns=["OWNER", "SIZE_GB"],
                query=(
                    """
                    SELECT owner, TO_CHAR(ROUND(SUM(bytes) / POWER(1024, 3), 8))
                    FROM cdb_segments
                    WHERE """
                    + custom_schema_owner_filter
                    + """
                    GROUP BY owner
                    ORDER BY SUM(bytes), owner
                    """
                    if is_cdb
                    else """
                    SELECT owner, TO_CHAR(ROUND(SUM(bytes) / POWER(1024, 3), 8))
                    FROM dba_segments
                    WHERE """
                    + custom_schema_owner_filter
                    + """
                    GROUP BY owner
                    ORDER BY SUM(bytes), owner
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="wallet_details",
                title="DB:Database Encrypted - Database Wallet Details from CDB/PDB",
                columns=[
                    "PDB_NAME",
                    "TYPE_ID",
                    "WRL_TYPE",
                    "WRL_PARAMETER",
                    "STATUS",
                    "WALLET_TYPE",
                    "WALLET_ORDER",
                    "FULLY_BACKED_UP",
                ],
                query=(
                    """
                    SELECT
                        vc.name,
                        CASE WHEN vc.con_id = 1 THEN 'CDB-ROOT' ELSE 'PDB-' || TO_CHAR(vc.con_id) END,
                        ew.wrl_type,
                        ew.wrl_parameter,
                        ew.status,
                        ew.wallet_type,
                        ew.wallet_order,
                        ew.fully_backed_up
                    FROM v$encryption_wallet ew
                    JOIN v$containers vc ON vc.con_id = ew.con_id
                    WHERE vc.name <> 'PDB$SEED'
                    ORDER BY ew.con_id
                    """
                    if is_cdb
                    else """
                    SELECT
                        name,
                        'NON-CDB',
                        wrl_type,
                        wrl_parameter,
                        status,
                        wallet_type,
                        wallet_order,
                        fully_backed_up
                    FROM v$encryption_wallet
                    CROSS JOIN (SELECT name FROM v$database)
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="global_names",
                title="DB:Database Global Names value details",
                columns=["SOURCE", "VALUE"],
                query="""
                    SELECT 'Show parameter global_names', value
                    FROM v$parameter
                    WHERE name = 'global_names'
                    UNION ALL
                    SELECT 'DBTIMEZONE', dbtimezone FROM dual
                    UNION ALL
                    SELECT 'GLOBAL_NAME', global_name FROM global_name
                """,
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="remote_objects",
                title="DB:Database Synonyms for Remote Objects",
                columns=["CONTAINER", "TYPE_ID", "OWNER", "SYNONYM_NAME", "TABLE_OWNER", "TABLE_NAME", "DB_LINK"],
                query=(
                    """
                    SELECT
                        vc.name,
                        CASE WHEN vc.con_id = 1 THEN 'CDB-ROOT' ELSE 'PDB-' || TO_CHAR(s.con_id) END,
                        s.owner,
                        s.synonym_name,
                        s.table_owner,
                        s.table_name,
                        s.db_link
                    FROM cdb_synonyms s
                    JOIN v$containers vc ON vc.con_id = s.con_id
                    WHERE s.db_link IS NOT NULL
                    ORDER BY vc.name, s.owner, s.synonym_name
                    """
                    if is_cdb
                    else """
                    SELECT
                        name,
                        'NON-CDB',
                        owner,
                        synonym_name,
                        table_owner,
                        table_name,
                        db_link
                    FROM dba_synonyms
                    CROSS JOIN (SELECT name FROM v$database)
                    WHERE db_link IS NOT NULL
                    ORDER BY owner, synonym_name
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="lob_segments_by_schema",
                title="DB:LOB Segment count group by schemas",
                columns=["CONTAINER", "OWNER", "LOB_SEGMENT_COUNT"],
                query=(
                    """
                    SELECT vc.name, s.owner, TO_CHAR(COUNT(*))
                    FROM cdb_segments s
                    JOIN v$containers vc ON vc.con_id = s.con_id
                    WHERE s.segment_type LIKE 'LOB%'
                      AND """
                    + lob_owner_filter
                    + """
                    GROUP BY vc.name, s.owner
                    ORDER BY COUNT(*) DESC, vc.name, s.owner
                    """
                    if is_cdb
                    else """
                    SELECT name, owner, TO_CHAR(COUNT(*))
                    FROM dba_segments
                    CROSS JOIN (SELECT name FROM v$database)
                    WHERE segment_type LIKE 'LOB%'
                      AND """
                    + lob_owner_filter
                    + """
                    GROUP BY name, owner
                    ORDER BY COUNT(*) DESC, owner
                    """
                ),
                errors=errors,
            ),
            self._query_additional_database_details_section(cursor, metadata, errors),
            self._query_table_section(
                cursor,
                key="auditing_check",
                title="DB:Auditing Check",
                columns=["NAME", "TYPE", "VALUE"],
                query="""
                    SELECT name, type, NVL(display_value, value)
                    FROM v$parameter
                    WHERE name IN (
                        'audit_file_dest',
                        'audit_sys_operations',
                        'audit_syslog_level',
                        'audit_trail',
                        'unified_audit_common_systemlog',
                        'unified_audit_sga_queue_size',
                        'unified_audit_systemlog'
                    )
                    ORDER BY name
                """,
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="cpu_memory_details",
                title="DB:CPU and Memory Details",
                columns=["STAT_NAME", "VALUE", "COMMENTS"],
                query="""
                    SELECT stat_name, value,
                           CASE
                               WHEN stat_name = 'NUM_CPUS' THEN 'Number of active CPUs'
                               WHEN stat_name = 'NUM_CPU_CORES' THEN 'Number of CPU cores'
                               WHEN stat_name = 'PHYSICAL_MEMORY_BYTES' THEN 'Physical memory size in bytes'
                               ELSE 'OS statistic'
                           END
                    FROM v$osstat
                    WHERE stat_name IN ('NUM_CPUS', 'NUM_CPU_CORES', 'PHYSICAL_MEMORY_BYTES')
                    ORDER BY stat_name
                """,
                errors=errors,
            ),
            self._query_cluster_check_section(cursor, metadata, errors),
            self._query_table_section(
                cursor,
                key="db_links",
                title="DB:DB link Info from CDB/PDB",
                columns=["CONTAINER", "TYPE_ID", "OWNER", "DB_LINK", "USERNAME", "HOST", "CREATED"],
                query=(
                    """
                    SELECT
                        vc.name,
                        CASE WHEN vc.con_id = 1 THEN 'CDB-ROOT' ELSE 'PDB-' || TO_CHAR(l.con_id) END,
                        l.owner,
                        l.db_link,
                        l.username,
                        l.host,
                        TO_CHAR(l.created, 'YYYY-MM-DD HH24:MI:SS')
                    FROM cdb_db_links l
                    JOIN v$containers vc ON vc.con_id = l.con_id
                    ORDER BY vc.name, l.owner, l.db_link
                    """
                    if is_cdb
                    else """
                    SELECT name, 'NON-CDB', owner, db_link, username, host, TO_CHAR(created, 'YYYY-MM-DD HH24:MI:SS')
                    FROM dba_db_links
                    CROSS JOIN (SELECT name FROM v$database)
                    ORDER BY owner, db_link
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="asm_disk_details",
                title="DB:Database ASM Disk Details from CDB/PDB",
                columns=["GROUP_NUMBER", "DISKGROUP_NAME", "STATE", "TYPE", "TOTAL_MB", "FREE_MB"],
                query="""
                    SELECT TO_CHAR(group_number), name, state, type, TO_CHAR(total_mb), TO_CHAR(free_mb)
                    FROM v$asm_diskgroup
                    ORDER BY name
                """,
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="database_components",
                title="DB:Database Components from CDB/PDB",
                columns=["CONTAINER", "COMP_ID", "COMP_NAME", "VERSION", "STATUS"],
                query=(
                    """
                    SELECT vc.name, r.comp_id, r.comp_name, r.version, r.status
                    FROM cdb_registry r
                    JOIN v$containers vc ON vc.con_id = r.con_id
                    WHERE vc.name <> 'PDB$SEED'
                    ORDER BY vc.name, r.comp_name
                    """
                    if is_cdb
                    else """
                    SELECT name, comp_id, comp_name, version, status
                    FROM dba_registry
                    CROSS JOIN (SELECT name FROM v$database)
                    ORDER BY comp_name
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="feature_usage",
                title="DB:Database Feature Usage from CDB/PDB",
                columns=["NAME", "DETECTED_USAGES", "CURRENTLY_USED", "LAST_USAGE_DATE"],
                query="""
                    SELECT name, TO_CHAR(detected_usages), currently_used, TO_CHAR(last_usage_date, 'YYYY-MM-DD')
                    FROM dba_feature_usage_statistics
                    WHERE detected_usages > 0 OR currently_used = 'TRUE'
                    ORDER BY name
                """,
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="database_home",
                title="DB:Database Home",
                columns=["NAME", "VALUE"],
                query="""
                    SELECT 'Oracle Home' AS name,
                           COALESCE(
                               MAX(
                                   CASE
                                       WHEN value IS NOT NULL
                                        AND value NOT LIKE '+%'
                                        AND REGEXP_LIKE(value, '.*/dbs/[^/]+$')
                                       THEN REGEXP_REPLACE(value, '/dbs/[^/]+$', '')
                                   END
                               ),
                               'Not available from SQL'
                           ) AS value
                    FROM v$parameter
                    WHERE name = 'spfile'
                    UNION ALL
                    SELECT 'SPFILE', NVL(MAX(value), 'Not available')
                    FROM v$parameter
                    WHERE name = 'spfile'
                    UNION ALL
                    SELECT name, value
                    FROM v$diag_info
                    WHERE name IN ('ADR Base', 'ADR Home', 'Diag Trace')
                    ORDER BY 1
                """,
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="materialized_views_info",
                title="DB:Database MV_Views_Info from CDB/PDB",
                columns=["CONTAINER", "OWNER", "MVIEW_NAME", "REFRESH_MODE", "REFRESH_METHOD", "FAST_REFRESHABLE"],
                query=(
                    """
                    SELECT vc.name, m.owner, m.mview_name, m.refresh_mode, m.refresh_method, m.fast_refreshable
                    FROM cdb_mviews m
                    JOIN v$containers vc ON vc.con_id = m.con_id
                    ORDER BY vc.name, m.owner, m.mview_name
                    """
                    if is_cdb
                    else """
                    SELECT name, owner, mview_name, refresh_mode, refresh_method, fast_refreshable
                    FROM dba_mviews
                    CROSS JOIN (SELECT name FROM v$database)
                    ORDER BY owner, mview_name
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="options_features",
                title="DB:Database Options and Features",
                columns=["PARAMETER", "VALUE"],
                query="""
                    SELECT parameter, value
                    FROM v$option
                    ORDER BY parameter
                """,
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="database_parameters",
                title="DB:Database Parameters",
                columns=["NAME", "VALUE", "ISDEFAULT", "ISMODIFIED"],
                query="""
                    SELECT name, NVL(display_value, value), isdefault, ismodified
                    FROM v$parameter
                    ORDER BY name
                """,
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="database_properties",
                title="DB:Database Properties",
                columns=["PROPERTY_NAME", "PROPERTY_VALUE", "DESCRIPTION"],
                query="""
                    SELECT property_name, property_value, description
                    FROM database_properties
                    ORDER BY property_name
                """,
                errors=errors,
            ),
            self._query_database_size_section(cursor, is_cdb, errors),
            self._query_standby_section(cursor, errors),
            self._query_database_users_section(metadata),
            self._query_table_section(
                cursor,
                key="xml_table_columns",
                title="DB:Database XML_Table_Columns from CDB/PDB",
                columns=["CONTAINER", "OWNER", "TABLE_NAME", "COLUMN_NAME", "DATA_TYPE"],
                query=(
                    """
                    SELECT vc.name, c.owner, c.table_name, c.column_name, c.data_type
                    FROM cdb_tab_columns c
                    JOIN v$containers vc ON vc.con_id = c.con_id
                    WHERE c.data_type = 'XMLTYPE'
                      AND """
                    + self._non_default_cdb_owner_filter(
                        owner_column="c.owner",
                        con_id_column="c.con_id",
                    )
                    + """
                    ORDER BY vc.name, c.owner, c.table_name, c.column_name
                    """
                    if is_cdb
                    else """
                    SELECT name, owner, table_name, column_name, data_type
                    FROM dba_tab_columns
                    CROSS JOIN (SELECT name FROM v$database)
                    WHERE data_type = 'XMLTYPE'
                      AND """
                    + self._non_default_dba_owner_filter(owner_column="owner")
                    + """
                    ORDER BY owner, table_name, column_name
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="xml_table_info",
                title="DB:Database XML_Table_Info from CDB/PDB",
                columns=["CONTAINER", "OWNER", "TABLE_NAME", "XMLSCHEMA", "STORAGE_TYPE"],
                query=(
                    """
                    SELECT vc.name, x.owner, x.table_name, x.xmlschema, x.storage_type
                    FROM cdb_xml_tables x
                    JOIN v$containers vc ON vc.con_id = x.con_id
                    ORDER BY vc.name, x.owner, x.table_name
                    """
                    if is_cdb
                    else """
                    SELECT name, owner, table_name, xmlschema, storage_type
                    FROM dba_xml_tables
                    CROSS JOIN (SELECT name FROM v$database)
                    ORDER BY owner, table_name
                    """
                ),
                errors=errors,
            ),
            self._query_datafiles_tempfiles_section(cursor, is_cdb, errors),
            self._query_table_section(
                cursor,
                key="directories",
                title="DB:Directories Information from CDB/PDB",
                columns=["CONTAINER", "OWNER", "DIRECTORY_NAME", "DIRECTORY_PATH"],
                query=(
                    """
                    SELECT vc.name, d.owner, d.directory_name, d.directory_path
                    FROM cdb_directories d
                    JOIN v$containers vc ON vc.con_id = d.con_id
                    ORDER BY vc.name, d.owner, d.directory_name
                    """
                    if is_cdb
                    else """
                    SELECT name, owner, directory_name, directory_path
                    FROM dba_directories
                    CROSS JOIN (SELECT name FROM v$database)
                    ORDER BY owner, directory_name
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="external_tables",
                title="DB:External Tables from CDB/PDB",
                columns=["CONTAINER", "OWNER", "TABLE_NAME", "TYPE_NAME", "DEFAULT_DIRECTORY_NAME"],
                query=(
                    """
                    SELECT vc.name, e.owner, e.table_name, e.type_name, e.default_directory_name
                    FROM cdb_external_tables e
                    JOIN v$containers vc ON vc.con_id = e.con_id
                    ORDER BY vc.name, e.owner, e.table_name
                    """
                    if is_cdb
                    else """
                    SELECT name, owner, table_name, type_name, default_directory_name
                    FROM dba_external_tables
                    CROSS JOIN (SELECT name FROM v$database)
                    ORDER BY owner, table_name
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="index_organized_tables",
                title="DB:Index Organised Tables from CDB/PDB",
                columns=["CONTAINER", "OWNER", "TABLE_NAME", "IOT_TYPE"],
                query=(
                    """
                    SELECT vc.name, t.owner, t.table_name, t.iot_type
                    FROM cdb_tables t
                    JOIN v$containers vc ON vc.con_id = t.con_id
                    WHERE t.iot_type IS NOT NULL
                      AND """
                    + self._non_default_cdb_owner_filter(
                        owner_column="t.owner",
                        con_id_column="t.con_id",
                    )
                    + """
                    ORDER BY vc.name, t.owner, t.table_name
                    """
                    if is_cdb
                    else """
                    SELECT name, owner, table_name, iot_type
                    FROM dba_tables
                    CROSS JOIN (SELECT name FROM v$database)
                    WHERE iot_type IS NOT NULL
                      AND """
                    + self._non_default_dba_owner_filter(owner_column="owner")
                    + """
                    ORDER BY owner, table_name
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="invalid_objects",
                title="DB:Invalid Objects from CDB/PDB",
                columns=["CONTAINER", "TYPE_ID", "OBJECT_NAME", "OBJECT_TYPE", "STATUS"],
                query=(
                    """
                    SELECT
                        vc.name,
                        CASE WHEN vc.con_id = 1 THEN 'CDB-ROOT' ELSE 'PDB-' || TO_CHAR(o.con_id) END,
                        o.owner || '.' || o.object_name,
                        o.object_type,
                        o.status
                    FROM cdb_objects o
                    JOIN v$containers vc ON vc.con_id = o.con_id
                    WHERE o.status <> 'VALID'
                    ORDER BY vc.name, o.owner, o.object_name
                    """
                    if is_cdb
                    else """
                    SELECT name, 'NON-CDB', owner || '.' || object_name, object_type, status
                    FROM dba_objects
                    CROSS JOIN (SELECT name FROM v$database)
                    WHERE status <> 'VALID'
                    ORDER BY owner, object_name
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="scheduled_jobs_cdb_jobs",
                title="DB:Scheduled Jobs_From_CDB_JOBS (CDB/PDB)",
                columns=["CONTAINER", "LOG_USER", "JOB", "SCHEMA_USER", "BROKEN", "INTERVAL"],
                query=(
                    """
                    SELECT vc.name, j.log_user, TO_CHAR(j.job), j.schema_user, j.broken, j.interval
                    FROM cdb_jobs j
                    JOIN v$containers vc ON vc.con_id = j.con_id
                    ORDER BY vc.name, j.schema_user, j.job
                    """
                    if is_cdb
                    else """
                    SELECT name, log_user, TO_CHAR(job), schema_user, broken, interval
                    FROM dba_jobs
                    CROSS JOIN (SELECT name FROM v$database)
                    ORDER BY schema_user, job
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="scheduled_jobs_scheduler",
                title="DB:Scheduled Jobs_From_CDB_SCHEDULER_JOBS (CDB/PDB)",
                columns=["CONTAINER", "OWNER", "JOB_NAME", "ENABLED", "STATE", "JOB_STYLE"],
                query=(
                    """
                    SELECT vc.name, j.owner, j.job_name, j.enabled, j.state, j.job_style
                    FROM cdb_scheduler_jobs j
                    JOIN v$containers vc ON vc.con_id = j.con_id
                    ORDER BY vc.name, j.owner, j.job_name
                    """
                    if is_cdb
                    else """
                    SELECT name, owner, job_name, enabled, state, job_style
                    FROM dba_scheduler_jobs
                    CROSS JOIN (SELECT name FROM v$database)
                    ORDER BY owner, job_name
                    """
                ),
                errors=errors,
            ),
            self._query_schema_wise_object_count_section(metadata),
            self._query_table_section(
                cursor,
                key="software_version_psu_1",
                title="DB:Software Version and PSU Info_1",
                columns=["BANNER"],
                query="SELECT banner FROM v$version ORDER BY banner",
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="software_version_psu_2",
                title="DB:Software Version and PSU Info_2 from CDB/PDB",
                columns=["ACTION_TIME", "ACTION", "STATUS", "VERSION", "DESCRIPTION"],
                query="""
                    SELECT
                        TO_CHAR(action_time, 'YYYY-MM-DD HH24:MI:SS'),
                        action,
                        status,
                        version,
                        description
                    FROM dba_registry_sqlpatch
                    ORDER BY action_time DESC
                """,
                errors=errors,
                required=False,
            ),
            self._query_table_section(
                cursor,
                key="software_version_psu_3",
                title="DB:Software Version and PSU Info_3 from CDB/PDB",
                columns=["PRODUCT", "VERSION", "STATUS"],
                query="""
                    SELECT product, version, status
                    FROM product_component_version
                    ORDER BY product
                """,
                errors=errors,
            ),
            self._query_tablespace_details_section(metadata),
            self._query_table_section(
                cursor,
                key="vpd_exempt_users",
                title="DB:VPD:DB Users with Exempt Access Policy from CDB/PDB",
                columns=["CONTAINER", "GRANTEE", "PRIVILEGE"],
                query=(
                    """
                    SELECT vc.name, p.grantee, p.privilege
                    FROM cdb_sys_privs p
                    JOIN v$containers vc ON vc.con_id = p.con_id
                    WHERE p.privilege = 'EXEMPT ACCESS POLICY'
                    ORDER BY vc.name, p.grantee
                    """
                    if is_cdb
                    else """
                    SELECT name, grantee, privilege
                    FROM dba_sys_privs
                    CROSS JOIN (SELECT name FROM v$database)
                    WHERE privilege = 'EXEMPT ACCESS POLICY'
                    ORDER BY grantee
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="xml_types",
                title="DB:XML_Types from CDB/PDB",
                columns=["CONTAINER", "OWNER", "TABLE_NAME", "COLUMN_NAME"],
                query=(
                    """
                    SELECT vc.name, c.owner, c.table_name, c.column_name
                    FROM cdb_tab_columns c
                    JOIN v$containers vc ON vc.con_id = c.con_id
                    WHERE c.data_type = 'XMLTYPE'
                    ORDER BY vc.name, c.owner, c.table_name, c.column_name
                    """
                    if is_cdb
                    else """
                    SELECT name, owner, table_name, column_name
                    FROM dba_tab_columns
                    CROSS JOIN (SELECT name FROM v$database)
                    WHERE data_type = 'XMLTYPE'
                    ORDER BY owner, table_name, column_name
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="ogg_all_unsupported",
                title="OGG:All Unsupported from CDB/PDB",
                columns=["CONTAINER", "OWNER", "TABLE_NAME", "COLUMN_NAME", "DATA_TYPE"],
                query=self._unsupported_datatypes_query(is_cdb),
                errors=errors,
            ),
            self._query_archive_volume_per_day_section(cursor, errors),
            self._query_table_section(
                cursor,
                key="compressed_tables_partitions",
                title="Compressed Tables and Table Partitions from CDB/PDB",
                columns=["CONTAINER", "OWNER", "OBJECT_NAME", "OBJECT_TYPE", "COMPRESSION"],
                query=self._compressed_objects_query(is_cdb),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="constraints_tables",
                title="Constraints and Tables from CDB/PDB",
                columns=["CONTAINER", "OWNER", "TABLE_NAME", "CONSTRAINT_NAME", "CONSTRAINT_TYPE", "STATUS"],
                query=(
                    """
                    SELECT vc.name, c.owner, c.table_name, c.constraint_name, c.constraint_type, c.status
                    FROM cdb_constraints c
                    JOIN v$containers vc ON vc.con_id = c.con_id
                    WHERE c.constraint_type IN ('P', 'U', 'R', 'C')
                      AND """
                    + self._non_default_cdb_owner_filter(
                        owner_column="c.owner",
                        con_id_column="c.con_id",
                    )
                    + """
                    ORDER BY vc.name, c.owner, c.table_name, c.constraint_name
                    """
                    if is_cdb
                    else """
                    SELECT name, owner, table_name, constraint_name, constraint_type, status
                    FROM dba_constraints
                    CROSS JOIN (SELECT name FROM v$database)
                    WHERE constraint_type IN ('P', 'U', 'R', 'C')
                      AND """
                    + self._non_default_dba_owner_filter(owner_column="owner")
                    + """
                    ORDER BY owner, table_name, constraint_name
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="deferred_indexes",
                title="Deferred Indexes from CDB/PDB",
                columns=["CONTAINER", "OWNER", "INDEX_NAME", "TABLE_NAME", "STATUS", "VISIBILITY"],
                query=(
                    """
                    SELECT vc.name, i.owner, i.index_name, i.table_name, i.status, i.visibility
                    FROM cdb_indexes i
                    JOIN v$containers vc ON vc.con_id = i.con_id
                    WHERE (i.status <> 'VALID' OR i.visibility = 'INVISIBLE')
                      AND """
                    + self._non_default_cdb_owner_filter(
                        owner_column="i.owner",
                        con_id_column="i.con_id",
                    )
                    + """
                    ORDER BY vc.name, i.owner, i.index_name
                    """
                    if is_cdb
                    else """
                    SELECT name, owner, index_name, table_name, status, visibility
                    FROM dba_indexes
                    CROSS JOIN (SELECT name FROM v$database)
                    WHERE (status <> 'VALID' OR visibility = 'INVISIBLE')
                      AND """
                    + self._non_default_dba_owner_filter(owner_column="owner")
                    + """
                    ORDER BY owner, index_name
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="mview_list",
                title="OGG:Materialized View List from CDB/PDB",
                columns=["CONTAINER", "OWNER", "MVIEW_NAME", "QUERY_LEN"],
                query=(
                    """
                    SELECT vc.name, m.owner, m.mview_name, TO_CHAR(m.query_len)
                    FROM cdb_mviews m
                    JOIN v$containers vc ON vc.con_id = m.con_id
                    ORDER BY vc.name, m.owner, m.mview_name
                    """
                    if is_cdb
                    else """
                    SELECT name, owner, mview_name, TO_CHAR(query_len)
                    FROM dba_mviews
                    CROSS JOIN (SELECT name FROM v$database)
                    ORDER BY owner, mview_name
                    """
                ),
                errors=errors,
                required=False,
            ),
            self._query_table_section(
                cursor,
                key="redo_log_information",
                title="Redo Log Information",
                columns=["GROUP#", "THREAD#", "SEQUENCE#", "BYTES_MB", "MEMBERS", "ARCHIVED", "STATUS"],
                query="""
                    SELECT
                        TO_CHAR(group#),
                        TO_CHAR(thread#),
                        TO_CHAR(sequence#),
                        TO_CHAR(ROUND(bytes / POWER(1024, 2), 2)),
                        TO_CHAR(members),
                        archived,
                        status
                    FROM v$log
                    ORDER BY thread#, group#
                """,
                errors=errors,
            ),
            self._query_redo_log_switch_section(cursor, errors),
            self._query_table_section(
                cursor,
                key="supplemental_logging",
                title="OGG:Supplemental Logging",
                columns=[
                    "MIN",
                    "PK",
                    "UI",
                    "FK",
                    "ALL",
                    "FORCE_LOGGING",
                ],
                query="""
                    SELECT
                        supplemental_log_data_min,
                        supplemental_log_data_pk,
                        supplemental_log_data_ui,
                        supplemental_log_data_fk,
                        supplemental_log_data_all,
                        force_logging
                    FROM v$database
                """,
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="tables_without_pk_uk",
                title="OGG:Tables Without Primary or Unique Key from CDB/PDB",
                columns=["CONTAINER", "OWNER", "TABLE_NAME"],
                query=self._tables_without_key_query(is_cdb),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="domain_indexes",
                title="tables with Domain Indexes from CDB/PDB",
                columns=["CONTAINER", "OWNER", "TABLE_NAME", "INDEX_NAME", "INDEX_TYPE"],
                query=(
                    """
                    SELECT vc.name, i.owner, i.table_name, i.index_name, i.index_type
                    FROM cdb_indexes i
                    JOIN v$containers vc ON vc.con_id = i.con_id
                    WHERE i.index_type LIKE '%DOMAIN%'
                    ORDER BY vc.name, i.owner, i.index_name
                    """
                    if is_cdb
                    else """
                    SELECT name, owner, table_name, index_name, index_type
                    FROM dba_indexes
                    CROSS JOIN (SELECT name FROM v$database)
                    WHERE index_type LIKE '%DOMAIN%'
                    ORDER BY owner, index_name
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="nologging_tables",
                title="OGG:Tables with Nologging setting from CDB/PDB",
                columns=["CONTAINER", "OWNER", "TABLE_NAME", "LOGGING"],
                query=(
                    """
                    SELECT vc.name, t.owner, t.table_name, t.logging
                    FROM cdb_tables t
                    JOIN v$containers vc ON vc.con_id = t.con_id
                    WHERE t.logging = 'NO'
                      AND """
                    + self._non_default_cdb_owner_filter(
                        owner_column="t.owner",
                        con_id_column="t.con_id",
                    )
                    + """
                    ORDER BY vc.name, t.owner, t.table_name
                    """
                    if is_cdb
                    else """
                    SELECT name, owner, table_name, logging
                    FROM dba_tables
                    CROSS JOIN (SELECT name FROM v$database)
                    WHERE logging = 'NO'
                      AND """
                    + self._non_default_dba_owner_filter(owner_column="owner")
                    + """
                    ORDER BY owner, table_name
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="tables_with_triggers",
                title="OGG:Tables with Triggers from CDB/PDB",
                columns=["CONTAINER", "OWNER", "TABLE_NAME", "TRIGGER_COUNT"],
                query=(
                    """
                    SELECT vc.name, t.table_owner, t.table_name, TO_CHAR(COUNT(*))
                    FROM cdb_triggers t
                    JOIN v$containers vc ON vc.con_id = t.con_id
                    WHERE """
                    + self._non_default_cdb_owner_filter(
                        owner_column="t.table_owner",
                        con_id_column="t.con_id",
                    )
                    + """
                    GROUP BY vc.name, t.table_owner, t.table_name
                    ORDER BY COUNT(*) DESC, vc.name, t.table_owner, t.table_name
                    """
                    if is_cdb
                    else """
                    SELECT name, table_owner, table_name, TO_CHAR(COUNT(*))
                    FROM dba_triggers
                    CROSS JOIN (SELECT name FROM v$database)
                    WHERE """
                    + self._non_default_dba_owner_filter(owner_column="table_owner")
                    + """
                    GROUP BY name, table_owner, table_name
                    ORDER BY COUNT(*) DESC, table_owner, table_name
                    """
                ),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="unsupported_datatypes",
                title="OGG:Unsupported Datatypes from CDB/PDB",
                columns=["CONTAINER", "OWNER", "TABLE_NAME", "COLUMN_NAME", "DATA_TYPE"],
                query=self._unsupported_datatypes_query(is_cdb),
                errors=errors,
            ),
            self._query_table_section(
                cursor,
                key="memory_parameters",
                title="Memory Parameters",
                columns=["NAME", "VALUE", "ISDEFAULT", "ISMODIFIED"],
                query="""
                    SELECT name, NVL(display_value, value), isdefault, ismodified
                    FROM v$parameter
                    WHERE name LIKE '%memory%'
                       OR name LIKE 'sga%'
                       OR name LIKE 'pga%'
                    ORDER BY name
                """,
                errors=errors,
            ),
        ]

        return [section for section in sections if section is not None]

    def _build_discovery_summary(
        self,
        metadata: OracleSourceMetadata,
    ) -> list[OracleDiscoverySummaryItem]:
        job_count = self._section_row_count(metadata.discovery_sections, "scheduled_jobs_cdb_jobs")
        scheduler_job_count = self._section_row_count(metadata.discovery_sections, "scheduled_jobs_scheduler")
        directories_count = self._section_row_count(metadata.discovery_sections, "directories")
        db_link_count = self._section_row_count(metadata.discovery_sections, "db_links")
        external_table_count = self._section_row_count(metadata.discovery_sections, "external_tables")
        invalid_count = metadata.inventory_summary.invalid_object_count if metadata.inventory_summary else 0
        encrypted_tablespace_count = sum(
            1 for item in metadata.tablespaces if item.encrypted
        )
        profile_count = len(
            {
                (user.container_name, user.profile)
                for user in metadata.database_users
                if user.profile and user.profile.upper() != "DEFAULT"
            }
        )
        partition_count = self._section_row_count(metadata.discovery_sections, "compressed_tables_partitions")
        summary = [
            OracleDiscoverySummaryItem(
                key_point="Discovery Utility Version",
                key_value="App Discovery 1",
                observation="Application discovery build version.",
            ),
            OracleDiscoverySummaryItem(
                key_point="CDB Name",
                key_value=metadata.db_name or "Not available",
                observation="Information to be noted.",
            ),
            OracleDiscoverySummaryItem(
                key_point="PDB Name",
                key_value=", ".join(pdb.name for pdb in metadata.pdbs)
                if metadata.pdbs
                else "Not available",
                observation="Information to be noted.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Database Server",
                key_value=metadata.host_name or "Not available",
                observation="Information to be noted.",
            ),
            OracleDiscoverySummaryItem(
                key_point="DB Link",
                key_value=str(db_link_count),
                observation="Needs to be highlighted. Please check details in the report.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Database Directories",
                key_value=str(directories_count),
                observation="Needs to be highlighted. Please check details in the report.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Total Database_size",
                key_value=f"{metadata.database_size_gb} GB"
                if metadata.database_size_gb is not None
                else "Not available",
                observation="Total Database Size [Datafiles + Temp files].",
            ),
            OracleDiscoverySummaryItem(
                key_point="Actual Database_size",
                key_value=f"{round(sum(item.used_mb or 0 for item in metadata.tablespaces) / 1024, 2)} GB"
                if metadata.tablespaces
                else "Not available",
                observation="Actual Data Size.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Archive Log Mode",
                key_value="ARCHIVELOG" if metadata.archivelog_enabled else "NOARCHIVELOG",
                observation="Archive log mode.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Invalid objects",
                key_value=str(invalid_count),
                observation="Needs to be highlighted. Please check details in the report.",
            ),
            OracleDiscoverySummaryItem(
                key_point="External Table",
                key_value=str(external_table_count),
                observation="Needs to be highlighted. Please check details in the report.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Database Version",
                key_value=metadata.oracle_version or "Not available",
                observation="Information to be noted.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Source Operation System",
                key_value=metadata.platform or "Not available",
                observation="Information to be noted.",
            ),
            OracleDiscoverySummaryItem(
                key_point="NLS_CHARACTERSET",
                key_value=metadata.character_set or "Not available",
                observation="Please check this value at target database before migration.",
            ),
            OracleDiscoverySummaryItem(
                key_point="NLS_NCHAR_CHARACTERSET",
                key_value=metadata.nchar_character_set or "Not available",
                observation="Please check this value at target database before migration.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Encrypted - Database Wallet",
                key_value="ENABLED" if metadata.tde_enabled else "CLOSED",
                observation="Needs to be highlighted for Physical Migration.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Encrypted - Tablespace",
                key_value=str(encrypted_tablespace_count),
                observation="Encrypted tablespace count.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Database Block Size",
                key_value=f"{next((item.block_size for item in metadata.tablespaces if item.block_size), 'Not available')}",
                observation="Information to be noted.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Database JOBs",
                key_value=str(job_count + scheduler_job_count),
                observation="Needs to be highlighted. Please check details in the report.",
            ),
            OracleDiscoverySummaryItem(
                key_point="10g Password Version",
                key_value=str(
                    sum(
                        1
                        for user in metadata.database_users
                        if user.password_versions and "10G" in user.password_versions
                    )
                ),
                observation="Needs to be highlighted. Please check details in the report.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Endianness",
                key_value=metadata.endianness or "Not available",
                observation="Information to be noted.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Standby available",
                key_value=self._standby_value(metadata.discovery_sections),
                observation="Standby availability.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Cluster Check",
                key_value="TRUE" if metadata.rac_enabled else "FALSE",
                observation="Cluster enabled state.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Partition Count",
                key_value=str(partition_count),
                observation="Partition-related object count.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Materialized View",
                key_value=str(self._section_row_count(metadata.discovery_sections, "mview_list")),
                observation="Needs to be highlighted. Please check details in the report.",
            ),
            OracleDiscoverySummaryItem(
                key_point="Non-Default User Profile",
                key_value=str(profile_count),
                observation="Needs to be highlighted. Please check details in the report.",
            ),
        ]
        return summary

    def _query_table_section(
        self,
        cursor: object,
        key: str,
        title: str,
        columns: list[str],
        query: str,
        errors: list[str],
        row_limit: int = DEFAULT_DISCOVERY_ROW_LIMIT,
        required: bool = True,
    ) -> OracleDiscoverySection | None:
        try:
            cursor.execute(query)
            rows = cursor.fetchall() or []
        except Exception:
            if required:
                errors.append(f"{key} could not be collected from Oracle.")
            return None

        truncated = len(rows) > row_limit
        limited_rows = rows[:row_limit]
        return OracleDiscoverySection(
            key=key,
            title=title,
            columns=columns,
            rows=[
                {
                    columns[index]: self._stringify_value(row[index] if index < len(row) else None)
                    for index in range(len(columns))
                }
                for row in limited_rows
            ],
            row_count=len(rows),
            truncated=truncated,
        )

    def _query_additional_database_details_section(
        self,
        cursor: object,
        metadata: OracleSourceMetadata,
        errors: list[str],
    ) -> OracleDiscoverySection | None:
        rows: list[dict[str, str]] = []
        try:
            cursor.execute(
                """
                SELECT
                    TO_CHAR(dbid),
                    name,
                    TO_CHAR(created, 'YYYY-MM-DD HH24:MI:SS'),
                    TO_CHAR(startup_time, 'YYYY-MM-DD HH24:MI:SS'),
                    logins,
                    log_mode,
                    open_mode,
                    remote_archive,
                    database_role,
                    platform_id,
                    platform_name,
                    db_unique_name
                FROM v$database
                CROSS JOIN v$instance
                """
            )
            for row in cursor.fetchall() or []:
                rows.append(
                    {
                        "SCOPE": "CDB",
                        "DBID": self._stringify_value(row[0]),
                        "NAME": self._stringify_value(row[1]),
                        "CREATED": self._stringify_value(row[2]),
                        "STARTUP_TIME": self._stringify_value(row[3]),
                        "LOGINS": self._stringify_value(row[4]),
                        "LOG_MODE": self._stringify_value(row[5]),
                        "OPEN_MODE": self._stringify_value(row[6]),
                        "REMOTE_ARCHIVE": self._stringify_value(row[7]),
                        "DATABASE_ROLE": self._stringify_value(row[8]),
                        "PLATFORM_ID": self._stringify_value(row[9]),
                        "PLATFORM_NAME": self._stringify_value(row[10]),
                        "DB_UNIQUE_NAME": self._stringify_value(row[11]),
                    }
                )
        except Exception:
            errors.append("additional_database_details could not be collected from Oracle.")
            return None

        for pdb in metadata.pdbs:
            rows.append(
                {
                    "SCOPE": "PDB",
                    "DBID": "",
                    "NAME": pdb.name,
                    "CREATED": "",
                    "STARTUP_TIME": self._stringify_value(pdb.open_time),
                    "LOGINS": "",
                    "LOG_MODE": "ARCHIVELOG" if metadata.archivelog_enabled else "NOARCHIVELOG",
                    "OPEN_MODE": self._stringify_value(pdb.open_mode),
                    "REMOTE_ARCHIVE": "",
                    "DATABASE_ROLE": "",
                    "PLATFORM_ID": "",
                    "PLATFORM_NAME": self._stringify_value(metadata.platform),
                    "DB_UNIQUE_NAME": "",
                }
            )

        return OracleDiscoverySection(
            key="additional_database_details",
            title="DB:Additional Database Details",
            columns=[
                "SCOPE",
                "DBID",
                "NAME",
                "CREATED",
                "STARTUP_TIME",
                "LOGINS",
                "LOG_MODE",
                "OPEN_MODE",
                "REMOTE_ARCHIVE",
                "DATABASE_ROLE",
                "PLATFORM_ID",
                "PLATFORM_NAME",
                "DB_UNIQUE_NAME",
            ],
            rows=rows[:DEFAULT_DISCOVERY_ROW_LIMIT],
            row_count=len(rows),
            truncated=len(rows) > DEFAULT_DISCOVERY_ROW_LIMIT,
        )

    def _query_cluster_check_section(
        self,
        cursor: object,
        metadata: OracleSourceMetadata,
        errors: list[str],
    ) -> OracleDiscoverySection | None:
        cluster_database = self._query_scalar(
            cursor,
            "cluster_database",
            "SELECT value FROM v$parameter WHERE name = 'cluster_database'",
            errors,
        )
        instance_count = self._query_scalar(
            cursor,
            "cluster_instance_count",
            "SELECT COUNT(*) FROM gv$instance",
            errors,
            transform=lambda value: int(value) if value is not None else 0,
        )
        rows = [
            {
                "CHECK_NAME": "cluster_database",
                "VALUE": self._stringify_value(cluster_database),
                "OBSERVATION": "Database cluster parameter.",
            },
            {
                "CHECK_NAME": "rac_enabled",
                "VALUE": "TRUE" if metadata.rac_enabled else "FALSE",
                "OBSERVATION": "Derived from gv$instance count.",
            },
            {
                "CHECK_NAME": "instance_count",
                "VALUE": self._stringify_value(instance_count),
                "OBSERVATION": "Number of visible instances.",
            },
        ]
        return OracleDiscoverySection(
            key="cluster_check",
            title="DB:Cluster Check",
            columns=["CHECK_NAME", "VALUE", "OBSERVATION"],
            rows=rows,
            row_count=len(rows),
            truncated=False,
        )

    def _query_database_size_section(
        self,
        cursor: object,
        is_cdb: bool,
        errors: list[str],
    ) -> OracleDiscoverySection | None:
        query = (
            """
            SELECT 'DATAFILES', TO_CHAR(ROUND(SUM(bytes) / POWER(1024, 3), 2)) FROM cdb_data_files
            UNION ALL
            SELECT 'TEMPFILES', TO_CHAR(ROUND(SUM(bytes) / POWER(1024, 3), 2)) FROM cdb_temp_files
            UNION ALL
            SELECT 'REDOLOGS', TO_CHAR(ROUND(SUM(bytes) / POWER(1024, 3), 2)) FROM v$log
            """
            if is_cdb
            else """
            SELECT 'DATAFILES', TO_CHAR(ROUND(SUM(bytes) / POWER(1024, 3), 2)) FROM dba_data_files
            UNION ALL
            SELECT 'TEMPFILES', TO_CHAR(ROUND(SUM(bytes) / POWER(1024, 3), 2)) FROM dba_temp_files
            UNION ALL
            SELECT 'REDOLOGS', TO_CHAR(ROUND(SUM(bytes) / POWER(1024, 3), 2)) FROM v$log
            """
        )
        return self._query_table_section(
            cursor,
            key="database_size",
            title="DB:Database Size",
            columns=["COMPONENT", "SIZE_GB"],
            query=query,
            errors=errors,
        )

    def _query_standby_section(
        self,
        cursor: object,
        errors: list[str],
    ) -> OracleDiscoverySection | None:
        return self._query_table_section(
            cursor,
            key="standby_availability",
            title="DB:Database Standby availibility",
            columns=["DATABASE_ROLE", "SWITCHOVER_STATUS", "GUARD_STATUS", "FORCE_LOGGING"],
            query="""
                SELECT database_role, switchover_status, guard_status, force_logging
                FROM v$database
            """,
            errors=errors,
        )

    def _query_database_users_section(
        self,
        metadata: OracleSourceMetadata,
    ) -> OracleDiscoverySection | None:
        rows = [
            {
                "CONTAINER": item.container_name,
                "TYPE_ID": "CDB-ROOT" if item.container_type == "CDB_ROOT" else f"PDB-{item.con_id}",
                "USER_TYPE": item.user_type,
                "CUSTOM_USER": item.username,
                "ACCOUNT_STATUS": self._stringify_value(item.account_status),
                "CREATED": self._stringify_value(item.created),
                "EXPIRY_DATE": self._stringify_value(item.expiry_date),
                "PROFILE": self._stringify_value(item.profile),
                "PVERSION": self._stringify_value(item.password_versions),
                "DEFAULT_TABLESPACE": self._stringify_value(item.default_tablespace),
                "TEMPORARY_TABLESPACE": self._stringify_value(item.temporary_tablespace),
            }
            for item in metadata.database_users[:DEFAULT_DISCOVERY_ROW_LIMIT]
        ]
        return OracleDiscoverySection(
            key="database_users",
            title="DB:Database Users from CDB/PDB",
            columns=[
                "CONTAINER",
                "TYPE_ID",
                "USER_TYPE",
                "CUSTOM_USER",
                "ACCOUNT_STATUS",
                "CREATED",
                "EXPIRY_DATE",
                "PROFILE",
                "PVERSION",
                "DEFAULT_TABLESPACE",
                "TEMPORARY_TABLESPACE",
            ],
            rows=rows,
            row_count=len(metadata.database_users),
            truncated=len(metadata.database_users) > DEFAULT_DISCOVERY_ROW_LIMIT,
        )

    def _query_datafiles_tempfiles_section(
        self,
        cursor: object,
        is_cdb: bool,
        errors: list[str],
    ) -> OracleDiscoverySection | None:
        return self._query_table_section(
            cursor,
            key="datafiles_tempfiles",
            title="DB:Datafiles - Tempfiles from CDB/PDB",
            columns=["CONTAINER", "TYPE", "TABLESPACE_NAME", "FILE_NAME", "BYTES_GB"],
            query=(
                """
                SELECT vc.name, 'DATAFILE', d.tablespace_name, d.file_name, TO_CHAR(ROUND(d.bytes / POWER(1024, 3), 2))
                FROM cdb_data_files d JOIN v$containers vc ON vc.con_id = d.con_id
                UNION ALL
                SELECT vc.name, 'TEMPFILE', t.tablespace_name, t.file_name, TO_CHAR(ROUND(t.bytes / POWER(1024, 3), 2))
                FROM cdb_temp_files t JOIN v$containers vc ON vc.con_id = t.con_id
                ORDER BY 1, 2, 3, 4
                """
                if is_cdb
                else """
                SELECT name, 'DATAFILE', d.tablespace_name, d.file_name, TO_CHAR(ROUND(d.bytes / POWER(1024, 3), 2))
                FROM dba_data_files d CROSS JOIN (SELECT name FROM v$database)
                UNION ALL
                SELECT name, 'TEMPFILE', t.tablespace_name, t.file_name, TO_CHAR(ROUND(t.bytes / POWER(1024, 3), 2))
                FROM dba_temp_files t CROSS JOIN (SELECT name FROM v$database)
                ORDER BY 1, 2, 3, 4
                """
            ),
            errors=errors,
        )

    def _query_datafiles_section(
        self,
        cursor: object,
        is_cdb: bool,
        errors: list[str],
    ) -> OracleDiscoverySection | None:
        return self._query_table_section(
            cursor,
            key="datafiles",
            title="DB:Datafiles from CDB/PDB",
            columns=["CONTAINER", "TABLESPACE_NAME", "FILE_NAME", "BYTES_GB", "AUTOEXTENSIBLE"],
            query=(
                """
                SELECT vc.name, d.tablespace_name, d.file_name, TO_CHAR(ROUND(d.bytes / POWER(1024, 3), 2)), d.autoextensible
                FROM cdb_data_files d
                JOIN v$containers vc ON vc.con_id = d.con_id
                ORDER BY vc.name, d.tablespace_name, d.file_name
                """
                if is_cdb
                else """
                SELECT name, d.tablespace_name, d.file_name, TO_CHAR(ROUND(d.bytes / POWER(1024, 3), 2)), d.autoextensible
                FROM dba_data_files d CROSS JOIN (SELECT name FROM v$database)
                ORDER BY d.tablespace_name, d.file_name
                """
            ),
            errors=errors,
        )

    def _query_schema_wise_object_count_section(
        self,
        metadata: OracleSourceMetadata,
    ) -> OracleDiscoverySection | None:
        rows: list[dict[str, str]] = []
        for item in metadata.schema_inventory[:DEFAULT_DISCOVERY_ROW_LIMIT]:
            for object_type, count in (
                ("TABLE", item.table_count),
                ("INDEX", item.index_count),
                ("VIEW", item.view_count),
                ("MATERIALIZED VIEW", item.materialized_view_count),
                ("SEQUENCE", item.sequence_count),
                ("PROCEDURE", item.procedure_count),
                ("FUNCTION", item.function_count),
                ("PACKAGE", item.package_count),
                ("TRIGGER", item.trigger_count),
            ):
                if count <= 0:
                    continue
                rows.append(
                    {
                        "CONTAINER": item.container_name,
                        "TYPE_ID": "CDB-ROOT" if item.container_type == "CDB_ROOT" else f"PDB-{item.con_id}",
                        "OWNER": item.owner,
                        "OBJECT_TYPE": object_type,
                        "OBJECT_COUNT": str(count),
                    }
                )
        return OracleDiscoverySection(
            key="schema_wise_object_count",
            title="DB:Schema Wise Object Count from CDB/PDB",
            columns=["CONTAINER", "TYPE_ID", "OWNER", "OBJECT_TYPE", "OBJECT_COUNT"],
            rows=rows[:DEFAULT_DISCOVERY_ROW_LIMIT],
            row_count=len(rows),
            truncated=len(rows) > DEFAULT_DISCOVERY_ROW_LIMIT,
        )

    def _query_tablespace_details_section(
        self,
        metadata: OracleSourceMetadata,
    ) -> OracleDiscoverySection | None:
        rows = [
            {
                "CONTAINER": item.container_name,
                "TYPE_ID": "CDB-ROOT" if item.container_type == "CDB_ROOT" else f"PDB-{item.con_id}",
                "TABLESPACE": item.tablespace_name,
                "CONTENTS": self._stringify_value(item.contents),
                "EXTENT_MAN": self._stringify_value(item.extent_management),
                "SEGMEN": self._stringify_value(item.segment_space_management),
                "AUT": "YES" if item.bigfile else "NO",
                "STATUS": self._stringify_value(item.status),
                "BLOCK_SIZE": self._stringify_value(item.block_size),
                "USED_MB": self._stringify_value(item.used_mb),
                "FREE_MB": self._stringify_value(item.free_mb),
                "TOTAL_MB": self._stringify_value(item.total_mb),
                "PCT_FREE": self._stringify_value(item.pct_free),
                "MAXSPACE": self._stringify_value(item.max_size_mb),
                "ENCRYPTED": "YES" if item.encrypted else "NO",
            }
            for item in metadata.tablespaces[:DEFAULT_DISCOVERY_ROW_LIMIT]
        ]
        return OracleDiscoverySection(
            key="tablespace_details",
            title="DB:Tablespace Details from CDB/PDB",
            columns=[
                "CONTAINER",
                "TYPE_ID",
                "TABLESPACE",
                "CONTENTS",
                "EXTENT_MAN",
                "SEGMEN",
                "AUT",
                "STATUS",
                "BLOCK_SIZE",
                "USED_MB",
                "FREE_MB",
                "TOTAL_MB",
                "PCT_FREE",
                "MAXSPACE",
                "ENCRYPTED",
            ],
            rows=rows,
            row_count=len(metadata.tablespaces),
            truncated=len(metadata.tablespaces) > DEFAULT_DISCOVERY_ROW_LIMIT,
        )

    def _query_archive_volume_per_day_section(
        self,
        cursor: object,
        errors: list[str],
    ) -> OracleDiscoverySection | None:
        return self._query_table_section(
            cursor,
            key="archivelog_volume_per_day",
            title="OGG:Archivelog Volume per Day",
            columns=["DAY", "ARCHIVE_COUNT", "ARCHIVE_GB"],
            query="""
                SELECT
                    TO_CHAR(TRUNC(first_time), 'YYYY-MM-DD'),
                    TO_CHAR(COUNT(*)),
                    TO_CHAR(ROUND(SUM(blocks * block_size) / POWER(1024, 3), 2))
                FROM v$archived_log
                WHERE first_time >= TRUNC(SYSDATE) - 7
                GROUP BY TRUNC(first_time)
                ORDER BY TRUNC(first_time) DESC
            """,
            errors=errors,
        )

    def _query_redo_log_switch_section(
        self,
        cursor: object,
        errors: list[str],
    ) -> OracleDiscoverySection | None:
        return self._query_table_section(
            cursor,
            key="redo_log_switch_history",
            title="Redo Log Switch History for last week and horuly",
            columns=["DAY", "HOUR", "SWITCH_COUNT"],
            query="""
                SELECT
                    TO_CHAR(first_time, 'YYYY-MM-DD'),
                    TO_CHAR(first_time, 'HH24'),
                    TO_CHAR(COUNT(*))
                FROM v$log_history
                WHERE first_time >= TRUNC(SYSDATE) - 7
                GROUP BY TO_CHAR(first_time, 'YYYY-MM-DD'), TO_CHAR(first_time, 'HH24')
                ORDER BY 1 DESC, 2 DESC
            """,
            errors=errors,
        )

    def _unsupported_datatypes_query(self, is_cdb: bool) -> str:
        return (
            """
            SELECT vc.name, c.owner, c.table_name, c.column_name, c.data_type
            FROM cdb_tab_columns c
            JOIN v$containers vc ON vc.con_id = c.con_id
            WHERE c.data_type IN ('BFILE', 'LONG', 'LONG RAW', 'UROWID', 'ANYDATA')
            ORDER BY vc.name, c.owner, c.table_name, c.column_name
            """
            if is_cdb
            else """
            SELECT name, owner, table_name, column_name, data_type
            FROM dba_tab_columns
            CROSS JOIN (SELECT name FROM v$database)
            WHERE data_type IN ('BFILE', 'LONG', 'LONG RAW', 'UROWID', 'ANYDATA')
            ORDER BY owner, table_name, column_name
            """
        )

    def _compressed_objects_query(self, is_cdb: bool) -> str:
        return (
            """
            SELECT vc.name, t.owner, t.table_name, 'TABLE', t.compression
            FROM cdb_tables t
            JOIN v$containers vc ON vc.con_id = t.con_id
            WHERE t.compression = 'ENABLED'
            UNION ALL
            SELECT vc.name, p.table_owner, p.table_name || ':' || p.partition_name, 'TABLE PARTITION', p.compression
            FROM cdb_tab_partitions p
            JOIN v$containers vc ON vc.con_id = p.con_id
            WHERE p.compression = 'ENABLED'
            ORDER BY 1, 2, 3
            """
            if is_cdb
            else """
            SELECT name, owner, table_name, 'TABLE', compression
            FROM dba_tables
            CROSS JOIN (SELECT name FROM v$database)
            WHERE compression = 'ENABLED'
            UNION ALL
            SELECT name, table_owner, table_name || ':' || partition_name, 'TABLE PARTITION', compression
            FROM dba_tab_partitions
            CROSS JOIN (SELECT name FROM v$database)
            WHERE compression = 'ENABLED'
            ORDER BY 1, 2, 3
            """
        )

    @staticmethod
    def _normalize_names(values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            cleaned = value.strip().upper()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    @staticmethod
    def _sql_name_list(values: list[str]) -> str:
        return ", ".join("'" + value.replace("'", "''") + "'" for value in values)

    def _tables_without_key_query(self, is_cdb: bool) -> str:
        return (
            """
            SELECT vc.name, t.owner, t.table_name
            FROM cdb_tables t
            JOIN v$containers vc ON vc.con_id = t.con_id
            WHERE t.temporary = 'N'
              AND """
            + self._non_default_cdb_owner_filter(
                owner_column="t.owner",
                con_id_column="t.con_id",
            )
            + """
              AND NOT EXISTS (
                  SELECT 1
                  FROM cdb_constraints c
                  WHERE c.con_id = t.con_id
                    AND c.owner = t.owner
                    AND c.table_name = t.table_name
                    AND c.constraint_type IN ('P', 'U')
              )
            ORDER BY vc.name, t.owner, t.table_name
            """
            if is_cdb
            else """
            SELECT name, t.owner, t.table_name
            FROM dba_tables t
            CROSS JOIN (SELECT name FROM v$database)
            WHERE t.temporary = 'N'
              AND """
            + self._non_default_dba_owner_filter(owner_column="t.owner")
            + """
              AND NOT EXISTS (
                  SELECT 1
                  FROM dba_constraints c
                  WHERE c.owner = t.owner
                    AND c.table_name = t.table_name
                    AND c.constraint_type IN ('P', 'U')
              )
            ORDER BY t.owner, t.table_name
            """
        )

    @staticmethod
    def _stringify_value(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.isoformat(sep=" ", timespec="seconds")
        return str(value)

    @staticmethod
    def _section_row_count(
        sections: list[OracleDiscoverySection],
        key: str,
    ) -> int:
        for section in sections:
            if section.key == key:
                return section.row_count
        return 0

    @staticmethod
    def _standby_value(sections: list[OracleDiscoverySection]) -> str:
        for section in sections:
            if section.key == "standby_availability" and section.rows:
                role = section.rows[0].get("DATABASE_ROLE", "")
                return role or "Not available"
        return "Not available"

    @staticmethod
    def _container_type(container_name: str) -> str:
        return "CDB_ROOT" if container_name == "CDB$ROOT" else "PDB"
