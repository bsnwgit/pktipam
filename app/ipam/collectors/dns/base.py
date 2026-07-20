"""
app/ipam/collectors/dns/base.py
----------------------------------
Shared data shapes + abstract base class for every DNS collector plugin
(generic AXFR zone transfer, PowerDNS, Windows Server DNS, Infoblox).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DnsRecordReading:
    zone: str
    name: str
    record_type: str   # A | AAAA | PTR | CNAME
    value: str
    ttl: int | None = None


@dataclass
class DnsPollResult:
    records: list[DnsRecordReading] = field(default_factory=list)


class DnsCollector(ABC):
    """Base class every DNS collector plugin implements."""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def poll(self) -> DnsPollResult:
        """Fetch current records from the DNS server. Raise on failure —
        the caller (poll_engine / the poll-now API) records the error."""
        raise NotImplementedError

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.poll()
            return True, f"OK — {len(result.records)} record(s) found"
        except Exception as exc:
            return False, str(exc)
