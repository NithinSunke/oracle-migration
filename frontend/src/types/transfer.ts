import type { OracleConnectionConfig } from "./migration";

export type DataPumpOperation = "EXPORT" | "IMPORT";
export type DataPumpScope = "FULL" | "SCHEMA" | "TABLE";
export type DataPumpExecutionBackend = "auto" | "cli" | "db_api";
export type DataPumpResolvedBackend = "cli" | "db_api";
export type DataPumpStorageType = "LOCAL_FS" | "OCI_OBJECT_STORAGE";
export type DataPumpJobStatus =
  | "QUEUED"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "PLANNED";

export interface SchemaRemap {
  source_schema: string;
  target_schema: string;
}

export interface DataPumpJobOptions {
  directory_object: string;
  dump_file: string;
  log_file: string | null;
  storage_type: DataPumpStorageType;
  object_storage: {
    credential_name: string;
    region: string;
    namespace: string;
    bucket: string;
    object_prefix: string | null;
  } | null;
  transfer_dump_files: boolean;
  parallel: number;
  schemas: string[];
  tables: string[];
  exclude_statistics: boolean;
  compression_enabled: boolean;
  table_exists_action: "SKIP" | "APPEND" | "TRUNCATE" | "REPLACE";
  remap_schemas: SchemaRemap[];
}

export interface DataPumpCommandPreview {
  backend: DataPumpResolvedBackend;
  executable: string;
  command_line: string;
  parameter_lines: string[];
}

export interface DataPumpFailureAnalysis {
  failed_stage: string | null;
  failed_object: string | null;
  failed_owner: string | null;
  failed_error_code: string | null;
  summary: string | null;
  retry_notes: string[];
  suggested_parameter_changes: string[];
}

export interface DataPumpConnectivityDiagnosticCheck {
  code: string;
  label: string;
  status: "PASS" | "WARN" | "FAIL" | "INFO";
  detail: string;
}

export interface DataPumpConnectivityDiagnosticsRequest {
  source_connection?: OracleConnectionConfig | null;
  target_connection?: OracleConnectionConfig | null;
  object_storage?: DataPumpJobOptions["object_storage"] | null;
}

export interface DataPumpConnectivityDiagnosticsResponse {
  summary: string;
  checks: DataPumpConnectivityDiagnosticCheck[];
}

export interface DataPumpJobCreate {
  job_id?: string;
  request_id?: string | null;
  job_name?: string | null;
  operation: DataPumpOperation;
  scope: DataPumpScope;
  dry_run: boolean;
  source_connection?: OracleConnectionConfig | null;
  target_connection?: OracleConnectionConfig | null;
  options: DataPumpJobOptions;
}

export interface DataPumpJobRecord {
  job_id: string;
  request_id: string | null;
  retry_of_job_id: string | null;
  task_id: string | null;
  job_name: string | null;
  operation: DataPumpOperation;
  scope: DataPumpScope;
  status: DataPumpJobStatus;
  can_retry: boolean;
  dry_run: boolean;
  source_connection: Record<string, unknown> | null;
  target_connection: Record<string, unknown> | null;
  options: DataPumpJobOptions;
  command_preview: DataPumpCommandPreview | null;
  failure_analysis: DataPumpFailureAnalysis | null;
  output_excerpt: string[];
  output_log: string[];
  oracle_log_lines: string[];
  artifact_paths: string[];
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface DataPumpJobListResponse {
  items: DataPumpJobRecord[];
  total: number;
}

export interface DataPumpJobPurgeResponse {
  purged_job_ids: string[];
  purged_count: number;
  preserved_recent_count: number;
  skipped_active_job_ids: string[];
  skipped_active_count: number;
}

export interface DataPumpCapabilitiesResponse {
  execution_enabled: boolean;
  actual_run_ready: boolean;
  execution_backend: DataPumpExecutionBackend;
  resolved_backend: DataPumpResolvedBackend | null;
  cli_available: boolean;
  db_api_available: boolean;
  expdp_path: string;
  impdp_path: string;
  work_dir: string;
  blockers: string[];
  note: string;
}
