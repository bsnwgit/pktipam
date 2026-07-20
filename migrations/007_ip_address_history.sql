-- Historical record of which device (MAC/hostname) held a given IP over
-- time. Written by the reconcile engine only when something actually
-- changes for an IP (not once per 60s tick) — so this stays proportional
-- to real turnover, not to poll frequency.
CREATE TABLE IF NOT EXISTS ip_address_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    subnet_id     INTEGER NOT NULL REFERENCES subnets(id) ON DELETE CASCADE,
    ip_address    TEXT NOT NULL,
    event         TEXT NOT NULL,   -- first_seen | changed | released
    status        TEXT,
    mac_address   TEXT,
    hostname      TEXT,
    source        TEXT,
    recorded_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ip_address_history_ip ON ip_address_history(ip_address);
CREATE INDEX IF NOT EXISTS idx_ip_address_history_subnet_ip ON ip_address_history(subnet_id, ip_address);
CREATE INDEX IF NOT EXISTS idx_ip_address_history_recorded_at ON ip_address_history(recorded_at);
