"""
app/ipam/collectors/device/registry.py
--------------------------------------------
Single place that lists every device-derived IP discovery collector
pktIPAM knows about. Both entries can be enabled at once — a given install
may have pktsnmp present, absent, or both native SNMP and pktsnmp
aggregation wanted simultaneously.
"""
from __future__ import annotations

from app.ipam.collectors.field_schema import text, number, host_list, credential_select, pktsnmp_select
from app.ipam.collectors.device.base import DeviceCollector
from app.ipam.collectors.device.snmp_generic import SnmpGenericDeviceCollector
from app.ipam.collectors.device.pktsnmp_suite import PktSnmpSuiteCollector

DEVICE_COLLECTOR_TYPES: dict[str, dict] = {
    "snmp_generic": {
        "label": "Generic SNMP (native ARP/IP-MIB walk)",
        "implemented": True,
        "cls": SnmpGenericDeviceCollector,
        "fields": [
            credential_select("credential_id", "SNMP Credential", required=True,
                               help="Manage credentials under Settings -> SNMP Credentials"),
            number("port", "SNMP port", default=161),
            host_list("hosts", "Devices to poll", [
                text("ip", "IP address", required=True, placeholder="10.0.0.1"),
                text("label", "Label", placeholder="core-switch-1"),
            ], help="Every switch/router to walk for ARP + interface data — all use the same credential above"),
        ],
    },
    "pktsnmp_suite": {
        "label": "pktsnmp (suite-token aggregation)",
        "implemented": True,
        "cls": PktSnmpSuiteCollector,
        "fields": [
            pktsnmp_select("integration_id", "pktsnmp Instance", required=True,
                            help="Manage connections under Settings -> Security -> Suite Integration"),
        ],
    },
}


def get_device_collector_instance(collector_type: str, config: dict) -> DeviceCollector | None:
    meta = DEVICE_COLLECTOR_TYPES.get(collector_type)
    if not meta:
        return None
    return meta["cls"](config)
