import { useMemo, useState } from "react";

import type { MigrationRemediationPack } from "../types";

interface RemediationPackPanelProps {
  pack: MigrationRemediationPack | null | undefined;
  requestId: string;
}

function downloadSqlFile(filename: string, content: string): void {
  const blob = new Blob([content], { type: "application/sql" });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export function RemediationPackPanel({
  pack,
  requestId,
}: RemediationPackPanelProps) {
  const [approvedCategories, setApprovedCategories] = useState<Record<string, boolean>>({});

  if (!pack || !pack.scripts.length) {
    return null;
  }

  const groupedScripts = useMemo(() => {
    const groups = new Map<string, typeof pack.scripts>();
    for (const script of pack.scripts) {
      const current = groups.get(script.category) ?? [];
      current.push(script);
      groups.set(script.category, current);
    }
    return Array.from(groups.entries());
  }, [pack.scripts]);

  return (
    <section className="panel panel--inner">
      <div className="section-heading">
        <h2>SQL Remediation Pack</h2>
        <p>{pack.summary}</p>
      </div>

      <div className="callout-card">
        <p className="callout-label">Target Preparation Wizard</p>
        <p>
          Use these approval gates before import to confirm target schemas, tablespaces, temporary
          tablespaces, roles, quotas, grants, ACLs, and object storage credentials are ready.
        </p>
        <div className="toggle-inline">
          {groupedScripts.map(([category, scripts]) => (
            <label key={category} className="checkbox-inline">
              <input
                type="checkbox"
                checked={approvedCategories[category] ?? false}
                onChange={(event) =>
                  setApprovedCategories((current) => ({
                    ...current,
                    [category]: event.target.checked,
                  }))
                }
              />
              <span>
                Approve {category.replace(/_/g, " ")} ({scripts.length})
              </span>
            </label>
          ))}
        </div>
      </div>

      <div className="summary-actions">
        <button
          className="secondary-button"
          type="button"
          onClick={() =>
            downloadSqlFile(
              `${requestId.toLowerCase()}_remediation_pack.sql`,
              pack.combined_sql,
            )
          }
        >
          Download SQL Pack
        </button>
      </div>

      <div className="table-wrap">
        <table className="results-table results-table--compact">
          <thead>
            <tr>
              <th>Gate</th>
              <th>Script</th>
              <th>Category</th>
              <th>Status</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>
            {pack.scripts.map((script) => (
              <tr key={script.code}>
                <td>
                  <span
                    className={
                      approvedCategories[script.category]
                        ? "soft-badge soft-badge--success"
                        : "soft-badge soft-badge--warning"
                    }
                  >
                    {approvedCategories[script.category] ? "Approved" : "Pending"}
                  </span>
                </td>
                <td>{script.label}</td>
                <td>{script.category.replace(/_/g, " ")}</td>
                <td>{script.status}</td>
                <td>
                  <p>{script.summary}</p>
                  <pre className="runbook-code-block">
                    <code>{script.sql}</code>
                  </pre>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
