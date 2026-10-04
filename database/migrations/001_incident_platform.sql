-- Infrastructure Intelligence
-- Member 2 / Incident Platform
-- Migration: 001_incident_platform.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    priority VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    version INTEGER NOT NULL DEFAULT 1,
    affected_services JSONB NOT NULL DEFAULT '[]'::jsonb,
    primary_suspect TEXT,
    confidence DOUBLE PRECISION,

    CONSTRAINT incidents_status_check
        CHECK (
            status IN (
                'DETECTED',
                'ACKNOWLEDGED',
                'TRIAGED',
                'INVESTIGATING',
                'MITIGATING',
                'RECOVERY_VERIFY',
                'RESOLVED',
                'FALSE_POSITIVE',
                'REOPENED'
            )
        ),

    CONSTRAINT incidents_priority_check
        CHECK (
            priority IN ('P0', 'P1', 'P2', 'P3')
        ),

    CONSTRAINT incidents_version_check
        CHECK (version >= 1),

    CONSTRAINT incidents_confidence_check
        CHECK (
            confidence IS NULL
            OR (confidence >= 0 AND confidence <= 1)
        )
);

CREATE TABLE IF NOT EXISTS incident_events (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,
    event_id UUID NOT NULL UNIQUE,
    event_type VARCHAR(80) NOT NULL,
    sequence BIGSERIAL NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,

    CONSTRAINT incident_events_sequence_unique
        UNIQUE (incident_id, sequence)
);

CREATE TABLE IF NOT EXISTS anomalies (
    id UUID PRIMARY KEY,
    incident_id UUID
        REFERENCES incidents(id)
        ON DELETE SET NULL,
    service_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    observed_value DOUBLE PRECISION NOT NULL,
    expected_value DOUBLE PRECISION,
    deviation DOUBLE PRECISION,
    severity VARCHAR(20) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,

    CONSTRAINT anomalies_confidence_check
        CHECK (confidence >= 0 AND confidence <= 1)
);

CREATE TABLE IF NOT EXISTS evidence (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,
    evidence_type VARCHAR(40) NOT NULL,
    source_ref TEXT NOT NULL,
    weight DOUBLE PRECISION,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS hypotheses (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,
    entity_id TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    reasons JSONB NOT NULL,
    rank INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,
    title TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    assignee TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS comments (
    id UUID PRIMARY KEY,
    incident_id UUID NOT NULL
        REFERENCES incidents(id)
        ON DELETE CASCADE,
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY,
    incident_id UUID
        REFERENCES incidents(id)
        ON DELETE SET NULL,
    actor TEXT NOT NULL,
    action VARCHAR(80) NOT NULL,
    target TEXT,
    result VARCHAR(30) NOT NULL,
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    request_hash TEXT NOT NULL,
    response_status INTEGER NOT NULL,
    response_body JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scenarios (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    injector_type TEXT NOT NULL,
    parameters JSONB NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS scenario_runs (
    id UUID PRIMARY KEY,
    scenario_id TEXT NOT NULL
        REFERENCES scenarios(id),
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    status VARCHAR(30) NOT NULL,
    injected BOOLEAN NOT NULL DEFAULT false,
    recovered BOOLEAN NOT NULL DEFAULT false,
    verified BOOLEAN NOT NULL DEFAULT false,
    incident_id UUID
        REFERENCES incidents(id),
    result JSONB
);

CREATE TABLE IF NOT EXISTS evaluations (
    id UUID PRIMARY KEY,
    scenario_run_id UUID NOT NULL
        REFERENCES scenario_runs(id),
    detection_seconds DOUBLE PRECISION,
    correlation_seconds DOUBLE PRECISION,
    rca_seconds DOUBLE PRECISION,
    recovery_seconds DOUBLE PRECISION,
    rca_correct BOOLEAN,
    recovery_verified BOOLEAN,
    false_positive BOOLEAN,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_incidents_status_priority
    ON incidents(status, priority, created_at);

CREATE INDEX IF NOT EXISTS idx_incident_events_incident_sequence
    ON incident_events(incident_id, sequence);

CREATE INDEX IF NOT EXISTS idx_hypotheses_incident_score
    ON hypotheses(incident_id, score DESC);

CREATE INDEX IF NOT EXISTS idx_anomalies_incident
    ON anomalies(incident_id);

CREATE INDEX IF NOT EXISTS idx_evidence_incident
    ON evidence(incident_id);
