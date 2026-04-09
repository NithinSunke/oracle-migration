import type {
  MigrationRecord,
  MetadataCollectionOptions,
  OracleConnectionConfig,
  RecommendationResponse,
  RecommendationReport,
} from "../../types";

export interface ImplementationRunbookDocument {
  title: string;
  filename: string;
  description: string;
}

export interface ImplementationRunbookCommand {
  title: string;
  description: string;
  language: "bash" | "sql" | "ini" | "text";
  content: string;
  filename?: string;
}

export interface ImplementationRunbookSection {
  title: string;
  description: string;
  commands: ImplementationRunbookCommand[];
}

export interface ImplementationPlan {
  overview: string;
  assumptions: string[];
  prerequisites: string[];
  warnings: string[];
  documents: ImplementationRunbookDocument[];
  sections: ImplementationRunbookSection[];
}

function formatApproach(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function getApproachKey(value: string): string {
  return value.trim().toUpperCase().replace(/[\s/-]+/g, "_");
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 32);
}

function shellQuote(value: string): string {
  return JSON.stringify(value);
}

function pick<T>(...values: Array<T | null | undefined>): T | undefined {
  return values.find((value) => value !== null && value !== undefined);
}

function valueOrPlaceholder(value: string | number | undefined, placeholder: string): string {
  if (value === undefined) {
    return placeholder;
  }
  const normalized = String(value).trim();
  return normalized || placeholder;
}

function getValidationWarnings(
  migration: MigrationRecord,
  recommendation: RecommendationResponse,
): string[] {
  const warnings = [
    ...(migration.migration_validation?.warnings ?? []),
    ...recommendation.risk_flags,
    ...recommendation.manual_review_flags,
  ];

  return Array.from(new Set(warnings));
}

function getConnections(
  metadataCollection: MetadataCollectionOptions | null | undefined,
): {
  source: OracleConnectionConfig | null;
  target: OracleConnectionConfig | null;
} {
  return {
    source: metadataCollection?.source_connection ?? null,
    target: metadataCollection?.target_connection ?? null,
  };
}

function getPrimarySchemaHint(migration: MigrationRecord): string {
  if (
    migration.scope.migration_scope === "SCHEMA" &&
    migration.scope.schema_count === 1 &&
    migration.source_metadata?.schema_inventory.length
  ) {
    return migration.source_metadata.schema_inventory[0].owner;
  }
  return "<schema_list>";
}

function getSelectionClause(migration: MigrationRecord): string {
  switch (migration.scope.migration_scope) {
    case "FULL_DATABASE":
      return "full=y";
    case "SCHEMA":
      return `schemas=${getPrimarySchemaHint(migration)}`;
    case "TABLE":
      return "tables=<schema.table_name>";
    case "SUBSET":
      return "include=<object_type:\"IN (...)\" clause>";
    default:
      return "full=y";
  }
}

function getParallelDegree(migration: MigrationRecord): number {
  const size = migration.source.database_size_gb ?? migration.source_metadata?.database_size_gb ?? 0;
  if (size >= 1000) {
    return 12;
  }
  if (size >= 250) {
    return 8;
  }
  return 4;
}

function buildConnectionProfileCommand(
  label: "SRC" | "TGT",
  roleLabel: string,
  connection: OracleConnectionConfig | null,
  fallbackService: string,
): ImplementationRunbookCommand {
  const userVar = `${label}_DB_USER`;
  const passVar = `${label}_DB_PASS`;
  const hostVar = `${label}_DB_HOST`;
  const portVar = `${label}_DB_PORT`;
  const serviceVar = `${label}_DB_SERVICE`;
  const host = valueOrPlaceholder(connection?.host, `<${label.toLowerCase()}_host>`);
  const port = valueOrPlaceholder(connection?.port, "1521");
  const service = valueOrPlaceholder(connection?.service_name, fallbackService);
  const username = valueOrPlaceholder(connection?.username, `<${label.toLowerCase()}_user>`);

  return {
    title: `${roleLabel} connection profile`,
    description:
      `Export reusable variables for the ${roleLabel.toLowerCase()} Oracle connection. ` +
      "Only replace the password placeholder before running the commands.",
    language: "bash",
    filename: `${label.toLowerCase()}_connection_profile.sh`,
    content: [
      `export ${label}_DB_HOST=${shellQuote(host)}`,
      `export ${label}_DB_PORT=${shellQuote(port)}`,
      `export ${label}_DB_SERVICE=${shellQuote(service)}`,
      `export ${label}_DB_USER=${shellQuote(username)}`,
      `export ${label}_DB_PASS=${shellQuote(`<${roleLabel.toLowerCase().replace(/\s+/g, "_")}_password>`)}`,
      `export ${label}_CONNECT_STRING="\${${userVar}}/\${${passVar}}@//\${${hostVar}}:\${${portVar}}/\${${serviceVar}}"`,
    ].join("\n"),
  };
}

function buildConnectivityTestCommand(
  label: "SRC" | "TGT",
  roleLabel: string,
): ImplementationRunbookCommand {
  const connectVar = `${label}_CONNECT_STRING`;
  return {
    title: `${roleLabel} login test`,
    description:
      `Run a lightweight SQL*Plus login test against the ${roleLabel.toLowerCase()} database before executing migration tooling.`,
    language: "bash",
    filename: `${label.toLowerCase()}_login_test.sh`,
    content: [
      `sqlplus -L "\${${connectVar}}" <<'SQL'`,
      "set pages 100 lines 220",
      "select name, db_unique_name, open_mode, log_mode from v$database;",
      "select instance_name, host_name, version from v$instance;",
      "SQL",
    ].join("\n"),
  };
}

function buildSourceDiscoveryCommand(): ImplementationRunbookCommand {
  return {
    title: "Source metadata collection HTML",
    description:
      "Generate the HTML discovery report from SQL*Plus so the app can ingest it directly when a live connection is not available later.",
    language: "bash",
    filename: "source_metadata_collection.sh",
    content: [
      "sqlplus -L \"${SRC_CONNECT_STRING}\" @source_metadata_collection_html.sql",
      "",
      "# Output file:",
      "ls -l source_metadata_collection_report.html",
    ].join("\n"),
  };
}

function buildTargetReadinessSql(): ImplementationRunbookCommand {
  return {
    title: "Target readiness SQL",
    description:
      "Validate target version, open mode, role, and character set before executing the chosen migration method.",
    language: "bash",
    filename: "target_readiness_checks.sh",
    content: [
      "sqlplus -L \"${TGT_CONNECT_STRING}\" <<'SQL'",
      "set pages 200 lines 220",
      "select name, db_unique_name, open_mode, database_role from v$database;",
      "select value from nls_database_parameters where parameter = 'NLS_CHARACTERSET';",
      "select value from nls_database_parameters where parameter = 'NLS_NCHAR_CHARACTERSET';",
      "show parameter global_names",
      "SQL",
    ].join("\n"),
  };
}

function buildPostCutoverValidationSql(migration: MigrationRecord): ImplementationRunbookCommand {
  const schemaFilter =
    migration.scope.migration_scope === "FULL_DATABASE"
      ? ""
      : getPrimarySchemaHint(migration) === "<schema_list>"
        ? "  and owner in (<schema_list>)"
        : `  and owner in ('${getPrimarySchemaHint(migration)}')`;

  return {
    title: "Post-cutover validation SQL",
    description:
      "Run the same validation set after import, restore, sync, or switchover to confirm object health and service readiness.",
    language: "bash",
    filename: "post_cutover_validation.sh",
    content: [
      "sqlplus -L \"${TGT_CONNECT_STRING}\" <<'SQL'",
      "set pages 200 lines 220",
      "select name, open_mode, database_role from v$database;",
      "select owner, count(*) as invalid_objects",
      "from dba_objects",
      "where status <> 'VALID'",
      schemaFilter,
      "group by owner",
      "order by count(*) desc;",
      "select owner, object_name, object_type, status",
      "from dba_objects",
      "where status <> 'VALID'",
      schemaFilter,
      "fetch first 50 rows only;",
      "SQL",
    ]
      .filter(Boolean)
      .join("\n"),
  };
}

function buildDataPumpSection(
  migration: MigrationRecord,
  requestSlug: string,
): ImplementationRunbookSection {
  const selection = getSelectionClause(migration);
  const parallel = getParallelDegree(migration);
  const directoryName = `DP_${requestSlug.toUpperCase()}`.slice(0, 28);
  const dumpPrefix = `${requestSlug}_src`;
  const sourceHost = valueOrPlaceholder(
    migration.metadata_collection?.source_connection?.host,
    "<source_host>",
  );
  const targetHost = valueOrPlaceholder(
    migration.metadata_collection?.target_connection?.host,
    "<target_host>",
  );
  const sourceService = valueOrPlaceholder(
    migration.metadata_collection?.source_connection?.service_name,
    "<source_service>",
  );
  const targetService = valueOrPlaceholder(
    migration.metadata_collection?.target_connection?.service_name,
    "<target_service>",
  );
  const sourceUser = valueOrPlaceholder(
    migration.metadata_collection?.source_connection?.username,
    "<source_user>",
  );
  const targetUser = valueOrPlaceholder(
    migration.metadata_collection?.target_connection?.username,
    "<target_user>",
  );
  const schemaHint = getPrimarySchemaHint(migration);
  const sourceDumpPath = `/u02/dpump/${requestSlug}/${sourceService}`;
  const targetDumpPath = `/u02/dpump/${requestSlug}/${targetService}`;
  const scopeLabel = migration.scope.migration_scope.replace(/_/g, " ").toLowerCase();

  const importSelection =
    migration.scope.migration_scope === "FULL_DATABASE"
      ? "full=y"
      : selection;
  const remapSchema = migration.scope.need_schema_remap
    ? "\nremap_schema=<source_schema>:<target_schema>"
    : "";
  const remapTablespace = migration.scope.need_tablespace_remap
    ? "\nremap_tablespace=<source_tablespace>:<target_tablespace>"
    : "";

  return {
    title: "Data Pump Command Runbook",
    description:
      `Use these Data Pump commands for the approved ${scopeLabel} migration. ` +
      "They are structured as an execution runbook with source preparation, export, transfer, import, and validation steps.",
    commands: [
      {
        title: "Utility help commands",
        description:
          "Run these first if the DBA team wants to review the available Data Pump options directly on the source or target host.",
        language: "bash",
        filename: "datapump_help_commands.sh",
        content: [
          "expdp help=y",
          "impdp help=y",
        ].join("\n"),
      },
      {
        title: "Source host dump directory",
        description:
          `Create the filesystem directory on source host ${sourceHost} before creating the Oracle directory object.`,
        language: "bash",
        filename: `${requestSlug}_source_dump_dir.sh`,
        content: [
          `ssh oracle@${sourceHost}`,
          `mkdir -p ${sourceDumpPath}`,
          `chmod 775 ${sourceDumpPath}`,
          `ls -ld ${sourceDumpPath}`,
        ].join("\n"),
      },
      {
        title: "Source Oracle directory and grants",
        description:
          "Create the source-side Oracle directory object and grant the captured source user read and write access.",
        language: "bash",
        filename: `${requestSlug}_source_directory_setup.sh`,
        content: [
          "sqlplus -L \"${SRC_CONNECT_STRING}\" <<'SQL'",
          `create or replace directory ${directoryName} as '${sourceDumpPath}';`,
          `grant read, write on directory ${directoryName} to ${sourceUser};`,
          "select directory_name, directory_path from dba_directories where directory_name = upper('" + directoryName + "');",
          "SQL",
        ].join("\n"),
      },
      {
        title: "Source export parameter file",
        description:
          "Save this as the source export parameter file. It already reflects the captured migration scope and parallelism.",
        language: "ini",
        filename: `${requestSlug}_expdp.par`,
        content: [
          `directory=${directoryName}`,
          `dumpfile=${dumpPrefix}_%U.dmp`,
          `logfile=${requestSlug}_expdp.log`,
          selection,
          `parallel=${parallel}`,
          "metrics=y",
          "logtime=all",
          "cluster=n",
          "flashback_time=systimestamp",
          "exclude=statistics",
        ].join("\n"),
      },
      {
        title: "Source export command",
        description:
          "Run the export from the source host after saving the parameter file locally.",
        language: "bash",
        filename: `${requestSlug}_expdp.sh`,
        content: `expdp "\${SRC_CONNECT_STRING}" parfile=${requestSlug}_expdp.par`,
      },
      {
        title: "Alternative direct export examples",
        description:
          "Use one of these direct command forms if you prefer not to maintain a parameter file.",
        language: "bash",
        filename: `${requestSlug}_expdp_examples.sh`,
        content: [
          `expdp "\${SRC_CONNECT_STRING}" full=y directory=${directoryName} dumpfile=${dumpPrefix}_full_%U.dmp logfile=${requestSlug}_full_expdp.log parallel=${parallel}`,
          `expdp "\${SRC_CONNECT_STRING}" schemas=${schemaHint} directory=${directoryName} dumpfile=${dumpPrefix}_schema_%U.dmp logfile=${requestSlug}_schema_expdp.log parallel=${parallel}`,
          `expdp "\${SRC_CONNECT_STRING}" tables=<schema.table_name> directory=${directoryName} dumpfile=${dumpPrefix}_table_%U.dmp logfile=${requestSlug}_table_expdp.log`,
        ].join("\n\n"),
      },
      {
        title: "Dump file transfer to target host",
        description:
          `Copy the generated dump files from source host ${sourceHost} to target host ${targetHost} before import starts.`,
        language: "bash",
        filename: `${requestSlug}_dump_transfer.sh`,
        content: [
          `ssh oracle@${targetHost} "mkdir -p ${targetDumpPath} && chmod 775 ${targetDumpPath}"`,
          `scp ${sourceDumpPath}/${dumpPrefix}_*.dmp oracle@${targetHost}:${targetDumpPath}/`,
          `scp ${sourceDumpPath}/${requestSlug}_expdp.log oracle@${targetHost}:${targetDumpPath}/`,
        ].join("\n"),
      },
      {
        title: "Target Oracle directory and grants",
        description:
          "Create the target-side Oracle directory object and grant the captured target user read and write access.",
        language: "bash",
        filename: `${requestSlug}_target_directory_setup.sh`,
        content: [
          "sqlplus -L \"${TGT_CONNECT_STRING}\" <<'SQL'",
          `create or replace directory ${directoryName} as '${targetDumpPath}';`,
          `grant read, write on directory ${directoryName} to ${targetUser};`,
          "select directory_name, directory_path from dba_directories where directory_name = upper('" + directoryName + "');",
          "SQL",
        ].join("\n"),
      },
      {
        title: "Target import parameter file",
        description:
          "Save this as the target import parameter file. Keep remap clauses only when the assessment requires schema or tablespace remapping.",
        language: "ini",
        filename: `${requestSlug}_impdp.par`,
        content: [
          `directory=${directoryName}`,
          `dumpfile=${dumpPrefix}_%U.dmp`,
          `logfile=${requestSlug}_impdp.log`,
          importSelection,
          `parallel=${parallel}`,
          "metrics=y",
          "logtime=all",
          "table_exists_action=replace",
          remapSchema.trim(),
          remapTablespace.trim(),
        ]
          .filter(Boolean)
          .join("\n"),
      },
      {
        title: "Target import command",
        description:
          "Run the import from the target host after the dump files are copied and the Oracle directory object is in place.",
        language: "bash",
        filename: `${requestSlug}_impdp.sh`,
        content: `impdp "\${TGT_CONNECT_STRING}" parfile=${requestSlug}_impdp.par`,
      },
      {
        title: "Alternative direct import examples",
        description:
          "Use these direct import forms when the DBA team wants one-liner commands for schema, full, or remap-based imports.",
        language: "bash",
        filename: `${requestSlug}_impdp_examples.sh`,
        content: [
          `impdp "\${TGT_CONNECT_STRING}" full=y directory=${directoryName} dumpfile=${dumpPrefix}_full_%U.dmp logfile=${requestSlug}_full_impdp.log parallel=${parallel}`,
          `impdp "\${TGT_CONNECT_STRING}" schemas=${schemaHint} directory=${directoryName} dumpfile=${dumpPrefix}_schema_%U.dmp logfile=${requestSlug}_schema_impdp.log parallel=${parallel}`,
          `impdp "\${TGT_CONNECT_STRING}" schemas=${schemaHint} directory=${directoryName} dumpfile=${dumpPrefix}_schema_%U.dmp logfile=${requestSlug}_remap_impdp.log remap_schema=<source_schema>:<target_schema> remap_tablespace=<source_tablespace>:<target_tablespace>`,
        ].join("\n\n"),
      },
      {
        title: "Network link import option",
        description:
          "Use this option only when source and target connectivity is stable and a DB link path is approved instead of dump-file movement.",
        language: "bash",
        filename: `${requestSlug}_network_link_impdp.sh`,
        content: [
          "sqlplus -L \"${TGT_CONNECT_STRING}\" <<'SQL'",
          `create database link ${requestSlug.toUpperCase()}_SRC_LINK`,
          `connect to ${sourceUser} identified by "<source_password>"`,
          `using '//${sourceHost}:${valueOrPlaceholder(migration.metadata_collection?.source_connection?.port, "1521")}/${sourceService}';`,
          "SQL",
          "",
          `impdp "\${TGT_CONNECT_STRING}" ${importSelection} network_link=${requestSlug.toUpperCase()}_SRC_LINK logfile=${requestSlug}_network_impdp.log parallel=${parallel}`,
        ].join("\n"),
      },
      {
        title: "Data-only or metadata-only import options",
        description:
          "Use these focused import patterns when the migration runbook calls for staged metadata and data loading.",
        language: "bash",
        filename: `${requestSlug}_content_only_impdp.sh`,
        content: [
          `impdp "\${TGT_CONNECT_STRING}" ${importSelection} directory=${directoryName} dumpfile=${dumpPrefix}_%U.dmp logfile=${requestSlug}_metadata_impdp.log content=metadata_only`,
          `impdp "\${TGT_CONNECT_STRING}" ${importSelection} directory=${directoryName} dumpfile=${dumpPrefix}_%U.dmp logfile=${requestSlug}_data_impdp.log content=data_only`,
        ].join("\n\n"),
      },
    ],
  };
}

function buildRmanSection(
  migration: MigrationRecord,
  sourceDbName: string,
  targetDbName: string,
): ImplementationRunbookSection {
  const duplicateTarget = targetDbName.toUpperCase() || "<target_db_name>";

  return {
    title: "Implementation Runbook",
    description:
      "Use these RMAN-oriented commands when the recommendation is backup, restore, or duplicate based.",
    commands: [
      {
        title: "RMAN source validation",
        description:
          "Check backup visibility and archivelog coverage before the duplicate or restore window starts.",
        language: "bash",
        filename: `${migration.request_id.toLowerCase()}_rman_validate.rman`,
        content: [
          "rman target \"${SRC_CONNECT_STRING}\" <<'RMAN'",
          "report schema;",
          "list backup summary;",
          "sql \"select log_mode from v$database\";",
          "exit",
          "RMAN",
        ].join("\n"),
      },
      {
        title: "RMAN duplicate command",
        description:
          `Duplicate ${sourceDbName || "<source_db_name>"} to ${duplicateTarget} using the collected source and target connection endpoints.`,
        language: "bash",
        filename: `${migration.request_id.toLowerCase()}_rman_duplicate.rman`,
        content: [
          "rman target \"${SRC_CONNECT_STRING}\" auxiliary \"${TGT_CONNECT_STRING}\" <<'RMAN'",
          `duplicate target database to '${duplicateTarget}'`,
          "  from active database",
          "  nofilenamecheck;",
          "exit",
          "RMAN",
        ].join("\n"),
      },
      {
        title: "RMAN post-open SQL",
        description:
          "Validate that the restored target is open in the expected role and logging mode.",
        language: "bash",
        filename: `${migration.request_id.toLowerCase()}_rman_post_open.sh`,
        content: [
          "sqlplus -L \"${TGT_CONNECT_STRING}\" <<'SQL'",
          "select name, open_mode, database_role, log_mode from v$database;",
          "select instance_name, host_name, version from v$instance;",
          "SQL",
        ].join("\n"),
      },
    ],
  };
}

function buildGoldenGateSection(
  sourceDbName: string,
  targetDbName: string,
): ImplementationRunbookSection {
  const sourceSlug = slugify(sourceDbName || "source_db");
  const deploymentName = `${sourceSlug}_msa`.slice(0, 24);
  return {
    title: "Implementation Runbook",
    description:
      "Use these Oracle GoldenGate Microservices Architecture snippets for low-downtime replication with source and target connection details already aligned.",
    commands: [
      {
        title: "Source supplemental logging SQL",
        description:
          "Enable the base logging required before GoldenGate extract is started.",
        language: "bash",
        filename: `${slugify(sourceDbName)}_ogg_supplemental_logging.sh`,
        content: [
          "sqlplus -L \"${SRC_CONNECT_STRING}\" <<'SQL'",
          "alter database add supplemental log data;",
          "alter database force logging;",
          "SQL",
        ].join("\n"),
      },
      {
        title: "GoldenGate Microservices environment profile",
        description:
          "Export the deployment URLs and credentials used by Admin Service, Distribution Service, and Receiver Service before creating Extract and Replicat.",
        language: "bash",
        filename: `${sourceSlug}_ogg_microservices_env.sh`,
        content: [
          `export OGG_DEPLOYMENT_NAME=${shellQuote(deploymentName)}`,
          "export OGG_ADMIN_USER=${OGG_ADMIN_USER:-oggadmin}",
          "export OGG_ADMIN_PASS=${OGG_ADMIN_PASS:-'<ogg_admin_password>'}",
          "export OGG_SRC_ADMIN_URL=${OGG_SRC_ADMIN_URL:-https://<source_ogg_host>:<adminsrvr_port>/services/v2}",
          "export OGG_SRC_DIST_URL=${OGG_SRC_DIST_URL:-https://<source_ogg_host>:<distsrvr_port>/services/v2}",
          "export OGG_TGT_ADMIN_URL=${OGG_TGT_ADMIN_URL:-https://<target_ogg_host>:<adminsrvr_port>/services/v2}",
          "export OGG_TGT_RECV_URL=${OGG_TGT_RECV_URL:-https://<target_ogg_host>:<recvsrvr_port>/services/v2}",
          "export OGG_SRC_CREDENTIAL_ALIAS=${OGG_SRC_CREDENTIAL_ALIAS:-SRCDB}",
          "export OGG_TGT_CREDENTIAL_ALIAS=${OGG_TGT_CREDENTIAL_ALIAS:-TGTDB}",
          "export OGG_PATH_NAME=${OGG_PATH_NAME:-DP01}",
          "export OGG_EXTRACT_NAME=${OGG_EXTRACT_NAME:-EXT01}",
          "export OGG_REPLICAT_NAME=${OGG_REPLICAT_NAME:-REP01}",
          "export OGG_TRAIL_NAME=${OGG_TRAIL_NAME:-ea}",
        ].join("\n"),
      },
      {
        title: "Admin Service credential store setup",
        description:
          `Register source ${sourceDbName || "<source_db_name>"} and target ${targetDbName || "<target_db_name>"} database credentials in the GoldenGate Microservices credential store.`,
        language: "bash",
        filename: `${sourceSlug}_ogg_microservices_credentials.sh`,
        content: [
          "curl -k -u \"${OGG_ADMIN_USER}:${OGG_ADMIN_PASS}\" -H 'Content-Type: application/json' \\",
          "  -X POST \"${OGG_SRC_ADMIN_URL}/credentials\" \\",
          "  -d '{",
          "    \"userid\": \"'\"${SRC_DB_USER}\"'@//'\"${SRC_DB_HOST}\"':'\"${SRC_DB_PORT}\"'/'\"${SRC_DB_SERVICE}\"'\",",
          "    \"password\": \"'\"${SRC_DB_PASS}\"'\",",
          "    \"alias\": \"'\"${OGG_SRC_CREDENTIAL_ALIAS}\"'\"",
          "  }'",
          "",
          "curl -k -u \"${OGG_ADMIN_USER}:${OGG_ADMIN_PASS}\" -H 'Content-Type: application/json' \\",
          "  -X POST \"${OGG_TGT_ADMIN_URL}/credentials\" \\",
          "  -d '{",
          "    \"userid\": \"'\"${TGT_DB_USER}\"'@//'\"${TGT_DB_HOST}\"':'\"${TGT_DB_PORT}\"'/'\"${TGT_DB_SERVICE}\"'\",",
          "    \"password\": \"'\"${TGT_DB_PASS}\"'\",",
          "    \"alias\": \"'\"${OGG_TGT_CREDENTIAL_ALIAS}\"'\"",
          "  }'",
        ].join("\n"),
      },
      {
        title: "Distribution path and process creation via REST",
        description:
          "Create the Extract, target Receiver path, and Replicat by using the Microservices REST endpoints instead of classic GGSCI commands.",
        language: "bash",
        filename: `${sourceSlug}_ogg_microservices_setup.sh`,
        content: [
          "curl -k -u \"${OGG_ADMIN_USER}:${OGG_ADMIN_PASS}\" -H 'Content-Type: application/json' \\",
          "  -X POST \"${OGG_SRC_ADMIN_URL}/extracts\" \\",
          "  -d '{",
          "    \"name\": \"'\"${OGG_EXTRACT_NAME}\"'\",",
          "    \"type\": \"integrated\",",
          "    \"begin\": \"now\",",
          "    \"config\": [",
          "      \"EXTRACT ${OGG_EXTRACT_NAME}\",",
          "      \"USERIDALIAS ${OGG_SRC_CREDENTIAL_ALIAS}\",",
          "      \"EXTTRAIL ./dirdat/${OGG_TRAIL_NAME}\",",
          "      \"DDL INCLUDE MAPPED\",",
          "      \"TABLE <schema_list>.*;\"",
          "    ]",
          "  }'",
          "",
          "curl -k -u \"${OGG_ADMIN_USER}:${OGG_ADMIN_PASS}\" -H 'Content-Type: application/json' \\",
          "  -X POST \"${OGG_SRC_DIST_URL}/paths\" \\",
          "  -d '{",
          "    \"name\": \"'\"${OGG_PATH_NAME}\"'\",",
          "    \"source\": \"'\"${OGG_EXTRACT_NAME}\"'\",",
          "    \"target\": \"'\"${OGG_TGT_RECV_URL}\"'/receivers/default\",",
          "    \"trail\": \"'\"${OGG_TRAIL_NAME}\"'\"",
          "  }'",
          "",
          "curl -k -u \"${OGG_ADMIN_USER}:${OGG_ADMIN_PASS}\" -H 'Content-Type: application/json' \\",
          "  -X POST \"${OGG_TGT_ADMIN_URL}/replicats\" \\",
          "  -d '{",
          "    \"name\": \"'\"${OGG_REPLICAT_NAME}\"'\",",
          "    \"type\": \"integrated\",",
          "    \"config\": [",
          "      \"REPLICAT ${OGG_REPLICAT_NAME}\",",
          "      \"USERIDALIAS ${OGG_TGT_CREDENTIAL_ALIAS}\",",
          "      \"MAP <schema_list>.*, TARGET <schema_list>.*;\"",
          "    ]",
          "  }'",
        ].join("\n"),
      },
      {
        title: "GoldenGate Microservices parameter skeleton",
        description:
          "Use this skeleton for Microservices-managed Extract and Replicat parameter content and refine the schema mapping from the approved migration scope.",
        language: "ini",
        filename: `${sourceSlug}_goldengate_microservices_params.prm`,
        content: [
          "EXTRACT EXT01",
          "USERIDALIAS SRCDB",
          "EXTTRAIL ./dirdat/ea",
          "DDL INCLUDE MAPPED",
          "TABLE <schema_list>.*;",
          "",
          "REPLICAT REP01",
          "USERIDALIAS TGTDB",
          "MAP <schema_list>.*, TARGET <schema_list>.*;",
        ].join("\n"),
      },
      {
        title: "Microservices health and lag checks",
        description:
          "Use REST health calls to confirm Admin Service, Distribution Service, Extract, and Replicat status during rehearsal and cutover.",
        language: "bash",
        filename: `${sourceSlug}_ogg_microservices_status.sh`,
        content: [
          "curl -k -u \"${OGG_ADMIN_USER}:${OGG_ADMIN_PASS}\" \"${OGG_SRC_ADMIN_URL}/extracts/${OGG_EXTRACT_NAME}/info/status\"",
          "curl -k -u \"${OGG_ADMIN_USER}:${OGG_ADMIN_PASS}\" \"${OGG_SRC_DIST_URL}/paths/${OGG_PATH_NAME}/info/status\"",
          "curl -k -u \"${OGG_ADMIN_USER}:${OGG_ADMIN_PASS}\" \"${OGG_TGT_ADMIN_URL}/replicats/${OGG_REPLICAT_NAME}/info/status\"",
        ].join("\n"),
      },
    ],
  };
}

function buildZdmSection(
  sourceDbName: string,
  targetDbName: string,
): ImplementationRunbookSection {
  return {
    title: "Implementation Runbook",
    description:
      "Use this Zero Downtime Migration response-file flow when ZDM is the recommended execution path.",
    commands: [
      {
        title: "ZDM response file",
        description:
          "Populate the response file with the exact host, service, and DB names collected during assessment.",
        language: "ini",
        filename: `${slugify(sourceDbName)}_zdm_migration.rsp`,
        content: [
          `sourcedb=${sourceDbName || "<source_db_name>"}`,
          "sourcehost=${SRC_DB_HOST}",
          "sourcesid=${SRC_DB_SERVICE}",
          "sourceuser=${SRC_DB_USER}",
          `targetdb=${targetDbName || "<target_db_name>"}`,
          "targethost=${TGT_DB_HOST}",
          "targetsid=${TGT_DB_SERVICE}",
          "targetuser=${TGT_DB_USER}",
          "migrationmethod=online",
        ].join("\n"),
      },
      {
        title: "ZDM evaluation command",
        description:
          "Run an evaluation first so prerequisite failures are caught before the production migration command.",
        language: "bash",
        filename: `${slugify(sourceDbName)}_zdm_eval.sh`,
        content: [
          "zdmcli migrate database \\",
          "  -rsp /u01/zdm/runbooks/migration.rsp \\",
          "  -sourcesyspassword ${SRC_DB_PASS} \\",
          "  -targetsyspassword ${TGT_DB_PASS} \\",
          "  -eval",
        ].join("\n"),
      },
      {
        title: "ZDM execution command",
        description:
          "Use the same response file for the final execution after evaluation passes and the change window opens.",
        language: "bash",
        filename: `${slugify(sourceDbName)}_zdm_execute.sh`,
        content: [
          "zdmcli migrate database \\",
          "  -rsp /u01/zdm/runbooks/migration.rsp \\",
          "  -sourcesyspassword ${SRC_DB_PASS} \\",
          "  -targetsyspassword ${TGT_DB_PASS}",
        ].join("\n"),
      },
    ],
  };
}

function buildDataGuardSection(
  migration: MigrationRecord,
  sourceDbName: string,
  targetDbName: string,
): ImplementationRunbookSection {
  const requestSlug = slugify(migration.request_id || sourceDbName || "dataguard");
  const sourceUniqueName = valueOrPlaceholder(sourceDbName, "<source_db_name>");
  const targetUniqueName = valueOrPlaceholder(targetDbName, "<target_db_name>");
  const sourceHost = valueOrPlaceholder(
    migration.metadata_collection?.source_connection?.host,
    "<source_host>",
  );
  const targetHost = valueOrPlaceholder(
    migration.metadata_collection?.target_connection?.host,
    "<target_host>",
  );
  const sourcePort = valueOrPlaceholder(
    migration.metadata_collection?.source_connection?.port,
    "1521",
  );
  const targetPort = valueOrPlaceholder(
    migration.metadata_collection?.target_connection?.port,
    "1521",
  );
  const sourceService = valueOrPlaceholder(
    migration.metadata_collection?.source_connection?.service_name,
    sourceUniqueName,
  );
  const targetService = valueOrPlaceholder(
    migration.metadata_collection?.target_connection?.service_name,
    targetUniqueName,
  );
  const brokerConfigName = `dg_${slugify(sourceUniqueName || "primary")}`;
  return {
    title: "Implementation Runbook",
    description:
      "Use these Data Guard commands as a source-and-target execution runbook for standby creation, synchronization, broker management, and switchover.",
    commands: [
      {
        title: "Source primary prechecks and logging",
        description:
          "Run on the source primary first to confirm role, archivelog mode, force logging, and standby redo log readiness.",
        language: "bash",
        filename: `${requestSlug}_dataguard_source_prechecks.sh`,
        content: [
          "sqlplus -L \"${SRC_CONNECT_STRING}\" <<'SQL'",
          "set lines 220 pages 200",
          "select name, db_unique_name, database_role, open_mode, log_mode, force_logging from v$database;",
          "select instance_name, host_name, version from v$instance;",
          "select thread#, count(*) as standby_redo_logs from v$standby_log group by thread# order by thread#;",
          "archive log list",
          "alter database force logging;",
          "alter database flashback on;",
          "alter system set standby_file_management='AUTO' scope=both;",
          "show parameter db_unique_name",
          "show parameter log_archive_config",
          "show parameter log_archive_dest_1",
          "show parameter log_archive_dest_2",
          "SQL",
        ].join("\n"),
      },
      {
        title: "Source network and broker parameter setup",
        description:
          "Run on the source host to validate connectivity to the future standby service and to stage broker-related settings.",
        language: "bash",
        filename: `${requestSlug}_dataguard_source_network.sh`,
        content: [
          `tnsping //${targetHost}:${targetPort}/${targetService}`,
          "",
          "sqlplus -L \"${SRC_CONNECT_STRING}\" <<'SQL'",
          `alter system set log_archive_config='DG_CONFIG=(${sourceUniqueName},${targetUniqueName})' scope=both;`,
          `alter system set log_archive_dest_2='service=${targetService} async valid_for=(online_logfiles,primary_role) db_unique_name=${targetUniqueName}' scope=both;`,
          "alter system set dg_broker_start=true scope=both;",
          "SQL",
        ].join("\n"),
      },
      {
        title: "Target standby host preparation",
        description:
          `Run on the target host ${targetHost} to prepare directories, password file, listener connectivity, and minimal init parameters before duplicate.`,
        language: "bash",
        filename: `${requestSlug}_dataguard_target_prep.sh`,
        content: [
          `ssh oracle@${targetHost}`,
          `mkdir -p /u01/app/oracle/admin/${targetUniqueName}/adump`,
          `mkdir -p /u02/oradata/${targetUniqueName}`,
          `mkdir -p /u03/fra/${targetUniqueName}`,
          `orapwd file=$ORACLE_HOME/dbs/orapw${targetUniqueName} password='<sys_password>' force=y format=12`,
          `cat > /tmp/init${targetUniqueName}.ora <<'EOF'`,
          `db_name='${sourceUniqueName}'`,
          `db_unique_name='${targetUniqueName}'`,
          `enable_pluggable_database=true`,
          `db_create_file_dest='/u02/oradata'`,
          `db_recovery_file_dest='/u03/fra'`,
          `db_recovery_file_dest_size=200G`,
          `audit_file_dest='/u01/app/oracle/admin/${targetUniqueName}/adump'`,
          "EOF",
          `lsnrctl status`,
          `tnsping //${sourceHost}:${sourcePort}/${sourceService}`,
        ].join("\n"),
      },
      {
        title: "RMAN active duplicate for physical standby",
        description:
          "Use this from the target host to create the standby database directly from the source primary using active duplicate.",
        language: "bash",
        filename: `${requestSlug}_dataguard_duplicate.rman`,
        content: [
          "rman target \"sys/${SRC_DB_PASS}@//${SRC_DB_HOST}:${SRC_DB_PORT}/${SRC_DB_SERVICE}\" auxiliary \"sys/${TGT_DB_PASS}@//${TGT_DB_HOST}:${TGT_DB_PORT}/${TGT_DB_SERVICE}\" <<'RMAN'",
          `duplicate target database for standby from active database`,
          "  dorecover",
          "  spfile",
          `    set db_unique_name='${targetUniqueName}'`,
          `    set log_archive_config='DG_CONFIG=(${sourceUniqueName},${targetUniqueName})'`,
          `    set log_archive_dest_2='service=${sourceService} async valid_for=(online_logfiles,primary_role) db_unique_name=${sourceUniqueName}'`,
          "  nofilenamecheck;",
          "exit",
          "RMAN",
        ].join("\n"),
      },
      {
        title: "Target standby recovery start and validation",
        description:
          "Run on the target standby after duplicate to open mounted standby recovery and verify apply status.",
        language: "bash",
        filename: `${requestSlug}_dataguard_target_recovery.sh`,
        content: [
          "sqlplus -L \"${TGT_CONNECT_STRING}\" <<'SQL'",
          "set lines 220 pages 200",
          "select name, db_unique_name, database_role, open_mode, switchover_status from v$database;",
          "alter database recover managed standby database using current logfile disconnect from session;",
          "select process, status, thread#, sequence# from v$managed_standby order by process;",
          "select name, value, unit from v$dataguard_stats where name in ('transport lag','apply lag','apply finish time');",
          "SQL",
        ].join("\n"),
      },
      {
        title: "Broker configuration and validation",
        description:
          `Create broker configuration for primary ${sourceUniqueName} and standby ${targetUniqueName}, then validate both databases and the full configuration.`,
        language: "text",
        filename: `${requestSlug}_dataguard_broker_setup.txt`,
        content: [
          "dgmgrl sys/${SRC_DB_PASS}@//${SRC_DB_HOST}:${SRC_DB_PORT}/${SRC_DB_SERVICE}",
          `create configuration '${brokerConfigName}' as primary database is '${sourceUniqueName}' connect identifier is '${sourceService}';`,
          `add database '${targetUniqueName}' as connect identifier is '${targetService}' maintained as physical;`,
          "enable configuration;",
          `validate database '${sourceUniqueName}';`,
          `validate database '${targetUniqueName}';`,
          "show configuration verbose;",
          "show database verbose '${sourceUniqueName}';",
          "show database verbose '${targetUniqueName}';",
        ].join("\n"),
      },
      {
        title: "Switchover execution and post-cutover checks",
        description:
          "Run only after lag is zero, application readiness is approved, and rollback criteria are documented.",
        language: "text",
        filename: `${requestSlug}_dataguard_switchover.txt`,
        content: [
          "dgmgrl sys/${SRC_DB_PASS}@//${SRC_DB_HOST}:${SRC_DB_PORT}/${SRC_DB_SERVICE}",
          "show configuration;",
          `switchover to '${targetUniqueName}';`,
          "show configuration;",
          "",
          "sqlplus -L \"${TGT_CONNECT_STRING}\" <<'SQL'",
          "set lines 220 pages 200",
          "select name, db_unique_name, database_role, open_mode, switchover_status from v$database;",
          "select process, status, thread#, sequence# from v$managed_standby order by process;",
          "SQL",
        ].join("\n"),
      },
    ],
  };
}

function buildMethodSection(
  migration: MigrationRecord,
  recommendation: RecommendationResponse,
  requestSlug: string,
  sourceDbName: string,
  targetDbName: string,
): ImplementationRunbookSection {
  switch (getApproachKey(recommendation.recommended_approach)) {
    case "DATAPUMP":
      return buildDataPumpSection(migration, requestSlug);
    case "RMAN":
      return buildRmanSection(migration, sourceDbName, targetDbName);
    case "GOLDENGATE":
      return buildGoldenGateSection(sourceDbName, targetDbName);
    case "ZDM":
      return buildZdmSection(sourceDbName, targetDbName);
    case "DATA_GUARD":
      return buildDataGuardSection(migration, sourceDbName, targetDbName);
    default:
      return {
        title: "Implementation Runbook",
        description:
          "Use this generic execution block when the selected method is outside the built-in command templates.",
        commands: [
          {
            title: "Execution placeholder",
            description:
              `Execute the approved ${formatApproach(recommendation.recommended_approach)} method with the validated source and target connection details shown above.`,
            language: "text",
            filename: `${requestSlug}_implementation_notes.txt`,
            content: [
              "1. Confirm source and target login using the profile commands above.",
              "2. Execute the approved migration runbook in the change window.",
              "3. Capture logs, timings, row counts, invalid objects, and application validation evidence.",
            ].join("\n"),
          },
        ],
      };
  }
}

function getDocuments(
  migration: MigrationRecord,
  recommendation: RecommendationResponse,
  requestSlug: string,
): ImplementationRunbookDocument[] {
  const docs: ImplementationRunbookDocument[] = [
    {
      title: "Decision record",
      filename: `${requestSlug}_decision_record.md`,
      description:
        `Captures the approved ${formatApproach(recommendation.recommended_approach)} path, downtime window, fallback path, and owner sign-offs.`,
    },
    {
      title: "Source discovery archive",
      filename: `${requestSlug}_source_metadata_collection_report.html`,
      description:
        "Stores the source discovery output imported into the app so the same assessment evidence can be reused later.",
    },
    {
      title: "Source precheck SQL",
      filename: `${requestSlug}_source_prechecks.sql`,
      description:
        "Contains source validation SQL for version, open mode, invalid objects, and feature usage before execution.",
    },
    {
      title: "Target readiness SQL",
      filename: `${requestSlug}_target_readiness.sql`,
      description:
        "Contains target validation SQL for role, version, character set, and open mode before cutover.",
    },
    {
      title: "Cutover validation SQL",
      filename: `${requestSlug}_post_cutover_validation.sql`,
      description:
        "Contains post-migration checks for invalid objects, role, open mode, and smoke-test evidence capture.",
    },
  ];

  switch (getApproachKey(recommendation.recommended_approach)) {
    case "DATAPUMP":
      docs.push({
        title: "Data Pump parameter bundle",
        filename: `${requestSlug}_datapump_bundle.zip`,
        description:
          "Package the export and import parameter files, directory SQL, and transfer checklist together for CAB execution.",
      });
      break;
    case "RMAN":
      docs.push({
        title: "RMAN duplicate script",
        filename: `${requestSlug}_rman_duplicate.rman`,
        description:
          "Stores the duplicate or restore command file aligned to the exact source and target service names.",
      });
      break;
    case "GOLDENGATE":
      docs.push({
        title: "GoldenGate Microservices pack",
        filename: `${requestSlug}_goldengate_microservices_pack.txt`,
        description:
          "Stores Microservices credential aliases, REST setup scripts, Extract and Replicat parameter files, and lag checkpoints.",
      });
      break;
    case "ZDM":
      docs.push({
        title: "ZDM response file",
        filename: `${requestSlug}_zdm_migration.rsp`,
        description:
          "Stores the ZDM response file populated with the collected host, service, and database names.",
      });
      break;
    case "DATA_GUARD":
      docs.push({
        title: "Data Guard broker script",
        filename: `${requestSlug}_broker_commands.txt`,
        description:
          "Stores broker configuration, validation, and switchover commands matched to the source and target DB names.",
      });
      break;
  }

  if (migration.business.fallback_required) {
    docs.push({
      title: "Fallback plan",
      filename: `${requestSlug}_fallback_plan.md`,
      description:
        "Defines the rollback checkpoint, backup reference, recovery owner, and downtime exit criteria.",
      });
  }

  return docs;
}

export function buildImplementationPlan(
  migration: MigrationRecord,
  recommendation: RecommendationResponse,
): ImplementationPlan {
  const warnings = getValidationWarnings(migration, recommendation);
  const prerequisites = Array.from(
    new Set([
      ...recommendation.prerequisites,
      ...(migration.migration_validation?.blockers ?? []),
    ]),
  );
  const requestSlug = slugify(migration.request_id || recommendation.request_id || "migration");
  const { source: sourceConnection, target: targetConnection } = getConnections(
    migration.metadata_collection,
  );
  const sourceDbName = valueOrPlaceholder(
    pick(migration.source_metadata?.db_name, sourceConnection?.service_name),
    "<source_db_name>",
  );
  const targetDbName = valueOrPlaceholder(
    pick(
      migration.target_metadata?.db_unique_name,
      migration.target_metadata?.db_name,
      targetConnection?.service_name,
    ),
    "<target_db_name>",
  );
  const size = migration.source.database_size_gb ?? migration.source_metadata?.database_size_gb ?? 0;
  const downtime = migration.business.downtime_window_minutes;
  const scope = migration.scope.migration_scope.replace(/_/g, " ").toLowerCase();

  const sections: ImplementationRunbookSection[] = [
    {
      title: "Connection Profiles",
      description:
        "Start by exporting source and target connection variables. These values are derived from the captured intake details so the same profile can be reused across SQL*Plus, Data Pump, RMAN, and validation scripts.",
      commands: [
        buildConnectionProfileCommand(
          "SRC",
          "Source",
          sourceConnection,
          sourceDbName,
        ),
        buildConnectivityTestCommand("SRC", "Source"),
        buildConnectionProfileCommand(
          "TGT",
          "Target",
          targetConnection,
          targetDbName,
        ),
        buildConnectivityTestCommand("TGT", "Target"),
      ],
    },
    {
      title: "Discovery And Readiness",
      description:
        "Use the precheck commands below to validate the source inventory, capture the HTML report, and confirm the target is ready before cutover.",
      commands: [
        buildSourceDiscoveryCommand(),
        ...(targetConnection || migration.target_metadata
          ? [buildTargetReadinessSql()]
          : []),
      ],
    },
    buildMethodSection(
      migration,
      recommendation,
      requestSlug,
      sourceDbName,
      targetDbName,
    ),
    {
      title: "Post-Cutover Validation",
      description:
        "Run these checks immediately after the migration step completes so object validity, database role, and smoke-test evidence are recorded in the same change window.",
      commands: [buildPostCutoverValidationSql(migration)],
    },
  ];

  return {
    overview:
      `Implementation runbook for ${formatApproach(recommendation.recommended_approach)} ` +
      `covering a ${scope} migration, approximately ${size || "unknown"} GB source size, ` +
      `and a ${downtime} minute downtime window.`,
    assumptions: [
      `Source database: ${sourceDbName}.`,
      `Target database: ${targetDbName}.`,
      `Source version: ${migration.source_metadata?.oracle_version ?? migration.source.oracle_version ?? "not provided"}.`,
      `Target version: ${migration.target_metadata?.oracle_version ?? migration.target.oracle_version ?? "not provided"}.`,
      `Source platform: ${migration.source_metadata?.platform ?? migration.source.platform ?? "not provided"}.`,
      `Target platform: ${migration.target_metadata?.platform ?? migration.target.platform ?? "not provided"}.`,
      `Source service: ${sourceConnection?.service_name ?? sourceDbName}.`,
      `Target service: ${targetConnection?.service_name ?? targetDbName}.`,
    ],
    prerequisites,
    warnings,
    documents: getDocuments(migration, recommendation, requestSlug),
    sections,
  };
}

export function buildImplementationPlanFromReport(
  report: RecommendationReport,
): ImplementationPlan {
  return buildImplementationPlan(report.migration, report.recommendation);
}
