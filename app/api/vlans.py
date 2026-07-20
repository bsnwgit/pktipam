"""
/api/vlans/* — VLAN catalog, associated with subnets by vlan_id.
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import CurrentUser, AnalystUser

router = APIRouter()


class VlanRequest(BaseModel):
    vlan_tag: int
    name: str
    site: str | None = None
    description: str | None = None


def _vlan_out(row) -> dict:
    return {
        "id": row["id"], "vlan_tag": row["vlan_tag"], "name": row["name"],
        "site": row["site"], "description": row["description"], "created_at": row["created_at"],
    }


@router.get("")
async def list_vlans(user: CurrentUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM vlans ORDER BY vlan_tag") as cur:
        rows = await cur.fetchall()
    return [_vlan_out(r) for r in rows]


@router.post("", status_code=201)
async def create_vlan(body: VlanRequest, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    try:
        cur = await db.execute(
            "INSERT INTO vlans (vlan_tag, name, site, description) VALUES (?, ?, ?, ?) RETURNING *",
            (body.vlan_tag, body.name, body.site, body.description),
        )
        row = await cur.fetchone()
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=409, detail=f"VLAN {body.vlan_tag} already exists for this site")
    return _vlan_out(row)


@router.patch("/{vlan_id}")
async def update_vlan(vlan_id: int, body: VlanRequest, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT id FROM vlans WHERE id = ?", (vlan_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="VLAN not found")
    await db.execute(
        "UPDATE vlans SET vlan_tag = ?, name = ?, site = ?, description = ? WHERE id = ?",
        (body.vlan_tag, body.name, body.site, body.description, vlan_id),
    )
    await db.commit()
    async with db.execute("SELECT * FROM vlans WHERE id = ?", (vlan_id,)) as cur:
        row = await cur.fetchone()
    return _vlan_out(row)


@router.delete("/{vlan_id}", status_code=204)
async def delete_vlan(vlan_id: int, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    await db.execute("DELETE FROM vlans WHERE id = ?", (vlan_id,))
    await db.commit()
