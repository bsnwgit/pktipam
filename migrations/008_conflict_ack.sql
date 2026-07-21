-- Acknowledgement trail for conflicts, independent of resolved_at/resolved_by —
-- lets History (resolved) entries be marked as reviewed, same pattern as alert_events.
ALTER TABLE conflicts ADD COLUMN acked INTEGER NOT NULL DEFAULT 0;
ALTER TABLE conflicts ADD COLUMN acked_by TEXT;
ALTER TABLE conflicts ADD COLUMN acked_at TEXT;
