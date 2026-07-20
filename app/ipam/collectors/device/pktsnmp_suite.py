"""
app/ipam/collectors/device/pktsnmp_suite.py
------------------------------------------------
Suite-token client path for device-derived IP discovery: pulls the device
inventory pktsnmp already polls, so pktIPAM doesn't need its own SNMP
credentials/reachability to a device pktsnmp already manages.

Important constraint: pktsnmp's `/api/snmp/devices` inventory has each
device's management IP and name, but **not a MAC address** — pktsnmp polls
whatever OIDs are in its own catalog, not necessarily the standard ARP
table, so there is no MAC to report here. Readings from this collector
mark an IP as "seen" (source=arp, device_label set) but leave mac_address
null — the reconcile engine's MAC-based conflict checks skip those.

For a full IP<->MAC ARP table, use the native `snmp_generic` device
collector instead (or in addition — both can be enabled at once, since a
given install may have pktsnmp present, absent, or both wanted).

Config shape:
{
  "base_url": "http://10.0.0.50:8767",
  "suite_token": "..."
}
"""
from __future__ import annotations

from app.ipam.collectors.device.base import DeviceCollector, DevicePollResult, ArpEntryReading
from app.integrations.pktsnmp_client import PktSnmpClient


class PktSnmpSuiteCollector(DeviceCollector):
    async def poll(self) -> DevicePollResult:
        base_url = self.config.get("base_url")
        suite_token = self.config.get("suite_token")
        if not base_url or not suite_token:
            raise ValueError("pktsnmp suite collector requires 'base_url' and 'suite_token'")

        client = PktSnmpClient(base_url, suite_token, suite_user="pktipam", suite_role="admin")
        devices = await client.get_devices()

        result = DevicePollResult()
        for d in devices:
            ip = d.get("ip")
            if not ip:
                continue
            result.entries.append(ArpEntryReading(
                ip_address=ip,
                mac_address=None,
                device_label=d.get("name") or ip,
                interface=None,
                vlan_tag=None,
            ))
        return result
