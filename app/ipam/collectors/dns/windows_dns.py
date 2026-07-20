"""
app/ipam/collectors/dns/windows_dns.py
------------------------------------------
Windows Server DNS, via WinRM (pywinrm) — runs the built-in DnsServer
PowerShell module remotely (Get-DnsServerZone / Get-DnsServerResourceRecord)
and parses its ConvertTo-Json output. Same mechanism and unverified-against-
live-server caveat as `dhcp/windows_dhcp.py`.

Config shape:
{
  "host": "10.0.0.42",
  "username": "DOMAIN\\svc-pktipam",
  "password": "...",
  "transport": "ntlm",
  "verify_tls": true,
  "zones": []               # empty = all primary zones on the server
}
"""
from __future__ import annotations

import json
import logging

from app.ipam.collectors.dns.base import DnsCollector, DnsPollResult, DnsRecordReading

log = logging.getLogger("pktipam.collectors.dns.windows_dns")

_PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$zoneNames = @(%(ZONE_FILTER)s)
if ($zoneNames.Count -eq 0) {
    $zones = Get-DnsServerZone | Where-Object { -not $_.IsAutoCreated -and -not $_.IsReverseLookupZone -or $_.IsReverseLookupZone }
} else {
    $zones = Get-DnsServerZone | Where-Object { $zoneNames -contains $_.ZoneName }
}
$out = @()
foreach ($zone in $zones) {
    $records = Get-DnsServerResourceRecord -ZoneName $zone.ZoneName -RRType A, AAAA, CNAME, PTR -ErrorAction SilentlyContinue
    foreach ($r in $records) {
        $value = switch ($r.RecordType) {
            "A"     { $r.RecordData.IPv4Address.ToString() }
            "AAAA"  { $r.RecordData.IPv6Address.ToString() }
            "CNAME" { $r.RecordData.HostNameAlias }
            "PTR"   { $r.RecordData.PtrDomainName }
            default { "" }
        }
        $out += [PSCustomObject]@{
            Zone       = $zone.ZoneName
            Name       = $r.HostName
            RecordType = $r.RecordType
            Value      = $value
            TTL        = $r.TimeToLive.TotalSeconds
        }
    }
}
$out | ConvertTo-Json -Depth 4
"""


def _run_ps_sync(config: dict) -> str:
    import winrm

    zones = config.get("zones") or []
    zone_filter = ", ".join(f'"{z}"' for z in zones)
    script = _PS_SCRIPT % {"ZONE_FILTER": zone_filter}

    session = winrm.Session(
        config["host"],
        auth=(config["username"], config["password"]),
        transport=config.get("transport", "ntlm"),
        server_cert_validation="ignore" if not config.get("verify_tls", True) else "validate",
    )
    result = session.run_ps(script)
    if result.status_code != 0:
        raise RuntimeError(f"WinRM PowerShell exited {result.status_code}: {result.std_err.decode(errors='replace')}")
    return result.std_out.decode(errors="replace")


class WindowsDnsCollector(DnsCollector):
    async def poll(self) -> DnsPollResult:
        import asyncio

        for required in ("host", "username", "password"):
            if not self.config.get(required):
                raise ValueError(f"Windows DNS collector requires '{required}'")

        raw_out = await asyncio.to_thread(_run_ps_sync, self.config)
        raw_out = raw_out.strip()
        if not raw_out:
            return DnsPollResult()

        data = json.loads(raw_out)
        if isinstance(data, dict):
            data = [data]

        result = DnsPollResult()
        for r in data:
            if not r.get("Value"):
                continue
            result.records.append(DnsRecordReading(
                zone=r.get("Zone", ""), name=r.get("Name", ""),
                record_type=r.get("RecordType", ""), value=str(r.get("Value")),
                ttl=int(r["TTL"]) if r.get("TTL") is not None else None,
            ))
        return result
