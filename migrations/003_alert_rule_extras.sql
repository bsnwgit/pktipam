-- Cooldown: suppresses a rule from re-firing for the same target within
-- this many minutes after its last active alert_event auto-resolves, so a
-- flapping condition doesn't spam new events every 30s eval tick.
ALTER TABLE alert_rules ADD COLUMN cooldown_min INTEGER NOT NULL DEFAULT 15;
