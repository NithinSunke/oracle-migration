import type { OracleConnectionConfig } from "./migration";

export type DataPumpOperation = "EXPORT" | "IMPORT";
export type DataPumpScope = "FULL" | "SCHEMA";
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
  task_id: string | null;
  job_name: string | null;
  operation: DataPumpOperation;
  scope: DataPumpScope;
  status: DataPumpJobStatus;
  dry_run: boolean;
  source_connection: Record<string, unknown> | null;
  target_connection: Record<string, unknown> | null;
  options: DataPumpJobOptions;
  command_preview: DataPumpCommandPreview | null;
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
