"""
/api/routes/* — read-only view of raw per-collector routing-table rows
(app/ipam/poll_engine.py owns writing these).
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends

from app.database import get_db
from app.dependencies import CurrentUser

router = APIRouter()


def _route_out(row) -> dict:
    return {
        "id": row["id"], "collector_id": row["collector_id"], "device_label": row["device_label"],
        "destination": row["destination"], "next_hop": row["next_hop"], "interface": row["interface"],
        "protocol": row["protocol"], "metric": row["metric"], "last_seen": row["last_seen"],
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
    query += " ORDER BY destination LIMIT ?"
    params.append(limit)
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_route_out(r) for r in rows]
