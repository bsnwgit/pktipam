-- Support multiple named pktsnmp (or future sibling-app) integrations
-- instead of one singleton row per app_name. Each instance gets a
-- user-given `name`, referenced by the pktsnmp_suite device collector's
-- integration_id picker (Collectors -> Add Collector -> Device) instead
-- of typing base_url/suite_token inline every time. SQLite can't ALTER a
-- UNIQUE constraint away, so this rebuilds the table.
CREATE TABLE integrations_new (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL UNIQUE,   -- user-given label, e.g. "Main pktsnmp"
    app_name          TEXT NOT NULL DEFAULT 'pktsnmp',
    base_url          TEXT NOT NULL DEFAULT '',
    suite_token       TEXT NOT NULL DEFAULT '',
    enabled           INTEGER NOT NULL DEFAULT 1,
    health_status     TEXT NOT NULL DEFAULT 'unknown',
    last_health_check TEXT,
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Carry over any existing singleton row (only ever had app_name='pktsnmp'
-- with a real base_url) as a named instance so a configured connection
-- isn't silently dropped by this migration.
INSERT INTO integrations_new (name, app_name, base_url, suite_token, enabled, health_status, last_health_check, updated_at)
SELECT
    CASE WHEN app_name = 'pktsnmp' THEN 'pktsnmp' ELSE app_name END,
    app_name, base_url, suite_token, enabled, health_status, last_health_check, updated_at
FROM integrations
WHERE base_url != '' OR suite_token != '';

DROP TABLE integrations;
ALTER TABLE integrations_new RENAME TO integrations;

CREATE INDEX IF NOT EXISTS idx_integrations_app_name ON integrations(app_name);
