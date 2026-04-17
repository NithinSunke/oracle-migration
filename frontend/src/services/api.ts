import type {
  HistoryListResponse,
  DataPumpJobCreate,
  DataPumpCapabilitiesResponse,
  DataPumpConnectivityDiagnosticsRequest,
  DataPumpConnectivityDiagnosticsResponse,
  DataPumpJobListResponse,
  DataPumpJobPurgeResponse,
  DataPumpJobRecord,
  MetadataEnrichmentSummary,
  MigrationCompatibilityAssessment,
  MigrationCreate,
  MigrationRecord,
  RecommendationReport,
  RecommendationResponse,
} from "../types";

export interface AuthPayload {
  username: string;
  password: string;
  persistent: boolean;
}

export interface AuthSessionResponse {
  user_id: string;
  username: string;
  authenticated_at: string;
  persistent: boolean;
}

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "/api/v1";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function formatErrorDetail(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (
          item &&
          typeof item === "object" &&
          "msg" in item &&
          typeof item.msg === "string"
        ) {
          const location =
            "loc" in item && Array.isArray(item.loc)
              ? item.loc
                  .filter((part: unknown): part is string | number =>
                    typeof part === "string" || typeof part === "number",
                  )
                  .join(".")
              : "";

          return location ? `${location}: ${item.msg}` : item.msg;
        }

        if (typeof item === "string" && item.trim()) {
          return item;
        }

        return null;
      })
      .filter((message): message is string => Boolean(message));

    if (messages.length > 0) {
      return messages.join(" | ");
    }
  }

  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? {});
  if (!(init?.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers,
    ...init,
  });

  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`;

    try {
      const payload = (await response.json()) as { detail?: unknown };
      const formattedDetail = formatErrorDetail(payload.detail);
      if (formattedDetail) {
        message = formattedDetail;
      }
    } catch {
      // Keep the fallback error message when the response is not JSON.
    }

    throw new ApiError(message, response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  login(payload: AuthPayload): Promise<AuthSessionResponse> {
    return request<AuthSessionResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  register(payload: AuthPayload): Promise<AuthSessionResponse> {
    return request<AuthSessionResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  listHistory(limit = 50): Promise<HistoryListResponse> {
    return request<HistoryListResponse>(`/history?limit=${limit}`);
  },
  testSourceMetadataConnection(
    payload: MigrationCreate,
  ): Promise<MetadataEnrichmentSummary> {
    return request<MetadataEnrichmentSummary>("/metadata/test", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  importSourceMetadataHtml(file: File): Promise<MetadataEnrichmentSummary> {
    const formData = new FormData();
    formData.append("file", file);
    return request<MetadataEnrichmentSummary>("/metadata/import-html", {
      method: "POST",
      body: formData,
    });
  },
  validateMigration(
    payload: MigrationCreate,
  ): Promise<MigrationCompatibilityAssessment> {
    return request<MigrationCompatibilityAssessment>("/metadata/validate-migration", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  createMigration(payload: MigrationCreate): Promise<MigrationRecord> {
    return request<MigrationRecord>("/migrations", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  getMigration(requestId: string): Promise<MigrationRecord> {
    return request<MigrationRecord>(`/migrations/${requestId}`);
  },
  createRecommendation(payload: MigrationCreate): Promise<RecommendationResponse> {
    return request<RecommendationResponse>("/recommendations", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  getRecommendation(requestId: string): Promise<RecommendationResponse> {
    return request<RecommendationResponse>(`/recommendations/${requestId}`);
  },
  getReport(requestId: string): Promise<RecommendationReport> {
    return request<RecommendationReport>(`/reports/${requestId}`);
  },
  async downloadReport(requestId: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/reports/${requestId}`, {
      method: "POST",
    });

    if (!response.ok) {
      let message = `Request failed with status ${response.status}.`;

      try {
        const payload = (await response.json()) as { detail?: unknown };
        const formattedDetail = formatErrorDetail(payload.detail);
        if (formattedDetail) {
          message = formattedDetail;
        }
      } catch {
        // Keep the fallback error message when the response is not JSON.
      }

      throw new ApiError(message, response.status);
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${requestId}-report.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
  createDataPumpJob(payload: DataPumpJobCreate): Promise<DataPumpJobRecord> {
    return request<DataPumpJobRecord>("/transfers/datapump/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  getDataPumpCapabilities(): Promise<DataPumpCapabilitiesResponse> {
    return request<DataPumpCapabilitiesResponse>("/transfers/datapump/capabilities");
  },
  runDataPumpDiagnostics(
    payload: DataPumpConnectivityDiagnosticsRequest,
  ): Promise<DataPumpConnectivityDiagnosticsResponse> {
    return request<DataPumpConnectivityDiagnosticsResponse>("/transfers/datapump/diagnostics", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
  listDataPumpJobs(limit = 25): Promise<DataPumpJobListResponse> {
    return request<DataPumpJobListResponse>(`/transfers/datapump/jobs?limit=${limit}`);
  },
  purgeDataPumpJobsHistory(): Promise<DataPumpJobPurgeResponse> {
    return request<DataPumpJobPurgeResponse>("/transfers/datapump/jobs/history", {
      method: "DELETE",
    });
  },
  getDataPumpJob(jobId: string): Promise<DataPumpJobRecord> {
    return request<DataPumpJobRecord>(`/transfers/datapump/jobs/${jobId}`);
  },
  retryDataPumpJob(jobId: string): Promise<DataPumpJobRecord> {
    return request<DataPumpJobRecord>(`/transfers/datapump/jobs/${jobId}/retry`, {
      method: "POST",
    });
  },
};
