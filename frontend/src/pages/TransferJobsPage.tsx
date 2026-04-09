import { FormEvent, useEffect, useState } from "react";

import { AppFrame } from "../components/AppFrame";
import { StatusPanel } from "../components/StatusPanel";
import { api, ApiError } from "../services/api";
import type {
  DataPumpCapabilitiesResponse,
  DataPumpJobCreate,
  DataPumpJobRecord,
  DataPumpOperation,
  DataPumpScope,
  DataPumpStorageType,
  OracleConnectionConfig,
} from "../types";

interface ConnectionFormState {
  host: string;
  port: number;
  service_name: string;
  username: string;
  password: string;
  mode: "thin" | "thick";
  sysdba: boolean;
  wallet_location: string;
}

function defaultConnection(): ConnectionFormState {
  return {
    host: "",
    port: 1521,
    service_name: "",
    username: "",
    password: "",
    mode: "thin",
    sysdba: false,
    wallet_location: "",
  };
}

function toConnectionPayload(value: ConnectionFormState): OracleConnectionConfig {
  return {
    host: value.host,
    port: value.port,
    service_name: value.service_name,
    username: value.username,
    password: value.password,
    mode: value.mode,
    sysdba: value.sysdba,
    wallet_location: value.wallet_location.trim() || null,
  };
}

function formatDate(value: string | null): string {
  if (!value) {
    return "Not available";
  }

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function statusBadgeClass(status: DataPumpJobRecord["status"]): string {
  if (status === "SUCCEEDED" || status === "PLANNED") {
    return "soft-badge soft-badge--success";
  }
  if (status === "FAILED") {
    return "soft-badge soft-badge--warning";
  }
  return "soft-badge soft-badge--neutral";
}

function statusLabel(job: DataPumpJobRecord): string {
  if (job.status === "PLANNED") {
    return "PLANNED ONLY";
  }
  return job.status;
}

function backendLabel(value: "auto" | "cli" | "db_api" | null): string {
  if (value === null) {
    return "Not available";
  }
  if (value === "db_api") {
    return "DBMS_DATAPUMP";
  }
  if (value === "cli") {
    return "CLI";
  }
  return "Auto";
}

function summarizeConnection(connection: Record<string, unknown> | null): string {
  if (!connection || Object.keys(connection).length === 0) {
    return "Not configured";
  }

  const username = typeof connection.username === "string" ? connection.username : "unknown-user";
  const host = typeof connection.host === "string" ? connection.host : "unknown-host";
  const port = typeof connection.port === "number" ? connection.port : "unknown-port";
  const serviceName =
    typeof connection.service_name === "string" ? connection.service_name : "unknown-service";
  const sysdba = connection.sysdba === true ? " as SYSDBA" : "";

  return `${username}@${host}:${port}/${serviceName}${sysdba}`;
}

function storageLabel(value: DataPumpStorageType): string {
  if (value === "OCI_OBJECT_STORAGE") {
    return "OCI Object Storage";
  }
  return "Local Filesystem";
}

function summarizeObjectStorage(
  value:
    | {
        credential_name: string;
        region: string;
        namespace: string;
        bucket: string;
        object_prefix: string | null;
      }
    | null
    | undefined,
): string {
  if (!value) {
    return "Not configured";
  }

  const prefix = value.object_prefix?.trim() ? `/${value.object_prefix.trim()}` : "";
  return `${value.bucket}${prefix} (${value.region}, ${value.credential_name})`;
}

export function TransferJobsPage() {
  const [capabilities, setCapabilities] = useState<DataPumpCapabilitiesResponse | null>(null);
  const [jobs, setJobs] = useState<DataPumpJobRecord[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<DataPumpJobRecord | null>(null);
  const [jobName, setJobName] = useState("");
  const [requestId, setRequestId] = useState("");
  const [operation, setOperation] = useState<DataPumpOperation>("EXPORT");
  const [scope, setScope] = useState<DataPumpScope>("SCHEMA");
  const [dryRun, setDryRun] = useState(true);
  const [sourceConnection, setSourceConnection] = useState<ConnectionFormState>(
    defaultConnection,
  );
  const [targetConnection, setTargetConnection] = useState<ConnectionFormState>(
    defaultConnection,
  );
  const [directoryObject, setDirectoryObject] = useState("DATA_PUMP_DIR");
  const [dumpFile, setDumpFile] = useState("migration_export.dmp");
  const [logFile, setLogFile] = useState("migration_export.log");
  const [storageType, setStorageType] = useState<DataPumpStorageType>("LOCAL_FS");
  const [objectStorageCredential, setObjectStorageCredential] = useState("");
  const [objectStorageRegion, setObjectStorageRegion] = useState("");
  const [objectStorageNamespace, setObjectStorageNamespace] = useState("");
  const [objectStorageBucket, setObjectStorageBucket] = useState("");
  const [objectStoragePrefix, setObjectStoragePrefix] = useState("");
  const [transferDumpFiles, setTransferDumpFiles] = useState(false);
  const [parallel, setParallel] = useState(1);
  const [schemasText, setSchemasText] = useState("");
  const [remapText, setRemapText] = useState("");
  const [excludeStatistics, setExcludeStatistics] = useState(true);
  const [compressionEnabled, setCompressionEnabled] = useState(false);
  const [tableExistsAction, setTableExistsAction] = useState<
    "SKIP" | "APPEND" | "TRUNCATE" | "REPLACE"
  >("SKIP");
  const [isLoadingJobs, setIsLoadingJobs] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPurgingHistory, setIsPurgingHistory] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [historyMessage, setHistoryMessage] = useState<string | null>(null);
  const [showFullLog, setShowFullLog] = useState(false);
  const actualRunUnavailable =
    dryRun === false && capabilities?.actual_run_ready === false;
  const objectStorageImportNeedsCli =
    operation === "IMPORT" &&
    storageType === "OCI_OBJECT_STORAGE";
  const currentSelectionNeedsCli =
    dryRun === false &&
    operation === "IMPORT" &&
    storageType === "OCI_OBJECT_STORAGE";
  const currentSelectionReady =
    dryRun === true
      ? true
      : currentSelectionNeedsCli
        ? (capabilities?.cli_available ?? false)
        : (capabilities?.actual_run_ready ?? false);
  const importNeedsSourceConnection =
    operation === "IMPORT" &&
    storageType === "LOCAL_FS" &&
    transferDumpFiles;
  const purgeableJobs = jobs.filter(
    (job) => job.status !== "QUEUED" && job.status !== "RUNNING",
  );

  async function loadJobs(preferredJobId?: string | null) {
    setIsLoadingJobs(true);
    try {
      const response = await api.listDataPumpJobs();
      setJobs(response.items);

      const requestedJobId = preferredJobId ?? selectedJobId;
      const nextSelectedJobId =
        response.items.find((item) => item.job_id === requestedJobId)?.job_id ??
        response.items[0]?.job_id ??
        null;
      setSelectedJobId(nextSelectedJobId);
      if (nextSelectedJobId) {
        const match =
          response.items.find((item) => item.job_id === nextSelectedJobId) ?? null;
        setSelectedJob(match);
        setShowFullLog(false);
      } else {
        setSelectedJob(null);
      }
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("Unable to load Data Pump jobs.");
      }
    } finally {
      setIsLoadingJobs(false);
    }
  }

  async function handlePurgeHistory() {
    if (purgeableJobs.length === 0) {
      setHistoryMessage("There are no completed or planned Data Pump jobs to purge right now.");
      return;
    }

    const confirmed = window.confirm(
      "Purge historical Data Pump jobs from the app? Running and queued jobs will be kept.",
    );
    if (!confirmed) {
      return;
    }

    setIsPurgingHistory(true);
    setErrorMessage(null);
    setHistoryMessage(null);

    try {
      const response = await api.purgeDataPumpJobsHistory();
      const keptMessage =
        response.skipped_active_count > 0
          ? ` ${response.skipped_active_count} active job${
              response.skipped_active_count === 1 ? " was" : "s were"
            } kept.`
          : "";

      if (response.purged_count > 0) {
        setHistoryMessage(
          `Purged ${response.purged_count} historical Data Pump job${
            response.purged_count === 1 ? "" : "s"
          }.${keptMessage}`,
        );
      } else {
        setHistoryMessage(`No historical jobs were purged.${keptMessage}`);
      }

      await loadJobs();
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("Unable to purge historical Data Pump jobs.");
      }
    } finally {
      setIsPurgingHistory(false);
    }
  }

  useEffect(() => {
    void api.getDataPumpCapabilities().then((response) => {
      setCapabilities(response);
    }).catch(() => {
      // Leave the page usable even if capabilities fail to load.
    });

    void loadJobs();
  }, []);

  useEffect(() => {
    if (!selectedJobId) {
      setSelectedJob(null);
      return;
    }

    const jobId = selectedJobId;
    let active = true;

    async function loadSelectedJob() {
      try {
        const response = await api.getDataPumpJob(jobId);
        if (active) {
          setSelectedJob(response);
          setShowFullLog(false);
        }
      } catch (error) {
        if (!active) {
          return;
        }
        if (error instanceof ApiError) {
          setErrorMessage(error.message);
        } else {
          setErrorMessage("Unable to load the selected Data Pump job.");
        }
      }
    }

    void loadSelectedJob();

    return () => {
      active = false;
    };
  }, [selectedJobId]);

  useEffect(() => {
    setShowFullLog(selectedJob?.status === "FAILED");
  }, [selectedJob?.job_id, selectedJob?.status]);

  useEffect(() => {
    if (!selectedJobId || !selectedJob) {
      return;
    }
    if (selectedJob.status !== "QUEUED" && selectedJob.status !== "RUNNING") {
      return;
    }

    const intervalId = window.setInterval(() => {
      void api.getDataPumpJob(selectedJobId).then((response) => {
        setSelectedJob(response);
        setJobs((current) =>
          current.map((item) => (item.job_id === response.job_id ? response : item)),
        );
      }).catch(() => {
        // Keep the last visible state if polling fails.
      });
    }, 4000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [selectedJob, selectedJobId]);

  function renderConnectionFields(
    title: string,
    description: string,
    value: ConnectionFormState,
    setValue: (next: ConnectionFormState) => void,
  ) {
    return (
      <section className="panel panel--inner">
        <div className="section-heading">
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <div className="form-grid form-grid--metadata">
          <label className="field">
            <span>Host</span>
            <input
              value={value.host}
              onChange={(event) => setValue({ ...value, host: event.target.value })}
              placeholder="db-host.example.com"
            />
          </label>
          <label className="field">
            <span>Port</span>
            <input
              type="number"
              min="1"
              value={value.port}
              onChange={(event) =>
                setValue({ ...value, port: Number(event.target.value) || 1521 })
              }
            />
          </label>
          <label className="field">
            <span>Service Name</span>
            <input
              value={value.service_name}
              onChange={(event) =>
                setValue({ ...value, service_name: event.target.value })
              }
              placeholder="ORCLPDB1"
            />
          </label>
          <label className="field">
            <span>Username</span>
            <input
              value={value.username}
              onChange={(event) =>
                setValue({ ...value, username: event.target.value })
              }
              placeholder="system"
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={value.password}
              onChange={(event) =>
                setValue({ ...value, password: event.target.value })
              }
              placeholder="Enter password"
            />
          </label>
          <label className="field">
            <span>Mode</span>
            <select
              value={value.mode}
              onChange={(event) =>
                setValue({
                  ...value,
                  mode: event.target.value as "thin" | "thick",
                })
              }
            >
              <option value="thin">Thin</option>
              <option value="thick">Thick</option>
            </select>
          </label>
          <label className="field">
            <span>Wallet Location</span>
            <input
              value={value.wallet_location}
              onChange={(event) =>
                setValue({ ...value, wallet_location: event.target.value })
              }
              placeholder="/opt/oracle/wallet"
            />
          </label>
          <label className="checkbox-inline">
            <input
              type="checkbox"
              checked={value.sysdba}
              onChange={(event) =>
                setValue({ ...value, sysdba: event.target.checked })
              }
            />{" "}
            Connect as SYSDBA
          </label>
        </div>
      </section>
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setHistoryMessage(null);

    if (actualRunUnavailable) {
      setErrorMessage(
        "Actual-run submission is blocked because live Data Pump execution is not available in the current runtime. Re-enable Dry-run only, or enable at least one execution backend for this worker.",
      );
      return;
    }
    setIsSubmitting(true);

    try {
      const schemas = schemasText
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const remapSchemas = remapText
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean)
        .map((item) => {
          const [source_schema, target_schema] = item.split(":").map((part) => part.trim());
          return { source_schema, target_schema };
        })
        .filter((item) => item.source_schema && item.target_schema);

      const payload: DataPumpJobCreate = {
        request_id: requestId.trim() || null,
        job_name: jobName.trim() || null,
        operation,
        scope,
        dry_run: dryRun,
        source_connection:
          operation === "EXPORT" || transferDumpFiles
            ? toConnectionPayload(sourceConnection)
            : null,
        target_connection:
          operation === "IMPORT" ? toConnectionPayload(targetConnection) : null,
        options: {
          directory_object: directoryObject.trim(),
          dump_file: dumpFile.trim(),
          log_file: logFile.trim() || null,
          storage_type: storageType,
          object_storage:
            storageType === "OCI_OBJECT_STORAGE"
              ? {
                  credential_name: objectStorageCredential.trim(),
                  region: objectStorageRegion.trim().replace(/\.+$/, ""),
                  namespace: objectStorageNamespace.trim(),
                  bucket: objectStorageBucket.trim(),
                  object_prefix: objectStoragePrefix.trim() || null,
                }
              : null,
          transfer_dump_files:
            storageType === "LOCAL_FS" ? transferDumpFiles : false,
          parallel,
          schemas,
          exclude_statistics: excludeStatistics,
          compression_enabled: compressionEnabled,
          table_exists_action: tableExistsAction,
          remap_schemas: remapSchemas,
        },
      };

      const created = await api.createDataPumpJob(payload);
      setSelectedJobId(created.job_id);
      setSelectedJob(created);
      await loadJobs(created.job_id);
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("Unable to start the Data Pump job.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AppFrame
      eyebrow="Export-Import"
      title="Run Oracle Data Pump export and import jobs"
      summary="Launch Data Pump jobs from the app, keep the command plan in one place, and monitor worker status without leaving the assessment platform."
      pageClassName="page--wide"
    >
      {isLoadingJobs ? (
        <StatusPanel
          title="Loading Data Pump jobs"
          description="Fetching the recent export and import jobs created through the app."
        />
      ) : null}

      {!isLoadingJobs && errorMessage ? (
        <StatusPanel title="Export-Import feature unavailable" description={errorMessage} tone="error" />
      ) : null}

      {!isLoadingJobs ? (
        <div className="panel-grid report-layout transfer-layout">
          <section className="panel">
            <div className="section-heading">
              <h2>Create Data Pump Job</h2>
              <p>
                Use dry-run to preview the generated command, or submit an actual-run request
                when the worker environment is ready to execute Oracle Data Pump.
              </p>
            </div>
            {capabilities ? (
              <div
                className={
                  currentSelectionReady
                    ? "form-alert form-alert--success"
                    : "form-alert form-alert--error"
                }
              >
                <strong>
                  {currentSelectionReady
                    ? "Current selection is ready."
                    : "Current selection is not ready for actual execution."}
                </strong>
                <p>{capabilities.note}</p>
                {currentSelectionNeedsCli ? (
                  <p>
                    This form selection needs the CLI <code>impdp</code> path.{" "}
                    {capabilities.cli_available
                      ? "CLI tools are available in the worker runtime."
                      : "CLI ready is No, so this actual-run request will fail until impdp is mounted into the worker runtime."}
                  </p>
                ) : null}
                {!currentSelectionNeedsCli && dryRun === false ? (
                  <p>
                    This form selection can use the currently resolved backend:{" "}
                    <strong>{backendLabel(capabilities.resolved_backend)}</strong>.
                  </p>
                ) : null}
                <p>
                  Configured backend: <strong>{backendLabel(capabilities.execution_backend)}</strong>
                  {" • "}
                  Resolved backend: <strong>{backendLabel(capabilities.resolved_backend)}</strong>
                </p>
                <p>
                  CLI ready: <strong>{capabilities.cli_available ? "Yes" : "No"}</strong>
                  {" • "}
                  DB API ready: <strong>{capabilities.db_api_available ? "Yes" : "No"}</strong>
                </p>
                {!capabilities.actual_run_ready && capabilities.blockers.length > 0 ? (
                  <ul className="bullet-list">
                    {capabilities.blockers.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
            <form className="transfer-form-stack" onSubmit={handleSubmit}>
              <section className="panel panel--inner">
                <div className="form-grid">
                  <label className="field">
                    <span>Job Name</span>
                    <input
                      value={jobName}
                      onChange={(event) => setJobName(event.target.value)}
                      placeholder="Finance schema export"
                    />
                  </label>
                  <label className="field">
                    <span>Request ID (optional)</span>
                    <input
                      value={requestId}
                      onChange={(event) => setRequestId(event.target.value)}
                      placeholder="MIG-..."
                    />
                  </label>
                  <label className="field">
                    <span>Operation</span>
                    <select
                      value={operation}
                      onChange={(event) =>
                        setOperation(event.target.value as DataPumpOperation)
                      }
                    >
                      <option value="EXPORT">Export</option>
                      <option value="IMPORT">Import</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>Scope</span>
                    <select
                      value={scope}
                      onChange={(event) => setScope(event.target.value as DataPumpScope)}
                    >
                      <option value="SCHEMA">Schema</option>
                      <option value="FULL">Full</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>Storage Type</span>
                    <select
                      value={storageType}
                      onChange={(event) => {
                        const nextValue = event.target.value as DataPumpStorageType;
                        setStorageType(nextValue);
                        if (nextValue !== "LOCAL_FS") {
                          setTransferDumpFiles(false);
                        }
                      }}
                    >
                      <option value="LOCAL_FS">Local Filesystem</option>
                      <option value="OCI_OBJECT_STORAGE">OCI Object Storage</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>Directory Object</span>
                    <input
                      value={directoryObject}
                      onChange={(event) => setDirectoryObject(event.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>Dump File</span>
                    <input
                      value={dumpFile}
                      onChange={(event) => setDumpFile(event.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>Log File</span>
                    <input
                      value={logFile}
                      onChange={(event) => setLogFile(event.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>Parallel</span>
                    <input
                      type="number"
                      min="1"
                      max="32"
                      value={parallel}
                      onChange={(event) => setParallel(Number(event.target.value) || 1)}
                    />
                  </label>
                  {scope === "SCHEMA" ? (
                    <label className="field">
                      <span>Schemas (comma-separated)</span>
                      <input
                        value={schemasText}
                        onChange={(event) => setSchemasText(event.target.value)}
                        placeholder="HR,FINANCE"
                      />
                    </label>
                  ) : null}
                  {operation === "IMPORT" ? (
                    <label className="field">
                      <span>Schema Remap (source:target)</span>
                      <input
                        value={remapText}
                        onChange={(event) => setRemapText(event.target.value)}
                      placeholder="HR:HR_STAGE,FINANCE:FINANCE_NEW"
                    />
                  </label>
                ) : null}
                  {storageType === "OCI_OBJECT_STORAGE" ? (
                    <>
                      <label className="field">
                        <span>Credential Name</span>
                        <input
                          value={objectStorageCredential}
                          onChange={(event) => setObjectStorageCredential(event.target.value)}
                          placeholder="OCI_DP_CRED"
                        />
                      </label>
                      <label className="field">
                        <span>Region</span>
                        <input
                          value={objectStorageRegion}
                          onChange={(event) => setObjectStorageRegion(event.target.value)}
                          placeholder="us-ashburn-1"
                        />
                      </label>
                      <label className="field">
                        <span>Namespace</span>
                        <input
                          value={objectStorageNamespace}
                          onChange={(event) => setObjectStorageNamespace(event.target.value)}
                          placeholder="yourtenancynamespace"
                        />
                      </label>
                      <label className="field">
                        <span>Bucket</span>
                        <input
                          value={objectStorageBucket}
                          onChange={(event) => setObjectStorageBucket(event.target.value)}
                          placeholder="migration-dumps"
                        />
                      </label>
                    <label className="field">
                      <span>Object Prefix</span>
                      <input
                        value={objectStoragePrefix}
                        onChange={(event) => setObjectStoragePrefix(event.target.value)}
                        placeholder="exports/finance"
                      />
                    </label>
                    {operation === "IMPORT" ? (
                      <p className="field-helper field-helper--standalone">
                        Leave <code>Object Prefix</code> empty for OCI import actual-runs.
                        Oracle Data Pump import rejects Object Storage URIs that require
                        encoded slash segments such as <code>%2F</code>.
                      </p>
                    ) : null}
                  </>
                ) : null}
                </div>
                <div
                  className={
                    objectStorageImportNeedsCli && !dryRun
                      ? "form-alert form-alert--error"
                      : storageType === "OCI_OBJECT_STORAGE"
                        ? "form-alert form-alert--success"
                        : "form-alert"
                  }
                >
                  <strong>
                    {objectStorageImportNeedsCli && !dryRun
                      ? "OCI Object Storage CLI mode"
                      : storageType === "OCI_OBJECT_STORAGE"
                        ? "Direct OCI Object Storage mode"
                        : "Local filesystem mode"}
                  </strong>
                  <p>
                    {objectStorageImportNeedsCli && !dryRun
                      ? "This import needs the CLI impdp runtime in the worker. The app will use impdp for actual execution instead of DBMS_DATAPUMP."
                      : storageType === "OCI_OBJECT_STORAGE"
                        ? "The app will build the Data Pump job to export to or import from OCI Object Storage directly by using the database credential and object URI."
                        : "The app will use the Oracle DIRECTORY object and local filesystem path for the Data Pump dump file."}
                  </p>
                  {objectStorageImportNeedsCli ? (
                    <p>
                      Actual OCI import will run through <code>impdp</code>. If the worker does
                      not have the CLI tools mounted yet, the submission will fail with a
                      runtime-preparation message instead of falling back to the unsupported
                      DBMS_DATAPUMP import path.
                    </p>
                  ) : null}
                </div>
                <div className="toggle-sections">
                  <fieldset className="toggle-group">
                    <legend>Execution Options</legend>
                    <label>
                      <input
                        type="checkbox"
                        checked={dryRun}
                        onChange={(event) => setDryRun(event.target.checked)}
                      />{" "}
                      Dry-run only
                    </label>
                    {capabilities?.actual_run_ready === false ? (
                      <p className="field-helper field-helper--standalone">
                        You can still switch between dry-run and actual-run here. In the
                        current environment, actual-run submissions are blocked until backend
                        execution is enabled and at least one runtime path is ready.
                      </p>
                    ) : null}
                    {actualRunUnavailable ? (
                      <div className="form-alert form-alert--error">
                        <strong>Actual run is not available right now.</strong>
                        <p>
                          This environment cannot execute Oracle Data Pump yet. Re-enable
                          <code> Dry-run only </code> or prepare the worker runtime for either
                          the CLI path or the DBMS_DATAPUMP path.
                        </p>
                      </div>
                    ) : null}
                    {objectStorageImportNeedsCli ? (
                      <div className="form-alert">
                        <strong>OCI import uses the CLI path.</strong>
                        <p>
                          Direct OCI Object Storage imports are routed through{" "}
                          <code>impdp</code> for actual runs because the{" "}
                          <code>DBMS_DATAPUMP</code> import path is not reliable in this
                          environment.
                        </p>
                        <p>
                          The app passes the configured credential and Object Storage URI
                          directly to <code>impdp</code>. It does not use the PDB{" "}
                          <code>DEFAULT_CREDENTIAL</code> property.
                        </p>
                        <p>
                          Store the dump file at the bucket root for import. Nested object
                          prefixes make OCI encode the object name with <code>%2F</code>, and
                          Oracle Data Pump import rejects that URI format.
                        </p>
                      </div>
                    ) : null}
                    <label>
                      <input
                        type="checkbox"
                        checked={excludeStatistics}
                        onChange={(event) => setExcludeStatistics(event.target.checked)}
                      />{" "}
                      Exclude statistics
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={compressionEnabled}
                        onChange={(event) => setCompressionEnabled(event.target.checked)}
                        disabled={operation !== "EXPORT"}
                      />{" "}
                      Compression enabled
                    </label>
                  </fieldset>
                  {operation === "IMPORT" && storageType === "LOCAL_FS" ? (
                    <fieldset className="toggle-group">
                      <legend>Import Behavior</legend>
                      <label>
                        <input
                          type="checkbox"
                          checked={transferDumpFiles}
                          onChange={(event) => setTransferDumpFiles(event.target.checked)}
                        />{" "}
                        Transfer dump file from source to target before import
                      </label>
                      <p className="field-helper field-helper--standalone">
                        Turn this on only when the dump file is still on the source side and
                        you want the app to plan around source-to-target transfer. Leave it off
                        when the dump file is already available on the target system.
                      </p>
                      {transferDumpFiles ? (
                        <div className="form-alert">
                          <strong>Transfer requested</strong>
                          <p>
                            Source details are now required for this import request because the
                            dump file is expected to come from the source side.
                          </p>
                          <p>
                            Actual transfer execution is not implemented yet. Use this option
                            only for planning right now, or leave it off when the dump file is
                            already available on the target side.
                          </p>
                        </div>
                      ) : (
                        <div className="form-alert form-alert--success">
                          <strong>Transfer not requested</strong>
                          <p>
                            This import assumes the dump file is already present on the target
                            side, so source connection details are optional.
                          </p>
                        </div>
                      )}
                      <label>
                        <span>Table Exists Action</span>
                        <select
                          value={tableExistsAction}
                          onChange={(event) =>
                            setTableExistsAction(
                              event.target.value as "SKIP" | "APPEND" | "TRUNCATE" | "REPLACE",
                            )
                          }
                        >
                          <option value="SKIP">Skip</option>
                          <option value="APPEND">Append</option>
                          <option value="TRUNCATE">Truncate</option>
                          <option value="REPLACE">Replace</option>
                        </select>
                      </label>
                    </fieldset>
                  ) : null}
                  {operation === "IMPORT" && storageType === "OCI_OBJECT_STORAGE" ? (
                    <fieldset className="toggle-group">
                      <legend>Import Behavior</legend>
                      <p className="field-helper field-helper--standalone">
                        This import will read the dump file directly from OCI Object Storage, so
                        source-to-target dump transfer is not used.
                      </p>
                      <label>
                        <span>Table Exists Action</span>
                        <select
                          value={tableExistsAction}
                          onChange={(event) =>
                            setTableExistsAction(
                              event.target.value as "SKIP" | "APPEND" | "TRUNCATE" | "REPLACE",
                            )
                          }
                        >
                          <option value="SKIP">Skip</option>
                          <option value="APPEND">Append</option>
                          <option value="TRUNCATE">Truncate</option>
                          <option value="REPLACE">Replace</option>
                        </select>
                      </label>
                    </fieldset>
                  ) : null}
                </div>
              </section>

              {operation === "EXPORT" || importNeedsSourceConnection
                ? renderConnectionFields(
                    "Source Oracle Connection",
                    operation === "EXPORT"
                      ? "Export jobs use this Oracle connection for either the CLI expdp path or the DBMS_DATAPUMP execution path."
                      : "Provide the source Oracle connection because this import request expects dump-file transfer from source to target.",
                    sourceConnection,
                    setSourceConnection,
                  )
                : operation === "IMPORT"
                  ? (
                    <section className="panel panel--inner">
                      <div className="section-heading">
                        <h2>Source Oracle Connection</h2>
                        <p>
                          Not required for this import because dump-file transfer is not selected.
                        </p>
                      </div>
                    </section>
                  )
                  : null}

              {operation === "IMPORT"
                ? renderConnectionFields(
                    "Target Oracle Connection",
                    "Import jobs use this Oracle target connection for either the CLI impdp path or the DBMS_DATAPUMP execution path.",
                    targetConnection,
                    setTargetConnection,
                  )
                : null}

              <div className="form-actions">
                <button
                  className="primary-button"
                  type="submit"
                  disabled={isSubmitting}
                >
                  {isSubmitting
                    ? "Submitting Data Pump Job..."
                    : dryRun
                      ? "Create Data Pump Plan"
                      : "Queue Actual Data Pump Run"}
                </button>
              </div>
            </form>
          </section>

          <section className="panel">
            <div className="section-heading">
              <h2>Recent Data Pump Jobs</h2>
              <p>Select a job to inspect its current state, generated command, and worker output.</p>
            </div>
            <div className="form-actions">
              <button
                className="secondary-button"
                type="button"
                disabled={isPurgingHistory || purgeableJobs.length === 0}
                onClick={() => {
                  void handlePurgeHistory();
                }}
              >
                {isPurgingHistory ? "Purging History..." : "Purge Historical Jobs"}
              </button>
            </div>
            <p className="field-helper field-helper--standalone">
              This clears finished app history only. Active <code>QUEUED</code> and{" "}
              <code>RUNNING</code> jobs are kept.
            </p>
            {historyMessage ? (
              <div className="form-alert form-alert--success">
                <strong>History updated</strong>
                <p>{historyMessage}</p>
              </div>
            ) : null}
            {jobs.length === 0 ? (
              <StatusPanel
                title="No transfer jobs yet"
                description="Create a dry-run export or import job to preview the generated Data Pump command here."
              />
            ) : (
              <ul className="selection-list">
                {jobs.map((job) => (
                  <li key={job.job_id}>
                    <button
                      type="button"
                      className={`selection-card${
                        selectedJobId === job.job_id ? " selection-card--active" : ""
                      }`}
                      onClick={() => {
                        setErrorMessage(null);
                        setHistoryMessage(null);
                        setSelectedJobId(job.job_id);
                      }}
                    >
                      <strong>{job.job_name || job.job_id}</strong>
                      <span>
                        {job.operation} {job.scope}
                      </span>
                      <small>
                        Created {formatDate(job.created_at)} •{" "}
                        <span className={statusBadgeClass(job.status)}>{statusLabel(job)}</span>
                      </small>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {selectedJob ? (
              <section className="panel panel--inner">
                <div className="section-heading">
                  <h2>Selected Job</h2>
                  <p>
                    {selectedJob.status === "PLANNED"
                      ? "This job was planned but not executed. Review the generated command and worker notes below."
                      : "Review the generated Data Pump command and the latest worker notes."}
                  </p>
                </div>
                {selectedJob.status === "PLANNED" ? (
                  <div className="form-alert">
                    <strong>Planned only</strong>
                    <p>
                      This usually means the job was submitted with <code>Dry-run only</code>{" "}
                      enabled, or live Data Pump execution is disabled in the worker runtime.
                    </p>
                  </div>
                ) : null}
                <dl className="snapshot-grid snapshot-grid--compact">
                  <div>
                    <dt>Job ID</dt>
                    <dd>{selectedJob.job_id}</dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>{statusLabel(selectedJob)}</dd>
                  </div>
                  <div>
                    <dt>Task ID</dt>
                    <dd>{selectedJob.task_id ?? "Not assigned"}</dd>
                  </div>
                  <div>
                    <dt>Request ID</dt>
                    <dd>{selectedJob.request_id ?? "Not linked"}</dd>
                  </div>
                  <div>
                    <dt>Started</dt>
                    <dd>{formatDate(selectedJob.started_at)}</dd>
                  </div>
                  <div>
                    <dt>Completed</dt>
                    <dd>{formatDate(selectedJob.completed_at)}</dd>
                  </div>
                  <div>
                    <dt>Source</dt>
                    <dd>{summarizeConnection(selectedJob.source_connection)}</dd>
                  </div>
                  <div>
                    <dt>Target</dt>
                    <dd>{summarizeConnection(selectedJob.target_connection)}</dd>
                  </div>
                  <div>
                    <dt>Directory</dt>
                    <dd>{selectedJob.options.directory_object}</dd>
                  </div>
                  <div>
                    <dt>Storage</dt>
                    <dd>{storageLabel(selectedJob.options.storage_type)}</dd>
                  </div>
                  <div>
                    <dt>Transfer Dump</dt>
                    <dd>{selectedJob.options.transfer_dump_files ? "Yes" : "No"}</dd>
                  </div>
                  <div>
                    <dt>Object Storage</dt>
                    <dd>{summarizeObjectStorage(selectedJob.options.object_storage)}</dd>
                  </div>
                  <div>
                    <dt>Dump / Log</dt>
                    <dd>
                      {selectedJob.options.dump_file}
                      {" / "}
                      {selectedJob.options.log_file ?? "auto-generated"}
                    </dd>
                  </div>
                </dl>

                {selectedJob.command_preview ? (
                  <>
                    <div className="section-heading report-preview__heading">
                      <h2>Command Preview</h2>
                    </div>
                    <p className="field-helper field-helper--standalone">
                      Backend: <strong>{backendLabel(selectedJob.command_preview.backend)}</strong>
                    </p>
                    <pre className="runbook-code-block">
                      <code>{selectedJob.command_preview.command_line}</code>
                    </pre>
                    <pre className="runbook-code-block">
                      <code>{selectedJob.command_preview.parameter_lines.join("\n")}</code>
                    </pre>
                  </>
                ) : null}

                {selectedJob.output_excerpt.length > 0 ? (
                  <>
                    <div className="section-heading report-preview__heading">
                      <h2>Worker Output Tail</h2>
                      {selectedJob.output_log.length > selectedJob.output_excerpt.length ? (
                        <p>
                          Showing the short tail here. Use the full log section below for the
                          complete execution details.
                        </p>
                      ) : null}
                    </div>
                    <pre className="runbook-code-block">
                      <code>{selectedJob.output_excerpt.join("\n")}</code>
                    </pre>
                  </>
                ) : null}

                {selectedJob.output_log.length > 0 ? (
                  <>
                    <div className="section-heading report-preview__heading">
                      <h2>Complete Job Log</h2>
                      <p>Open the full execution log captured by the app for this job.</p>
                    </div>
                    <div className="form-actions">
                      <button
                        className="secondary-button"
                        type="button"
                        onClick={() => setShowFullLog((current) => !current)}
                      >
                        {showFullLog ? "Hide Full Log" : "Show Full Log"}
                      </button>
                    </div>
                    {showFullLog ? (
                      <pre className="runbook-code-block">
                        <code>{selectedJob.output_log.join("\n")}</code>
                      </pre>
                    ) : null}
                  </>
                ) : null}

                {selectedJob.oracle_log_lines.length > 0 ? (
                  <>
                    <div className="section-heading report-preview__heading">
                      <h2>Oracle Data Pump Log</h2>
                      <p>
                        These are the log entries read back from the Oracle DIRECTORY object for
                        this job.
                      </p>
                    </div>
                    <pre className="runbook-code-block">
                      <code>{selectedJob.oracle_log_lines.join("\n")}</code>
                    </pre>
                  </>
                ) : null}

                {selectedJob.error_message ? (
                  <div className="form-alert form-alert--error">
                    <strong>Execution error</strong>
                    <p>{selectedJob.error_message}</p>
                  </div>
                ) : null}

                {selectedJob.artifact_paths.length > 0 ? (
                  <>
                    <div className="section-heading report-preview__heading">
                      <h2>Artifacts</h2>
                    </div>
                    <ul className="bullet-list">
                      {selectedJob.artifact_paths.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </>
                ) : null}
              </section>
            ) : null}
          </section>
        </div>
      ) : null}
    </AppFrame>
  );
}
