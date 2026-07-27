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

Also walks ipCidrRouteTable (IP-FORWARD-MIB) for each host's IPv4 routing
table, and inetCidrRouteTable (IP-FORWARD-MIB, RFC 4292) for IPv6 (and any
dual-stack IPv4 rows a device chooses to report there instead) — reuses
the same host list/credentials as the ARP walk above rather than requiring
a second collector, since it's the same boxes either way. Both walks are
non-fatal on failure (older devices, or gear that only implements one of
the two route tables, are common — not an error).

Uses pysnmp's `pysnmp.hlapi.asyncio` API (the installed dependency is
`pysnmp-lextudio>=6.1.0`, whose `pysnmp.hlapi` top level is empty — the
classic synchronous hlapi from pysnmp 4.x, which this file originally
targeted, no longer exists in that package). Mirrors the working async
pattern already proven in pktsnmp's app/snmp/poll_engine.py: one
SnmpEngine per host, GETBULK-walked via an awaited coroutine, closed once
in a finally block (never closing it leaks a socket per host per poll —
same failure class as [[pktsnmp-fd-leak-and-oid-cap]]).

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

import asyncio
import ipaddress
import logging

from app.ipam.collectors.device.base import DeviceCollector, DevicePollResult, ArpEntryReading, RouteReading

log = logging.getLogger("pktipam.collectors.device.snmp_generic")

_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
_IP_NET_TO_MEDIA_PHYS_ADDR = "1.3.6.1.2.1.4.22.1.2"
_DOT1D_BASE_PORT_IF_INDEX = "1.3.6.1.2.1.17.1.4.1.2"
_DOT1Q_PVID = "1.3.6.1.2.1.17.7.1.4.5.1.1"

# IP-FORWARD-MIB ipCidrRouteTable — INDEX is
# {ipCidrRouteDest, ipCidrRouteMask, ipCidrRouteTos, ipCidrRouteNextHop}
# (4 + 4 + 1 + 4 = 13 sub-identifiers after the column OID), so every
# column walk shares the same 13-part suffix and rows are correlated by it.
_ROUTE_IF_INDEX = "1.3.6.1.2.1.4.24.4.1.5"
_ROUTE_PROTO = "1.3.6.1.2.1.4.24.4.1.7"
_ROUTE_METRIC1 = "1.3.6.1.2.1.4.24.4.1.11"

# ipCidrRouteProto enumeration (IP-FORWARD-MIB, shares values with the
# older ipRouteProtocol) — codes not listed here fall back to "other".
_ROUTE_PROTO_NAMES = {
    2: "local", 3: "static", 4: "icmp", 5: "egp", 6: "ggp", 7: "hello",
    8: "rip", 9: "is-is", 10: "es-is", 11: "igrp", 12: "bbn-spf-igp",
    13: "ospf", 14: "bgp", 15: "idpr", 16: "eigrp",
}

# inetCidrRouteTable (IP-FORWARD-MIB, RFC 4292) — the address-family-agnostic
# successor to ipCidrRouteTable, used here for IPv6 (and any IPv4 rows a
# device reports only through this table). inetCidrRouteProto reuses the
# same IANAipRouteProtocol enumeration as ipCidrRouteProto above.
# INDEX is {inetCidrRouteDestType, inetCidrRouteDest, inetCidrRoutePfxLen,
# inetCidrRoutePolicy, inetCidrRouteNextHopType, inetCidrRouteNextHop} —
# unlike ipCidrRouteTable this index is variable-length (InetAddress values
# are length-prefixed to support both 4-byte IPv4 and 16-byte IPv6), so
# each row's suffix has to be parsed positionally instead of split into
# fixed-width chunks.
_INET_ROUTE_IF_INDEX = "1.3.6.1.2.1.4.24.7.1.7"
_INET_ROUTE_PROTO = "1.3.6.1.2.1.4.24.7.1.9"
_INET_ROUTE_METRIC1 = "1.3.6.1.2.1.4.24.7.1.12"

# InetAddressType (INET-ADDRESS-MIB) — only the two byte-string-shaped
# address families are handled; dns/ipv4z/ipv6z/etc. rows are skipped.
_INET_ADDR_LEN = {1: 4, 2: 16}  # ipv4 -> 4 bytes, ipv6 -> 16 bytes


def _inet_addr_from_parts(addr_type: int, byte_parts: list[str]) -> str | None:
    expected_len = _INET_ADDR_LEN.get(addr_type)
    if expected_len is None or len(byte_parts) != expected_len:
        return None
    try:
        raw = bytes(int(b) for b in byte_parts)
    except ValueError:
        return None
    return str(ipaddress.IPv4Address(raw)) if addr_type == 1 else str(ipaddress.IPv6Address(raw))


def _parse_inet_cidr_route_suffix(parts: list[str]) -> dict | None:
    """Positionally decode one inetCidrRouteTable row's OID suffix into
    {destination, next_hop}. Returns None for address families this
    collector doesn't handle, or a suffix that doesn't parse cleanly
    (some devices emit malformed/truncated rows for exotic route types)."""
    try:
        idx = 0
        dest_type = int(parts[idx]); idx += 1
        dest_len = int(parts[idx]); idx += 1
        dest_bytes = parts[idx:idx + dest_len]; idx += dest_len
        pfxlen = int(parts[idx]); idx += 1
        policy_len = int(parts[idx]); idx += 1
        idx += policy_len  # inetCidrRoutePolicy OID — not needed, skip over it
        next_hop_type = int(parts[idx]); idx += 1
        nh_len = int(parts[idx]); idx += 1
        nh_bytes = parts[idx:idx + nh_len]; idx += nh_len
    except (IndexError, ValueError):
        return None
    if idx != len(parts):
        return None

    dest_addr = _inet_addr_from_parts(dest_type, dest_bytes)
    if dest_addr is None:
        return None
    next_hop_addr = _inet_addr_from_parts(next_hop_type, nh_bytes) if nh_len else None
    return {"destination": f"{dest_addr}/{pfxlen}", "next_hop": next_hop_addr}


def _mac_from_bytes(value) -> str:
    raw = bytes(value)
    return ":".join(f"{b:02x}" for b in raw) if raw else ""


def _mask_to_prefixlen(mask: str) -> int:
    return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen


async def _walk_column(engine, auth_data, target, ctx, root_oid: str,
                        max_rows: int = 4096, batch: int = 25) -> dict[str, object]:
    """GETBULK-walk every instance under root_oid, keyed by the OID suffix
    (the row index, i.e. everything after root_oid) — same approach as
    pktsnmp's app/snmp/poll_engine.py::_walk_column."""
    from pysnmp.hlapi.asyncio import bulkCmd, ObjectType, ObjectIdentity

    out: dict[str, object] = {}
    next_oid = root_oid
    while len(out) < max_rows:
        error_indication, error_status, _error_index, var_bind_table = await bulkCmd(
            engine, auth_data, target, ctx, 0, batch,
            ObjectType(ObjectIdentity(next_oid)),
        )
        if error_indication or error_status or not var_bind_table:
            break
        done = False
        for row in var_bind_table:
            oid_str, value = row[0]
            oid_str = str(oid_str)
            if oid_str == root_oid or not oid_str.startswith(root_oid + "."):
                done = True
                break
            out[oid_str[len(root_oid) + 1:]] = value
            next_oid = oid_str
            if len(out) >= max_rows:
                break
        if done:
            break
    return out


async def _poll_host(host: dict, creds: dict) -> tuple[list[ArpEntryReading], list[RouteReading]]:
    from pysnmp.hlapi.asyncio import (
        SnmpEngine, CommunityData, UsmUserData, UdpTransportTarget, ContextData,
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

    target = UdpTransportTarget((ip, port), timeout=3, retries=1)
    ctx = ContextData()
    engine = SnmpEngine()

    entries: list[ArpEntryReading] = []
    routes: list[RouteReading] = []

    try:
        # -- Fail-fast connectivity/auth check ---------------------------------------
        # A plain sysDescr GET before any of the best-effort table walks below —
        # this is the cheapest possible request, so a bad community/username/
        # auth-priv password or an unreachable host is caught immediately and
        # raised as a real error (visible on the collector as status=error +
        # last_error) instead of silently falling through every walk below
        # (each individually non-fatal by design) and reporting a false "ok"
        # with zero entries/routes found.
        from pysnmp.hlapi.asyncio import getCmd, ObjectType, ObjectIdentity
        error_indication, error_status, _error_index, _var_binds = await getCmd(
            engine, auth_data, target, ctx, ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0")),
        )
        if error_indication:
            raise RuntimeError(f"SNMP connection to {label} ({ip}) failed: {error_indication}")
        if error_status:
            raise RuntimeError(f"SNMP connection to {label} ({ip}) failed: {error_status.prettyPrint()}")

        # -- ifIndex -> ifDescr (interface names) -----------------------------------
        if_names: dict[str, str] = {}
        try:
            raw = await _walk_column(engine, auth_data, target, ctx, _IF_DESCR)
            if_names = {suffix: str(value) for suffix, value in raw.items()}
        except Exception as exc:
            log.debug(f"{ip}: ifTable walk failed: {exc}")

        # -- dot1dBasePort -> ifIndex, then ifIndex -> PVID (best-effort VLAN) ------
        # VLAN MIB support failing outright is the *common* case on
        # non-enterprise gear, not an edge case — non-fatal, same
        # philosophy as pktwifi's snmp_generic dot11-channel walk.
        port_to_vlan: dict[str, int] = {}
        try:
            base_port_to_ifindex = {
                suffix: str(value)
                for suffix, value in (await _walk_column(engine, auth_data, target, ctx, _DOT1D_BASE_PORT_IF_INDEX)).items()
            }
            pvid_raw = await _walk_column(engine, auth_data, target, ctx, _DOT1Q_PVID)
            for base_port, pvid in pvid_raw.items():
                if_index = base_port_to_ifindex.get(base_port)
                if if_index:
                    port_to_vlan[if_index] = int(pvid)
        except Exception as exc:
            log.debug(f"{ip}: VLAN mapping (dot1dBasePortIfIndex/dot1qPvid) unavailable: {exc}")

        # -- ipNetToMediaTable (ARP: IP <-> MAC per ifIndex) -------------------------
        # INDEX is {ipNetToMediaIfIndex, ipNetToMediaNetAddress} — suffix is
        # <ifIndex>.<ip1>.<ip2>.<ip3>.<ip4>.
        try:
            raw = await _walk_column(engine, auth_data, target, ctx, _IP_NET_TO_MEDIA_PHYS_ADDR)
            for suffix, value in raw.items():
                parts = suffix.split(".")
                if len(parts) < 5:
                    continue
                if_index = parts[0]
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

        # -- ipCidrRouteTable (routing table) ----------------------------------------
        # Walk ifIndex as the primary column, then proto/metric as
        # secondary columns correlated by the same 13-part index suffix.
        route_if_index: dict[str, str] = {}
        try:
            route_if_index = {
                suffix: str(value)
                for suffix, value in (await _walk_column(engine, auth_data, target, ctx, _ROUTE_IF_INDEX)).items()
            }
        except Exception as exc:
            log.debug(f"{ip}: ipCidrRouteTable walk unavailable: {exc}")

        if route_if_index:
            route_proto: dict[str, int] = {}
            try:
                route_proto = {
                    suffix: int(value)
                    for suffix, value in (await _walk_column(engine, auth_data, target, ctx, _ROUTE_PROTO)).items()
                }
            except Exception as exc:
                log.debug(f"{ip}: ipCidrRouteProto walk unavailable: {exc}")

            route_metric: dict[str, int] = {}
            try:
                route_metric = {
                    suffix: int(value)
                    for suffix, value in (await _walk_column(engine, auth_data, target, ctx, _ROUTE_METRIC1)).items()
                }
            except Exception as exc:
                log.debug(f"{ip}: ipCidrRouteMetric1 walk unavailable: {exc}")

            for suffix, if_index in route_if_index.items():
                parts = suffix.split(".")
                if len(parts) != 13:
                    continue
                dest = ".".join(parts[0:4])
                mask = ".".join(parts[4:8])
                next_hop = ".".join(parts[9:13])
                try:
                    prefixlen = _mask_to_prefixlen(mask)
                except ValueError:
                    continue
                proto_code = route_proto.get(suffix)
                routes.append(RouteReading(
                    destination=f"{dest}/{prefixlen}",
                    next_hop=next_hop if next_hop != "0.0.0.0" else None,
                    interface=if_names.get(if_index),
                    protocol=_ROUTE_PROTO_NAMES.get(proto_code, "other") if proto_code else None,
                    metric=route_metric.get(suffix),
                    device_label=label,
                ))

        # -- inetCidrRouteTable (IPv6 routing table) ---------------------------------
        # Same shape as the ipCidrRouteTable block above, keyed by the raw
        # suffix instead of a fixed split since InetAddress index fields are
        # variable-length (see _parse_inet_cidr_route_suffix). IPv4 rows
        # decoded from this table are dropped below — some devices report
        # IPv4 through both tables, and ipCidrRouteTable above already has
        # them.
        inet_if_index: dict[str, str] = {}
        try:
            inet_if_index = {
                suffix: str(value)
                for suffix, value in (await _walk_column(engine, auth_data, target, ctx, _INET_ROUTE_IF_INDEX)).items()
            }
        except Exception as exc:
            log.debug(f"{ip}: inetCidrRouteTable walk unavailable: {exc}")

        if inet_if_index:
            inet_proto: dict[str, int] = {}
            try:
                inet_proto = {
                    suffix: int(value)
                    for suffix, value in (await _walk_column(engine, auth_data, target, ctx, _INET_ROUTE_PROTO)).items()
                }
            except Exception as exc:
                log.debug(f"{ip}: inetCidrRouteProto walk unavailable: {exc}")

            inet_metric: dict[str, int] = {}
            try:
                inet_metric = {
                    suffix: int(value)
                    for suffix, value in (await _walk_column(engine, auth_data, target, ctx, _INET_ROUTE_METRIC1)).items()
                }
            except Exception as exc:
                log.debug(f"{ip}: inetCidrRouteMetric1 walk unavailable: {exc}")

            for suffix, if_index in inet_if_index.items():
                decoded = _parse_inet_cidr_route_suffix(suffix.split("."))
                if decoded is None or ":" not in decoded["destination"]:
                    # None: undecodable/unsupported address family. No ":":
                    # an IPv4 row reported through this table too — already
                    # covered by ipCidrRouteTable above, skip to avoid a
                    # duplicate entry.
                    continue
                proto_code = inet_proto.get(suffix)
                routes.append(RouteReading(
                    destination=decoded["destination"],
                    next_hop=decoded["next_hop"],
                    interface=if_names.get(if_index),
                    protocol=_ROUTE_PROTO_NAMES.get(proto_code, "other") if proto_code else None,
                    metric=inet_metric.get(suffix),
                    device_label=label,
                ))
    finally:
        # SnmpEngine holds an open UDP socket via its transport dispatcher —
        # never closing it leaks one fd per host per poll cycle, eventually
        # exhausting the process's open-file limit.
        try:
            engine.closeDispatcher()
        except Exception as exc:
            log.debug(f"{ip}: closeDispatcher failed: {exc}")

    return entries, routes


class SnmpGenericDeviceCollector(DeviceCollector):
    async def poll(self) -> DevicePollResult:
        hosts = self.config.get("hosts") or []
        if not hosts:
            raise ValueError("No hosts configured for this SNMP collector")

        per_host = await asyncio.gather(
            *[_poll_host(host, self.config) for host in hosts],
            return_exceptions=True,
        )

        result = DevicePollResult()
        errors: list[str] = []
        for host_result in per_host:
            if isinstance(host_result, Exception):
                log.warning(f"SNMP device poll failed for a host: {host_result}")
                errors.append(str(host_result))
                continue
            entries, routes = host_result
            result.entries.extend(entries)
            result.routes.extend(routes)

        # A connection/auth failure on any configured host is a real problem
        # worth surfacing on the collector (status=error, last_error shown in
        # the UI) rather than silently reporting "ok" with whatever partial
        # data the other hosts returned — a bad credential is easy to miss
        # otherwise, since the collector would otherwise just look "healthy"
        # with a lower-than-expected row count.
        if errors:
            raise RuntimeError("; ".join(errors))
        return result
