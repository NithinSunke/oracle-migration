from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup, Tag

from backend.app.services.oracle_dependency_analysis import (
    oracle_dependency_analysis_service,
)
from backend.app.schemas.oracle import (
    MetadataEnrichmentSummary,
    OracleDiscoverySection,
    OracleDiscoverySummaryItem,
    OracleInvalidObjectOwnerSummary,
    OracleObjectInventorySummary,
    OraclePdbInventoryEntry,
    OracleSchemaInventoryEntry,
    OracleSourceMetadata,
    OracleTablespaceInventoryEntry,
    OracleUserInventoryEntry,
)


class OracleHtmlImportService:
    def import_html(
        self,
        content: bytes,
        filename: str | None = None,
    ) -> MetadataEnrichmentSummary:
        errors: list[str] = []
        notes: list[str] = []
        html_text = self._decode_content(content)
        soup = BeautifulSoup(html_text, "html.parser")

        metadata = OracleSourceMetadata(collected_at=datetime.now(timezone.utc))
        metadata.discovery_sections = self._extract_sections(soup)

        if not metadata.discovery_sections:
            return MetadataEnrichmentSummary(
                status="FAILED",
                source=None,
                collected_fields=[],
                applied_fields=[],
                errors=[
                    "The uploaded HTML file did not contain any readable metadata tables."
                ],
                notes=[],
            )

        metadata.discovery_summary = self._extract_discovery_summary(
            metadata.discovery_sections
        )
        overview_rows = self._extract_overview_rows(metadata.discovery_sections)
        self._apply_core_metadata(metadata, overview_rows)
        self._apply_scalar_section_facts(metadata, metadata.discovery_sections)
        self._apply_discovery_summary_facts(metadata)
        metadata.pdbs = self._extract_pdb_inventory(metadata.discovery_sections)
        metadata.database_users = self._extract_user_inventory(
            metadata.discovery_sections,
            metadata.db_name,
        )
        metadata.tablespaces = self._extract_tablespaces(
            metadata.discovery_sections,
            metadata.db_name,
        )
        metadata.invalid_objects_by_schema = self._extract_invalid_objects(
            metadata.discovery_sections,
            metadata.db_name,
        )
        metadata.schema_inventory = self._extract_schema_inventory(
            metadata.discovery_sections,
            metadata.db_name,
        )
        metadata.inventory_summary = self._extract_inventory_summary(
            metadata.discovery_sections,
            metadata.schema_inventory,
            metadata.invalid_objects_by_schema,
        )
        metadata.dependency_analysis = oracle_dependency_analysis_service.analyze(
            metadata
        )

        if filename:
            notes.append(f"Source metadata was imported from uploaded HTML file: {filename}.")
        else:
            notes.append("Source metadata was imported from an uploaded HTML file.")
        notes.append(
            "Imported metadata can be used for assessment and report generation when live source connectivity is unavailable."
        )

        collected_fields = self._collect_non_empty_fields(metadata)
        status = "COLLECTED" if collected_fields else "FAILED"
        if status == "FAILED":
            errors.append("The uploaded HTML file was parsed, but no source metadata fields could be extracted.")

        return MetadataEnrichmentSummary(
            status=status,
            source=metadata if status != "FAILED" else None,
            collected_fields=collected_fields,
            applied_fields=[],
            errors=errors,
            notes=notes,
        )

    @staticmethod
    def _decode_content(content: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="ignore")

    def _extract_sections(self, soup: BeautifulSoup) -> list[OracleDiscoverySection]:
        sections: list[OracleDiscoverySection] = []
        used_keys: dict[str, int] = {}

        for table in soup.find_all("table"):
            parsed = self._parse_table(table)
            if parsed is None:
                continue

            columns, rows = parsed
            title = self._resolve_table_title(table, columns)
            if title is None:
                continue

            base_key = self._section_key(title, columns)
            suffix = used_keys.get(base_key, 0) + 1
            used_keys[base_key] = suffix
            key = base_key if suffix == 1 else f"{base_key}_{suffix}"

            sections.append(
                OracleDiscoverySection(
                    key=key,
                    title=title,
                    columns=columns,
                    rows=rows,
                    row_count=len(rows),
                    truncated=False,
                )
            )

        return sections

    def _parse_table(
        self,
        table: Tag,
    ) -> tuple[list[str], list[dict[str, str]]] | None:
        rows = table.find_all("tr")
        if not rows:
            return None

        header_row: Tag | None = None
        for row in rows:
            if row.find("th") is not None:
                header_row = row
                break

        if header_row is None:
            return None

        columns = [
            self._normalize_text(cell.get_text(" ", strip=True))
            for cell in header_row.find_all(["th", "td"])
        ]
        columns = [column for column in columns if column]
        if not columns:
            return None

        data_rows: list[dict[str, str]] = []
        start_index = rows.index(header_row) + 1
        for row in rows[start_index:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            values = [self._normalize_text(cell.get_text(" ", strip=True)) for cell in cells]
            if not any(values):
                continue
            normalized_values = values[: len(columns)]
            if len(normalized_values) < len(columns):
                normalized_values.extend([""] * (len(columns) - len(normalized_values)))
            data_rows.append(
                {
                    column: normalized_values[index]
                    for index, column in enumerate(columns)
                }
            )

        if not data_rows:
            return None

        return columns, data_rows

    def _resolve_table_title(self, table: Tag, columns: list[str]) -> str | None:
        inferred = self._infer_title_from_columns(columns)
        title = self._find_nearest_heading(table)

        if title and title.upper() != "MAIN MENU":
            generic_titles = {
                "ORACLE MIGRATION FACTORY - DISCOVERY OUTPUT (V5.0)",
                "ORACLE MIGRATION APP - SOURCE METADATA SQL REPORT",
                "EXECUTION CONTEXT",
                "CORE SOURCE METADATA QUERIES",
                "INVENTORY SUMMARY QUERIES",
                "PDB AND USER INVENTORY QUERIES",
            }
            if title.upper() not in generic_titles:
                return title

        return inferred

    def _find_nearest_heading(self, table: Tag) -> str | None:
        current: Tag | None = table
        while current is not None:
            sibling = current.previous_sibling
            while sibling is not None:
                if isinstance(sibling, Tag):
                    if sibling.name in {"h1", "h2", "h3"}:
                        title = self._normalize_text(sibling.get_text(" ", strip=True))
                        if title:
                            return title
                    if sibling.name == "a" and sibling.get("name"):
                        title = self._normalize_text(str(sibling.get("name")))
                        if title:
                            return title
                sibling = sibling.previous_sibling
            parent = current.parent
            current = parent if isinstance(parent, Tag) else None
        return None

    def _infer_title_from_columns(self, columns: list[str]) -> str | None:
        column_set = {column.upper() for column in columns}
        if {"KEY_POINTS", "KEY_VALUE", "OBSERVATION"}.issubset(column_set):
            return "Discovery Summary"
        if {"DB_NAME", "DB_VERSION", "HOST_NAME", "OS_PLATFORM"}.issubset(column_set):
            return "Database Overview"
        if {"PDB_NAME", "SERVICE_NAME", "OPEN_MODE"}.issubset(column_set):
            return "PDB Inventory"
        if {"NAME", "OPEN_MODE", "OPEN_TIME", "TOTAL_SIZE_GB"}.issubset(column_set):
            return "PDB Inventory"
        return None

    def _section_key(self, title: str, columns: list[str]) -> str:
        normalized_title = title.strip().lower()
        if "discovery summary" in normalized_title:
            return "discovery_summary"
        if "database users" in normalized_title or "cdb users" in normalized_title:
            return "database_users"
        if "db link" in normalized_title:
            return "db_links"
        if "network acl" in normalized_title or "host ace" in normalized_title:
            return "network_acls"
        if "directories" in normalized_title:
            return "directories"
        if "external tables" in normalized_title:
            return "external_tables"
        if "java objects" in normalized_title:
            return "java_objects"
        if "schema wise object count" in normalized_title:
            return "schema_inventory"
        if "invalid objects" in normalized_title:
            return "invalid_objects"
        if "scheduler_jobs" in normalized_title or "scheduler jobs" in normalized_title:
            return "scheduled_jobs_scheduler"
        if "jobs_from_cdb_jobs" in normalized_title or "scheduled jobs_from_cdb_jobs" in normalized_title:
            return "scheduled_jobs_cdb_jobs"
        if "tablespace details" in normalized_title or "cdb tablespaces" in normalized_title:
            return "tablespace_details"
        if "xml_table_columns" in normalized_title:
            return "xml_table_columns"
        if "xml_table_info" in normalized_title:
            return "xml_table_info"
        if "xml_types" in normalized_title:
            return "xml_types"
        if "unsupported datatypes" in normalized_title or "all unsupported" in normalized_title:
            return "unsupported_datatypes"
        if "domain indexes" in normalized_title:
            return "domain_indexes"
        if "modifiable parameters" in normalized_title:
            return "modifiable_parameters"
        if "datafiles" in normalized_title:
            return "datafiles"
        if "pdb" in normalized_title and "inventory" in normalized_title:
            return "pdb_inventory"
        if {"DB_NAME", "DB_VERSION", "HOST_NAME", "OS_PLATFORM"}.issubset(
            {column.upper() for column in columns}
        ):
            return "database_overview"

        key = re.sub(r"[^a-z0-9]+", "_", normalized_title).strip("_")
        return key or "section"

    def _extract_discovery_summary(
        self,
        sections: list[OracleDiscoverySection],
    ) -> list[OracleDiscoverySummaryItem]:
        for section in sections:
            if not {"KEY_POINTS", "KEY_VALUE", "OBSERVATION"}.issubset(set(section.columns)):
                continue
            items: list[OracleDiscoverySummaryItem] = []
            for row in section.rows:
                key_point = row.get("KEY_POINTS", "").strip()
                key_value = row.get("KEY_VALUE", "").strip()
                observation = row.get("OBSERVATION", "").strip()
                if not key_point:
                    continue
                items.append(
                    OracleDiscoverySummaryItem(
                        key_point=key_point,
                        key_value=key_value,
                        observation=observation,
                    )
                )
            if items:
                return items
        return []

    def _extract_overview_rows(
        self,
        sections: list[OracleDiscoverySection],
    ) -> list[dict[str, str]]:
        overview_rows: list[dict[str, str]] = []
        for section in sections:
            columns = {column.upper() for column in section.columns}
            if {"DB_NAME", "DB_VERSION", "HOST_NAME", "OS_PLATFORM"}.issubset(columns):
                overview_rows.extend(section.rows)
            elif {"DB_NAME", "CDB", "DB_UNIQUE_NAME", "PLATFORM_NAME", "LOG_MODE"}.issubset(
                columns
            ):
                overview_rows.extend(section.rows)
            elif section.key.startswith("database_overview"):
                overview_rows.extend(section.rows)
        return overview_rows

    def _apply_core_metadata(
        self,
        metadata: OracleSourceMetadata,
        overview_rows: list[dict[str, str]],
    ) -> None:
        overview = overview_rows[0] if overview_rows else {}
        metadata.db_name = overview.get("DB_NAME") or metadata.db_name
        metadata.host_name = overview.get("HOST_NAME") or metadata.host_name
        metadata.edition = overview.get("EDITION") or metadata.edition
        metadata.endianness = overview.get("ENDIANNESS") or metadata.endianness
        metadata.oracle_version = (
            overview.get("DB_VERSION")
            or overview.get("VERSION")
            or metadata.oracle_version
        )
        metadata.platform = (
            overview.get("OS_PLATFORM")
            or overview.get("PLATFORM")
            or overview.get("PLATFORM_NAME")
            or metadata.platform
        )
        metadata.database_size_gb = (
            self._to_float(
                overview.get("DB_SIZE")
                or overview.get("DATABASE_SIZE_GB")
                or overview.get("TOTAL_SIZE_GB")
            )
            or metadata.database_size_gb
        )

        multitenant = (overview.get("MULTITENANT_OPTION") or "").upper()
        if "CDB" in multitenant or "MULTITENANT" in multitenant:
            metadata.deployment_type = "CDB_PDB"
        elif multitenant:
            metadata.deployment_type = "NON_CDB"

        cdb_value = (overview.get("CDB") or "").upper()
        if metadata.deployment_type is None and cdb_value:
            metadata.deployment_type = "CDB_PDB" if cdb_value == "YES" else "NON_CDB"

        log_mode = (overview.get("LOG_MODE") or "").upper()
        if metadata.archivelog_enabled is None and log_mode:
            metadata.archivelog_enabled = log_mode == "ARCHIVELOG"

    def _apply_scalar_section_facts(
        self,
        metadata: OracleSourceMetadata,
        sections: list[OracleDiscoverySection],
    ) -> None:
        section_value_map: dict[str, str] = {}
        for section in sections:
            value = self._first_scalar_value(section)
            if value is None:
                continue
            section_value_map[section.title.strip().lower()] = value

        metadata.db_name = (
            section_value_map.get("db name")
            or metadata.db_name
        )
        metadata.host_name = (
            section_value_map.get("host name")
            or metadata.host_name
        )
        metadata.edition = (
            section_value_map.get("edition banner")
            or metadata.edition
        )
        metadata.endianness = (
            section_value_map.get("endianness")
            or metadata.endianness
        )
        metadata.oracle_version = (
            section_value_map.get("oracle version")
            or metadata.oracle_version
        )
        metadata.deployment_type = (
            self._normalize_deployment_type(section_value_map.get("deployment type"))
            or metadata.deployment_type
        )
        metadata.database_size_gb = (
            self._to_float(
                section_value_map.get("database size - cdb variant")
                or section_value_map.get("database size - non-cdb variant")
                or section_value_map.get("database size")
            )
            or metadata.database_size_gb
        )
        metadata.archivelog_enabled = (
            self._to_bool(section_value_map.get("archive log enabled"))
            if self._to_bool(section_value_map.get("archive log enabled")) is not None
            else metadata.archivelog_enabled
        )
        metadata.platform = (
            section_value_map.get("platform")
            or metadata.platform
        )
        metadata.rac_enabled = (
            self._to_bool(section_value_map.get("rac enabled"))
            if self._to_bool(section_value_map.get("rac enabled")) is not None
            else metadata.rac_enabled
        )
        metadata.tde_enabled = (
            self._to_bool(section_value_map.get("tde enabled"))
            if self._to_bool(section_value_map.get("tde enabled")) is not None
            else metadata.tde_enabled
        )
        metadata.character_set = (
            section_value_map.get("nls character set")
            or metadata.character_set
        )
        metadata.nchar_character_set = (
            section_value_map.get("nls nchar character set")
            or metadata.nchar_character_set
        )

    def _first_scalar_value(self, section: OracleDiscoverySection) -> str | None:
        if len(section.rows) != 1 or len(section.columns) != 1:
            return None
        column = section.columns[0]
        value = section.rows[0].get(column, "").strip()
        return value or None

    def _apply_discovery_summary_facts(self, metadata: OracleSourceMetadata) -> None:
        facts = {
            self._normalize_text(item.key_point).upper(): item.key_value
            for item in metadata.discovery_summary
        }

        metadata.db_name = (
            facts.get("CDB NAME")
            or facts.get("DB NAME")
            or facts.get("DATABASE NAME")
            or metadata.db_name
        )
        metadata.host_name = facts.get("DATABASE SERVER") or metadata.host_name
        metadata.database_size_gb = (
            self._to_float(
                facts.get("ACTUAL DATABASE_SIZE")
                or facts.get("TOTAL DATABASE_SIZE")
                or facts.get("DB SIZE")
            )
            or metadata.database_size_gb
        )

        archive_mode = (facts.get("ARCHIVE LOG MODE") or "").upper()
        if archive_mode:
            metadata.archivelog_enabled = archive_mode == "ARCHIVELOG"

        if metadata.deployment_type is None:
            if "CDB NAME" in facts or "PDB NAME" in facts:
                metadata.deployment_type = "CDB_PDB"

        if metadata.tde_enabled is None:
            encrypted_value = (
                facts.get("DATABASE ENCRYPTED")
                or facts.get("TDE")
                or facts.get("ENCRYPTION")
                or ""
            ).upper()
            if encrypted_value:
                metadata.tde_enabled = encrypted_value in {"YES", "ENABLED", "TRUE", "OPEN"}

    def _extract_pdb_inventory(
        self,
        sections: list[OracleDiscoverySection],
    ) -> list[OraclePdbInventoryEntry]:
        entries: list[OraclePdbInventoryEntry] = []
        for section in sections:
            columns = {column.upper() for column in section.columns}
            if not (
                "PDB_NAME" in columns
                or ("NAME" in columns and "OPEN_MODE" in columns)
            ):
                continue

            for index, row in enumerate(section.rows, start=1):
                name = row.get("PDB_NAME") or row.get("NAME") or ""
                name = name.strip()
                if not name or name.upper() == "PDB$SEED":
                    continue
                service_names = self._split_csv(
                    row.get("SERVICE_NAME") or row.get("SERVICE_NAMES") or ""
                )
                entries.append(
                    OraclePdbInventoryEntry(
                        name=name,
                        con_id=self._to_int(row.get("CON_ID")) or index,
                        open_mode=row.get("OPEN_MODE") or None,
                        open_time=self._to_datetime(row.get("OPEN_TIME")),
                        service_names=service_names,
                        total_size_gb=self._to_float(
                            row.get("DB_SIZE") or row.get("TOTAL_SIZE_GB")
                        ),
                    )
                )
            if entries:
                break

        return entries

    def _extract_user_inventory(
        self,
        sections: list[OracleDiscoverySection],
        db_name: str | None,
    ) -> list[OracleUserInventoryEntry]:
        entries: list[OracleUserInventoryEntry] = []
        for section in sections:
            normalized_title = section.title.lower()
            columns = {column.upper() for column in section.columns}
            looks_like_user_inventory = (
                "users" in normalized_title
                or "database users" in normalized_title
                or "cdb users" in normalized_title
                or {"DEFAULT_TABLESPACE", "TEMPORARY_TABLESPACE", "ACCOUNT_STATUS"}.intersection(columns)
            )
            if not looks_like_user_inventory:
                continue

            for row in section.rows:
                username = (
                    row.get("CUSTOM_USER")
                    or row.get("USERNAME")
                    or row.get("USER_NAME")
                    or ""
                ).strip()
                if not username or username.upper() == "PUBLIC":
                    continue

                user_type = (
                    row.get("USER_TYPE")
                    or row.get("ACCOUNT_TYPE")
                    or "Regular"
                )
                oracle_maintained = self._to_bool(row.get("ORACLE_MAINTAINED"))
                if oracle_maintained is None:
                    oracle_maintained = "ORACLE MANAGED" in user_type.upper()
                if oracle_maintained:
                    continue

                container_name = self._container_name_from_row(row, db_name, username)
                con_id = self._to_int(row.get("CON_ID")) or 0
                container_type = (
                    "CDB_ROOT"
                    if con_id in {0, 1} and self._looks_like_root_container(container_name, db_name)
                    else "PDB"
                )

                entries.append(
                    OracleUserInventoryEntry(
                        container_name=container_name,
                        container_type=container_type,
                        con_id=con_id,
                        username=username,
                        user_type=user_type,
                        oracle_maintained=False,
                        account_status=row.get("ACCOUNT_STATUS") or None,
                        created=self._to_datetime(row.get("CREATED")),
                        expiry_date=self._to_datetime(row.get("EXPIRY_DATE")),
                        profile=row.get("PROFILE") or None,
                        password_versions=row.get("PASSWORD_VERSIONS") or None,
                        default_tablespace=row.get("DEFAULT_TABLESPACE") or None,
                        temporary_tablespace=row.get("TEMPORARY_TABLESPACE") or None,
                    )
                )

        return entries

    def _extract_tablespaces(
        self,
        sections: list[OracleDiscoverySection],
        db_name: str | None,
    ) -> list[OracleTablespaceInventoryEntry]:
        entries: list[OracleTablespaceInventoryEntry] = []
        for section in sections:
            columns = {column.upper() for column in section.columns}
            if "TABLESPACE_NAME" not in columns:
                continue

            for row in section.rows:
                tablespace_name = row.get("TABLESPACE_NAME", "").strip()
                if not tablespace_name:
                    continue
                container_name = self._container_name_from_row(row, db_name, tablespace_name)
                con_id = self._to_int(row.get("CON_ID")) or 0
                container_type = (
                    "CDB_ROOT"
                    if con_id in {0, 1} and self._looks_like_root_container(container_name, db_name)
                    else "PDB"
                )
                entries.append(
                    OracleTablespaceInventoryEntry(
                        container_name=container_name,
                        container_type=container_type,
                        con_id=con_id,
                        tablespace_name=tablespace_name,
                        contents=row.get("CONTENTS") or None,
                        extent_management=row.get("EXTENT_MANAGEMENT") or None,
                        segment_space_management=row.get("SEGMENT_SPACE_MANAGEMENT") or None,
                        bigfile=self._to_bool(row.get("BIGFILE")),
                        status=row.get("STATUS") or None,
                        block_size=self._to_int(row.get("BLOCK_SIZE")),
                        used_mb=self._to_float(row.get("USED_MB")),
                        free_mb=self._to_float(row.get("FREE_MB")),
                        total_mb=self._to_float(row.get("TOTAL_MB")),
                        pct_free=self._to_float(row.get("PCT_FREE")),
                        max_size_mb=self._to_float(row.get("MAX_SIZE_MB")),
                        encrypted=self._to_bool(row.get("ENCRYPTED")),
                    )
                )

        return entries

    def _extract_invalid_objects(
        self,
        sections: list[OracleDiscoverySection],
        db_name: str | None,
    ) -> list[OracleInvalidObjectOwnerSummary]:
        entries: list[OracleInvalidObjectOwnerSummary] = []
        for section in sections:
            normalized_title = section.title.lower()
            columns = {column.upper() for column in section.columns}
            if "invalid objects" not in normalized_title and "INVALID_OBJECT_COUNT" not in columns:
                continue
            if not {"OWNER", "SCHEMA", "USERNAME"}.intersection(columns):
                continue

            for row in section.rows:
                owner = (
                    row.get("OWNER")
                    or row.get("SCHEMA")
                    or row.get("USERNAME")
                    or row.get("CUSTOM_USER")
                    or ""
                ).strip()
                if not owner or owner.upper() == "PUBLIC":
                    continue
                invalid_count = self._to_int(
                    row.get("INVALID_OBJECT_COUNT")
                    or row.get("COUNT")
                    or row.get("OBJECT_COUNT")
                )
                if invalid_count is None:
                    continue

                container_name = self._container_name_from_row(row, db_name, owner)
                con_id = self._to_int(row.get("CON_ID")) or 0
                container_type = (
                    "CDB_ROOT"
                    if con_id in {0, 1} and self._looks_like_root_container(container_name, db_name)
                    else "PDB"
                )

                entries.append(
                    OracleInvalidObjectOwnerSummary(
                        container_name=container_name,
                        container_type=container_type,
                        con_id=con_id,
                        owner=owner,
                        invalid_object_count=invalid_count,
                    )
                )

        return entries

    def _extract_schema_inventory(
        self,
        sections: list[OracleDiscoverySection],
        db_name: str | None,
    ) -> list[OracleSchemaInventoryEntry]:
        entries: list[OracleSchemaInventoryEntry] = []
        for section in sections:
            normalized_title = section.title.lower()
            columns = {column.upper() for column in section.columns}
            if "schema wise object count" not in normalized_title and "OBJECT_COUNT" not in columns:
                continue
            if not {"OWNER", "SCHEMA", "USERNAME", "CUSTOM_USER"}.intersection(columns):
                continue

            for row in section.rows:
                owner = (
                    row.get("OWNER")
                    or row.get("SCHEMA")
                    or row.get("USERNAME")
                    or row.get("CUSTOM_USER")
                    or ""
                ).strip()
                if not owner or owner.upper() == "PUBLIC":
                    continue

                container_name = self._container_name_from_row(row, db_name, owner)
                con_id = self._to_int(row.get("CON_ID")) or 0
                container_type = (
                    "CDB_ROOT"
                    if con_id in {0, 1} and self._looks_like_root_container(container_name, db_name)
                    else ("PDB" if con_id > 1 else "NON_CDB")
                )

                entries.append(
                    OracleSchemaInventoryEntry(
                        container_name=container_name,
                        container_type=container_type,
                        con_id=con_id,
                        owner=owner,
                        object_count=self._to_int(row.get("OBJECT_COUNT")) or 0,
                        table_count=self._to_int(row.get("TABLE_COUNT")) or 0,
                        index_count=self._to_int(row.get("INDEX_COUNT")) or 0,
                        view_count=self._to_int(row.get("VIEW_COUNT")) or 0,
                        materialized_view_count=self._to_int(
                            row.get("MATERIALIZED_VIEW_COUNT")
                        )
                        or 0,
                        sequence_count=self._to_int(row.get("SEQUENCE_COUNT")) or 0,
                        procedure_count=self._to_int(row.get("PROCEDURE_COUNT")) or 0,
                        function_count=self._to_int(row.get("FUNCTION_COUNT")) or 0,
                        package_count=self._to_int(row.get("PACKAGE_COUNT")) or 0,
                        trigger_count=self._to_int(row.get("TRIGGER_COUNT")) or 0,
                        invalid_object_count=self._to_int(
                            row.get("INVALID_OBJECT_COUNT")
                        )
                        or 0,
                    )
                )

        return entries

    def _extract_inventory_summary(
        self,
        sections: list[OracleDiscoverySection],
        schema_inventory: list[OracleSchemaInventoryEntry],
        invalid_objects: list[OracleInvalidObjectOwnerSummary],
    ) -> OracleObjectInventorySummary | None:
        for section in sections:
            columns = {column.upper() for column in section.columns}
            summary_columns = {
                "SCHEMA_COUNT",
                "TOTAL_OBJECTS",
                "TOTAL_TABLES",
                "TOTAL_INDEXES",
            }
            if not summary_columns.issubset(columns) or not section.rows:
                continue
            row = section.rows[0]
            return OracleObjectInventorySummary(
                schema_count=self._to_int(row.get("SCHEMA_COUNT")) or 0,
                total_objects=self._to_int(row.get("TOTAL_OBJECTS")) or 0,
                total_tables=self._to_int(row.get("TOTAL_TABLES")) or 0,
                total_indexes=self._to_int(row.get("TOTAL_INDEXES")) or 0,
                total_views=self._to_int(row.get("TOTAL_VIEWS")) or 0,
                total_materialized_views=self._to_int(
                    row.get("TOTAL_MATERIALIZED_VIEWS")
                )
                or 0,
                total_sequences=self._to_int(row.get("TOTAL_SEQUENCES")) or 0,
                total_procedures=self._to_int(row.get("TOTAL_PROCEDURES")) or 0,
                total_functions=self._to_int(row.get("TOTAL_FUNCTIONS")) or 0,
                total_packages=self._to_int(row.get("TOTAL_PACKAGES")) or 0,
                total_triggers=self._to_int(row.get("TOTAL_TRIGGERS")) or 0,
                invalid_object_count=self._to_int(row.get("INVALID_OBJECT_COUNT")) or 0,
            )

        if not schema_inventory:
            return None

        return OracleObjectInventorySummary(
            schema_count=len({entry.owner for entry in schema_inventory}),
            total_objects=sum(entry.object_count for entry in schema_inventory),
            total_tables=sum(entry.table_count for entry in schema_inventory),
            total_indexes=sum(entry.index_count for entry in schema_inventory),
            total_views=sum(entry.view_count for entry in schema_inventory),
            total_materialized_views=sum(
                entry.materialized_view_count for entry in schema_inventory
            ),
            total_sequences=sum(entry.sequence_count for entry in schema_inventory),
            total_procedures=sum(entry.procedure_count for entry in schema_inventory),
            total_functions=sum(entry.function_count for entry in schema_inventory),
            total_packages=sum(entry.package_count for entry in schema_inventory),
            total_triggers=sum(entry.trigger_count for entry in schema_inventory),
            invalid_object_count=sum(
                entry.invalid_object_count for entry in schema_inventory
            )
            or sum(item.invalid_object_count for item in invalid_objects),
        )

    @staticmethod
    def _container_name_from_row(
        row: dict[str, str],
        db_name: str | None,
        fallback: str,
    ) -> str:
        for key in ("CONTAINER_NAME", "PDB_NAME", "CDB_NAME", "CON_NAME", "NAME"):
            value = row.get(key, "").strip()
            if value:
                return value
        return db_name or fallback

    @staticmethod
    def _looks_like_root_container(
        container_name: str | None,
        db_name: str | None,
    ) -> bool:
        normalized = (container_name or "").strip().upper()
        return normalized in {"CDB$ROOT", "ROOT"} or (
            bool(db_name) and normalized == db_name.strip().upper()
        )

    @staticmethod
    def _collect_non_empty_fields(metadata: OracleSourceMetadata) -> list[str]:
        fields: list[str] = []
        for field_name, value in metadata.model_dump(exclude={"collected_at"}).items():
            if value is None:
                continue
            if isinstance(value, list) and not value:
                continue
            fields.append(field_name)
        return fields

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    @staticmethod
    def _split_csv(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _to_int(value: str | None) -> int | None:
        if value is None:
            return None
        match = re.search(r"-?\d+", value.replace(",", ""))
        if match is None:
            return None
        return int(match.group(0))

    @staticmethod
    def _to_float(value: str | None) -> float | None:
        if value is None:
            return None
        match = re.search(r"-?\d+(?:,\d{3})*(?:\.\d+)?", value)
        if match is None:
            return None
        return float(match.group(0).replace(",", ""))

    @staticmethod
    def _to_bool(value: str | None) -> bool | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            return None
        if normalized in {"1", "YES", "Y", "TRUE", "ENABLED", "OPEN"}:
            return True
        if normalized in {"0", "NO", "N", "FALSE", "DISABLED", "NONE"}:
            return False
        return None

    @staticmethod
    def _to_datetime(value: str | None) -> datetime | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None

        candidates = (
            "%Y-%m-%d %H:%M:%S",
            "%d-%b-%y %I.%M.%S.%f %p %z",
            "%d-%b-%Y %H:%M:%S",
            "%d-%b-%y %H:%M:%S",
        )
        for fmt in candidates:
            try:
                return datetime.strptime(normalized, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def _normalize_deployment_type(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if normalized in {"CDB_PDB", "NON_CDB"}:
            return normalized
        return None


oracle_html_import_service = OracleHtmlImportService()
