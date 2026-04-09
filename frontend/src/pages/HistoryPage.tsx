import { useEffect, useState } from "react";

import { AppFrame } from "../components/AppFrame";
import { StatusPanel } from "../components/StatusPanel";
import { HistoryTable } from "../features/history/HistoryTable";
import { api, ApiError } from "../services/api";
import type { HistoryItem } from "../types";

export function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [downloadInProgressId, setDownloadInProgressId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadHistory() {
      setIsLoading(true);
      setErrorMessage(null);

      try {
        const response = await api.listHistory();
        if (!active) {
          return;
        }
        setItems(response.items);
      } catch (error) {
        if (!active) {
          return;
        }
        if (error instanceof ApiError) {
          setErrorMessage(error.message);
        } else {
          setErrorMessage("Unable to load recommendation history.");
        }
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    void loadHistory();

    return () => {
      active = false;
    };
  }, []);

  async function handleDownloadReport(requestId: string) {
    setDownloadInProgressId(requestId);
    setErrorMessage(null);

    try {
      await api.downloadReport(requestId);
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("Unable to download the report.");
      }
    } finally {
      setDownloadInProgressId((current) => (current === requestId ? null : current));
    }
  }

  return (
    <AppFrame
      eyebrow="Assessment History"
      title="Review saved migration assessments and reopen recommendations"
      summary="Browse stored Oracle migration assessments, compare recommendation outcomes, and export JSON reports for audit or review workflows."
    >
      {isLoading ? (
        <StatusPanel
          title="Loading history"
          description="Fetching stored assessments and their latest recommendation summary."
        />
      ) : null}

      {!isLoading && errorMessage ? (
        <StatusPanel title="History unavailable" description={errorMessage} tone="error" />
      ) : null}

      {!isLoading && !errorMessage && items.length === 0 ? (
        <StatusPanel
          title="No saved assessments yet"
          description="Create and save a migration assessment first, then return here to review history and reports."
        />
      ) : null}

      {!isLoading && items.length > 0 ? (
        <section className="panel">
          <div className="section-heading">
            <h2>Recommendation History</h2>
            <p>Each row shows the latest stored recommendation for the assessment when one exists.</p>
          </div>
          <HistoryTable
            items={items}
            onDownloadReport={handleDownloadReport}
            downloadInProgressId={downloadInProgressId}
          />
        </section>
      ) : null}
    </AppFrame>
  );
}
