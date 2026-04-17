import type { FormEvent, ReactNode } from "react";
import { useState } from "react";

import { MigrationReadinessSummary } from "../../components/MigrationReadinessSummary";
import { api, ApiError } from "../../services/api";
import type {
  MetadataEnrichmentSummary,
  MigrationCompatibilityAssessment,
  MigrationCreate,
} from "../../types";
import { defaultMigrationForm } from "./defaults";
import type { MigrationFormValues } from "./formModel";
import {
  MIGRATION_SCOPE_OPTIONS,
  ORACLE_CHARACTER_SET_OPTIONS,
  ORACLE_VERSION_OPTIONS,
  SOURCE_PLATFORM_OPTIONS,
  STORAGE_OPTIONS,
  TARGET_PLATFORM_OPTIONS,
} from "./options";
import { toMigrationCreate } from "./formModel";
import {
  validateMigrationFormWithOptions,
  validateSourceConnectionForm,
  validateTargetConnectionForm,
} from "./validation";

interface MigrationIntakeFormProps {
  onSubmit: (payload: MigrationCreate) => Promise<void>;
  isSubmitting: boolean;
  errorMessage: string | null;
  errorAction?: ReactNode;
}

type ConnectionKey = "source_connection" | "target_connection";
type IntakeStepId =
  | "foundation"
  | "constraints"
  | "connections"
  | "review";

function toNumber(value: string): number {
  if (value.trim() === "") {
    return 0;
  }

  return Number(value);
}

function statusBadgeClass(
  status: "success" | "warning" | "neutral",
): string {
  if (status === "success") {
    return "soft-badge soft-badge--success";
  }
  if (status === "warning") {
    return "soft-badge soft-badge--warning";
  }
  return "soft-badge soft-badge--neutral";
}

function feasibilityBadgeClass(
  status: MigrationCompatibilityAssessment["status"] | null,
): string {
  if (status === "MIGRATABLE") {
    return "soft-badge soft-badge--success";
  }
  if (status === "CONDITIONALLY_MIGRATABLE") {
    return "soft-badge soft-badge--warning";
  }
  if (status === "NOT_MIGRATABLE" || status === "FAILED") {
    return "soft-badge soft-badge--warning";
  }
  return "soft-badge";
}

function validationCheckTone(status: string | null | undefined): "success" | "warning" | "danger" | "neutral" {
  const normalized = status?.trim().toUpperCase() ?? "";
  if (normalized === "PASS" || normalized === "CONNECTED" || normalized === "READY") {
    return "success";
  }
  if (normalized === "FAIL" || normalized === "FAILED" || normalized === "NOT_MIGRATABLE") {
    return "danger";
  }
  if (normalized === "WARN" || normalized === "WARNING" || normalized === "CONDITIONALLY_MIGRATABLE") {
    return "warning";
  }
  return "neutral";
}

function validationCheckBadgeClass(status: string | null | undefined): string {
  const tone = validationCheckTone(status);
  if (tone === "success") {
    return "soft-badge soft-badge--success";
  }
  if (tone === "danger") {
    return "soft-badge soft-badge--danger";
  }
  if (tone === "warning") {
    return "soft-badge soft-badge--warning";
  }
  return "soft-badge soft-badge--neutral";
}

function validationSnapshotClass(status: string | null | undefined): string {
  const tone = validationCheckTone(status);
  if (tone === "success") {
    return "validation-snapshot validation-snapshot--success";
  }
  if (tone === "danger") {
    return "validation-snapshot validation-snapshot--danger";
  }
  if (tone === "warning") {
    return "validation-snapshot validation-snapshot--warning";
  }
  return "validation-snapshot";
}

function validationRowClass(status: string | null | undefined): string {
  const tone = validationCheckTone(status);
  if (tone === "success") {
    return "results-table__row--success";
  }
  if (tone === "danger") {
    return "results-table__row--danger";
  }
  if (tone === "warning") {
    return "results-table__row--warning";
  }
  return "";
}

function findValidationCheckStatus(
  assessment: MigrationCompatibilityAssessment,
  ...keywords: string[]
): string | null {
  const normalizedKeywords = keywords.map((item) => item.toLowerCase());
  const match = assessment.checks.find((check) => {
    const haystack = `${check.code} ${check.label}`.toLowerCase();
    return normalizedKeywords.every((keyword) => haystack.includes(keyword));
  });
  return match?.status ?? null;
}

function formatOptionalValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "Not provided";
  }

  return String(value);
}

export function MigrationIntakeForm({
  onSubmit,
  isSubmitting,
  errorMessage,
  errorAction,
}: MigrationIntakeFormProps) {
  const [form, setForm] = useState<MigrationFormValues>(defaultMigrationForm);
  const [currentStep, setCurrentStep] = useState<IntakeStepId>("foundation");
  const [targetValidationEnabled, setTargetValidationEnabled] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [isTestingConnection, setIsTestingConnection] = useState(false);
  const [isValidatingMigration, setIsValidatingMigration] = useState(false);
  const [isUploadingMetadataHtml, setIsUploadingMetadataHtml] = useState(false);
  const [selectedMetadataHtmlFile, setSelectedMetadataHtmlFile] =
    useState<File | null>(null);
  const [metadataTestResult, setMetadataTestResult] =
    useState<MetadataEnrichmentSummary | null>(null);
  const [metadataTestError, setMetadataTestError] = useState<string | null>(null);
  const [metadataInputMode, setMetadataInputMode] =
    useState<"live" | "html" | null>(null);
  const [migrationValidationResult, setMigrationValidationResult] =
    useState<MigrationCompatibilityAssessment | null>(null);
  const [migrationValidationError, setMigrationValidationError] =
    useState<string | null>(null);

  const resetValidationState = (preserveImportedMetadata = true) => {
    if (!(preserveImportedMetadata && metadataInputMode === "html")) {
      setMetadataTestResult(null);
      setMetadataTestError(null);
      setMetadataInputMode(null);
    }
    setMigrationValidationResult(null);
    setMigrationValidationError(null);
  };

  const hasImportedMetadata =
    metadataInputMode === "html" &&
    metadataTestResult !== null &&
    metadataTestResult.status !== "FAILED";

  const resolvedSourceMetadata =
    migrationValidationResult?.source ?? metadataTestResult?.source ?? null;
  const resolvedTargetMetadata = migrationValidationResult?.target ?? null;
  const sourceConnectionCheckStatus = migrationValidationResult
    ? findValidationCheckStatus(migrationValidationResult, "source", "connection") ??
      migrationValidationResult.source_connection_status
    : null;
  const targetConnectionCheckStatus = migrationValidationResult
    ? findValidationCheckStatus(migrationValidationResult, "target", "connection") ??
      migrationValidationResult.target_connection_status
    : null;
  const sourceVersionCheckStatus = migrationValidationResult
    ? findValidationCheckStatus(migrationValidationResult, "source", "version")
    : null;
  const targetVersionCheckStatus = migrationValidationResult
    ? findValidationCheckStatus(migrationValidationResult, "target", "version")
    : null;
  const sourceDeploymentCheckStatus = migrationValidationResult
    ? findValidationCheckStatus(migrationValidationResult, "source", "deployment")
    : null;
  const targetDeploymentCheckStatus = migrationValidationResult
    ? findValidationCheckStatus(migrationValidationResult, "target", "deployment")
    : null;
  const sourceCharsetCheckStatus = migrationValidationResult
    ? findValidationCheckStatus(migrationValidationResult, "source", "character")
    : null;
  const targetCharsetCheckStatus = migrationValidationResult
    ? findValidationCheckStatus(migrationValidationResult, "target", "character")
    : null;
  const targetGlobalNameCheckStatus = migrationValidationResult
    ? findValidationCheckStatus(migrationValidationResult, "global", "name")
    : null;
  const targetRoleCheckStatus = migrationValidationResult
    ? findValidationCheckStatus(migrationValidationResult, "target", "role")
    : null;

  const hasVerifiedMigration =
    !form.metadata_collection.enabled ||
    (metadataTestResult !== null && metadataTestResult.status !== "FAILED") ||
    migrationValidationResult?.source_connection_status === "CONNECTED";

  const intakeSteps: {
    id: IntakeStepId;
    title: string;
    description: string;
    complete: boolean;
  }[] = [
    {
      id: "foundation",
      title: "Foundation",
      description: "Scope, sizing, and platform profile",
      complete:
        form.source.database_size_gb > 0 &&
        form.business.downtime_window_minutes > 0 &&
        Boolean(form.source.oracle_version) &&
        Boolean(form.target.oracle_version),
    },
    {
      id: "constraints",
      title: "Constraints",
      description: "Business, topology, and migration signals",
      complete:
        form.connectivity.network_bandwidth_mbps > 0 &&
        form.scope.schema_count > 0,
    },
    {
      id: "connections",
      title: "Connections",
      description: "Source test, HTML import, and optional target validation",
      complete: hasVerifiedMigration,
    },
    {
      id: "review",
      title: "Review",
      description: "Final checks before generating recommendation",
      complete:
        validationErrors.length === 0 &&
        (!targetValidationEnabled || migrationValidationResult !== null),
    },
  ];

  const setTextField = <
    TSection extends keyof MigrationFormValues,
    TKey extends keyof MigrationFormValues[TSection],
  >(
    section: TSection,
    key: TKey,
    value: string,
  ) => {
    resetValidationState();
    setForm((current) => ({
      ...current,
      [section]: {
        ...(current[section] as object),
        [key]: value,
      },
    }));
  };

  const setNumberField = <
    TSection extends keyof MigrationFormValues,
    TKey extends keyof MigrationFormValues[TSection],
  >(
    section: TSection,
    key: TKey,
    value: string,
  ) => {
    resetValidationState();
    setForm((current) => ({
      ...current,
      [section]: {
        ...(current[section] as object),
        [key]: toNumber(value),
      },
    }));
  };

  const setBooleanField = <
    TSection extends keyof MigrationFormValues,
    TKey extends keyof MigrationFormValues[TSection],
  >(
    section: TSection,
    key: TKey,
    checked: boolean,
  ) => {
    resetValidationState();
    setForm((current) => ({
      ...current,
      [section]: {
        ...(current[section] as object),
        [key]: checked,
      },
    }));
  };

  const setMetadataField = <
    TKey extends keyof MigrationFormValues["metadata_collection"],
  >(
    key: TKey,
    value: MigrationFormValues["metadata_collection"][TKey],
  ) => {
    resetValidationState();
    setForm((current) => ({
      ...current,
      metadata_collection: {
        ...current.metadata_collection,
        [key]: value,
      },
    }));
  };

  const setMetadataConnectionField = <
    TKey extends keyof MigrationFormValues["metadata_collection"]["source_connection"],
  >(
    connectionKey: ConnectionKey,
    key: TKey,
    value: MigrationFormValues["metadata_collection"]["source_connection"][TKey],
  ) => {
    resetValidationState();
    setForm((current) => ({
      ...current,
      metadata_collection: {
        ...current.metadata_collection,
        [connectionKey]: {
          ...current.metadata_collection[connectionKey],
          [key]: value,
        },
      },
    }));
  };

  const handleTestConnection = async () => {
    setMetadataTestError(null);
    setMetadataTestResult(null);
    setMetadataInputMode(null);

    const metadataErrors = validateSourceConnectionForm(form);
    if (metadataErrors.length > 0) {
      setMetadataTestError(metadataErrors.join(" "));
      return;
    }

    try {
      setIsTestingConnection(true);
      const payload = toMigrationCreate(form);
      if (payload.metadata_collection) {
        payload.metadata_collection = {
          ...payload.metadata_collection,
          target_connection: null,
        };
      }
      const result = await api.testSourceMetadataConnection(payload);
      setMetadataTestResult(result);
      setMetadataInputMode("live");
    } catch (error) {
      if (error instanceof ApiError) {
        setMetadataTestError(error.message);
      } else {
        setMetadataTestError("Unable to test the source database connection right now.");
      }
    } finally {
      setIsTestingConnection(false);
    }
  };

  const handleImportMetadataHtml = async () => {
    setMetadataTestError(null);
    setMetadataTestResult(null);
    setMetadataInputMode(null);

    if (!selectedMetadataHtmlFile) {
      setMetadataTestError("Select a source metadata HTML file before uploading.");
      return;
    }

    try {
      setIsUploadingMetadataHtml(true);
      const result = await api.importSourceMetadataHtml(selectedMetadataHtmlFile);
      setMetadataTestResult(result);
      setMetadataInputMode("html");
    } catch (error) {
      if (error instanceof ApiError) {
        setMetadataTestError(error.message);
      } else {
        setMetadataTestError("Unable to import the source metadata HTML report right now.");
      }
    } finally {
      setIsUploadingMetadataHtml(false);
    }
  };

  const handleValidateMigration = async () => {
    setMigrationValidationError(null);
    setMigrationValidationResult(null);

    if (!targetValidationEnabled) {
      setMigrationValidationError(
        "Enable target validation first, then enter target connection details to compare source and target databases.",
      );
      return;
    }

    if (metadataInputMode === "html") {
      setMigrationValidationError(
        "Source-to-target validation still requires a live source connection. The uploaded HTML report can be used for assessment and report generation when the source database is unreachable.",
      );
      return;
    }

    const metadataErrors = [
      ...validateSourceConnectionForm(form),
      ...validateTargetConnectionForm(form, true),
    ];
    if (metadataErrors.length > 0) {
      setMigrationValidationError(metadataErrors.join(" "));
      return;
    }

    try {
      setIsValidatingMigration(true);
      const result = await api.validateMigration(toMigrationCreate(form));
      setMigrationValidationResult(result);
      if (result.source) {
        setMetadataInputMode("live");
        setMetadataTestResult({
          status:
            result.status === "FAILED"
              ? "FAILED"
              : "COLLECTED",
          source: result.source,
          collected_fields: [],
          applied_fields: [],
          errors: [],
          notes: [],
        });
      }
    } catch (error) {
      if (error instanceof ApiError) {
        setMigrationValidationError(error.message);
      } else {
        setMigrationValidationError(
          "Unable to validate the source and target databases right now.",
        );
      }
    } finally {
      setIsValidatingMigration(false);
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const errors = validateMigrationFormWithOptions(form, {
      allowImportedSourceMetadata: hasImportedMetadata,
    });
    if (form.metadata_collection.enabled && !hasVerifiedMigration) {
      errors.push(
        "Test the source database connection successfully or import a source metadata HTML report before submitting the assessment.",
      );
    }
    setValidationErrors(errors);
    if (errors.length > 0) {
      return;
    }

    const payload = toMigrationCreate(form);
    payload.source_metadata =
      migrationValidationResult?.source ?? metadataTestResult?.source ?? null;
    if (migrationValidationResult?.target) {
      payload.target_metadata = migrationValidationResult.target;
    }
    if (migrationValidationResult) {
      payload.migration_validation = migrationValidationResult;
    }

    await onSubmit(payload);
  };

  const scrollToMetadataCollection = () => {
    document
      .getElementById("source-metadata-collection")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const scrollToStep = (stepId: IntakeStepId) => {
    setCurrentStep(stepId);
    document
      .getElementById(`intake-step-${stepId}`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const currentStepIndex = intakeSteps.findIndex((step) => step.id === currentStep);

  const moveStep = (direction: -1 | 1) => {
    const nextStep = intakeSteps[currentStepIndex + direction];
    if (nextStep) {
      scrollToStep(nextStep.id);
    }
  };

  const renderConnectionFields = (
    title: string,
    description: string,
    connectionKey: ConnectionKey,
    hostPlaceholder: string,
    servicePlaceholder: string,
    passwordPlaceholder: string,
  ) => {
    const connection = form.metadata_collection[connectionKey];

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
              value={connection.host}
              onChange={(event) =>
                setMetadataConnectionField(connectionKey, "host", event.target.value)
              }
              placeholder={hostPlaceholder}
              disabled={!form.metadata_collection.enabled}
            />
          </label>

          <label className="field">
            <span>Listener Port</span>
            <input
              type="number"
              min="1"
              value={connection.port}
              onChange={(event) =>
                setMetadataConnectionField(
                  connectionKey,
                  "port",
                  toNumber(event.target.value),
                )
              }
              disabled={!form.metadata_collection.enabled}
            />
          </label>

          <label className="field">
            <span>Service Name</span>
            <input
              value={connection.service_name}
              onChange={(event) =>
                setMetadataConnectionField(
                  connectionKey,
                  "service_name",
                  event.target.value,
                )
              }
              placeholder={servicePlaceholder}
              disabled={!form.metadata_collection.enabled}
            />
          </label>

          <label className="field">
            <span>Username</span>
            <input
              value={connection.username}
              onChange={(event) =>
                setMetadataConnectionField(
                  connectionKey,
                  "username",
                  event.target.value,
                )
              }
              placeholder="system"
              disabled={!form.metadata_collection.enabled}
            />
          </label>

          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={connection.password}
              onChange={(event) =>
                setMetadataConnectionField(
                  connectionKey,
                  "password",
                  event.target.value,
                )
              }
              placeholder={passwordPlaceholder}
              disabled={!form.metadata_collection.enabled}
            />
          </label>

          <label className="field">
            <span>Connection Mode</span>
            <select
              value={connection.mode}
              onChange={(event) =>
                setMetadataConnectionField(
                  connectionKey,
                  "mode",
                  event.target.value as "thin" | "thick",
                )
              }
              disabled={!form.metadata_collection.enabled}
            >
              <option value="thin">Thin</option>
              <option value="thick">Thick</option>
            </select>
          </label>

          <label className="field">
            <span>Wallet Location (optional)</span>
            <input
              value={connection.wallet_location}
              onChange={(event) =>
                setMetadataConnectionField(
                  connectionKey,
                  "wallet_location",
                  event.target.value,
                )
              }
              placeholder="/opt/oracle/wallet"
              disabled={!form.metadata_collection.enabled}
            />
          </label>

          <div className="field checkbox-field">
            <span>Privilege Mode</span>
            <label className="checkbox-inline">
              <input
                type="checkbox"
                checked={connection.sysdba}
                onChange={(event) =>
                  setMetadataConnectionField(
                    connectionKey,
                    "sysdba",
                    event.target.checked,
                  )
                }
                disabled={!form.metadata_collection.enabled}
              />{" "}
              Connect as SYSDBA
            </label>
          </div>
        </div>
      </section>
    );
  };

  return (
    <form className="intake-layout" onSubmit={handleSubmit}>
      <section className="panel panel--form">
        <div className="section-heading">
          <h2>Migration Intake</h2>
          <p>Capture source, target, downtime, and tooling signals used for the recommendation.</p>
        </div>

        <div className="panel panel--inner intake-stepper">
          <div className="section-heading">
            <h2>Guided Workflow</h2>
            <p>Work through the assessment in order, then submit once the source is verified.</p>
          </div>
          <div className="intake-stepper__grid">
            {intakeSteps.map((step) => (
              <button
                key={step.id}
                className={`intake-stepper__button${
                  currentStep === step.id ? " intake-stepper__button--active" : ""
                }`}
                type="button"
                onClick={() => scrollToStep(step.id)}
              >
                <span className="intake-stepper__title">{step.title}</span>
                <small>{step.description}</small>
                <span
                  className={statusBadgeClass(step.complete ? "success" : "warning")}
                >
                  {step.complete ? "Ready" : "Pending"}
                </span>
              </button>
            ))}
          </div>
          <div className="summary-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={() => moveStep(-1)}
              disabled={currentStepIndex <= 0}
            >
              Previous Step
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={() => moveStep(1)}
              disabled={currentStepIndex >= intakeSteps.length - 1}
            >
              Next Step
            </button>
          </div>
        </div>

        {validationErrors.length > 0 ? (
          <div className="form-alert" role="alert">
            <strong>Resolve the highlighted gaps before submitting.</strong>
            <ul>
              {validationErrors.map((error) => (
                <li key={error}>{error}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {errorMessage ? (
          <div className="form-alert form-alert--error" role="alert">
            <strong>Recommendation request failed.</strong>
            <p>{errorMessage}</p>
            {errorAction ? <div className="form-alert__action">{errorAction}</div> : null}
          </div>
        ) : null}

        <div className="panel panel--inner">
          <div className="section-heading">
            <h2>Connection Validation</h2>
            <p>
              Use the source test and source-to-target validation before submit so the app can
              prove connectivity and decide whether the databases are migration-ready.
            </p>
          </div>
          <div className="summary-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={scrollToMetadataCollection}
            >
              Open Connection Section
            </button>
            <span
              className={statusBadgeClass(
                !form.metadata_collection.enabled
                  ? "neutral"
                  : hasVerifiedMigration
                    ? "success"
                    : "warning",
              )}
            >
              {!form.metadata_collection.enabled
                ? "Connection validation is off"
                : hasVerifiedMigration
                  ? metadataInputMode === "html"
                    ? "Source metadata imported"
                    : "Source connection validated"
                  : "Source validation required before submit"}
            </span>
          </div>
        </div>

        <section id="intake-step-foundation" className="report-preview__heading">
          <div className="section-heading">
            <h2>Step 1: Foundation</h2>
            <p>
              Provide the base profile first. These values drive the first migration strategy
              shortlist even before live metadata is collected.
            </p>
          </div>
        </section>

        <div className="form-grid">
          <label className="field">
            <span>Request ID (optional)</span>
            <input
              value={form.request_id ?? ""}
              onChange={(event) => setForm((current) => ({ ...current, request_id: event.target.value }))}
              placeholder="MIG-2026-Q2-APP01"
            />
          </label>

          <label className="field">
            <span>Migration Scope</span>
            <select
              value={form.scope.migration_scope}
              onChange={(event) => setTextField("scope", "migration_scope", event.target.value)}
            >
              {MIGRATION_SCOPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Source Oracle Version</span>
            <select
              value={form.source.oracle_version}
              onChange={(event) => setTextField("source", "oracle_version", event.target.value)}
            >
              {ORACLE_VERSION_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Target Oracle Version</span>
            <select
              value={form.target.oracle_version}
              onChange={(event) => setTextField("target", "oracle_version", event.target.value)}
            >
              {ORACLE_VERSION_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Source Platform</span>
            <select
              value={form.source.platform}
              onChange={(event) => setTextField("source", "platform", event.target.value)}
            >
              {SOURCE_PLATFORM_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Target Platform</span>
            <select
              value={form.target.platform}
              onChange={(event) => setTextField("target", "platform", event.target.value)}
            >
              {TARGET_PLATFORM_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Source Storage</span>
            <select
              value={form.source.storage_type}
              onChange={(event) => setTextField("source", "storage_type", event.target.value)}
            >
              {STORAGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Target Storage</span>
            <select
              value={form.target.storage_type}
              onChange={(event) => setTextField("target", "storage_type", event.target.value)}
            >
              {STORAGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Database Size (GB)</span>
            <input
              type="number"
              min="0"
              value={form.source.database_size_gb}
              onChange={(event) => setNumberField("source", "database_size_gb", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Largest Table (GB)</span>
            <input
              type="number"
              min="0"
              value={form.source.largest_table_gb}
              onChange={(event) => setNumberField("source", "largest_table_gb", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Daily Change Rate (GB)</span>
            <input
              type="number"
              min="0"
              value={form.source.daily_change_rate_gb}
              onChange={(event) => setNumberField("source", "daily_change_rate_gb", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Peak Redo (MB/sec)</span>
            <input
              type="number"
              min="0"
              value={form.source.peak_redo_mb_per_sec}
              onChange={(event) => setNumberField("source", "peak_redo_mb_per_sec", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Schema Count</span>
            <input
              type="number"
              min="0"
              value={form.scope.schema_count}
              onChange={(event) => setNumberField("scope", "schema_count", event.target.value)}
            />
          </label>

          {form.scope.migration_scope === "SCHEMA" ? (
            <label className="field">
              <span>Schema Names</span>
              <input
                value={form.scope.schema_names}
                onChange={(event) => setTextField("scope", "schema_names", event.target.value)}
                placeholder="HR, FINANCE, PMSADMIN"
              />
            </label>
          ) : null}

          <label className="field">
            <span>Downtime Window (minutes)</span>
            <input
              type="number"
              min="0"
              value={form.business.downtime_window_minutes}
              onChange={(event) => setNumberField("business", "downtime_window_minutes", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Network Bandwidth (Mbps)</span>
            <input
              type="number"
              min="0"
              value={form.connectivity.network_bandwidth_mbps}
              onChange={(event) => setNumberField("connectivity", "network_bandwidth_mbps", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Character Set</span>
            <input
              list="oracle-character-set-options"
              value={form.source.character_set}
              onChange={(event) => setTextField("source", "character_set", event.target.value)}
              placeholder="AL32UTF8"
            />
            <datalist id="oracle-character-set-options">
              {ORACLE_CHARACTER_SET_OPTIONS.map((characterSet) => (
                <option key={characterSet} value={characterSet} />
              ))}
            </datalist>
            <small className="field-helper">
              Oracle character set identifiers are preloaded for quick selection.
            </small>
          </label>
        </div>

        <section
          className="panel panel--inner"
          id="source-metadata-collection"
        >
          <div id="intake-step-connections" className="section-heading">
            <h2>Step 2: Connections</h2>
            <p>
              Test the source before submit. Target validation stays optional and is used only
              when you want a direct source-to-target compatibility verdict.
            </p>
          </div>

          <div className="summary-actions">
            <span
              className={statusBadgeClass(
                !form.metadata_collection.enabled
                  ? "neutral"
                  : hasVerifiedMigration
                    ? "success"
                    : "warning",
              )}
            >
              {!form.metadata_collection.enabled
                ? "Live discovery disabled"
                : hasVerifiedMigration
                  ? metadataInputMode === "html"
                    ? "HTML metadata imported"
                    : "Source discovery ready"
                  : "Test source connection before submit"}
            </span>
            <span
              className={statusBadgeClass(
                targetValidationEnabled && migrationValidationResult
                  ? "success"
                  : targetValidationEnabled
                    ? "warning"
                    : "neutral",
              )}
            >
              {!targetValidationEnabled
                ? "Target validation optional"
                : migrationValidationResult
                  ? "Target comparison captured"
                  : "Target details entered but not validated"}
            </span>
          </div>

          <div className="field-helper field-helper--standalone">
            Why this matters: the app can replace manual estimates with discovered Oracle values
            and can confirm whether the target landing zone is actually compatible.
          </div>

          <div className="section-heading">
            <h2>Source And Target Connection Validation</h2>
            <p>
              Enable this to collect source metadata. Target connection details are optional and
              are used only when you want source-to-target compatibility validation.
            </p>
          </div>

          <div className="toggle-inline">
            <label>
              <input
                type="checkbox"
                checked={form.metadata_collection.enabled}
                onChange={(event) =>
                  setMetadataField("enabled", event.target.checked)
                }
              />{" "}
              Collect metadata directly from source database
            </label>
            <label>
              <input
                type="checkbox"
                checked={form.metadata_collection.prefer_collected_values}
                onChange={(event) =>
                  setMetadataField("prefer_collected_values", event.target.checked)
                }
                disabled={!form.metadata_collection.enabled}
              />{" "}
              Prefer collected values over manual inputs
            </label>
            <label>
              <input
                type="checkbox"
                checked={targetValidationEnabled}
                onChange={(event) => {
                  setTargetValidationEnabled(event.target.checked);
                  setMigrationValidationError(null);
                  setMigrationValidationResult(null);
                }}
                disabled={!form.metadata_collection.enabled}
              />{" "}
              Validate against target database
            </label>
          </div>

          <div className="summary-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={() => void handleTestConnection()}
              disabled={!form.metadata_collection.enabled || isTestingConnection}
            >
              {isTestingConnection ? "Validating Source..." : "Validate Source"}
            </button>
            <button
              className="primary-button"
              type="button"
              onClick={() => void handleValidateMigration()}
              disabled={
                !form.metadata_collection.enabled ||
                !targetValidationEnabled ||
                isValidatingMigration
              }
            >
              {isValidatingMigration
                ? "Validating Source And Target..."
                : "Validate Source To Target Migration"}
            </button>
            {form.metadata_collection.enabled ? (
              <span className={feasibilityBadgeClass(migrationValidationResult?.status ?? null)}>
                {migrationValidationResult
                  ? migrationValidationResult.status.replace(/_/g, " ")
                  : "Target validation optional"}
              </span>
            ) : null}
          </div>

          <section className="panel panel--inner">
            <div className="section-heading">
              <h2>HTML Import Fallback</h2>
              <p>
                If live source connectivity is unavailable, upload a source metadata HTML report
                and use that imported discovery data to generate the assessment report.
              </p>
            </div>
            <div className="form-grid form-grid--metadata">
              <label className="field">
                <span>Source Metadata HTML File</span>
                <input
                  type="file"
                  accept=".html,.htm,text/html"
                  onChange={(event) => {
                    setSelectedMetadataHtmlFile(event.target.files?.[0] ?? null);
                    setMetadataTestError(null);
                  }}
                  disabled={!form.metadata_collection.enabled || isUploadingMetadataHtml}
                />
                <small className="field-helper">
                  {selectedMetadataHtmlFile
                    ? `Selected file: ${selectedMetadataHtmlFile.name}`
                    : "Upload the Oracle metadata HTML report when the source database cannot be reached directly."}
                </small>
              </label>
            </div>
            <div className="summary-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() => void handleImportMetadataHtml()}
                disabled={
                  !form.metadata_collection.enabled ||
                  !selectedMetadataHtmlFile ||
                  isUploadingMetadataHtml
                }
              >
                {isUploadingMetadataHtml ? "Importing HTML..." : "Import HTML Metadata"}
              </button>
              {metadataInputMode === "html" && metadataTestResult?.status !== "FAILED" ? (
                <span className={statusBadgeClass("success")}>
                  HTML metadata ready for submit
                </span>
              ) : null}
            </div>
          </section>

          {metadataTestError ? (
            <div className="form-alert form-alert--error" role="alert">
              <strong>Source metadata step failed.</strong>
              <p>{metadataTestError}</p>
            </div>
          ) : null}

          {migrationValidationError ? (
            <div className="form-alert form-alert--error" role="alert">
              <strong>Source-to-target validation failed.</strong>
              <p>{migrationValidationError}</p>
            </div>
          ) : null}

          {metadataTestResult?.source ? (
            <div
              className={`form-alert ${
                metadataTestResult.status === "FAILED"
                  ? "form-alert--error"
                  : "form-alert--success"
              }`}
              role="status"
            >
              <strong>
                {metadataInputMode === "html"
                  ? "Imported source metadata status"
                  : "Source metadata test status"}
                : {metadataTestResult.status}
              </strong>
              {metadataInputMode === "html" ? (
                <p>
                  The uploaded HTML report was parsed and its source discovery details will be
                  attached to the assessment when you submit.
                </p>
              ) : null}
              <dl className="snapshot-grid snapshot-grid--compact">
                <div>
                  <dt>Version</dt>
                  <dd>{metadataTestResult.source.oracle_version ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Deployment</dt>
                  <dd>{metadataTestResult.source.deployment_type ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Database Size</dt>
                  <dd>{metadataTestResult.source.database_size_gb ?? "Not available"} GB</dd>
                </div>
                <div>
                  <dt>Platform</dt>
                  <dd>{metadataTestResult.source.platform ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Character Set</dt>
                  <dd>{metadataTestResult.source.character_set ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>PDBs</dt>
                  <dd>{metadataTestResult.source.pdbs.length || "Not available"}</dd>
                </div>
              </dl>
              {metadataTestResult.notes.length > 0 ? (
                <ul className="bullet-list">
                  {metadataTestResult.notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {migrationValidationResult ? (
            <div
              className={`form-alert ${
                migrationValidationResult.status === "MIGRATABLE"
                  ? "form-alert--success"
                  : migrationValidationResult.status === "FAILED" ||
                      migrationValidationResult.status === "NOT_MIGRATABLE"
                    ? "form-alert--error"
                    : ""
              }`}
              role="status"
            >
              <strong>
                Migration validation status:{" "}
                {migrationValidationResult.status.replace(/_/g, " ")}
              </strong>
              <p>{migrationValidationResult.summary}</p>

              <dl className="snapshot-grid snapshot-grid--compact">
                <div className={validationSnapshotClass(sourceConnectionCheckStatus)}>
                  <dt>Source Connection</dt>
                  <dd>
                    <span className={validationCheckBadgeClass(sourceConnectionCheckStatus)}>
                      {migrationValidationResult.source_connection_status}
                    </span>
                  </dd>
                </div>
                <div className={validationSnapshotClass(targetConnectionCheckStatus)}>
                  <dt>Target Connection</dt>
                  <dd>
                    <span className={validationCheckBadgeClass(targetConnectionCheckStatus)}>
                      {migrationValidationResult.target_connection_status}
                    </span>
                  </dd>
                </div>
                <div className={validationSnapshotClass(sourceVersionCheckStatus)}>
                  <dt>Source Version</dt>
                  <dd>{migrationValidationResult.source?.oracle_version ?? "Not available"}</dd>
                </div>
                <div className={validationSnapshotClass(targetVersionCheckStatus)}>
                  <dt>Target Version</dt>
                  <dd>{migrationValidationResult.target?.oracle_version ?? "Not available"}</dd>
                </div>
                <div className={validationSnapshotClass(sourceDeploymentCheckStatus)}>
                  <dt>Source Deployment</dt>
                  <dd>{migrationValidationResult.source?.deployment_type ?? "Not available"}</dd>
                </div>
                <div className={validationSnapshotClass(targetDeploymentCheckStatus)}>
                  <dt>Target Deployment</dt>
                  <dd>{migrationValidationResult.target?.deployment_type ?? "Not available"}</dd>
                </div>
                <div className={validationSnapshotClass(sourceCharsetCheckStatus)}>
                  <dt>Source Character Set</dt>
                  <dd>{migrationValidationResult.source?.character_set ?? "Not available"}</dd>
                </div>
                <div className={validationSnapshotClass(targetCharsetCheckStatus)}>
                  <dt>Target Character Set</dt>
                  <dd>{migrationValidationResult.target?.character_set ?? "Not available"}</dd>
                </div>
                <div className={validationSnapshotClass(targetGlobalNameCheckStatus)}>
                  <dt>Target Global Name</dt>
                  <dd>{migrationValidationResult.target?.global_name ?? "Not available"}</dd>
                </div>
                <div className={validationSnapshotClass(targetRoleCheckStatus)}>
                  <dt>Target Role</dt>
                  <dd>{migrationValidationResult.target?.database_role ?? "Not available"}</dd>
                </div>
              </dl>

              {migrationValidationResult.checks.length > 0 ? (
                <div className="table-wrap">
                  <table className="results-table results-table--compact results-table--validation">
                    <thead>
                      <tr>
                        <th>Check</th>
                        <th>Status</th>
                        <th>Source</th>
                        <th>Target</th>
                        <th>Observation</th>
                      </tr>
                    </thead>
                    <tbody>
                      {migrationValidationResult.checks.map((check) => (
                        <tr key={check.code} className={validationRowClass(check.status)}>
                          <td>{check.label}</td>
                          <td>
                            <span className={validationCheckBadgeClass(check.status)}>
                              {check.status}
                            </span>
                          </td>
                          <td>{check.source_value ?? ""}</td>
                          <td>{check.target_value ?? ""}</td>
                          <td>{check.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}

              {migrationValidationResult.blockers.length > 0 ? (
                <ul className="bullet-list">
                  {migrationValidationResult.blockers.map((item) => (
                    <li key={item}>Blocker: {item}</li>
                  ))}
                </ul>
              ) : null}

              {migrationValidationResult.warnings.length > 0 ? (
                <ul className="bullet-list">
                  {migrationValidationResult.warnings.map((item) => (
                    <li key={item}>Warning: {item}</li>
                  ))}
                </ul>
              ) : null}

              <MigrationReadinessSummary assessment={migrationValidationResult} />
            </div>
          ) : null}

          {renderConnectionFields(
            "Source Oracle Connection",
            "Used to collect discovery details and the source-side inventory.",
            "source_connection",
            "source-db-host.example.com",
            "ORCLPDB1",
            "Enter source database password",
          )}

          {targetValidationEnabled
            ? renderConnectionFields(
                "Target Oracle Connection",
                "Used to verify the landing database and compare compatibility with the source.",
                "target_connection",
                "target-db-host.example.com",
                "TARGETPDB1",
                "Enter target database password",
              )
            : null}

          <p className="field-helper field-helper--standalone">
            Connection passwords are used only for runtime validation calls. Persisted assessment
            records store connection configuration without the passwords. Source connection is
            required only for live validation. You can upload a source metadata HTML file instead
            when the source database is unreachable. Target connection is optional and only needed
            for source-to-target compatibility validation.
          </p>
        </section>

        <section id="intake-step-constraints" className="report-preview__heading">
          <div className="section-heading">
            <h2>Step 3: Constraints And Signals</h2>
            <p>
              Confirm the business constraints and technical signals that can elevate or rule out
              Data Pump, RMAN, GoldenGate, ZDM, or standby-led approaches.
            </p>
          </div>
        </section>

        <div className="toggle-sections">
          <fieldset className="toggle-group">
            <legend>Source Traits</legend>
            <label><input type="checkbox" checked={form.source.tde_enabled} onChange={(event) => setBooleanField("source", "tde_enabled", event.target.checked)} /> TDE enabled</label>
            <label><input type="checkbox" checked={form.source.rac_enabled} onChange={(event) => setBooleanField("source", "rac_enabled", event.target.checked)} /> RAC enabled</label>
            <label><input type="checkbox" checked={form.source.dataguard_enabled} onChange={(event) => setBooleanField("source", "dataguard_enabled", event.target.checked)} /> Data Guard enabled</label>
            <label><input type="checkbox" checked={form.source.archivelog_enabled} onChange={(event) => setBooleanField("source", "archivelog_enabled", event.target.checked)} /> Archivelog enabled</label>
          </fieldset>

          <fieldset className="toggle-group">
            <legend>Scope and Business</legend>
            <label><input type="checkbox" checked={form.scope.need_schema_remap} onChange={(event) => setBooleanField("scope", "need_schema_remap", event.target.checked)} /> Schema remap required</label>
            <label><input type="checkbox" checked={form.scope.need_tablespace_remap} onChange={(event) => setBooleanField("scope", "need_tablespace_remap", event.target.checked)} /> Tablespace remap required</label>
            <label><input type="checkbox" checked={form.scope.need_reorg} onChange={(event) => setBooleanField("scope", "need_reorg", event.target.checked)} /> Reorganization required</label>
            <label><input type="checkbox" checked={form.scope.subset_only} onChange={(event) => setBooleanField("scope", "subset_only", event.target.checked)} /> Subset only</label>
            <label><input type="checkbox" checked={form.business.fallback_required} onChange={(event) => setBooleanField("business", "fallback_required", event.target.checked)} /> Fallback required</label>
            <label><input type="checkbox" checked={form.business.near_zero_downtime_required} onChange={(event) => setBooleanField("business", "near_zero_downtime_required", event.target.checked)} /> Near-zero downtime required</label>
            <label><input type="checkbox" checked={form.business.regulated_workload} onChange={(event) => setBooleanField("business", "regulated_workload", event.target.checked)} /> Regulated workload</label>
          </fieldset>

          <fieldset className="toggle-group">
            <legend>Connectivity and Features</legend>
            <label><input type="checkbox" checked={form.connectivity.direct_host_connectivity} onChange={(event) => setBooleanField("connectivity", "direct_host_connectivity", event.target.checked)} /> Direct host connectivity</label>
            <label><input type="checkbox" checked={form.connectivity.shared_storage_available} onChange={(event) => setBooleanField("connectivity", "shared_storage_available", event.target.checked)} /> Shared storage available</label>
            <label><input type="checkbox" checked={form.target.target_is_exadata} onChange={(event) => setBooleanField("target", "target_is_exadata", event.target.checked)} /> Target is Exadata</label>
            <label><input type="checkbox" checked={form.target.same_endian} onChange={(event) => setBooleanField("target", "same_endian", event.target.checked)} /> Same endian platform</label>
            <label><input type="checkbox" checked={form.features.need_version_upgrade} onChange={(event) => setBooleanField("features", "need_version_upgrade", event.target.checked)} /> Version upgrade needed</label>
            <label><input type="checkbox" checked={form.features.need_cross_platform_move} onChange={(event) => setBooleanField("features", "need_cross_platform_move", event.target.checked)} /> Cross-platform move</label>
            <label><input type="checkbox" checked={form.features.need_non_cdb_to_pdb_conversion} onChange={(event) => setBooleanField("features", "need_non_cdb_to_pdb_conversion", event.target.checked)} /> Non-CDB to PDB conversion</label>
            <label><input type="checkbox" checked={form.features.goldengate_license_available} onChange={(event) => setBooleanField("features", "goldengate_license_available", event.target.checked)} /> GoldenGate license available</label>
            <label><input type="checkbox" checked={form.features.zdm_supported_target} onChange={(event) => setBooleanField("features", "zdm_supported_target", event.target.checked)} /> ZDM supported target</label>
          </fieldset>
        </div>

        <section id="intake-step-review" className="panel panel--inner">
          <div className="section-heading">
            <h2>Step 4: Review Before Submit</h2>
            <p>
              Confirm that the request is complete and that the app will use the right collected
              source and target values in the recommendation.
            </p>
          </div>
          <dl className="snapshot-grid snapshot-grid--compact">
            <div>
              <dt>Source Validation</dt>
              <dd>
                {!form.metadata_collection.enabled
                  ? "Skipped"
                  : hasVerifiedMigration
                    ? metadataInputMode === "html"
                      ? "Imported from HTML"
                      : "Connected"
                    : "Pending"}
              </dd>
            </div>
            <div>
              <dt>Target Validation</dt>
              <dd>
                {!targetValidationEnabled
                  ? "Optional"
                  : migrationValidationResult
                    ? migrationValidationResult.status
                    : "Pending"}
              </dd>
            </div>
            <div>
              <dt>Resolved Source Version</dt>
              <dd>
                {resolvedSourceMetadata?.oracle_version ?? form.source.oracle_version}
              </dd>
            </div>
            <div>
              <dt>Resolved Source Size</dt>
              <dd>
                {formatOptionalValue(
                  resolvedSourceMetadata?.database_size_gb ?? form.source.database_size_gb,
                )}{" "}
                GB
              </dd>
            </div>
            <div>
              <dt>Resolved Target Version</dt>
              <dd>
                {resolvedTargetMetadata?.oracle_version ?? form.target.oracle_version}
              </dd>
            </div>
            <div>
              <dt>Recommendation Ready</dt>
              <dd>{hasVerifiedMigration ? "Yes" : "No"}</dd>
            </div>
          </dl>
        </section>

        <div className="form-actions">
          <button className="primary-button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Generating Recommendation..." : "Get Recommendation"}
          </button>
        </div>
      </section>

      <aside className="panel panel--sidebar">
        <div className="section-heading">
          <h2>Live Assessment Summary</h2>
          <p>
            This panel shows what the app will actually use for the recommendation, including
            discovered values when source metadata has already been collected.
          </p>
        </div>

        <dl className="snapshot-grid snapshot-grid--sidebar">
          <div>
            <dt>Source Status</dt>
            <dd>
              {!form.metadata_collection.enabled
                ? "Manual only"
                : hasVerifiedMigration
                  ? metadataInputMode === "html"
                    ? "Imported HTML"
                    : "Live metadata"
                  : "Pending"}
            </dd>
          </div>
          <div>
            <dt>Target Status</dt>
            <dd>
              {!targetValidationEnabled
                ? "Optional"
                : migrationValidationResult
                  ? migrationValidationResult.status
                  : "Awaiting validation"}
            </dd>
          </div>
          <div>
            <dt>Source Version</dt>
            <dd>{resolvedSourceMetadata?.oracle_version ?? form.source.oracle_version}</dd>
          </div>
          <div>
            <dt>Source Size</dt>
            <dd>
              {formatOptionalValue(
                resolvedSourceMetadata?.database_size_gb ?? form.source.database_size_gb,
              )}{" "}
              GB
            </dd>
          </div>
          <div>
            <dt>Downtime</dt>
            <dd>{form.business.downtime_window_minutes} minutes</dd>
          </div>
          <div>
            <dt>Primary Scope</dt>
            <dd>{form.scope.migration_scope}</dd>
          </div>
        </dl>

        <div className="callout-card">
          <p className="callout-label">Collected Vs Manual</p>
          <ul className="info-list">
            <li>
              <span>Platform</span>
              <strong>{resolvedSourceMetadata?.platform ?? form.source.platform}</strong>
            </li>
            <li>
              <span>Character Set</span>
              <strong>
                {resolvedSourceMetadata?.character_set ?? form.source.character_set}
              </strong>
            </li>
            <li>
              <span>Deployment</span>
              <strong>
                {resolvedSourceMetadata?.deployment_type ?? form.source.deployment_type}
              </strong>
            </li>
            <li>
              <span>Target Version</span>
              <strong>
                {resolvedTargetMetadata?.oracle_version ?? form.target.oracle_version}
              </strong>
            </li>
          </ul>
        </div>

        <div className="callout-card">
          <p className="callout-label">Operator Guidance</p>
          <strong>Test the source first, then validate the target only when it is available.</strong>
          <p>
            Source connection is mandatory only when you want live metadata collection.
            Target connection remains optional and is used only for direct compatibility checks.
          </p>
        </div>
      </aside>
    </form>
  );
}
