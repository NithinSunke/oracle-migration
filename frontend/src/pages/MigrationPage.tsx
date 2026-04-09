import { useEffect, useState } from "react";

import { navigate } from "../app/router";
import { AppFrame } from "../components/AppFrame";
import { StatusPanel } from "../components/StatusPanel";
import { api, ApiError } from "../services/api";
import type { MigrationRecord, RecommendationResponse } from "../types";

interface MigrationPageProps {
  requestId: string;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatText(value: string | null | undefined): string {
  return value && value.trim() ? value : "Not provided";
}

function formatNumber(value: number | null | undefined, suffix = ""): string {
  if (value === null || value === undefined) {
    return "Not provided";
  }

  return `${value}${suffix}`;
}

function formatBoolean(value: boolean | null | undefined): string {
  if (value === null || value === undefined) {
    return "Not available";
  }

  return value ? "Yes" : "No";
}

export function MigrationPage({ requestId }: MigrationPageProps) {
  const [migration, setMigration] = useState<MigrationRecord | null>(null);
  const [recommendation, setRecommendation] = useState<RecommendationResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadData() {
      setIsLoading(true);
      setErrorMessage(null);

      try {
        const migrationResponse = await api.getMigration(requestId);
        let recommendationResponse: RecommendationResponse | null = null;

        try {
          recommendationResponse = await api.getRecommendation(requestId);
        } catch (error) {
          if (!(error instanceof ApiError) || error.status !== 404) {
            throw error;
          }
        }

        if (!active) {
          return;
        }

        setMigration(migrationResponse);
        setRecommendation(recommendationResponse);
      } catch (error) {
        if (!active) {
          return;
        }

        if (error instanceof ApiError) {
          setErrorMessage(error.message);
        } else {
          setErrorMessage("Unable to load the migration assessment.");
        }
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    void loadData();

    return () => {
      active = false;
    };
  }, [requestId]);

  return (
    <AppFrame
      eyebrow="Assessment Details"
      title={`Migration ${requestId}`}
      summary="Review the saved migration assessment record and continue into recommendation review when available."
      actions={
        recommendation ? (
          <button
            className="primary-button"
            type="button"
            onClick={() => navigate(`/recommendation/${requestId}`)}
          >
            View Recommendation
          </button>
        ) : (
          <button
            className="secondary-button"
            type="button"
            onClick={() => navigate("/migration/new")}
          >
            New Assessment
          </button>
        )
      }
    >
      {isLoading ? (
        <StatusPanel
          title="Loading assessment"
          description="Fetching the saved migration record and checking whether a recommendation is already available."
        />
      ) : null}

      {!isLoading && errorMessage ? (
        <StatusPanel
          title="Assessment unavailable"
          description={errorMessage}
          tone="error"
          action={
            <button className="primary-button" type="button" onClick={() => navigate("/migration/new")}>
              Start a new assessment
            </button>
          }
        />
      ) : null}

      {!isLoading && !errorMessage && migration ? (
        <div className="detail-panels">
          <section className="panel">
            <div className="summary-card">
              <div>
                <p className="chip">Saved Assessment</p>
                <h2>{migration.request_id}</h2>
                <p className="summary-note">
                  Captured on {formatDate(migration.created_at)} with status {migration.status}.
                </p>
              </div>
              <div className="summary-actions">
                {recommendation ? (
                  <button
                    className="primary-button"
                    type="button"
                    onClick={() => navigate(`/recommendation/${migration.request_id}`)}
                  >
                    Open Recommendation
                  </button>
                ) : (
                  <span className="soft-badge">Recommendation not available yet</span>
                )}
              </div>
            </div>
          </section>

          <section className="panel">
            <div className="section-heading">
              <h2>Assessment Snapshot</h2>
              <p>Stable request details fetched from the migration API.</p>
            </div>
            <dl className="snapshot-grid">
              <div>
                <dt>Scope</dt>
                <dd>{migration.scope.migration_scope}</dd>
              </div>
              <div>
                <dt>Source Version</dt>
                <dd>{formatText(migration.source.oracle_version)}</dd>
              </div>
              <div>
                <dt>Target Version</dt>
                <dd>{formatText(migration.target.oracle_version)}</dd>
              </div>
              <div>
                <dt>Database Size</dt>
                <dd>{formatNumber(migration.source.database_size_gb, " GB")}</dd>
              </div>
              <div>
                <dt>Largest Table</dt>
                <dd>{formatNumber(migration.source.largest_table_gb, " GB")}</dd>
              </div>
              <div>
                <dt>Daily Change Rate</dt>
                <dd>{formatNumber(migration.source.daily_change_rate_gb, " GB")}</dd>
              </div>
              <div>
                <dt>Peak Redo</dt>
                <dd>{formatNumber(migration.source.peak_redo_mb_per_sec, " MB/sec")}</dd>
              </div>
              <div>
                <dt>Downtime Window</dt>
                <dd>{formatNumber(migration.business.downtime_window_minutes, " minutes")}</dd>
              </div>
              <div>
                <dt>Network Bandwidth</dt>
                <dd>{formatNumber(migration.connectivity.network_bandwidth_mbps, " Mbps")}</dd>
              </div>
            </dl>
          </section>

          <section className="panel">
            <div className="section-heading">
              <h2>Source Metadata Status</h2>
              <p>
                Shows whether the source Oracle metadata collection succeeded and what details
                were captured for this assessment.
              </p>
            </div>
            <dl className="snapshot-grid">
              <div>
                <dt>Collection Status</dt>
                <dd>{recommendation?.metadata_enrichment?.status ?? "Not requested"}</dd>
              </div>
              <div>
                <dt>Collected Fields</dt>
                <dd>
                  {recommendation?.metadata_enrichment?.collected_fields.length
                    ? recommendation.metadata_enrichment.collected_fields.join(", ")
                    : "Not available"}
                </dd>
              </div>
              <div>
                <dt>Applied Fields</dt>
                <dd>
                  {recommendation?.metadata_enrichment?.applied_fields.length
                    ? recommendation.metadata_enrichment.applied_fields.join(", ")
                    : "Not applied"}
                </dd>
              </div>
              <div>
                <dt>DB Name</dt>
                <dd>{migration.source_metadata?.db_name ?? "Not available"}</dd>
              </div>
              <div>
                <dt>Host</dt>
                <dd>{migration.source_metadata?.host_name ?? "Not available"}</dd>
              </div>
              <div>
                <dt>Edition</dt>
                <dd>{migration.source_metadata?.edition ?? "Not available"}</dd>
              </div>
              <div>
                <dt>Endianness</dt>
                <dd>{migration.source_metadata?.endianness ?? "Not available"}</dd>
              </div>
              <div>
                <dt>Source Version</dt>
                <dd>{migration.source_metadata?.oracle_version ?? "Not available"}</dd>
              </div>
              <div>
                <dt>Deployment Type</dt>
                <dd>{migration.source_metadata?.deployment_type ?? "Not available"}</dd>
              </div>
              <div>
                <dt>Collected Size</dt>
                <dd>{migration.source_metadata?.database_size_gb ?? "Not available"} GB</dd>
              </div>
              <div>
                <dt>Platform</dt>
                <dd>{migration.source_metadata?.platform ?? "Not available"}</dd>
              </div>
              <div>
                <dt>Character Set</dt>
                <dd>{migration.source_metadata?.character_set ?? "Not available"}</dd>
              </div>
              <div>
                <dt>NCHAR Character Set</dt>
                <dd>{migration.source_metadata?.nchar_character_set ?? "Not available"}</dd>
              </div>
              <div>
                <dt>RAC Enabled</dt>
                <dd>{formatBoolean(migration.source_metadata?.rac_enabled)}</dd>
              </div>
              <div>
                <dt>TDE Enabled</dt>
                <dd>{formatBoolean(migration.source_metadata?.tde_enabled)}</dd>
              </div>
              <div>
                <dt>Archivelog Enabled</dt>
                <dd>{formatBoolean(migration.source_metadata?.archivelog_enabled)}</dd>
              </div>
              <div>
                <dt>Collected At</dt>
                <dd>
                  {migration.source_metadata?.collected_at
                    ? formatDate(migration.source_metadata.collected_at)
                    : "Not available"}
                </dd>
              </div>
            </dl>

            {recommendation?.metadata_enrichment?.errors.length ? (
              <div className="form-alert form-alert--error">
                <strong>Metadata collection errors</strong>
                <ul>
                  {recommendation.metadata_enrichment.errors.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {recommendation?.metadata_enrichment?.notes.length ? (
              <div className="form-alert">
                <strong>Metadata collection notes</strong>
                <ul>
                  {recommendation.metadata_enrichment.notes.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>

          {migration.migration_validation ? (
            <section className="panel">
              <div className="section-heading">
                <h2>Source To Target Validation</h2>
                <p>Saved connectivity and compatibility verdict captured before recommendation generation.</p>
              </div>
              <dl className="snapshot-grid">
                <div>
                  <dt>Validation Status</dt>
                  <dd>{migration.migration_validation.status}</dd>
                </div>
                <div>
                  <dt>Source Connection</dt>
                  <dd>{migration.migration_validation.source_connection_status}</dd>
                </div>
                <div>
                  <dt>Target Connection</dt>
                  <dd>{migration.migration_validation.target_connection_status}</dd>
                </div>
                <div>
                  <dt>Target DB Name</dt>
                  <dd>{migration.target_metadata?.db_name ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Target Global Name</dt>
                  <dd>{migration.target_metadata?.global_name ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Target Version</dt>
                  <dd>{migration.target_metadata?.oracle_version ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Target Platform</dt>
                  <dd>{migration.target_metadata?.platform ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Target Character Set</dt>
                  <dd>{migration.target_metadata?.character_set ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Target Role</dt>
                  <dd>{migration.target_metadata?.database_role ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Validated At</dt>
                  <dd>{formatDate(migration.migration_validation.validated_at)}</dd>
                </div>
              </dl>

              <p>{migration.migration_validation.summary}</p>

              {migration.migration_validation.checks.length ? (
                <div className="table-wrap">
                  <table className="results-table results-table--compact">
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
                      {migration.migration_validation.checks.map((check) => (
                        <tr key={check.code}>
                          <td>{check.label}</td>
                          <td>{check.status}</td>
                          <td>{check.source_value ?? ""}</td>
                          <td>{check.target_value ?? ""}</td>
                          <td>
                            <p>{check.message}</p>
                            {check.remediation_sql ? (
                              <pre className="runbook-code-block">
                                <code>{check.remediation_sql}</code>
                              </pre>
                            ) : null}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}

              {migration.migration_validation.blockers.length ? (
                <div className="form-alert form-alert--error">
                  <strong>Migration blockers</strong>
                  <ul>
                    {migration.migration_validation.blockers.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {migration.migration_validation.warnings.length ? (
                <div className="form-alert">
                  <strong>Migration warnings</strong>
                  <ul>
                    {migration.migration_validation.warnings.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>
          ) : null}

          <section className="panel panel-grid">
            <div>
              <div className="section-heading">
                <h2>Source and Target Traits</h2>
              </div>
              <ul className="info-list">
                <li><span>Source platform</span><strong>{formatText(migration.source.platform)}</strong></li>
                <li><span>Target platform</span><strong>{formatText(migration.target.platform)}</strong></li>
                <li><span>Source storage</span><strong>{formatText(migration.source.storage_type)}</strong></li>
                <li><span>Target storage</span><strong>{formatText(migration.target.storage_type)}</strong></li>
                <li><span>Character set</span><strong>{formatText(migration.source.character_set)}</strong></li>
                <li><span>Same endian</span><strong>{migration.target.same_endian ? "Yes" : "No"}</strong></li>
              </ul>
            </div>
            <div>
              <div className="section-heading">
                <h2>Constraints and Feature Signals</h2>
              </div>
              <ul className="info-list">
                <li><span>Fallback required</span><strong>{migration.business.fallback_required ? "Yes" : "No"}</strong></li>
                <li><span>Near-zero downtime</span><strong>{migration.business.near_zero_downtime_required ? "Yes" : "No"}</strong></li>
                <li><span>Regulated workload</span><strong>{migration.business.regulated_workload ? "Yes" : "No"}</strong></li>
                <li><span>Target Exadata</span><strong>{migration.target.target_is_exadata ? "Yes" : "No"}</strong></li>
                <li><span>GoldenGate license</span><strong>{migration.features.goldengate_license_available ? "Yes" : "No"}</strong></li>
                <li><span>ZDM supported target</span><strong>{migration.features.zdm_supported_target ? "Yes" : "No"}</strong></li>
              </ul>
            </div>
          </section>
        </div>
      ) : null}
    </AppFrame>
  );
}
