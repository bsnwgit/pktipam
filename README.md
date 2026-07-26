# pktIPAM

<p align="center">
  <img src="lockup-256h.png" alt="pktIPAM" height="64">
</p>

Enterprise IP Address Management — part of the pkt suite. Gathers lease,
zone, and device-ARP data from your DHCP servers, DNS servers, and network
devices, reconciles it into a single source of truth (subnets, IP
addresses, VLANs), and detects conflicts between sources. Surfaces it
through a React UI with alerting.

**Default port:** `8761` (HTTP)

**Deployment status:** built, verified end-to-end, and installed as a live
systemd service on the internal `aiserver` host.

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
   (Kea, Windows,         (AXFR generic,          (native SNMP ARP/IP-MIB,
    ISC dhcpd legacy,      PowerDNS, Windows,       pktsnmp suite client)
    Infoblox, Pi-hole)      Infoblox, Pi-hole)
        |                        |                         |
        v                        v                         v
   dhcp_leases table       dns_records table        arp_entries table
        \_______________________|_________________________/
                                 |
                    app/ipam/reconcile_engine.py
                    (own tick, ~60s — merges sources into
                     ip_addresses, detects conflicts, updates
                     subnet utilization history, logs
                     ip_address_history on change)
                                 |
                                 v
                    ip_addresses / conflicts / subnets
                    (what the UI and API actually read)
```

Each collector category persists into its own raw table
(`app/ipam/poll_engine.py`, one file, dispatches by category since a DHCP
lease, a DNS record, and an ARP entry are structurally different). A
separate reconciliation engine (`app/ipam/reconcile_engine.py`) runs on its
own independent tick, merging the three raw sources plus manually-managed
static entries into the `ip_addresses` table the UI and API actually read,
and writing detected conflicts to the `conflicts` table. This decoupling —
collectors just report what they see, reconciliation separately decides
what it means — is the core structural difference from a simpler pkt* app
like pktWiFi (which persists each collector's readings independently, with
no cross-source merge step).

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
| ISC Kea | `kea` | Control Agent REST API (`lease4-get-all`/`lease6-get-all`). Clean JSON API — the reference/primary collector. `app/ipam/collectors/dhcp/kea.py` |
| Windows Server DHCP | `windows_dhcp` | WinRM (`pywinrm`) running `Get-DhcpServerv4Scope`/`Get-DhcpServerv4Lease`. Built to the documented cmdlet shape — **unverified against a live server**; spot-check field mappings. `app/ipam/collectors/dhcp/windows_dhcp.py` |
| ISC dhcpd (legacy) | `isc_dhcpd_legacy` | SSH (`paramiko`) + parses `dhcpd.leases` directly — no REST API exists for classic dhcpd. `app/ipam/collectors/dhcp/isc_dhcpd_legacy.py` |
| Infoblox NIOS | `infoblox_dhcp` | WAPI REST API, full `_page_id` paging (no result truncation at scale). `app/ipam/collectors/dhcp/infoblox.py` |
| Pi-hole | `pihole` | Pi-hole v6 REST API. Also the source of pktIPAM's [synthetic DNS records](#synthetic-dns-records), since Pi-hole's own DHCP+DNS integration isn't exposed as a separate "DNS record" anywhere in its API. `app/ipam/collectors/dhcp/pihole.py` |

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

Conflicts are upserted keyed by (type, ip_address, subnet_id) — re-detected
each tick they stay/reopen; a resolved conflict whose underlying condition
is still true reopens on the next tick, since Resolve acknowledges the
conflict rather than fixing the data. An IP that was previously tracked but
no source sees on a given tick is logged as `released` and reset back to
`free` (mac/hostname/dns_ptr cleared) rather than left showing stale data
indefinitely — manual/static entries are never touched by this reset.

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
and the outbound pktsnmp integration are all managed via the UI and stored
in SQLite — this file only covers infrastructure/startup settings.

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

Any public IP address rendered in the app is a clickable link (`GET /api/ip-info/{ip}`) that opens a lookup combining:

- **ipinfo.io** — geolocation/ASN/org info, plus company, privacy (VPN/proxy/Tor/relay/hosting), and abuse contact on paid plans
- **ipapi.is** — geolocation, ASN/org, company, abuse contact, VPN/proxy/Tor/datacenter/abuser detection, all in one call, no plan gating
- **AbuseIPDB** — abuse confidence score and report history
- **MXToolbox** — reverse DNS (PTR), ASN, and a blacklist/RBL check

All four are called concurrently. Private/loopback/link-local/reserved/multicast addresses are rejected — external providers have nothing useful to say about them. Unlike the rest of the pkt* suite, there's no separate "internal IP" counterpart here (`/api/ip-info/internal/{ip}` elsewhere calls out to pktIPAM over Suite Integration) — pktIPAM *is* the source of truth for internal addresses, via its own `/api/ip-addresses`.

Keys are **per-user**, not app-wide: each logged-in user stores their own under Settings -> User Keys (`app/api/user_api_keys.py`), and lookups run under that user's own key/quota — no shared/admin key, no cross-user visibility. A fifth provider slot, IPQualityScore, can be saved and tested there but isn't consumed by the lookup yet.

MXToolbox's other commands — email/DNS record checks (SPF, DMARC, DKIM, MX, DNS, TXT, SOA, BIMI, MTA-STS, TLSRPT, A, AAAA) and active probes (ping, traceroute, TCP/HTTP/HTTPS/SMTP connect, run from MXToolbox's own infrastructure against the target) — are reachable via `POST /api/mxtoolbox/lookup` (`{command, argument, port?}`, `app/api/mxtoolbox.py`) but aren't surfaced in the UI yet.

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

---

## Backup & Restore

Settings -> Data -> Backups -> "Run backup now", or let the built-in
scheduler run on the configured interval (default every 24 hours). Each
snapshot is a timestamped directory under `<install_dir>/backups/`
containing `pktipam.db` + `config.yaml`; a full backup bundle can also be
downloaded as a `.tar.gz`. Restoring a backup requires a manual service
restart afterward to pick up any restored config.

---

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
- **The pktsnmp suite-integration device collector has no MAC data** —
  pktsnmp's device inventory doesn't include one; use the native
  `snmp_generic` device collector for a full ARP table.
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
