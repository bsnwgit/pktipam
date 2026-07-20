"""
/api/ip-addresses/* — the reconciled IP view (app/ipam/reconcile_engine.py
writes most rows here automatically; this router also lets an admin/
analyst create/edit manual static reservations directly).
"""
from __future__ import annotations

import ipaddress
import json

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.subnets import _subnet_out
from app.database import get_db
from app.dependencies import CurrentUser, AnalystUser

router = APIRouter()


class ManualIpRequest(BaseModel):
    subnet_id: int
    ip_address: str
    status: str = "static"   # static | reserved
    mac_address: str | None = None
    hostname: str | None = None
    description: str | None = None
    owner: str | None = None
    tags: list[str] = []


class BulkUpdateRequest(BaseModel):
    """Mass-edit a set of IPs in one subnet. No hostname/mac_address —
    those only make sense per-IP, not applied identically across a
    selection. Each `apply_*` flag opts that field into the update; fields
    left un-applied are untouched on IPs that already have a row, and get
    a sensible default (status defaults to 'static', matching a normal
    manual reservation) on IPs that don't have one yet."""
    subnet_id: int
    ip_addresses: list[str]
    apply_status: bool = False
    status: str | None = None
    apply_owner: bool = False
    owner: str | None = None
    apply_description: bool = False
    description: str | None = None
    apply_tags: bool = False
    tags: list[str] = []


async def _log_history(db: aiosqlite.Connection, subnet_id: int, ip_address: str, event: str,
                        status: str | None, mac_address: str | None, hostname: str | None, source: str = "manual") -> None:
    await db.execute(
        """INSERT INTO ip_address_history (subnet_id, ip_address, event, status, mac_address, hostname, source)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (subnet_id, ip_address, event, status, mac_address, hostname, source),
    )


def _ip_out(row) -> dict:
    return {
        "id": row["id"], "subnet_id": row["subnet_id"], "ip_address": row["ip_address"],
        "status": row["status"], "mac_address": row["mac_address"], "hostname": row["hostname"],
        "dns_ptr": row["dns_ptr"], "description": row["description"], "owner": row["owner"],
        "tags": json.loads(row["tags_json"] or "[]"), "source": row["source"],
        "last_seen": row["last_seen"], "created_at": row["created_at"], "updated_at": row["updated_at"],
        "has_history": bool(row["has_history"]) if "has_history" in row.keys() else False,
    }


@router.get("")
async def list_ip_addresses(
    user: CurrentUser,
    subnet_id: int | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 500,
    db: aiosqlite.Connection = Depends(get_db),
):
    query = """SELECT ip.*,
                      EXISTS(SELECT 1 FROM ip_address_history h WHERE h.ip_address = ip.ip_address) AS has_history
               FROM ip_addresses ip WHERE 1=1"""
    params: list = []
    if subnet_id is not None:
        query += " AND subnet_id = ?"
        params.append(subnet_id)
    if status:
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (ip_address LIKE ? OR hostname LIKE ? OR mac_address LIKE ? OR description LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like, like])
    query += " ORDER BY subnet_id, ip_address LIMIT ?"
    params.append(limit)
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_ip_out(r) for r in rows]


@router.get("/grid/{subnet_id}")
async def ip_grid(subnet_id: int, user: CurrentUser, db: aiosqlite.Connection = Depends(get_db)):
    """Full IP-by-IP grid for a subnet — every usable address, free or not."""
    async with db.execute("SELECT * FROM subnets WHERE id = ?", (subnet_id,)) as cur:
        subnet = await cur.fetchone()
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    network = ipaddress.ip_network(subnet["cidr"], strict=False)
    if network.num_addresses > 65536:
        raise HTTPException(status_code=400, detail="Subnet too large to render as a grid (max /16)")

    async with db.execute("SELECT * FROM ip_addresses WHERE subnet_id = ?", (subnet_id,)) as cur:
        rows = await cur.fetchall()
    by_ip = {r["ip_address"]: r for r in rows}

    hosts = list(network.hosts()) if network.num_addresses > 2 else list(network)
    grid = []
    for addr in hosts:
        ip_str = str(addr)
        row = by_ip.get(ip_str)
        if row:
            grid.append(_ip_out(row))
        else:
            grid.append({
                "id": None, "subnet_id": subnet_id, "ip_address": ip_str, "status": "free",
                "mac_address": None, "hostname": None, "dns_ptr": None, "description": None,
                "owner": None, "tags": [], "source": None, "last_seen": None,
                "created_at": None, "updated_at": None,
            })
    return grid


@router.get("/lookup")
async def lookup_ip(ip: str, user: CurrentUser, db: aiosqlite.Connection = Depends(get_db)):
    """Combined single-IP lookup — containing subnet, the reconciled
    ip_addresses row, any DHCP leases, DNS records and ARP sightings for
    that address. Used by sibling apps (e.g. pktflow's internal-IP link)
    over the Suite Integration channel, so this returns a 200 with
    found=false rather than 404 when nothing is known about the IP."""
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid IP address: {ip}")

    async with db.execute("SELECT * FROM subnets") as cur:
        subnet_rows = await cur.fetchall()
    subnet = None
    for row in subnet_rows:
        try:
            if ip_obj in ipaddress.ip_network(row["cidr"], strict=False):
                subnet = row
                break
        except ValueError:
            continue

    async with db.execute("SELECT * FROM ip_addresses WHERE ip_address = ?", (ip,)) as cur:
        ip_row = await cur.fetchone()

    async with db.execute("SELECT * FROM dhcp_leases WHERE ip_address = ? ORDER BY last_seen DESC", (ip,)) as cur:
        lease_rows = await cur.fetchall()

    async with db.execute("SELECT * FROM dns_records WHERE value = ? ORDER BY last_seen DESC", (ip,)) as cur:
        dns_rows = await cur.fetchall()

    async with db.execute("SELECT * FROM arp_entries WHERE ip_address = ? ORDER BY last_seen DESC", (ip,)) as cur:
        arp_rows = await cur.fetchall()

    found = bool(ip_row or lease_rows or dns_rows or arp_rows)

    return {
        "ip": ip,
        "found": found,
        "subnet": _subnet_out(subnet) if subnet else None,
        "ip_address": _ip_out(ip_row) if ip_row else None,
        "dhcp_leases": [
            {
                "mac_address": r["mac_address"], "hostname": r["hostname"], "client_id": r["client_id"],
                "starts_at": r["starts_at"], "ends_at": r["ends_at"], "state": r["state"], "last_seen": r["last_seen"],
            }
            for r in lease_rows
        ],
        "dns_records": [
            {"zone": r["zone"], "name": r["name"], "record_type": r["record_type"], "ttl": r["ttl"], "last_seen": r["last_seen"]}
            for r in dns_rows
        ],
        "arp_entries": [
            {
                "device_label": r["device_label"], "mac_address": r["mac_address"], "interface": r["interface"],
                "vlan_tag": r["vlan_tag"], "last_seen": r["last_seen"],
            }
            for r in arp_rows
        ],
    }


@router.get("/{ip_id}")
async def get_ip_address(ip_id: int, user: CurrentUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM ip_addresses WHERE id = ?", (ip_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="IP address not found")
    return _ip_out(row)


@router.post("", status_code=201)
async def create_manual_ip(body: ManualIpRequest, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    try:
        ipaddress.ip_address(body.ip_address)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid IP address '{body.ip_address}'")
    try:
        cur = await db.execute(
            """INSERT INTO ip_addresses
               (subnet_id, ip_address, status, mac_address, hostname, description, owner, tags_json, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'manual') RETURNING *""",
            (body.subnet_id, body.ip_address, body.status, body.mac_address, body.hostname,
             body.description, body.owner, json.dumps(body.tags)),
        )
        row = await cur.fetchone()
        await _log_history(db, body.subnet_id, body.ip_address, "first_seen", body.status, body.mac_address, body.hostname)
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=409, detail=f"{body.ip_address} already has an entry in this subnet")
    return _ip_out(row)


@router.post("/bulk-update")
async def bulk_update_ip_addresses(body: BulkUpdateRequest, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    if not body.ip_addresses:
        raise HTTPException(status_code=400, detail="No IP addresses selected")
    if not (body.apply_status or body.apply_owner or body.apply_description or body.apply_tags):
        raise HTTPException(status_code=400, detail="No fields selected to apply")

    insert_status = body.status if body.apply_status else "static"
    insert_owner = body.owner if body.apply_owner else None
    insert_description = body.description if body.apply_description else None
    insert_tags = json.dumps(body.tags) if body.apply_tags else "[]"

    update_clauses = ["source = 'manual'", "updated_at = datetime('now')"]
    if body.apply_status:
        update_clauses.append("status = excluded.status")
    if body.apply_owner:
        update_clauses.append("owner = excluded.owner")
    if body.apply_description:
        update_clauses.append("description = excluded.description")
    if body.apply_tags:
        update_clauses.append("tags_json = excluded.tags_json")

    updated = 0
    for ip in body.ip_addresses:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            continue
        await db.execute(
            f"""INSERT INTO ip_addresses (subnet_id, ip_address, status, owner, description, tags_json, source)
                VALUES (?, ?, ?, ?, ?, ?, 'manual')
                ON CONFLICT(subnet_id, ip_address) DO UPDATE SET {', '.join(update_clauses)}""",
            (body.subnet_id, ip, insert_status, insert_owner, insert_description, insert_tags),
        )
        updated += 1
    await db.commit()
    return {"status": "ok", "updated": updated}


@router.patch("/{ip_id}")
async def update_ip_address(ip_id: int, body: ManualIpRequest, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM ip_addresses WHERE id = ?", (ip_id,)) as cur:
        existing = await cur.fetchone()
    if not existing:
        raise HTTPException(status_code=404, detail="IP address not found")
    await db.execute(
        """UPDATE ip_addresses SET status = ?, mac_address = ?, hostname = ?, description = ?,
           owner = ?, tags_json = ?, source = 'manual', updated_at = datetime('now') WHERE id = ?""",
        (body.status, body.mac_address, body.hostname, body.description, body.owner,
         json.dumps(body.tags), ip_id),
    )
    if existing["mac_address"] != body.mac_address or existing["hostname"] != body.hostname:
        await _log_history(db, existing["subnet_id"], existing["ip_address"], "changed",
                            body.status, body.mac_address, body.hostname)
    await db.commit()
    async with db.execute("SELECT * FROM ip_addresses WHERE id = ?", (ip_id,)) as cur:
        row = await cur.fetchone()
    return _ip_out(row)


@router.delete("/{ip_id}", status_code=204)
async def delete_ip_address(ip_id: int, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM ip_addresses WHERE id = ?", (ip_id,)) as cur:
        existing = await cur.fetchone()
    if existing and (existing["mac_address"] or existing["hostname"] or existing["status"] != "free"):
        await _log_history(db, existing["subnet_id"], existing["ip_address"], "released",
                            "free", existing["mac_address"], existing["hostname"])
    await db.execute("DELETE FROM ip_addresses WHERE id = ?", (ip_id,))
    await db.commit()
