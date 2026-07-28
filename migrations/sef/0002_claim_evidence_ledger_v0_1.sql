BEGIN;

CREATE TABLE IF NOT EXISTS sef_evidence_ledger_metadata (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES sef_missions(id),
    evidence_id TEXT NOT NULL REFERENCES sef_evidence(id),
    correlation_id TEXT NOT NULL,
    tier TEXT NOT NULL CHECK (
        tier IN (
            'tier_1_authority',
            'tier_2_first_party',
            'tier_3_independent',
            'tier_4_signal',
            'unassessed'
        )
    ),
    valid_at TEXT NOT NULL,
    fresh_until TEXT,
    recorded_at TEXT NOT NULL,
    UNIQUE(evidence_id),
    CHECK (fresh_until IS NULL OR fresh_until >= valid_at)
);

CREATE INDEX IF NOT EXISTS idx_sef_evidence_ledger_mission
    ON sef_evidence_ledger_metadata(mission_id, evidence_id);

CREATE TABLE IF NOT EXISTS sef_predicate_freshness_policies (
    predicate TEXT PRIMARY KEY,
    max_age_days INTEGER NOT NULL CHECK (max_age_days >= 0),
    accepted_tiers_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sef_claim_conflict_groups (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES sef_missions(id),
    entity_id TEXT NOT NULL REFERENCES sef_entities(id),
    predicate TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('unresolved', 'resolved')),
    accepted_claim_id TEXT REFERENCES sef_claims(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (
        (state = 'resolved' AND accepted_claim_id IS NOT NULL)
        OR (state = 'unresolved' AND accepted_claim_id IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_sef_conflict_subject
    ON sef_claim_conflict_groups(mission_id, entity_id, predicate);

CREATE TABLE IF NOT EXISTS sef_claim_conflict_members (
    conflict_group_id TEXT NOT NULL REFERENCES sef_claim_conflict_groups(id),
    claim_id TEXT NOT NULL REFERENCES sef_claims(id),
    value_digest TEXT NOT NULL,
    PRIMARY KEY (conflict_group_id, claim_id)
);

CREATE TABLE IF NOT EXISTS sef_ledger_snapshots (
    id TEXT PRIMARY KEY,
    mission_id TEXT NOT NULL REFERENCES sef_missions(id),
    correlation_id TEXT NOT NULL,
    as_of TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(mission_id, as_of)
);

COMMIT;
