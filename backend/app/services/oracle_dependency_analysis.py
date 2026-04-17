from __future__ import annotations

from collections.abc import Callable

from backend.app.schemas.oracle import (
    OracleDiscoverySection,
    OracleSchemaDependencyAnalysis,
    OracleSchemaDependencyIssue,
    OracleSourceMetadata,
)

ORACLE_SUPPLIED_SCHEMAS = {
    "ANONYMOUS",
    "APPQOSSYS",
    "AUDSYS",
    "CTXSYS",
    "DBSFWUSER",
    "DBSNMP",
    "DIP",
    "DMSYS",
    "DVF",
    "DVSYS",
    "GGSYS",
    "GSMADMIN_INTERNAL",
    "GSMCATUSER",
    "GSMROOTUSER",
    "GSMUSER",
    "LBACSYS",
    "MDDATA",
    "MDSYS",
    "OJVMSYS",
    "OLAPSYS",
    "ORACLE_OCM",
    "ORDDATA",
    "ORDPLUGINS",
    "ORDSYS",
    "OUTLN",
    "PUBLIC",
    "REMOTE_SCHEDULER_AGENT",
    "SI_INFORMTN_SCHEMA",
    "SYS",
    "SYS$UMF",
    "SYSBACKUP",
    "SYSDG",
    "SYSKM",
    "SYSRAC",
    "SYSTEM",
    "SYSMAN",
    "WMSYS",
    "XDB",
    "XS$NULL",
}

DEFAULT_DIRECTORY_NAMES = {
    "DATA_PUMP_DIR",
    "ORACLE_OCM_CONFIG_DIR",
    "OPATCH_INST_DIR",
    "OPATCH_LOG_DIR",
    "OPATCH_SCRIPT_DIR",
    "XMLDIR",
}

DEPENDENCY_ANALYSIS_VERSION = 2


class OracleDependencyAnalysisService:
    def analyze(
        self,
        metadata: OracleSourceMetadata,
    ) -> OracleSchemaDependencyAnalysis:
        sections_by_key = {section.key: section for section in metadata.discovery_sections}

        issues = [
            self._issue_from_sections(
                sections_by_key=sections_by_key,
                code="DB_LINKS",
                label="Database links",
                section_keys=["db_links"],
                status_when_found="HIGH_RISK",
                observation_when_found=(
                    "Database links can fail late during migration because they depend on remote connectivity, credentials, and post-cutover endpoint mapping."
                ),
                recommended_action=(
                    "Inventory each DB link target, credential owner, and usage path. Replace, disable, or recreate links as part of cutover planning."
                ),
                object_name_resolver=self._resolve_db_link_name,
            ),
            self._issue_from_sections(
                sections_by_key=sections_by_key,
                code="DIRECTORY_OBJECTS",
                label="Directory objects",
                section_keys=["directories"],
                status_when_found="REVIEW",
                observation_when_found=(
                    "Directory objects often hide file-system dependencies for external tables, BFILEs, Data Pump, or custom application file handling."
                ),
                recommended_action=(
                    "Review which directory objects are still required on the target host and recreate only the ones needed by the application or migration tooling."
                ),
                object_name_resolver=self._resolve_directory_name,
            ),
            self._issue_from_sections(
                sections_by_key=sections_by_key,
                code="EXTERNAL_TABLES",
                label="External tables",
                section_keys=["external_tables"],
                status_when_found="HIGH_RISK",
                observation_when_found=(
                    "External tables depend on target-side file paths, directory objects, and operating-system access that are easy to miss until late testing."
                ),
                recommended_action=(
                    "Map each external table to its target directory, file source, and access method. Validate target path permissions before rehearsal."
                ),
                object_name_resolver=self._resolve_external_table_name,
            ),
            self._issue_from_sections(
                sections_by_key=sections_by_key,
                code="SCHEDULER_JOBS",
                label="Scheduler jobs",
                section_keys=["scheduled_jobs_cdb_jobs", "scheduled_jobs_scheduler"],
                status_when_found="REVIEW",
                observation_when_found=(
                    "Scheduled jobs can fire unexpectedly after import or cutover and may still reference source-side paths, services, or credentials."
                ),
                recommended_action=(
                    "Inventory jobs, decide which to disable during migration, and validate external dependencies before re-enabling them on the target."
                ),
                object_name_resolver=self._resolve_scheduler_job_name,
            ),
            self._issue_from_sections(
                sections_by_key=sections_by_key,
                code="NETWORK_ACLS",
                label="Network ACLs",
                section_keys=["network_acls"],
                status_when_found="HIGH_RISK",
                observation_when_found=(
                    "ACL-protected network calls such as UTL_HTTP, SMTP, or web-service integrations often fail only after migration when ACLs are missing or incomplete."
                ),
                recommended_action=(
                    "Review ACL principals, hosts, and privileges. Recreate required ACL entries on the target before integration testing."
                ),
                object_name_resolver=self._resolve_network_acl_name,
            ),
            self._issue_from_sections(
                sections_by_key=sections_by_key,
                code="JAVA_OBJECTS",
                label="Java objects",
                section_keys=["java_objects"],
                status_when_found="HIGH_RISK",
                observation_when_found=(
                    "Java-based database objects can introduce JVM, permission, and component dependencies that are frequently discovered late in migrations."
                ),
                recommended_action=(
                    "Review Java schema objects, JVM component requirements, and any external JAR or file dependencies before migration rehearsal."
                ),
                object_name_resolver=self._resolve_java_object_name,
            ),
            self._issue_from_sections(
                sections_by_key=sections_by_key,
                code="XML_DB_USAGE",
                label="XML DB usage",
                section_keys=["xml_table_columns", "xml_table_info", "xml_types"],
                status_when_found="REVIEW",
                observation_when_found=(
                    "XML DB usage can add XMLType storage, schema, and component dependencies that need explicit target validation."
                ),
                recommended_action=(
                    "Review XMLType columns, XML tables, and XML schema usage. Confirm component support and validate application behavior on the target."
                ),
                object_name_resolver=self._resolve_xml_usage_name,
            ),
            self._issue_from_sections(
                sections_by_key=sections_by_key,
                code="UNSUPPORTED_FEATURES",
                label="Unsupported features and datatypes",
                section_keys=["unsupported_datatypes", "domain_indexes"],
                status_when_found="HIGH_RISK",
                observation_when_found=(
                    "Unsupported datatypes, domain indexes, or related edge-case objects often cause migration failures after the main plan already looks viable."
                ),
                recommended_action=(
                    "Review unsupported datatypes and domain indexes early, then choose object-level remediation, exclusion, or alternate migration tooling before execution."
                ),
                object_name_resolver=self._resolve_unsupported_feature_name,
            ),
        ]

        high_risk_count = sum(1 for issue in issues if issue.status == "HIGH_RISK")
        review_count = sum(1 for issue in issues if issue.status == "REVIEW")
        clear_count = sum(1 for issue in issues if issue.status == "CLEAR")

        if high_risk_count:
            status = "HIGH_RISK"
            summary = (
                "High-risk schema dependencies were detected. Review the flagged features before finalizing migration design or cutover steps."
            )
        elif review_count:
            status = "REVIEW"
            summary = (
                "Schema dependency review is required. No immediate blockers were found in every category, but some object classes need DBA validation."
            )
        else:
            status = "CLEAR"
            summary = (
                "No late-breaking schema dependency classes were detected in the collected metadata."
            )

        return OracleSchemaDependencyAnalysis(
            analysis_version=DEPENDENCY_ANALYSIS_VERSION,
            status=status,
            summary=summary,
            high_risk_count=high_risk_count,
            review_count=review_count,
            clear_count=clear_count,
            issues=issues,
        )

    def _issue_from_sections(
        self,
        *,
        sections_by_key: dict[str, OracleDiscoverySection],
        code: str,
        label: str,
        section_keys: list[str],
        status_when_found: str,
        observation_when_found: str,
        recommended_action: str,
        object_name_resolver: Callable[[str, dict[str, str]], str | None],
    ) -> OracleSchemaDependencyIssue:
        present_sections = [sections_by_key[key] for key in section_keys if key in sections_by_key]
        relevant_rows = self._relevant_rows_from_sections(present_sections)
        row_count = len(relevant_rows)
        object_names = self._object_names_from_rows(
            relevant_rows,
            object_name_resolver,
        )

        if row_count > 0:
            return OracleSchemaDependencyIssue(
                code=code,
                label=label,
                status=status_when_found,
                object_count=row_count,
                observation=observation_when_found,
                recommended_action=recommended_action,
                object_names=object_names,
                examples=object_names,
                section_keys=section_keys,
            )

        if present_sections:
            return OracleSchemaDependencyIssue(
                code=code,
                label=label,
                status="CLEAR",
                object_count=0,
                observation="No objects from this dependency class were detected in the collected metadata.",
                recommended_action=recommended_action,
                object_names=[],
                examples=[],
                section_keys=section_keys,
            )

        return OracleSchemaDependencyIssue(
            code=code,
            label=label,
            status="REVIEW",
            object_count=0,
            observation="This dependency class was not present in the collected metadata set, so it should be reviewed manually.",
            recommended_action=recommended_action,
            object_names=[],
            examples=[],
            section_keys=section_keys,
        )

    @staticmethod
    def _object_names_from_rows(
        section_rows: list[tuple[str, dict[str, str]]],
        resolver: Callable[[str, dict[str, str]], str | None],
    ) -> list[str]:
        object_names: list[str] = []
        for section_key, row in section_rows:
            object_name = resolver(section_key, row)
            if not object_name:
                continue
            if object_name not in object_names:
                object_names.append(object_name)
            if len(object_names) >= 10:
                return object_names
        return object_names

    @staticmethod
    def _value(row: dict[str, str], key: str) -> str:
        return row.get(key, "").strip()

    @classmethod
    def _relevant_rows_from_sections(
        cls,
        sections: list[OracleDiscoverySection],
    ) -> list[tuple[str, dict[str, str]]]:
        relevant_rows: list[tuple[str, dict[str, str]]] = []
        for section in sections:
            for row in section.rows:
                if cls._is_installation_default_row(section.key, row):
                    continue
                relevant_rows.append((section.key, row))
        return relevant_rows

    @classmethod
    def _is_installation_default_row(
        cls,
        section_key: str,
        row: dict[str, str],
    ) -> bool:
        if section_key == "directories":
            directory_name = cls._value(row, "DIRECTORY_NAME").upper()
            return directory_name in DEFAULT_DIRECTORY_NAMES or directory_name.startswith(
                "OPATCH_"
            )

        if section_key == "scheduled_jobs_cdb_jobs":
            return cls._is_oracle_supplied_principal(
                cls._value(row, "SCHEMA_USER")
            ) or cls._is_oracle_supplied_principal(cls._value(row, "LOG_USER"))

        if section_key == "network_acls":
            return cls._is_oracle_supplied_principal(cls._value(row, "PRINCIPAL"))

        owner = cls._value(row, "OWNER")
        if owner:
            return cls._is_oracle_supplied_principal(owner)

        schema_user = cls._value(row, "SCHEMA_USER")
        if schema_user:
            return cls._is_oracle_supplied_principal(schema_user)

        return False

    @staticmethod
    def _is_oracle_supplied_principal(value: str) -> bool:
        return value.strip().upper() in ORACLE_SUPPLIED_SCHEMAS if value else False

    @classmethod
    def _with_container(cls, row: dict[str, str], object_name: str | None) -> str | None:
        if not object_name:
            return None
        container = cls._value(row, "CONTAINER")
        return f"{container}: {object_name}" if container else object_name

    @classmethod
    def _owner_qualified_name(
        cls,
        row: dict[str, str],
        *parts: str,
    ) -> str | None:
        owner = cls._value(row, "OWNER") or cls._value(row, "SCHEMA_USER")
        name_parts = [cls._value(row, part) for part in parts if cls._value(row, part)]
        if not name_parts:
            return None
        base_name = ".".join(name_parts)
        return f"{owner}.{base_name}" if owner else base_name

    @classmethod
    def _resolve_db_link_name(cls, _section_key: str, row: dict[str, str]) -> str | None:
        return cls._with_container(row, cls._owner_qualified_name(row, "DB_LINK"))

    @classmethod
    def _resolve_directory_name(cls, _section_key: str, row: dict[str, str]) -> str | None:
        return cls._with_container(row, cls._value(row, "DIRECTORY_NAME") or None)

    @classmethod
    def _resolve_external_table_name(cls, _section_key: str, row: dict[str, str]) -> str | None:
        return cls._with_container(row, cls._owner_qualified_name(row, "TABLE_NAME"))

    @classmethod
    def _resolve_scheduler_job_name(cls, section_key: str, row: dict[str, str]) -> str | None:
        if section_key == "scheduled_jobs_scheduler":
            object_name = cls._owner_qualified_name(row, "JOB_NAME")
        else:
            job_id = cls._value(row, "JOB")
            schema_user = cls._value(row, "SCHEMA_USER")
            object_name = f"{schema_user}.JOB#{job_id}" if schema_user and job_id else None
        return cls._with_container(row, object_name)

    @classmethod
    def _resolve_network_acl_name(cls, _section_key: str, row: dict[str, str]) -> str | None:
        host = cls._value(row, "HOST")
        principal = cls._value(row, "PRINCIPAL")
        if not host and not principal:
            return None
        object_name = f"{host} ({principal})" if host and principal else host or principal
        return cls._with_container(row, object_name)

    @classmethod
    def _resolve_java_object_name(cls, _section_key: str, row: dict[str, str]) -> str | None:
        return cls._with_container(row, cls._owner_qualified_name(row, "OBJECT_NAME"))

    @classmethod
    def _resolve_xml_usage_name(cls, section_key: str, row: dict[str, str]) -> str | None:
        if section_key in {"xml_table_columns", "xml_types"}:
            object_name = cls._owner_qualified_name(row, "TABLE_NAME", "COLUMN_NAME")
        else:
            object_name = cls._owner_qualified_name(row, "TABLE_NAME")
        return cls._with_container(row, object_name)

    @classmethod
    def _resolve_unsupported_feature_name(
        cls,
        section_key: str,
        row: dict[str, str],
    ) -> str | None:
        if section_key == "domain_indexes":
            object_name = cls._owner_qualified_name(row, "INDEX_NAME")
        else:
            object_name = cls._owner_qualified_name(row, "TABLE_NAME", "COLUMN_NAME")
        return cls._with_container(row, object_name)


oracle_dependency_analysis_service = OracleDependencyAnalysisService()
