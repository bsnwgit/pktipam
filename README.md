# pktIPAM

<p align="center">
  <img src="lockup-256h.png" alt="pktIPAM" height="64">
</p>

Enterprise IP Address Management — part of the [pkt suite](#the-pkt-suite). Gathers lease,
zone, device-ARP, and routing-table data from your DHCP servers, DNS
servers, and network devices, reconciles it into a single source of truth
(subnets, IP addresses, VLANs), and detects conflicts between sources.
Surfaces it through a React UI with alerting.
Every page/section has a "?" help button (same pattern across the whole
pkt* suite) with a short in-context explainer — no separate user manual.

**Default port:** `8761` (HTTP)

**Deployment status:** built, verified end-to-end, and installed as a live
systemd service on an internal Linux host.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Frontend Build & Deploy](#frontend-build--deploy)
- [Collectors](#collectors)
- [Collector Config Forms](#collector-config-forms)
- [SNMP Credential Library](#snmp-credential-library)
- [Sites](#sites)
- [Reconciliation & Conflict Detection](#reconciliation--conflict-detection)
- [Synthetic DNS Records](#synthetic-dns-records)
- [IP Address History](#ip-address-history)
- [Subnets, VLANs & Mass IP Update](#subnets-vlans--mass-ip-update)
- [Routing Tables](#routing-tables)
- [Settings Layout](#settings-layout)
- [Configuration Reference](#configuration-reference)
- [Running & Managing the Service](#running--managing-the-service)
- [Roles & Auth](#roles--auth)
- [IP Intelligence Lookup](#ip-intelligence-lookup)
- [Alerting](#alerting)
- [Suite Integration](#suite-integration)
- [Backup & Restore](#backup--restore)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Contributing](#contributing)
- [Known Gaps / Fast-Follow Work](#known-gaps--fast-follow-work)
- [Log Forwarding](#log-forwarding)
- [The pkt suite](#the-pkt-suite)

---

## Quick Start

```bash
# 1. Get the code onto the target host
git clone git@github.com:bsnwgit/pktipam.git
cd pktipam

# 2. Run the installer — prompts for an install directory (default
#    /opt/pktipam) and a port (default 8761), then handles system
#    packages, Python venv, config.yaml + secret/credential keys, DB
#    migrations, admin user, frontend build (if npm is present), and the
#    systemd service (installed + started). Run as your normal user —
#    never `sudo ./install.sh`; the script calls sudo internally where it
#    actually needs root.
bash install.sh

# Prints the admin password at the end — save it, it is not shown again.

# 3. Open the firewall for the app port
sudo ufw allow 8761/tcp

# 4. Open http://<server-ip>:8761 and log in with the admin credentials from step 2
```

### Environment variables

`install.sh` honors the following overrides (skips the matching
interactive prompt when set):

| Variable | Default | Description |
|---|---|---|
| `PKTIPAM_INSTALL_DIR` | `/opt/pktipam` | App root — every other path defaults to somewhere under this |
| `PKTIPAM_PORT` | `8761` | HTTP port, written into `config.yaml` and the systemd unit |
| `PKTIPAM_LOG_DIR` | `$PKTIPAM_INSTALL_DIR/logs` | Log file directory |
| `PKTIPAM_SERVICE_USER` | current user | systemd service user |
| `PKTIPAM_SERVICE_GROUP` | same as service user | systemd service group |

---

## Architecture

```
   DHCP collectors        DNS collectors         Device collectors
   (Kea, Windows,         (AXFR generic,          (native SNMP ARP/routes,
    ISC dhcpd legacy,      PowerDNS, Windows,       pktsnmp suite client)
    Infoblox, Pi-hole)      Infoblox, Pi-hole)
        |                        |                         |
        v                        v                    v         v
   dhcp_leases table       dns_records table   arp_entries   routes table
        \_______________________|_________________/              |
                                 |                                |
                    app/ipam/reconcile_engine.py <----------------/
                    (own tick, ~60s — merges sources into
                     ip_addresses, detects conflicts (incl.
                     route-based ones), updates subnet
                     utilization history, logs
                     ip_address_history on change)
                                 |
                                 v
                    ip_addresses / conflicts / subnets
                    (what the UI and API actually read)
```

Each collector category persists into its own raw table
(`app/ipam/poll_engine.py`, one file, dispatches by category since a DHCP
lease, a DNS record, an ARP entry, and a route are structurally
different). A separate reconciliation engine
(`app/ipam/reconcile_engine.py`) runs on its own independent tick, merging
the raw sources plus manually-managed static entries into the
`ip_addresses` table the UI and API actually read, and writing detected
conflicts to the `conflicts` table. This decoupling — collectors just
report what they see, reconciliation separately decides what it means —
is the core structural difference from a simpler pkt* app like pktWiFi
(which persists each collector's readings independently, with no
cross-source merge step).

**Scope note:** pktIPAM only ships DHCP/DNS collectors for products whose
*primary* function is running that service (Kea, ISC dhcpd, Windows
Server, Infoblox, Pi-hole). Network gear that merely offers DHCP/DNS as a
secondary feature (FortiGate, Juniper, UniFi, Cisco IOS, Netgear) was
deliberately **not built here** — that class of device is covered on the
SNMP/ARP side instead, by the `snmp_generic` device collector or by
pktsnmp's own inventory via `pktsnmp_suite`. See
[Collectors](#collectors).

---

## Requirements

- Ubuntu Server 22.04/24.04 LTS (install.sh targets this; other Linux
  distros likely work with manual package-manager substitution)
- Python 3.10+
- Node.js + npm (only needed to build the frontend — see
  [Frontend Build & Deploy](#frontend-build--deploy))

Key Python dependencies (see `requirements.txt` for the full pinned list):
FastAPI/uvicorn, aiosqlite, `python3-saml` (SSO), `cryptography` (Fernet
credential encryption), `pysnmp-lextudio` (SNMP device collector),
`dnspython` (AXFR), `pywinrm` (Windows DHCP/DNS), `paramiko` (legacy ISC
dhcpd over SSH).

---

## Installation

See [Quick Start](#quick-start). `install.sh` runs 8 steps: system
packages, install/log directories, Python venv, copying application files
(skipped when run in-place inside the repo checkout, i.e.
`REPO_DIR == INSTALL_DIR`), `config.yaml` generation (secret key + Fernet
credential key + port + install_dir), DB migrations + admin user creation
(random password, printed once at the end), frontend build (only if `npm`
is present — otherwise it's a manual follow-up step, see
[Troubleshooting](#troubleshooting)), and systemd service install/start.
It is idempotent-ish: re-running it will not overwrite an existing
`config.yaml`.

No source file hardcodes an absolute install path — `install_dir` is
resolved at runtime (env var -> config.yaml location -> cwd) and every
other path (db, logs, ssl, backups) is derived from it. See `app/config.py`.

Database schema is applied via the numbered files in `migrations/`,
run automatically by `install.sh` (and by `app.database.init_db()` on every
app start) — no manual migration step is needed.

---

## Frontend Build & Deploy

```bash
cd frontend
npm install
npm run build         # outputs frontend/dist
```

`app/main.py` serves `frontend/dist` directly when it exists. After a
rebuild, always clear the old `dist/` before copying a new one in — Vite
doesn't clean up stale hashed chunk filenames, and a browser holding an old
`index.html` will happily keep loading old-but-still-present JS chunks with
no 404 to reveal the problem.

---

## Collectors

Configured under **Collectors** in the UI, one row per data source: a
category (dhcp/dns/device), a type, a poll interval, and a config blob
whose secret fields (passwords, API keys, SNMP v3 auth, WinRM/SSH
credentials) are Fernet-encrypted at rest using `credential_key` (see
[Configuration Reference](#configuration-reference)). The config itself is
built through a structured form, not raw JSON — see
[Collector Config Forms](#collector-config-forms). Each collector row has
a "Poll Now" button that runs an immediate poll outside its schedule; a
failure shows a dismissable error modal with the collector's `last_error`.

### DHCP

| Type | Registry key | Notes |
|---|---|---|
| ISC Kea | `kea` | Control Agent REST API (`lease4-get-all`/`lease6-get-all`). Clean JSON API — the reference/primary collector. **Known gap:** only polls leases, never Kea's host reservations — a reservation in active use looks like a plain dynamic lease (never `reserved`), and one with no active lease doesn't appear at all. Not fixed yet; depends on whether the `host_cmds` hook is loaded on a given install and there's no live Kea server on hand to verify the response shape. `app/ipam/collectors/dhcp/kea.py` |
| Windows Server DHCP | `windows_dhcp` | WinRM (`pywinrm`) running `Get-DhcpServerv4Scope`/`Get-DhcpServerv4Lease`. Built to the documented cmdlet shape — **unverified against a live server**; spot-check field mappings. `app/ipam/collectors/dhcp/windows_dhcp.py` |
| ISC dhcpd (legacy) | `isc_dhcpd_legacy` | SSH (`paramiko`) + parses `dhcpd.leases` directly — no REST API exists for classic dhcpd. `app/ipam/collectors/dhcp/isc_dhcpd_legacy.py` |
| Infoblox NIOS | `infoblox_dhcp` | WAPI REST API, full `_page_id` paging (no result truncation at scale). Fetches Fixed Addresses (host reservations) separately from leases and cross-references by IP so a reservation always reports `reserved` — whether or not it currently holds a live lease. `app/ipam/collectors/dhcp/infoblox.py` |
| Pi-hole | `pihole` | Pi-hole v6 REST API. Cross-references DHCP static-host config against live leases so a reserved IP always reports `reserved`, not a plain dynamic lease. Also the source of pktIPAM's [synthetic DNS records](#synthetic-dns-records), since Pi-hole's own DHCP+DNS integration isn't exposed as a separate "DNS record" anywhere in its API. `app/ipam/collectors/dhcp/pihole.py` |

**Out of scope, not implemented:** FortiGate, Juniper, Ubiquiti UniFi,
Cisco IOS/IOS-XE, and Netgear DHCP collectors do not exist in this
codebase (confirmed absent from `app/ipam/collectors/dhcp/`). DHCP on
network gear is a secondary feature of those products, and pktIPAM's
primary-service-only design pushes that visibility to the SNMP/ARP side
(`snmp_generic` or `pktsnmp_suite`) instead of a per-vendor DHCP collector.

### DNS

| Type | Registry key | Notes |
|---|---|---|
| Generic DNS zone transfer (AXFR) | `axfr_generic` | Vendor-neutral, standard RFC 5936 zone transfer via `dnspython`. Works against BIND9, Windows DNS, PowerDNS, or anything that permits transfer — zero vendor-specific credentials needed. Default DNS collector. `app/ipam/collectors/dns/axfr_generic.py` |
| PowerDNS | `powerdns_api` | Authoritative Server REST API — doesn't require AXFR to be enabled. `app/ipam/collectors/dns/powerdns_api.py` |
| Windows Server DNS | `windows_dns` | WinRM running `Get-DnsServerResourceRecord`. Same unverified-against-live-server caveat as Windows DHCP. `app/ipam/collectors/dns/windows_dns.py` |
| Infoblox NIOS | `infoblox_dns` | WAPI REST API across `record:a`/`record:aaaa`/`record:cname`/`record:ptr` (no unified records endpoint). `app/ipam/collectors/dns/infoblox.py` |
| Pi-hole | `pihole` | Pi-hole v6 REST API, Local DNS Records. `app/ipam/collectors/dns/pihole.py` |

### Device

| Type | Registry key | Notes |
|---|---|---|
| Generic SNMP | `snmp_generic` | Native vendor-neutral walk of IP-MIB `ipNetToMediaTable` (ARP: IP↔MAC), `ifTable` (interface names), and best-effort `Q-BRIDGE-MIB` per-port VLAN. Auth comes from the [SNMP Credential Library](#snmp-credential-library), picked by name — not typed inline per collector. `app/ipam/collectors/device/snmp_generic.py` |
| pktsnmp (suite aggregation) | `pktsnmp_suite` | Pulls device inventory a named [Suite Integration](#suite-integration) pktsnmp instance already collected. **Only has IP+name, no MAC** (pktsnmp polls its own OID catalog, not necessarily the ARP table) — readings mark an IP as "seen" but are excluded from MAC-based conflict checks. Use `snmp_generic` for a full ARP table. `app/ipam/collectors/device/pktsnmp_suite.py` |

Both device collector types can be enabled simultaneously — a given
install may have pktsnmp present, absent, or both native SNMP and pktsnmp
aggregation wanted at once.

Add a new vendor by writing a `*Collector` subclass in the relevant
category's package (see each category's `base.py` for the reading
dataclass shapes) and registering it in that category's `registry.py`.
See [`docs/collector-setup.md`](docs/collector-setup.md) for the full
per-collector field reference and setup notes.

---

## Collector Config Forms

Collector config is defined by a field schema
(`app/ipam/collectors/field_schema.py`) per registry entry, rendered by
`frontend/src/components/CollectorConfigForm.tsx` — no raw-JSON editing.
Field types: `text`, `password`, `number`, `toggle`, `select`,
`multiselect`, `string_list` (repeatable strings, e.g. DNS zones),
`host_list` (repeatable rows of sub-fields, e.g. SNMP hosts to poll),
`site_select` (dropdown from the [Sites](#sites) list), `credential_select`
(dropdown from the [SNMP Credential Library](#snmp-credential-library)),
and `pktsnmp_select` (dropdown from named
[Suite Integration](#suite-integration) pktsnmp connections, with a
deep-link to Settings when none exist yet).

Any field can declare `show_if: (other_key, value)` so it only renders
when another field in the same form currently equals that value — built
for collectors offering more than one auth mode (e.g. an API-key-vs-
username/password picker). As of this build, **no registered pktIPAM
collector actually uses `show_if`** — the mechanism exists and is
exercised by pktWiFi's/pktIPAM's own network-device-auth patterns
elsewhere in the pkt suite, but the one collector here that would have
needed it (UniFi) was removed as out-of-scope network gear. It's ready for
the next collector that needs it.

`credential_select` and `pktsnmp_select` don't store real secrets in the
collector's own config — just an id. `app/ipam/poll_engine.py`'s
`resolve_device_config()` resolves that id to real SNMP auth or
base_url/suite_token fields at poll time, so rotating a shared credential
or integration doesn't require touching every collector that references
it.

---

## SNMP Credential Library

**Settings -> SNMP Credentials** — named, reusable SNMP auth (v2c
community string, or v3 user/auth-protocol/auth-key/priv-protocol/priv-key),
created once and assigned to any number of `snmp_generic` device collectors
by id, instead of re-entering a community string or v3 auth per collector.
Secrets are Fernet-encrypted at rest (`app/ipam/collectors/crypto.py`);
list/get responses mask them (`••••••••`) and only report whether an
auth/priv key is set. Deleting a credential still in use by a collector is
blocked (409) until it's reassigned. Mirrors pktsnmp's own Settings -> SNMP
-> Credentials pattern exactly. API: `app/api/snmp_credentials.py`, schema:
`migrations/005_snmp_credentials.sql`.

---

## Sites

A managed site catalog (**Settings** or the **Sites** page, `app/api/sites.py`,
`migrations/002_sites.sql`) that Subnets and VLANs pick from via a dropdown
instead of free-typing a site name — avoids typo'd duplicates like "HQ" /
"Hq" / "headquarters" referring to the same place. `subnets.site` and
`vlans.site` remain plain TEXT columns (no FK), so existing values aren't
migrated automatically. The `site_select` field type in
[Collector Config Forms](#collector-config-forms) exists for a collector
that wants to scope itself to a site, but no current collector registry
entry uses it.

---

## Reconciliation & Conflict Detection

`app/ipam/reconcile_engine.py` runs on its own ~60s tick, independent of
collector poll cadence. Source precedence for merged fields (highest
wins): manual static entry > active DHCP lease > ARP/device sighting.

Resulting `ip_addresses.status` values: `free` (nothing currently sees this
IP), `dhcp` (an active dynamic lease), `reserved` (every lease seen for
this IP reports the DHCP server's own fixed-IP/reservation state — kept
distinct from a plain dynamic lease rather than collapsed into the same
"dhcp" status), `static` (a manual reservation), `used` (DNS-only
corroboration, no lease/ARP), and `conflict` (a `duplicate_ip` or
`static_dhcp_mismatch` was detected for this IP this tick).

Conflict types detected each tick:

| Type | Meaning |
|---|---|
| `duplicate_ip` | The same IP has active leases from >1 distinct MAC |
| `duplicate_mac` | The same MAC is bound to >1 IP concurrently (leases + ARP sightings combined) |
| `static_dhcp_mismatch` | A manual static reservation's MAC differs from an active DHCP lease's MAC for the same IP |
| `dns_mismatch` | A DNS A/AAAA record points at an IP with no corroborating lease, ARP sighting, or manual entry ("stale DNS") |
| `subnet_overlap` | Two configured subnets have overlapping CIDRs |
| `subnet_unrouted` | A subnet has no discovered route (in the [routing table](#routing-tables)) for its exact CIDR from any device collector's routing-table walk. Only checked once at least one route has been discovered anywhere, so an install with no routing-capable device collector configured doesn't flag every subnet as unrouted |
| `route_gateway_mismatch` | A subnet has a configured gateway, a route exists for that subnet's exact CIDR, and none of that route's discovered next-hops match the configured gateway |

Conflicts are upserted keyed by (type, ip_address, subnet_id) — re-detected
each tick they stay/reopen; a resolved conflict whose underlying condition
is still true reopens on the next tick, since Resolve acknowledges the
conflict rather than fixing the data. An IP that was previously tracked but
no source sees on a given tick is logged as `released` and reset back to
`free` (mac/hostname/dns_ptr cleared) rather than left showing stale data
indefinitely — manual/static entries are never touched by this reset.

The **Conflicts** page has Active/History tabs (mirroring Alerts), each
with independent search and 25/50/75/100-per-page pagination. Resolve is
available per-row or in bulk — select a subset and resolve just those, or
"Resolve all" for everything currently active. A resolved conflict also
carries an ack trail (`acked`/`acked_by`/`acked_at`) separate from
resolution itself. `app/api/conflicts.py`, `frontend/src/pages/Conflicts.tsx`.

---

## Synthetic DNS Records

Some DHCP servers (Pi-hole/dnsmasq in particular) hand a client its own
hostname as part of the DHCP lease itself, making that name effectively
resolvable even though it's never exposed as a distinct "DNS record" in
the server's own API. `app/ipam/poll_engine.py` surfaces this: every time a
DHCP collector persists its leases, it also synthesizes an `A` record
(zone `"dhcp"`) into `dns_records` for each active/reserved lease that has
a real hostname (placeholder names like `""` or `"*"` — dnsmasq/Pi-hole's
"no hostname sent" marker — are skipped). These synthetic records are
tagged to the same `collector_id` and fully replaced on every poll, so a
lease that renews with a new IP, loses its hostname, or expires entirely
is reflected immediately — nothing stale survives past the next poll.
They show up on the **DNS Records** page like any other record.

---

## IP Address History

Every IP address has a change-triggered history timeline — not a
per-tick snapshot — recorded to the `ip_address_history` table
(`migrations/007_ip_address_history.sql`) with one of three events:
`first_seen` (an IP appears for the first time), `changed` (its MAC or
hostname differs from the last recorded state), or `released` (it
disappeared from every source and was reset to free). Written by
`app/ipam/reconcile_engine.py` for reconciled (non-manual) IPs, and by
`app/api/ip_addresses.py` directly for manual create/edit/delete, so a
static reservation's own edits are captured too. Read-only API:
`GET /api/ip-address-history?ip_address=...` (or `subnet_id=...`),
`app/api/ip_address_history.py`. In the UI, open an IP's row in
**Subnet Detail** to view its history in the modal
(`frontend/src/components/IpHistoryModal.tsx`) — rows carrying history
are flagged with a `has_history` marker on the IP Addresses, DHCP Leases,
and Subnet Detail list endpoints so the UI knows which rows to make
clickable without a separate round-trip per row.

---

## Subnets, VLANs & Mass IP Update

**Subnets** hold a CIDR, optional VLAN link, site, gateway, and parent
subnet (for hierarchy). Picking a VLAN in the Subnet form auto-fills the
subnet's description from that VLAN's own description (editable
afterward, and only applied once per session per field — editing the
description manually stops future VLAN changes from overwriting it).
Frontend: `frontend/src/pages/Subnets.tsx`.

**VLANs** (`app/api/vlans.py`) are a simple catalog: tag, name, site,
description — unique per site.

**Mass IP update** (`POST /api/ip-addresses/bulk-update`,
`app/api/ip_addresses.py`) lets an admin/analyst select a set of IPs in one
subnet from the IP Addresses grid and apply status, owner, description,
and/or tags across all of them in one call. Each field has its own
`apply_*` flag so, e.g., setting owner without touching status or tags is
possible — fields left un-applied are untouched on IPs that already have a
row, and get a sensible default (status defaults to `static`, matching a
normal manual reservation) on IPs that don't have one yet. Every affected
IP is stamped `source = 'manual'`.

---

## Routing Tables

Device collectors that can walk a routing table persist into a `routes`
table (`migrations/011_routes.sql`), same full-replace-on-poll pattern as
ARP entries. Currently `snmp_generic` is the only source: it walks
`ipCidrRouteTable` (IP-FORWARD-MIB) for IPv4 and `inetCidrRouteTable`
(RFC 4292) for IPv6, alongside its existing ARP walk. The `pktsnmp_suite`
collector reports the same shape of route data when the target pktsnmp
instance is new enough to expose its own topology endpoints (see
[Suite Integration](#suite-integration)); older pktsnmp deployments just
fall back to plain device-inventory entries for that device.

The **Routes** page (`GET /api/routes`, `frontend/src/pages/Routes.tsx`)
groups rows by (destination, next_hop) — the same physical route is
commonly reported by more than one collector or device at once, and raw
per-collector rows would otherwise show up as noisy duplicates. Each
grouped row lists every contributing device/interface, plus a distinct
"subnet gateway" column sourced from the Subnets page's own admin-
configured gateway (not SNMP-observed data — a directly-connected route
has no real next-hop in any protocol, since the reporting device itself
is the router for that segment).

Discovered routes feed two reconciliation conflict types — see
[Reconciliation & Conflict Detection](#reconciliation--conflict-detection):
`subnet_unrouted` and `route_gateway_mismatch`. Both only run once at
least one route has been discovered anywhere, so an install with no
routing-capable device collector configured never flags every subnet.

This is distinct from a dedicated route-table *collector* (a standalone
collector type sourced independently of the SNMP device walk) — that idea
is noted but not started; what's documented here is the SNMP-sourced
routing-table walk that already ships.

---

## Settings Layout

The **Settings** page is organized into two **sections**, chosen from a
section bar above the tab bar:

| Section | Tabs |
|---|---|
| **pktIPAM** | SNMP Credentials · Sites · Collectors (admin-only) |

Common holds the settings that are identical across every pkt* app;
pktIPAM holds this app's own. Selecting a section swaps the tab bar
beneath it, so only one group's tabs are visible at a time — previously
they shared a single long row separated by a thin divider. Deep links
still work unchanged: `/settings?tab=collectors` (the target of the
"unknown collector" alert link, among others) selects the right section
automatically.

---

## Configuration Reference

See `config.example.yaml` for the full annotated list. Key fields:

| Key | Default | Description |
|---|---|---|
| `host` | `0.0.0.0` | Bind address |
| `port` | `8761` | HTTP port |
| `workers` | `2` | uvicorn worker count |
| `debug` | `false` | Debug mode |
| `install_dir` | — | App root — appended by install.sh, don't hand-edit unless moving the install |
| `db_path` | `<install_dir>/pktipam.db` | SQLite DB location (optional override) |
| `secret_key` | — | JWT signing key (generate with `openssl rand -hex 32`) |
| `credential_key` | — | Fernet key encrypting collector credentials at rest (generate via the Fernet command in the file's comments) |
| `cors_origins` | — | Restrict to your actual origin in production |
| `log_level` | `info` | Log verbosity |
| `log_file` | `<install_dir>/logs/pktipam.log` | Log file path (optional override) |
| `ssl_dir` | `<install_dir>/ssl` | SSL certificate directory (optional override) |

Collector configuration (DHCP/DNS/SNMP credentials), alert rules, sites,
the outbound pktsnmp integration, and per-user IP-lookup API keys are all
managed via the UI and stored in
SQLite — this file only covers infrastructure/startup settings.

---

## Running & Managing the Service

```bash
sudo systemctl status pktipam
sudo systemctl restart pktipam
journalctl -u pktipam -f
```

An admin can also trigger a restart from the UI (Settings -> System) —
`POST /api/system/restart` waits ~1.5s then exits the process so systemd's
`Restart=on-failure` brings it back up; it only works when the service is
actually managed by systemd.

---

## Roles & Auth

Three roles: `admin` (full access, including Collectors/Integrations/
Settings/Users), `analyst` (can create/edit subnets, VLANs, sites, manual
IP reservations, resolve conflicts, ack/resolve alerts), `viewer`
(read-only).

Local username/password auth is always available; SAML 2.0 SSO can be
layered on top via Settings (same IdP-agnostic implementation as the rest
of the suite — `app/auth/saml.py`). When pktHub proxies a request with a
valid `X-Suite-Token`, the `X-Suite-Role` header maps directly onto these
three roles (see `app/dependencies.py`).

---

## IP Intelligence Lookup

pktIPAM ships the same IP-intelligence backend as the rest of the pkt*
suite (`GET /api/ip-info/{ip}`), combining:

- **ipinfo.io** — geolocation/ASN/org info, plus company, privacy (VPN/proxy/Tor/relay/hosting), and abuse contact on paid plans
- **ipapi.is** — geolocation, ASN/org, company, abuse contact, VPN/proxy/Tor/datacenter/abuser detection, all in one call, no plan gating; has a keyless **free-tier** toggle (1,000 req/day, no signup) as an alternative to a personal key
- **AbuseIPDB** — abuse confidence score and report history
- **MXToolbox** — reverse DNS (PTR), ASN, and a blacklist/RBL check

All four are called concurrently. Private/loopback/link-local/reserved/multicast addresses are rejected — external providers have nothing useful to say about them. Keys are **per-user**: each logged-in user stores their own under Settings -> User Keys (`app/api/user_api_keys.py`), and lookups run under that user's own key/quota. Keys are Fernet-encrypted at rest (`app/ipam/collectors/crypto.py`, same `credential_key` used for collector secrets) — decrypted only in memory when a lookup runs or the owning user views their own key. A fifth provider slot, IPQualityScore, can be saved and tested there but isn't consumed by the lookup yet. For ipinfo.io, ipapi.is, and MXToolbox, a user can also set `enabled_fields` to select which sections of that provider's response they care about.

**No consuming UI in pktIPAM** — unlike pktsnmp/pktflow/pktlog/pktwifi (which each have an `IpLink.tsx` making public IPs clickable), pktIPAM has no lookup modal wired to any page; the backend, per-user keys, and Settings test buttons work, but nothing in the frontend calls `/api/ip-info/{ip}`. This is a deliberate scope decision, not a gap: every IP pktIPAM displays (subnets, leases, DNS records) is internal/private by nature — RFC1918 addresses these providers can't say anything useful about — so there was no page to attach it to. Also, unlike the rest of the suite, there's no separate "internal IP" counterpart here (`/api/ip-info/internal/{ip}` elsewhere calls out to pktIPAM over Suite Integration) — pktIPAM *is* the source of truth for internal addresses, via its own `/api/ip-addresses`. Revisit if pktIPAM starts managing public-facing subnets.

MXToolbox's other commands — email/DNS record checks (SPF, DMARC, DKIM, MX, DNS, TXT, SOA, BIMI, MTA-STS, TLSRPT, A, AAAA) and active probes (ping, traceroute, TCP/HTTP/HTTPS/SMTP connect, run from MXToolbox's own infrastructure against the target) — are reachable via `POST /api/mxtoolbox/lookup` (`{command, argument, port?}`, `app/api/mxtoolbox.py`) but aren't surfaced anywhere in the UI.

---

## Alerting

Five built-in condition types (`app/ipam/alerts/engine.py`):
`subnet_near_exhaustion`, `ip_conflict_detected`, `dhcp_pool_exhausted`,
`dns_ptr_mismatch`, `collector_down`. Create rules under Alerts -> Rules
via an inline form (no separate modal/page); the engine evaluates every
30 seconds and auto-resolves an alert once its target is no longer in
violation. Each rule has a **cooldown** (minutes, default 15) — after an
alert auto-resolves, the same rule won't re-fire for the same target
again until the cooldown window passes, so a flapping condition doesn't
spam a new event every eval tick. Each rule also has **notification
channels** (`inapp`, `email`, `webhook`, `slack` — toggled per rule) and
an enabled/disabled toggle switch.

The Alerts page has Active/History/Rules tabs with independent
pagination, severity + text + time-range filtering, "Ack all", and CSV
export/import for rules (a template download is available for the
expected column layout: name, condition_type, threshold, severity,
enabled, cooldown_min, channels). `app/api/alerts.py`,
`frontend/src/pages/Alerts.tsx`.

Resolved alert events and subnet-utilization-history rows aren't kept
forever: `app/ipam/alerts/cleanup.py` runs once a day and deletes rows
past their retention window (default 90 days for alert events, 30 days
for utilization history).

---

## Suite Integration

Same token flow as every other pkt app, split into inbound and outbound
directions under **Settings -> Security -> Suite Integration**:

**Inbound** (pktHub calling into pktIPAM) — a suite token is generated
automatically on this tab. Copy it into pktHub's App Manager when
registering pktIPAM.

**Outbound / "Sibling pkt Apps"** (pktIPAM calling into pktsnmp for device
inventory) — this is a **named, multi-instance list**, not a single
token: add as many pktsnmp connections as you have deployments, each with
its own name, base URL, and suite token (copied from that pktsnmp
instance's own Settings -> Security -> Suite Integration page). Each
integration has a "Test" action that runs a live health check and records
`health_status`/`last_health_check`. The `pktsnmp_suite` device collector
picks one of these by name via the `pktsnmp_select` field — see
[Collector Config Forms](#collector-config-forms) — instead of typing a
base_url/suite_token inline; if no integrations exist yet, the collector
form shows a deep-link straight to this Settings tab. Deleting an
integration still referenced by a collector is blocked (409) until it's
reassigned. API: `app/api/integrations.py`, schema:
`migrations/006_multi_integrations.sql`.

### Nav manifest (pktHub's APPS sidebar)

`GET /api/nav/manifest` (`app/api/nav.py`) publishes pktIPAM's own left-nav so
pktHub can mirror it under **APPS** in its sidebar. Entries are
`{path, label, icon, admin_only, divider_before}`. pktHub's health poller
reads the endpoint on every cycle and caches the result, so a page added here
shows up in the hub within one poll interval with no change on the hub side.

Selecting one of those rows opens pktIPAM's **real page** inside pktHub —
proxied, and chromeless so it renders without this app's own sidebar or
header. It is not a re-implementation and cannot drift from what the page
actually does.

`NAV_MANIFEST` in `app/api/nav.py` and `NAV` in
`frontend/src/components/Layout.tsx` are two declarations of one menu, and each
carries a comment pointing at the other — a page added to one belongs in both.
The endpoint is gated by `require_suite_token` for the same reason the widget
endpoints are: it discloses this app's page structure.

`admin_only` controls only what the hub *draws*. The real authorisation is
this app's own role check against the `X-Suite-Role` pktHub asserts.

### Chromeless layout needs a definite height

`Layout.tsx`'s chromeless branch uses `h-screen overflow-auto`, not
`min-h-screen`. A page that fills its container sizes itself with `h-full`,
which resolves against the parent's height — and collapses to zero against an
auto-height parent, rendering blank. Maps and canvases hit this first.

### Widget endpoints now require the suite token

`app/api/widgets.py` previously mounted its router with a bare `APIRouter()`,
so the server-rendered widget views — which read internal data — answered
anyone who could reach the port. The router now carries
`dependencies=[Depends(require_suite_token)]`, matching the NOC Builder's
actual access path. Anything calling those URLs without `X-Suite-Token` now
gets a 401.


---

## Backup & Restore

Settings -> Data -> Backups -> "Run backup now", or let the built-in
scheduler run on the configured interval (default every 24 hours). Each
snapshot is a timestamped directory under `<install_dir>/backups/`
containing `pktipam.db` + `config.yaml`; a full backup bundle can also be
downloaded as a `.tar.gz`. Downloading that bundle requires re-entering your current password: it pairs the database with `config.yaml`, i.e. every encrypted secret alongside the key that decrypts them, in one file that lands in a Downloads folder. Being logged in as an admin isn't a high enough bar to hand that over. Each listed snapshot has a **Restore…** link
that restores directly from that on-server snapshot — no download/upload
round trip required — and lets you pick just `pktipam.db` or just
`config.yaml` instead of always restoring both together; the same
per-file selection is available on the bundle-upload restore. Restoring a
backup requires a manual service restart afterward to pick up any
restored config.

---

### Backup integrity

Database snapshots are taken through SQLite's own online-backup API and then
verified with `PRAGMA integrity_check`; a snapshot that does not pass is logged
loudly and not counted as usable.

This matters more than it sounds. The database runs in WAL mode, so at any
instant the committed state is split between the `.db` file and its `-wal`
sidecar. The previous implementation copied the `.db` alone with `shutil.copy2`,
which captures neither a consistent snapshot nor the most recent commits — the
worst possible failure mode for the one artifact you reach for in an emergency,
because it looks like a backup either way.


## Troubleshooting

**Web UI shows `{"detail":"Not Found"}`** — the frontend wasn't built.
Run `cd frontend && npm install && npm run build`, then
`sudo systemctl restart pktipam`.

**Collector shows `status: error`** — check `last_error` via the
collector's error modal (click the underlined error text, or "Poll Now"
to retry immediately) on the Collectors page. For SNMP/AXFR collectors
this is almost always a reachability/credential/ACL problem
(zone-transfer ACL denying pktIPAM's IP, wrong SNMP credential selected);
for WinRM collectors, a WinRM-not-enabled or auth-transport mismatch; for
the pktsnmp integration, a stale/missing/disabled Suite Integration entry.

**A conflict keeps reappearing after Resolve** — this is expected: Resolve
acknowledges the conflict, it doesn't fix the underlying data mismatch. If
the same DHCP/DNS/ARP condition is still true on the next reconcile tick
(~60s), the conflict reopens.

---

## Development

```bash
# Backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
PKTIPAM_ADMIN_PASSWORD=devpassword uvicorn app.main:app --reload --port 8761

# Frontend (separate terminal)
cd frontend && npm install && npm run dev   # proxies /api to :8761
```

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branch strategy, PR workflow,
deployment rules, and commit message style.

---

## Known Gaps / Fast-Follow Work

This is a first build, scoped deliberately to ship something real rather
than everything at once:

- **Windows DHCP/DNS collectors are unverified against live hardware** —
  built against the documented WinRM cmdlet shapes
  (`Get-DhcpServerv4Lease`/`Get-DnsServerResourceRecord`), but no live
  Windows Server has actually been polled yet; spot-check field mappings
  against a real response before relying on them.
- **The pktsnmp suite-integration device collector falls back to no-MAC
  data on older pktsnmp deployments** — it now reports full ARP/route
  parity with `snmp_generic` when the target pktsnmp instance exposes its
  topology endpoints (`GET /api/snmp/devices/{id}/arp-entries`/`/routes`),
  but silently drops back to a plain IP+name inventory entry for any
  device pktsnmp hasn't polled yet, or against a pktsnmp version that
  predates those endpoints.
- **Kea never reports `reserved` status** — the collector only polls
  active leases, not Kea's own host reservations; see the DHCP collector
  table above. Pi-hole and Infoblox don't have this gap.
- **No dedicated route-table collector** — the [routing tables](#routing-tables)
  feature is an SNMP walk built into `snmp_generic`/`pktsnmp_suite`, not a
  standalone collector type sourced independently of SNMP; noted as a
  possible future addition, not started.
- **Network-gear DHCP/DNS is intentionally out of scope** — see
  [Collectors](#collectors) and the Architecture scope note; this isn't a
  gap so much as a deliberate boundary, but it's worth restating so a
  future contributor doesn't reintroduce a FortiGate/Juniper/UniFi/Cisco
  IOS/Netgear DHCP collector without revisiting that decision first.
- **`show_if` conditional fields and `site_select` exist but are unused**
  — both are real, working mechanisms in
  `app/ipam/collectors/field_schema.py`, but no currently-registered
  collector's schema actually uses them (the one that would have,
  UniFi's dual API-key/username-password auth mode, was removed as
  out-of-scope network gear). Ready for the next collector that needs
  conditional fields or a site-scoped config.
- **No IPv6 subnet hierarchy UI polish** — the data model and reconcile
  engine handle IPv6 (via Python's `ipaddress` module throughout), but the
  IP-grid visualization caps at /16 to stay renderable, which rules out
  any real IPv6 prefix.
- **No email/webhook/Slack notifications wired to actual alert firing** —
  channels can be selected per alert rule and the Notifications tab's
  "Send Test" is a real dispatch, but no alert condition currently
  triggers a live send automatically (same state as every other pkt* app
  in this suite — Send Test is the entire notification feature
  everywhere, not unique to pktIPAM).

## Resonance (embedded assistant)

Resonance is the suite's shared assistant. It mounts as a launcher in the bottom corner of every
authenticated page, but the assistant itself runs on the resonance server, not inside pktIPAM.
Configure it under **Settings → Resonance** (admin only); every field ships blank, so a fresh
install shows nothing until it is pointed at a resonance server of its own.

`app/integrations/resonance/` and `frontend/src/resonance/` are **vendored** — copied between
pkt\* apps byte-for-byte except for `APP_SLUG`. They are deliberately not a published package,
because `install.sh` builds a venv on customer hosts and a private index would put a credentialed
network dependency in the middle of every install. pktLog is the reference implementation.

```
browser                 pktIPAM                       resonance
embed.js  ──GET──▶  /api/resonance/code  ──POST──▶  /embed/session
          ◀─code──                        ◀─code───
frame ──────────────────────────────────────────────▶  /embed?c=<code>
```

pktIPAM vouches for whoever is signed in and receives a short-lived, single-use code. The key is
encrypted at rest, never reaches the browser, and resonance never sees a pktIPAM credential.
`GET /api/resonance/code` is the one cookie-authenticated route in the app — `embed.js` fetches it
itself, outside the SPA, and the access token lives in memory — so `Sec-Fetch-Site` and `Origin`
are both checked before the cookie is honoured.

**The data surface.** Two documents let resonance discover what it may call, both public because
they carry names rather than data:

| path | what it is |
|---|---|
| `/.well-known/resonance.json` | the grant — the operations this install permits |
| `/api/resonance/openapi.json` | those operations' OpenAPI, narrowed from the app's own |
| `/api/resonance/docs` | the shipped guides, for resonance to ingest (suite token or admin) |

Point resonance's **READ SPEC** at `/api/resonance/openapi.json`. The published operations are:

- `getIpamSummary`
- `listSubnets`
- `searchIpAddresses`
- `listVlans`
- `listConflicts`
- `listCollectors`
- `listAlertEvents`
- `listAlertRules`
- `searchApplicationLog`
- `ackAlertEvent`  *(writes)*
- `ackAllAlertEvents`  *(writes)*
- `toggleAlertRule`  *(writes)*

Every call is made by pktIPAM's own page, same-origin, on the session of the person already signed
in, so nothing here reaches data that person could not already open. Which operations exist is
fixed in `app/api/resonance_data.py`, not configurable per install. Write operations are withheld
from the grant entirely until an administrator sets a role to **Read and write**.

**Never exposed:** a collector's stored configuration, which holds its DHCP, DNS and SNMP credentials. Nothing here creates, edits or deletes a subnet, address, VLAN or collector, reserves or releases an address, or resolves a conflict.

## Log Forwarding

pktIPAM writes its own application log to the in-app **Logs** page. It can also
ship that log to a syslog collector — normally **pktLog**, which listens on
port `5514` — so this app's events sit alongside the rest of the estate.

Settings keys (Settings → Data → Log Forwarding in apps that expose the UI;
otherwise via `PUT /api/settings`):

| Key | Default | Meaning |
|---|---|---|
| `log_forward_enabled` | `false` | Turn forwarding on |
| `log_forward_host` | `""` | Collector hostname or IP |
| `log_forward_port` | `5514` | pktLog's syslog port |
| `log_forward_protocol` | `udp` | `udp` or `tcp` |
| `log_forward_level` | `INFO` | Minimum level forwarded |
| `log_forward_app_name` | `pktipam` | APP-NAME in the syslog message |

Admin endpoints:

- `GET  /api/system/log-forward/status` — delivery counters (sent, dropped, errors)
- `POST /api/system/log-forward/test` — send one test line without saving settings
- `POST /api/system/log-forward/reload` — apply settings changes without a restart

**Format is RFC 5424, deliberately.** pktLog parses both 3164 and 5424, but
3164 timestamps carry no timezone and the collector has to guess the offset —
which has produced wrong timestamps in this suite before. 5424 carries a full
offset, so there is nothing to guess.

**Delivery is fire-and-forget** on a background thread, with counters. Log
forwarding must never block or crash the thing it observes: a dropped line is a
nuisance, a stalled collector loop is an outage. If the collector is
unreachable, lines are dropped and counted rather than raised.

### If forwarded logs never arrive

**pktLog drops syslog from sources that are not registered.** Its
`collector_registry` gates what is allowed to persist, so the sending host's IP
must be present *and enabled* under pktLog's Settings → Collectors. Until then
the messages are accepted on the wire and silently discarded — the sender sees
a successful send either way, because UDP cannot tell it otherwise. pktLog also
caches that registry for five minutes, so a newly enabled source is not live
immediately.

Use the **Send test message** button (or the `test` endpoint) to confirm the
path end to end rather than assuming it works.

## The pkt suite

**pktIPAM** is one of ten apps in the pkt suite — self-hosted tooling for network
and security operations. Each installs and runs standalone, so take only the ones
you need; they share one architecture (FastAPI + React), one look, one
`admin`/`analyst`/`viewer` role model, and a suite token that lets siblings read
one another's data. Default ports don't collide (8760–8769), so any combination
runs on a single host.

| App | Port | What it does |
|---|---|---|
| **[pktFlow](https://github.com/bsnwgit/pktflow)** | `8766` | NetFlow, sFlow and IPFIX collection — flow search, traffic analytics, geo and topology views |
| **[pktSNMP](https://github.com/bsnwgit/pktsnmp)** | `8767` | SNMP polling and trap receiving for any OID — device health and metric history without a full NMS |
| **[pktLog](https://github.com/bsnwgit/pktlog)** | `8768` | Syslog over UDP, TCP and TLS — parsing, enrichment, full-text search and forwarding |
| **[pktPCAP](https://github.com/bsnwgit/pktpcap)** | `8765` | Packet capture analysis in the browser — drop in a `.pcap` for TCP, DNS and threat findings, no Wireshark install |
| **[pktWiFi](https://github.com/bsnwgit/pktwifi)** | `8769` | Access point, RF and client visibility from Meraki and UniFi controllers or plain SNMP polling |
| **pktIPAM** *(you are here)* | `8761` | IP address management reconciling declared subnets against live DHCP, DNS and device data, flagging conflicts |
| **[pktNode](https://github.com/bsnwgit/pktnode)** | `8764` | Endpoint monitoring and management for Mac, Windows and Linux via a lightweight Go agent |
| **[pktSecurity](https://pktsolution.com/pktSecurity/index.html)** | `8762` | Security operations across the estate — CVE exposure, threat intelligence, ATT&CK-mapped detections and case management |
| **[pktCert](https://github.com/bsnwgit/pktcert)** | `8763` | TLS certificate discovery and expiry tracking, plus an internal CA — issue, revoke and serve CRLs |
| **[pktHub](https://github.com/bsnwgit/pkthub)** | `8760` | The front door — one sign-in, one alert stream, NOC wallboards and user management across every registered app |

[pktHub](https://github.com/bsnwgit/pkthub) is optional — it registers the others
and puts them behind a single login with shared alerting and NOC wallboards — but
every app is fully usable without it.

More at **[pktsolution.com](https://pktsolution.com)**.
