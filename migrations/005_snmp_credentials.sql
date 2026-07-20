-- Named, reusable SNMP credential sets — create once here, assign to any
-- number of device collectors instead of re-entering SNMP auth per
-- collector. Mirrors pktsnmp's snmp_credentials table/UX exactly (its
-- Settings -> SNMP -> Credentials tab).
CREATE TABLE IF NOT EXISTS snmp_credentials (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL UNIQUE,
    description    TEXT NOT NULL DEFAULT '',
    snmp_version   TEXT NOT NULL DEFAULT 'v2c',   -- v2c | v3
    community      TEXT NOT NULL DEFAULT 'public', -- v2c only
    security_name  TEXT NOT NULL DEFAULT '',       -- v3 username
    security_level TEXT NOT NULL DEFAULT 'noAuthNoPriv', -- noAuthNoPriv | authNoPriv | authPriv
    auth_protocol  TEXT NOT NULL DEFAULT 'SHA',    -- SHA | MD5 — matches what the SNMP walk code actually supports
    auth_key_enc   TEXT,
    priv_protocol  TEXT NOT NULL DEFAULT 'AES',    -- AES | DES — matches what the SNMP walk code actually supports
    priv_key_enc   TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_snmp_credentials_name ON snmp_credentials(name);
