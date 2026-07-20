"""
/api/ip-address-history/* — read-only timeline of which device (MAC/
hostname) held a given IP over time. Written by app/ipam/reconcile_engine.py
(DHCP/DNS/ARP-driven changes) and app/api/ip_addresses.py (manual create/
edit/delete) — this router only reads it back.
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends

from app.database import get_db
from app.dependencies import CurrentUser

router = APIRouter()


def _entry_out(row) -> dict:
    return {
        "id": row["id"], "subnet_id": row["subnet_id"], "ip_address": row["ip_address"],
        "event": row["event"], "status": row["status"], "mac_address": row["mac_address"],
        "hostname": row["hostname"], "source": row["source"], "recorded_at": row["recorded_at"],
    }


@router.get("")
async def list_ip_address_history(
    user: CurrentUser,
    ip_address: str | None = None,
    subnet_id: int | None = None,
    limit: int = 200,
    db: aiosqlite.Connection = Depends(get_db),
):
    query = "SELECT * FROM ip_address_history WHERE 1=1"
    params: list = []
    if ip_address:
        query += " AND ip_address = ?"
        params.append(ip_address)
    if subnet_id is not None:
        query += " AND subnet_id = ?"
        params.append(subnet_id)
    query += " ORDER BY recorded_at DESC, id DESC LIMIT ?"
    params.append(limit)
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_entry_out(r) for r in rows]
