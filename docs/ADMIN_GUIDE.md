# pktIPAM — Administrator Guide

Covers installing, configuring, and operating pktIPAM. For day-to-day usage (Subnets, IP Addresses, Conflicts, Alerts), see [USER_GUIDE.md](USER_GUIDE.md). See the [README](../README.md) for the full technical reference and [docs/collector-setup.md](collector-setup.md) for per-collector field details.

## Installation

```bash
git clone git@github.com:bsnwgit/pktipam.git
cd pktipam
bash install.sh
```

Prompts for install directory and port, handles the venv, `config.yaml` + secret key, DB migrations, admin user, frontend build, and systemd service. Open the app port in your firewall and log in with the printed admin credentials.

## First-time setup checklist

1. **Change the admin password.**
2. **Add sites** (Settings → Sites) if you plan to organize subnets/VLANs by location.
3. **Add SNMP credentials** (Settings → SNMP Credential Library) if you'll poll network devices for ARP/routing data.
4. **Configure collectors** (Settings → Collectors) for DHCP, DNS, and/or device (SNMP/pktsnmp) data sources — see Collectors below. Use **Poll Now** to test each one immediately after saving.
5. **Create subnets and VLANs** to match your real network, or let discovery/reconciliation populate them as collectors report data.
6. **Set up alert rules** (Alerts → Rules) and notification channels.
7. **Set up backups** (Data → Backups) and confirm a manual run succeeds.
8. **Create accounts** for your team.

## Finding your way around Settings

Settings has a section bar above its tab bar with two buttons:

- **Common** — General, Security (Users, Auth, Suite Integration, AI Assistant, SSL/TLS), Data (Storage, Backups), Notifications, User Keys, System. Identical across every pkt* app.
- **pktIPAM** — SNMP Credentials, Sites, Collectors (admin-only). This app's own.

The tab bar shows only the selected section's tabs, so switch sections if a tab isn't where you expect it. These used to be one long row split by a thin divider. Deep links to a tab — including the "unknown collector" alert link into Settings → Collectors — still work and select the section for you.

## Users & roles

`admin` (full access, including collectors/integrations/settings/users), `analyst` (create/edit subnets/VLANs/sites/manual reservations, resolve conflicts, ack/resolve alerts), `viewer` (read-only). Local auth is always available; layer SAML SSO on top via Settings if needed. When pktHub proxies a request with a valid suite token, its `X-Suite-Role` header maps directly onto these same three roles.

## Collectors

One row per data source under Settings → Collectors: category (dhcp/dns/device), type, poll interval, and a **schema-driven config form** (not raw JSON) with secret fields (passwords, API keys, SNMP v3 auth, WinRM/SSH creds) Fernet-encrypted at rest. **Poll Now** runs an immediate poll outside the schedule; a failure shows the collector's `last_error` in a dismissable modal.

**DHCP sources**: ISC Kea (reference/primary — REST API; known gap: only polls leases, not Kea host reservations), Windows Server DHCP (WinRM — unverified against a live server), ISC dhcpd legacy (SSH, parses `dhcpd.leases` directly), Infoblox NIOS (WAPI, full paging), Pi-hole (v6 REST API — also the source of synthetic DNS records, see below).

**DNS sources**: generic AXFR zone transfer (vendor-neutral, default), PowerDNS API, Windows Server DNS (WinRM, unverified live), Infoblox NIOS (WAPI), Pi-hole (v6 REST API, Local DNS Records).

**Device sources**: generic SNMP (native ARP/interface/VLAN walk, auth from the SNMP Credential Library), and `pktsnmp_suite` (pulls device inventory a connected pktSNMP instance already collected — IP+name only, no MAC, so it's excluded from MAC-based conflict checks; use generic SNMP for a full ARP table). Both can run simultaneously.

**By design, not a gap**: FortiGate, Juniper, UniFi, Cisco IOS/IOS-XE, and Netgear DHCP collectors don't exist here — DHCP on network gear is secondary to its main job, so that visibility comes through the SNMP/ARP side instead of a per-vendor DHCP collector for those products.

## Reconciliation & conflict detection

Runs on its own ~60-second tick, independent of collector poll cadence. Source precedence for merged fields: manual static entry > active DHCP lease > ARP/device sighting. Conflict types: `duplicate_ip`, `duplicate_mac`, `static_dhcp_mismatch`, `dns_mismatch` (stale DNS), `subnet_overlap`, `subnet_unrouted`, `route_gateway_mismatch`. Conflicts are re-detected every tick — resolving one acknowledges it, it doesn't fix the underlying data, so a still-present cause reopens it. An IP no source sees anymore is marked `released` and reset to `free` (manual/static entries are never touched by this reset).

## Synthetic DNS records

Some DHCP servers (Pi-hole/dnsmasq) hand a client its own hostname as part of the lease without exposing it as a separate DNS record anywhere in their API. pktIPAM synthesizes an `A` record (zone `"dhcp"`) for every active/reserved lease with a real hostname, fully replaced on every poll — a renewed, renamed, or expired lease is reflected immediately. These show up on the DNS Records page tagged as synthetic.

## IP address history

Change-triggered (not per-tick-snapshot) history per IP: `first_seen`, `changed` (MAC/hostname differs from last state), `released`. Written by the reconcile engine for collector-sourced IPs, and directly by the IP Addresses API for manual create/edit/delete — so static reservations get history too. View it by opening an IP's row in Subnet Detail.

## Routing tables

Device collectors that can walk a routing table (currently `snmp_generic`, via `ipCidrRouteTable`/`inetCidrRouteTable`) persist into a routes table, same full-replace-on-poll pattern as ARP. The Routes page groups by (destination, next-hop) to avoid duplicate rows when multiple devices report the same physical route, and shows a separate "subnet gateway" column sourced from your configured gateway on Subnets — not SNMP-observed data. Feeds the `subnet_unrouted` and `route_gateway_mismatch` conflict types once at least one route has been discovered anywhere (so an install with no routing-capable collector doesn't flag every subnet as unrouted).

## Capacity Planner

Given a required host count, calculates the smallest CIDR that fits, finds where it fits across your existing subnets, and reserves it in one step (writes `reserved` rows into `ip_addresses`, same mechanism as the IP grid/bulk-update). Reservation size and scan limits are capped internally to keep the search fast on very large subnets.

## Alerting

Five built-in condition types: `subnet_near_exhaustion`, `ip_conflict_detected`, `dhcp_pool_exhausted`, `dns_ptr_mismatch`, `collector_down`. Create rules under Alerts → Rules — an inline form, no separate modal. The engine evaluates every 30 seconds and auto-resolves once the target is no longer in violation. Each rule has a **cooldown** (minutes, default 15) so a flapping condition doesn't spam a new event every tick, and per-rule notification channels (`inapp`, `email`, `webhook`, `slack`). CSV export/import (with a template) is available for bulk rule provisioning. Resolved alert events and utilization-history rows are purged automatically after their retention window (default 90 / 30 days).

## Backup & Restore

Configure schedule and rotation at Settings → Data → Backups, or trigger immediately with **Run backup now**. Each snapshot is a timestamped directory under the configured backup path containing `pktipam.db` + `config.yaml`.

**Restoring:**
- Every listed snapshot has a **Restore…** link — restores directly from that on-server snapshot, no download/upload needed. Expanding it shows a checkbox per file present, so you can restore just `pktipam.db` or just `config.yaml` instead of both together.
- A full bundle can also be downloaded/uploaded as a `.tar.gz`, with the same per-file selection on upload.
- Restoring a backup requires a manual service restart afterward to pick up any restored config.

## Suite Integration

Both directions live on Settings → Security → Suite Integration: the inbound Suite Token pktHub uses to proxy in, and the multi-instance list of named pktSNMP connections that the `pktsnmp_suite` device collector reads from (deep-links to Settings for each). Regenerating the token immediately revokes the old one.

## Troubleshooting

| Symptom | Check |
|---|---|
| Service won't start | `journalctl -u pktipam -n 50`; check `config.yaml` and secret key |
| Collector shows `status: error` | Check `last_error` via the Collectors page, or **Poll Now** for the full error |
| A device/lease you expect isn't showing up | Confirm the relevant collector is enabled and its last poll succeeded |
| Frontend shows `{"detail":"Not Found"}` | Frontend wasn't built — `cd frontend && npm install && npm run build`, then restart |
| A restored `config.yaml` didn't take effect | Restart the service — restoring never does this automatically |

## Upgrading

Pull the latest code, rebuild the frontend if you build manually, then restart the service. Migrations run automatically on startup.
