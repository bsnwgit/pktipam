"""
app/ipam/collectors/device/base.py
--------------------------------------
Shared data shapes + abstract base class for every device-derived IP
discovery collector (native SNMP ARP/IP-MIB walk, pktsnmp suite-token
aggregation).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ArpEntryReading:
    ip_address: str
    # Optional: the pktsnmp suite-integration path (pktsnmp_suite.py) only
    # has device inventory (IP + name), not an ARP table, so it can't
    # always supply a MAC — those readings still mark the IP as "seen" but
    # are excluded from MAC-based conflict detection in the reconcile engine.
    mac_address: str | None = None
    device_label: str | None = None
    interface: str | None = None
    vlan_tag: int | None = None


@dataclass
class DevicePollResult:
    entries: list[ArpEntryReading] = field(default_factory=list)


class DeviceCollector(ABC):
    """Base class every device collector plugin implements."""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def poll(self) -> DevicePollResult:
        """Fetch current ARP/IP<->MAC bindings from devices. Raise on
        failure — the caller (poll_engine / the poll-now API) records the
        error."""
        raise NotImplementedError

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.poll()
            return True, f"OK — {len(result.entries)} binding(s) found"
        except Exception as exc:
            return False, str(exc)
