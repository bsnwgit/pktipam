"""
pktIPAM — Widget endpoints for pktHub NOC Builder integration.

Manifest: GET /api/widgets/manifest  → list of widget definitions
Views:    GET /api/widgets/{id}      → server-rendered HTML page (iframe target)
Options:  GET /api/widgets/options/* → JSON [{value,label}] for dynamic param pickers
"""
from __future__ import annotations

import html
from contextvars import ContextVar

import aiosqlite
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import get_settings
from app.dependencies import CurrentUser, require_suite_token

# These views are embedded as unauthenticated iframes by pktHub's NOC Builder,
# so they can't require a login session — but they do render internal subnet,
# address and alert data, so every route on this router requires a valid
# X-Suite-Token (the trusted-proxy secret pktHub already sends on every
# proxied request).
# ── Refresh interval ──────────────────────────────────────────────────────────
# pktHub's Settings → NOC → "Widget refresh" governs how often a tile reloads
# itself. It arrives as ?refresh=<seconds> on the widget URL; captured here as a
# router dependency so the ~150 view functions need no signature change.
_REFRESH: ContextVar = ContextVar("widget_refresh", default=30)


async def _capture_refresh(request: Request) -> None:
    raw = request.query_params.get("refresh")
    try:
        _REFRESH.set(max(5, min(int(raw), 3600)) if raw else 30)
    except (TypeError, ValueError):
        _REFRESH.set(30)


router = APIRouter(dependencies=[Depends(_capture_refresh), Depends(require_suite_token)])
_s     = get_settings()
_DB    = _s.db_path

# ── Manifest ──────────────────────────────────────────────────────────────────
# `category` groups these in pktHub's NOC library picker. Every data surface the
# app renders in its own UI should have an entry here — the NOC builder can only
# offer what this list declares.
_SUBNET_PARAM = {
    "key": "subnet_id", "label": "Subnet", "type": "select",
    "options_path": "/api/widgets/options/subnets",
}

MANIFEST = [
    # ── Overview ──────────────────────────────────────────────────────────────
    {
        "id": "ipam_summary", "title": "IPAM Summary", "category": "Overview",
        "description": "Subnet, address and conflict counts across the estate",
        "view_path": "/api/widgets/ipam_summary",
        "default_w": 620, "default_h": 200, "min_w": 320, "min_h": 150,
    },
    {
        "id": "alert_summary", "title": "Alert Summary", "category": "Overview",
        "description": "Active alert counts by severity",
        "view_path": "/api/widgets/alert_summary",
        "default_w": 420, "default_h": 200, "min_w": 260, "min_h": 150,
    },
    {
        "id": "subnets_by_site", "title": "Subnets by Site", "category": "Overview",
        "description": "Subnet count per site",
        "view_path": "/api/widgets/subnets_by_site",
        "default_w": 460, "default_h": 300, "min_w": 270, "min_h": 180,
    },

    # ── Subnets ───────────────────────────────────────────────────────────────
    {
        "id": "subnet_utilization", "title": "Subnet Utilization", "category": "Subnets",
        "description": "All subnets by IP utilization, most-used first",
        "view_path": "/api/widgets/subnet_utilization",
        "default_w": 640, "default_h": 380, "min_w": 340, "min_h": 220,
    },
    {
        "id": "subnet_detail", "title": "Subnet Detail", "category": "Subnets",
        "description": "Free/used/reserved/DHCP breakdown for one subnet",
        "view_path": "/api/widgets/subnet_detail",
        "default_w": 460, "default_h": 320, "min_w": 280, "min_h": 200,
        "params": [_SUBNET_PARAM],
    },
    {
        "id": "subnet_exhaustion", "title": "Subnet Exhaustion", "category": "Subnets",
        "description": "Subnets closest to running out of addresses",
        "view_path": "/api/widgets/subnet_exhaustion",
        "default_w": 600, "default_h": 340, "min_w": 320, "min_h": 200,
    },
    {
        "id": "subnet_growth", "title": "Subnet Growth", "category": "Subnets",
        "description": "Utilization over time for one subnet",
        "view_path": "/api/widgets/subnet_growth",
        "default_w": 680, "default_h": 320, "min_w": 320, "min_h": 180,
        "params": [_SUBNET_PARAM],
    },

    # ── Addresses ─────────────────────────────────────────────────────────────
    {
        "id": "address_status", "title": "Address Status", "category": "Addresses",
        "description": "Address distribution across free, used, reserved and DHCP",
        "view_path": "/api/widgets/address_status",
        "default_w": 460, "default_h": 280, "min_w": 270, "min_h": 170,
    },
    {
        "id": "addresses_by_source", "title": "Addresses by Source", "category": "Addresses",
        "description": "How addresses entered the inventory — manual, DHCP, DNS or ARP",
        "view_path": "/api/widgets/addresses_by_source",
        "default_w": 460, "default_h": 280, "min_w": 270, "min_h": 170,
    },
    {
        "id": "recent_addresses", "title": "Recently Seen", "category": "Addresses",
        "description": "Addresses observed most recently",
        "view_path": "/api/widgets/recent_addresses",
        "default_w": 700, "default_h": 360, "min_w": 340, "min_h": 200,
    },

    # ── DHCP & DNS ────────────────────────────────────────────────────────────
    {
        "id": "dhcp_leases", "title": "DHCP Leases", "category": "DHCP & DNS",
        "description": "Active DHCP leases, newest first",
        "view_path": "/api/widgets/dhcp_leases",
        "default_w": 700, "default_h": 360, "min_w": 340, "min_h": 200,
    },
    {
        "id": "lease_expiry", "title": "Lease Expiry", "category": "DHCP & DNS",
        "description": "Leases expiring soonest",
        "view_path": "/api/widgets/lease_expiry",
        "default_w": 640, "default_h": 340, "min_w": 320, "min_h": 200,
    },
    {
        "id": "dns_records", "title": "DNS Records", "category": "DHCP & DNS",
        "description": "Record counts by zone and type",
        "view_path": "/api/widgets/dns_records",
        "default_w": 540, "default_h": 320, "min_w": 300, "min_h": 190,
    },

    # ── Network ───────────────────────────────────────────────────────────────
    {
        "id": "vlans", "title": "VLANs", "category": "Network",
        "description": "VLAN inventory with attached subnets",
        "view_path": "/api/widgets/vlans",
        "default_w": 620, "default_h": 340, "min_w": 320, "min_h": 200,
    },
    {
        "id": "routes", "title": "Routes", "category": "Network",
        "description": "Discovered routing table entries",
        "view_path": "/api/widgets/routes",
        "default_w": 720, "default_h": 360, "min_w": 340, "min_h": 200,
    },
    {
        "id": "arp_entries", "title": "ARP Table", "category": "Network",
        "description": "Recently discovered IP-to-MAC bindings",
        "view_path": "/api/widgets/arp_entries",
        "default_w": 700, "default_h": 360, "min_w": 340, "min_h": 200,
    },

    # ── Conflicts & Alerts ────────────────────────────────────────────────────
    {
        "id": "ip_conflicts", "title": "IP Conflicts", "category": "Conflicts & Alerts",
        "description": "Active (unresolved) address conflicts",
        "view_path": "/api/widgets/ip_conflicts",
        "default_w": 640, "default_h": 340, "min_w": 320, "min_h": 200,
    },
    {
        "id": "active_alerts", "title": "Active Alerts", "category": "Conflicts & Alerts",
        "description": "Unresolved IPAM alert events",
        "view_path": "/api/widgets/active_alerts",
        "default_w": 640, "default_h": 360, "min_w": 320, "min_h": 200,
    },

    # ── Collectors ────────────────────────────────────────────────────────────
    {
        "id": "collector_status", "title": "Collector Status", "category": "Collectors",
        "description": "DHCP/DNS/device collector health and last poll",
        "view_path": "/api/widgets/collector_status",
        "default_w": 660, "default_h": 320, "min_w": 320, "min_h": 190,
    },
]


@router.get("/manifest")
async def widget_manifest():
    return MANIFEST



# ── Widget states ──────────────────────────────────────────────────────────────
# A blank tile on a wallboard reads as "all quiet", so the three reasons a widget
# can show nothing must look different from each other:
#   empty — the query ran and there genuinely is nothing
#   cfg   — the widget needs a param chosen in the NOC editor before it can run
#   err   — the query failed; this must never be mistaken for "nothing to report"
# Query helpers record failures here rather than swallowing them; _page() renders
# the error state instead of whatever half-built body the caller produced. The
# ContextVar is per-request: each request runs in its own task context.
_WIDGET_ERR: ContextVar = ContextVar("widget_err", default=None)


def _note_err(exc: BaseException) -> None:
    _WIDGET_ERR.set(f"{type(exc).__name__}: {exc}"[:200])


def _state(kind: str, msg: str, sub: str = "") -> str:
    icon = {"empty": "○", "cfg": "⚙", "err": "⚠"}.get(kind, "○")
    sub_html = f'<div class="state-sub">{html.escape(str(sub))}</div>' if sub else ""
    return (f'<div class="state state-{kind}"><div class="state-icon">{icon}</div>'
            f'<div class="state-msg">{html.escape(str(msg))}</div>{sub_html}</div>')


def _empty(msg: str) -> str:
    return _state("empty", msg)


def _needs(msg: str) -> str:
    """The widget is fine — it is waiting on a filter the NOC editor must set."""
    return _state("cfg", msg, "Select it in the widget's Filters panel")


# ── Shared page shell ───────────────────────────────────────────────────────────
def _page(title: str, body: str) -> str:
    # Widget titles carry device/metric/subnet names chosen in the NOC editor
    # and read back from device data, and these pages render on an
    # unauthenticated display URL — escape before interpolating.
    title = html.escape(str(title))
    # A failed query leaves a body saying "nothing here" — which is a lie.
    _err = _WIDGET_ERR.get()
    if _err:
        body = _state("err", "Widget unavailable", _err)
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#04060a;color:#e2e8f0;font-family:'Inter',system-ui,sans-serif;font-size:13px;height:100vh;overflow:hidden;display:flex;flex-direction:column}}
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
.chart-wrap{{width:100%;height:100%;min-height:90px;display:flex;flex-direction:column}}
.chart-meta{{display:flex;gap:12px;font-size:10px;color:#475569;margin-bottom:6px;flex-wrap:wrap}}
.chart-meta b{{color:#94a3b8;font-weight:600}}
.chart-svg{{flex:1;width:100%;min-height:0}}
.legend{{display:flex;gap:12px;font-size:10px;color:#94a3b8;margin-top:6px;flex-wrap:wrap}}
.legend i{{width:8px;height:2px;display:inline-block;margin-right:4px;vertical-align:middle}}
.state{{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;min-height:80px;text-align:center;padding:18px;gap:5px}}
.state-icon{{font-size:17px;line-height:1;opacity:0.85}}
.state-msg{{font-size:12px;font-weight:500}}
.state-sub{{font-size:10px;color:#64748b;max-width:92%;word-break:break-word}}
.state-empty{{color:#64748b}}
.state-cfg{{color:#fbbf24}}
.state-err{{color:#f87171}}
</style>
<script>setTimeout(()=>location.reload(),{_REFRESH.get() * 1000})</script>
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
    except Exception as exc:
        _note_err(exc)

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
        body = _empty('No subnets defined')
    return HTMLResponse(_page("Subnet Utilization", body))


# ── Subnet Detail widget (per-subnet, dynamic) ───────────────────────────────
@router.get("/subnet_detail", response_class=HTMLResponse, include_in_schema=False)
async def widget_subnet_detail(user: CurrentUser, subnet_id: int | None = None):
    if not subnet_id:
        return HTMLResponse(_page("Subnet Detail", _needs('Select a subnet')))

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
    except Exception as exc:
        _note_err(exc)

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
    except Exception as exc:
        _note_err(exc)

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
        body = _empty('No active conflicts')
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
    except Exception as exc:
        _note_err(exc)

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
        body = _empty('No active alerts')
    return HTMLResponse(_page("Active Alerts", body))


# ── Query helper ──────────────────────────────────────────────────────────────
async def _rows(sql: str, params: tuple = ()) -> list[dict]:
    try:
        async with aiosqlite.connect(_DB) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, params) as cur:
                return [dict(r) for r in await cur.fetchall()]
    except Exception as exc:
        _note_err(exc)
        return []


def _fmt_ts(ts) -> str:
    return str(ts)[:19].replace("T", " ") if ts else "—"


def _fmt_n(n) -> str:
    try:
        return f"{float(n or 0):.0f}"
    except (TypeError, ValueError):
        return "—"


def _tiles(pairs) -> str:
    return '<div class="tile-row">' + "".join(
        f'<div class="tile"><div class="tile-label">{html.escape(str(label))}</div>'
        f'<div class="tile-value">{html.escape(str(value))}</div></div>'
        for label, value in pairs
    ) + "</div>"


def _bars(rows, color: str = "#f472b6") -> str:
    """rows = [(label, numeric_value, display_value)] — scaled to the largest."""
    peak = max((r[1] or 0) for r in rows) if rows else 0
    return "".join(
        f'<div class="bar-row"><div class="bar-lbl" title="{html.escape(str(lbl))}">{html.escape(str(lbl))}</div>'
        f'<div class="bar-trk"><div class="bar-fill" style="width:{(val / peak * 100) if peak else 0:.1f}%;background:{color}"></div></div>'
        f'<div class="bar-val">{html.escape(str(disp))}</div></div>'
        for lbl, val, disp in rows
    )


# ── Inline SVG line chart ─────────────────────────────────────────────────────
# Server-rendered so the iframe stays dependency-free — pktIPAM ships no charting
# library to these views, and the NOC display must render without network access
# to anything but this app.
_SERIES_COLORS = ("#f472b6", "#60a5fa", "#4ade80", "#fbbf24", "#a78bfa")


def _line_chart(series, fmt=_fmt_n, height: int = 120) -> str:
    """series = [(label, [float, ...])] — equal-length samples, oldest first."""
    series = [(lbl, [v for v in vals if v is not None]) for lbl, vals in series]
    series = [(lbl, vals) for lbl, vals in series if len(vals) >= 2]
    if not series:
        return _empty('Not enough history yet')

    W, H, PAD = 600, height, 4
    lo = min(min(v) for _, v in series)
    hi = max(max(v) for _, v in series)
    span = (hi - lo) or 1.0

    def _y(v: float) -> float:
        return PAD + (H - 2 * PAD) * (1 - (v - lo) / span)

    paths, legend = [], []
    for i, (lbl, vals) in enumerate(series):
        color = _SERIES_COLORS[i % len(_SERIES_COLORS)]
        step  = W / (len(vals) - 1)
        pts   = [(j * step, _y(v)) for j, v in enumerate(vals)]
        line  = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        area  = f"{line} L{W:.1f},{H} L0,{H} Z"
        paths.append(
            f'<path d="{area}" fill="{color}" opacity="0.10"/>'
            f'<path d="{line}" fill="none" stroke="{color}" stroke-width="1.5" '
            f'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
        )
        legend.append(
            f'<span><i style="background:{color}"></i>{html.escape(str(lbl))} '
            f'<b>{html.escape(fmt(vals[-1]))}</b></span>'
        )

    meta = (f'<div class="chart-meta"><span>min <b>{html.escape(fmt(lo))}</b></span>'
            f'<span>max <b>{html.escape(fmt(hi))}</b></span>'
            f'<span>samples <b>{max(len(v) for _, v in series)}</b></span></div>')
    return (
        f'<div class="chart-wrap">{meta}'
        f'<svg class="chart-svg" viewBox="0 0 {W} {H}" preserveAspectRatio="none" '
        f'xmlns="http://www.w3.org/2000/svg">{"".join(paths)}</svg>'
        f'<div class="legend">{"".join(legend)}</div></div>'
    )


# ── IPAM Summary widget ───────────────────────────────────────────────────────
@router.get("/ipam_summary", response_class=HTMLResponse, include_in_schema=False)
async def widget_ipam_summary(user: CurrentUser):
    subnets = await _rows("SELECT COUNT(*) AS n FROM subnets")
    addrs   = await _rows(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN status IN ('used','static') THEN 1 ELSE 0 END) AS used,
                  SUM(CASE WHEN status = 'free'             THEN 1 ELSE 0 END) AS free,
                  SUM(CASE WHEN status = 'dhcp'             THEN 1 ELSE 0 END) AS dhcp
           FROM ip_addresses"""
    )
    confl   = await _rows("SELECT COUNT(*) AS n FROM conflicts WHERE resolved_at IS NULL")
    a = addrs[0] if addrs else {}
    body = _tiles([
        ("Subnets",   (subnets[0]["n"] if subnets else 0) or 0),
        ("Addresses", a.get("total") or 0),
        ("Used",      a.get("used")  or 0),
        ("Free",      a.get("free")  or 0),
        ("DHCP",      a.get("dhcp")  or 0),
        ("Conflicts", (confl[0]["n"] if confl else 0) or 0),
    ])
    return HTMLResponse(_page("IPAM Summary", body))


# ── Alert Summary widget ──────────────────────────────────────────────────────
@router.get("/alert_summary", response_class=HTMLResponse, include_in_schema=False)
async def widget_alert_summary(user: CurrentUser):
    rows   = await _rows(
        "SELECT LOWER(severity) AS sev, COUNT(*) AS n FROM alert_events "
        "WHERE active = 1 AND acked = 0 GROUP BY sev"
    )
    counts = {r["sev"]: r["n"] for r in rows}
    body   = _tiles([
        ("Active",   sum(counts.values())),
        ("Critical", counts.get("critical", 0)),
        ("Warning",  counts.get("warning", 0)),
        ("Info",     counts.get("info", 0)),
    ])
    return HTMLResponse(_page("Alert Summary", body))


# ── Subnets by Site widget ────────────────────────────────────────────────────
@router.get("/subnets_by_site", response_class=HTMLResponse, include_in_schema=False)
async def widget_subnets_by_site(user: CurrentUser):
    rows = await _rows(
        "SELECT CASE WHEN site IS NULL OR site = '' THEN 'Unassigned' ELSE site END AS site, "
        "COUNT(*) AS n FROM subnets GROUP BY site ORDER BY n DESC LIMIT 20"
    )
    body = _bars([(r["site"], r["n"], str(r["n"])) for r in rows]) \
        if rows else _empty('No subnets defined')
    return HTMLResponse(_page("Subnets by Site", body))


# ── Subnet Exhaustion widget ──────────────────────────────────────────────────
@router.get("/subnet_exhaustion", response_class=HTMLResponse, include_in_schema=False)
async def widget_subnet_exhaustion(user: CurrentUser):
    rows = await _rows(
        """SELECT s.cidr, s.description, h.pct_used, h.used_count, h.total_count
           FROM subnets s
           JOIN subnet_utilization_history h ON h.id = (
               SELECT id FROM subnet_utilization_history
               WHERE subnet_id = s.id ORDER BY id DESC LIMIT 1)
           ORDER BY h.pct_used DESC LIMIT 25"""
    )
    body = _bars([
        (r["cidr"], float(r["pct_used"] or 0),
         f"{float(r['pct_used'] or 0):.0f}% ({r['used_count']}/{r['total_count']})")
        for r in rows
    ]) if rows else _empty('No utilization history yet')
    return HTMLResponse(_page("Subnet Exhaustion", body))


# ── Subnet Growth widget (chart) ──────────────────────────────────────────────
@router.get("/subnet_growth", response_class=HTMLResponse, include_in_schema=False)
async def widget_subnet_growth(user: CurrentUser, subnet_id: int | None = None):
    if not subnet_id:
        return HTMLResponse(_page("Subnet Growth", _needs('Select a subnet')))

    # A NOC screen outlives the plan it was built against — say so plainly rather
    # than render an empty chart the wall-watcher reads as "no growth".
    subnet = await _rows("SELECT cidr FROM subnets WHERE id = ?", (subnet_id,))
    if not subnet:
        return HTMLResponse(_page("Subnet Growth",
                                  f_empty('Subnet {html.escape(str(subnet_id))} no longer exists')))

    rows = await _rows(
        """SELECT pct_used FROM subnet_utilization_history
           WHERE subnet_id = ? ORDER BY id ASC LIMIT 500""",
        (subnet_id,),
    )
    body = _line_chart([("Utilization", [r["pct_used"] for r in rows])],
                       fmt=lambda v: f"{float(v):.0f}%")
    return HTMLResponse(_page(f"{subnet[0]['cidr']} utilization", body))


# ── Address Status widget ─────────────────────────────────────────────────────
@router.get("/address_status", response_class=HTMLResponse, include_in_schema=False)
async def widget_address_status(user: CurrentUser):
    rows = await _rows(
        "SELECT status, COUNT(*) AS n FROM ip_addresses GROUP BY status ORDER BY n DESC"
    )
    body = _bars([(r["status"], r["n"], str(r["n"])) for r in rows]) \
        if rows else _empty('No addresses recorded in any subnet')
    return HTMLResponse(_page("Address Status", body))


# ── Addresses by Source widget ────────────────────────────────────────────────
@router.get("/addresses_by_source", response_class=HTMLResponse, include_in_schema=False)
async def widget_addresses_by_source(user: CurrentUser):
    rows = await _rows(
        "SELECT COALESCE(NULLIF(source,''),'unknown') AS source, COUNT(*) AS n "
        "FROM ip_addresses GROUP BY source ORDER BY n DESC"
    )
    body = _bars([(r["source"], r["n"], str(r["n"])) for r in rows]) \
        if rows else _empty('No addresses recorded in any subnet')
    return HTMLResponse(_page("Addresses by Source", body))


# ── Recently Seen widget ──────────────────────────────────────────────────────
@router.get("/recent_addresses", response_class=HTMLResponse, include_in_schema=False)
async def widget_recent_addresses(user: CurrentUser):
    rows = await _rows(
        """SELECT a.ip_address, a.hostname, a.mac_address, a.status, a.source, a.last_seen, s.cidr
           FROM ip_addresses a LEFT JOIN subnets s ON s.id = a.subnet_id
           WHERE a.last_seen IS NOT NULL ORDER BY a.last_seen DESC LIMIT 40"""
    )
    if rows:
        trs = "".join(
            f"<tr><td>{html.escape(str(r['ip_address']))}</td>"
            f"<td>{html.escape(str(r.get('hostname') or ''))}</td>"
            f"<td>{html.escape(str(r.get('mac_address') or ''))}</td>"
            f"<td>{html.escape(str(r.get('cidr') or ''))}</td>"
            f"<td>{html.escape(str(r.get('source') or ''))}</td>"
            f"<td>{html.escape(_fmt_ts(r.get('last_seen')))}</td></tr>"
            for r in rows
        )
        body = ("<table><thead><tr><th>Address</th><th>Hostname</th><th>MAC</th>"
                "<th>Subnet</th><th>Source</th><th>Last Seen</th></tr></thead>"
                f"<tbody>{trs}</tbody></table>")
    else:
        body = _empty('No addresses seen')
    return HTMLResponse(_page("Recently Seen", body))


# ── DHCP Leases widget ────────────────────────────────────────────────────────
@router.get("/dhcp_leases", response_class=HTMLResponse, include_in_schema=False)
async def widget_dhcp_leases(user: CurrentUser):
    rows = await _rows(
        """SELECT ip_address, mac_address, hostname, state, starts_at, ends_at
           FROM dhcp_leases WHERE state = 'active' ORDER BY last_seen DESC LIMIT 40"""
    )
    if rows:
        trs = "".join(
            f"<tr><td>{html.escape(str(r['ip_address']))}</td>"
            f"<td>{html.escape(str(r.get('mac_address') or ''))}</td>"
            f"<td>{html.escape(str(r.get('hostname') or ''))}</td>"
            f"<td>{html.escape(_fmt_ts(r.get('ends_at')))}</td></tr>"
            for r in rows
        )
        body = ("<table><thead><tr><th>Address</th><th>MAC</th><th>Hostname</th>"
                "<th>Expires</th></tr></thead>"
                f"<tbody>{trs}</tbody></table>")
    else:
        body = _empty('No DHCP collector reports an active lease')
    return HTMLResponse(_page("DHCP Leases", body))


# ── Lease Expiry widget ───────────────────────────────────────────────────────
@router.get("/lease_expiry", response_class=HTMLResponse, include_in_schema=False)
async def widget_lease_expiry(user: CurrentUser):
    rows = await _rows(
        """SELECT ip_address, mac_address, hostname, ends_at FROM dhcp_leases
           WHERE state = 'active' AND ends_at IS NOT NULL
           ORDER BY ends_at ASC LIMIT 40"""
    )
    if rows:
        trs = "".join(
            f"<tr><td>{html.escape(str(r['ip_address']))}</td>"
            f"<td>{html.escape(str(r.get('hostname') or r.get('mac_address') or ''))}</td>"
            f"<td>{html.escape(_fmt_ts(r.get('ends_at')))}</td></tr>"
            for r in rows
        )
        body = ("<table><thead><tr><th>Address</th><th>Client</th><th>Expires</th></tr></thead>"
                f"<tbody>{trs}</tbody></table>")
    else:
        body = _empty('No leases with an expiry')
    return HTMLResponse(_page("Lease Expiry", body))


# ── DNS Records widget ────────────────────────────────────────────────────────
@router.get("/dns_records", response_class=HTMLResponse, include_in_schema=False)
async def widget_dns_records(user: CurrentUser):
    rows = await _rows(
        "SELECT zone, record_type, COUNT(*) AS n FROM dns_records "
        "GROUP BY zone, record_type ORDER BY n DESC LIMIT 25"
    )
    body = _bars([
        (f"{r['zone']} · {r['record_type']}", r["n"], str(r["n"])) for r in rows
    ]) if rows else _empty('No DNS collector has returned records')
    return HTMLResponse(_page("DNS Records", body))


# ── VLANs widget ──────────────────────────────────────────────────────────────
@router.get("/vlans", response_class=HTMLResponse, include_in_schema=False)
async def widget_vlans(user: CurrentUser):
    rows = await _rows(
        """SELECT v.vlan_tag, v.name, v.site, COUNT(s.id) AS subnets
           FROM vlans v LEFT JOIN subnets s ON s.vlan_id = v.id
           GROUP BY v.id ORDER BY v.vlan_tag LIMIT 60"""
    )
    if rows:
        trs = "".join(
            f"<tr><td>{r['vlan_tag']}</td><td>{html.escape(str(r['name']))}</td>"
            f"<td>{html.escape(str(r.get('site') or ''))}</td><td>{r['subnets']}</td></tr>"
            for r in rows
        )
        body = ("<table><thead><tr><th>Tag</th><th>Name</th><th>Site</th><th>Subnets</th></tr></thead>"
                f"<tbody>{trs}</tbody></table>")
    else:
        body = _empty('No VLANs')
    return HTMLResponse(_page("VLANs", body))


# ── Routes widget ─────────────────────────────────────────────────────────────
@router.get("/routes", response_class=HTMLResponse, include_in_schema=False)
async def widget_routes(user: CurrentUser):
    rows = await _rows(
        """SELECT device_label, destination, next_hop, interface, protocol, metric
           FROM routes ORDER BY last_seen DESC LIMIT 50"""
    )
    if rows:
        trs = "".join(
            f"<tr><td>{html.escape(str(r.get('device_label') or ''))}</td>"
            f"<td>{html.escape(str(r['destination']))}</td>"
            f"<td>{html.escape(str(r.get('next_hop') or ''))}</td>"
            f"<td>{html.escape(str(r.get('interface') or ''))}</td>"
            f"<td>{html.escape(str(r.get('protocol') or ''))}</td></tr>"
            for r in rows
        )
        body = ("<table><thead><tr><th>Device</th><th>Destination</th><th>Next Hop</th>"
                "<th>Interface</th><th>Proto</th></tr></thead>"
                f"<tbody>{trs}</tbody></table>")
    else:
        body = _empty('No collector has returned routing entries')
    return HTMLResponse(_page("Routes", body))


# ── ARP Table widget ──────────────────────────────────────────────────────────
@router.get("/arp_entries", response_class=HTMLResponse, include_in_schema=False)
async def widget_arp_entries(user: CurrentUser):
    rows = await _rows(
        """SELECT device_label, ip_address, mac_address, interface, vlan_tag, last_seen
           FROM arp_entries ORDER BY last_seen DESC LIMIT 50"""
    )
    if rows:
        trs = "".join(
            f"<tr><td>{html.escape(str(r['ip_address']))}</td>"
            f"<td>{html.escape(str(r.get('mac_address') or ''))}</td>"
            f"<td>{html.escape(str(r.get('device_label') or ''))}</td>"
            f"<td>{html.escape(str(r.get('interface') or ''))}</td>"
            f"<td>{r.get('vlan_tag') if r.get('vlan_tag') is not None else '—'}</td></tr>"
            for r in rows
        )
        body = ("<table><thead><tr><th>Address</th><th>MAC</th><th>Device</th>"
                "<th>Interface</th><th>VLAN</th></tr></thead>"
                f"<tbody>{trs}</tbody></table>")
    else:
        body = _empty('No collector has returned ARP bindings')
    return HTMLResponse(_page("ARP Table", body))


# ── Collector Status widget ───────────────────────────────────────────────────
@router.get("/collector_status", response_class=HTMLResponse, include_in_schema=False)
async def widget_collector_status(user: CurrentUser):
    rows = await _rows(
        """SELECT name, category, collector_type, enabled, status, last_poll_at, last_error
           FROM collectors ORDER BY category, name"""
    )
    if rows:
        def _badge(r) -> str:
            if not r.get("enabled"):
                return '<span class="badge bn">DISABLED</span>'
            s = (r.get("status") or "unknown").lower()
            cls = "bg" if s == "ok" else ("br" if s == "error" else "bn")
            return f'<span class="badge {cls}">{html.escape(s.upper())}</span>'

        trs = "".join(
            f"<tr><td>{html.escape(str(r['name']))}</td>"
            f"<td>{html.escape(str(r.get('category') or ''))}</td>"
            f"<td>{html.escape(str(r.get('collector_type') or ''))}</td>"
            f"<td>{_badge(r)}</td>"
            f"<td>{html.escape(_fmt_ts(r.get('last_poll_at')))}</td></tr>"
            for r in rows
        )
        body = ("<table><thead><tr><th>Collector</th><th>Category</th><th>Type</th>"
                "<th>Status</th><th>Last Poll</th></tr></thead>"
                f"<tbody>{trs}</tbody></table>")
    else:
        body = _empty('No collectors')
    return HTMLResponse(_page("Collector Status", body))


# ── Param option pickers ──────────────────────────────────────────────────────
# Reads live state rather than a static list, so a subnet added or removed after
# a NOC screen was built shows up (or drops out) the next time the editor opens
# the param — no manifest edit and no pktHub change needed.
@router.get("/options/subnets")
async def widget_options_subnets(user: CurrentUser):
    rows = await _rows("SELECT id, cidr, description FROM subnets ORDER BY cidr")
    return JSONResponse([
        {"value": str(r["id"]), "label": r["cidr"] + (f" — {r['description']}" if r["description"] else "")}
        for r in rows
    ])
