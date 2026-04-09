import type {
  MigrationCompatibilityCheck,
  MigrationRecord,
  RecommendationResponse,
} from "../../types";

interface RecommendationViewProps {
  migration: MigrationRecord | null;
  recommendation: RecommendationResponse;
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

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function getCheckTone(check: MigrationCompatibilityCheck): string {
  if (check.status === "FAIL") {
    return "comparison-card comparison-card--danger";
  }
  if (check.status === "WARN") {
    return "comparison-card comparison-card--warning";
  }
  return "comparison-card comparison-card--success";
}

function getImmediateActions(
  migration: MigrationRecord | null,
  recommendation: RecommendationResponse,
): string[] {
  const actions: string[] = [];

  if (migration?.migration_validation?.blockers.length) {
    actions.push(`Resolve blocker: ${migration.migration_validation.blockers[0]}`);
  }
  if (recommendation.prerequisites.length) {
    actions.push(`Prepare prerequisite: ${recommendation.prerequisites[0]}`);
  }
  if (recommendation.risk_flags.length) {
    actions.push(`Review risk: ${recommendation.risk_flags[0]}`);
  }
  if (recommendation.secondary_option) {
    actions.push(
      `Keep ${recommendation.secondary_option.approach} as the fallback migration path.`,
    );
  }

  actions.push(
    "Run a rehearsal using representative schema volume before final cutover approval.",
  );

  return Array.from(new Set(actions)).slice(0, 4);
}

export function RecommendationView({
  migration,
  recommendation,
}: RecommendationViewProps) {
  const immediateActions = getImmediateActions(migration, recommendation);
  const highlightChecks =
    migration?.migration_validation?.checks.filter(
      (check) => check.status === "FAIL" || check.status === "WARN",
    ) ?? [];

  return (
    <div className="results-layout">
      <section className="panel panel--hero-result">
        <div className="result-hero">
          <div>
            <p className="chip">Primary Recommendation</p>
            <h2>{recommendation.recommended_approach}</h2>
            <p className="result-summary">
              Confidence {recommendation.confidence} with score {recommendation.score}/100.
              Generated on {formatDate(recommendation.generated_at)} using rules version{" "}
              {recommendation.rules_version}.
            </p>
          </div>
          <div className="score-ring">
            <span>{recommendation.score}</span>
            <small>score</small>
          </div>
        </div>

        <div className="hero-metrics">
          <article className="hero-metric-card">
            <span>Source Validation</span>
            <strong>
              {migration?.migration_validation?.source_connection_status ??
                (recommendation.metadata_enrichment?.status ?? "Not requested")}
            </strong>
          </article>
          <article className="hero-metric-card">
            <span>Target Validation</span>
            <strong>
              {migration?.migration_validation?.target_connection_status ?? "Optional"}
            </strong>
          </article>
          <article className="hero-metric-card">
            <span>Downtime Window</span>
            <strong>
              {formatNumber(
                migration?.business.downtime_window_minutes,
                " minutes",
              )}
            </strong>
          </article>
          <article className="hero-metric-card">
            <span>Database Size</span>
            <strong>{formatNumber(migration?.source.database_size_gb, " GB")}</strong>
          </article>
        </div>
      </section>

      <section className="panel panel-grid">
        <div>
          <div className="section-heading">
            <h2>Immediate Next Actions</h2>
            <p>Use this short list to move from recommendation to execution planning.</p>
          </div>
          <ul className="bullet-list">
            {immediateActions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <div className="section-heading">
            <h2>Decision Signals</h2>
            <p>High-value inputs that influenced the strategy ranking the most.</p>
          </div>
          <dl className="snapshot-grid snapshot-grid--two-up">
            <div>
              <dt>Primary Method</dt>
              <dd>{recommendation.recommended_approach}</dd>
            </div>
            <div>
              <dt>Fallback Method</dt>
              <dd>{recommendation.secondary_option?.approach ?? "Not provided"}</dd>
            </div>
            <div>
              <dt>Scope</dt>
              <dd>{migration?.scope.migration_scope ?? "Not provided"}</dd>
            </div>
            <div>
              <dt>Source Version</dt>
              <dd>{formatText(migration?.source.oracle_version)}</dd>
            </div>
            <div>
              <dt>Target Version</dt>
              <dd>{formatText(migration?.target.oracle_version)}</dd>
            </div>
            <div>
              <dt>Network Bandwidth</dt>
              <dd>{formatNumber(migration?.connectivity.network_bandwidth_mbps, " Mbps")}</dd>
            </div>
          </dl>
        </div>
      </section>

      {migration ? (
        <section className="panel">
          <div className="section-heading">
            <h2>Assessment Snapshot</h2>
            <p>Stable request data fetched through the migration API.</p>
          </div>
          <dl className="snapshot-grid">
            <div>
              <dt>Request ID</dt>
              <dd>{migration.request_id}</dd>
            </div>
            <div>
              <dt>Captured</dt>
              <dd>{formatDate(migration.created_at)}</dd>
            </div>
            <div>
              <dt>Database Size</dt>
              <dd>{formatNumber(migration.source.database_size_gb, " GB")}</dd>
            </div>
            <div>
              <dt>Downtime Window</dt>
              <dd>{formatNumber(migration.business.downtime_window_minutes, " minutes")}</dd>
            </div>
            <div>
              <dt>Target Exadata</dt>
              <dd>{migration.target.target_is_exadata ? "Yes" : "No"}</dd>
            </div>
            <div>
              <dt>ZDM Supported</dt>
              <dd>{migration.features.zdm_supported_target ? "Yes" : "No"}</dd>
            </div>
            <div>
              <dt>Source Platform</dt>
              <dd>{formatText(migration.source.platform)}</dd>
            </div>
            <div>
              <dt>Target Platform</dt>
              <dd>{formatText(migration.target.platform)}</dd>
            </div>
            <div>
              <dt>Network Bandwidth</dt>
              <dd>{formatNumber(migration.connectivity.network_bandwidth_mbps, " Mbps")}</dd>
            </div>
          </dl>
        </section>
      ) : null}

      {migration?.migration_validation ? (
        <section className="panel">
          <div className="section-heading">
            <h2>Source And Target Fit</h2>
            <p>
              These comparison cards surface the most important compatibility gaps before
              you move into the detailed report or runbook.
            </p>
          </div>
          <div className="comparison-grid">
            {highlightChecks.length > 0 ? (
              highlightChecks.slice(0, 6).map((check) => (
                <article className={getCheckTone(check)} key={check.code}>
                  <div className="comparison-card__header">
                    <strong>{check.label}</strong>
                    <span className="chip">{check.status}</span>
                  </div>
                  <dl className="comparison-values">
                    <div>
                      <dt>Source</dt>
                      <dd>{check.source_value ?? "Not provided"}</dd>
                    </div>
                    <div>
                      <dt>Target</dt>
                      <dd>{check.target_value ?? "Not provided"}</dd>
                    </div>
                  </dl>
                  <p>{check.message}</p>
                </article>
              ))
            ) : (
              <article className="comparison-card comparison-card--success">
                <div className="comparison-card__header">
                  <strong>No active source-to-target mismatches</strong>
                  <span className="chip">PASS</span>
                </div>
                <p>
                  The stored validation did not return any WARN or FAIL checks for the
                  key source and target compatibility comparisons.
                </p>
              </article>
            )}
          </div>
        </section>
      ) : null}

      <section className="panel">
        <div className="section-heading">
          <h2>Why This Was Chosen</h2>
          <p>
            Explainability is front and center so reviewers can challenge or confirm the
            recommendation.
          </p>
        </div>
        <ul className="bullet-list">
          {recommendation.why.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </section>

      <section className="panel panel-grid">
        <div>
          <div className="section-heading">
            <h2>Prerequisites</h2>
          </div>
          <ul className="bullet-list">
            {recommendation.prerequisites.length > 0 ? (
              recommendation.prerequisites.map((item) => <li key={item}>{item}</li>)
            ) : (
              <li>No special prerequisites were returned.</li>
            )}
          </ul>
        </div>
        <div>
          <div className="section-heading">
            <h2>Risk Flags</h2>
          </div>
          <ul className="bullet-list bullet-list--danger">
            {recommendation.risk_flags.length > 0 ? (
              recommendation.risk_flags.map((item) => <li key={item}>{item}</li>)
            ) : (
              <li>No active risk flags were returned.</li>
            )}
          </ul>
        </div>
      </section>

      <section className="panel panel-grid">
        <div>
          <div className="section-heading">
            <h2>Companion Tools</h2>
          </div>
          <ul className="tag-list">
            {recommendation.companion_tools.map((tool) => (
              <li key={tool}>{tool}</li>
            ))}
          </ul>
        </div>
        <div>
          <div className="section-heading">
            <h2>Manual Review Flags</h2>
          </div>
          <ul className="bullet-list">
            {recommendation.manual_review_flags.length > 0 ? (
              recommendation.manual_review_flags.map((flag) => <li key={flag}>{flag}</li>)
            ) : (
              <li>No manual review flags were returned.</li>
            )}
          </ul>
        </div>
      </section>

      {recommendation.secondary_option ? (
        <section className="panel">
          <div className="section-heading">
            <h2>Secondary Option</h2>
            <p>A fallback path for technical review or rehearsal planning.</p>
          </div>
          <div className="secondary-card">
            <strong>{recommendation.secondary_option.approach}</strong>
            <span>Score {recommendation.secondary_option.score}/100</span>
            <ul className="bullet-list">
              {recommendation.secondary_option.why.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      <section className="panel">
        <div className="section-heading">
          <h2>Rejected Approaches</h2>
          <p>Methods ruled out by the current inputs and rule set.</p>
        </div>
        <div className="table-wrap">
          <table className="results-table">
            <thead>
              <tr>
                <th>Approach</th>
                <th>Score</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {recommendation.rejected_approaches.map((item) => (
                <tr key={item.approach}>
                  <td>{item.approach}</td>
                  <td>{item.score}</td>
                  <td>{item.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
