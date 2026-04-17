import type { OracleSchemaDependencyAnalysis } from "../types";

interface SchemaDependencyAnalyzerProps {
  analysis: OracleSchemaDependencyAnalysis | null | undefined;
}

function badgeClass(status: OracleSchemaDependencyAnalysis["status"] | "CLEAR" | "REVIEW" | "HIGH_RISK"): string {
  if (status === "HIGH_RISK") {
    return "soft-badge soft-badge--danger";
  }
  if (status === "REVIEW") {
    return "soft-badge soft-badge--warning";
  }
  return "soft-badge soft-badge--success";
}

export function SchemaDependencyAnalyzer({
  analysis,
}: SchemaDependencyAnalyzerProps) {
  if (!analysis) {
    return null;
  }

  const getObjectNames = (issue: OracleSchemaDependencyAnalysis["issues"][number]) =>
    issue.object_names.length ? issue.object_names : issue.examples;

  return (
    <section className="dependency-analyzer">
      <div className="dependency-analyzer__hero">
        <div>
          <div className="section-heading">
            <h2>Schema Dependency Analyzer</h2>
            <p>{analysis.summary}</p>
          </div>
        </div>
        <span className={badgeClass(analysis.status)}>{analysis.status.replace("_", " ")}</span>
      </div>

      <div className="dependency-analyzer__summary">
        <article className="dependency-analyzer__metric">
          <span>High Risk</span>
          <strong>{analysis.high_risk_count}</strong>
        </article>
        <article className="dependency-analyzer__metric">
          <span>Review</span>
          <strong>{analysis.review_count}</strong>
        </article>
        <article className="dependency-analyzer__metric">
          <span>Clear</span>
          <strong>{analysis.clear_count}</strong>
        </article>
      </div>

      <div className="table-wrap">
        <table className="results-table results-table--compact">
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
            {analysis.issues.map((issue) => (
              <tr key={issue.code}>
                <td>{issue.label}</td>
                <td>{issue.status}</td>
                <td>{issue.object_count}</td>
                <td>
                  <p>{issue.observation}</p>
                  {issue.recommended_action ? (
                    <p className="field-helper field-helper--standalone">
                      Action: {issue.recommended_action}
                    </p>
                  ) : null}
                </td>
                <td>
                  {getObjectNames(issue).length ? (
                    <ul className="bullet-list">
                      {getObjectNames(issue).map((item) => (
                        <li key={`${issue.code}-${item}`}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    "None"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
