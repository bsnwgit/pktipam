"""
app/ipam/collectors/dns/axfr_generic.py
-------------------------------------------
Vendor-neutral DNS collector: standard zone transfer (AXFR, RFC 5936) via
`dnspython`. This is the DNS equivalent of pktWiFi's `snmp_generic.py` —
works against BIND9, Windows Server DNS, PowerDNS, or anything else that
permits a transfer from pktIPAM's IP, with zero vendor-specific
credentials needed. Primary/default DNS collector.

Requires the target server's zone transfer ACL to allow pktIPAM's IP (e.g.
BIND's `allow-transfer`) — if AXFR is disabled, use a vendor-specific
collector instead (powerdns_api, windows_dns) or enable transfer to a
single trusted secondary IP.

Config shape:
{
  "server": "10.0.0.40",
  "port": 53,
  "zones": ["example.com", "1.0.10.in-addr.arpa"],
  "tsig_key_name": "...",      # optional, for authenticated transfer
  "tsig_key_secret": "...",
  "tsig_algorithm": "hmac-sha256"
}
"""
from __future__ import annotations

import logging

from app.ipam.collectors.dns.base import DnsCollector, DnsPollResult, DnsRecordReading

log = logging.getLogger("pktipam.collectors.dns.axfr_generic")

_RECORD_TYPES = {"A", "AAAA", "PTR", "CNAME"}


def _transfer_zone_sync(server: str, port: int, zone_name: str, config: dict) -> list[DnsRecordReading]:
    """Runs in a worker thread — dnspython's zone transfer is synchronous."""
    import dns.query
    import dns.zone
    import dns.tsigkeyring

    keyring = None
    keyname = config.get("tsig_key_name")
    if keyname:
        keyring = dns.tsigkeyring.from_text({keyname: config.get("tsig_key_secret", "")})

    xfr = dns.query.xfr(
        server, zone_name, port=port, timeout=15,
        keyring=keyring, keyalgorithm=config.get("tsig_algorithm", "hmac-sha256") if keyring else None,
    )
    zone = dns.zone.from_xfr(xfr)

    readings: list[DnsRecordReading] = []
    for name, node in zone.nodes.items():
        record_name = str(name.derelativize(zone.origin)).rstrip(".")
        for rdataset in node.rdatasets:
            rtype = dns.rdatatype.to_text(rdataset.rdtype)
            if rtype not in _RECORD_TYPES:
                continue
            for rdata in rdataset:
                readings.append(DnsRecordReading(
                    zone=zone_name, name=record_name, record_type=rtype,
                    value=str(rdata).rstrip("."), ttl=rdataset.ttl,
                ))
    return readings


class AxfrGenericCollector(DnsCollector):
    async def poll(self) -> DnsPollResult:
        import asyncio

        if not self.config.get("server"):
            raise ValueError("AXFR collector requires 'server'")
        zones = self.config.get("zones") or []
        if not zones:
            raise ValueError("AXFR collector requires at least one zone in 'zones'")

        port = int(self.config.get("port") or 53)
        result = DnsPollResult()
        errors: list[str] = []

        for zone_name in zones:
            try:
                readings = await asyncio.to_thread(_transfer_zone_sync, self.config["server"], port, zone_name, self.config)
                result.records.extend(readings)
            except Exception as exc:
                errors.append(f"{zone_name}: {exc}")
                log.warning(f"AXFR failed for zone '{zone_name}': {exc}")

        if errors and not result.records:
            raise RuntimeError("; ".join(errors))
        return result
