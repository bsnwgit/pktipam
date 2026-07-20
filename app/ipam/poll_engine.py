"""
app/ipam/poll_engine.py
--------------------------
Background loop that polls every enabled collector on its own configured
interval and persists what it returns into that category's raw table
(dhcp_leases, dns_records, arp_entries). Each poll is treated as a full
current-state snapshot for that collector — the previous poll's rows for
that collector_id are replaced, not merged — since every implemented
collector (Kea's lease4-get-all, an AXFR zone transfer, an SNMP ARP walk)
already returns its complete current state, not a delta.

This mirrors pktWiFi's poll_engine.py (one file, one tick loop, health
tracked on the collectors row) generalized to dispatch by category, since
the three categories persist into structurally different tables. The
cross-source merge into `ip_addresses` + conflict detection is a separate
concern — see app/ipam/reconcile_engine.py, which runs on its own
independent tick.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import aiosqlite

from app.ipam.collectors.crypto import decrypt_config, decrypt_str
from app.ipam.collectors.dhcp.registry import get_dhcp_collector_instance
from app.ipam.collectors.dns.registry import get_dns_collector_instance
from app.ipam.collectors.device.registry import get_device_collector_instance

log = logging.getLogger("pktipam.poll_engine")

_TICK_SECONDS = 15


async def resolve_credential(db: aiosqlite.Connection, config: dict) -> dict:
    """If a collector's config references a saved SNMP credential (device/
    snmp_generic's credential_id field, set via the Settings -> SNMP
    Credentials picker instead of typing auth inline), decrypt it and
    merge the resulting auth fields into the config the collector actually
    reads. Keeps individual collectors as pure functions of a flat config
    dict — credential resolution happens once, centrally, here, so the
    same logic covers both the scheduled poller and the manual "Poll Now"
    button (app/api/collectors.py) instead of duplicating it in each.
    A no-op for any config without a credential_id (every non-SNMP
    collector, and future device types that don't use this pattern)."""
    credential_id = config.get("credential_id")
    if not credential_id:
        return config
    async with db.execute("SELECT * FROM snmp_credentials WHERE id = ?", (credential_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise ValueError(f"SNMP credential id {credential_id} not found — check Settings -> SNMP Credentials")
    cred = dict(row)
    resolved = dict(config)
    resolved["version"] = cred["snmp_version"]
    resolved["community"] = cred["community"]
    resolved["username"] = cred["security_name"]
    resolved["auth_protocol"] = cred["auth_protocol"]
    resolved["auth_password"] = decrypt_str(cred["auth_key_enc"])
    resolved["priv_protocol"] = cred["priv_protocol"]
    resolved["priv_password"] = decrypt_str(cred["priv_key_enc"])
    return resolved


async def resolve_integration(db: aiosqlite.Connection, config: dict) -> dict:
    """If a collector's config references a named pktsnmp connection
    (device/pktsnmp_suite's integration_id field, set via the Settings ->
    Security -> Suite Integration picker instead of typing base_url/
    suite_token inline), look it up and merge the resulting fields into
    the config the collector actually reads. Same centralized-resolution
    pattern as resolve_credential above — a no-op for any config without
    an integration_id."""
    integration_id = config.get("integration_id")
    if not integration_id:
        return config
    async with db.execute("SELECT * FROM integrations WHERE id = ?", (integration_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise ValueError(f"pktsnmp integration id {integration_id} not found — check Settings -> Security -> Suite Integration")
    resolved = dict(config)
    resolved["base_url"] = row["base_url"]
    resolved["suite_token"] = row["suite_token"]
    return resolved


async def resolve_device_config(db: aiosqlite.Connection, config: dict) -> dict:
    """Runs every centralized config-resolution step for a device
    collector — currently SNMP credential lookup and pktsnmp integration
    lookup, each a no-op if its key isn't present in the config."""
    config = await resolve_credential(db, config)
    config = await resolve_integration(db, config)
    return config

# Placeholder hostnames some DHCP servers report for a client that never
# sent one via DHCP option 12 (e.g. Pi-hole/dnsmasq's "*") — no real name
# exists for these, so no DNS record can be synthesized for them either.
_NO_HOSTNAME = {"", "*"}


async def _persist_dhcp(db: aiosqlite.Connection, collector_id: int, result) -> int:
    await db.execute("DELETE FROM dhcp_leases WHERE collector_id = ?", (collector_id,))
    for lease in result.leases:
        if not lease.ip_address:
            continue
        await db.execute(
            """INSERT OR IGNORE INTO dhcp_leases
               (collector_id, ip_address, mac_address, hostname, client_id, starts_at, ends_at, state, raw_json, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (collector_id, lease.ip_address, lease.mac_address, lease.hostname, lease.client_id,
             lease.starts_at, lease.ends_at, lease.state, json.dumps(lease.raw)),
        )

    # A DHCP server that's also handing out the client's own hostname
    # effectively makes that name resolvable (this is exactly how Pi-hole/
    # dnsmasq's combined DHCP+DNS works — see the pktIPAM DNS Records page
    # discussion) even though it's not a "DNS record" in any collector's
    # own API. Surface that here as a synthetic A record tagged to this
    # same DHCP collector, so it shows up in the DNS Records page too.
    # Full replace-on-poll (same pattern as dhcp_leases above) means a
    # lease that renews with a new IP, loses its hostname, or disappears
    # entirely is reflected — no stale record survives past the next poll.
    await db.execute("DELETE FROM dns_records WHERE collector_id = ?", (collector_id,))
    for lease in result.leases:
        if not lease.ip_address or lease.state not in ("active", "reserved"):
            continue
        hostname = (lease.hostname or "").strip()
        if hostname in _NO_HOSTNAME:
            continue
        await db.execute(
            """INSERT OR IGNORE INTO dns_records
               (collector_id, zone, name, record_type, value, ttl, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (collector_id, "dhcp", hostname, "A", lease.ip_address, None),
        )

    return len(result.leases)


async def _persist_dns(db: aiosqlite.Connection, collector_id: int, result) -> int:
    await db.execute("DELETE FROM dns_records WHERE collector_id = ?", (collector_id,))
    for rec in result.records:
        if not rec.value:
            continue
        await db.execute(
            """INSERT OR IGNORE INTO dns_records
               (collector_id, zone, name, record_type, value, ttl, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (collector_id, rec.zone, rec.name, rec.record_type, rec.value, rec.ttl),
        )
    return len(result.records)


async def _persist_device(db: aiosqlite.Connection, collector_id: int, result) -> int:
    await db.execute("DELETE FROM arp_entries WHERE collector_id = ?", (collector_id,))
    for entry in result.entries:
        if not entry.ip_address:
            continue
        await db.execute(
            """INSERT OR IGNORE INTO arp_entries
               (collector_id, source, device_label, ip_address, mac_address, interface, vlan_tag, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (collector_id, "native_snmp" if entry.mac_address else "pktsnmp",
             entry.device_label, entry.ip_address, entry.mac_address, entry.interface, entry.vlan_tag),
        )
    return len(result.entries)


_PERSISTERS = {
    "dhcp": _persist_dhcp,
    "dns": _persist_dns,
    "device": _persist_device,
}

_REGISTRIES = {
    "dhcp": get_dhcp_collector_instance,
    "dns": get_dns_collector_instance,
    "device": get_device_collector_instance,
}


class PollEngine:
    _instance: "Optional[PollEngine]" = None

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._db_path: str = ""

    async def start(self, db_path: str) -> None:
        PollEngine._instance = self
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
                log.error(f"Poll engine tick error: {exc}")
            await asyncio.sleep(_TICK_SECONDS)

    async def _tick(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM collectors WHERE enabled = 1 AND
                   (last_poll_at IS NULL OR
                    last_poll_at < datetime('now', '-' || poll_interval_sec || ' seconds'))"""
            ) as cur:
                due = await cur.fetchall()
            for row in due:
                await self._poll_one(db, row)

    async def _poll_one(self, db: aiosqlite.Connection, row: aiosqlite.Row) -> None:
        category = row["category"]
        get_instance = _REGISTRIES.get(category)
        persist = _PERSISTERS.get(category)
        if get_instance is None or persist is None:
            log.warning(f"Collector '{row['name']}' has unknown category '{category}'")
            return

        try:
            config = await resolve_device_config(db, decrypt_config(row["config_json"]))
        except ValueError as exc:
            log.warning(f"Collector '{row['name']}' credential resolution failed: {exc}")
            await db.execute(
                "UPDATE collectors SET status = 'error', last_error = ?, last_poll_at = datetime('now') WHERE id = ?",
                (str(exc), row["id"]),
            )
            await db.commit()
            return

        collector = get_instance(row["collector_type"], config)
        if collector is None:
            return
        try:
            result = await collector.poll()
            count = await persist(db, row["id"], result)
            await db.execute(
                "UPDATE collectors SET status = 'ok', last_error = NULL, last_poll_at = datetime('now') WHERE id = ?",
                (row["id"],),
            )
            log.debug(f"Collector '{row['name']}' ({category}) polled ok — {count} row(s)")
        except Exception as exc:
            log.warning(f"Collector '{row['name']}' poll failed: {exc}")
            await db.execute(
                "UPDATE collectors SET status = 'error', last_error = ?, last_poll_at = datetime('now') WHERE id = ?",
                (str(exc), row["id"]),
            )
        await db.commit()
