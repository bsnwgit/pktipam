"""
/api/collectors/* — configure and manage pktIPAM data collectors across the
three categories: dhcp, dns, device. `category` on each collector row
selects which registry (and therefore which config-field set / poll
result shape) applies.
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import CurrentUser, AdminUser
from app.ipam.collectors.crypto import encrypt_config, decrypt_config
from app.ipam.collectors.dhcp.registry import DHCP_COLLECTOR_TYPES, get_dhcp_collector_instance
from app.ipam.collectors.dns.registry import DNS_COLLECTOR_TYPES, get_dns_collector_instance
from app.ipam.collectors.device.registry import DEVICE_COLLECTOR_TYPES, get_device_collector_instance

router = APIRouter()

_REGISTRIES = {
    "dhcp": DHCP_COLLECTOR_TYPES,
    "dns": DNS_COLLECTOR_TYPES,
    "device": DEVICE_COLLECTOR_TYPES,
}
_INSTANCE_GETTERS = {
    "dhcp": get_dhcp_collector_instance,
    "dns": get_dns_collector_instance,
    "device": get_device_collector_instance,
}


class CollectorRequest(BaseModel):
    name: str
    category: str
    collector_type: str
    config: dict = {}
    poll_interval_sec: int = 300
    enabled: bool = True


def _collector_out(r, reveal_config: bool = False) -> dict:
    out = {
        "id": r["id"], "name": r["name"], "category": r["category"],
        "collector_type": r["collector_type"],
        "poll_interval_sec": r["poll_interval_sec"], "enabled": bool(r["enabled"]),
        "status": r["status"], "last_poll_at": r["last_poll_at"],
        "last_error": r["last_error"], "created_at": r["created_at"],
    }
    if reveal_config:
        try:
            out["config"] = decrypt_config(r["config_json"])
        except Exception:
            out["config"] = {}
    return out


def _validate_category_and_type(category: str, collector_type: str) -> None:
    registry = _REGISTRIES.get(category)
    if registry is None:
        raise HTTPException(status_code=400, detail=f"Unknown category '{category}' — must be one of {sorted(_REGISTRIES)}")
    if collector_type not in registry:
        raise HTTPException(status_code=400, detail=f"Unknown collector_type '{collector_type}' for category '{category}'")


@router.get("/types")
async def list_collector_types(user: CurrentUser):
    """Available collector plugins per category, and whether each is fully implemented yet."""
    out = {}
    for category, registry in _REGISTRIES.items():
        out[category] = [
            {"type": key, "label": meta["label"], "implemented": meta["implemented"], "fields": meta["fields"]}
            for key, meta in registry.items()
        ]
    return out


@router.get("")
async def list_collectors(user: CurrentUser, category: str | None = None, db: aiosqlite.Connection = Depends(get_db)):
    query = "SELECT * FROM collectors WHERE 1=1"
    params: list = []
    if category:
        query += " AND category = ?"
        params.append(category)
    query += " ORDER BY category, name"
    async with db.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [_collector_out(r) for r in rows]


@router.get("/{collector_id}")
async def get_collector(collector_id: int, user: AdminUser, db: aiosqlite.Connection = Depends(get_db)):
    """Admin-only — includes decrypted config so it can be edited in the UI."""
    async with db.execute("SELECT * FROM collectors WHERE id = ?", (collector_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Collector not found")
    return _collector_out(row, reveal_config=True)


@router.post("", status_code=201)
async def create_collector(body: CollectorRequest, user: AdminUser, db: aiosqlite.Connection = Depends(get_db)):
    _validate_category_and_type(body.category, body.collector_type)
    cur = await db.execute(
        """INSERT INTO collectors (name, category, collector_type, config_json, poll_interval_sec, enabled)
           VALUES (?, ?, ?, ?, ?, ?) RETURNING *""",
        (body.name, body.category, body.collector_type, encrypt_config(body.config),
         body.poll_interval_sec, int(body.enabled)),
    )
    row = await cur.fetchone()
    await db.commit()
    return _collector_out(row)


@router.patch("/{collector_id}")
async def update_collector(collector_id: int, body: CollectorRequest, user: AdminUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT id FROM collectors WHERE id = ?", (collector_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Collector not found")
    _validate_category_and_type(body.category, body.collector_type)
    await db.execute(
        """UPDATE collectors SET name = ?, category = ?, collector_type = ?, config_json = ?,
           poll_interval_sec = ?, enabled = ? WHERE id = ?""",
        (body.name, body.category, body.collector_type, encrypt_config(body.config),
         body.poll_interval_sec, int(body.enabled), collector_id),
    )
    await db.commit()
    async with db.execute("SELECT * FROM collectors WHERE id = ?", (collector_id,)) as cur:
        row = await cur.fetchone()
    return _collector_out(row)


@router.delete("/{collector_id}", status_code=204)
async def delete_collector(collector_id: int, user: AdminUser, db: aiosqlite.Connection = Depends(get_db)):
    await db.execute("DELETE FROM collectors WHERE id = ?", (collector_id,))
    await db.commit()


@router.post("/{collector_id}/poll-now")
async def poll_now(collector_id: int, user: AdminUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM collectors WHERE id = ?", (collector_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Collector not found")

    get_instance = _INSTANCE_GETTERS.get(row["category"])
    if get_instance is None:
        raise HTTPException(status_code=400, detail=f"Unknown category '{row['category']}'")

    from app.ipam.poll_engine import resolve_device_config
    try:
        config = await resolve_device_config(db, decrypt_config(row["config_json"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    collector = get_instance(row["collector_type"], config)
    if collector is None:
        raise HTTPException(status_code=400, detail="Collector type is not implemented yet")
    try:
        result = await collector.poll()
    except Exception as exc:
        # Some exceptions (e.g. httpx.ConnectTimeout) have an empty str() —
        # always include the exception type name so the user never sees a
        # blank error message.
        detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        await db.execute(
            "UPDATE collectors SET status = 'error', last_error = ?, last_poll_at = datetime('now') WHERE id = ?",
            (detail, collector_id),
        )
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Poll failed: {detail}")

    from app.ipam.poll_engine import _PERSISTERS
    persist = _PERSISTERS[row["category"]]
    count = await persist(db, collector_id, result)

    await db.execute(
        "UPDATE collectors SET status = 'ok', last_error = NULL, last_poll_at = datetime('now') WHERE id = ?",
        (collector_id,),
    )
    await db.commit()
    return {"status": "ok", "rows": count}
