"""
/api/dns-records/* — read-only view of raw per-collector DNS record rows
(app/ipam/poll_engine.py owns writing these).
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends

from app.database import get_db
from app.dependencies import CurrentUser

router = APIRouter()


def _record_out(row) -> dict:
    return {
        "id": row["id"], "collector_id": row["collector_id"], "zone": row["zone"],
        "name": row["name"], "record_type": row["record_type"], "value": row["value"],
        "ttl": row["ttl"], "last_seen": row["last_seen"],
    }


@router.get("")
async def list_dns_records(
    user: CurrentUser,
    collector_id: int | None = None,
    record_type: str | None = None,
    search: str | None = None,
    limit: int = 500,
    db: aiosqlite.Connection = Depends(get_db),
):
    query = "SELECT * FROM dns_records WHERE 1=1"
    params: list = []
    if collector_id is not None:
        query += " AND collector_id = ?"
        params.append(collector_id)
    if record_type:
        query += " AND record_type = ?"
        params.append(record_type)
    if search:
        query += " AND (name LIKE ? OR value LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like])
    query += " ORDER BY name LIMIT ?"
    params.append(limit)
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_record_out(r) for r in rows]
