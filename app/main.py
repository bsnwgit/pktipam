"""
pktIPAM — FastAPI application entry point.
"""
from __future__ import annotations

import logging
import os.path
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import init_db, seed_admin

# -- Routers -------------------------------------------------------------------
from app.api import (
    auth,
    users,
    settings as settings_router,
    system as system_router,
    subnets as subnets_router,
    vlans as vlans_router,
    sites as sites_router,
    ip_addresses as ip_addresses_router,
    ip_address_history as ip_address_history_router,
    dhcp_leases as dhcp_leases_router,
    dns_records as dns_records_router,
    routes as routes_router,
    conflicts as conflicts_router,
    alerts as alerts_router,
    logs as logs_router,
    collectors as collectors_router,
    integrations as integrations_router,
    suite as suite_router,
    user_api_keys as user_api_keys_router,
    snmp_credentials as snmp_credentials_router,
    ip_info as ip_info_router,
    mxtoolbox as mxtoolbox_router,
    widgets as widgets_router,
    nav as nav_router,
    capacity as capacity_router,
    docs as docs_router,
)
from app.api import resonance as resonance_router
from app.api import resonance_data as resonance_data_router

settings = get_settings()
log = logging.getLogger("pktipam")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # -- Startup ---------------------------------------------------------------
    from app.logging_handler import SQLiteLogHandler
    _log_handler = SQLiteLogHandler(db_path=settings.db_path)
    _log_handler.attach_to_root_logger("pktipam")
    app.state.log_handler = _log_handler

    log.info("pktIPAM starting up")
    # Ship our own logs to pktLog if configured.
    try:
        import json as _json, logging as _logging
        import aiosqlite as _aio
        _fwd: dict = {}
        async with _aio.connect(settings.db_path) as _db:
            async with _db.execute(
                "SELECT key, value FROM settings WHERE key LIKE 'log_forward_%'"
            ) as _cur:
                for _k, _v in await _cur.fetchall():
                    try:
                        _fwd[_k] = _json.loads(_v)
                    except Exception:
                        _fwd[_k] = _v
        if _fwd.get("log_forward_enabled"):
            from app.log_forward import configure_forwarding
            configure_forwarding(
                enabled=True,
                host=str(_fwd.get("log_forward_host") or ""),
                port=int(_fwd.get("log_forward_port") or 5514),
                protocol=str(_fwd.get("log_forward_protocol") or "udp"),
                level=getattr(_logging, str(_fwd.get("log_forward_level") or "INFO"), _logging.INFO),
                app_name=str(_fwd.get("log_forward_app_name") or "pktipam"),
            )
    except Exception as _e:
        log.warning(f"Log forwarding setup skipped: {_e}")

    await init_db()
    log.info("Database migrations applied")

    await seed_admin()
    log.info("Admin seed check complete")

    from app.ipam.alerts.engine import AlertEngine
    alert_engine = AlertEngine()
    await alert_engine.start(settings.db_path)
    app.state.alert_engine = alert_engine
    log.info("Alert engine started")

    from app.ipam.alerts.cleanup import AlertCleanup
    cleanup = AlertCleanup()
    await cleanup.start()
    log.info("Alert cleanup started")

    from app.backup import BackupScheduler
    backup_scheduler = BackupScheduler()
    await backup_scheduler.start()
    log.info("Backup scheduler started")

    from app.ipam.poll_engine import PollEngine
    poll_engine = PollEngine()
    await poll_engine.start(settings.db_path)
    app.state.poll_engine = poll_engine
    log.info("Collector poll engine started")

    from app.ipam.reconcile_engine import ReconcileEngine
    reconcile_engine = ReconcileEngine()
    await reconcile_engine.start(settings.db_path)
    app.state.reconcile_engine = reconcile_engine
    log.info("Reconciliation engine started")

    yield

    # -- Shutdown ----------------------------------------------------------------
    log.info("pktIPAM shutting down")
    await reconcile_engine.stop()
    await poll_engine.stop()
    await alert_engine.stop()
    await cleanup.stop()
    await backup_scheduler.stop()
    _log_handler.stop()
    log.info("Shutdown complete")


# -- App -------------------------------------------------------------------------

app = FastAPI(
    title="pktIPAM",
    description="Enterprise IP Address Management — subnets, DHCP/DNS/device reconciliation, and conflict detection for the pkt suite",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# -- Middleware --------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- API Routers -----------------------------------------------------------------

app.include_router(auth.router,             prefix="/api/auth",         tags=["auth"])
app.include_router(users.router,            prefix="/api/users",        tags=["users"])
app.include_router(subnets_router.router,   prefix="/api/subnets",      tags=["subnets"])
app.include_router(vlans_router.router,     prefix="/api/vlans",        tags=["vlans"])
app.include_router(capacity_router.router,  prefix="/api/capacity",     tags=["capacity"])
app.include_router(sites_router.router,     prefix="/api/sites",        tags=["sites"])
app.include_router(ip_addresses_router.router, prefix="/api/ip-addresses", tags=["ip-addresses"])
app.include_router(ip_address_history_router.router, prefix="/api/ip-address-history", tags=["ip-address-history"])
app.include_router(dhcp_leases_router.router, prefix="/api/dhcp-leases", tags=["dhcp-leases"])
app.include_router(dns_records_router.router, prefix="/api/dns-records", tags=["dns-records"])
app.include_router(routes_router.router,    prefix="/api/routes",       tags=["routes"])
app.include_router(conflicts_router.router, prefix="/api/conflicts",    tags=["conflicts"])
app.include_router(alerts_router.router,    prefix="/api/alerts",       tags=["alerts"])
app.include_router(logs_router.router,      prefix="/api/logs",         tags=["logs"])
app.include_router(collectors_router.router, prefix="/api/collectors", tags=["collectors"])
app.include_router(snmp_credentials_router.router, prefix="/api/snmp-credentials", tags=["snmp-credentials"])
app.include_router(integrations_router.router, prefix="/api/integrations", tags=["integrations"])
app.include_router(settings_router.router,  prefix="/api/settings",     tags=["settings"])
app.include_router(system_router.router,    prefix="/api/system",       tags=["system"])
app.include_router(suite_router.router,     prefix="/api/suite",        tags=["suite"])
app.include_router(user_api_keys_router.router, prefix="/api/user-api-keys", tags=["user-api-keys"])
app.include_router(ip_info_router.router,   prefix="/api/ip-info",      tags=["ip-info"])
app.include_router(mxtoolbox_router.router, prefix="/api/mxtoolbox",    tags=["mxtoolbox"])
app.include_router(widgets_router.router,   prefix="/api/widgets",      tags=["widgets"])
app.include_router(nav_router.router,       prefix="/api/nav",          tags=["nav"])
app.include_router(docs_router.router,      prefix="/api/docs-content", tags=["docs"])
app.include_router(resonance_router.router, prefix="/api/resonance",    tags=["resonance"])
# The assistant's data surface. Carries its own absolute paths — /api/resonance/data/*
# plus the two documents at /api/resonance/openapi.json and /.well-known/resonance.json —
# so it is mounted without a prefix, and before the SPA catch-all so the grant file wins
# over it.
app.include_router(resonance_data_router.router)
resonance_data_router.register_error_handler(app)
resonance_data_router.validate_grants(app)

# -- Health check ------------------------------------------------------------------

@app.get("/api/health", tags=["system"])
async def health():
    return {"status": "ok", "version": "0.1.0"}

# -- Serve React frontend (production build) ---------------------------------------
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(request: Request, full_path: str):
        # /api/ and /.well-known/ are answered by real routes or not at all.
        # Falling through to index.html gave a 200 of HTML to anything asking
        # for a well-known document — resonance reading
        # /.well-known/resonance.json on an install that publishes none got a
        # page instead of an honest 404.
        if full_path.startswith("api/") or full_path.startswith(".well-known/"):
            raise HTTPException(status_code=404, detail="Not found")
        # Normalize-then-prefix-check (CodeQL's own documented pattern for
        # py/path-injection) rather than pathlib's resolve()/is_relative_to,
        # which its Python taint tracker doesn't recognize as a sanitizer.
        _dist_root = os.path.normpath(str(_frontend_dist))
        _candidate = os.path.normpath(os.path.join(_dist_root, full_path))
        if not (_candidate == _dist_root or _candidate.startswith(_dist_root + os.sep)):
            raise HTTPException(status_code=404, detail="Not found")
        static_file = Path(_candidate)
        if static_file.exists() and static_file.is_file():
            return FileResponse(str(static_file))
        index = _frontend_dist / "index.html"
        response = FileResponse(str(index))
        # pktHub suite-token bootstrap — set sso cookies so React logs in automatically
        _cfg = settings
        _suite_tk = request.headers.get("x-suite-token", "")
        if _suite_tk and _cfg.suite_token and _suite_tk == _cfg.suite_token:
            from datetime import datetime, timedelta, timezone
            from jose import jwt as _jose_jwt
            from app.dependencies import _SUITE_ROLE_MAP
            _hub_user = request.headers.get("x-suite-user", "hub_user")
            _hub_role = request.headers.get("x-suite-role", "viewer")
            _local_role = _SUITE_ROLE_MAP.get(_hub_role, "viewer")
            _expire = datetime.now(tz=timezone.utc) + timedelta(hours=8)
            _payload = {"sub": "0", "role": _local_role, "exp": _expire, "type": "access"}
            _jwt = _jose_jwt.encode(_payload, _cfg.secret_key, algorithm=_cfg.algorithm)
            response.set_cookie("sso_access_token", _jwt,       max_age=60, httponly=False, samesite="lax")
            response.set_cookie("sso_role",         _local_role, max_age=60, httponly=False, samesite="lax")
        return response


# -- Entrypoint (used by systemd: python -m app.main) -----------------------------
if __name__ == "__main__":
    import json
    import sqlite3
    import uvicorn

    _db_path = Path(__file__).parent.parent / "pktipam.db"
    _ssl_enabled  = False
    _ssl_certfile = None
    _ssl_keyfile  = None
    try:
        _conn = sqlite3.connect(str(_db_path))
        for _key in ("ssl_enabled", "ssl_certfile", "ssl_keyfile"):
            _row = _conn.execute("SELECT value FROM settings WHERE key=?", (_key,)).fetchone()
            if _row:
                _val = json.loads(_row[0])
                if _key == "ssl_enabled":
                    _ssl_enabled = bool(_val)
                elif _key == "ssl_certfile":
                    _ssl_certfile = _val if _val else None
                elif _key == "ssl_keyfile":
                    _ssl_keyfile = _val if _val else None
        _conn.close()
    except Exception as _e:
        log.warning(f"Could not read SSL settings from config DB: {_e}")

    _bind_port = settings.https_port if _ssl_enabled else settings.port

    _uvicorn_kwargs = dict(
        host=settings.host,
        port=_bind_port,
        log_level=settings.log_level.lower(),
        workers=1,
    )

    _ssl_dir = Path(settings.ssl_dir)
    if not _ssl_certfile and (_ssl_dir / "server.crt").exists():
        _ssl_certfile = str(_ssl_dir / "server.crt")
    if not _ssl_keyfile and (_ssl_dir / "server.key").exists():
        _ssl_keyfile = str(_ssl_dir / "server.key")

    if _ssl_enabled and _ssl_certfile and _ssl_keyfile:
        _uvicorn_kwargs["ssl_certfile"] = _ssl_certfile
        _uvicorn_kwargs["ssl_keyfile"]  = _ssl_keyfile
        log.info(f"Starting with HTTPS on port {_bind_port}: cert={_ssl_certfile}")
    else:
        log.info(f"Starting with HTTP on port {_bind_port} (no SSL configured)")

    uvicorn.run("app.main:app", **_uvicorn_kwargs)
