"""
/api/subnets/* — subnet inventory (CIDR blocks, hierarchy, VLAN
association, utilization).
"""
from __future__ import annotations

import ipaddress

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import CurrentUser, AnalystUser

router = APIRouter()


class SubnetRequest(BaseModel):
    cidr: str
    vlan_id: int | None = None
    site: str | None = None
    description: str | None = None
    gateway: str | None = None
    parent_subnet_id: int | None = None


def _subnet_out(row, computed_parent_id: int | None = None) -> dict:
    return {
        "id": row["id"], "cidr": row["cidr"], "vlan_id": row["vlan_id"],
        "site": row["site"], "description": row["description"], "gateway": row["gateway"],
        "parent_subnet_id": row["parent_subnet_id"], "computed_parent_id": computed_parent_id,
        "source": row["source"], "created_at": row["created_at"], "updated_at": row["updated_at"],
    }


def compute_parents(rows) -> dict[int, int | None]:
    """Map each subnet id to the id of the tightest other subnet whose CIDR
    fully contains it — derived purely from the CIDRs on hand, not the
    (currently unused) parent_subnet_id column. Lets a "supernet" like
    10.1.0.0/16 automatically pick up any subnet carved out of it, in any
    order, with no manual linking."""
    parsed = []
    for r in rows:
        try:
            parsed.append((r["id"], ipaddress.ip_network(r["cidr"], strict=False)))
        except ValueError:
            continue

    parents: dict[int, int | None] = {}
    for sid, net in parsed:
        best_id, best_prefix = None, -1
        for oid, onet in parsed:
            if oid == sid or onet.version != net.version:
                continue
            if onet.prefixlen < net.prefixlen and net.subnet_of(onet) and onet.prefixlen > best_prefix:
                best_id, best_prefix = oid, onet.prefixlen
        parents[sid] = best_id
    return parents


def _validate_cidr(cidr: str) -> None:
    try:
        ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid CIDR '{cidr}': {exc}")


@router.get("")
async def list_subnets(user: CurrentUser, site: str | None = None, db: aiosqlite.Connection = Depends(get_db)):
    query = "SELECT * FROM subnets WHERE 1=1"
    params: list = []
    if site:
        query += " AND site = ?"
        params.append(site)
    query += " ORDER BY cidr"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    parents = compute_parents(rows)

    out = []
    for r in rows:
        d = _subnet_out(r, parents.get(r["id"]))
        async with db.execute(
            """SELECT used_count, total_count, pct_used FROM subnet_utilization_history
               WHERE subnet_id = ? ORDER BY id DESC LIMIT 1""",
            (r["id"],),
        ) as ucur:
            util = await ucur.fetchone()
        d["utilization"] = (
            {"used_count": util["used_count"], "total_count": util["total_count"], "pct_used": util["pct_used"]}
            if util else None
        )
        out.append(d)
    return out


@router.get("/{subnet_id}")
async def get_subnet(subnet_id: int, user: CurrentUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM subnets") as cur:
        rows = await cur.fetchall()
    row = next((r for r in rows if r["id"] == subnet_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Subnet not found")
    return _subnet_out(row, compute_parents(rows).get(subnet_id))


@router.get("/{subnet_id}/utilization-history")
async def subnet_utilization_history(
    subnet_id: int, user: CurrentUser, since_hours: int = 24, db: aiosqlite.Connection = Depends(get_db)
):
    async with db.execute(
        """SELECT used_count, total_count, pct_used, recorded_at FROM subnet_utilization_history
           WHERE subnet_id = ? AND recorded_at >= datetime('now', ?) ORDER BY recorded_at ASC""",
        (subnet_id, f"-{since_hours} hours"),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_subnet(body: SubnetRequest, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    _validate_cidr(body.cidr)
    try:
        cur = await db.execute(
            """INSERT INTO subnets (cidr, vlan_id, site, description, gateway, parent_subnet_id, source)
               VALUES (?, ?, ?, ?, ?, ?, 'manual') RETURNING *""",
            (body.cidr, body.vlan_id, body.site, body.description, body.gateway, body.parent_subnet_id),
        )
        row = await cur.fetchone()
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=409, detail=f"Subnet '{body.cidr}' already exists")
    return _subnet_out(row)


@router.patch("/{subnet_id}")
async def update_subnet(subnet_id: int, body: SubnetRequest, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    _validate_cidr(body.cidr)
    async with db.execute("SELECT id FROM subnets WHERE id = ?", (subnet_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Subnet not found")
    await db.execute(
        """UPDATE subnets SET cidr = ?, vlan_id = ?, site = ?, description = ?, gateway = ?,
           parent_subnet_id = ?, updated_at = datetime('now') WHERE id = ?""",
        (body.cidr, body.vlan_id, body.site, body.description, body.gateway, body.parent_subnet_id, subnet_id),
    )
    await db.commit()
    async with db.execute("SELECT * FROM subnets WHERE id = ?", (subnet_id,)) as cur:
        row = await cur.fetchone()
    return _subnet_out(row)


@router.delete("/{subnet_id}", status_code=204)
async def delete_subnet(subnet_id: int, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    await db.execute("DELETE FROM subnets WHERE id = ?", (subnet_id,))
    await db.commit()
