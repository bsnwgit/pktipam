"""
app/ipam/collectors/dhcp/windows_dhcp.py
-------------------------------------------
Windows Server DHCP, via WinRM (pywinrm) — runs the built-in DhcpServer
PowerShell module remotely (Get-DhcpServerv4Scope / Get-DhcpServerv4Lease)
and parses its ConvertTo-Json output. No agent/API install needed on the
Windows box beyond WinRM being enabled (it is by default on Windows Server
with the DHCP role, via `winrm quickconfig`).

Built to the documented cmdlet output shape — **unverified against a live
Windows DHCP server**; spot-check field mappings against a real response
before relying on it. See README "Vendor Collectors" table.

Config shape:
{
  "host": "10.0.0.20",
  "username": "DOMAIN\\svc-pktipam",
  "password": "...",
  "transport": "ntlm",       # ntlm | kerberos | basic | credssp
  "use_ssl": true,
  "port": 5986
}
"""
from __future__ import annotations

import json
import logging

from app.ipam.collectors.dhcp.base import DhcpCollector, DhcpPollResult, DhcpLeaseReading

log = logging.getLogger("pktipam.collectors.dhcp.windows_dhcp")

_PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$scopes = Get-DhcpServerv4Scope
$out = @()
foreach ($scope in $scopes) {
    $leases = Get-DhcpServerv4Lease -ScopeId $scope.ScopeId
    foreach ($lease in $leases) {
        $out += [PSCustomObject]@{
            IPAddress    = $lease.IPAddress.ToString()
            ClientId     = $lease.ClientId
            HostName     = $lease.HostName
            LeaseExpiryTime = $lease.LeaseExpiryTime
            AddressState = $lease.AddressState.ToString()
            ScopeId      = $scope.ScopeId.ToString()
        }
    }
}
$out | ConvertTo-Json -Depth 4
"""

# Windows AddressState values -> pktIPAM lease state.
_STATE_MAP = {
    "Active": "active",
    "ActiveReservation": "reserved",
    "Declined": "expired",
    "Expired": "expired",
    "InactiveReservation": "reserved",
}


def _run_ps_sync(config: dict) -> str:
    """Runs in a worker thread — pywinrm is synchronous."""
    import winrm

    session = winrm.Session(
        config["host"],
        auth=(config["username"], config["password"]),
        transport=config.get("transport", "ntlm"),
        server_cert_validation="ignore" if not config.get("verify_tls", True) else "validate",
    )
    result = session.run_ps(_PS_SCRIPT)
    if result.status_code != 0:
        raise RuntimeError(f"WinRM PowerShell exited {result.status_code}: {result.std_err.decode(errors='replace')}")
    return result.std_out.decode(errors="replace")


class WindowsDhcpCollector(DhcpCollector):
    async def poll(self) -> DhcpPollResult:
        import asyncio

        for required in ("host", "username", "password"):
            if not self.config.get(required):
                raise ValueError(f"Windows DHCP collector requires '{required}'")

        raw_out = await asyncio.to_thread(_run_ps_sync, self.config)
        raw_out = raw_out.strip()
        if not raw_out:
            return DhcpPollResult()

        data = json.loads(raw_out)
        if isinstance(data, dict):
            data = [data]

        result = DhcpPollResult()
        for lease in data:
            state = _STATE_MAP.get(lease.get("AddressState", ""), "active")
            result.leases.append(DhcpLeaseReading(
                ip_address=lease.get("IPAddress"),
                mac_address=lease.get("ClientId"),
                hostname=lease.get("HostName") or None,
                client_id=lease.get("ClientId"),
                ends_at=lease.get("LeaseExpiryTime"),
                state=state,
                raw=lease,
            ))
        return result
