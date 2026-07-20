"""
app/ipam/reconcile_engine.py
-------------------------------
The core of pktIPAM: merges the three independent raw sources
(dhcp_leases, dns_records, arp_entries) plus manually-managed static
entries into the single reconciled `ip_addresses` view the UI and API
read, and detects conflicts between sources. Runs on its own tick,
independent of collector poll cadence — mirrors how pktWiFi's AlertEngine
runs independently of its PollEngine.

Source precedence for merged fields (highest wins): manual static entry >
active DHCP lease > ARP/device sighting. DNS only ever supplies
hostname/dns_ptr, never a status on its own unless it's the *only* source
for that IP (in which case, that's exactly what dns_mismatch flags as
suspicious — see below).

Conflict types detected each tick:
  duplicate_ip           - the same IP has leases from >1 distinct MAC across
                            (possibly different) DHCP collectors
  duplicate_mac           - the same MAC is bound to >1 IP concurrently
                            (across DHCP leases + ARP sightings combined)
  static_dhcp_mismatch    - a manual static reservation's MAC differs from
                            an active DHCP lease's MAC for the same IP
  dns_mismatch             - a DNS A/AAAA record points at an IP with no
                            corroborating lease, ARP sighting, or manual
                            entry at all ("stale DNS")
  subnet_overlap           - two subnets rows have overlapping CIDRs

Conflicts are upserted keyed by (conflict_type, ip_address, subnet_id):
re-detected each tick they stay/become unresolved (resolved_at cleared);
conflicts not re-detected this tick are left alone (a user's manual
resolution isn't clobbered just because the underlying data briefly
disappeared from one poll).
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
from collections import defaultdict
from typing import Optional

import aiosqlite

log = logging.getLogger("pktipam.reconcile_engine")

_TICK_SECONDS = 60


def _find_subnet(ip_obj, subnets: list[dict]) -> Optional[dict]:
    """Longest-prefix-match: the most specific subnet containing this IP."""
    best = None
    for s in subnets:
        try:
            network = ipaddress.ip_network(s["cidr"], strict=False)
        except ValueError:
            continue
        if ip_obj in network:
            if best is None or network.prefixlen > ipaddress.ip_network(best["cidr"], strict=False).prefixlen:
                best = s
    return best


def _usable_count(cidr: str) -> int:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return 0
    if network.version == 4 and network.prefixlen <= 30:
        return network.num_addresses - 2
    return network.num_addresses


async def _upsert_conflict(db: aiosqlite.Connection, conflict_type: str, ip_address: str | None,
                            subnet_id: int | None, details: dict) -> None:
    import json
    await db.execute(
        """INSERT INTO conflicts (conflict_type, ip_address, subnet_id, details_json, detected_at, resolved_at)
           VALUES (?, ?, ?, ?, datetime('now'), NULL)
           ON CONFLICT(conflict_type, ip_address, subnet_id) DO UPDATE SET
             details_json = excluded.details_json, detected_at = datetime('now'), resolved_at = NULL""",
        (conflict_type, ip_address, subnet_id, json.dumps(details)),
    )


async def _log_history(db: aiosqlite.Connection, subnet_id: int, ip_address: str, event: str,
                        status: str | None, mac_address: str | None, hostname: str | None, source: str | None) -> None:
    await db.execute(
        """INSERT INTO ip_address_history (subnet_id, ip_address, event, status, mac_address, hostname, source)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (subnet_id, ip_address, event, status, mac_address, hostname, source),
    )


class ReconcileEngine:
    _instance: "Optional[ReconcileEngine]" = None

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._db_path: str = ""

    async def start(self, db_path: str) -> None:
        ReconcileEngine._instance = self
        self._db_path = db_path
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception as exc:
                log.error(f"Reconcile engine tick error: {exc}")
            await asyncio.sleep(_TICK_SECONDS)

    async def _tick(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute("SELECT * FROM subnets") as cur:
                subnets = [dict(r) for r in await cur.fetchall()]
            async with db.execute("SELECT * FROM dhcp_leases WHERE state IN ('active', 'reserved')") as cur:
                dhcp_rows = [dict(r) for r in await cur.fetchall()]
            async with db.execute("SELECT * FROM dns_records WHERE record_type IN ('A', 'AAAA')") as cur:
                dns_rows = [dict(r) for r in await cur.fetchall()]
            async with db.execute("SELECT * FROM arp_entries") as cur:
                arp_rows = [dict(r) for r in await cur.fetchall()]
            async with db.execute("SELECT * FROM ip_addresses WHERE source = 'manual'") as cur:
                manual_rows = [dict(r) for r in await cur.fetchall()]
            # Snapshot of every non-manual row's prior state, for change
            # detection below — manual entries are excluded since this
            # loop never touches them (they're not derived from
            # dhcp/dns/arp) and have their own history logging in
            # app/api/ip_addresses.py's create/update/delete handlers.
            async with db.execute(
                "SELECT subnet_id, ip_address, status, mac_address, hostname, source FROM ip_addresses WHERE source != 'manual'"
            ) as cur:
                previous_state = {(r["subnet_id"], r["ip_address"]): dict(r) for r in await cur.fetchall()}
            seen_keys: set[tuple[int, str]] = set()

            dhcp_by_ip: dict[str, list[dict]] = defaultdict(list)
            for r in dhcp_rows:
                dhcp_by_ip[r["ip_address"]].append(r)
            dns_by_ip: dict[str, list[dict]] = defaultdict(list)
            for r in dns_rows:
                dns_by_ip[r["value"]].append(r)
            arp_by_ip: dict[str, list[dict]] = defaultdict(list)
            for r in arp_rows:
                arp_by_ip[r["ip_address"]].append(r)
            manual_by_key = {(r["subnet_id"], r["ip_address"]): r for r in manual_rows}

            all_ips = set(dhcp_by_ip) | set(dns_by_ip) | set(arp_by_ip)

            for ip in all_ips:
                try:
                    ip_obj = ipaddress.ip_address(ip)
                except ValueError:
                    continue
                subnet = _find_subnet(ip_obj, subnets)
                if subnet is None:
                    continue

                leases = dhcp_by_ip.get(ip, [])
                dns_recs = dns_by_ip.get(ip, [])
                arps = arp_by_ip.get(ip, [])
                manual = manual_by_key.get((subnet["id"], ip))

                active_leases = [l for l in leases if l["state"] == "active"] or leases
                mac = None
                hostname = None
                status = "used"
                source = "arp"

                if arps:
                    macs = [a["mac_address"] for a in arps if a["mac_address"]]
                    if macs:
                        mac = macs[0]
                    source = "arp"

                if leases:
                    mac = active_leases[0]["mac_address"] or mac
                    hostname = active_leases[0]["hostname"]
                    lease_states = {l["state"] for l in leases}
                    # A DHCP-server-side fixed-IP reservation (all leases
                    # for this IP report state="reserved") is meaningfully
                    # different from a plain dynamic lease — surface it as
                    # its own status instead of collapsing both into "dhcp".
                    status = "reserved" if lease_states == {"reserved"} else "dhcp"
                    source = "dhcp_lease"

                dns_ptr = None
                if dns_recs:
                    hostname = hostname or dns_recs[0]["name"]
                    dns_ptr = dns_recs[0]["name"]
                    if not leases and not arps:
                        status = "used"
                        source = "dns_record"

                if manual:
                    status = "static"
                    mac = manual["mac_address"] or mac
                    hostname = manual["hostname"] or hostname
                    source = "manual"

                # duplicate_ip: >1 distinct MAC actively leasing the same IP
                distinct_lease_macs = {l["mac_address"] for l in leases if l["mac_address"]}
                if len(distinct_lease_macs) > 1:
                    status = "conflict"
                    await _upsert_conflict(db, "duplicate_ip", ip, subnet["id"],
                                            {"macs": sorted(distinct_lease_macs)})

                # static_dhcp_mismatch
                if manual and manual["mac_address"] and active_leases:
                    lease_mac = active_leases[0]["mac_address"]
                    if lease_mac and lease_mac.lower() != manual["mac_address"].lower():
                        status = "conflict"
                        await _upsert_conflict(db, "static_dhcp_mismatch", ip, subnet["id"],
                                                {"static_mac": manual["mac_address"], "lease_mac": lease_mac})

                # dns_mismatch: DNS-only, no corroboration from any other source
                if dns_recs and not leases and not arps and not manual:
                    await _upsert_conflict(db, "dns_mismatch", ip, subnet["id"],
                                            {"dns_name": dns_recs[0]["name"]})

                # History: log only on an actual change, not every tick —
                # a manual entry sharing this IP already owns the row (its
                # own history is logged separately in app/api/
                # ip_addresses.py), so skip logging here to avoid a
                # duplicate/confusing entry attributed to the wrong source.
                key = (subnet["id"], ip)
                seen_keys.add(key)
                if not manual:
                    prior = previous_state.get(key)
                    if prior is None:
                        await _log_history(db, subnet["id"], ip, "first_seen", status, mac, hostname, source)
                    elif prior["mac_address"] != mac or prior["hostname"] != hostname:
                        await _log_history(db, subnet["id"], ip, "changed", status, mac, hostname, source)

                await db.execute(
                    """INSERT INTO ip_addresses
                       (subnet_id, ip_address, status, mac_address, hostname, dns_ptr, source, last_seen, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                       ON CONFLICT(subnet_id, ip_address) DO UPDATE SET
                         status = excluded.status, mac_address = excluded.mac_address,
                         hostname = excluded.hostname, dns_ptr = excluded.dns_ptr,
                         source = CASE WHEN ip_addresses.source = 'manual' THEN 'manual' ELSE excluded.source END,
                         last_seen = datetime('now'), updated_at = datetime('now')
                       WHERE ip_addresses.source != 'manual' OR excluded.source = 'manual'""",
                    (subnet["id"], ip, status, mac, hostname, dns_ptr, source),
                )

            # History: an IP that was previously tracked (non-manual,
            # had a real mac/hostname) but no source saw it this tick has
            # been released — log it and reset the live row back to free
            # instead of leaving stale mac/hostname/status sitting there
            # forever (the upsert above only ever touches IPs currently in
            # all_ips, so without this an IP whose lease expired would
            # keep showing its last-known device indefinitely).
            for key, prior in previous_state.items():
                if key in seen_keys:
                    continue
                if not prior["mac_address"] and not prior["hostname"] and prior["status"] == "free":
                    continue
                prior_subnet_id, prior_ip = key
                await _log_history(db, prior_subnet_id, prior_ip, "released",
                                    "free", prior["mac_address"], prior["hostname"], prior["source"])
                await db.execute(
                    """UPDATE ip_addresses SET status = 'free', mac_address = NULL, hostname = NULL,
                       dns_ptr = NULL, updated_at = datetime('now')
                       WHERE subnet_id = ? AND ip_address = ? AND source != 'manual'""",
                    (prior_subnet_id, prior_ip),
                )

            # duplicate_mac: same MAC bound to >1 concurrently-active IP
            mac_to_ips: dict[str, set] = defaultdict(set)
            for ip, leases in dhcp_by_ip.items():
                for l in leases:
                    if l["mac_address"]:
                        mac_to_ips[l["mac_address"]].add(ip)
            for ip, arps in arp_by_ip.items():
                for a in arps:
                    if a["mac_address"]:
                        mac_to_ips[a["mac_address"]].add(ip)
            for mac, ips in mac_to_ips.items():
                if len(ips) > 1:
                    await _upsert_conflict(db, "duplicate_mac", None, None,
                                            {"mac_address": mac, "ips": sorted(ips)})

            # subnet_overlap
            for i, s1 in enumerate(subnets):
                try:
                    n1 = ipaddress.ip_network(s1["cidr"], strict=False)
                except ValueError:
                    continue
                for s2 in subnets[i + 1:]:
                    try:
                        n2 = ipaddress.ip_network(s2["cidr"], strict=False)
                    except ValueError:
                        continue
                    if n1.version == n2.version and n1.overlaps(n2):
                        await _upsert_conflict(db, "subnet_overlap", None, s1["id"],
                                                {"other_subnet_id": s2["id"], "other_cidr": s2["cidr"]})

            # Utilization history — one row per subnet per tick.
            for subnet in subnets:
                async with db.execute(
                    "SELECT COUNT(*) FROM ip_addresses WHERE subnet_id = ? AND status != 'free'",
                    (subnet["id"],),
                ) as cur:
                    used_row = await cur.fetchone()
                used = used_row[0] if used_row else 0
                total = _usable_count(subnet["cidr"]) or 1
                pct = round(100.0 * used / total, 2)
                await db.execute(
                    """INSERT INTO subnet_utilization_history (subnet_id, used_count, total_count, pct_used)
                       VALUES (?, ?, ?, ?)""",
                    (subnet["id"], used, total, pct),
                )

            await db.commit()
