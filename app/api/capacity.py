"""
/api/capacity/* — capacity planning: given a host count, work out the
smallest block that fits, find where it fits in existing subnets, and
reserve it in one step (writes 'reserved' rows into ip_addresses, same
mechanism the IP grid / bulk-update already use).
"""
from __future__ import annotations

import ipaddress
import json
import math

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import CurrentUser, AnalystUser

router = APIRouter()

MAX_CANDIDATES_PER_SUBNET = 3
MAX_TOTAL_CANDIDATES = 8
MAX_ALIGNED_SCAN_BLOCKS = 20000
MAX_FALLBACK_SCAN_ADDRESSES = 65536
MAX_RESERVATION_SIZE = 4096


class ReserveRequest(BaseModel):
    subnet_id: int
    start_ip: str
    end_ip: str
    description: str | None = None
    owner: str | None = None
    tags: list[str] = []


def _hosts_to_prefix(required_hosts: int) -> int:
    n = 2
    while (2 ** n - 2) < required_hosts:
        n += 1
        if n > 32:
            raise HTTPException(status_code=400, detail="Requested host count is too large")
    return 32 - n


def _block_hosts(network) -> list:
    return list(network.hosts()) if network.num_addresses > 2 else list(network)


async def _used_ips(db: aiosqlite.Connection, subnet_id: int) -> set[str]:
    async with db.execute(
        "SELECT ip_address FROM ip_addresses WHERE subnet_id = ? AND status != 'free'", (subnet_id,)
    ) as cur:
        rows = await cur.fetchall()
    return {r["ip_address"] for r in rows}


def _descendant_networks(subnet_row, all_rows) -> list:
    """Other subnets carved out of this one (e.g. the /24s under a /16
    supernet). Their whole address range counts as claimed even where no
    individual IP has a row yet — it's earmarked for that subnet, not free
    space in the parent."""
    try:
        network = ipaddress.ip_network(subnet_row["cidr"], strict=False)
    except ValueError:
        return []
    descendants = []
    for r in all_rows:
        if r["id"] == subnet_row["id"]:
            continue
        try:
            onet = ipaddress.ip_network(r["cidr"], strict=False)
        except ValueError:
            continue
        if onet.version == network.version and onet.prefixlen > network.prefixlen and onet.subnet_of(network):
            descendants.append(onet)
    return descendants


async def _find_candidates_in_subnet(
    db: aiosqlite.Connection, subnet_row, prefix: int, required_hosts: int, limit: int, all_rows,
) -> list[dict]:
    try:
        network = ipaddress.ip_network(subnet_row["cidr"], strict=False)
    except ValueError:
        return []
    if prefix < network.prefixlen:
        return []

    used = await _used_ips(db, subnet_row["id"])
    descendants = _descendant_networks(subnet_row, all_rows)
    candidates: list[dict] = []

    scanned = 0
    for block in network.subnets(new_prefix=prefix):
        scanned += 1
        if scanned > MAX_ALIGNED_SCAN_BLOCKS:
            break
        if any(block.overlaps(d) for d in descendants):
            continue
        hosts = _block_hosts(block)
        if not hosts:
            continue
        if any(str(h) in used for h in hosts):
            continue
        candidates.append({
            "subnet_id": subnet_row["id"], "subnet_cidr": subnet_row["cidr"],
            "cidr": str(block), "start_ip": str(hosts[0]), "end_ip": str(hosts[-1]),
            "size": len(hosts), "aligned": True,
        })
        if len(candidates) >= limit:
            return candidates

    if candidates or network.num_addresses > MAX_FALLBACK_SCAN_ADDRESSES:
        return candidates

    # No aligned block available — fall back to the longest contiguous free
    # run, even if it doesn't land on a clean CIDR boundary.
    all_hosts = _block_hosts(network)
    best_start = None
    run_start = None
    best_len = 0
    run_len = 0
    for h in all_hosts:
        claimed = str(h) in used or any(h in d for d in descendants)
        if not claimed:
            if run_start is None:
                run_start = h
            run_len += 1
            if run_len > best_len:
                best_len = run_len
                best_start = run_start
        else:
            run_start = None
            run_len = 0
    if best_start is not None and best_len >= required_hosts:
        best_start_int = int(best_start)
        end_ip = ipaddress.ip_address(best_start_int + required_hosts - 1)
        candidates.append({
            "subnet_id": subnet_row["id"], "subnet_cidr": subnet_row["cidr"],
            "cidr": None, "start_ip": str(best_start), "end_ip": str(end_ip),
            "size": required_hosts, "aligned": False,
        })
    return candidates


def _calculate(host_count: int, buffer_pct: float) -> dict:
    if host_count < 1:
        raise HTTPException(status_code=400, detail="host_count must be at least 1")
    if buffer_pct < 0:
        raise HTTPException(status_code=400, detail="buffer_pct cannot be negative")
    required_hosts = math.ceil(host_count * (1 + buffer_pct / 100))
    prefix = _hosts_to_prefix(required_hosts)
    block_size = 2 ** (32 - prefix)
    return {
        "host_count": host_count, "buffer_pct": buffer_pct, "required_hosts": required_hosts,
        "prefix": prefix, "block_size": block_size, "usable_hosts": block_size - 2,
    }


@router.get("/calculate")
async def calculate(host_count: int, user: CurrentUser, buffer_pct: float = 0):
    return _calculate(host_count, buffer_pct)


@router.get("/search")
async def search(
    host_count: int, user: CurrentUser, buffer_pct: float = 0, subnet_id: int | None = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    calc = _calculate(host_count, buffer_pct)
    prefix, required_hosts = calc["prefix"], calc["required_hosts"]

    async with db.execute("SELECT * FROM subnets ORDER BY cidr") as cur:
        all_rows = await cur.fetchall()

    if subnet_id is not None:
        subnet_row = next((r for r in all_rows if r["id"] == subnet_id), None)
        if not subnet_row:
            raise HTTPException(status_code=404, detail="Subnet not found")
        candidates = await _find_candidates_in_subnet(db, subnet_row, prefix, required_hosts, MAX_CANDIDATES_PER_SUBNET, all_rows)
    else:
        candidates = []
        for subnet_row in all_rows:
            remaining = MAX_TOTAL_CANDIDATES - len(candidates)
            if remaining <= 0:
                break
            candidates.extend(await _find_candidates_in_subnet(db, subnet_row, prefix, required_hosts, min(1, remaining), all_rows))

    return {**calc, "candidates": candidates}


@router.post("/reserve", status_code=201)
async def reserve(body: ReserveRequest, user: AnalystUser, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM subnets") as cur:
        all_rows = await cur.fetchall()
    subnet_row = next((r for r in all_rows if r["id"] == body.subnet_id), None)
    if not subnet_row:
        raise HTTPException(status_code=404, detail="Subnet not found")

    try:
        network = ipaddress.ip_network(subnet_row["cidr"], strict=False)
        start = ipaddress.ip_address(body.start_ip)
        end = ipaddress.ip_address(body.end_ip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid IP: {exc}")

    if start not in network or end not in network:
        raise HTTPException(status_code=400, detail="Range must fall within the subnet")
    if int(end) < int(start):
        raise HTTPException(status_code=400, detail="end_ip must not be before start_ip")

    size = int(end) - int(start) + 1
    if size > MAX_RESERVATION_SIZE:
        raise HTTPException(status_code=400, detail=f"Range too large to reserve in one step (max {MAX_RESERVATION_SIZE} addresses)")

    descendants = _descendant_networks(subnet_row, all_rows)
    overlapping = next(
        (d for d in descendants if int(start) <= int(d.broadcast_address) and int(end) >= int(d.network_address)), None,
    )
    if overlapping is not None:
        raise HTTPException(
            status_code=409,
            detail=f"This range falls inside {overlapping}, which is already its own subnet — reserve within that subnet instead",
        )

    range_ips = [str(ipaddress.ip_address(int(start) + i)) for i in range(size)]

    used = await _used_ips(db, body.subnet_id)
    conflicts = [ip for ip in range_ips if ip in used]
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail=f"{len(conflicts)} address(es) in this range are already in use, e.g. {', '.join(conflicts[:5])}",
        )

    tags_json = json.dumps(body.tags)
    for ip in range_ips:
        await db.execute(
            """INSERT INTO ip_addresses (subnet_id, ip_address, status, description, owner, tags_json, source)
               VALUES (?, ?, 'reserved', ?, ?, ?, 'manual')
               ON CONFLICT(subnet_id, ip_address) DO UPDATE SET
                 status = 'reserved', description = excluded.description, owner = excluded.owner,
                 tags_json = excluded.tags_json, source = 'manual', updated_at = datetime('now')""",
            (body.subnet_id, ip, body.description, body.owner, tags_json),
        )
    await db.commit()

    return {"status": "ok", "subnet_id": body.subnet_id, "start_ip": body.start_ip, "end_ip": body.end_ip, "count": size}
