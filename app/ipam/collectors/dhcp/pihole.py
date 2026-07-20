"""
app/ipam/collectors/dhcp/pihole.py
--------------------------------------
Pi-hole (v6 REST API) DHCP collector. Reports two kinds of data, both
confirmed against Pi-hole's own OpenAPI spec (pi-hole/FTL
src/api/docs/content/specs/dhcp.yaml and config.yaml):

- Active dynamic leases: GET /api/dhcp/leases -> {"leases": [{"expires":
  <epoch int, 0 = infinite>, "name": <hostname>, "hwaddr": <mac>, "ip":
  <ip>, "clientid": <str>}]}. Reported with state="active" (or "expired"
  if the FTL-reported expiry has already passed — FTL doesn't prune
  expired entries from this list itself).
- Static DHCP reservations: GET /api/config -> config.dhcp.hosts, an array
  of "MAC,IP[,HOSTNAME]" strings (this is Pi-hole's own static-lease
  config format, same shape shown in the OpenAPI spec's example). Reported
  with state="reserved" — Pi-hole doesn't require the reserved MAC to
  currently hold an active lease, so these are collected independently of
  the leases list above (the poll engine/reconcile layer already handles
  a MAC/IP appearing in both).

Config shape:
{
  "base_url": "https://10.0.0.90",   # no trailing slash
  "password": "...",                  # admin password or an App Password
  "verify_tls": false
}
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.ipam.collectors.dhcp.base import DhcpCollector, DhcpPollResult, DhcpLeaseReading
from app.ipam.collectors.pihole_api import PiHoleClient


def _epoch_to_iso(epoch: int | None) -> str | None:
    if not epoch:
        return None
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        return None


class PiHoleDhcpCollector(DhcpCollector):
    def __init__(self, config: dict):
        super().__init__(config)
        self.pihole = PiHoleClient(config)

    async def poll(self) -> DhcpPollResult:
        result = DhcpPollResult()
        now = datetime.now(tz=timezone.utc)

        async with self.pihole.new_client() as client:
            await self.pihole.authenticate(client)
            leases_data = await self.pihole.get(client, "dhcp/leases")
            for l in leases_data.get("leases", []):
                ip = l.get("ip")
                if not ip:
                    continue
                expires = l.get("expires") or 0
                ends_at = _epoch_to_iso(expires)
                state = "active"
                if expires and datetime.fromtimestamp(expires, tz=timezone.utc) < now:
                    state = "expired"
                result.leases.append(DhcpLeaseReading(
                    ip_address=ip,
                    mac_address=l.get("hwaddr") or None,
                    hostname=l.get("name") or None,
                    client_id=l.get("clientid") or None,
                    ends_at=ends_at,
                    state=state,
                    raw=l,
                ))

            config_data = await self.pihole.get(client, "config")
            static_hosts = ((config_data.get("config") or {}).get("dhcp") or {}).get("hosts") or []
            for entry in static_hosts:
                parts = [p.strip() for p in entry.split(",")]
                if len(parts) < 2:
                    continue
                mac, ip = parts[0], parts[1]
                hostname = parts[2] if len(parts) > 2 else None
                if not ip:
                    continue
                result.leases.append(DhcpLeaseReading(
                    ip_address=ip,
                    mac_address=mac or None,
                    hostname=hostname,
                    state="reserved",
                    raw={"entry": entry},
                ))

        return result
