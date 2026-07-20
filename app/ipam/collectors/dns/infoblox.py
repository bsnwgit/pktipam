"""
app/ipam/collectors/dns/infoblox.py
----------------------------------------
Infoblox NIOS DNS, via its WAPI REST API. Pairs with `dhcp/infoblox.py`
(same appliance, same WAPI, same shared session/paging helper). WAPI has
no single unified "records" endpoint like PowerDNS's rrsets — each record
type is its own object type, so this pages through record:a, record:aaaa,
record:cname, and record:ptr separately.

Config shape:
{
  "base_url": "https://gm.example.com",
  "username": "...", "password": "...",
  "wapi_version": "2.12",
  "verify_tls": true
}
"""
from __future__ import annotations

from app.ipam.collectors.dns.base import DnsCollector, DnsPollResult, DnsRecordReading
from app.ipam.collectors.infoblox_wapi import WapiClient

# object_type -> (record_type, WAPI field holding the record's "value")
_RECORD_OBJECT_TYPES = {
    "record:a": ("A", "ipv4addr"),
    "record:aaaa": ("AAAA", "ipv6addr"),
    "record:cname": ("CNAME", "canonical"),
    "record:ptr": ("PTR", "ptrdname"),
}


class InfobloxDnsCollector(DnsCollector):
    async def poll(self) -> DnsPollResult:
        wapi = WapiClient(self.config)
        result = DnsPollResult()

        async with wapi.client() as client:
            for object_type, (record_type, value_field) in _RECORD_OBJECT_TYPES.items():
                fields = ["name", "ttl", "zone", value_field]
                records = await wapi.get_all(client, object_type, fields)
                for rec in records:
                    value = rec.get(value_field)
                    name = rec.get("name")
                    if not value or not name:
                        continue
                    result.records.append(DnsRecordReading(
                        zone=rec.get("zone") or "", name=name, record_type=record_type,
                        value=value, ttl=rec.get("ttl"),
                    ))
        return result
