BEGIN;

CREATE TABLE IF NOT EXISTS sef_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO sef_meta(key, value)
SELECT 'schema_version', '0.1.0'
WHERE NOT EXISTS (
    SELECT 1 FROM sef_meta WHERE key = 'schema_version'
);

CREATE TABLE IF NOT EXISTS sef_missions (
    id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL CHECK (schema_version = '0.1.0'),
    runtime_task_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    title TEXT NOT NULL,
    goal TEXT NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('created', 'running', 'review', 'completed', 'blocked', 'failed', 'cancelled')
    ),
    search_plan_id TEXT NOT NULL,
    search_plan_status TEXT NOT NULL CHECK (
        search_plan_status IN ('planned', 'running', 'completed', 'failed')
    ),
    search_query_count INTEGER NOT NULL DEFAULT 0 CHECK (search_query_count >= 0),
    search_required_source_kinds_json TEXT NOT NULL DEFAULT '[]',
    search_started_at TEXT,
    search_completed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        search_plan_status <> 'completed'
        OR (search_query_count > 0 AND search_completed_at IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_sef_missions_correlation
    ON sef_missions(correlation_id);

CREATE TABLE IF NOT EXISTS sef_entities (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES sef_missions(id),
    correlation_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sef_entity_identifiers (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES sef_missions(id),
    entity_id TEXT NOT NULL REFERENCES sef_entities(id),
    correlation_id TEXT NOT NULL,
    scheme TEXT NOT NULL,
    value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    UNIQUE(entity_id, scheme, normalized_value)
);

CREATE TABLE IF NOT EXISTS sef_sources (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES sef_missions(id),
    correlation_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (
        kind IN (
            'official_registry',
            'first_party',
            'licensed_provider',
            'news_media',
            'industry_catalog',
            'scientific_database',
            'social',
            'manual'
        )
    ),
    publisher TEXT NOT NULL,
    homepage_url TEXT NOT NULL,
    terms_ref TEXT
);

CREATE TABLE IF NOT EXISTS sef_documents (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES sef_missions(id),
    source_id TEXT NOT NULL REFERENCES sef_sources(id),
    correlation_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    accessed_at TEXT NOT NULL,
    fetch_status TEXT NOT NULL CHECK (fetch_status IN ('fetched', 'failed', 'blocked')),
    content_digest TEXT,
    media_type TEXT,
    CHECK (fetch_status <> 'fetched' OR content_digest IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS sef_provider_calls (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES sef_missions(id),
    correlation_id TEXT NOT NULL,
    provider_ref TEXT NOT NULL,
    operation TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('succeeded', 'partial', 'failed', 'skipped')),
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sef_discovery_hints (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES sef_missions(id),
    provider_call_id TEXT NOT NULL REFERENCES sef_provider_calls(id),
    correlation_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    snippet TEXT NOT NULL,
    discovered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sef_evidence (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES sef_missions(id),
    source_id TEXT NOT NULL REFERENCES sef_sources(id),
    document_id TEXT NOT NULL REFERENCES sef_documents(id),
    correlation_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL CHECK (
        evidence_type IN ('document_quote', 'official_record', 'dataset_row')
    ),
    quote TEXT NOT NULL CHECK (length(quote) > 0),
    locator TEXT NOT NULL CHECK (length(locator) > 0),
    observed_at TEXT NOT NULL,
    digest TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sef_claims (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES sef_missions(id),
    entity_id TEXT NOT NULL REFERENCES sef_entities(id),
    correlation_id TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value_json TEXT,
    state TEXT NOT NULL CHECK (
        state IN ('candidate', 'confirmed', 'contradicted', 'not_found')
    ),
    critical INTEGER NOT NULL DEFAULT 0 CHECK (critical IN (0, 1)),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sef_claims_subject
    ON sef_claims(entity_id, predicate);

CREATE TABLE IF NOT EXISTS sef_claim_evidence (
    claim_id TEXT NOT NULL REFERENCES sef_claims(id),
    evidence_id TEXT NOT NULL REFERENCES sef_evidence(id),
    relation TEXT NOT NULL CHECK (relation IN ('supports', 'contradicts')),
    PRIMARY KEY (claim_id, evidence_id, relation)
);

CREATE TABLE IF NOT EXISTS sef_cost_events (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES sef_missions(id),
    provider_call_id TEXT REFERENCES sef_provider_calls(id),
    correlation_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    amount NUMERIC(18, 6) NOT NULL CHECK (amount >= 0),
    units NUMERIC(18, 6) NOT NULL CHECK (units >= 0),
    unit_name TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sef_review_decisions (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES sef_missions(id),
    correlation_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('claim', 'evidence', 'report')),
    target_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (
        decision IN ('approved', 'rejected', 'needs_more_evidence')
    ),
    reviewer_ref TEXT NOT NULL,
    reason TEXT NOT NULL,
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sef_reports (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES sef_missions(id),
    correlation_id TEXT NOT NULL,
    title TEXT NOT NULL,
    client_facing INTEGER NOT NULL DEFAULT 1 CHECK (client_facing IN (0, 1)),
    generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sef_report_claims (
    report_id TEXT NOT NULL REFERENCES sef_reports(id),
    claim_id TEXT NOT NULL REFERENCES sef_claims(id),
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    PRIMARY KEY (report_id, claim_id),
    UNIQUE(report_id, ordinal)
);

COMMIT;
