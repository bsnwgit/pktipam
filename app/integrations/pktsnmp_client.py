"""
Pull device inventory and interface/metric data pktsnmp has already
collected via its own SNMP polling — so pktIPAM doesn't need to re-poll the
same wired switch/controller infrastructure it monitors alongside WAPs.
"""
from __future__ import annotations

from app.integrations.suite_client import SuiteClient


class PktSnmpClient(SuiteClient):
    async def get_devices(self) -> list:
        return await self.get("/api/snmp/devices")

    async def get_device_metrics_latest(self, device_id: int) -> dict:
        return await self.get(f"/api/snmp/devices/{device_id}/metrics/latest")

    async def get_device_interfaces(self, device_id: int) -> list:
        return await self.get(f"/api/snmp/devices/{device_id}/interfaces")
