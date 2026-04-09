import type { MigrationRecord } from "./migration";
import type { RecommendationResponse } from "./recommendation";

export interface ReportSummary {
  request_id: string;
  recommended_approach: string;
  confidence: string;
  score: number;
  rules_version: string;
  why: string[];
}

export interface RecommendationReport {
  report_id: string;
  request_id: string;
  generated_at: string;
  format: string;
  summary: ReportSummary;
  migration: MigrationRecord;
  recommendation: RecommendationResponse;
}
