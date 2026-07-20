"""
app/ipam/collectors/dns/powerdns_api.py
-------------------------------------------
PowerDNS Authoritative Server REST API
(https://doc.powerdns.com/authoritative/http-api/index.html). Doesn't
require AXFR to be enabled — uses the API key instead.

Config shape:
{
  "base_url": "http://10.0.0.41:8081",
  "api_key": "...",
  "server_id": "localhost",   # PowerDNS server instance id, usually "localhost"
  "zones": []                 # empty = all zones on the server
}
"""
from __future__ import annotations

import logging

import httpx

from app.ipam.collectors.dns.base import DnsCollector, DnsPollResult, DnsRecordReading

log = logging.getLogger("pktipam.collectors.dns.powerdns_api")

_RECORD_TYPES = {"A", "AAAA", "PTR", "CNAME"}


class PowerDnsApiCollector(DnsCollector):
    async def poll(self) -> DnsPollResult:
        base_url = self.config.get("base_url", "").rstrip("/")
        api_key = self.config.get("api_key")
        server_id = self.config.get("server_id") or "localhost"
        if not base_url or not api_key:
            raise ValueError("PowerDNS collector requires 'base_url' and 'api_key'")

        headers = {"X-API-Key": api_key}
        result = DnsPollResult()

        async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=15) as client:
            wanted_zones = self.config.get("zones") or None
            if not wanted_zones:
                resp = await client.get(f"/api/v1/servers/{server_id}/zones")
                resp.raise_for_status()
                wanted_zones = [z["name"].rstrip(".") for z in resp.json()]

            for zone_name in wanted_zones:
                resp = await client.get(f"/api/v1/servers/{server_id}/zones/{zone_name}.")
                resp.raise_for_status()
                zone = resp.json()
                for rrset in zone.get("rrsets", []):
                    rtype = rrset.get("type")
                    if rtype not in _RECORD_TYPES:
                        continue
                    name = rrset.get("name", "").rstrip(".")
                    ttl = rrset.get("ttl")
                    for record in rrset.get("records", []):
                        result.records.append(DnsRecordReading(
                            zone=zone_name, name=name, record_type=rtype,
                            value=record.get("content", "").rstrip("."), ttl=ttl,
                        ))
        return result
