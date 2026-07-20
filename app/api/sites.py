"""
/api/sites/* — site catalog. Subnets and VLANs each have a plain-text
`site` field for grouping/filtering; this is the managed list that
populates their site dropdowns instead of free-typing a name (and risking
typo'd duplicates like "HQ" / "Hq" / "headquarters" for the same place).
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import CurrentUser, AnalystUser

router = APIRouter()


class SiteRequest(BaseModel):
    name: str
    description: str | None = None


def _site_out(row) -> dict:
    return {"id": row["id"], "name": row["name"], "description": row["description"], "created_at": row["created_at"]}


@router.get("")
async def list_sites(user: CurrentUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM sites ORDER BY name") as cur:
        rows = await cur.fetchall()
    return [_site_out(r) for r in rows]


@router.post("", status_code=201)
async def create_site(body: SiteRequest, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    try:
        cur = await db.execute(
            "INSERT INTO sites (name, description) VALUES (?, ?) RETURNING *",
            (body.name, body.description),
        )
        row = await cur.fetchone()
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=409, detail=f"Site '{body.name}' already exists")
    return _site_out(row)


@router.patch("/{site_id}")
async def update_site(site_id: int, body: SiteRequest, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT id FROM sites WHERE id = ?", (site_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Site not found")
    try:
        await db.execute(
            "UPDATE sites SET name = ?, description = ? WHERE id = ?",
            (body.name, body.description, site_id),
        )
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=409, detail=f"Site '{body.name}' already exists")
    async with db.execute("SELECT * FROM sites WHERE id = ?", (site_id,)) as cur:
        row = await cur.fetchone()
    return _site_out(row)


@router.delete("/{site_id}", status_code=204)
async def delete_site(site_id: int, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    await db.execute("DELETE FROM sites WHERE id = ?", (site_id,))
    await db.commit()
