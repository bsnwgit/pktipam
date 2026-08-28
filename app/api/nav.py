"""
pktIPAM — Navigation manifest for pktHub's APPS sidebar.

Manifest: GET /api/nav/manifest  → this app's own left-nav, in display order

pktHub mirrors these entries under pktIPAM in its own sidebar and opens each
one as a chromeless embed of the real page (`/proxy/<app_id><path>?chromeless=1`),
so the hub's menu is this app's menu rather than a re-implementation of it.

Keep in step with NAV in frontend/src/components/Layout.tsx — that const is
what this app renders for a direct visit, this manifest is what the hub
renders. Same menu, two consumers: a page added to one belongs in the other.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import require_suite_token

# Fetched unauthenticated by pktHub's health poller, and it discloses this
# app's page structure — so it carries the same X-Suite-Token gate as the
# widget endpoints in app/api/widgets.py.
router = APIRouter(dependencies=[Depends(require_suite_token)])

# ── Manifest ──────────────────────────────────────────────────────────────────
# `path` is relative to this app's root. `icon` is the same glyph the app's own
# sidebar draws, so the hub renders a visually identical row.
NAV_MANIFEST = [
    {"path": "/",                 "label": "Dashboard",        "icon": "◑", "admin_only": False},
    {"path": "/dhcp-leases",      "label": "DHCP Leases",      "icon": "⇄", "admin_only": False},
    {"path": "/dns-records",      "label": "DNS Records",      "icon": "≡", "admin_only": False},
    {"path": "/routes",           "label": "Routing Tables",   "icon": "⇉", "admin_only": False},
    {"path": "/ip-addresses",     "label": "IP Addresses",     "icon": "▤", "admin_only": False},
    {"path": "/conflicts",        "label": "Conflicts",        "icon": "⚠", "admin_only": False},
    {"path": "/subnets",          "label": "Subnets",          "icon": "▦", "admin_only": False, "divider_before": True},
    {"path": "/vlans",            "label": "VLANs",            "icon": "⬡", "admin_only": False},
    {"path": "/capacity-planner", "label": "Capacity Planner", "icon": "⊞", "admin_only": False},
    {"path": "/alerts",           "label": "Alerts",           "icon": "△", "admin_only": False, "divider_before": True},
    {"path": "/logs",             "label": "Logs",             "icon": "☰", "admin_only": False},
    {"path": "/settings",         "label": "Settings",         "icon": "⚙", "admin_only": True,  "divider_before": True},
]


@router.get("/manifest")
async def nav_manifest():
    return NAV_MANIFEST
