"""
app/ipam/collectors/dns/registry.py
----------------------------------------
Single place that lists every DNS collector plugin pktIPAM knows about.
Add a new vendor by writing a DnsCollector subclass next to the others in
this package and adding one entry here.
"""
from __future__ import annotations

from app.ipam.collectors.field_schema import text, password, number, toggle, select, string_list
from app.ipam.collectors.dns.base import DnsCollector
from app.ipam.collectors.dns.axfr_generic import AxfrGenericCollector
from app.ipam.collectors.dns.powerdns_api import PowerDnsApiCollector
from app.ipam.collectors.dns.windows_dns import WindowsDnsCollector
from app.ipam.collectors.dns.infoblox import InfobloxDnsCollector
from app.ipam.collectors.dns.pihole import PiHoleDnsCollector

DNS_COLLECTOR_TYPES: dict[str, dict] = {
    "axfr_generic": {
        "label": "Generic DNS zone transfer (AXFR, vendor-neutral)",
        "implemented": True,
        "cls": AxfrGenericCollector,
        "fields": [
            text("server", "DNS server host/IP", required=True, placeholder="10.0.0.40"),
            number("port", "Port", default=53),
            string_list("zones", "Zones", item_placeholder="example.com",
                        help="Zone names to transfer — must allow AXFR from pktIPAM's IP"),
            text("tsig_key_name", "TSIG key name", help="Optional — only needed for authenticated transfer"),
            password("tsig_key_secret", "TSIG key secret"),
            select("tsig_algorithm", "TSIG algorithm",
                   [("hmac-sha256", "HMAC-SHA256"), ("hmac-sha1", "HMAC-SHA1"), ("hmac-md5", "HMAC-MD5")],
                   default="hmac-sha256"),
        ],
    },
    "powerdns_api": {
        "label": "PowerDNS (Authoritative Server REST API)",
        "implemented": True,
        "cls": PowerDnsApiCollector,
        "fields": [
            text("base_url", "API base URL", required=True, placeholder="http://10.0.0.41:8081"),
            password("api_key", "API key", required=True),
            text("server_id", "Server ID", placeholder="localhost", help="PowerDNS server instance id — usually 'localhost'"),
            string_list("zones", "Zones", item_placeholder="example.com",
                        help="Leave empty to pull every zone on the server"),
        ],
    },
    "windows_dns": {
        "label": "Windows Server DNS (WinRM)",
        "implemented": True,
        "cls": WindowsDnsCollector,
        "fields": [
            text("host", "Server host/IP", required=True, placeholder="10.0.0.42"),
            text("username", "Username", required=True, placeholder="DOMAIN\\svc-pktipam"),
            password("password", "Password", required=True),
            select("transport", "WinRM transport",
                   [("ntlm", "NTLM"), ("kerberos", "Kerberos"), ("basic", "Basic"), ("credssp", "CredSSP")],
                   default="ntlm"),
            toggle("verify_tls", "Verify TLS certificate", default=True),
            string_list("zones", "Zones", item_placeholder="example.com",
                        help="Leave empty to pull every primary zone on the server"),
        ],
    },
    "infoblox_dns": {
        "label": "Infoblox NIOS DNS (WAPI)",
        "implemented": True,
        "cls": InfobloxDnsCollector,
        "fields": [
            text("base_url", "Grid Manager / member URL", required=True, placeholder="https://gm.example.com"),
            text("username", "Username", required=True),
            password("password", "Password", required=True),
            text("wapi_version", "WAPI version", placeholder="2.12", help="Defaults to 2.12 if left blank"),
            toggle("verify_tls", "Verify TLS certificate", default=True),
        ],
    },
    "pihole": {
        "label": "Pi-hole (v6 REST API — Local DNS Records)",
        "implemented": True,
        "cls": PiHoleDnsCollector,
        "fields": [
            text("base_url", "Pi-hole URL", required=True, placeholder="https://10.0.0.90"),
            password("password", "Password", required=True,
                      help="Admin password, or a dedicated App Password from Settings -> API / Web interface"),
            toggle("verify_tls", "Verify TLS certificate", default=False),
        ],
    },
}


def get_dns_collector_instance(collector_type: str, config: dict) -> DnsCollector | None:
    meta = DNS_COLLECTOR_TYPES.get(collector_type)
    if not meta:
        return None
    return meta["cls"](config)
