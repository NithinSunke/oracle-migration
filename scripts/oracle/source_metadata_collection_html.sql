SET ECHO OFF
SET FEEDBACK ON
SET HEADING ON
SET LINESIZE 240
SET PAGESIZE 500
SET LONG 200000
SET LONGCHUNKSIZE 200000
SET TRIMSPOOL ON
SET TAB OFF
SET VERIFY OFF
SET MARKUP HTML ON SPOOL ON ENTMAP OFF

SPOOL source_metadata_collection_report.html

PROMPT <html>
PROMPT <head><title>Oracle Migration App - Source Metadata SQL Report</title></head>
PROMPT <body>
PROMPT <h1>Oracle Migration App - Source Metadata SQL Report</h1>
PROMPT <p>This script documents and executes the source-side SQL used by the app metadata collector. Some sections are CDB-specific and some are NON-CDB variants. The application chooses the correct variant automatically based on <code>v$database.cdb</code>.</p>

PROMPT <h2>Execution Context</h2>
SELECT name AS db_name, cdb, db_unique_name, platform_name, log_mode
FROM v$database;

SELECT instance_name, host_name, version, startup_time
FROM v$instance;

PROMPT <h2>Core Source Metadata Queries</h2>

PROMPT <h3>DB Name</h3>
SELECT name FROM v$database;

PROMPT <h3>Host Name</h3>
SELECT host_name FROM v$instance;

PROMPT <h3>Edition Banner</h3>
SELECT banner_full
FROM v$version
WHERE banner_full LIKE 'Oracle Database %'
FETCH FIRST 1 ROWS ONLY;

PROMPT <h3>Endianness</h3>
SELECT endian_format
FROM v$transportable_platform
WHERE platform_name = (SELECT platform_name FROM v$database);

PROMPT <h3>Oracle Version</h3>
SELECT version FROM v$instance;

PROMPT <h3>Deployment Type</h3>
SELECT CASE WHEN cdb = 'YES' THEN 'CDB_PDB' ELSE 'NON_CDB' END AS deployment_type
FROM v$database;

PROMPT <h3>Database Size - CDB Variant</h3>
SELECT ROUND(SUM(bytes) / POWER(1024, 3), 2) AS database_size_gb
FROM (
    SELECT bytes FROM cdb_data_files
    UNION ALL
    SELECT bytes FROM cdb_temp_files
);

PROMPT <h3>Database Size - NON-CDB Variant</h3>
SELECT ROUND(SUM(bytes) / POWER(1024, 3), 2) AS database_size_gb
FROM (
    SELECT bytes FROM dba_data_files
    UNION ALL
    SELECT bytes FROM dba_temp_files
);

PROMPT <h3>Archive Log Enabled</h3>
SELECT CASE WHEN log_mode = 'ARCHIVELOG' THEN 1 ELSE 0 END AS archivelog_enabled
FROM v$database;

PROMPT <h3>Platform</h3>
SELECT platform_name FROM v$database;

PROMPT <h3>RAC Enabled</h3>
SELECT CASE WHEN COUNT(*) > 1 THEN 1 ELSE 0 END AS rac_enabled
FROM gv$instance;

PROMPT <h3>TDE Enabled</h3>
SELECT CASE
           WHEN UPPER(status) IN ('OPEN', 'OPEN_NO_MASTER_KEY', 'AUTOLOGIN') THEN 1
           ELSE 0
       END AS tde_enabled
FROM v$encryption_wallet
FETCH FIRST 1 ROWS ONLY;

PROMPT <h3>NLS Character Set</h3>
SELECT value
FROM nls_database_parameters
WHERE parameter = 'NLS_CHARACTERSET';

PROMPT <h3>NLS NCHAR Character Set</h3>
SELECT value
FROM nls_database_parameters
WHERE parameter = 'NLS_NCHAR_CHARACTERSET';

PROMPT <h2>Inventory Summary Queries</h2>

PROMPT <h3>Inventory Summary - CDB Variant</h3>
SELECT
    COUNT(DISTINCT owner) AS schema_count,
    COUNT(*) AS total_objects,
    SUM(CASE WHEN object_type = 'TABLE' THEN 1 ELSE 0 END) AS total_tables,
    SUM(CASE WHEN object_type = 'INDEX' THEN 1 ELSE 0 END) AS total_indexes,
    SUM(CASE WHEN object_type = 'VIEW' THEN 1 ELSE 0 END) AS total_views,
    SUM(CASE WHEN object_type = 'MATERIALIZED VIEW' THEN 1 ELSE 0 END) AS total_materialized_views,
    SUM(CASE WHEN object_type = 'SEQUENCE' THEN 1 ELSE 0 END) AS total_sequences,
    SUM(CASE WHEN object_type = 'PROCEDURE' THEN 1 ELSE 0 END) AS total_procedures,
    SUM(CASE WHEN object_type = 'FUNCTION' THEN 1 ELSE 0 END) AS total_functions,
    SUM(CASE WHEN object_type = 'PACKAGE' THEN 1 ELSE 0 END) AS total_packages,
    SUM(CASE WHEN object_type = 'TRIGGER' THEN 1 ELSE 0 END) AS total_triggers,
    SUM(CASE WHEN status <> 'VALID' THEN 1 ELSE 0 END) AS invalid_object_count
FROM cdb_objects
WHERE owner <> 'PUBLIC'
  AND EXISTS (
      SELECT 1
      FROM cdb_users u
      WHERE u.con_id = con_id
        AND u.username = owner
        AND u.oracle_maintained = 'N'
  )
  AND con_id <> 2;

PROMPT <h3>Inventory Summary - NON-CDB Variant</h3>
SELECT
    COUNT(DISTINCT owner) AS schema_count,
    COUNT(*) AS total_objects,
    SUM(CASE WHEN object_type = 'TABLE' THEN 1 ELSE 0 END) AS total_tables,
    SUM(CASE WHEN object_type = 'INDEX' THEN 1 ELSE 0 END) AS total_indexes,
    SUM(CASE WHEN object_type = 'VIEW' THEN 1 ELSE 0 END) AS total_views,
    SUM(CASE WHEN object_type = 'MATERIALIZED VIEW' THEN 1 ELSE 0 END) AS total_materialized_views,
    SUM(CASE WHEN object_type = 'SEQUENCE' THEN 1 ELSE 0 END) AS total_sequences,
    SUM(CASE WHEN object_type = 'PROCEDURE' THEN 1 ELSE 0 END) AS total_procedures,
    SUM(CASE WHEN object_type = 'FUNCTION' THEN 1 ELSE 0 END) AS total_functions,
    SUM(CASE WHEN object_type = 'PACKAGE' THEN 1 ELSE 0 END) AS total_packages,
    SUM(CASE WHEN object_type = 'TRIGGER' THEN 1 ELSE 0 END) AS total_triggers,
    SUM(CASE WHEN status <> 'VALID' THEN 1 ELSE 0 END) AS invalid_object_count
FROM dba_objects
WHERE owner <> 'PUBLIC'
  AND EXISTS (
      SELECT 1
      FROM dba_users u
      WHERE u.username = owner
        AND u.oracle_maintained = 'N'
  );

PROMPT <h2>PDB And User Inventory Queries</h2>

PROMPT <h3>PDB Services</h3>
SELECT pdb, name
FROM cdb_services
WHERE pdb IS NOT NULL
ORDER BY pdb, name;

PROMPT <h3>PDB Inventory</h3>
SELECT
    con_id,
    name,
    open_mode,
    open_time,
    ROUND(total_size / POWER(1024, 3), 2) AS total_size_gb
FROM v$pdbs
WHERE name <> 'PDB$SEED'
ORDER BY con_id;

PROMPT <h3>CDB Users</h3>
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
ORDER BY u.con_id, u.username;

PROMPT <h3>CDB Tablespaces</h3>
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
ORDER BY t.con_id, t.tablespace_name;

PROMPT <h3>Invalid Objects By Schema - CDB</h3>
SELECT
    vc.name AS container_name,
    o.con_id,
    o.owner,
    COUNT(*) AS invalid_object_count
FROM cdb_objects o
JOIN v$containers vc ON vc.con_id = o.con_id
WHERE vc.name <> 'PDB$SEED'
  AND o.status <> 'VALID'
  AND o.owner <> 'PUBLIC'
  AND EXISTS (
      SELECT 1
      FROM cdb_users u
      WHERE u.con_id = o.con_id
        AND u.username = o.owner
        AND u.oracle_maintained = 'N'
  )
GROUP BY vc.name, o.con_id, o.owner
ORDER BY COUNT(*) DESC, vc.name, o.owner;

PROMPT <h3>Schema Inventory - CDB</h3>
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
  AND o.owner <> 'PUBLIC'
  AND EXISTS (
      SELECT 1
      FROM cdb_users u
      WHERE u.con_id = o.con_id
        AND u.username = o.owner
        AND u.oracle_maintained = 'N'
  )
GROUP BY vc.name, o.con_id, o.owner
ORDER BY COUNT(*) DESC, vc.name, o.owner;

PROMPT <h2>Discovery Section Queries</h2>

PROMPT <h3>DB:Database Custom Schema Size - CDB Variant</h3>
SELECT owner, TO_CHAR(ROUND(SUM(bytes) / POWER(1024, 3), 8)) AS size_gb
FROM cdb_segments
WHERE owner <> 'PUBLIC'
  AND EXISTS (
      SELECT 1
      FROM cdb_users u
      WHERE u.con_id = con_id
        AND u.username = owner
        AND u.oracle_maintained = 'N'
  )
GROUP BY owner
ORDER BY SUM(bytes), owner;

PROMPT <h3>DB:Database Custom Schema Size - NON-CDB Variant</h3>
SELECT owner, TO_CHAR(ROUND(SUM(bytes) / POWER(1024, 3), 8)) AS size_gb
FROM dba_segments
WHERE owner <> 'PUBLIC'
  AND EXISTS (
      SELECT 1
      FROM dba_users u
      WHERE u.username = owner
        AND u.oracle_maintained = 'N'
  )
GROUP BY owner
ORDER BY SUM(bytes), owner;

PROMPT <h3>DB:Database Encrypted - Database Wallet Details from CDB/PDB - CDB Variant</h3>
SELECT
    vc.name,
    CASE WHEN vc.con_id = 1 THEN 'CDB-ROOT' ELSE 'PDB-' || TO_CHAR(vc.con_id) END AS type_id,
    ew.wrl_type,
    ew.wrl_parameter,
    ew.status,
    ew.wallet_type,
    ew.wallet_order,
    ew.fully_backed_up
FROM v$encryption_wallet ew
JOIN v$containers vc ON vc.con_id = ew.con_id
WHERE vc.name <> 'PDB$SEED'
ORDER BY ew.con_id;

PROMPT <h3>DB:Database Global Names value details</h3>
SELECT 'Show parameter global_names' AS source, value
FROM v$parameter
WHERE name = 'global_names'
UNION ALL
SELECT 'DBTIMEZONE', dbtimezone FROM dual
UNION ALL
SELECT 'GLOBAL_NAME', global_name FROM global_name;

PROMPT <h3>DB:Database Synonyms for Remote Objects - CDB Variant</h3>
SELECT
    vc.name,
    CASE WHEN vc.con_id = 1 THEN 'CDB-ROOT' ELSE 'PDB-' || TO_CHAR(s.con_id) END AS type_id,
    s.owner,
    s.synonym_name,
    s.table_owner,
    s.table_name,
    s.db_link
FROM cdb_synonyms s
JOIN v$containers vc ON vc.con_id = s.con_id
WHERE s.db_link IS NOT NULL
ORDER BY vc.name, s.owner, s.synonym_name;

PROMPT <h3>DB:LOB Segment count group by schemas - CDB Variant</h3>
SELECT vc.name, s.owner, TO_CHAR(COUNT(*)) AS lob_segment_count
FROM cdb_segments s
JOIN v$containers vc ON vc.con_id = s.con_id
WHERE s.segment_type LIKE 'LOB%'
  AND s.owner <> 'PUBLIC'
  AND EXISTS (
      SELECT 1
      FROM cdb_users u
      WHERE u.con_id = s.con_id
        AND u.username = s.owner
        AND u.oracle_maintained = 'N'
  )
GROUP BY vc.name, s.owner
ORDER BY COUNT(*) DESC, vc.name, s.owner;

PROMPT <h3>DB:Additional Database Details</h3>
SELECT
    TO_CHAR(dbid) AS dbid,
    name,
    TO_CHAR(created, 'YYYY-MM-DD HH24:MI:SS') AS created,
    TO_CHAR(startup_time, 'YYYY-MM-DD HH24:MI:SS') AS startup_time,
    logins,
    log_mode,
    open_mode,
    remote_archive,
    database_role,
    platform_id,
    platform_name,
    db_unique_name
FROM v$database
CROSS JOIN v$instance;

PROMPT <h3>DB:Auditing Check</h3>
SELECT name, type, NVL(display_value, value) AS value
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
ORDER BY name;

PROMPT <h3>DB:CPU and Memory Details</h3>
SELECT stat_name, value,
       CASE
           WHEN stat_name = 'NUM_CPUS' THEN 'Number of active CPUs'
           WHEN stat_name = 'NUM_CPU_CORES' THEN 'Number of CPU cores'
           WHEN stat_name = 'PHYSICAL_MEMORY_BYTES' THEN 'Physical memory size in bytes'
           ELSE 'OS statistic'
       END AS comments
FROM v$osstat
WHERE stat_name IN ('NUM_CPUS', 'NUM_CPU_CORES', 'PHYSICAL_MEMORY_BYTES')
ORDER BY stat_name;

PROMPT <h3>DB:Cluster Check</h3>
SELECT value FROM v$parameter WHERE name = 'cluster_database';
SELECT COUNT(*) AS instance_count FROM gv$instance;

PROMPT <h3>DB:DB Link Info from CDB/PDB - CDB Variant</h3>
SELECT
    vc.name,
    CASE WHEN vc.con_id = 1 THEN 'CDB-ROOT' ELSE 'PDB-' || TO_CHAR(l.con_id) END AS type_id,
    l.owner,
    l.db_link,
    l.username,
    l.host,
    TO_CHAR(l.created, 'YYYY-MM-DD HH24:MI:SS') AS created
FROM cdb_db_links l
JOIN v$containers vc ON vc.con_id = l.con_id
ORDER BY vc.name, l.owner, l.db_link;

PROMPT <h3>DB:Database ASM Disk Details from CDB/PDB</h3>
SELECT TO_CHAR(group_number) AS group_number, name, state, type, TO_CHAR(total_mb) AS total_mb, TO_CHAR(free_mb) AS free_mb
FROM v$asm_diskgroup
ORDER BY name;

PROMPT <h3>DB:Database Components from CDB/PDB - CDB Variant</h3>
SELECT vc.name, r.comp_id, r.comp_name, r.version, r.status
FROM cdb_registry r
JOIN v$containers vc ON vc.con_id = r.con_id
WHERE vc.name <> 'PDB$SEED'
ORDER BY vc.name, r.comp_name;

PROMPT <h3>DB:Database Feature Usage from CDB/PDB</h3>
SELECT name, TO_CHAR(detected_usages) AS detected_usages, currently_used, TO_CHAR(last_usage_date, 'YYYY-MM-DD') AS last_usage_date
FROM dba_feature_usage_statistics
WHERE detected_usages > 0 OR currently_used = 'TRUE'
ORDER BY name;

PROMPT <h3>DB:Database Home</h3>
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
ORDER BY 1;

PROMPT <h3>DB:Database MV_Views_Info from CDB/PDB - CDB Variant</h3>
SELECT vc.name, m.owner, m.mview_name, m.refresh_mode, m.refresh_method, m.fast_refreshable
FROM cdb_mviews m
JOIN v$containers vc ON vc.con_id = m.con_id
ORDER BY vc.name, m.owner, m.mview_name;

PROMPT <h3>DB:Database Options and Features</h3>
SELECT parameter, value
FROM v$option
ORDER BY parameter;

PROMPT <h3>DB:Database Parameters</h3>
SELECT name, NVL(display_value, value) AS value, isdefault, ismodified
FROM v$parameter
ORDER BY name;

PROMPT <h3>DB:Database Properties</h3>
SELECT property_name, property_value, description
FROM database_properties
ORDER BY property_name;

PROMPT <h3>DB:Database Size - CDB Report Section</h3>
SELECT 'DATAFILES' AS component, TO_CHAR(ROUND(SUM(bytes) / POWER(1024, 3), 2)) AS size_gb FROM cdb_data_files
UNION ALL
SELECT 'TEMPFILES', TO_CHAR(ROUND(SUM(bytes) / POWER(1024, 3), 2)) FROM cdb_temp_files
UNION ALL
SELECT 'REDOLOGS', TO_CHAR(ROUND(SUM(bytes) / POWER(1024, 3), 2)) FROM v$log;

PROMPT <h3>DB:Database Standby availability</h3>
SELECT database_role, switchover_status, guard_status, force_logging
FROM v$database;

PROMPT <h3>DB:Database XML_Table_Columns from CDB/PDB - CDB Variant</h3>
SELECT vc.name, c.owner, c.table_name, c.column_name, c.data_type
FROM cdb_tab_columns c
JOIN v$containers vc ON vc.con_id = c.con_id
WHERE c.data_type = 'XMLTYPE'
  AND c.owner <> 'PUBLIC'
  AND EXISTS (
      SELECT 1
      FROM cdb_users u
      WHERE u.con_id = c.con_id
        AND u.username = c.owner
        AND u.oracle_maintained = 'N'
  )
ORDER BY vc.name, c.owner, c.table_name, c.column_name;

PROMPT <h3>DB:Database XML_Table_Info from CDB/PDB - CDB Variant</h3>
SELECT vc.name, x.owner, x.table_name, x.xmlschema, x.storage_type
FROM cdb_xml_tables x
JOIN v$containers vc ON vc.con_id = x.con_id
ORDER BY vc.name, x.owner, x.table_name;

PROMPT <h3>DB:Datafiles - Tempfiles from CDB/PDB - CDB Variant</h3>
SELECT vc.name, 'DATAFILE' AS type_name, d.tablespace_name, d.file_name, TO_CHAR(ROUND(d.bytes / POWER(1024, 3), 2)) AS bytes_gb
FROM cdb_data_files d
JOIN v$containers vc ON vc.con_id = d.con_id
UNION ALL
SELECT vc.name, 'TEMPFILE', t.tablespace_name, t.file_name, TO_CHAR(ROUND(t.bytes / POWER(1024, 3), 2))
FROM cdb_temp_files t
JOIN v$containers vc ON vc.con_id = t.con_id
ORDER BY 1, 2, 3, 4;

PROMPT <h3>DB:Directories Information from CDB/PDB - CDB Variant</h3>
SELECT vc.name, d.owner, d.directory_name, d.directory_path
FROM cdb_directories d
JOIN v$containers vc ON vc.con_id = d.con_id
ORDER BY vc.name, d.owner, d.directory_name;

PROMPT <h3>DB:External Tables from CDB/PDB - CDB Variant</h3>
SELECT vc.name, e.owner, e.table_name, e.type_name, e.default_directory_name
FROM cdb_external_tables e
JOIN v$containers vc ON vc.con_id = e.con_id
ORDER BY vc.name, e.owner, e.table_name;

PROMPT <h3>DB:Index Organised Tables from CDB/PDB - CDB Variant</h3>
SELECT vc.name, t.owner, t.table_name, t.iot_type
FROM cdb_tables t
JOIN v$containers vc ON vc.con_id = t.con_id
WHERE t.iot_type IS NOT NULL
  AND t.owner <> 'PUBLIC'
  AND EXISTS (
      SELECT 1
      FROM cdb_users u
      WHERE u.con_id = t.con_id
        AND u.username = t.owner
        AND u.oracle_maintained = 'N'
  )
ORDER BY vc.name, t.owner, t.table_name;

PROMPT <h3>DB:Invalid Objects from CDB/PDB - CDB Variant</h3>
SELECT
    vc.name,
    CASE WHEN vc.con_id = 1 THEN 'CDB-ROOT' ELSE 'PDB-' || TO_CHAR(o.con_id) END AS type_id,
    o.owner || '.' || o.object_name AS object_name,
    o.object_type,
    o.status
FROM cdb_objects o
JOIN v$containers vc ON vc.con_id = o.con_id
WHERE o.status <> 'VALID'
ORDER BY vc.name, o.owner, o.object_name;

PROMPT <h3>DB:Scheduled Jobs_From_CDB_JOBS (CDB/PDB)</h3>
SELECT vc.name, j.log_user, TO_CHAR(j.job) AS job, j.schema_user, j.broken, j.interval
FROM cdb_jobs j
JOIN v$containers vc ON vc.con_id = j.con_id
ORDER BY vc.name, j.schema_user, j.job;

PROMPT <h3>DB:Scheduled Jobs_From_CDB_SCHEDULER_JOBS (CDB/PDB)</h3>
SELECT vc.name, j.owner, j.job_name, j.enabled, j.state, j.job_style
FROM cdb_scheduler_jobs j
JOIN v$containers vc ON vc.con_id = j.con_id
ORDER BY vc.name, j.owner, j.job_name;

PROMPT <h3>DB:Software Version and PSU Info_1</h3>
SELECT banner FROM v$version ORDER BY banner;

PROMPT <h3>DB:Software Version and PSU Info_2 from CDB/PDB</h3>
SELECT
    TO_CHAR(action_time, 'YYYY-MM-DD HH24:MI:SS') AS action_time,
    action,
    status,
    version,
    description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;

PROMPT <h3>DB:Software Version and PSU Info_3 from CDB/PDB</h3>
SELECT product, version, status
FROM product_component_version
ORDER BY product;

PROMPT <h3>DB:VPD:DB Users with Exempt Access Policy from CDB/PDB - CDB Variant</h3>
SELECT vc.name, p.grantee, p.privilege
FROM cdb_sys_privs p
JOIN v$containers vc ON vc.con_id = p.con_id
WHERE p.privilege = 'EXEMPT ACCESS POLICY'
ORDER BY vc.name, p.grantee;

PROMPT <h3>DB:XML_Types from CDB/PDB - CDB Variant</h3>
SELECT vc.name, c.owner, c.table_name, c.column_name
FROM cdb_tab_columns c
JOIN v$containers vc ON vc.con_id = c.con_id
WHERE c.data_type = 'XMLTYPE'
ORDER BY vc.name, c.owner, c.table_name, c.column_name;

PROMPT <h3>OGG:All Unsupported from CDB/PDB - CDB Variant</h3>
SELECT vc.name, c.owner, c.table_name, c.column_name, c.data_type
FROM cdb_tab_columns c
JOIN v$containers vc ON vc.con_id = c.con_id
WHERE c.data_type IN ('BFILE', 'LONG', 'LONG RAW', 'UROWID', 'ANYDATA')
ORDER BY vc.name, c.owner, c.table_name, c.column_name;

PROMPT <h3>OGG:Archivelog Volume per Day</h3>
SELECT
    TO_CHAR(TRUNC(first_time), 'YYYY-MM-DD') AS day_name,
    TO_CHAR(COUNT(*)) AS archive_count,
    TO_CHAR(ROUND(SUM(blocks * block_size) / POWER(1024, 3), 2)) AS archive_gb
FROM v$archived_log
WHERE first_time >= TRUNC(SYSDATE) - 7
GROUP BY TRUNC(first_time)
ORDER BY TRUNC(first_time) DESC;

PROMPT <h3>Compressed Tables and Table Partitions from CDB/PDB - CDB Variant</h3>
SELECT vc.name, t.owner, t.table_name, 'TABLE' AS object_type, t.compression
FROM cdb_tables t
JOIN v$containers vc ON vc.con_id = t.con_id
WHERE t.compression = 'ENABLED'
UNION ALL
SELECT vc.name, p.table_owner, p.table_name || ':' || p.partition_name, 'TABLE PARTITION', p.compression
FROM cdb_tab_partitions p
JOIN v$containers vc ON vc.con_id = p.con_id
WHERE p.compression = 'ENABLED'
ORDER BY 1, 2, 3;

PROMPT <h3>Constraints and Tables from CDB/PDB - CDB Variant</h3>
SELECT vc.name, c.owner, c.table_name, c.constraint_name, c.constraint_type, c.status
FROM cdb_constraints c
JOIN v$containers vc ON vc.con_id = c.con_id
WHERE c.constraint_type IN ('P', 'U', 'R', 'C')
  AND c.owner <> 'PUBLIC'
  AND EXISTS (
      SELECT 1
      FROM cdb_users u
      WHERE u.con_id = c.con_id
        AND u.username = c.owner
        AND u.oracle_maintained = 'N'
  )
ORDER BY vc.name, c.owner, c.table_name, c.constraint_name;

PROMPT <h3>Deferred Indexes from CDB/PDB - CDB Variant</h3>
SELECT vc.name, i.owner, i.index_name, i.table_name, i.status, i.visibility
FROM cdb_indexes i
JOIN v$containers vc ON vc.con_id = i.con_id
WHERE (i.status <> 'VALID' OR i.visibility = 'INVISIBLE')
  AND i.owner <> 'PUBLIC'
  AND EXISTS (
      SELECT 1
      FROM cdb_users u
      WHERE u.con_id = i.con_id
        AND u.username = i.owner
        AND u.oracle_maintained = 'N'
  )
ORDER BY vc.name, i.owner, i.index_name;

PROMPT <h3>OGG:Materialized View List from CDB/PDB - CDB Variant</h3>
SELECT vc.name, m.owner, m.mview_name, TO_CHAR(m.query_len) AS query_len
FROM cdb_mviews m
JOIN v$containers vc ON vc.con_id = m.con_id
ORDER BY vc.name, m.owner, m.mview_name;

PROMPT <h3>Redo Log Information</h3>
SELECT
    TO_CHAR(group#) AS group_no,
    TO_CHAR(thread#) AS thread_no,
    TO_CHAR(sequence#) AS sequence_no,
    TO_CHAR(ROUND(bytes / POWER(1024, 2), 2)) AS bytes_mb,
    TO_CHAR(members) AS members,
    archived,
    status
FROM v$log
ORDER BY thread#, group#;

PROMPT <h3>Redo Log Switch History for last week and hourly</h3>
SELECT
    TO_CHAR(first_time, 'YYYY-MM-DD') AS day_name,
    TO_CHAR(first_time, 'HH24') AS hour_name,
    TO_CHAR(COUNT(*)) AS switch_count
FROM v$log_history
WHERE first_time >= TRUNC(SYSDATE) - 7
GROUP BY TO_CHAR(first_time, 'YYYY-MM-DD'), TO_CHAR(first_time, 'HH24')
ORDER BY 1 DESC, 2 DESC;

PROMPT <h3>OGG:Supplemental Logging</h3>
SELECT
    supplemental_log_data_min,
    supplemental_log_data_pk,
    supplemental_log_data_ui,
    supplemental_log_data_fk,
    supplemental_log_data_all,
    force_logging
FROM v$database;

PROMPT <h3>OGG:Tables Without Primary or Unique Key from CDB/PDB - CDB Variant</h3>
SELECT vc.name, t.owner, t.table_name
FROM cdb_tables t
JOIN v$containers vc ON vc.con_id = t.con_id
WHERE t.temporary = 'N'
  AND t.owner <> 'PUBLIC'
  AND EXISTS (
      SELECT 1
      FROM cdb_users u
      WHERE u.con_id = t.con_id
        AND u.username = t.owner
        AND u.oracle_maintained = 'N'
  )
  AND NOT EXISTS (
      SELECT 1
      FROM cdb_constraints c
      WHERE c.con_id = t.con_id
        AND c.owner = t.owner
        AND c.table_name = t.table_name
        AND c.constraint_type IN ('P', 'U')
  )
ORDER BY vc.name, t.owner, t.table_name;

PROMPT <h3>tables with Domain Indexes from CDB/PDB - CDB Variant</h3>
SELECT vc.name, i.owner, i.table_name, i.index_name, i.index_type
FROM cdb_indexes i
JOIN v$containers vc ON vc.con_id = i.con_id
WHERE i.index_type LIKE '%DOMAIN%'
ORDER BY vc.name, i.owner, i.index_name;

PROMPT <h3>OGG:Tables with Nologging setting from CDB/PDB - CDB Variant</h3>
SELECT vc.name, t.owner, t.table_name, t.logging
FROM cdb_tables t
JOIN v$containers vc ON vc.con_id = t.con_id
WHERE t.logging = 'NO'
  AND t.owner <> 'PUBLIC'
  AND EXISTS (
      SELECT 1
      FROM cdb_users u
      WHERE u.con_id = t.con_id
        AND u.username = t.owner
        AND u.oracle_maintained = 'N'
  )
ORDER BY vc.name, t.owner, t.table_name;

PROMPT <h3>OGG:Tables with Triggers from CDB/PDB - CDB Variant</h3>
SELECT vc.name, t.table_owner, t.table_name, TO_CHAR(COUNT(*)) AS trigger_count
FROM cdb_triggers t
JOIN v$containers vc ON vc.con_id = t.con_id
WHERE t.table_owner <> 'PUBLIC'
  AND EXISTS (
      SELECT 1
      FROM cdb_users u
      WHERE u.con_id = t.con_id
        AND u.username = t.table_owner
        AND u.oracle_maintained = 'N'
  )
GROUP BY vc.name, t.table_owner, t.table_name
ORDER BY COUNT(*) DESC, vc.name, t.table_owner, t.table_name;

PROMPT <h3>OGG:Unsupported Datatypes from CDB/PDB - CDB Variant</h3>
SELECT vc.name, c.owner, c.table_name, c.column_name, c.data_type
FROM cdb_tab_columns c
JOIN v$containers vc ON vc.con_id = c.con_id
WHERE c.data_type IN ('BFILE', 'LONG', 'LONG RAW', 'UROWID', 'ANYDATA')
ORDER BY vc.name, c.owner, c.table_name, c.column_name;

PROMPT <h3>Memory Parameters</h3>
SELECT name, NVL(display_value, value) AS value, isdefault, ismodified
FROM v$parameter
WHERE name LIKE '%memory%'
   OR name LIKE 'sga%'
   OR name LIKE 'pga%'
ORDER BY name;

PROMPT <h2>Notes</h2>
PROMPT <p>The application also derives some report sections from already-fetched result sets instead of issuing extra SQL. Examples include:</p>
PROMPT <ul>
PROMPT <li>DB:Database Users from CDB/PDB - built from the CDB users query result.</li>
PROMPT <li>DB:Schema Wise Object Count from CDB/PDB - built from schema inventory rows.</li>
PROMPT <li>DB:Tablespace Details from CDB/PDB - built from the CDB tablespaces query result.</li>
PROMPT <li>Discovery Summary - built in application logic from source metadata and section row counts.</li>
PROMPT </ul>

PROMPT </body>
PROMPT </html>

SPOOL OFF
SET MARKUP HTML OFF
