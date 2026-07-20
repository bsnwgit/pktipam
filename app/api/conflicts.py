"""
/api/conflicts/* — conflicts detected by app/ipam/reconcile_engine.py
(duplicate_ip, duplicate_mac, static_dhcp_mismatch, dns_mismatch,
subnet_overlap). Read-only + resolve/dismiss.
"""
from __future__ import annotations

import json

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.dependencies import CurrentUser, AnalystUser

router = APIRouter()


def _conflict_out(row) -> dict:
    return {
        "id": row["id"], "conflict_type": row["conflict_type"], "ip_address": row["ip_address"],
        "subnet_id": row["subnet_id"], "details": json.loads(row["details_json"] or "{}"),
        "detected_at": row["detected_at"], "resolved_at": row["resolved_at"], "resolved_by": row["resolved_by"],
    }


@router.get("")
async def list_conflicts(
    user: CurrentUser,
    resolved: bool | None = None,
    conflict_type: str | None = None,
    limit: int = 500,
    db: aiosqlite.Connection = Depends(get_db),
):
    query = "SELECT * FROM conflicts WHERE 1=1"
    params: list = []
    if resolved is not None:
        query += " AND resolved_at IS " + ("NOT NULL" if resolved else "NULL")
    if conflict_type:
        query += " AND conflict_type = ?"
        params.append(conflict_type)
    query += " ORDER BY detected_at DESC LIMIT ?"
    params.append(limit)
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_conflict_out(r) for r in rows]


@router.post("/{conflict_id}/resolve")
async def resolve_conflict(conflict_id: int, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT id FROM conflicts WHERE id = ?", (conflict_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Conflict not found")
    await db.execute(
        "UPDATE conflicts SET resolved_at = datetime('now'), resolved_by = ? WHERE id = ?",
        (user["username"], conflict_id),
    )
    await db.commit()
    return {"status": "ok"}
