"""
/api/conflicts/* — conflicts detected by app/ipam/reconcile_engine.py
(duplicate_ip, duplicate_mac, static_dhcp_mismatch, dns_mismatch,
subnet_overlap). Read-only + resolve/dismiss.
"""
from __future__ import annotations

import json

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import CurrentUser, AnalystUser

router = APIRouter()


def _conflict_out(row) -> dict:
    return {
        "id": row["id"], "conflict_type": row["conflict_type"], "ip_address": row["ip_address"],
        "subnet_id": row["subnet_id"], "details": json.loads(row["details_json"] or "{}"),
        "detected_at": row["detected_at"], "resolved_at": row["resolved_at"], "resolved_by": row["resolved_by"],
        "acked": bool(row["acked"]), "acked_by": row["acked_by"], "acked_at": row["acked_at"],
    }


@router.get("")
async def list_conflicts(
    user: CurrentUser,
    resolved: bool | None = None,
    acked: bool | None = None,
    conflict_type: str | None = None,
    limit: int = 500,
    db: aiosqlite.Connection = Depends(get_db),
):
    query = "SELECT * FROM conflicts WHERE 1=1"
    params: list = []
    if resolved is not None:
        query += " AND resolved_at IS " + ("NOT NULL" if resolved else "NULL")
    if acked is not None:
        query += " AND acked = ?"
        params.append(int(acked))
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


@router.post("/resolve-all")
async def resolve_all_conflicts(user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    cur = await db.execute(
        "UPDATE conflicts SET resolved_at = datetime('now'), resolved_by = ? WHERE resolved_at IS NULL",
        (user["username"],),
    )
    await db.commit()
    return {"status": "ok", "resolved": cur.rowcount}


class ConflictIdsBody(BaseModel):
    ids: list[int]


@router.post("/resolve-selected")
async def resolve_selected_conflicts(body: ConflictIdsBody, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    if not body.ids:
        return {"status": "ok", "resolved": 0}
    placeholders = ",".join("?" * len(body.ids))
    cur = await db.execute(
        f"UPDATE conflicts SET resolved_at = datetime('now'), resolved_by = ? WHERE id IN ({placeholders})",
        (user["username"], *body.ids),
    )
    await db.commit()
    return {"status": "ok", "resolved": cur.rowcount}


@router.post("/{conflict_id}/ack")
async def ack_conflict(conflict_id: int, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT id FROM conflicts WHERE id = ?", (conflict_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Conflict not found")
    await db.execute(
        "UPDATE conflicts SET acked = 1, acked_by = ?, acked_at = datetime('now') WHERE id = ?",
        (user["username"], conflict_id),
    )
    await db.commit()
    return {"status": "ok"}
