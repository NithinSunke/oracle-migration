# Oracle Migration Decision Engine

## Goal

Build an internal decision engine that recommends the best Oracle-to-Oracle migration approach based on user inputs, source/target characteristics, downtime constraints, and operational requirements.

The engine should recommend one primary approach from:

- `DATAPUMP`
- `RMAN_BACKUP_RESTORE`
- `RMAN_DUPLICATE`
- `DATA_GUARD`
- `GOLDENGATE`
- `ZDM`
- `MANUAL_REVIEW`

The engine should also return:

- confidence
- why the method was selected
- rejected methods with reasons
- prerequisites
- risk flags
- companion tools such as `AutoUpgrade`

## Design Principles

- Use rules first, not ML.
- Keep size as a weighting factor, not the only factor.
- Separate `eligibility` from `scoring`.
- Return explainable recommendations.
- Flag unsupported or ambiguous cases for manual review.
- Allow future extension for cloud targets and non-Oracle sources.

## High-Level Flow

1. Collect migration intake form inputs.
2. Normalize and validate values.
3. Derive technical facts from input.
4. Evaluate hard eligibility rules for each approach.
5. Score all eligible approaches.
6. Rank approaches.
7. Attach prerequisites, warnings, and companion steps.
8. Return recommendation payload.

## Input Model

### Migration Request

```json
{
  "request_id": "MIG-2026-0001",
  "source": {
    "oracle_version": "19c",
    "deployment_type": "NON_CDB",
    "platform": "Linux x86-64",
    "storage_type": "ASM",
    "database_size_gb": 6200,
    "largest_table_gb": 850,
    "daily_change_rate_gb": 180,
    "peak_redo_mb_per_sec": 42,
    "character_set": "AL32UTF8",
    "tde_enabled": true,
    "rac_enabled": true,
    "dataguard_enabled": false,
    "archivelog_enabled": true
  },
  "target": {
    "oracle_version": "19c",
    "deployment_type": "CDB_PDB",
    "platform": "Linux x86-64",
    "storage_type": "ASM",
    "target_is_exadata": false,
    "same_endian": true
  },
  "scope": {
    "migration_scope": "FULL_DATABASE",
    "schema_count": 14,
    "need_schema_remap": false,
    "need_tablespace_remap": false,
    "need_reorg": false,
    "subset_only": false
  },
  "business": {
    "downtime_window_minutes": 20,
    "fallback_required": true,
    "near_zero_downtime_required": true,
    "regulated_workload": true
  },
  "connectivity": {
    "network_bandwidth_mbps": 5000,
    "direct_host_connectivity": true,
    "shared_storage_available": false
  },
  "features": {
    "need_version_upgrade": false,
    "need_cross_platform_move": false,
    "need_non_cdb_to_pdb_conversion": true,
    "goldengate_license_available": true,
    "zdm_supported_target": false
  }
}
```

## Derived Fields

These should be computed before scoring:

- `is_large_db`: `database_size_gb >= 5000`
- `is_huge_db`: `database_size_gb >= 10000`
- `is_low_downtime`: `downtime_window_minutes <= 30`
- `is_ultra_low_downtime`: `downtime_window_minutes <= 5`
- `same_version_family`
- `same_platform`
- `same_endian`
- `full_database_move`
- `logical_transformation_needed`
- `physical_move_preferred`
- `upgrade_in_scope`
- `dg_candidate`
- `gg_candidate`
- `zdm_candidate`

## Decision Approach

### 1. Eligibility Rules

Every method gets one of:

- `ELIGIBLE`
- `CONDITIONALLY_ELIGIBLE`
- `NOT_ELIGIBLE`

Examples:

- `DATA_GUARD` is not eligible if `migration_scope != FULL_DATABASE`.
- `DATA_GUARD` is not eligible if the move requires major logical transformation.
- `GOLDENGATE` is not eligible if `goldengate_license_available = false`.
- `ZDM` is not eligible if `zdm_supported_target = false`.
- `DATAPUMP` is conditionally eligible for very large databases with tight downtime.
- `RMAN_BACKUP_RESTORE` is not a good fit when downtime is very small, but it can still be eligible.

### 2. Scoring Rules

Each eligible approach gets:

- base score
- positive score adjustments
- negative score adjustments
- mandatory warnings

Final score formula:

```text
final_score = base_score + sum(positive_weights) - sum(negative_weights)
```

### 3. Confidence

Confidence is based on:

- score gap between rank 1 and rank 2
- number of unresolved risk flags
- number of assumptions
- number of conditional eligibility checks

Suggested thresholds:

- `HIGH`: winner leads by 20+ points and has no blocking risk
- `MEDIUM`: winner leads by 10-19 points or has manageable flags
- `LOW`: close scores or multiple unresolved flags

## Recommended Rule Set

### Data Pump

Best when:

- subset or schema-level migration
- remap/reorg is required
- logical transformation is required
- downtime is acceptable

Penalties:

- very large database
- high change rate
- very small downtime window

### RMAN Backup Restore

Best when:

- full database move
- physical copy is acceptable
- outage window is moderate to large
- same platform or supported restore path exists

Penalties:

- subset migration
- logical transformation required
- ultra-low downtime

### RMAN Duplicate

Best when:

- full database clone or rehearsal is needed
- direct connectivity exists
- target environment build needs automation

Penalties:

- subset migration
- logical transformation required

### Data Guard

Best when:

- full database Oracle-to-Oracle
- minimal downtime required
- physical standby and switchover are feasible
- rollback/fallback matters

Penalties:

- schema remap needed
- subset migration
- major transformation needed

### GoldenGate

Best when:

- ultra-low downtime required
- high change rate workload
- phased synchronization or active cutover prep needed
- Data Guard is not suitable

Penalties:

- license unavailable
- team operational maturity is low
- migration is simple and outage is acceptable

### ZDM

Best when:

- target is in supported ZDM scope
- enterprise orchestration is required
- Oracle MAA-aligned workflow is preferred

Penalties:

- unsupported target
- small/simple migration where ZDM adds unnecessary complexity

## Pseudocode

```text
function recommend(request):
  normalized = normalize(request)
  derived = deriveFacts(normalized)
  evaluations = []

  for method in methods:
    eligibility = evaluateEligibility(method, normalized, derived)
    if eligibility.status == "NOT_ELIGIBLE":
      evaluations.append(rejected(method, eligibility.reasons))
      continue

    score = baseScore(method)
    score += applyPositiveWeights(method, normalized, derived)
    score -= applyNegativeWeights(method, normalized, derived)

    evaluations.append(candidate(method, score, eligibility, reasons, warnings))

  ranked = sortDescending(evaluations where candidate)
  recommendation = ranked[0] if any candidate else MANUAL_REVIEW
  confidence = computeConfidence(ranked, recommendation)
  companionTools = deriveCompanionTools(normalized, derived, recommendation)

  return buildResponse(recommendation, confidence, ranked, companionTools)
```

## API Contract

### Request

`POST /api/v1/migration/recommendation`

```json
{
  "request_id": "MIG-2026-0001",
  "source": {},
  "target": {},
  "scope": {},
  "business": {},
  "connectivity": {},
  "features": {}
}
```

### Response

```json
{
  "request_id": "MIG-2026-0001",
  "recommended_approach": "DATA_GUARD",
  "confidence": "HIGH",
  "score": 92,
  "why": [
    "Full database migration",
    "Downtime window is 20 minutes",
    "Near-zero downtime is required",
    "Same platform and endian enable physical standby approach",
    "Fallback requirement favors switchover-based migration"
  ],
  "companion_tools": [
    "RMAN",
    "Data Guard Broker",
    "AutoUpgrade"
  ],
  "prerequisites": [
    "ARCHIVELOG mode enabled",
    "Standby redo logs sized correctly",
    "Network throughput validated",
    "TDE wallet migration planned",
    "Non-CDB to PDB conversion steps validated"
  ],
  "risk_flags": [
    "CDB/PDB conversion requires additional rehearsal",
    "Application connection redirection must be scripted"
  ],
  "secondary_option": {
    "approach": "GOLDENGATE",
    "score": 76,
    "why": [
      "Low downtime requirement",
      "GoldenGate license available"
    ]
  },
  "rejected_approaches": [
    {
      "approach": "DATAPUMP",
      "reason": "Database size and downtime window make logical export/import risky"
    },
    {
      "approach": "ZDM",
      "reason": "Target is outside supported ZDM scope"
    }
  ],
  "manual_review_flags": [
    "Validate PDB conversion path",
    "Confirm Data Guard compatibility for current patch levels"
  ]
}
```

## Minimal Database Schema For The Control Application

### `migration_requests`

- `request_id`
- `created_at`
- `created_by`
- `source_payload_json`
- `target_payload_json`
- `scope_payload_json`
- `business_payload_json`
- `connectivity_payload_json`
- `features_payload_json`
- `status`

### `migration_recommendations`

- `recommendation_id`
- `request_id`
- `recommended_approach`
- `confidence`
- `score`
- `response_json`
- `rules_version`
- `created_at`

### `migration_rule_audit`

- `audit_id`
- `request_id`
- `approach`
- `eligibility_status`
- `score`
- `matched_rules_json`
- `rejected_rules_json`
- `created_at`

## Suggested Implementation Modules

- `intake-service`
  - validates request payloads
- `rule-engine`
  - evaluates eligibility and scoring
- `knowledge-base`
  - stores rule definitions and prerequisites
- `explainability-service`
  - renders why a method was selected
- `report-service`
  - exports HTML/PDF/JSON recommendation reports

## Future Extension Path

Phase 1:

- Oracle-to-Oracle on-prem only
- rules in JSON
- synchronous recommendation API

Phase 2:

- add effort estimation
- add cutover checklist generation
- add version-upgrade path suggestions

Phase 3:

- add cloud targets
- add cost estimation
- add execution orchestration hooks

## Initial Recommendation Defaults

- If `full_database_move = true` and `is_low_downtime = true` and `logical_transformation_needed = false`, prefer `DATA_GUARD`.
- If `full_database_move = true` and `downtime_window_minutes > 240`, prefer `RMAN_BACKUP_RESTORE`.
- If `subset_only = true` or `need_schema_remap = true` or `need_reorg = true`, prefer `DATAPUMP`.
- If `is_ultra_low_downtime = true` and `goldengate_license_available = true` and `DATA_GUARD` is not suitable, prefer `GOLDENGATE`.
- If `target_is_exadata = true` and `zdm_supported_target = true`, promote `ZDM`.
- If `need_version_upgrade = true`, add `AutoUpgrade` as a companion tool, not a replacement recommendation.

## Notes

- `AutoUpgrade` should be modeled as a companion workflow, not as a primary migration method.
- `RMAN_DUPLICATE` is often a strong secondary recommendation for rehearsal even when not selected as the final migration path.
- `MANUAL_REVIEW` should be returned whenever blockers or unsupported combinations are detected.
