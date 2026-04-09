CREATE TABLE IF NOT EXISTS migration_requests (
    request_id VARCHAR(64) PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(32) NOT NULL,
    source_payload JSONB NOT NULL,
    target_payload JSONB NOT NULL,
    scope_payload JSONB NOT NULL,
    business_payload JSONB NOT NULL,
    connectivity_payload JSONB NOT NULL,
    features_payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendation_results (
    recommendation_id VARCHAR(36) PRIMARY KEY,
    request_id VARCHAR(64) NOT NULL REFERENCES migration_requests(request_id),
    recommended_approach VARCHAR(64) NOT NULL,
    confidence VARCHAR(16) NOT NULL,
    score INTEGER NOT NULL,
    rules_version VARCHAR(32) NOT NULL,
    request_payload JSONB NOT NULL,
    response_payload JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_recommendation_results_request_id
    ON recommendation_results (request_id);

CREATE TABLE IF NOT EXISTS recommendation_rule_audit (
    audit_id VARCHAR(36) PRIMARY KEY,
    request_id VARCHAR(64) NOT NULL,
    recommendation_id VARCHAR(36) NOT NULL REFERENCES recommendation_results(recommendation_id),
    recommended_approach VARCHAR(64) NOT NULL,
    score INTEGER NOT NULL,
    rules_version VARCHAR(32) NOT NULL,
    request_payload JSONB NOT NULL,
    evaluation_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_recommendation_rule_audit_request_id
    ON recommendation_rule_audit (request_id);

CREATE TABLE IF NOT EXISTS datapump_jobs (
    job_id VARCHAR(32) PRIMARY KEY,
    request_id VARCHAR(64),
    task_id VARCHAR(64),
    job_name VARCHAR(128),
    operation VARCHAR(16) NOT NULL,
    scope VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    dry_run BOOLEAN NOT NULL DEFAULT FALSE,
    source_connection_payload JSONB NOT NULL,
    target_connection_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    options_payload JSONB NOT NULL,
    result_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_datapump_jobs_request_id
    ON datapump_jobs (request_id);

CREATE INDEX IF NOT EXISTS idx_datapump_jobs_task_id
    ON datapump_jobs (task_id);
