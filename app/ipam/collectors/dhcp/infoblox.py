"""
app/ipam/collectors/dhcp/infoblox.py
----------------------------------------
Infoblox NIOS (DDI appliance) DHCP, via its WAPI REST API. Uses the shared
session/paging helper in app/ipam/collectors/infoblox_wapi.py.

Reports two kinds of data, same shape as the Pi-hole collector for the
same reason — a NIOS "Fixed Address" (host reservation) only produces a
`lease` object once some client has actually completed a DHCP transaction
for it, so a `fixedaddress` reservation whose device is currently offline
would otherwise never appear at all. And a fixed address that *is*
currently leased reports binding_state "STATIC" on that lease — which
must map to state="reserved", not "active", or an in-use reservation is
indistinguishable from a plain dynamic lease. Both readings are cross-
referenced by IP before being added to result.leases (see pihole.py's
docstring for why a naive append-both-lists approach silently drops one
of them under the poll engine's INSERT OR IGNORE persistence).

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

_LEASE_RETURN_FIELDS = ["address", "hardware", "client_hostname", "starts", "ends", "binding_state"]
_FIXEDADDRESS_RETURN_FIELDS = ["ipv4addr", "mac", "name"]

# NIOS lease binding_state values -> pktIPAM lease state.
_STATE_MAP = {
    "ACTIVE": "active",
    "STATIC": "reserved",
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
            leases = await wapi.get_all(client, "lease", _LEASE_RETURN_FIELDS)
            fixed_addresses = await wapi.get_all(client, "fixedaddress", _FIXEDADDRESS_RETURN_FIELDS)

        fixed_by_ip = {
            fa["ipv4addr"]: (fa.get("mac") or None, fa.get("name") or None)
            for fa in fixed_addresses if fa.get("ipv4addr")
        }

        seen_ips: set[str] = set()
        for lease in leases:
            address = lease.get("address")
            if not address:
                continue
            seen_ips.add(address)
            fixed = fixed_by_ip.get(address)
            state = _STATE_MAP.get((lease.get("binding_state") or "").upper(), "active")
            if fixed and state not in ("expired", "released"):
                state = "reserved"
            result.leases.append(DhcpLeaseReading(
                ip_address=address,
                mac_address=(fixed[0] if fixed else None) or lease.get("hardware") or None,
                hostname=(fixed[1] if fixed else None) or lease.get("client_hostname") or None,
                starts_at=lease.get("starts"),
                ends_at=lease.get("ends"),
                state=state,
                raw=lease,
            ))

        # Fixed addresses with no current lease transaction (offline, or
        # never DHCP'd this reservation) have no `lease` object at all —
        # add those here so they still surface as "reserved".
        for ip, (mac, hostname) in fixed_by_ip.items():
            if ip in seen_ips:
                continue
            result.leases.append(DhcpLeaseReading(
                ip_address=ip,
                mac_address=mac,
                hostname=hostname,
                state="reserved",
                raw={"fixedaddress": True},
            ))

        return result
