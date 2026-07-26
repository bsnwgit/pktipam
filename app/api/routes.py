"""
/api/routes/* — read-only view of routing-table rows (app/ipam/poll_engine.py
owns writing these).

Grouped by (destination, next_hop) rather than returned raw: the same
physical route is commonly reported by more than one collector at once —
e.g. a device reachable via both a direct SNMP collector and the pktsnmp
suite-integration collector (see device/pktsnmp_suite.py), or two
different devices on the same segment each reporting their own connected
route to it — which otherwise shows up as literal duplicate rows with
nothing to tell them apart but collector_id/timestamp. device_label and
interface are GROUP_CONCAT'd (deduplicated) so the row still shows every
contributing device/interface instead of picking one arbitrarily and
hiding the rest.

Also left-joins subnets on destination to surface subnet_gateway: a
directly-connected ("local" protocol) route has no real next-hop in any
protocol — SNMP, NetFlow, BGP, none of them — since the reporting device
itself is the router for that segment, there is nothing to forward
through. subnet_gateway is not SNMP-observed routing data — it's the
subnet's admin-configured gateway (Subnets page) — so the frontend must
show it as a distinct, clearly-labeled fallback, never merged into
next_hop as if it were the same kind of data.
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends

from app.database import get_db
from app.dependencies import CurrentUser

router = APIRouter()


def _route_out(row) -> dict:
    return {
        "destination": row["destination"], "next_hop": row["next_hop"], "interface": row["interface"],
        "protocol": row["protocol"], "metric": row["metric"],
        "device_label": row["device_label"], "last_seen": row["last_seen"],
        "subnet_gateway": row["subnet_gateway"],
    }


@router.get("")
async def list_routes(
    user: CurrentUser,
    collector_id: int | None = None,
    protocol: str | None = None,
    search: str | None = None,
    limit: int = 500,
    db: aiosqlite.Connection = Depends(get_db),
):
    query = "SELECT * FROM routes WHERE 1=1"
    params: list = []
    if collector_id is not None:
        query += " AND collector_id = ?"
        params.append(collector_id)
    if protocol:
        query += " AND protocol = ?"
        params.append(protocol)
    if search:
        query += " AND (destination LIKE ? OR next_hop LIKE ? OR device_label LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
    query = f"""
        SELECT
            r.destination, r.next_hop,
            GROUP_CONCAT(DISTINCT r.interface) AS interface,
            MAX(r.protocol) AS protocol,
            MAX(r.metric) AS metric,
            GROUP_CONCAT(DISTINCT r.device_label) AS device_label,
            MAX(r.last_seen) AS last_seen,
            MAX(s.gateway) AS subnet_gateway
        FROM ({query}) r
        LEFT JOIN subnets s ON s.cidr = r.destination
        GROUP BY r.destination, r.next_hop
        ORDER BY r.destination LIMIT ?
    """
    params.append(limit)
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_route_out(r) for r in rows]
