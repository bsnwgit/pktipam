"""
/api/snmp-credentials/* — named, reusable SNMP credential library.

A credential is created once here (v2c community, or v3 user/auth/priv)
and assigned to any number of device collectors by id — same "define auth
once, reuse everywhere" pattern as pktsnmp's Settings -> SNMP ->
Credentials tab. Device collectors reference a credential by id inside
their own (encrypted) config_json rather than a plain FK column, so
"is this credential in use" is checked by decrypting every device-category
collector's config and looking for a match, not a simple SQL COUNT.
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import CurrentUser, AdminUser
from app.ipam.collectors.crypto import encrypt_str, decrypt_str, decrypt_config

router = APIRouter()

_MASK = "••••••••"
_SECRET_FIELDS = {"community", "auth_key_enc", "priv_key_enc"}


def _mask(row: dict) -> dict:
    d = dict(row)
    for field in _SECRET_FIELDS:
        if d.get(field):
            d[field] = _MASK
    d.pop("auth_key_enc", None)
    d.pop("priv_key_enc", None)
    d["has_auth_key"] = bool(row.get("auth_key_enc"))
    d["has_priv_key"] = bool(row.get("priv_key_enc"))
    return d


class CredentialCreate(BaseModel):
    name: str
    description: str = ""
    snmp_version: str = "v2c"
    community: str = "public"
    security_name: str = ""
    security_level: str = "noAuthNoPriv"
    auth_protocol: str = "SHA"
    auth_key: str = ""
    priv_protocol: str = "AES"
    priv_key: str = ""


class CredentialUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    snmp_version: str | None = None
    community: str | None = None
    security_name: str | None = None
    security_level: str | None = None
    auth_protocol: str | None = None
    auth_key: str | None = None
    priv_protocol: str | None = None
    priv_key: str | None = None


@router.get("")
async def list_credentials(user: CurrentUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM snmp_credentials ORDER BY name") as cur:
        rows = await cur.fetchall()
    return [_mask(dict(r)) for r in rows]


@router.get("/{cred_id}")
async def get_credential(cred_id: int, user: CurrentUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM snmp_credentials WHERE id = ?", (cred_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")
    return _mask(dict(row))


@router.post("", status_code=201)
async def create_credential(body: CredentialCreate, user: AdminUser, db: aiosqlite.Connection = Depends(get_db)):
    auth_key_enc = encrypt_str(body.auth_key) if body.auth_key else None
    priv_key_enc = encrypt_str(body.priv_key) if body.priv_key else None
    try:
        cur = await db.execute(
            """INSERT INTO snmp_credentials
               (name, description, snmp_version, community, security_name, security_level,
                auth_protocol, auth_key_enc, priv_protocol, priv_key_enc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *""",
            (body.name, body.description, body.snmp_version, body.community, body.security_name,
             body.security_level, body.auth_protocol, auth_key_enc, body.priv_protocol, priv_key_enc),
        )
        row = await cur.fetchone()
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=409, detail=f"Credential '{body.name}' already exists")
    return _mask(dict(row))


@router.put("/{cred_id}")
async def update_credential(cred_id: int, body: CredentialUpdate, user: AdminUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM snmp_credentials WHERE id = ?", (cred_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")
    existing = dict(row)

    updates = body.model_dump(exclude_none=True)
    auth_key = updates.pop("auth_key", None)
    priv_key = updates.pop("priv_key", None)
    auth_key_enc = encrypt_str(auth_key) if auth_key else existing["auth_key_enc"]
    priv_key_enc = encrypt_str(priv_key) if priv_key else existing["priv_key_enc"]
    existing.update(updates)

    try:
        await db.execute(
            """UPDATE snmp_credentials SET name = ?, description = ?, snmp_version = ?, community = ?,
               security_name = ?, security_level = ?, auth_protocol = ?, auth_key_enc = ?,
               priv_protocol = ?, priv_key_enc = ?, updated_at = datetime('now') WHERE id = ?""",
            (existing["name"], existing["description"], existing["snmp_version"], existing["community"],
             existing["security_name"], existing["security_level"], existing["auth_protocol"], auth_key_enc,
             existing["priv_protocol"], priv_key_enc, cred_id),
        )
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=409, detail=f"Credential '{existing['name']}' already exists")
    async with db.execute("SELECT * FROM snmp_credentials WHERE id = ?", (cred_id,)) as cur:
        row = await cur.fetchone()
    return _mask(dict(row))


@router.delete("/{cred_id}", status_code=204)
async def delete_credential(cred_id: int, user: AdminUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT collector_type, config_json FROM collectors WHERE category = 'device'") as cur:
        device_collectors = await cur.fetchall()
    for row in device_collectors:
        config = decrypt_config(row["config_json"])
        if config.get("credential_id") == cred_id:
            raise HTTPException(status_code=409, detail="Credential is used by a device collector — reassign it first")
    await db.execute("DELETE FROM snmp_credentials WHERE id = ?", (cred_id,))
    await db.commit()
