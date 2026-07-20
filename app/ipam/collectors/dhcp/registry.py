"""
app/ipam/collectors/dhcp/registry.py
----------------------------------------
Single place that lists every DHCP collector plugin pktIPAM knows about,
whether it's actually implemented yet, and what config fields its
Collectors UI form should render. Add a new vendor by writing a
DhcpCollector subclass next to the others in this package and adding one
entry here.
"""
from __future__ import annotations

from app.ipam.collectors.field_schema import text, password, number, toggle, select, multiselect
from app.ipam.collectors.dhcp.base import DhcpCollector
from app.ipam.collectors.dhcp.kea import KeaCollector
from app.ipam.collectors.dhcp.windows_dhcp import WindowsDhcpCollector
from app.ipam.collectors.dhcp.isc_dhcpd_legacy import IscDhcpdLegacyCollector
from app.ipam.collectors.dhcp.infoblox import InfobloxDhcpCollector
from app.ipam.collectors.dhcp.pihole import PiHoleDhcpCollector

DHCP_COLLECTOR_TYPES: dict[str, dict] = {
    "kea": {
        "label": "ISC Kea (Control Agent API)",
        "implemented": True,
        "cls": KeaCollector,
        "fields": [
            text("base_url", "Control Agent URL", required=True, placeholder="http://10.0.0.10:8000",
                 help="Kea Control Agent HTTP endpoint"),
            text("basic_auth_user", "Basic auth username", help="Leave blank if the Control Agent has no auth configured"),
            password("basic_auth_password", "Basic auth password"),
            multiselect("services", "Services", [("dhcp4", "DHCPv4"), ("dhcp6", "DHCPv6")],
                        default=["dhcp4"], help="Which Kea services to pull leases from"),
            toggle("verify_tls", "Verify TLS certificate", default=True),
        ],
    },
    "windows_dhcp": {
        "label": "Windows Server DHCP (WinRM)",
        "implemented": True,
        "cls": WindowsDhcpCollector,
        "fields": [
            text("host", "Server host/IP", required=True, placeholder="10.0.0.20"),
            text("username", "Username", required=True, placeholder="DOMAIN\\svc-pktipam"),
            password("password", "Password", required=True),
            select("transport", "WinRM transport",
                   [("ntlm", "NTLM"), ("kerberos", "Kerberos"), ("basic", "Basic"), ("credssp", "CredSSP")],
                   default="ntlm"),
            toggle("verify_tls", "Verify TLS certificate", default=True),
        ],
    },
    "isc_dhcpd_legacy": {
        "label": "ISC dhcpd (legacy, SSH + lease file)",
        "implemented": True,
        "cls": IscDhcpdLegacyCollector,
        "fields": [
            text("host", "Server host/IP", required=True, placeholder="10.0.0.30"),
            number("port", "SSH port", default=22),
            text("username", "SSH username", required=True, placeholder="root"),
            password("password", "SSH password", help="Either this or a private key path is required"),
            text("private_key_path", "SSH private key path", placeholder="/home/svc/.ssh/id_ed25519",
                 help="Alternative to password auth — path on the pktIPAM host"),
            text("leases_file", "Leases file path", placeholder="/var/lib/dhcp/dhcpd.leases",
                 help="Defaults to /var/lib/dhcp/dhcpd.leases if left blank"),
        ],
    },
    "infoblox_dhcp": {
        "label": "Infoblox NIOS DHCP (WAPI)",
        "implemented": True,
        "cls": InfobloxDhcpCollector,
        "fields": [
            text("base_url", "Grid Manager / member URL", required=True, placeholder="https://gm.example.com"),
            text("username", "Username", required=True),
            password("password", "Password", required=True),
            text("wapi_version", "WAPI version", placeholder="2.12", help="Defaults to 2.12 if left blank"),
            toggle("verify_tls", "Verify TLS certificate", default=True),
        ],
    },
    "pihole": {
        "label": "Pi-hole (v6 REST API)",
        "implemented": True,
        "cls": PiHoleDhcpCollector,
        "fields": [
            text("base_url", "Pi-hole URL", required=True, placeholder="https://10.0.0.90"),
            password("password", "Password", required=True,
                      help="Admin password, or a dedicated App Password from Settings -> API / Web interface"),
            toggle("verify_tls", "Verify TLS certificate", default=False),
        ],
    },
}


def get_dhcp_collector_instance(collector_type: str, config: dict) -> DhcpCollector | None:
    meta = DHCP_COLLECTOR_TYPES.get(collector_type)
    if not meta:
        return None
    return meta["cls"](config)
