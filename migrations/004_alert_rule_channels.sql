-- Notification channels a rule targets when it fires. Stored, shown in the
-- UI for parity with pktsnmp's rule form/table — not wired to actual
-- dispatch, same as every notification channel in every pkt* app (the
-- Settings -> Notifications "Send Test" button is the entire working
-- notification feature suite-wide; no alert condition anywhere triggers
-- one automatically yet).
ALTER TABLE alert_rules ADD COLUMN channels TEXT NOT NULL DEFAULT '["inapp"]';
