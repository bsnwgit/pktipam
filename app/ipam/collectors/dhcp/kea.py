"""
app/ipam/collectors/dhcp/kea.py
----------------------------------
ISC Kea DHCP server, via its Control Agent REST API
(https://kea.readthedocs.io/en/latest/arm/ctrl-channel.html).

This is the reference/primary DHCP collector — Kea's Control Agent gives a
clean JSON command interface, no file parsing or remote-shell needed.

Config shape:
{
  "base_url": "http://10.0.0.10:8000",   # Kea Control Agent endpoint
  "basic_auth_user": "...",               # optional
  "basic_auth_password": "...",           # optional
  "services": ["dhcp4"],                  # dhcp4 | dhcp6 | both
  "verify_tls": true
}
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.ipam.collectors.dhcp.base import DhcpCollector, DhcpPollResult, DhcpLeaseReading

log = logging.getLogger("pktipam.collectors.dhcp.kea")

# Kea lease4 "state" values (see Kea ARM, lease commands).
_STATE_MAP = {0: "active", 1: "declined", 2: "expired"}


def _epoch_to_iso(epoch: int | None) -> str | None:
    if not epoch:
        return None
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
    except (ValueError, OSError):
        return None


class KeaCollector(DhcpCollector):
    def _client(self) -> httpx.AsyncClient:
        auth = None
        user = self.config.get("basic_auth_user")
        if user:
            auth = (user, self.config.get("basic_auth_password") or "")
        return httpx.AsyncClient(
            base_url=self.config.get("base_url", "").rstrip("/"),
            timeout=15,
            verify=self.config.get("verify_tls", True),
            auth=auth,
        )

    async def _command(self, client: httpx.AsyncClient, command: str, service: str) -> list[dict]:
        resp = await client.post("/", json={"command": command, "service": [service]})
        resp.raise_for_status()
        body = resp.json()
        # Kea returns a list, one entry per targeted service.
        out: list[dict] = []
        for entry in body:
            if entry.get("result") not in (0, 3):  # 0 = success, 3 = empty
                raise RuntimeError(f"Kea command '{command}' failed: {entry.get('text')}")
            args = entry.get("arguments") or {}
            out.extend(args.get("leases", []))
        return out

    async def poll(self) -> DhcpPollResult:
        if not self.config.get("base_url"):
            raise ValueError("Kea collector requires 'base_url' (Control Agent endpoint)")

        services = self.config.get("services") or ["dhcp4"]
        result = DhcpPollResult()

        async with self._client() as client:
            if "dhcp4" in services:
                leases = await self._command(client, "lease4-get-all", "dhcp4")
                for l in leases:
                    result.leases.append(DhcpLeaseReading(
                        ip_address=l.get("ip-address"),
                        mac_address=l.get("hw-address"),
                        hostname=l.get("hostname") or None,
                        client_id=l.get("client-id"),
                        ends_at=_epoch_to_iso((l.get("cltt") or 0) + (l.get("valid-lft") or 0)),
                        starts_at=_epoch_to_iso(l.get("cltt")),
                        state=_STATE_MAP.get(l.get("state", 0), "active"),
                        raw=l,
                    ))

            if "dhcp6" in services:
                leases = await self._command(client, "lease6-get-all", "dhcp6")
                for l in leases:
                    result.leases.append(DhcpLeaseReading(
                        ip_address=l.get("ip-address"),
                        mac_address=l.get("duid"),
                        hostname=l.get("hostname") or None,
                        client_id=l.get("duid"),
                        ends_at=_epoch_to_iso((l.get("cltt") or 0) + (l.get("valid-lft") or 0)),
                        starts_at=_epoch_to_iso(l.get("cltt")),
                        state=_STATE_MAP.get(l.get("state", 0), "active"),
                        raw=l,
                    ))

        return result
