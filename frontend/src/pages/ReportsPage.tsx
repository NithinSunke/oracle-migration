import { useEffect, useState } from "react";

import { navigate } from "../app/router";
import { AppFrame } from "../components/AppFrame";
import { MigrationReadinessSummary } from "../components/MigrationReadinessSummary";
import { PostImportValidationPanel } from "../components/PostImportValidationPanel";
import { RemediationPackPanel } from "../components/RemediationPackPanel";
import { SchemaDependencyAnalyzer } from "../components/SchemaDependencyAnalyzer";
import { StatusPanel } from "../components/StatusPanel";
import { ImplementationPlanFromReport } from "../features/implementation-plan/ImplementationPlanView";
import { api, ApiError } from "../services/api";
import type {
  HistoryItem,
  OracleDiscoverySection,
  OracleDiscoverySummaryItem,
  RecommendationReport,
} from "../types";

type ReportTabId =
  | "summary"
  | "source"
  | "target"
  | "inventory"
  | "discovery"
  | "runbook"
  | "audit";

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

function normalizeApproachName(value: string): string {
  return value.trim().toUpperCase().replace(/[\s/-]+/g, "_");
}

function formatApproachLabel(value: string): string {
  return value
    .toLowerCase()
    .split(/[_\s/-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function escapeHtml(value: string | null | undefined): string {
  if (!value) {
    return "";
  }

  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function downloadTextFile(
  filename: string,
  content: string,
  contentType: string,
): void {
  const blob = new Blob([content], { type: contentType });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

function getMethodCatalog(report: RecommendationReport) {
  const canonicalMethods = [
    "DATAPUMP",
    "RMAN_TRANSPORT",
    "GOLDENGATE",
    "XTTS",
    "ZDM",
  ];
  const primary = normalizeApproachName(report.summary.recommended_approach);
  const secondary = report.recommendation.secondary_option
    ? normalizeApproachName(report.recommendation.secondary_option.approach)
    : null;
  const rejected = new Map(
    report.recommendation.rejected_approaches.map((item) => [
      normalizeApproachName(item.approach),
      item.reason,
    ]),
  );

  return canonicalMethods.map((method) => {
    if (method === primary) {
      return {
        method,
        suitability: "Supported",
        reason:
          report.recommendation.why[0] ?? "Chosen as the primary migration path.",
      };
    }
    if (secondary && method === secondary) {
      return {
        method,
        suitability: "Conditional",
        reason:
          report.recommendation.secondary_option?.why[0] ??
          "Retained as a fallback migration path.",
      };
    }
    if (rejected.has(method)) {
      return {
        method,
        suitability: "Not Suitable",
        reason: rejected.get(method) ?? "Rejected by the decision rules.",
      };
    }
    return {
      method,
      suitability: "Review",
      reason:
        "Not explicitly scored in the current report. Review manually if needed.",
    };
  });
}

function getDependencyObjectNames(issue: {
  object_names?: string[];
  examples?: string[];
}): string[] {
  if (issue.object_names?.length) {
    return issue.object_names;
  }

  return issue.examples ?? [];
}

function getRemediationHtml(report: RecommendationReport): string {
  const pack = report.migration.migration_validation?.remediation_pack;
  if (!pack || !pack.scripts.length) {
    return "";
  }

  return `
      <section>
        <h2>SQL Remediation Pack</h2>
        <p>${escapeHtml(pack.summary)}</p>
        <table>
          <thead>
            <tr>
              <th>Script</th>
              <th>Category</th>
              <th>Status</th>
              <th>Summary</th>
              <th>SQL</th>
            </tr>
          </thead>
          <tbody>
            ${pack.scripts
              .map(
                (script) => `
                  <tr>
                    <td>${escapeHtml(script.label)}</td>
                    <td>${escapeHtml(script.category.replace(/_/g, " "))}</td>
                    <td>${escapeHtml(script.status)}</td>
                    <td>${escapeHtml(script.summary)}</td>
                    <td><pre>${escapeHtml(script.sql)}</pre></td>
                  </tr>`,
              )
              .join("")}
          </tbody>
        </table>
      </section>
    `;
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function getReadinessScores(report: RecommendationReport) {
  const validation = report.migration.migration_validation;
  const compatibility =
    validation?.status === "MIGRATABLE"
      ? 95
      : validation?.status === "CONDITIONALLY_MIGRATABLE"
        ? 75
        : validation?.status === "NOT_MIGRATABLE"
          ? 35
          : 55;

  const sourceConnected =
    !report.migration.metadata_collection?.enabled ||
    report.recommendation.metadata_enrichment?.status === "COLLECTED" ||
    report.recommendation.metadata_enrichment?.status === "PARTIAL" ||
    validation?.source_connection_status === "CONNECTED";
  const targetConnected =
    !validation || validation.target_connection_status === "CONNECTED";

  const operational = clampScore(
    60 +
      (sourceConnected ? 15 : -20) +
      (targetConnected ? 10 : 0) -
      report.recommendation.prerequisites.length * 4 -
      report.recommendation.manual_review_flags.length * 3,
  );

  const invalidObjects =
    report.migration.source_metadata?.inventory_summary?.invalid_object_count ?? 0;
  const objectReadiness = clampScore(
    85 - invalidObjects * 2 - report.recommendation.risk_flags.length * 5,
  );

  const size = report.migration.source.database_size_gb ?? 0;
  const changeRate = report.migration.source.daily_change_rate_gb ?? 0;
  const downtime = report.migration.business.downtime_window_minutes;
  const performance = clampScore(
    80 -
      (size > 500 ? 15 : size > 100 ? 8 : 0) -
      (changeRate > 100 ? 10 : changeRate > 20 ? 5 : 0) +
      (downtime >= 240 ? 10 : downtime >= 60 ? 4 : -10),
  );

  const overall = clampScore(
    compatibility * 0.35 +
      operational * 0.25 +
      objectReadiness * 0.2 +
      performance * 0.2,
  );

  return {
    compatibility,
    operational,
    objectReadiness,
    performance,
    overall,
  };
}

function getReportAlerts(report: RecommendationReport) {
  const blockers = report.migration.migration_validation?.blockers ?? [];
  const warnings = [
    ...(report.migration.migration_validation?.warnings ?? []),
    ...report.recommendation.risk_flags,
    ...report.recommendation.manual_review_flags,
  ];
  const prerequisites = report.recommendation.prerequisites;

  return {
    blockers: Array.from(new Set(blockers)),
    warnings: Array.from(new Set(warnings)),
    prerequisites: Array.from(new Set(prerequisites)),
  };
}

function getTopSchemas(report: RecommendationReport) {
  return [...(report.migration.source_metadata?.schema_inventory ?? [])]
    .sort((left, right) => right.object_count - left.object_count)
    .slice(0, 5);
}

function getNextActions(report: RecommendationReport) {
  const actions: string[] = [];
  const alerts = getReportAlerts(report);

  if (alerts.blockers.length > 0) {
    actions.push(
      "Resolve migration blockers before scheduling rehearsal or cutover.",
    );
  }
  if (alerts.prerequisites.length > 0) {
    actions.push(`Complete prerequisite setup: ${alerts.prerequisites[0]}`);
  }
  if (alerts.warnings.length > 0) {
    actions.push(
      `Review active warnings with DBAs and application owners: ${alerts.warnings[0]}`,
    );
  }
  if (report.recommendation.secondary_option) {
    actions.push(
      `Keep ${formatApproachLabel(report.recommendation.secondary_option.approach)} as fallback during rehearsal planning.`,
    );
  }
  actions.push(
    "Run a rehearsal migration and capture actual duration, throughput, and rollback timings.",
  );
  actions.push(
    "Validate post-migration application smoke tests, invalid object recompilation, and schema statistics refresh.",
  );

  return Array.from(new Set(actions)).slice(0, 6);
}

function buildHtmlReport(report: RecommendationReport): string {
  const validation = report.migration.migration_validation;
  const readiness = validation?.readiness;
  const alerts = getReportAlerts(report);
  const topSchemas = getTopSchemas(report);
  const generatedAt = formatDate(report.generated_at);
  const validatedAt = validation ? formatDate(validation.validated_at) : "Not available";

  const readinessHtml = readiness
    ? `
      <section>
        <h2>Pre-Migration Readiness</h2>
        <div class="metric-grid">
          <div class="metric-card">
            <span>Overall Score</span>
            <strong>${readiness.overall_score}/100</strong>
          </div>
          <div class="metric-card">
            <span>Verdict</span>
            <strong>${escapeHtml(readiness.verdict)}</strong>
          </div>
        </div>
        <p>${escapeHtml(readiness.summary)}</p>
        <table>
          <thead>
            <tr>
              <th>Category</th>
              <th>Factor</th>
              <th>Status</th>
              <th>Score</th>
              <th>Observation</th>
            </tr>
          </thead>
          <tbody>
            ${readiness.categories
              .flatMap((category) =>
                category.factors.map(
                  (factor) => `
                    <tr>
                      <td>${escapeHtml(category.label)}</td>
                      <td>${escapeHtml(factor.label)}</td>
                      <td>${escapeHtml(factor.status)}</td>
                      <td>${factor.score}/100</td>
                      <td>${escapeHtml(factor.observation)}</td>
                    </tr>`,
                ),
              )
              .join("")}
          </tbody>
        </table>
      </section>
    `
    : "";

  const dependencyAnalysis = report.migration.source_metadata?.dependency_analysis;
  const dependencyHtml = dependencyAnalysis
    ? `
      <section>
        <h2>Schema Dependency Analyzer</h2>
        <div class="metric-grid">
          <div class="metric-card">
            <span>Status</span>
            <strong>${escapeHtml(dependencyAnalysis.status)}</strong>
          </div>
          <div class="metric-card">
            <span>High Risk</span>
            <strong>${dependencyAnalysis.high_risk_count}</strong>
          </div>
          <div class="metric-card">
            <span>Review</span>
            <strong>${dependencyAnalysis.review_count}</strong>
          </div>
          <div class="metric-card">
            <span>Clear</span>
            <strong>${dependencyAnalysis.clear_count}</strong>
          </div>
        </div>
        <p>${escapeHtml(dependencyAnalysis.summary)}</p>
        <table>
          <thead>
            <tr>
              <th>Dependency</th>
              <th>Status</th>
              <th>Objects</th>
              <th>Observation</th>
              <th>Object Names</th>
            </tr>
          </thead>
          <tbody>
            ${dependencyAnalysis.issues
              .map(
                (issue) => `
                  <tr>
                    <td>${escapeHtml(issue.label)}</td>
                    <td>${escapeHtml(issue.status)}</td>
                    <td>${issue.object_count}</td>
                    <td>${escapeHtml(issue.observation)}</td>
                    <td>${escapeHtml(getDependencyObjectNames(issue).join("; "))}</td>
                  </tr>`,
              )
              .join("")}
          </tbody>
        </table>
      </section>
    `
    : "";
  const remediationHtml = getRemediationHtml(report);

  const validationChecksHtml = validation
    ? `
      <section>
        <h2>Target Validation</h2>
        <div class="metric-grid">
          <div class="metric-card">
            <span>Status</span>
            <strong>${escapeHtml(validation.status)}</strong>
          </div>
          <div class="metric-card">
            <span>Source Connection</span>
            <strong>${escapeHtml(validation.source_connection_status)}</strong>
          </div>
          <div class="metric-card">
            <span>Target Connection</span>
            <strong>${escapeHtml(validation.target_connection_status)}</strong>
          </div>
          <div class="metric-card">
            <span>Validated At</span>
            <strong>${escapeHtml(validatedAt)}</strong>
          </div>
        </div>
        <p>${escapeHtml(validation.summary)}</p>
        <table>
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
            ${validation.checks
              .map(
                (check) => `
                  <tr>
                    <td>${escapeHtml(check.label)}</td>
                    <td>${escapeHtml(check.status)}</td>
                    <td>${escapeHtml(check.source_value ?? "")}</td>
                    <td>${escapeHtml(check.target_value ?? "")}</td>
                    <td>${escapeHtml(check.message)}</td>
                  </tr>`,
              )
              .join("")}
          </tbody>
        </table>
      </section>
    `
    : "";

  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${escapeHtml(report.request_id)} Migration Report</title>
    <style>
      body {
        margin: 0;
        padding: 32px;
        font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        color: #102033;
        background: #f7f8f6;
      }
      main {
        max-width: 1100px;
        margin: 0 auto;
        background: #ffffff;
        border-radius: 24px;
        padding: 32px;
        box-shadow: 0 20px 50px rgba(16, 32, 51, 0.08);
      }
      h1, h2, h3, p {
        margin-top: 0;
      }
      .eyebrow {
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: #0f6d69;
        font-size: 12px;
        font-weight: 700;
      }
      .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px;
        margin: 16px 0 20px;
      }
      .metric-card {
        border: 1px solid #d9e1e7;
        border-radius: 16px;
        padding: 14px 16px;
        background: #fbfcfb;
      }
      .metric-card span {
        display: block;
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #537086;
        margin-bottom: 6px;
      }
      .metric-card strong {
        font-size: 20px;
      }
      section {
        margin-top: 28px;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 14px;
      }
      th, td {
        border: 1px solid #d9e1e7;
        padding: 10px 12px;
        text-align: left;
        vertical-align: top;
      }
      th {
        background: #eef4f2;
      }
      ul {
        margin: 12px 0 0;
        padding-left: 20px;
      }
      .two-col {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 20px;
      }
      @media (max-width: 800px) {
        body {
          padding: 16px;
        }
        main {
          padding: 20px;
        }
        .two-col {
          grid-template-columns: 1fr;
        }
      }
    </style>
  </head>
  <body>
    <main>
      <div class="eyebrow">Oracle Migration Report</div>
      <h1>${escapeHtml(report.summary.recommended_approach)} Recommendation Summary</h1>
      <p>Request ${escapeHtml(report.request_id)} generated on ${escapeHtml(generatedAt)}.</p>

      <div class="metric-grid">
        <div class="metric-card">
          <span>Recommended Approach</span>
          <strong>${escapeHtml(report.summary.recommended_approach)}</strong>
        </div>
        <div class="metric-card">
          <span>Confidence</span>
          <strong>${escapeHtml(report.summary.confidence)}</strong>
        </div>
        <div class="metric-card">
          <span>Recommendation Score</span>
          <strong>${report.summary.score}/100</strong>
        </div>
        <div class="metric-card">
          <span>Rules Version</span>
          <strong>${escapeHtml(report.summary.rules_version)}</strong>
        </div>
      </div>

      ${readinessHtml}
      ${dependencyHtml}
      ${remediationHtml}
      ${validationChecksHtml}

      <section>
        <h2>Recommendation Narrative</h2>
        <ul>
          ${report.summary.why.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
        </ul>
      </section>

      <section class="two-col">
        <div>
          <h2>Warnings</h2>
          ${
            alerts.warnings.length
              ? `<ul>${alerts.warnings
                  .map((item) => `<li>${escapeHtml(item)}</li>`)
                  .join("")}</ul>`
              : "<p>No warnings are currently stored for this report.</p>"
          }
        </div>
        <div>
          <h2>Blockers</h2>
          ${
            alerts.blockers.length
              ? `<ul>${alerts.blockers
                  .map((item) => `<li>${escapeHtml(item)}</li>`)
                  .join("")}</ul>`
              : "<p>No blockers are currently stored for this report.</p>"
          }
        </div>
      </section>

      <section class="two-col">
        <div>
          <h2>Prerequisites</h2>
          ${
            alerts.prerequisites.length
              ? `<ul>${alerts.prerequisites
                  .map((item) => `<li>${escapeHtml(item)}</li>`)
                  .join("")}</ul>`
              : "<p>No explicit prerequisites are stored for this report.</p>"
          }
        </div>
        <div>
          <h2>Next Actions</h2>
          <ul>
            ${getNextActions(report)
              .map((item) => `<li>${escapeHtml(item)}</li>`)
              .join("")}
          </ul>
        </div>
      </section>

      <section>
        <h2>Top Source Schemas By Object Count</h2>
        ${
          topSchemas.length
            ? `<table>
                <thead>
                  <tr>
                    <th>Schema</th>
                    <th>Objects</th>
                    <th>Tables</th>
                    <th>Indexes</th>
                    <th>Invalid Objects</th>
                  </tr>
                </thead>
                <tbody>
                  ${topSchemas
                    .map(
                      (schema) => `
                        <tr>
                          <td>${escapeHtml(schema.owner)}</td>
                          <td>${schema.object_count}</td>
                          <td>${schema.table_count}</td>
                          <td>${schema.index_count}</td>
                          <td>${schema.invalid_object_count}</td>
                        </tr>`,
                    )
                    .join("")}
                </tbody>
              </table>`
            : "<p>No schema inventory is available in the stored report.</p>"
        }
      </section>
    </main>
  </body>
</html>`;
}

function getInitialReportTab(): ReportTabId {
  if (typeof window === "undefined") {
    return "summary";
  }

  const tab = new URLSearchParams(window.location.search).get("tab");
  const allowedTabs: ReportTabId[] = [
    "summary",
    "source",
    "target",
    "inventory",
    "discovery",
    "runbook",
    "audit",
  ];

  return allowedTabs.includes(tab as ReportTabId)
    ? (tab as ReportTabId)
    : "summary";
}

function setReportTabInUrl(tab: ReportTabId): void {
  if (typeof window === "undefined") {
    return;
  }

  const url = new URL(window.location.href);
  url.searchParams.set("tab", tab);
  window.history.replaceState({}, "", url.toString());
}

export function ReportsPage() {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [report, setReport] = useState<RecommendationReport | null>(null);
  const [activeTab, setActiveTab] = useState<ReportTabId>(getInitialReportTab);
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [isReportLoading, setIsReportLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [downloadJsonInProgress, setDownloadJsonInProgress] = useState(false);
  const [downloadHtmlInProgress, setDownloadHtmlInProgress] = useState(false);

  const visibleDiscoverySections =
    report?.migration.source_metadata?.discovery_sections.filter(
      (section) =>
        section.key !== "modifiable_parameters" &&
        section.key !== "datafiles" &&
        section.key !== "tablespace_details",
    ) ?? [];

  useEffect(() => {
    let active = true;

    async function loadHistory() {
      setIsHistoryLoading(true);
      setErrorMessage(null);

      try {
        const response = await api.listHistory();
        if (!active) {
          return;
        }

        const reportableItems = response.items.filter(
          (item) => item.recommended_approach,
        );
        setHistory(reportableItems);
        setSelectedRequestId(reportableItems[0]?.request_id ?? null);
      } catch (error) {
        if (!active) {
          return;
        }
        if (error instanceof ApiError) {
          setErrorMessage(error.message);
        } else {
          setErrorMessage("Unable to load report candidates.");
        }
      } finally {
        if (active) {
          setIsHistoryLoading(false);
        }
      }
    }

    void loadHistory();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedRequestId) {
      setReport(null);
      return;
    }

    const requestId = selectedRequestId;
    let active = true;

    async function loadReport() {
      setIsReportLoading(true);
      setErrorMessage(null);

      try {
        const response = await api.getReport(requestId);
        if (!active) {
          return;
        }
        setReport(response);
      } catch (error) {
        if (!active) {
          return;
        }
        if (error instanceof ApiError) {
          setErrorMessage(error.message);
        } else {
          setErrorMessage("Unable to load the report preview.");
        }
      } finally {
        if (active) {
          setIsReportLoading(false);
        }
      }
    }

    void loadReport();

    return () => {
      active = false;
    };
  }, [selectedRequestId]);

  async function handleDownloadJson() {
    if (!selectedRequestId) {
      return;
    }

    setDownloadJsonInProgress(true);
    setErrorMessage(null);
    try {
      await api.downloadReport(selectedRequestId);
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("Unable to download the report.");
      }
    } finally {
      setDownloadJsonInProgress(false);
    }
  }

  function handleDownloadHtml() {
    if (!report) {
      return;
    }

    setDownloadHtmlInProgress(true);
    setErrorMessage(null);
    try {
      downloadTextFile(
        `${report.request_id}-report.html`,
        buildHtmlReport(report),
        "text/html;charset=utf-8",
      );
    } catch {
      setErrorMessage("Unable to download the HTML report.");
    } finally {
      setDownloadHtmlInProgress(false);
    }
  }

  const handleTabChange = (tab: ReportTabId) => {
    setActiveTab(tab);
    setReportTabInUrl(tab);
  };

  return (
    <AppFrame
      eyebrow="Reports"
      title="Generate audit-ready recommendation summaries"
      summary="Preview stored assessment reports, confirm the recommendation narrative, and review the data in focused report tabs."
      pageClassName="page--wide"
      actions={
        report ? (
          <div className="summary-actions">
            <button
              className="secondary-button"
              type="button"
              onClick={handleDownloadHtml}
              disabled={downloadHtmlInProgress}
            >
              {downloadHtmlInProgress ? "Downloading HTML Report" : "Download HTML Report"}
            </button>
            <button
              className="primary-button"
              type="button"
              onClick={handleDownloadJson}
              disabled={downloadJsonInProgress}
            >
              {downloadJsonInProgress ? "Downloading JSON Report" : "Download JSON Report"}
            </button>
          </div>
        ) : undefined
      }
    >
      {isHistoryLoading ? (
        <StatusPanel
          title="Loading report catalog"
          description="Finding saved assessments that already have stored recommendation results."
        />
      ) : null}

      {!isHistoryLoading && errorMessage ? (
        <StatusPanel
          title="Reports unavailable"
          description={errorMessage}
          tone="error"
        />
      ) : null}

      {!isHistoryLoading && !errorMessage && history.length === 0 ? (
        <StatusPanel
          title="No reports available yet"
          description="Run and save at least one recommendation before opening the reporting view."
        />
      ) : null}

      {!isHistoryLoading && history.length > 0 ? (
        <div className="panel-grid report-layout">
          <section className="panel">
            <div className="section-heading">
              <h2>Available Reports</h2>
              <p>
                Select a saved recommendation to preview its downloadable report in
                grouped tabs.
              </p>
            </div>
            <ul className="selection-list">
              {history.map((item) => (
                <li key={item.request_id}>
                  <button
                    type="button"
                    className={`selection-card${
                      selectedRequestId === item.request_id
                        ? " selection-card--active"
                        : ""
                    }`}
                    onClick={() => setSelectedRequestId(item.request_id)}
                  >
                    <strong>{item.request_id}</strong>
                    <span>{item.recommended_approach}</span>
                    <small>
                      {item.confidence} confidence, score {item.score}, created{" "}
                      {formatDate(item.created_at)}
                    </small>
                  </button>
                </li>
              ))}
            </ul>
          </section>

          <section className="panel">
            {isReportLoading ? (
              <StatusPanel
                title="Loading report preview"
                description="Fetching the stored recommendation and audit summary for the selected request."
              />
            ) : null}

            {!isReportLoading && report ? (
              <div className="report-preview">
                {(() => {
                  const readiness = getReadinessScores(report);
                  const methods = getMethodCatalog(report);
                  const alerts = getReportAlerts(report);
                  const topSchemas = getTopSchemas(report);
                  const nextActions = getNextActions(report);
                  const tabDefinitions: {
                    id: ReportTabId;
                    label: string;
                    description: string;
                  }[] = [
                    {
                      id: "summary",
                      label: "Summary",
                      description: "Recommendation and readiness",
                    },
                    {
                      id: "source",
                      label: "Source Metadata",
                      description: "Collected source details",
                    },
                    {
                      id: "target",
                      label: "Target Validation",
                      description: "Compatibility and blockers",
                    },
                    {
                      id: "inventory",
                      label: "Inventory",
                      description: "Schemas, PDBs, objects",
                    },
                    {
                      id: "discovery",
                      label: "Detailed Discovery",
                      description: "Collected metadata sections",
                    },
                    {
                      id: "runbook",
                      label: "Runbook",
                      description: "Implementation commands",
                    },
                    {
                      id: "audit",
                      label: "Audit",
                      description: "Reasons and navigation",
                    },
                  ];

                  return (
                    <>
                      <section className="panel panel--inner report-hero-panel">
                        <div className="result-hero">
                          <div>
                            <p className="chip">Selected Report</p>
                            <h2>{report.summary.recommended_approach}</h2>
                            <p className="result-summary">
                              Stored assessment {report.request_id} with{" "}
                              {report.summary.confidence} confidence. Use the tabs below
                              to move between the recommendation, source metadata, target
                              validation, inventory, discovery detail, and execution
                              runbook.
                            </p>
                          </div>
                          <div className="score-ring">
                            <span>{readiness.overall}</span>
                            <small>ready</small>
                          </div>
                        </div>
                        <div className="hero-metrics">
                          <article className="hero-metric-card">
                            <span>Source Metadata</span>
                            <strong>
                              {report.recommendation.metadata_enrichment?.status ??
                                "Not requested"}
                            </strong>
                          </article>
                          <article className="hero-metric-card">
                            <span>Target Validation</span>
                            <strong>
                              {report.migration.migration_validation
                                ?.target_connection_status ?? "Optional"}
                            </strong>
                          </article>
                          <article className="hero-metric-card">
                            <span>Warnings</span>
                            <strong>{alerts.warnings.length}</strong>
                          </article>
                          <article className="hero-metric-card">
                            <span>Blockers</span>
                            <strong>{alerts.blockers.length}</strong>
                          </article>
                        </div>
                      </section>

                      <div className="report-tab-list" role="tablist" aria-label="Report tabs">
                        {tabDefinitions.map((tab) => (
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
                          <div className="section-heading">
                            <h2>Executive Summary</h2>
                            <p>
                              DBA-ready summary of migration fit, delivery risk, and
                              immediate next actions for the selected assessment.
                            </p>
                          </div>
                          <dl className="snapshot-grid">
                            <div>
                              <dt>Primary Recommendation</dt>
                              <dd>{report.summary.recommended_approach}</dd>
                            </div>
                            <div>
                              <dt>Readiness Score</dt>
                              <dd>{readiness.overall}/100</dd>
                            </div>
                            <div>
                              <dt>Compatibility</dt>
                              <dd>{readiness.compatibility}/100</dd>
                            </div>
                            <div>
                              <dt>Operational Readiness</dt>
                              <dd>{readiness.operational}/100</dd>
                            </div>
                            <div>
                              <dt>Object Readiness</dt>
                              <dd>{readiness.objectReadiness}/100</dd>
                            </div>
                            <div>
                              <dt>Performance Fit</dt>
                              <dd>{readiness.performance}/100</dd>
                            </div>
                            <div>
                              <dt>Confidence</dt>
                              <dd>{report.summary.confidence}</dd>
                            </div>
                            <div>
                              <dt>Secondary Option</dt>
                              <dd>
                                {report.recommendation.secondary_option?.approach ??
                                  "Not provided"}
                              </dd>
                            </div>
                            <div>
                              <dt>Blockers</dt>
                              <dd>{alerts.blockers.length}</dd>
                            </div>
                            <div>
                              <dt>Warnings</dt>
                              <dd>{alerts.warnings.length}</dd>
                            </div>
                            <div>
                              <dt>Prerequisites</dt>
                              <dd>{alerts.prerequisites.length}</dd>
                            </div>
                            <div>
                              <dt>Largest Scope Signal</dt>
                              <dd>{report.migration.scope.migration_scope}</dd>
                            </div>
                          </dl>

                          <div className="section-heading report-preview__heading">
                            <h2>Method Suitability Matrix</h2>
                            <p>
                              Fast view of which migration approaches are preferred,
                              conditional, or ruled out by the current assessment.
                            </p>
                          </div>
                          <div className="table-wrap">
                            <table className="results-table results-table--compact">
                              <thead>
                                <tr>
                                  <th>Method</th>
                                  <th>Suitability</th>
                                  <th>Assessment</th>
                                </tr>
                              </thead>
                              <tbody>
                                {methods.map((item) => (
                                  <tr key={item.method}>
                                    <td>{formatApproachLabel(item.method)}</td>
                                    <td>{item.suitability}</td>
                                    <td>{item.reason}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>

                          {alerts.blockers.length ||
                          alerts.warnings.length ||
                          alerts.prerequisites.length ? (
                            <div className="panel-grid report-preview__heading">
                              <section className="panel">
                                <div className="section-heading">
                                  <h2>Blockers And Warnings</h2>
                                </div>
                                {alerts.blockers.length ? (
                                  <ul className="bullet-list bullet-list--danger">
                                    {alerts.blockers.map((item) => (
                                      <li key={item}>{item}</li>
                                    ))}
                                  </ul>
                                ) : (
                                  <p>
                                    No hard blockers are currently stored for this report.
                                  </p>
                                )}
                                {alerts.warnings.length ? (
                                  <ul className="bullet-list">
                                    {alerts.warnings.map((item) => (
                                      <li key={item}>{item}</li>
                                    ))}
                                  </ul>
                                ) : null}
                              </section>

                              <section className="panel">
                                <div className="section-heading">
                                  <h2>Next Actions</h2>
                                </div>
                                <ul className="bullet-list">
                                  {nextActions.map((item) => (
                                    <li key={item}>{item}</li>
                                  ))}
                                </ul>
                              </section>
                            </div>
                          ) : null}

                          {topSchemas.length ? (
                            <>
                              <div className="section-heading report-preview__heading">
                                <h2>Top Schema Risk Summary</h2>
                                <p>
                                  Largest non-default schemas from the source discovery,
                                  useful for rehearsal sizing and object remediation
                                  planning.
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
                                      <th>Invalid Objects</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {topSchemas.map((schema) => (
                                      <tr
                                        key={`${schema.container_name}-${schema.owner}`}
                                      >
                                        <td>{schema.container_name}</td>
                                        <td>{schema.owner}</td>
                                        <td>{schema.object_count}</td>
                                        <td>{schema.table_count}</td>
                                        <td>{schema.index_count}</td>
                                        <td>{schema.invalid_object_count}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </>
                          ) : null}
                        </div>
                      ) : null}

                      {activeTab === "source" ? (
                        <div className="report-tab-panel">
                          <div className="section-heading">
                            <h2>Source Metadata Collection</h2>
                            <p>
                              This shows whether the app connected to the source Oracle
                              database and what metadata it actually collected before
                              generating the recommendation.
                            </p>
                          </div>
                          <dl className="snapshot-grid">
                            <div>
                              <dt>Collection Status</dt>
                              <dd>
                                {report.recommendation.metadata_enrichment?.status ??
                                  "Not requested"}
                              </dd>
                            </div>
                            <div>
                              <dt>Collected Fields</dt>
                              <dd>
                                {report.recommendation.metadata_enrichment?.collected_fields
                                  .length
                                  ? report.recommendation.metadata_enrichment.collected_fields.join(
                                      ", ",
                                    )
                                  : "Not available"}
                              </dd>
                            </div>
                            <div>
                              <dt>Applied Fields</dt>
                              <dd>
                                {report.recommendation.metadata_enrichment?.applied_fields
                                  .length
                                  ? report.recommendation.metadata_enrichment.applied_fields.join(
                                      ", ",
                                    )
                                  : "Not applied"}
                              </dd>
                            </div>
                            <div>
                              <dt>DB Name</dt>
                              <dd>
                                {report.migration.source_metadata?.db_name ??
                                  "Not available"}
                              </dd>
                            </div>
                            <div>
                              <dt>Host</dt>
                              <dd>
                                {report.migration.source_metadata?.host_name ??
                                  "Not available"}
                              </dd>
                            </div>
                            <div>
                              <dt>Edition</dt>
                              <dd>
                                {report.migration.source_metadata?.edition ??
                                  "Not available"}
                              </dd>
                            </div>
                            <div>
                              <dt>Endianness</dt>
                              <dd>
                                {report.migration.source_metadata?.endianness ??
                                  "Not available"}
                              </dd>
                            </div>
                            <div>
                              <dt>Source Version</dt>
                              <dd>
                                {report.migration.source_metadata?.oracle_version ??
                                  "Not available"}
                              </dd>
                            </div>
                            <div>
                              <dt>Deployment Type</dt>
                              <dd>
                                {report.migration.source_metadata?.deployment_type ??
                                  "Not available"}
                              </dd>
                            </div>
                            <div>
                              <dt>Collected Size</dt>
                              <dd>
                                {report.migration.source_metadata?.database_size_gb ??
                                  "Not available"}{" "}
                                GB
                              </dd>
                            </div>
                            <div>
                              <dt>Platform</dt>
                              <dd>
                                {report.migration.source_metadata?.platform ??
                                  "Not available"}
                              </dd>
                            </div>
                            <div>
                              <dt>Character Set</dt>
                              <dd>
                                {report.migration.source_metadata?.character_set ??
                                  "Not available"}
                              </dd>
                            </div>
                            <div>
                              <dt>NCHAR Character Set</dt>
                              <dd>
                                {report.migration.source_metadata?.nchar_character_set ??
                                  "Not available"}
                              </dd>
                            </div>
                            <div>
                              <dt>RAC Enabled</dt>
                              <dd>
                                {formatBoolean(
                                  report.migration.source_metadata?.rac_enabled,
                                )}
                              </dd>
                            </div>
                            <div>
                              <dt>TDE Enabled</dt>
                              <dd>
                                {formatBoolean(
                                  report.migration.source_metadata?.tde_enabled,
                                )}
                              </dd>
                            </div>
                            <div>
                              <dt>Archivelog Enabled</dt>
                              <dd>
                                {formatBoolean(
                                  report.migration.source_metadata?.archivelog_enabled,
                                )}
                              </dd>
                            </div>
                            <div>
                              <dt>Collected At</dt>
                              <dd>
                                {report.migration.source_metadata?.collected_at
                                  ? formatDate(
                                      report.migration.source_metadata.collected_at,
                                    )
                                  : "Not available"}
                              </dd>
                            </div>
                          </dl>

                          {report.migration.source_metadata?.discovery_summary.length ? (
                            <>
                              <div className="section-heading report-preview__heading">
                                <h2>Discovery Summary</h2>
                                <p>
                                  Derived summary matching the source database discovery
                                  output.
                                </p>
                              </div>
                              <DiscoverySummaryTable
                                items={
                                  report.migration.source_metadata.discovery_summary
                                }
                              />
                            </>
                          ) : null}

                          <SchemaDependencyAnalyzer
                            analysis={
                              report.migration.source_metadata?.dependency_analysis
                            }
                          />

                          {report.recommendation.metadata_enrichment?.errors.length ? (
                            <div className="form-alert form-alert--error">
                              <strong>Metadata collection errors</strong>
                              <ul>
                                {report.recommendation.metadata_enrichment.errors.map(
                                  (item) => (
                                    <li key={item}>{item}</li>
                                  ),
                                )}
                              </ul>
                            </div>
                          ) : null}

                          {report.recommendation.metadata_enrichment?.notes.length ? (
                            <div className="form-alert">
                              <strong>Metadata collection notes</strong>
                              <ul>
                                {report.recommendation.metadata_enrichment.notes.map(
                                  (item) => (
                                    <li key={item}>{item}</li>
                                  ),
                                )}
                              </ul>
                            </div>
                          ) : null}
                        </div>
                      ) : null}

                      {activeTab === "target" ? (
                        <div className="report-tab-panel">
                          {report.migration.migration_validation ? (
                            <>
                              <div className="section-heading">
                                <h2>Source To Target Validation</h2>
                                <p>
                                  Pre-submit validation showing whether the app connected
                                  to both databases and whether the source can be migrated
                                  to the target.
                                </p>
                              </div>
                              <dl className="snapshot-grid">
                                <div>
                                  <dt>Validation Status</dt>
                                  <dd>
                                    {report.migration.migration_validation.status}
                                  </dd>
                                </div>
                                <div>
                                  <dt>Source Connection</dt>
                                  <dd>
                                    {
                                      report.migration.migration_validation
                                        .source_connection_status
                                    }
                                  </dd>
                                </div>
                                <div>
                                  <dt>Target Connection</dt>
                                  <dd>
                                    {
                                      report.migration.migration_validation
                                        .target_connection_status
                                    }
                                  </dd>
                                </div>
                                <div>
                                  <dt>Target DB Name</dt>
                                  <dd>
                                    {report.migration.target_metadata?.db_name ??
                                      "Not available"}
                                  </dd>
                                </div>
                                <div>
                                  <dt>Target Global Name</dt>
                                  <dd>
                                    {report.migration.target_metadata?.global_name ??
                                      "Not available"}
                                  </dd>
                                </div>
                                <div>
                                  <dt>Target Version</dt>
                                  <dd>
                                    {report.migration.target_metadata?.oracle_version ??
                                      "Not available"}
                                  </dd>
                                </div>
                                <div>
                                  <dt>Target Platform</dt>
                                  <dd>
                                    {report.migration.target_metadata?.platform ??
                                      "Not available"}
                                  </dd>
                                </div>
                                <div>
                                  <dt>Target Character Set</dt>
                                  <dd>
                                    {report.migration.target_metadata?.character_set ??
                                      "Not available"}
                                  </dd>
                                </div>
                                <div>
                                  <dt>Target Role</dt>
                                  <dd>
                                    {report.migration.target_metadata?.database_role ??
                                      "Not available"}
                                  </dd>
                                </div>
                                <div>
                                  <dt>Validated At</dt>
                                  <dd>
                                    {formatDate(
                                      report.migration.migration_validation.validated_at,
                                    )}
                                  </dd>
                                </div>
                              </dl>
                              <p>{report.migration.migration_validation.summary}</p>

                              <MigrationReadinessSummary
                                assessment={report.migration.migration_validation}
                              />

                              <RemediationPackPanel
                                pack={report.migration.migration_validation.remediation_pack}
                                requestId={report.migration.request_id}
                              />

                              <PostImportValidationPanel
                                migration={report.migration}
                                requestId={report.migration.request_id}
                              />

                              {report.migration.migration_validation.checks.length ? (
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
                                      {report.migration.migration_validation.checks.map(
                                        (check) => (
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
                                        ),
                                      )}
                                    </tbody>
                                  </table>
                                </div>
                              ) : null}

                              {report.migration.migration_validation.blockers.length ? (
                                <div className="form-alert form-alert--error">
                                  <strong>Migration blockers</strong>
                                  <ul>
                                    {report.migration.migration_validation.blockers.map(
                                      (item) => (
                                        <li key={item}>{item}</li>
                                      ),
                                    )}
                                  </ul>
                                </div>
                              ) : null}

                              {report.migration.migration_validation.warnings.length ? (
                                <div className="form-alert">
                                  <strong>Migration warnings</strong>
                                  <ul>
                                    {report.migration.migration_validation.warnings.map(
                                      (item) => (
                                        <li key={item}>{item}</li>
                                      ),
                                    )}
                                  </ul>
                                </div>
                              ) : null}
                            </>
                          ) : (
                            <StatusPanel
                              title="No target validation captured"
                              description="This assessment was saved without source-to-target compatibility validation."
                            />
                          )}
                        </div>
                      ) : null}

                      {activeTab === "inventory" ? (
                        <div className="report-tab-panel">
                          {report.migration.source_metadata?.inventory_summary ? (
                            <>
                              <div className="section-heading">
                                <h2>Database Object Inventory</h2>
                                <p>
                                  Inventory collected from the source Oracle database
                                  during assessment execution.
                                </p>
                              </div>
                              <dl className="snapshot-grid">
                                <div>
                                  <dt>Schemas</dt>
                                  <dd>
                                    {
                                      report.migration.source_metadata.inventory_summary
                                        .schema_count
                                    }
                                  </dd>
                                </div>
                                <div>
                                  <dt>Total Objects</dt>
                                  <dd>
                                    {
                                      report.migration.source_metadata.inventory_summary
                                        .total_objects
                                    }
                                  </dd>
                                </div>
                                <div>
                                  <dt>Tables</dt>
                                  <dd>
                                    {
                                      report.migration.source_metadata.inventory_summary
                                        .total_tables
                                    }
                                  </dd>
                                </div>
                                <div>
                                  <dt>Indexes</dt>
                                  <dd>
                                    {
                                      report.migration.source_metadata.inventory_summary
                                        .total_indexes
                                    }
                                  </dd>
                                </div>
                                <div>
                                  <dt>Views</dt>
                                  <dd>
                                    {
                                      report.migration.source_metadata.inventory_summary
                                        .total_views
                                    }
                                  </dd>
                                </div>
                                <div>
                                  <dt>Materialized Views</dt>
                                  <dd>
                                    {
                                      report.migration.source_metadata.inventory_summary
                                        .total_materialized_views
                                    }
                                  </dd>
                                </div>
                                <div>
                                  <dt>Sequences</dt>
                                  <dd>
                                    {
                                      report.migration.source_metadata.inventory_summary
                                        .total_sequences
                                    }
                                  </dd>
                                </div>
                                <div>
                                  <dt>Procedures</dt>
                                  <dd>
                                    {
                                      report.migration.source_metadata.inventory_summary
                                        .total_procedures
                                    }
                                  </dd>
                                </div>
                                <div>
                                  <dt>Functions</dt>
                                  <dd>
                                    {
                                      report.migration.source_metadata.inventory_summary
                                        .total_functions
                                    }
                                  </dd>
                                </div>
                                <div>
                                  <dt>Packages</dt>
                                  <dd>
                                    {
                                      report.migration.source_metadata.inventory_summary
                                        .total_packages
                                    }
                                  </dd>
                                </div>
                                <div>
                                  <dt>Triggers</dt>
                                  <dd>
                                    {
                                      report.migration.source_metadata.inventory_summary
                                        .total_triggers
                                    }
                                  </dd>
                                </div>
                                <div>
                                  <dt>Invalid Objects</dt>
                                  <dd>
                                    {
                                      report.migration.source_metadata.inventory_summary
                                        .invalid_object_count
                                    }
                                  </dd>
                                </div>
                              </dl>
                            </>
                          ) : null}

                          {report.migration.source_metadata?.pdbs.length ? (
                            <>
                              <div className="section-heading report-preview__heading">
                                <h2>PDB Inventory</h2>
                                <p>
                                  All pluggable databases discovered from the source CDB
                                  connection.
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
                                    {report.migration.source_metadata.pdbs.map((pdb) => (
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

                          {report.migration.source_metadata?.schema_inventory.length ? (
                            <>
                              <div className="section-heading report-preview__heading">
                                <h2>Schema Inventory</h2>
                                <p>
                                  Schema-level object counts gathered from the source
                                  connection.
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
                                    {report.migration.source_metadata.schema_inventory.map(
                                      (schema) => (
                                        <tr
                                          key={`${schema.container_name}-${schema.owner}`}
                                        >
                                          <td>{schema.container_name}</td>
                                          <td>{schema.owner}</td>
                                          <td>{schema.object_count}</td>
                                          <td>{schema.table_count}</td>
                                          <td>{schema.index_count}</td>
                                          <td>{schema.view_count}</td>
                                          <td>
                                            {schema.materialized_view_count}
                                          </td>
                                          <td>{schema.sequence_count}</td>
                                          <td>{schema.invalid_object_count}</td>
                                        </tr>
                                      ),
                                    )}
                                  </tbody>
                                </table>
                              </div>
                            </>
                          ) : null}

                          {report.migration.source_metadata?.invalid_objects_by_schema
                            .length ? (
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
                                    {report.migration.source_metadata.invalid_objects_by_schema.map(
                                      (item) => (
                                        <tr
                                          key={`${item.container_name}-${item.owner}`}
                                        >
                                          <td>{item.container_name}</td>
                                          <td>{item.container_type}</td>
                                          <td>{item.owner}</td>
                                          <td>{item.invalid_object_count}</td>
                                        </tr>
                                      ),
                                    )}
                                  </tbody>
                                </table>
                              </div>
                            </>
                          ) : null}
                        </div>
                      ) : null}

                      {activeTab === "discovery" ? (
                        <div className="report-tab-panel">
                          {visibleDiscoverySections.length ? (
                            <>
                              <div className="section-heading">
                                <h2>Detailed Source Discovery</h2>
                                <p>
                                  Expand only the metadata sections you need. This keeps
                                  the report easier to review while preserving the full
                                  collected Oracle detail.
                                </p>
                              </div>
                              <div className="runbook-command-list">
                                {visibleDiscoverySections.map((section) => (
                                  <DiscoverySectionTable
                                    key={section.key}
                                    section={section}
                                  />
                                ))}
                              </div>
                            </>
                          ) : (
                            <StatusPanel
                              title="No detailed discovery sections"
                              description="This assessment does not currently have expanded discovery tables to display."
                            />
                          )}
                        </div>
                      ) : null}

                      {activeTab === "runbook" ? (
                        <div className="report-tab-panel">
                          <ImplementationPlanFromReport report={report} />
                        </div>
                      ) : null}

                      {activeTab === "audit" ? (
                        <div className="report-tab-panel">
                          <div className="section-heading">
                            <h2>Report Summary</h2>
                            <p>
                              Generated {formatDate(report.generated_at)} with rules
                              version {report.summary.rules_version}.
                            </p>
                          </div>
                          <dl className="snapshot-grid">
                            <div>
                              <dt>Request ID</dt>
                              <dd>{report.request_id}</dd>
                            </div>
                            <div>
                              <dt>Approach</dt>
                              <dd>{report.summary.recommended_approach}</dd>
                            </div>
                            <div>
                              <dt>Confidence</dt>
                              <dd>{report.summary.confidence}</dd>
                            </div>
                            <div>
                              <dt>Score</dt>
                              <dd>{report.summary.score}/100</dd>
                            </div>
                            <div>
                              <dt>Migration Scope</dt>
                              <dd>{report.migration.scope.migration_scope}</dd>
                            </div>
                            <div>
                              <dt>Database Size</dt>
                              <dd>
                                {report.migration.source.database_size_gb ??
                                  "Not provided"}{" "}
                                GB
                              </dd>
                            </div>
                          </dl>

                          <div className="section-heading report-preview__heading">
                            <h2>Report Reasons</h2>
                            <p>
                              The downloadable report includes the same explainability
                              trail stored with the recommendation.
                            </p>
                          </div>
                          <ul className="bullet-list">
                            {report.summary.why.map((reason) => (
                              <li key={reason}>{reason}</li>
                            ))}
                          </ul>

                          <div className="summary-actions">
                            <button
                              className="secondary-button"
                              type="button"
                              onClick={() =>
                                navigate(`/recommendation/${report.request_id}`)
                              }
                            >
                              Open Recommendation
                            </button>
                            <button
                              className="secondary-button"
                              type="button"
                              onClick={() =>
                                navigate(`/migration/${report.request_id}`)
                              }
                            >
                              Open Assessment
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </>
                  );
                })()}
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </AppFrame>
  );
}
