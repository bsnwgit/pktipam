"""
app/ipam/collectors/pihole_api.py
------------------------------------
Shared Pi-hole v6 REST API session helper, used by both the DHCP
(dhcp/pihole.py) and DNS (dns/pihole.py) collectors — same auth mechanism,
just different endpoints.

Auth (confirmed against Pi-hole's own OpenAPI spec — pi-hole/FTL
src/api/docs/content/specs/auth.yaml — and the actual working pihole6api
Python client, not guessed): POST {base}/api/auth with {"password": ...}
(the account password, or a dedicated "App Password" from Settings ->
API/Web interface) returns {"session": {"valid": true, "sid": "...",
"csrf": "...", "validity": N}}. Every subsequent request sends the sid
back as an `X-FTL-SID` header and the csrf token as `X-FTL-CSRF` — both
required, not just for state-changing requests. A session lasts
`validity` seconds (default 300); re-authenticate on a 401.
"""
from __future__ import annotations

import httpx


class PiHoleClient:
    def __init__(self, config: dict):
        self.base_url = (config.get("base_url") or "").rstrip("/") + "/api"
        self.password = config.get("password", "")
        self.verify_tls = bool(config.get("verify_tls", False))

        if not (config.get("base_url") or "").strip():
            raise ValueError("Pi-hole collector requires 'base_url'")
        if not self.password:
            raise ValueError("Pi-hole collector requires 'password'")

    async def authenticate(self, client: httpx.AsyncClient) -> None:
        """Call once right after entering the client's `async with` block —
        must not be called before the client is opened, or (must be called
        after) httpx raises on a later `async with` re-entry attempt."""
        resp = await client.post(f"{self.base_url}/auth", json={"password": self.password})
        resp.raise_for_status()
        session = resp.json().get("session") or {}
        if not session.get("valid"):
            raise ValueError(session.get("message") or "Pi-hole authentication failed")
        client.headers["X-FTL-SID"] = session["sid"]
        client.headers["X-FTL-CSRF"] = session["csrf"]

    async def get(self, client: httpx.AsyncClient, path: str) -> dict:
        resp = await client.get(f"{self.base_url}/{path}")
        if resp.status_code == 401:
            await self.authenticate(client)
            resp = await client.get(f"{self.base_url}/{path}")
        resp.raise_for_status()
        return resp.json()

    def new_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(verify=self.verify_tls, timeout=20, follow_redirects=True)
