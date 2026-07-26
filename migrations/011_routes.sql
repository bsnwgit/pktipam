-- Raw device routing-table entries (per-collector, full-replace-on-poll,
-- same pattern as arp_entries). Populated by device collectors that can
-- report a routing table (currently snmp_generic's ipCidrRouteTable walk)
-- and consumed by the reconcile engine to flag subnets with no discovered
-- route and routes whose next-hop disagrees with a subnet's configured
-- gateway.
CREATE TABLE IF NOT EXISTS routes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collector_id  INTEGER REFERENCES collectors(id) ON DELETE CASCADE,
    device_label  TEXT,
    destination   TEXT NOT NULL,   -- CIDR, e.g. 10.0.1.0/24 (0.0.0.0/0 for default route)
    next_hop      TEXT,
    interface     TEXT,
    protocol      TEXT,            -- local | static | rip | ospf | bgp | eigrp | isis | other
    metric        INTEGER,
    last_seen     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (collector_id, destination, next_hop, interface)
);
CREATE INDEX IF NOT EXISTS idx_routes_destination ON routes(destination);
