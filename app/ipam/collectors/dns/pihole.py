"""
app/ipam/collectors/dns/pihole.py
-------------------------------------
Pi-hole (v6 REST API) DNS collector. Pi-hole isn't an authoritative DNS
server for arbitrary zones — it's a resolver/sinkhole with a flat local
namespace of hand-configured Local DNS Records. Both confirmed against
Pi-hole's own OpenAPI spec (pi-hole/FTL
src/api/docs/content/specs/config.yaml): GET /api/config ->
config.dns.hosts (array of "IP HOSTNAME" strings -> A records) and
config.dns.cnameRecords (array of "ALIAS,TARGET[,TTL]" strings -> CNAME
records). `zone` is reported as the literal string "Manual" — these are
Pi-hole's hand-typed Local DNS Records, not an actual authoritative DNS
zone, and Pi-hole's own configured local domain (config.dns.domain.name)
is a separate, unrelated setting (only affects hostname resolution for
DHCP leases — see app/ipam/collectors/dhcp/pihole.py's synthetic "dhcp"
zone records) that would be misleading to reuse here.

Config shape:
{
  "base_url": "https://10.0.0.90",   # no trailing slash
  "password": "...",                  # admin password or an App Password
  "verify_tls": false
}
"""
from __future__ import annotations

from app.ipam.collectors.dns.base import DnsCollector, DnsPollResult, DnsRecordReading
from app.ipam.collectors.pihole_api import PiHoleClient


class PiHoleDnsCollector(DnsCollector):
    def __init__(self, config: dict):
        super().__init__(config)
        self.pihole = PiHoleClient(config)

    async def poll(self) -> DnsPollResult:
        result = DnsPollResult()

        async with self.pihole.new_client() as client:
            await self.pihole.authenticate(client)
            config_data = await self.pihole.get(client, "config")
            dns_cfg = (config_data.get("config") or {}).get("dns") or {}

        zone = "Manual"

        for entry in dns_cfg.get("hosts") or []:
            parts = entry.split()
            if len(parts) < 2:
                continue
            ip, hostname = parts[0], parts[1]
            record_type = "AAAA" if ":" in ip else "A"
            result.records.append(DnsRecordReading(zone=zone, name=hostname, record_type=record_type, value=ip))

        for entry in dns_cfg.get("cnameRecords") or []:
            parts = [p.strip() for p in entry.split(",")]
            if len(parts) < 2:
                continue
            alias, target = parts[0], parts[1]
            ttl = None
            if len(parts) > 2:
                try:
                    ttl = int(parts[2])
                except ValueError:
                    ttl = None
            result.records.append(DnsRecordReading(zone=zone, name=alias, record_type="CNAME", value=target, ttl=ttl))

        return result
