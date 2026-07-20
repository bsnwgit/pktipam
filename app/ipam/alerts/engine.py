"""
app/ipam/alerts/engine.py
----------------------------
Lightweight IPAM alert engine. Runs on an interval, evaluates enabled
alert_rules against the current state of subnets / ip_addresses /
conflicts / collectors, and opens/keeps-open/auto-resolves alert_events.

Supported condition_type values:
  subnet_near_exhaustion  - a subnet's latest utilization pct_used exceeds `threshold`
  ip_conflict_detected     - an unresolved row exists in `conflicts`
  dhcp_pool_exhausted       - a subnet with an active DHCP collector has
                              pct_used >= `threshold` (default 95) — a
                              stricter/near-100 variant of subnet_near_exhaustion
  dns_ptr_mismatch          - shorthand for the `dns_mismatch` conflict type
  collector_down            - a collector's status = 'error'

This intentionally does not attempt to replicate pktSNMP's much larger
generic OID-threshold engine — pktIPAM's v1 alert surface is a small,
fixed set of conditions, not arbitrary user-defined rules (same approach
pktWiFi took for its own alert engine).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import aiosqlite

log = logging.getLogger("pktipam.alerts")

_EVAL_INTERVAL = 30  # seconds


class AlertEngine:
    _instance: "Optional[AlertEngine]" = None

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._db_path: str = ""

    async def start(self, db_path: str) -> None:
        AlertEngine._instance = self
        self._db_path = db_path
        self._task = asyncio.create_task(self._run_loop())
        log.info("Alert engine started")

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
                await self._evaluate()
            except Exception as e:
                log.error(f"Alert engine evaluation error: {e}")
            await asyncio.sleep(_EVAL_INTERVAL)

    async def _evaluate(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM alert_rules WHERE enabled = 1") as cur:
                rules = await cur.fetchall()

            for rule in rules:
                handler = _HANDLERS.get(rule["condition_type"])
                if handler:
                    await handler(db, rule)
            await db.commit()


async def _fire_or_keep(db: aiosqlite.Connection, rule, subnet_id=None, ip_address=None,
                         message: str = "", value: Optional[float] = None):
    """Open a new alert_event if one isn't already active for this rule+target,
    and it hasn't auto-resolved within the rule's cooldown window (so a
    flapping condition doesn't reopen a new event every 30s eval tick)."""
    async with db.execute(
        """SELECT id FROM alert_events
           WHERE rule_id = ? AND active = 1
             AND subnet_id IS ? AND ip_address IS ?""",
        (rule["id"], subnet_id, ip_address),
    ) as cur:
        existing = await cur.fetchone()
    if existing:
        return

    cooldown_min = rule["cooldown_min"] or 0
    if cooldown_min:
        async with db.execute(
            """SELECT id FROM alert_events
               WHERE rule_id = ? AND subnet_id IS ? AND ip_address IS ?
                 AND resolved_at >= datetime('now', ?)
               ORDER BY resolved_at DESC LIMIT 1""",
            (rule["id"], subnet_id, ip_address, f"-{cooldown_min} minutes"),
        ) as cur:
            recently_resolved = await cur.fetchone()
        if recently_resolved:
            return

    await db.execute(
        """INSERT INTO alert_events
           (rule_id, subnet_id, ip_address, severity, message, value, threshold, active)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
        (rule["id"], subnet_id, ip_address, rule["severity"], message, value, rule["threshold"]),
    )


async def _auto_resolve(db: aiosqlite.Connection, rule, still_bad_subnet_ids: set, still_bad_ips: set):
    """Auto-resolve active alerts for this rule whose target is no longer in violation."""
    async with db.execute(
        "SELECT id, subnet_id, ip_address FROM alert_events WHERE rule_id = ? AND active = 1",
        (rule["id"],),
    ) as cur:
        active = await cur.fetchall()
    for row in active:
        subnet_ok = row["subnet_id"] is None or row["subnet_id"] not in still_bad_subnet_ids
        ip_ok = row["ip_address"] is None or row["ip_address"] not in still_bad_ips
        if subnet_ok and ip_ok:
            await db.execute(
                """UPDATE alert_events SET active = 0, resolved = 1, auto_resolved = 1,
                   resolved_at = datetime('now') WHERE id = ?""",
                (row["id"],),
            )


async def _latest_utilization(db: aiosqlite.Connection) -> dict[int, float]:
    async with db.execute(
        """SELECT subnet_id, pct_used FROM subnet_utilization_history
           WHERE id IN (SELECT MAX(id) FROM subnet_utilization_history GROUP BY subnet_id)"""
    ) as cur:
        rows = await cur.fetchall()
    return {r["subnet_id"]: r["pct_used"] for r in rows}


async def _check_subnet_near_exhaustion(db: aiosqlite.Connection, rule) -> None:
    threshold = rule["threshold"] or 85
    latest = await _latest_utilization(db)
    bad_ids = set()
    for subnet_id, pct in latest.items():
        if pct >= threshold:
            bad_ids.add(subnet_id)
            async with db.execute("SELECT cidr FROM subnets WHERE id = ?", (subnet_id,)) as cur:
                s = await cur.fetchone()
            cidr = s["cidr"] if s else str(subnet_id)
            await _fire_or_keep(db, rule, subnet_id=subnet_id, value=pct,
                                 message=f"Subnet {cidr} is {pct:.0f}% utilized")
    await _auto_resolve(db, rule, bad_ids, set())


async def _check_dhcp_pool_exhausted(db: aiosqlite.Connection, rule) -> None:
    threshold = rule["threshold"] or 95
    latest = await _latest_utilization(db)
    bad_ids = set()
    for subnet_id, pct in latest.items():
        if pct >= threshold:
            bad_ids.add(subnet_id)
            async with db.execute("SELECT cidr FROM subnets WHERE id = ?", (subnet_id,)) as cur:
                s = await cur.fetchone()
            cidr = s["cidr"] if s else str(subnet_id)
            await _fire_or_keep(db, rule, subnet_id=subnet_id, value=pct,
                                 message=f"Subnet {cidr} is nearly out of addresses ({pct:.0f}% used)")
    await _auto_resolve(db, rule, bad_ids, set())


async def _check_ip_conflict_detected(db: aiosqlite.Connection, rule) -> None:
    async with db.execute("SELECT * FROM conflicts WHERE resolved_at IS NULL") as cur:
        rows = await cur.fetchall()
    bad_ips = set()
    for c in rows:
        if not c["ip_address"]:
            continue
        bad_ips.add(c["ip_address"])
        await _fire_or_keep(db, rule, subnet_id=c["subnet_id"], ip_address=c["ip_address"],
                             message=f"{c['conflict_type']} conflict on {c['ip_address']}")
    await _auto_resolve(db, rule, set(), bad_ips)


async def _check_dns_ptr_mismatch(db: aiosqlite.Connection, rule) -> None:
    async with db.execute(
        "SELECT * FROM conflicts WHERE conflict_type = 'dns_mismatch' AND resolved_at IS NULL"
    ) as cur:
        rows = await cur.fetchall()
    bad_ips = set()
    for c in rows:
        if not c["ip_address"]:
            continue
        bad_ips.add(c["ip_address"])
        details = json.loads(c["details_json"] or "{}")
        await _fire_or_keep(db, rule, subnet_id=c["subnet_id"], ip_address=c["ip_address"],
                             message=f"DNS record '{details.get('dns_name', '?')}' points at "
                                     f"{c['ip_address']} with no corroborating lease/ARP sighting")
    await _auto_resolve(db, rule, set(), bad_ips)


async def _check_collector_down(db: aiosqlite.Connection, rule) -> None:
    async with db.execute("SELECT id, name FROM collectors WHERE enabled = 1 AND status = 'error'") as cur:
        rows = await cur.fetchall()
    bad_ips = set()
    for c in rows:
        marker = f"collector:{c['id']}"
        bad_ips.add(marker)
        await _fire_or_keep(db, rule, ip_address=marker,
                             message=f"Collector '{c['name']}' is in an error state")
    await _auto_resolve(db, rule, set(), bad_ips)


_HANDLERS = {
    "subnet_near_exhaustion": _check_subnet_near_exhaustion,
    "ip_conflict_detected": _check_ip_conflict_detected,
    "dhcp_pool_exhausted": _check_dhcp_pool_exhausted,
    "dns_ptr_mismatch": _check_dns_ptr_mismatch,
    "collector_down": _check_collector_down,
}
