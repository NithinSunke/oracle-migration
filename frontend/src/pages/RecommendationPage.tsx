import { useEffect, useState } from "react";

import { navigate } from "../app/router";
import { AppFrame } from "../components/AppFrame";
import { StatusPanel } from "../components/StatusPanel";
import { ImplementationPlanFromRecommendation } from "../features/implementation-plan/ImplementationPlanView";
import { RecommendationView } from "../features/recommendation-results/RecommendationView";
import { api, ApiError } from "../services/api";
import type {
  MigrationRecord,
  OracleDiscoverySection,
  OracleDiscoverySummaryItem,
  RecommendationResponse,
} from "../types";

interface RecommendationPageProps {
  requestId: string;
}

type RecommendationTabId =
  | "summary"
  | "source"
  | "target"
  | "inventory"
  | "discovery"
  | "runbook";

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatBoolean(value: boolean | null | undefined): string {
  if (value === null || value === undefined) {
    return "Not available";
  }

  return value ? "Yes" : "No";
}

function isDefaultOracleUser(username: string, oracleManaged?: boolean): boolean {
  const normalized = username.trim().toUpperCase();
  if (oracleManaged) {
    return true;
  }

  return normalized === "PUBLIC";
}

function DiscoverySummaryTable({ items }: { items: OracleDiscoverySummaryItem[] }) {
  return (
    <div className="table-wrap">
      <table className="results-table results-table--compact">
        <thead>
          <tr>
            <th>Key Point</th>
            <th>Key Value</th>
            <th>Observation</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.key_point}>
              <td>{item.key_point}</td>
              <td>{item.key_value}</td>
              <td>{item.observation}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DiscoverySectionTable({ section }: { section: OracleDiscoverySection }) {
  const visibleRows =
    section.key === "database_users"
      ? section.rows.filter(
          (row) =>
            !isDefaultOracleUser(
              row.CUSTOM_USER ?? "",
              row.USER_TYPE === "Oracle Managed",
            ),
        )
      : section.rows;

  return (
    <details className="discovery-section" open={section.key === "database_users"}>
      <summary className="discovery-section__summary">
        <div>
          <strong>{section.title}</strong>
          <p>
            {visibleRows.length} row{visibleRows.length === 1 ? "" : "s"} collected
            {section.truncated ? " (display limited in the app)." : "."}
          </p>
        </div>
        <span className="soft-badge soft-badge--neutral">Expand</span>
      </summary>
      <div className="table-wrap">
        <table className="results-table results-table--compact">
          <thead>
            <tr>
              {section.columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, index) => (
              <tr key={`${section.key}-${index}`}>
                {section.columns.map((column) => (
                  <td key={`${section.key}-${index}-${column}`}>{row[column] || ""}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function getInitialRecommendationTab(): RecommendationTabId {
  if (typeof window === "undefined") {
    return "summary";
  }

  const tab = new URLSearchParams(window.location.search).get("tab");
  const allowedTabs: RecommendationTabId[] = [
    "summary",
    "source",
    "target",
    "inventory",
    "discovery",
    "runbook",
  ];

  return allowedTabs.includes(tab as RecommendationTabId)
    ? (tab as RecommendationTabId)
    : "summary";
}

function setRecommendationTabInUrl(tab: RecommendationTabId): void {
  if (typeof window === "undefined") {
    return;
  }

  const url = new URL(window.location.href);
  url.searchParams.set("tab", tab);
  window.history.replaceState({}, "", url.toString());
}

export function RecommendationPage({ requestId }: RecommendationPageProps) {
  const [migration, setMigration] = useState<MigrationRecord | null>(null);
  const [recommendation, setRecommendation] =
    useState<RecommendationResponse | null>(null);
  const [activeTab, setActiveTab] =
    useState<RecommendationTabId>(getInitialRecommendationTab);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const visibleDiscoverySections =
    migration?.source_metadata?.discovery_sections.filter(
      (section) =>
        section.key !== "modifiable_parameters" &&
        section.key !== "datafiles" &&
        section.key !== "tablespace_details",
    ) ?? [];

  useEffect(() => {
    let active = true;

    async function loadData() {
      setIsLoading(true);
      setErrorMessage(null);

      try {
        const [migrationResponse, recommendationResponse] = await Promise.all([
          api.getMigration(requestId),
          api.getRecommendation(requestId),
        ]);

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
          setErrorMessage("Unable to load the recommendation details.");
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

  const handleTabChange = (tab: RecommendationTabId) => {
    setActiveTab(tab);
    setRecommendationTabInUrl(tab);
  };

  return (
    <AppFrame
      eyebrow="Recommendation Review"
      title={`Assessment ${requestId}`}
      summary="Review the chosen approach, decision rationale, prerequisites, risks, and collected metadata in focused tabs before planning cutover and execution."
      pageClassName="page--wide"
      actions={
        <>
          <button
            className="secondary-button"
            type="button"
            onClick={() => navigate("/reports")}
          >
            Open Reports
          </button>
          <button
            className="primary-button"
            type="button"
            onClick={() => navigate("/migration/new")}
          >
            Run Another Assessment
          </button>
        </>
      }
    >
      {isLoading ? (
        <StatusPanel
          title="Loading recommendation"
          description="Fetching the migration record and recommendation payload from the API."
        />
      ) : null}

      {!isLoading && errorMessage ? (
        <StatusPanel
          title="Recommendation unavailable"
          description={errorMessage}
          tone="error"
          action={
            <button
              className="primary-button"
              type="button"
              onClick={() => navigate("/migration/new")}
            >
              Start a new assessment
            </button>
          }
        />
      ) : null}

      {!isLoading && !errorMessage && recommendation ? (
        <>
          <div className="report-tab-list" role="tablist" aria-label="Recommendation tabs">
            {[
              {
                id: "summary" as const,
                label: "Summary",
                description: "Decision and rationale",
              },
              {
                id: "source" as const,
                label: "Source Metadata",
                description: "Collected source details",
              },
              {
                id: "target" as const,
                label: "Target Validation",
                description: "Compatibility checks",
              },
              {
                id: "inventory" as const,
                label: "Inventory",
                description: "Schemas, objects, PDBs",
              },
              {
                id: "discovery" as const,
                label: "Detailed Discovery",
                description: "Expanded metadata sections",
              },
              {
                id: "runbook" as const,
                label: "Runbook",
                description: "Implementation commands",
              },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.id}
                className={`report-tab${
                  activeTab === tab.id ? " report-tab--active" : ""
                }`}
                onClick={() => handleTabChange(tab.id)}
              >
                <span className="report-tab__label">{tab.label}</span>
                <small>{tab.description}</small>
              </button>
            ))}
          </div>

          {activeTab === "summary" ? (
            <div className="report-tab-panel">
              <RecommendationView migration={migration} recommendation={recommendation} />
            </div>
          ) : null}

          {activeTab === "source" ? (
            <section className="panel report-tab-panel">
              <div className="section-heading">
                <h2>Source Metadata Status</h2>
                <p>
                  See the source connection result here immediately after execution,
                  without needing to switch to the Reports page first.
                </p>
              </div>
              <dl className="snapshot-grid">
                <div>
                  <dt>Collection Status</dt>
                  <dd>{recommendation.metadata_enrichment?.status ?? "Not requested"}</dd>
                </div>
                <div>
                  <dt>Collected Fields</dt>
                  <dd>
                    {recommendation.metadata_enrichment?.collected_fields.length
                      ? recommendation.metadata_enrichment.collected_fields.join(", ")
                      : "Not available"}
                  </dd>
                </div>
                <div>
                  <dt>Applied Fields</dt>
                  <dd>
                    {recommendation.metadata_enrichment?.applied_fields.length
                      ? recommendation.metadata_enrichment.applied_fields.join(", ")
                      : "Not applied"}
                  </dd>
                </div>
                <div>
                  <dt>DB Name</dt>
                  <dd>{migration?.source_metadata?.db_name ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Host</dt>
                  <dd>{migration?.source_metadata?.host_name ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Edition</dt>
                  <dd>{migration?.source_metadata?.edition ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Endianness</dt>
                  <dd>{migration?.source_metadata?.endianness ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Source Version</dt>
                  <dd>{migration?.source_metadata?.oracle_version ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Deployment Type</dt>
                  <dd>{migration?.source_metadata?.deployment_type ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Collected Size</dt>
                  <dd>{migration?.source_metadata?.database_size_gb ?? "Not available"} GB</dd>
                </div>
                <div>
                  <dt>Platform</dt>
                  <dd>{migration?.source_metadata?.platform ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>Character Set</dt>
                  <dd>{migration?.source_metadata?.character_set ?? "Not available"}</dd>
                </div>
                <div>
                  <dt>NCHAR Character Set</dt>
                  <dd>
                    {migration?.source_metadata?.nchar_character_set ?? "Not available"}
                  </dd>
                </div>
                <div>
                  <dt>RAC Enabled</dt>
                  <dd>{formatBoolean(migration?.source_metadata?.rac_enabled)}</dd>
                </div>
                <div>
                  <dt>TDE Enabled</dt>
                  <dd>{formatBoolean(migration?.source_metadata?.tde_enabled)}</dd>
                </div>
                <div>
                  <dt>Archivelog Enabled</dt>
                  <dd>
                    {formatBoolean(migration?.source_metadata?.archivelog_enabled)}
                  </dd>
                </div>
                <div>
                  <dt>Collected At</dt>
                  <dd>
                    {migration?.source_metadata?.collected_at
                      ? formatDate(migration.source_metadata.collected_at)
                      : "Not available"}
                  </dd>
                </div>
              </dl>

              {migration?.source_metadata?.discovery_summary.length ? (
                <>
                  <div className="section-heading report-preview__heading">
                    <h2>Discovery Summary</h2>
                    <p>
                      HTML-style discovery summary derived from the source database
                      connection.
                    </p>
                  </div>
                  <DiscoverySummaryTable
                    items={migration.source_metadata.discovery_summary}
                  />
                </>
              ) : null}

              {recommendation.metadata_enrichment?.errors.length ? (
                <div className="form-alert form-alert--error">
                  <strong>Metadata collection errors</strong>
                  <ul>
                    {recommendation.metadata_enrichment.errors.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {recommendation.metadata_enrichment?.notes.length ? (
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
          ) : null}

          {activeTab === "target" ? (
            <section className="panel report-tab-panel">
              {migration?.migration_validation ? (
                <>
                  <div className="section-heading">
                    <h2>Source To Target Validation</h2>
                    <p>
                      Pre-submit validation proving whether the app connected to both
                      databases and whether the source is migration-ready for the target.
                    </p>
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
                      <dd>
                        {migration.target_metadata?.global_name ?? "Not available"}
                      </dd>
                    </div>
                    <div>
                      <dt>Target Version</dt>
                      <dd>
                        {migration.target_metadata?.oracle_version ?? "Not available"}
                      </dd>
                    </div>
                    <div>
                      <dt>Target Platform</dt>
                      <dd>{migration.target_metadata?.platform ?? "Not available"}</dd>
                    </div>
                    <div>
                      <dt>Target Character Set</dt>
                      <dd>
                        {migration.target_metadata?.character_set ?? "Not available"}
                      </dd>
                    </div>
                    <div>
                      <dt>Target Role</dt>
                      <dd>
                        {migration.target_metadata?.database_role ?? "Not available"}
                      </dd>
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
                </>
              ) : (
                <StatusPanel
                  title="No target validation captured"
                  description="This recommendation was generated without source-to-target validation."
                />
              )}
            </section>
          ) : null}

          {activeTab === "inventory" ? (
            <section className="panel report-tab-panel">
              {migration?.source_metadata?.inventory_summary ? (
                <>
                  <div className="section-heading">
                    <h2>Database Object Inventory</h2>
                    <p>
                      Schema and object counts gathered from Oracle after the source
                      connection succeeded.
                    </p>
                  </div>
                  <dl className="snapshot-grid">
                    <div>
                      <dt>Schemas</dt>
                      <dd>{migration.source_metadata.inventory_summary.schema_count}</dd>
                    </div>
                    <div>
                      <dt>Total Objects</dt>
                      <dd>{migration.source_metadata.inventory_summary.total_objects}</dd>
                    </div>
                    <div>
                      <dt>Tables</dt>
                      <dd>{migration.source_metadata.inventory_summary.total_tables}</dd>
                    </div>
                    <div>
                      <dt>Indexes</dt>
                      <dd>{migration.source_metadata.inventory_summary.total_indexes}</dd>
                    </div>
                    <div>
                      <dt>Views</dt>
                      <dd>{migration.source_metadata.inventory_summary.total_views}</dd>
                    </div>
                    <div>
                      <dt>Materialized Views</dt>
                      <dd>
                        {migration.source_metadata.inventory_summary
                          .total_materialized_views}
                      </dd>
                    </div>
                    <div>
                      <dt>Sequences</dt>
                      <dd>{migration.source_metadata.inventory_summary.total_sequences}</dd>
                    </div>
                    <div>
                      <dt>Procedures</dt>
                      <dd>{migration.source_metadata.inventory_summary.total_procedures}</dd>
                    </div>
                    <div>
                      <dt>Functions</dt>
                      <dd>{migration.source_metadata.inventory_summary.total_functions}</dd>
                    </div>
                    <div>
                      <dt>Packages</dt>
                      <dd>{migration.source_metadata.inventory_summary.total_packages}</dd>
                    </div>
                    <div>
                      <dt>Triggers</dt>
                      <dd>{migration.source_metadata.inventory_summary.total_triggers}</dd>
                    </div>
                    <div>
                      <dt>Invalid Objects</dt>
                      <dd>
                        {migration.source_metadata.inventory_summary.invalid_object_count}
                      </dd>
                    </div>
                  </dl>
                </>
              ) : null}

              {migration?.source_metadata?.pdbs.length ? (
                <>
                  <div className="section-heading report-preview__heading">
                    <h2>PDB Inventory</h2>
                    <p>
                      All pluggable databases discovered from the source CDB connection.
                    </p>
                  </div>
                  <div className="table-wrap">
                    <table className="results-table results-table--compact">
                      <thead>
                        <tr>
                          <th>PDB</th>
                          <th>Con ID</th>
                          <th>Open Mode</th>
                          <th>Open Time</th>
                          <th>Services</th>
                          <th>Size GB</th>
                        </tr>
                      </thead>
                      <tbody>
                        {migration.source_metadata.pdbs.map((pdb) => (
                          <tr key={`${pdb.con_id}-${pdb.name}`}>
                            <td>{pdb.name}</td>
                            <td>{pdb.con_id}</td>
                            <td>{pdb.open_mode ?? "Not available"}</td>
                            <td>
                              {pdb.open_time
                                ? formatDate(pdb.open_time)
                                : "Not available"}
                            </td>
                            <td>
                              {pdb.service_names.length
                                ? pdb.service_names.join(", ")
                                : "Not available"}
                            </td>
                            <td>{pdb.total_size_gb ?? "Not available"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : null}

              {migration?.source_metadata?.schema_inventory.length ? (
                <>
                  <div className="section-heading report-preview__heading">
                    <h2>Schema Inventory</h2>
                    <p>
                      Schema-level object counts gathered from the source connection.
                    </p>
                  </div>
                  <div className="table-wrap">
                    <table className="results-table results-table--compact">
                      <thead>
                        <tr>
                          <th>Container</th>
                          <th>Schema</th>
                          <th>Objects</th>
                          <th>Tables</th>
                          <th>Indexes</th>
                          <th>Views</th>
                          <th>MVs</th>
                          <th>Sequences</th>
                          <th>Invalid</th>
                        </tr>
                      </thead>
                      <tbody>
                        {migration.source_metadata.schema_inventory.map((schema) => (
                          <tr key={`${schema.container_name}-${schema.owner}`}>
                            <td>{schema.container_name}</td>
                            <td>{schema.owner}</td>
                            <td>{schema.object_count}</td>
                            <td>{schema.table_count}</td>
                            <td>{schema.index_count}</td>
                            <td>{schema.view_count}</td>
                            <td>{schema.materialized_view_count}</td>
                            <td>{schema.sequence_count}</td>
                            <td>{schema.invalid_object_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : null}

              {migration?.source_metadata?.invalid_objects_by_schema.length ? (
                <>
                  <div className="section-heading report-preview__heading">
                    <h2>Invalid Objects By Schema</h2>
                    <p>
                      Grouped invalid object counts from the CDB root and all
                      discovered PDBs.
                    </p>
                  </div>
                  <div className="table-wrap">
                    <table className="results-table results-table--compact">
                      <thead>
                        <tr>
                          <th>Container</th>
                          <th>Type</th>
                          <th>Schema</th>
                          <th>Invalid Objects</th>
                        </tr>
                      </thead>
                      <tbody>
                        {migration.source_metadata.invalid_objects_by_schema.map((item) => (
                          <tr key={`${item.container_name}-${item.owner}`}>
                            <td>{item.container_name}</td>
                            <td>{item.container_type}</td>
                            <td>{item.owner}</td>
                            <td>{item.invalid_object_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : null}
            </section>
          ) : null}

          {activeTab === "discovery" ? (
            <div className="report-tab-panel">
              {visibleDiscoverySections.length ? (
                <div className="runbook-command-list">
                  {visibleDiscoverySections.map((section) => (
                    <DiscoverySectionTable key={section.key} section={section} />
                  ))}
                </div>
              ) : (
                <StatusPanel
                  title="No detailed discovery sections"
                  description="This recommendation does not currently have expanded discovery tables to display."
                />
              )}
            </div>
          ) : null}

          {activeTab === "runbook" ? (
            <>
              {migration ? (
                <div className="report-tab-panel">
                  <ImplementationPlanFromRecommendation
                    migration={migration}
                    recommendation={recommendation}
                  />
                </div>
              ) : null}
            </>
          ) : null}
        </>
      ) : null}
    </AppFrame>
  );
}
