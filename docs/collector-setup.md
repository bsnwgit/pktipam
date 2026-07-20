# pktIPAM Collector Setup

Each collector is created under **Collectors** in the UI: a category
(dhcp/dns/device), a type, a poll interval, and a config form generated
from that type's field schema (`app/ipam/collectors/field_schema.py`) —
not raw JSON. Secret fields (passwords, API keys, SNMP v3 auth, WinRM/SSH
credentials) are Fernet-encrypted at rest using `credential_key` (see
[Configuration Reference](../README.md#configuration-reference)). A
collector's "Poll Now" button runs an immediate poll outside its schedule;
a failure shows a dismissable error modal with the collector's
`last_error`.

**Scope note:** pktIPAM only ships DHCP/DNS collectors for products whose
*primary* function is running that service. Network gear that offers
DHCP/DNS as a secondary feature (FortiGate, Juniper, UniFi, Cisco IOS,
Netgear) is intentionally out of scope here — see that class of device
through [Device collectors](#device) instead (`snmp_generic` or
`pktsnmp_suite`).

---

## DHCP

### ISC Kea (`kea`)

Control Agent REST API — the reference/primary DHCP collector, clean JSON
throughout.

| Field | Notes |
|---|---|
| `base_url` | Kea Control Agent HTTP endpoint, e.g. `http://10.0.0.10:8000` |
| `basic_auth_user` / `basic_auth_password` | Leave blank if the Control Agent has no auth configured |
| `services` | DHCPv4 and/or DHCPv6 — which Kea services to pull leases from |
| `verify_tls` | On by default |

Requires the Kea Control Agent to be running and reachable from the
pktIPAM host (`lease4-get-all`/`lease6-get-all` commands).

### Windows Server DHCP (`windows_dhcp`)

WinRM (`pywinrm`), running `Get-DhcpServerv4Scope`/`Get-DhcpServerv4Lease`.

| Field | Notes |
|---|---|
| `host` | Server IP/hostname |
| `username` / `password` | A domain service account is recommended over a personal login |
| `transport` | NTLM (default), Kerberos, Basic, or CredSSP |
| `verify_tls` | On by default |

> Built against the documented cmdlet shape but **unverified against a
> live server** as of this writing — spot-check field mappings the first
> time you point this at a real Windows DHCP server.

WinRM must be enabled on the target (`winrm quickconfig`) and the account
needs rights to query the DHCP server role.

### ISC dhcpd (legacy) (`isc_dhcpd_legacy`)

No REST API exists for classic `dhcpd` — this collector SSHes in
(`paramiko`) and parses the lease file directly.

| Field | Notes |
|---|---|
| `host` | Server IP/hostname |
| `port` | SSH port, default `22` |
| `username` | SSH username |
| `password` / `private_key_path` | Either one is required — private key path is a path on the pktIPAM host, not the target |
| `leases_file` | Defaults to `/var/lib/dhcp/dhcpd.leases` if left blank |

### Infoblox NIOS DHCP (`infoblox_dhcp`)

WAPI REST API with full `_page_id` paging, so large grids aren't
truncated.

| Field | Notes |
|---|---|
| `base_url` | Grid Manager or member URL |
| `username` / `password` | WAPI-capable account |
| `wapi_version` | Defaults to `2.12` if left blank |
| `verify_tls` | On by default |

### Pi-hole (`pihole`)

Pi-hole v6 REST API. This is also the source of pktIPAM's
[synthetic DNS records](../README.md#synthetic-dns-records), since
Pi-hole's own DHCP+DNS integration isn't exposed as a separate DNS record
anywhere in its API.

| Field | Notes |
|---|---|
| `base_url` | e.g. `https://10.0.0.90` |
| `password` | Admin password, or a dedicated App Password from Pi-hole's Settings -> API / Web interface |
| `verify_tls` | Off by default (Pi-hole's default cert is usually self-signed) |

> If Pi-hole clients aren't resolving as expected, check
> `dns.expandHosts` and `domainNeeded` on the Pi-hole side — a disabled
> `expandHosts` setting blocks DHCP clients from ever resolving as FQDNs,
> independent of anything pktIPAM does.

---

## DNS

### Generic AXFR (`axfr_generic`)

Vendor-neutral, standard RFC 5936 zone transfer (`dnspython`). Works
against BIND9, Windows DNS, PowerDNS, or anything that permits transfer —
no vendor-specific credentials needed. This is the default DNS collector.

| Field | Notes |
|---|---|
| `server` / `port` | DNS server IP and port (default `53`) |
| `zones` | Zone names to transfer — the server's ACL must permit AXFR from pktIPAM's IP |
| `tsig_key_name` / `tsig_key_secret` / `tsig_algorithm` | Optional — only needed for authenticated transfer (HMAC-SHA256 default) |

### PowerDNS (`powerdns_api`)

Authoritative Server REST API — doesn't require AXFR to be enabled.

| Field | Notes |
|---|---|
| `base_url` | e.g. `http://10.0.0.41:8081` |
| `api_key` | From PowerDNS's `api-key` config setting |
| `server_id` | Usually `localhost` |
| `zones` | Leave empty to pull every zone on the server |

### Windows Server DNS (`windows_dns`)

WinRM, running `Get-DnsServerResourceRecord`.

| Field | Notes |
|---|---|
| `host` / `username` / `password` | Same auth model as Windows DHCP |
| `transport` | NTLM (default), Kerberos, Basic, or CredSSP |
| `verify_tls` | On by default |
| `zones` | Leave empty to pull every primary zone on the server |

> Same unverified-against-live-server caveat as Windows DHCP.

### Infoblox NIOS DNS (`infoblox_dns`)

WAPI REST API across `record:a`/`record:aaaa`/`record:cname`/`record:ptr`
(no unified records endpoint).

| Field | Notes |
|---|---|
| `base_url` / `username` / `password` / `wapi_version` / `verify_tls` | Same as Infoblox DHCP — one credential set typically covers both |

### Pi-hole (`pihole`)

Pi-hole v6 REST API, Local DNS Records.

| Field | Notes |
|---|---|
| `base_url` / `password` / `verify_tls` | Same fields as the Pi-hole DHCP collector |

---

## Device

### Generic SNMP (`snmp_generic`)

Native vendor-neutral walk of IP-MIB `ipNetToMediaTable` (ARP: IP↔MAC),
`ifTable` (interface names), and a best-effort `Q-BRIDGE-MIB` per-port
VLAN read.

| Field | Notes |
|---|---|
| `credential_id` | Picked from the [SNMP Credential Library](../README.md#snmp-credential-library) — Settings -> SNMP Credentials — not typed inline here |
| `port` | SNMP port, default `161` |
| `hosts` | Repeatable list of `{ ip, label }` — every switch/router to walk, all using the same credential above |

Create the credential first if one doesn't already exist for this device
set.

### pktsnmp (suite aggregation) (`pktsnmp_suite`)

Pulls device inventory a named [Suite Integration](../README.md#suite-integration)
pktsnmp instance already collected, instead of polling devices directly.

| Field | Notes |
|---|---|
| `integration_id` | Picked from Settings -> Security -> Suite Integration's named pktsnmp connections list |

> **Only has IP + name, no MAC** — pktsnmp polls its own OID catalog, not
> necessarily the ARP table, so readings from this collector mark an IP
> as "seen" but are excluded from MAC-based conflict checks. Use
> `snmp_generic` instead when you need a full ARP table.

Both device collector types can be enabled simultaneously.

---

## Not implemented / out of scope

FortiGate, Juniper, Ubiquiti UniFi, Cisco IOS/IOS-XE, and Netgear DHCP/DNS
collectors do not exist in this codebase, and this is deliberate — DHCP/DNS
on network gear is a secondary feature of those products. Visibility into
those devices comes from the SNMP/ARP side instead (`snmp_generic` or
`pktsnmp_suite` above), not a per-vendor DHCP/DNS collector. See the
Architecture scope note in the main [README](../README.md#architecture)
before adding one back.
