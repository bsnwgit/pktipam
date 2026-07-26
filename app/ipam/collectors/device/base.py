"""
app/ipam/collectors/device/base.py
--------------------------------------
Shared data shapes + abstract base class for every device-derived IP
discovery collector (native SNMP ARP/IP-MIB walk, pktsnmp suite-token
aggregation). A device poll optionally also returns routing-table entries
(populated by snmp_generic directly, and by pktsnmp_suite via pktsnmp's
own SNMP-collected ARP/route data over the Suite Integration channel) — a
separate list on the same result rather than a second collector category,
since a routing walk reuses the exact same host list/credentials as the
ARP walk.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ArpEntryReading:
    ip_address: str
    # Optional — null for a plain device-inventory reading (a pktsnmp-known
    # device with no ARP data available for it, e.g. an older pktsnmp
    # version or a device pktsnmp hasn't polled yet); populated for a real
    # ARP-table sighting from either snmp_generic's direct walk or
    # pktsnmp_suite's pktsnmp-sourced one. Readings with no MAC still mark
    # the IP as "seen" but are excluded from MAC-based conflict detection
    # in the reconcile engine.
    mac_address: str | None = None
    device_label: str | None = None
    interface: str | None = None
    vlan_tag: int | None = None


@dataclass
class RouteReading:
    destination: str            # CIDR, e.g. "10.0.1.0/24" (or "0.0.0.0/0" for default)
    next_hop: str | None = None
    interface: str | None = None
    protocol: str | None = None  # local | static | rip | ospf | bgp | eigrp | isis | other
    metric: int | None = None
    device_label: str | None = None


@dataclass
class DevicePollResult:
    entries: list[ArpEntryReading] = field(default_factory=list)
    routes: list[RouteReading] = field(default_factory=list)


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
            msg = f"OK — {len(result.entries)} binding(s) found"
            if result.routes:
                msg += f", {len(result.routes)} route(s) found"
            return True, msg
        except Exception as exc:
            return False, str(exc)
