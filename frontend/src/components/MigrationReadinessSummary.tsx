import type { MigrationCompatibilityAssessment } from "../types";

interface MigrationReadinessSummaryProps {
  assessment: MigrationCompatibilityAssessment;
}

function getVerdictTone(verdict: string): string {
  if (verdict === "READY") {
    return "soft-badge soft-badge--success";
  }
  if (verdict === "BLOCKED") {
    return "soft-badge soft-badge--danger";
  }
  return "soft-badge soft-badge--warning";
}

function getFactorTone(status: string): "success" | "warning" | "danger" | "neutral" {
  const normalized = status.trim().toUpperCase();
  if (normalized === "PASS" || normalized === "READY") {
    return "success";
  }
  if (normalized === "FAIL" || normalized === "FAILED" || normalized === "BLOCKED") {
    return "danger";
  }
  if (normalized === "WARN" || normalized === "WARNING") {
    return "warning";
  }
  return "neutral";
}

function getFactorBadgeClass(status: string): string {
  const tone = getFactorTone(status);
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

function getFactorRowClass(status: string): string {
  const tone = getFactorTone(status);
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

function getCategoryClass(statuses: string[]): string {
  const tones = statuses.map(getFactorTone);
  if (tones.includes("danger")) {
    return "migration-readiness__category migration-readiness__category--danger";
  }
  if (tones.includes("warning")) {
    return "migration-readiness__category migration-readiness__category--warning";
  }
  if (tones.length > 0 && tones.every((tone) => tone === "success")) {
    return "migration-readiness__category migration-readiness__category--success";
  }
  return "migration-readiness__category";
}

export function MigrationReadinessSummary({
  assessment,
}: MigrationReadinessSummaryProps) {
  const readiness = assessment.readiness;
  if (!readiness) {
    return null;
  }

  return (
    <div className="migration-readiness">
      <div className="migration-readiness__hero">
        <div className="score-ring">
          <span>{readiness.overall_score}</span>
          <small>readiness</small>
        </div>
        <div className="migration-readiness__copy">
          <div className="migration-readiness__headline">
            <strong>Pre-migration readiness score</strong>
            <span className={getVerdictTone(readiness.verdict)}>
              {readiness.verdict}
            </span>
          </div>
          <p>{readiness.summary}</p>
        </div>
      </div>

      <div className="migration-readiness__categories">
        {readiness.categories.map((category) => (
          <article
            key={category.key}
            className={getCategoryClass(category.factors.map((factor) => factor.status))}
          >
            <div className="migration-readiness__category-header">
              <strong>{category.label}</strong>
              <span>{category.score}/100</span>
            </div>
            <p>Weighted contribution: {category.weight}%</p>
          </article>
        ))}
      </div>

      <div className="table-wrap">
        <table className="results-table results-table--compact">
          <thead>
            <tr>
              <th>Category</th>
              <th>Factor</th>
              <th>Status</th>
              <th>Weight</th>
              <th>Score</th>
              <th>Observation</th>
            </tr>
          </thead>
          <tbody>
            {readiness.categories.flatMap((category) =>
              category.factors.map((factor) => (
                <tr
                  key={`${category.key}-${factor.code}`}
                  className={getFactorRowClass(factor.status)}
                >
                  <td>{category.label}</td>
                  <td>{factor.label}</td>
                  <td>
                    <span className={getFactorBadgeClass(factor.status)}>{factor.status}</span>
                  </td>
                  <td>{factor.weight}%</td>
                  <td>{factor.score}/100</td>
                  <td>
                    <p>{factor.observation}</p>
                    {factor.source_value || factor.target_value ? (
                      <p className="field-helper field-helper--standalone">
                        Source: {factor.source_value ?? "n/a"} | Target:{" "}
                        {factor.target_value ?? "n/a"}
                      </p>
                    ) : null}
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
