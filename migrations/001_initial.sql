-- pktIPAM initial schema

CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT NOT NULL UNIQUE,
    email             TEXT NOT NULL UNIQUE,
    hashed_password   TEXT NOT NULL,
    role              TEXT NOT NULL DEFAULT 'viewer',   -- admin | analyst | viewer
    is_active         INTEGER NOT NULL DEFAULT 1,
    auth_provider     TEXT NOT NULL DEFAULT 'local',     -- local | saml
    is_default_admin  INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    last_login        TEXT
);

-- Generic key/value store for runtime settings (JSON-encoded values),
-- mirrors the pattern used across the pkt* suite.
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS app_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level       TEXT NOT NULL,
    level_no    INTEGER NOT NULL,
    logger      TEXT NOT NULL,
    message     TEXT NOT NULL,
    exc_info    TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_app_logs_created ON app_logs(created_at);

-- Per-user external API keys (IP-reputation/WHOIS style lookups), keyed by
-- username rather than user id — suite-proxy (pktHub) requests share a
-- single pseudo user id of 0 across every hub-authenticated identity.
CREATE TABLE IF NOT EXISTS user_api_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL,
    provider    TEXT NOT NULL,
    api_key     TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (username, provider)
);

-- ── Collectors ──────────────────────────────────────────────────────────────
-- One row per configured data source across three categories: dhcp, dns,
-- device. `config_json` holds collector-specific settings; any secret
-- fields inside it (passwords, API keys, SNMP v3 auth) are Fernet-encrypted
-- at rest — see app/ipam/collectors/*/base.py.
CREATE TABLE IF NOT EXISTS collectors (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    category          TEXT NOT NULL,    -- dhcp | dns | device
    collector_type    TEXT NOT NULL,    -- kea | windows_dhcp | isc_dhcpd_legacy | infoblox_dhcp |
                                         -- axfr_generic | powerdns_api | windows_dns | infoblox_dns |
                                         -- snmp_generic | pktsnmp_suite
    config_json       TEXT NOT NULL DEFAULT '{}',
    poll_interval_sec INTEGER NOT NULL DEFAULT 300,
    enabled           INTEGER NOT NULL DEFAULT 1,
    status            TEXT NOT NULL DEFAULT 'unknown',   -- ok | error | unknown
    last_poll_at      TEXT,
    last_error        TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_collectors_category ON collectors(category);

-- ── VLANs ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS vlans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    vlan_tag    INTEGER NOT NULL,
    name        TEXT NOT NULL,
    site        TEXT,
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (vlan_tag, site)
);

-- ── Subnets ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS subnets (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    cidr              TEXT NOT NULL UNIQUE,     -- e.g. 10.0.1.0/24
    vlan_id           INTEGER REFERENCES vlans(id) ON DELETE SET NULL,
    site              TEXT,
    description       TEXT,
    gateway           TEXT,
    parent_subnet_id  INTEGER REFERENCES subnets(id) ON DELETE SET NULL,
    source            TEXT NOT NULL DEFAULT 'manual',   -- manual | discovered
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_subnets_parent ON subnets(parent_subnet_id);
CREATE INDEX IF NOT EXISTS idx_subnets_vlan ON subnets(vlan_id);

-- ── IP addresses (the reconciled view — what the UI reads) ─────────────────
CREATE TABLE IF NOT EXISTS ip_addresses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    subnet_id     INTEGER NOT NULL REFERENCES subnets(id) ON DELETE CASCADE,
    ip_address    TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'free',   -- free | used | reserved | dhcp | static | conflict
    mac_address   TEXT,
    hostname      TEXT,
    dns_ptr       TEXT,
    description   TEXT,
    owner         TEXT,
    tags_json     TEXT NOT NULL DEFAULT '[]',
    source        TEXT NOT NULL DEFAULT 'manual', -- manual | dhcp_lease | dns_record | arp
    last_seen     TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (subnet_id, ip_address)
);
CREATE INDEX IF NOT EXISTS idx_ip_addresses_subnet ON ip_addresses(subnet_id);
CREATE INDEX IF NOT EXISTS idx_ip_addresses_status ON ip_addresses(status);
CREATE INDEX IF NOT EXISTS idx_ip_addresses_mac ON ip_addresses(mac_address);
CREATE INDEX IF NOT EXISTS idx_ip_addresses_ip ON ip_addresses(ip_address);

-- ── Raw DHCP leases (per-collector, upserted on each poll) ─────────────────
CREATE TABLE IF NOT EXISTS dhcp_leases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collector_id  INTEGER NOT NULL REFERENCES collectors(id) ON DELETE CASCADE,
    ip_address    TEXT NOT NULL,
    mac_address   TEXT,
    hostname      TEXT,
    client_id     TEXT,
    starts_at     TEXT,
    ends_at       TEXT,
    state         TEXT NOT NULL DEFAULT 'active',   -- active | expired | released | reserved
    raw_json      TEXT NOT NULL DEFAULT '{}',
    last_seen     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (collector_id, ip_address)
);
CREATE INDEX IF NOT EXISTS idx_dhcp_leases_ip ON dhcp_leases(ip_address);
CREATE INDEX IF NOT EXISTS idx_dhcp_leases_mac ON dhcp_leases(mac_address);

-- ── Raw DNS records (per-collector, upserted on each poll) ─────────────────
CREATE TABLE IF NOT EXISTS dns_records (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collector_id  INTEGER NOT NULL REFERENCES collectors(id) ON DELETE CASCADE,
    zone          TEXT NOT NULL,
    name          TEXT NOT NULL,
    record_type   TEXT NOT NULL,   -- A | AAAA | PTR | CNAME
    value         TEXT NOT NULL,
    ttl           INTEGER,
    last_seen     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (collector_id, zone, name, record_type, value)
);
CREATE INDEX IF NOT EXISTS idx_dns_records_value ON dns_records(value);
CREATE INDEX IF NOT EXISTS idx_dns_records_name ON dns_records(name);

-- ── Raw ARP/device-derived IP<->MAC bindings ────────────────────────────────
CREATE TABLE IF NOT EXISTS arp_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collector_id  INTEGER REFERENCES collectors(id) ON DELETE CASCADE,
    source        TEXT NOT NULL,   -- native_snmp | pktsnmp
    device_label  TEXT,
    ip_address    TEXT NOT NULL,
    mac_address   TEXT,
    interface     TEXT,
    vlan_tag      INTEGER,
    last_seen     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (collector_id, ip_address)
);
CREATE INDEX IF NOT EXISTS idx_arp_entries_ip ON arp_entries(ip_address);
CREATE INDEX IF NOT EXISTS idx_arp_entries_mac ON arp_entries(mac_address);

-- ── Conflicts detected by the reconciliation engine ─────────────────────────
CREATE TABLE IF NOT EXISTS conflicts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    conflict_type  TEXT NOT NULL,   -- duplicate_ip | duplicate_mac | static_dhcp_mismatch | dns_mismatch | subnet_overlap
    ip_address     TEXT,
    subnet_id      INTEGER REFERENCES subnets(id) ON DELETE CASCADE,
    details_json   TEXT NOT NULL DEFAULT '{}',
    detected_at    TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at    TEXT,
    resolved_by    TEXT,
    UNIQUE (conflict_type, ip_address, subnet_id)
);
CREATE INDEX IF NOT EXISTS idx_conflicts_unresolved ON conflicts(resolved_at);

-- ── Subnet utilization history (trend charts) ───────────────────────────────
CREATE TABLE IF NOT EXISTS subnet_utilization_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subnet_id    INTEGER NOT NULL REFERENCES subnets(id) ON DELETE CASCADE,
    used_count   INTEGER NOT NULL,
    total_count  INTEGER NOT NULL,
    pct_used     REAL NOT NULL,
    recorded_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_subnet_util_subnet_ts ON subnet_utilization_history(subnet_id, recorded_at);

-- ── Alerting ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alert_rules (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    condition_type TEXT NOT NULL,   -- subnet_near_exhaustion | ip_conflict_detected | dhcp_pool_exhausted | dns_ptr_mismatch | collector_down
    threshold      REAL,
    severity       TEXT NOT NULL DEFAULT 'warning',   -- info | warning | critical
    enabled        INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS alert_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id          INTEGER REFERENCES alert_rules(id) ON DELETE SET NULL,
    subnet_id        INTEGER REFERENCES subnets(id) ON DELETE SET NULL,
    ip_address       TEXT,
    severity         TEXT NOT NULL DEFAULT 'warning',
    message          TEXT NOT NULL,
    value            REAL,
    threshold        REAL,
    active           INTEGER NOT NULL DEFAULT 1,
    acked            INTEGER NOT NULL DEFAULT 0,
    acked_by         TEXT,
    acked_at         TEXT,
    resolved         INTEGER NOT NULL DEFAULT 0,
    auto_resolved    INTEGER NOT NULL DEFAULT 0,
    resolved_at      TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_alert_events_active ON alert_events(active, acked);

-- ── Outbound suite integrations (pktIPAM acting as a client of sibling apps) ─
-- base_url + suite_token for calling pktsnmp directly (device/ARP data), in
-- addition to pktIPAM's own inbound /api/suite/* for pktHub to call in.
CREATE TABLE IF NOT EXISTS integrations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name          TEXT NOT NULL UNIQUE,   -- pktsnmp
    base_url          TEXT NOT NULL DEFAULT '',
    suite_token       TEXT NOT NULL DEFAULT '',
    enabled           INTEGER NOT NULL DEFAULT 0,
    health_status     TEXT NOT NULL DEFAULT 'unknown',
    last_health_check TEXT,
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
