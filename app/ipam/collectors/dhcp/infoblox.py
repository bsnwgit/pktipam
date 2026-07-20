"""
app/ipam/collectors/dhcp/infoblox.py
----------------------------------------
Infoblox NIOS (DDI appliance) DHCP, via its WAPI REST API. Uses the shared
session/paging helper in app/ipam/collectors/infoblox_wapi.py.

Config shape:
{
  "base_url": "https://gm.example.com",
  "username": "...", "password": "...",
  "wapi_version": "2.12",     # optional, defaults to 2.12
  "verify_tls": true
}
"""
from __future__ import annotations

from app.ipam.collectors.dhcp.base import DhcpCollector, DhcpPollResult, DhcpLeaseReading
from app.ipam.collectors.infoblox_wapi import WapiClient

_RETURN_FIELDS = ["address", "hardware", "client_hostname", "starts", "ends", "binding_state"]

# NIOS lease binding_state values -> pktIPAM lease state.
_STATE_MAP = {
    "ACTIVE": "active",
    "STATIC": "active",
    "OFFER": "active",
    "FREE": "released",
    "EXPIRED": "expired",
    "ABANDONED": "released",
    "REJECTED": "released",
    "RESET": "released",
    "BACKUP": "active",
}


class InfobloxDhcpCollector(DhcpCollector):
    async def poll(self) -> DhcpPollResult:
        wapi = WapiClient(self.config)
        result = DhcpPollResult()

        async with wapi.client() as client:
            leases = await wapi.get_all(client, "lease", _RETURN_FIELDS)

        for lease in leases:
            address = lease.get("address")
            if not address:
                continue
            result.leases.append(DhcpLeaseReading(
                ip_address=address,
                mac_address=lease.get("hardware") or None,
                hostname=lease.get("client_hostname") or None,
                starts_at=lease.get("starts"),
                ends_at=lease.get("ends"),
                state=_STATE_MAP.get((lease.get("binding_state") or "").upper(), "active"),
                raw=lease,
            ))
        return result
