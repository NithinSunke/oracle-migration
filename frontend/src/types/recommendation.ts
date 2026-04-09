export interface RankedApproach {
  approach: string;
  score: number;
  reason: string;
}

export interface SecondaryOption {
  approach: string;
  score: number;
  why: string[];
}

export interface MetadataEnrichmentSummary {
  status: "COLLECTED" | "PARTIAL" | "FAILED";
  source: import("./migration").OracleSourceMetadata | null;
  collected_fields: string[];
  applied_fields: string[];
  errors: string[];
  notes: string[];
}

export interface RecommendationResponse {
  request_id: string;
  recommended_approach: string;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  score: number;
  why: string[];
  companion_tools: string[];
  prerequisites: string[];
  risk_flags: string[];
  secondary_option: SecondaryOption | null;
  rejected_approaches: RankedApproach[];
  manual_review_flags: string[];
  rules_version: string;
  metadata_enrichment?: MetadataEnrichmentSummary | null;
  generated_at: string;
}
