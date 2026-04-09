export interface HistoryItem {
  request_id: string;
  created_at: string;
  status: string;
  migration_scope: string;
  source_version: string | null;
  target_version: string | null;
  database_size_gb: number | null;
  recommended_approach: string | null;
  confidence: string | null;
  score: number | null;
  rules_version: string | null;
  recommendation_generated_at: string | null;
}

export interface HistoryListResponse {
  items: HistoryItem[];
  total: number;
}
