"""
pktIPAM — Widget endpoints for pktHub NOC Builder integration.

Manifest: GET /api/widgets/manifest  → list of widget definitions
Views:    GET /api/widgets/{id}      → server-rendered HTML page (iframe target)
Options:  GET /api/widgets/options/* → JSON [{value,label}] for dynamic param pickers
"""
from __future__ import annotations

import html

import aiosqlite
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import get_settings
from app.dependencies import CurrentUser

router = APIRouter()
_s     = get_settings()
_DB    = _s.db_path

# ── Manifest ──────────────────────────────────────────────────────────────────
MANIFEST = [
    {
        "id": "subnet_utilization", "title": "Subnet Utilization",
        "description": "All subnets by IP utilization, most-used first",
        "view_path": "/api/widgets/subnet_utilization",
        "default_w": 640, "default_h": 380, "min_w": 340, "min_h": 220,
    },
    {
        "id": "subnet_detail", "title": "Subnet Detail",
        "description": "Free/used/reserved/DHCP breakdown for one subnet",
        "view_path": "/api/widgets/subnet_detail",
        "default_w": 460, "default_h": 320, "min_w": 280, "min_h": 200,
        "params": [
            {
                "key": "subnet_id", "label": "Subnet", "type": "select",
                "options_path": "/api/widgets/options/subnets",
            }
        ],
    },
    {
        "id": "ip_conflicts", "title": "IP Conflicts",
        "description": "Active (unresolved) address conflicts",
        "view_path": "/api/widgets/ip_conflicts",
        "default_w": 640, "default_h": 340, "min_w": 320, "min_h": 200,
    },
    {
        "id": "active_alerts", "title": "Active Alerts",
        "description": "Unresolved IPAM alert events",
        "view_path": "/api/widgets/active_alerts",
        "default_w": 640, "default_h": 360, "min_w": 320, "min_h": 200,
    },
]


@router.get("/manifest")
async def widget_manifest():
    return MANIFEST


# ── Shared page shell ───────────────────────────────────────────────────────────
def _page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a1628;color:#e2e8f0;font-family:'Inter',system-ui,sans-serif;font-size:13px;height:100vh;overflow:hidden;display:flex;flex-direction:column}}
.hdr{{padding:8px 14px;border-bottom:1px solid #1e293b;display:flex;align-items:center;gap:8px;flex-shrink:0;height:36px}}
.hdr-dot{{width:6px;height:6px;border-radius:50%;background:#f472b6;flex-shrink:0}}
.hdr-title{{font-size:11px;font-weight:600;color:#94a3b8;letter-spacing:0.03em}}
.content{{flex:1;overflow:auto;padding:12px}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;font-size:10px;color:#475569;font-weight:600;text-transform:uppercase;letter-spacing:0.06em;padding:4px 8px;border-bottom:1px solid #1e293b}}
td{{padding:6px 8px;border-bottom:1px solid #0f172a;font-size:12px;color:#cbd5e1}}
tr:hover td{{background:#111827}}
.badge{{display:inline-block;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600}}
.bg{{background:#052e16;color:#4ade80}}.br{{background:#3f1515;color:#f87171}}
.by{{background:#422006;color:#fbbf24}}.bn{{background:#1e293b;color:#64748b}}
.empty{{text-align:center;padding:40px;color:#334155;font-size:12px}}
.bar-row{{display:flex;align-items:center;gap:8px;margin-bottom:8px}}
.bar-lbl{{font-size:11px;color:#94a3b8;width:150px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.bar-trk{{flex:1;background:#1e293b;border-radius:3px;height:8px;overflow:hidden}}
.bar-fill{{height:8px;border-radius:3px;background:#f472b6}}
.bar-val{{font-size:10px;color:#475569;width:40px;text-align:right;flex-shrink:0}}
.tile-row{{display:flex;gap:14px;margin-bottom:14px;flex-wrap:wrap}}
.tile{{flex:1;min-width:100px;background:#111827;border:1px solid #1e293b;border-radius:8px;padding:10px 12px}}
.tile-label{{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px}}
.tile-value{{font-size:22px;font-weight:700;color:#e2e8f0}}
</style>
<script>setTimeout(()=>location.reload(),30000)</script>
</head><body>
<div class="hdr"><div class="hdr-dot"></div><div class="hdr-title">{title}</div></div>
<div class="content">{body}</div>
</body></html>"""


# ── Subnet Utilization widget ─────────────────────────────────────────────────
@router.get("/subnet_utilization", response_class=HTMLResponse, include_in_schema=False)
async def widget_subnet_utilization(user: CurrentUser):
    rows = []
    try:
        async with aiosqlite.connect(_DB) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT s.id, s.cidr, s.description,
                          (SELECT pct_used FROM subnet_utilization_history
                           WHERE subnet_id = s.id ORDER BY id DESC LIMIT 1) AS pct_used
                   FROM subnets s ORDER BY s.cidr"""
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
    except Exception:
        pass

    rows.sort(key=lambda r: r["pct_used"] if r["pct_used"] is not None else -1, reverse=True)

    if rows:
        parts = []
        for r in rows:
            pct = r["pct_used"]
            pct_label = f"{pct:.0f}%" if pct is not None else "—"
            parts.append(
                f'<div class="bar-row"><span class="bar-lbl">{html.escape(str(r["cidr"]))}</span>'
                f'<div class="bar-trk"><div class="bar-fill" style="width:{pct or 0}%"></div></div>'
                f'<span class="bar-val">{pct_label}</span></div>'
            )
        body = "".join(parts)
    else:
        body = '<div class="empty">No subnets</div>'
    return HTMLResponse(_page("Subnet Utilization", body))


# ── Subnet Detail widget (per-subnet, dynamic) ───────────────────────────────
@router.get("/subnet_detail", response_class=HTMLResponse, include_in_schema=False)
async def widget_subnet_detail(user: CurrentUser, subnet_id: int | None = None):
    if not subnet_id:
        return HTMLResponse(_page("Subnet Detail", '<div class="empty">Select a subnet</div>'))

    cidr = str(subnet_id)
    counts: dict[str, int] = {}
    try:
        async with aiosqlite.connect(_DB) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT cidr FROM subnets WHERE id=?", (subnet_id,)) as cur:
                row = await cur.fetchone()
                if row:
                    cidr = row["cidr"]
            async with db.execute(
                "SELECT status, COUNT(*) as n FROM ip_addresses WHERE subnet_id=? GROUP BY status",
                (subnet_id,),
            ) as cur:
                counts = {r["status"]: r["n"] for r in await cur.fetchall()}
    except Exception:
        pass

    labels = [("free", "Free"), ("used", "Used"), ("static", "Static"),
              ("reserved", "Reserved"), ("dhcp", "DHCP"), ("conflict", "Conflict")]
    tiles = "".join(
        f'<div class="tile"><div class="tile-label">{label}</div><div class="tile-value">{counts.get(key, 0)}</div></div>'
        for key, label in labels
    )
    body = (
        f'<div style="margin-bottom:8px;color:#64748b;font-size:11px">{html.escape(str(cidr))}</div>'
        f'<div class="tile-row">{tiles}</div>'
    )
    return HTMLResponse(_page("Subnet Detail", body))


# ── IP Conflicts widget ────────────────────────────────────────────────────────
@router.get("/ip_conflicts", response_class=HTMLResponse, include_in_schema=False)
async def widget_ip_conflicts(user: CurrentUser):
    rows = []
    try:
        async with aiosqlite.connect(_DB) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT c.conflict_type, c.ip_address, c.detected_at, s.cidr
                   FROM conflicts c LEFT JOIN subnets s ON s.id = c.subnet_id
                   WHERE c.resolved_at IS NULL
                   ORDER BY c.detected_at DESC LIMIT 40"""
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
    except Exception:
        pass

    if rows:
        trs = "".join(
            f'<tr><td><span class="badge by">{html.escape(str(r["conflict_type"]).replace("_"," ").upper())}</span></td>'
            f"<td>{html.escape(str(r['ip_address']))}</td><td>{html.escape(str(r.get('cidr') or ''))}</td>"
            f"<td>{html.escape(str(r['detected_at'])[:19].replace('T',' '))}</td></tr>"
            for r in rows
        )
        body = (
            "<table><thead><tr><th>Type</th><th>IP</th><th>Subnet</th><th>Detected</th></tr></thead>"
            f"<tbody>{trs}</tbody></table>"
        )
    else:
        body = '<div class="empty">No active conflicts</div>'
    return HTMLResponse(_page("IP Conflicts", body))


# ── Active Alerts widget ──────────────────────────────────────────────────────
@router.get("/active_alerts", response_class=HTMLResponse, include_in_schema=False)
async def widget_active_alerts(user: CurrentUser):
    rows = []
    try:
        async with aiosqlite.connect(_DB) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT ae.severity, ae.message, ae.created_at, s.cidr
                   FROM alert_events ae LEFT JOIN subnets s ON s.id = ae.subnet_id
                   WHERE ae.active = 1 AND ae.acked = 0
                   ORDER BY ae.created_at DESC LIMIT 40"""
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
    except Exception:
        pass

    if rows:
        trs = "".join(
            f'<tr><td><span class="badge {"br" if r["severity"]=="critical" else "by"}">{html.escape(str(r["severity"]).upper())}</span></td>'
            f"<td>{html.escape(str(r.get('cidr') or ''))}</td><td>{html.escape(str(r['message']))}</td>"
            f"<td>{html.escape(str(r['created_at'])[:19].replace('T',' '))}</td></tr>"
            for r in rows
        )
        body = (
            "<table><thead><tr><th>Severity</th><th>Subnet</th><th>Message</th><th>Fired</th></tr></thead>"
            f"<tbody>{trs}</tbody></table>"
        )
    else:
        body = '<div class="empty">No active alerts</div>'
    return HTMLResponse(_page("Active Alerts", body))


# ── Param option pickers ──────────────────────────────────────────────────────
@router.get("/options/subnets")
async def widget_options_subnets(user: CurrentUser):
    try:
        async with aiosqlite.connect(_DB) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT id, cidr, description FROM subnets ORDER BY cidr") as cur:
                rows = [dict(r) for r in await cur.fetchall()]
        return JSONResponse([
            {"value": str(r["id"]), "label": r["cidr"] + (f" — {r['description']}" if r["description"] else "")}
            for r in rows
        ])
    except Exception:
        return JSONResponse([])
