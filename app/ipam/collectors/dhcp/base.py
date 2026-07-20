"""
app/ipam/collectors/dhcp/base.py
----------------------------------
Shared data shapes + abstract base class for every DHCP collector plugin
(ISC Kea, Windows Server DHCP, legacy ISC dhcpd, Infoblox).

A collector's only job is: given its config dict, return a DhcpPollResult
describing the leases it currently sees. app/ipam/poll_engine.py owns
turning that into database rows — a new collector never needs to know
about SQL.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DhcpLeaseReading:
    ip_address: str
    mac_address: str | None = None
    hostname: str | None = None
    client_id: str | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    state: str = "active"   # active | expired | released | reserved
    raw: dict = field(default_factory=dict)


@dataclass
class DhcpPollResult:
    leases: list[DhcpLeaseReading] = field(default_factory=list)


class DhcpCollector(ABC):
    """Base class every DHCP collector plugin implements."""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def poll(self) -> DhcpPollResult:
        """Fetch current lease state from the DHCP server. Raise on failure —
        the caller (poll_engine / the poll-now API) records the error."""
        raise NotImplementedError

    async def test_connection(self) -> tuple[bool, str]:
        """Default implementation: a poll that succeeds counts as reachable."""
        try:
            result = await self.poll()
            return True, f"OK — {len(result.leases)} lease(s) found"
        except Exception as exc:
            return False, str(exc)
