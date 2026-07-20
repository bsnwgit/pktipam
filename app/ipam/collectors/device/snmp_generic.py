"""
app/ipam/collectors/device/snmp_generic.py
-----------------------------------------------
Vendor-neutral SNMP device collector: walks the standard IP-MIB ARP table
(ipNetToMediaTable) across a configured host list to directly discover
active IP<->MAC bindings from switches/routers — this is what populates
pktIPAM's device-derived IP discovery when pktsnmp isn't present (or in
addition to it, per the "any combination" scoping decision — see
device/pktsnmp_suite.py for the other path).

Also best-effort walks ifTable (interface names) and dot1qPvid (per-port
VLAN, Q-BRIDGE-MIB) to annotate each binding — vendor MIB support for VLAN
mapping varies, so that part is non-fatal on failure, same philosophy as
pktwifi's snmp_generic dot11-channel walk.

Config shape:
{
  "version": "v2c" | "v3",
  "community": "...",
  "username": "...", "auth_protocol": "SHA" | "MD5", "auth_password": "...",
  "priv_protocol": "AES" | "DES", "priv_password": "...",
  "port": 161,
  "hosts": [{"ip": "10.0.0.1", "label": "core-switch-1"}, ...]
}
"""
from __future__ import annotations

import logging

from app.ipam.collectors.device.base import DeviceCollector, DevicePollResult, ArpEntryReading

log = logging.getLogger("pktipam.collectors.device.snmp_generic")

_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
_IP_NET_TO_MEDIA_PHYS_ADDR = "1.3.6.1.2.1.4.22.1.2"
_DOT1D_BASE_PORT_IF_INDEX = "1.3.6.1.2.1.17.1.4.1.2"
_DOT1Q_PVID = "1.3.6.1.2.1.17.7.1.4.5.1.1"


def _mac_from_bytes(value) -> str:
    raw = bytes(value)
    return ":".join(f"{b:02x}" for b in raw) if raw else ""


def _walk(engine, auth_data, transport, base_oid: str) -> list[tuple[str, object]]:
    from pysnmp.hlapi import ContextData, ObjectType, ObjectIdentity, nextCmd

    out = []
    for err_indication, err_status, _err_index, var_binds in nextCmd(
        engine, auth_data, transport, ContextData(),
        ObjectType(ObjectIdentity(base_oid)),
        lexicographicMode=False,
    ):
        if err_indication or err_status:
            break
        for oid, value in var_binds:
            out.append((str(oid), value))
    return out


def _poll_host_sync(host: dict, creds: dict) -> list[ArpEntryReading]:
    """Runs in a worker thread — pysnmp's classic hlapi is synchronous."""
    from pysnmp.hlapi import (
        SnmpEngine, CommunityData, UsmUserData, UdpTransportTarget,
        usmHMACSHAAuthProtocol, usmHMACMD5AuthProtocol,
        usmAesCfb128Protocol, usmDESPrivProtocol,
    )

    ip = host["ip"]
    label = host.get("label") or ip
    port = int(creds.get("port") or 161)

    if creds.get("version") == "v3":
        auth_proto = usmHMACSHAAuthProtocol if creds.get("auth_protocol", "SHA") == "SHA" else usmHMACMD5AuthProtocol
        priv_proto = usmAesCfb128Protocol if creds.get("priv_protocol", "AES") == "AES" else usmDESPrivProtocol
        auth_data = UsmUserData(
            creds.get("username", ""),
            authKey=creds.get("auth_password") or None,
            privKey=creds.get("priv_password") or None,
            authProtocol=auth_proto,
            privProtocol=priv_proto,
        )
    else:
        auth_data = CommunityData(creds.get("community", "public"), mpModel=1)

    transport = UdpTransportTarget((ip, port), timeout=3, retries=1)

    # -- ifIndex -> ifDescr (interface names) -----------------------------------
    if_names: dict[str, str] = {}
    engine = SnmpEngine()
    try:
        for oid, value in _walk(engine, auth_data, transport, _IF_DESCR):
            if_index = oid.rsplit(".", 1)[-1]
            if_names[if_index] = str(value)
    except Exception as exc:
        log.debug(f"{ip}: ifTable walk failed: {exc}")
    finally:
        engine.transportDispatcher.closeDispatcher()

    # -- dot1dBasePort -> ifIndex, then ifIndex -> PVID (best-effort VLAN) ------
    # Each engine's dispatcher must close even if its walk raises — VLAN MIB
    # support failing outright is the *common* case on non-enterprise gear,
    # not an edge case, so relying on the happy path to reach
    # closeDispatcher() leaks a socket on nearly every poll of such a
    # device (same failure class as [[pktsnmp-fd-leak-and-oid-cap]]).
    port_to_vlan: dict[str, int] = {}
    base_port_to_ifindex: dict[str, str] = {}
    engine_b = SnmpEngine()
    try:
        for oid, value in _walk(engine_b, auth_data, transport, _DOT1D_BASE_PORT_IF_INDEX):
            base_port = oid.rsplit(".", 1)[-1]
            base_port_to_ifindex[base_port] = str(value)
    except Exception as exc:
        log.debug(f"{ip}: dot1dBasePortIfIndex walk unavailable: {exc}")
    finally:
        engine_b.transportDispatcher.closeDispatcher()

    engine_c = SnmpEngine()
    try:
        for oid, value in _walk(engine_c, auth_data, transport, _DOT1Q_PVID):
            base_port = oid.rsplit(".", 1)[-1]
            if_index = base_port_to_ifindex.get(base_port)
            if if_index:
                port_to_vlan[if_index] = int(value)
    except Exception as exc:
        log.debug(f"{ip}: dot1qPvid walk unavailable: {exc}")
    finally:
        engine_c.transportDispatcher.closeDispatcher()

    # -- ipNetToMediaTable (ARP: IP <-> MAC per ifIndex) -------------------------
    entries: list[ArpEntryReading] = []
    engine2 = SnmpEngine()
    try:
        for oid, value in _walk(engine2, auth_data, transport, _IP_NET_TO_MEDIA_PHYS_ADDR):
            # OID suffix: <ifIndex>.<ip1>.<ip2>.<ip3>.<ip4>
            parts = oid.split(".")
            if len(parts) < 5:
                continue
            if_index = parts[-5]
            entry_ip = ".".join(parts[-4:])
            mac = _mac_from_bytes(value)
            if not mac or mac == "00:00:00:00:00:00":
                continue
            entries.append(ArpEntryReading(
                ip_address=entry_ip, mac_address=mac, device_label=label,
                interface=if_names.get(if_index), vlan_tag=port_to_vlan.get(if_index),
            ))
    except Exception as exc:
        log.warning(f"{ip}: ipNetToMediaTable walk failed: {exc}")
    finally:
        engine2.transportDispatcher.closeDispatcher()

    return entries


class SnmpGenericDeviceCollector(DeviceCollector):
    async def poll(self) -> DevicePollResult:
        import asyncio

        hosts = self.config.get("hosts") or []
        if not hosts:
            raise ValueError("No hosts configured for this SNMP collector")

        per_host = await asyncio.gather(
            *[asyncio.to_thread(_poll_host_sync, host, self.config) for host in hosts],
            return_exceptions=True,
        )

        result = DevicePollResult()
        for readings in per_host:
            if isinstance(readings, Exception):
                log.warning(f"SNMP device poll failed for a host: {readings}")
                continue
            result.entries.extend(readings)
        return result
