-- Phase 5 scenario execution persistence.
-- Uses dedicated tables so existing incident-platform tables remain compatible.

CREATE TABLE IF NOT EXISTS scenario_catalog (
    scenario_id VARCHAR(120) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(120) NOT NULL,
    description TEXT NOT NULL,
    risk_level VARCHAR(30) NOT NULL,
    injector_type VARCHAR(120) NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    expected_signals JSONB NOT NULL DEFAULT '[]'::jsonb,
    recovery_required BOOLEAN NOT NULL DEFAULT TRUE,
    verification_required BOOLEAN NOT NULL DEFAULT TRUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scenario_execution_runs (
    run_id UUID PRIMARY KEY,
    scenario_id VARCHAR(120) NOT NULL REFERENCES scenario_catalog(scenario_id),
    incident_id UUID NULL,
    status VARCHAR(40) NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    recovery_result JSONB NOT NULL DEFAULT '{}'::jsonb,
    verification_result JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ NULL,
    timeout_seconds INTEGER NOT NULL DEFAULT 30,
    created_by VARCHAR(120) NOT NULL DEFAULT 'operator'
);

CREATE INDEX IF NOT EXISTS idx_scenario_runs_scenario
    ON scenario_execution_runs(scenario_id);

CREATE INDEX IF NOT EXISTS idx_scenario_runs_incident
    ON scenario_execution_runs(incident_id);

CREATE INDEX IF NOT EXISTS idx_scenario_runs_status
    ON scenario_execution_runs(status);

CREATE TABLE IF NOT EXISTS scenario_audit_log (
    audit_id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES scenario_execution_runs(run_id),
    action VARCHAR(80) NOT NULL,
    actor VARCHAR(120) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
