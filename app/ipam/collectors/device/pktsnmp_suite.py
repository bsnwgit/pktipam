"""
app/ipam/collectors/device/pktsnmp_suite.py
------------------------------------------------
Suite-token client path for device-derived IP discovery: pulls data
pktsnmp already collects via its own SNMP polling, so pktIPAM doesn't need
its own SNMP credentials/reachability to a device pktsnmp already manages.

Brought to parity with the native `snmp_generic` device collector
(2026-07-26) — pktsnmp now walks and exposes each device's real ARP table
(IP<->MAC, with interface/VLAN) and IPv4 routing table over the Suite
Integration channel (GET /api/snmp/devices/{id}/arp-entries and
/routes — see pktsnmp's app/snmp/poll_engine.py::_poll_topology), so this
collector reports the same shape of data as a direct SNMP poll would, just
sourced from pktsnmp's already-established credentials instead of
pktIPAM's own.

Per-device ARP/route lookups are best-effort and independently
non-fatal — an older pktsnmp deployment without these endpoints, or a
device pktsnmp hasn't polled yet, just falls back to the plain device
inventory entry (IP+name, no MAC) for that device rather than failing the
whole poll.

Config shape:
{
  "base_url": "http://10.0.0.50:8767",
  "suite_token": "..."
}
"""
from __future__ import annotations

import asyncio
import logging

from app.ipam.collectors.device.base import DeviceCollector, DevicePollResult, ArpEntryReading, RouteReading
from app.integrations.pktsnmp_client import PktSnmpClient

log = logging.getLogger("pktipam.collectors.device.pktsnmp_suite")


async def _fetch_device_topology(client: PktSnmpClient, device: dict) -> tuple[dict, list, list]:
    device_id = device.get("id")
    arp: list = []
    routes: list = []
    if device_id is not None:
        try:
            arp = await client.get_device_arp_entries(device_id)
        except Exception as exc:
            log.debug(f"ARP entries unavailable for pktsnmp device {device_id}: {exc}")
        try:
            routes = await client.get_device_routes(device_id)
        except Exception as exc:
            log.debug(f"Routes unavailable for pktsnmp device {device_id}: {exc}")
    return device, arp, routes


class PktSnmpSuiteCollector(DeviceCollector):
    async def poll(self) -> DevicePollResult:
        base_url = self.config.get("base_url")
        suite_token = self.config.get("suite_token")
        if not base_url or not suite_token:
            raise ValueError("pktsnmp suite collector requires 'base_url' and 'suite_token'")

        client = PktSnmpClient(base_url, suite_token, suite_user="pktipam", suite_role="admin")
        devices = await client.get_devices()

        result = DevicePollResult()
        per_device = await asyncio.gather(*[_fetch_device_topology(client, d) for d in devices])

        for device, arp_rows, route_rows in per_device:
            ip = device.get("ip")
            label = device.get("name") or ip
            if not ip:
                continue

            # ARP-table entries first, then the device's own management IP
            # as an unconditional fallback (same as before this collector
            # gained ARP support) — persisted via INSERT OR IGNORE keyed on
            # ip_address, so ordering here matters in the rare case a
            # device's own IP also shows up in its own ARP table: the
            # richer ARP-sourced reading (real MAC) must land first so it's
            # the one kept, not silently discarded in favor of the mac=None
            # fallback.
            for row in arp_rows:
                if not row.get("ip_address"):
                    continue
                result.entries.append(ArpEntryReading(
                    ip_address=row["ip_address"],
                    mac_address=row.get("mac_address"),
                    device_label=label,
                    interface=row.get("interface_label"),
                    vlan_tag=row.get("vlan_tag"),
                ))

            result.entries.append(ArpEntryReading(
                ip_address=ip, mac_address=None, device_label=label,
                interface=None, vlan_tag=None,
            ))

            for row in route_rows:
                if not row.get("destination"):
                    continue
                result.routes.append(RouteReading(
                    destination=row["destination"],
                    next_hop=row.get("next_hop"),
                    interface=row.get("interface_label"),
                    protocol=row.get("protocol"),
                    metric=row.get("metric"),
                    device_label=label,
                ))

        return result
