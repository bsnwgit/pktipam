"""
app/ipam/collectors/dhcp/isc_dhcpd_legacy.py
------------------------------------------------
Classic ISC `dhcpd` (no REST API) — SSH in (paramiko) and read+parse
`dhcpd.leases`, the well-known lease-database grammar ISC dhcpd has used
for decades. Only lease state is parsed in v1 (not `dhcpd.conf` subnet/pool
declarations) — subnets are managed directly in pktIPAM; the leases file is
what carries authoritative current-binding state.

The lease file is append-only — a given IP can have many historical lease
blocks; the LAST block for an IP in file order is its current state, which
is what this parser keeps.

Config shape:
{
  "host": "10.0.0.30",
  "port": 22,
  "username": "root",
  "password": "...",          # either password or private_key_path
  "private_key_path": "...",
  "leases_file": "/var/lib/dhcp/dhcpd.leases"
}
"""
from __future__ import annotations

import logging
import re

from app.ipam.collectors.dhcp.base import DhcpCollector, DhcpPollResult, DhcpLeaseReading

log = logging.getLogger("pktipam.collectors.dhcp.isc_dhcpd_legacy")

_LEASE_BLOCK_RE = re.compile(r"lease\s+([\d.]+)\s*\{([^}]*)\}", re.DOTALL)
_FIELD_RES = {
    "starts": re.compile(r"starts\s+\d\s+([\d/]+\s[\d:]+);"),
    "ends": re.compile(r"ends\s+\d\s+([\d/]+\s[\d:]+);"),
    "binding_state": re.compile(r"binding state (\w+);"),
    "hardware": re.compile(r"hardware ethernet ([0-9a-fA-F:]+);"),
    "hostname": re.compile(r'client-hostname "([^"]*)";'),
}

# ISC dhcpd binding states -> pktIPAM lease state.
_STATE_MAP = {
    "active": "active",
    "free": "released",
    "expired": "expired",
    "released": "released",
    "abandoned": "released",
    "reset": "released",
    "backup": "active",
}


def _apply_host_key_policy(client) -> None:
    """Verify the host key instead of trusting it on first sight.

    AutoAddPolicy accepted any key a host offered and cached it, so the first
    connection — the one that establishes trust — was unauthenticated. A machine
    in between could present its own key and capture the SSH credentials used to
    log in to network infrastructure.

    Known hosts come from the system file, then ~/.ssh/known_hosts, then
    PKT_SSH_KNOWN_HOSTS if set — which is how an estate with its own key store
    points this at it. There is deliberately no "trust anything" switch: that
    would just put the original vulnerability behind a flag.
    """
    import os

    import paramiko

    client.load_system_host_keys()
    for candidate in (
        os.environ.get("PKT_SSH_KNOWN_HOSTS"),
        os.path.expanduser("~/.ssh/known_hosts"),
    ):
        if candidate and os.path.exists(candidate):
            try:
                client.load_host_keys(candidate)
            except OSError:
                pass

    # RejectPolicy unconditionally. An earlier version of this fix kept an
    # AutoAddPolicy escape hatch behind an environment variable, which is
    # exactly the blind first-contact trust the fix exists to remove — it just
    # moved it behind a flag. Point PKT_SSH_KNOWN_HOSTS at a file instead: a
    # host key can be recorded deliberately, which is auditable, where
    # "accept whatever answers this time" is not.
    client.set_missing_host_key_policy(paramiko.RejectPolicy())


def _fetch_file_sync(config: dict) -> str:
    """Runs in a worker thread — paramiko is synchronous."""
    import paramiko

    client = paramiko.SSHClient()
    _apply_host_key_policy(client)
    connect_kwargs: dict = {
        "hostname": config["host"],
        "port": int(config.get("port") or 22),
        "username": config["username"],
        "timeout": 10,
    }
    if config.get("private_key_path"):
        connect_kwargs["key_filename"] = config["private_key_path"]
    else:
        connect_kwargs["password"] = config.get("password") or ""

    try:
        client.connect(**connect_kwargs)
        leases_file = config.get("leases_file") or "/var/lib/dhcp/dhcpd.leases"
        _stdin, stdout, stderr = client.exec_command(f"cat {leases_file}")
        content = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        if not content and err:
            raise RuntimeError(f"Could not read {leases_file}: {err.strip()}")
        return content
    finally:
        client.close()


def _parse_leases(content: str) -> list[DhcpLeaseReading]:
    by_ip: dict[str, DhcpLeaseReading] = {}
    for match in _LEASE_BLOCK_RE.finditer(content):
        ip, body = match.group(1), match.group(2)
        fields = {}
        for key, rx in _FIELD_RES.items():
            m = rx.search(body)
            fields[key] = m.group(1) if m else None

        # Last block per IP in file order wins — dict insertion order preserved.
        by_ip[ip] = DhcpLeaseReading(
            ip_address=ip,
            mac_address=fields["hardware"],
            hostname=fields["hostname"] or None,
            starts_at=fields["starts"],
            ends_at=fields["ends"],
            state=_STATE_MAP.get(fields["binding_state"] or "", "active"),
            raw={"binding_state": fields["binding_state"]},
        )
    return list(by_ip.values())


class IscDhcpdLegacyCollector(DhcpCollector):
    async def poll(self) -> DhcpPollResult:
        import asyncio

        for required in ("host", "username"):
            if not self.config.get(required):
                raise ValueError(f"ISC dhcpd collector requires '{required}'")
        if not self.config.get("password") and not self.config.get("private_key_path"):
            raise ValueError("ISC dhcpd collector requires either 'password' or 'private_key_path'")

        content = await asyncio.to_thread(_fetch_file_sync, self.config)
        result = DhcpPollResult()
        result.leases = _parse_leases(content)
        return result
