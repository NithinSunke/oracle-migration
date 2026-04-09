import { navigate } from "../../app/router";
import type { HistoryItem } from "../../types";

interface HistoryTableProps {
  items: HistoryItem[];
  onDownloadReport?: (requestId: string) => void;
  downloadInProgressId?: string | null;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "Not generated";
  }

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatValue(value: string | number | null): string {
  if (value === null || value === undefined || value === "") {
    return "Not available";
  }

  return String(value);
}

export function HistoryTable({
  items,
  onDownloadReport,
  downloadInProgressId,
}: HistoryTableProps) {
  return (
    <div className="table-wrap">
      <table className="results-table">
        <thead>
          <tr>
            <th>Request ID</th>
            <th>Created</th>
            <th>Scope</th>
            <th>Source</th>
            <th>Target</th>
            <th>Recommended</th>
            <th>Confidence</th>
            <th>Rules</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.request_id}>
              <td>{item.request_id}</td>
              <td>{formatDate(item.created_at)}</td>
              <td>{item.migration_scope}</td>
              <td>{formatValue(item.source_version)}</td>
              <td>{formatValue(item.target_version)}</td>
              <td>{formatValue(item.recommended_approach)}</td>
              <td>{formatValue(item.confidence)}</td>
              <td>{formatValue(item.rules_version)}</td>
              <td>
                <div className="inline-actions">
                  <button
                    className="nav-link"
                    type="button"
                    onClick={() => navigate(`/migration/${item.request_id}`)}
                  >
                    Assessment
                  </button>
                  {item.recommended_approach ? (
                    <button
                      className="nav-link"
                      type="button"
                      onClick={() => navigate(`/recommendation/${item.request_id}`)}
                    >
                      Recommendation
                    </button>
                  ) : null}
                  {item.recommended_approach && onDownloadReport ? (
                    <button
                      className="nav-link"
                      type="button"
                      onClick={() => onDownloadReport(item.request_id)}
                      disabled={downloadInProgressId === item.request_id}
                    >
                      {downloadInProgressId === item.request_id ? "Downloading" : "Report"}
                    </button>
                  ) : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
