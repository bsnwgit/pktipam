"""
/api/dhcp-leases/* — read-only view of raw per-collector lease rows
(app/ipam/poll_engine.py owns writing these).
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends

from app.database import get_db
from app.dependencies import CurrentUser

router = APIRouter()


def _lease_out(row) -> dict:
    return {
        "id": row["id"], "collector_id": row["collector_id"], "ip_address": row["ip_address"],
        "mac_address": row["mac_address"], "hostname": row["hostname"], "client_id": row["client_id"],
        "starts_at": row["starts_at"], "ends_at": row["ends_at"], "state": row["state"],
        "last_seen": row["last_seen"],
        "has_history": bool(row["has_history"]) if "has_history" in row.keys() else False,
    }


@router.get("")
async def list_dhcp_leases(
    user: CurrentUser,
    collector_id: int | None = None,
    state: str | None = None,
    search: str | None = None,
    limit: int = 500,
    db: aiosqlite.Connection = Depends(get_db),
):
    query = """SELECT l.*,
                      EXISTS(SELECT 1 FROM ip_address_history h WHERE h.ip_address = l.ip_address) AS has_history
               FROM dhcp_leases l WHERE 1=1"""
    params: list = []
    if collector_id is not None:
        query += " AND collector_id = ?"
        params.append(collector_id)
    if state:
        query += " AND state = ?"
        params.append(state)
    if search:
        query += " AND (ip_address LIKE ? OR hostname LIKE ? OR mac_address LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
    query += " ORDER BY ip_address LIMIT ?"
    params.append(limit)
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_lease_out(r) for r in rows]
