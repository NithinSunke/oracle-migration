export type MigrationScope = "FULL_DATABASE" | "SCHEMA" | "TABLE" | "SUBSET";

export interface SourceDetails {
  oracle_version: string | null;
  deployment_type: string | null;
  platform: string | null;
  storage_type: string | null;
  database_size_gb: number | null;
  largest_table_gb: number | null;
  daily_change_rate_gb: number | null;
  peak_redo_mb_per_sec: number | null;
  character_set: string | null;
  tde_enabled: boolean;
  rac_enabled: boolean;
  dataguard_enabled: boolean;
  archivelog_enabled: boolean;
}

export interface TargetDetails {
  oracle_version: string | null;
  deployment_type: string | null;
  platform: string | null;
  storage_type: string | null;
  target_is_exadata: boolean;
  same_endian: boolean;
}

export interface ScopeDetails {
  migration_scope: MigrationScope;
  schema_count: number | null;
  schema_names: string[];
  need_schema_remap: boolean;
  need_tablespace_remap: boolean;
  need_reorg: boolean;
  subset_only: boolean;
}

export interface BusinessDetails {
  downtime_window_minutes: number;
  fallback_required: boolean;
  near_zero_downtime_required: boolean;
  regulated_workload: boolean;
}

export interface ConnectivityDetails {
  network_bandwidth_mbps: number | null;
  direct_host_connectivity: boolean;
  shared_storage_available: boolean;
}

export interface FeatureDetails {
  need_version_upgrade: boolean;
  need_cross_platform_move: boolean;
  need_non_cdb_to_pdb_conversion: boolean;
  goldengate_license_available: boolean;
  zdm_supported_target: boolean;
}

export interface OracleConnectionConfig {
  host: string;
  port: number;
  service_name: string;
  username: string;
  password?: string | null;
  password_configured?: boolean;
  mode: "thin" | "thick";
  sysdba: boolean;
  wallet_location: string | null;
}

export interface MetadataCollectionOptions {
  enabled: boolean;
  prefer_collected_values: boolean;
  source_connection: OracleConnectionConfig | null;
  target_connection: OracleConnectionConfig | null;
}

export interface OracleSourceMetadata {
  db_name: string | null;
  host_name: string | null;
  edition: string | null;
  endianness: string | null;
  oracle_version: string | null;
  deployment_type: "NON_CDB" | "CDB_PDB" | null;
  database_size_gb: number | null;
  archivelog_enabled: boolean | null;
  platform: string | null;
  rac_enabled: boolean | null;
  tde_enabled: boolean | null;
  character_set: string | null;
  nchar_character_set: string | null;
  inventory_summary: OracleObjectInventorySummary | null;
  schema_inventory: OracleSchemaInventoryEntry[];
  pdbs: OraclePdbInventoryEntry[];
  database_users: OracleUserInventoryEntry[];
  tablespaces: OracleTablespaceInventoryEntry[];
  invalid_objects_by_schema: OracleInvalidObjectOwnerSummary[];
  discovery_summary: OracleDiscoverySummaryItem[];
  discovery_sections: OracleDiscoverySection[];
  dependency_analysis: OracleSchemaDependencyAnalysis | null;
  collected_at: string;
}

export interface OracleTargetMetadata {
  db_name: string | null;
  db_unique_name: string | null;
  global_name: string | null;
  host_name: string | null;
  edition: string | null;
  endianness: string | null;
  oracle_version: string | null;
  deployment_type: "NON_CDB" | "CDB_PDB" | null;
  database_role: string | null;
  open_mode: string | null;
  database_size_gb: number | null;
  archivelog_enabled: boolean | null;
  platform: string | null;
  rac_enabled: boolean | null;
  tde_enabled: boolean | null;
  character_set: string | null;
  nchar_character_set: string | null;
  collected_at: string;
}

export interface OracleObjectInventorySummary {
  schema_count: number;
  total_objects: number;
  total_tables: number;
  total_indexes: number;
  total_views: number;
  total_materialized_views: number;
  total_sequences: number;
  total_procedures: number;
  total_functions: number;
  total_packages: number;
  total_triggers: number;
  invalid_object_count: number;
}

export interface OracleSchemaInventoryEntry {
  container_name: string;
  container_type: "CDB_ROOT" | "PDB" | "NON_CDB";
  con_id: number;
  owner: string;
  object_count: number;
  table_count: number;
  index_count: number;
  view_count: number;
  materialized_view_count: number;
  sequence_count: number;
  procedure_count: number;
  function_count: number;
  package_count: number;
  trigger_count: number;
  invalid_object_count: number;
}

export interface OraclePdbInventoryEntry {
  name: string;
  con_id: number;
  open_mode: string | null;
  open_time: string | null;
  service_names: string[];
  total_size_gb: number | null;
}

export interface OracleUserInventoryEntry {
  container_name: string;
  container_type: "CDB_ROOT" | "PDB" | "NON_CDB";
  con_id: number;
  username: string;
  user_type: string;
  oracle_maintained: boolean;
  account_status: string | null;
  created: string | null;
  expiry_date: string | null;
  profile: string | null;
  password_versions: string | null;
  default_tablespace: string | null;
  temporary_tablespace: string | null;
}

export interface OracleTablespaceInventoryEntry {
  container_name: string;
  container_type: "CDB_ROOT" | "PDB" | "NON_CDB";
  con_id: number;
  tablespace_name: string;
  contents: string | null;
  extent_management: string | null;
  segment_space_management: string | null;
  bigfile: boolean | null;
  status: string | null;
  block_size: number | null;
  used_mb: number | null;
  free_mb: number | null;
  total_mb: number | null;
  pct_free: number | null;
  max_size_mb: number | null;
  encrypted: boolean | null;
}

export interface OracleInvalidObjectOwnerSummary {
  container_name: string;
  container_type: "CDB_ROOT" | "PDB" | "NON_CDB";
  con_id: number;
  owner: string;
  invalid_object_count: number;
}

export interface OracleDiscoverySummaryItem {
  key_point: string;
  key_value: string;
  observation: string;
}

export interface OracleDiscoverySection {
  key: string;
  title: string;
  columns: string[];
  rows: Record<string, string>[];
  row_count: number;
  truncated: boolean;
}

export interface OracleSchemaDependencyIssue {
  code: string;
  label: string;
  status: "CLEAR" | "REVIEW" | "HIGH_RISK";
  object_count: number;
  observation: string;
  recommended_action: string | null;
  object_names: string[];
  examples: string[];
  section_keys: string[];
}

export interface OracleSchemaDependencyAnalysis {
  status: "CLEAR" | "REVIEW" | "HIGH_RISK";
  summary: string;
  high_risk_count: number;
  review_count: number;
  clear_count: number;
  issues: OracleSchemaDependencyIssue[];
}

export interface MigrationCompatibilityCheck {
  code: string;
  label: string;
  status: "PASS" | "WARN" | "FAIL" | "INFO";
  message: string;
  source_value: string | null;
  target_value: string | null;
  remediation_sql: string | null;
}

export interface MigrationRemediationScript {
  code: string;
  label: string;
  category:
    | "USER"
    | "TABLESPACE"
    | "DIRECTORY"
    | "DIRECTORY_GRANT"
    | "PROFILE"
    | "ROLE"
    | "ACL"
    | "OBJECT_STORAGE_CREDENTIAL";
  status: "READY" | "OPTIONAL";
  summary: string;
  sql: string;
}

export interface MigrationRemediationPack {
  pack_version: number;
  summary: string;
  scripts: MigrationRemediationScript[];
  combined_sql: string;
}

export interface MigrationReadinessFactor {
  code: string;
  label: string;
  weight: number;
  status: "PASS" | "WARN" | "FAIL" | "INFO";
  score: number;
  observation: string;
  source_value: string | null;
  target_value: string | null;
}

export interface MigrationReadinessCategory {
  key: string;
  label: string;
  weight: number;
  score: number;
  factors: MigrationReadinessFactor[];
}

export interface MigrationReadinessSummary {
  overall_score: number;
  verdict: "READY" | "REVIEW" | "BLOCKED";
  summary: string;
  categories: MigrationReadinessCategory[];
}

export interface MigrationCompatibilityAssessment {
  status:
    | "MIGRATABLE"
    | "CONDITIONALLY_MIGRATABLE"
    | "NOT_MIGRATABLE"
    | "FAILED";
  summary: string;
  source_connection_status: "CONNECTED" | "FAILED" | "NOT_PROVIDED";
  target_connection_status: "CONNECTED" | "FAILED" | "NOT_PROVIDED";
  source: OracleSourceMetadata | null;
  target: OracleTargetMetadata | null;
  checks: MigrationCompatibilityCheck[];
  remediation_pack: MigrationRemediationPack | null;
  blockers: string[];
  warnings: string[];
  readiness: MigrationReadinessSummary | null;
  notes: string[];
  validated_at: string;
}

export interface MigrationCreate {
  request_id?: string;
  source: SourceDetails;
  target: TargetDetails;
  scope: ScopeDetails;
  business: BusinessDetails;
  connectivity: ConnectivityDetails;
  features: FeatureDetails;
  metadata_collection?: MetadataCollectionOptions | null;
  source_metadata?: OracleSourceMetadata | null;
  target_metadata?: OracleTargetMetadata | null;
  migration_validation?: MigrationCompatibilityAssessment | null;
}

export interface MigrationRecord {
  request_id: string;
  source: SourceDetails;
  target: TargetDetails;
  scope: ScopeDetails;
  business: BusinessDetails;
  connectivity: ConnectivityDetails;
  features: FeatureDetails;
  metadata_collection?: MetadataCollectionOptions | null;
  source_metadata?: OracleSourceMetadata | null;
  target_metadata?: OracleTargetMetadata | null;
  migration_validation?: MigrationCompatibilityAssessment | null;
  created_at: string;
  status: "draft" | "submitted";
}
