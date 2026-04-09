import type { MigrationCreate, MigrationScope } from "../../types";

export interface MigrationFormValues {
  request_id: string;
  source: {
    oracle_version: string;
    deployment_type: string;
    platform: string;
    storage_type: string;
    database_size_gb: number;
    largest_table_gb: number;
    daily_change_rate_gb: number;
    peak_redo_mb_per_sec: number;
    character_set: string;
    tde_enabled: boolean;
    rac_enabled: boolean;
    dataguard_enabled: boolean;
    archivelog_enabled: boolean;
  };
  target: {
    oracle_version: string;
    deployment_type: string;
    platform: string;
    storage_type: string;
    target_is_exadata: boolean;
    same_endian: boolean;
  };
  scope: {
    migration_scope: MigrationScope;
    schema_count: number;
    schema_names: string;
    need_schema_remap: boolean;
    need_tablespace_remap: boolean;
    need_reorg: boolean;
    subset_only: boolean;
  };
  business: {
    downtime_window_minutes: number;
    fallback_required: boolean;
    near_zero_downtime_required: boolean;
    regulated_workload: boolean;
  };
  connectivity: {
    network_bandwidth_mbps: number;
    direct_host_connectivity: boolean;
    shared_storage_available: boolean;
  };
  features: {
    need_version_upgrade: boolean;
    need_cross_platform_move: boolean;
    need_non_cdb_to_pdb_conversion: boolean;
    goldengate_license_available: boolean;
    zdm_supported_target: boolean;
  };
  metadata_collection: {
    enabled: boolean;
    prefer_collected_values: boolean;
    source_connection: {
      host: string;
      port: number;
      service_name: string;
      username: string;
      password: string;
      mode: "thin" | "thick";
      sysdba: boolean;
      wallet_location: string;
    };
    target_connection: {
      host: string;
      port: number;
      service_name: string;
      username: string;
      password: string;
      mode: "thin" | "thick";
      sysdba: boolean;
      wallet_location: string;
    };
  };
}

function normalizeText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function hasConnectionInput(connection: {
  host: string;
  service_name: string;
  username: string;
  password: string;
  wallet_location: string;
}): boolean {
  return Boolean(
    connection.host.trim() ||
      connection.service_name.trim() ||
      connection.username.trim() ||
      connection.password.trim() ||
      connection.wallet_location.trim(),
  );
}

function toConnectionPayload(connection: {
  host: string;
  port: number;
  service_name: string;
  username: string;
  password: string;
  mode: "thin" | "thick";
  sysdba: boolean;
  wallet_location: string;
}) {
  return {
    host: connection.host.trim(),
    port: connection.port,
    service_name: connection.service_name.trim(),
    username: connection.username.trim(),
    password: connection.password.trim() || null,
    password_configured: Boolean(connection.password.trim()),
    mode: connection.mode,
    sysdba: connection.sysdba,
    wallet_location: normalizeText(connection.wallet_location),
  };
}

export function toMigrationCreate(form: MigrationFormValues): MigrationCreate {
  const schemaNames = form.scope.schema_names
    .split(",")
    .map((value) => value.trim().toUpperCase())
    .filter(Boolean);

  const metadataCollection = form.metadata_collection.enabled
    ? (() => {
        const payload: NonNullable<MigrationCreate["metadata_collection"]> = {
          enabled: true,
          prefer_collected_values: form.metadata_collection.prefer_collected_values,
          source_connection: null,
          target_connection: null,
        };

        if (hasConnectionInput(form.metadata_collection.source_connection)) {
          payload.source_connection = toConnectionPayload(
            form.metadata_collection.source_connection,
          );
        }

        if (hasConnectionInput(form.metadata_collection.target_connection)) {
          payload.target_connection = toConnectionPayload(
            form.metadata_collection.target_connection,
          );
        }

        return payload;
      })()
    : null;

  return {
    request_id: form.request_id.trim() ? form.request_id.trim() : undefined,
    source: {
      oracle_version: normalizeText(form.source.oracle_version),
      deployment_type: normalizeText(form.source.deployment_type),
      platform: normalizeText(form.source.platform),
      storage_type: normalizeText(form.source.storage_type),
      database_size_gb: form.source.database_size_gb,
      largest_table_gb: form.source.largest_table_gb,
      daily_change_rate_gb: form.source.daily_change_rate_gb,
      peak_redo_mb_per_sec: form.source.peak_redo_mb_per_sec,
      character_set: normalizeText(form.source.character_set),
      tde_enabled: form.source.tde_enabled,
      rac_enabled: form.source.rac_enabled,
      dataguard_enabled: form.source.dataguard_enabled,
      archivelog_enabled: form.source.archivelog_enabled,
    },
    target: {
      oracle_version: normalizeText(form.target.oracle_version),
      deployment_type: normalizeText(form.target.deployment_type),
      platform: normalizeText(form.target.platform),
      storage_type: normalizeText(form.target.storage_type),
      target_is_exadata: form.target.target_is_exadata,
      same_endian: form.target.same_endian,
    },
    scope: {
      migration_scope: form.scope.migration_scope,
      schema_count: form.scope.schema_count,
      schema_names: schemaNames,
      need_schema_remap: form.scope.need_schema_remap,
      need_tablespace_remap: form.scope.need_tablespace_remap,
      need_reorg: form.scope.need_reorg,
      subset_only: form.scope.subset_only,
    },
    business: {
      downtime_window_minutes: form.business.downtime_window_minutes,
      fallback_required: form.business.fallback_required,
      near_zero_downtime_required: form.business.near_zero_downtime_required,
      regulated_workload: form.business.regulated_workload,
    },
    connectivity: {
      network_bandwidth_mbps: form.connectivity.network_bandwidth_mbps,
      direct_host_connectivity: form.connectivity.direct_host_connectivity,
      shared_storage_available: form.connectivity.shared_storage_available,
    },
    features: {
      need_version_upgrade: form.features.need_version_upgrade,
      need_cross_platform_move: form.features.need_cross_platform_move,
      need_non_cdb_to_pdb_conversion: form.features.need_non_cdb_to_pdb_conversion,
      goldengate_license_available: form.features.goldengate_license_available,
      zdm_supported_target: form.features.zdm_supported_target,
    },
    metadata_collection: metadataCollection,
  };
}
