import type { MigrationFormValues } from "./formModel";

function hasSourceConnectionInput(payload: MigrationFormValues): boolean {
  const connection = payload.metadata_collection.source_connection;
  return Boolean(
    connection.host.trim() ||
      connection.service_name.trim() ||
      connection.username.trim() ||
      connection.password.trim() ||
      connection.wallet_location.trim(),
  );
}

function hasTargetConnectionInput(payload: MigrationFormValues): boolean {
  const connection = payload.metadata_collection.target_connection;
  return Boolean(
    connection.host.trim() ||
      connection.service_name.trim() ||
      connection.username.trim() ||
      connection.password.trim() ||
      connection.wallet_location.trim(),
  );
}

export function validateSourceConnectionForm(
  payload: MigrationFormValues,
  requireSource = true,
): string[] {
  const errors: string[] = [];

  if (!payload.metadata_collection.enabled) {
    return errors;
  }

  const sourceProvided = hasSourceConnectionInput(payload);
  if (!requireSource && !sourceProvided) {
    return errors;
  }

  if (!payload.metadata_collection.source_connection.host.trim()) {
    errors.push("Source database host is required when metadata collection is enabled.");
  }
  if (payload.metadata_collection.source_connection.port <= 0) {
    errors.push("Source listener port must be greater than 0.");
  }
  if (!payload.metadata_collection.source_connection.service_name.trim()) {
    errors.push("Source service name is required when metadata collection is enabled.");
  }
  if (!payload.metadata_collection.source_connection.username.trim()) {
    errors.push("Source database username is required when metadata collection is enabled.");
  }
  if (!payload.metadata_collection.source_connection.password.trim()) {
    errors.push("Source database password is required when metadata collection is enabled.");
  }
  if (
    payload.metadata_collection.source_connection.username.trim().toLowerCase() === "sys" &&
    !payload.metadata_collection.source_connection.sysdba
  ) {
    errors.push("When using the SYS account, enable 'Connect as SYSDBA' before testing.");
  }

  return errors;
}

export function validateTargetConnectionForm(
  payload: MigrationFormValues,
  requireTarget = false,
): string[] {
  const errors: string[] = [];

  if (!payload.metadata_collection.enabled) {
    return errors;
  }

  const targetProvided = hasTargetConnectionInput(payload);
  if (!requireTarget && !targetProvided) {
    return errors;
  }

  if (!payload.metadata_collection.target_connection.host.trim()) {
    errors.push("Target database host is required when target validation is used.");
  }
  if (payload.metadata_collection.target_connection.port <= 0) {
    errors.push("Target listener port must be greater than 0.");
  }
  if (!payload.metadata_collection.target_connection.service_name.trim()) {
    errors.push("Target service name is required when target validation is used.");
  }
  if (!payload.metadata_collection.target_connection.username.trim()) {
    errors.push("Target database username is required when target validation is used.");
  }
  if (!payload.metadata_collection.target_connection.password.trim()) {
    errors.push("Target database password is required when target validation is used.");
  }
  if (
    payload.metadata_collection.target_connection.username.trim().toLowerCase() === "sys" &&
    !payload.metadata_collection.target_connection.sysdba
  ) {
    errors.push("When using the target SYS account, enable 'Connect as SYSDBA' before testing.");
  }

  return errors;
}

export function validateMetadataConnectionForm(
  payload: MigrationFormValues,
): string[] {
  return [
    ...validateSourceConnectionForm(payload),
    ...validateTargetConnectionForm(payload, false),
  ];
}

export function validateMigrationForm(payload: MigrationFormValues): string[] {
  return validateMigrationFormWithOptions(payload, {
    allowImportedSourceMetadata: false,
  });
}

export function validateMigrationFormWithOptions(
  payload: MigrationFormValues,
  options: {
    allowImportedSourceMetadata: boolean;
  },
): string[] {
  const errors: string[] = [];

  if (!payload.source.oracle_version.trim()) {
    errors.push("Source Oracle version is required.");
  }
  if (!payload.target.oracle_version.trim()) {
    errors.push("Target Oracle version is required.");
  }
  if (!payload.source.platform.trim()) {
    errors.push("Source platform is required.");
  }
  if (!payload.target.platform.trim()) {
    errors.push("Target platform is required.");
  }
  if (payload.source.database_size_gb <= 0) {
    errors.push("Database size must be greater than 0 GB.");
  }
  if (payload.scope.schema_count < 0) {
    errors.push("Schema count cannot be negative.");
  }
  if (
    payload.scope.migration_scope === "SCHEMA" &&
    !payload.scope.schema_names
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean).length
  ) {
    errors.push(
      "Schema names are required for schema-scoped validation so the app can verify target prerequisites.",
    );
  }
  if (payload.business.downtime_window_minutes < 0) {
    errors.push("Downtime window cannot be negative.");
  }
  if (payload.connectivity.network_bandwidth_mbps < 0) {
    errors.push("Network bandwidth cannot be negative.");
  }
  errors.push(
    ...validateSourceConnectionForm(
      payload,
      !options.allowImportedSourceMetadata,
    ),
  );
  errors.push(...validateTargetConnectionForm(payload, false));

  return errors;
}
