# pktIPAM — User Guide

This guide is for people who use pktIPAM to manage subnets, IP addresses, and DNS/DHCP records — not for installing or administering the server. See [ADMIN_GUIDE.md](ADMIN_GUIDE.md) for setup, users, backups, and integrations.

## Logging in

Log in with your username and password, or Okta SSO if configured.

| Action | Admin | Analyst | Viewer |
|---|---|---|---|
| View everything | ✓ | ✓ | ✓ |
| Create/edit subnets, VLANs, sites, manual IP reservations | ✓ | ✓ | — |
| Resolve conflicts, ack/resolve alerts | ✓ | ✓ | — |
| Manage collectors, integrations, Settings, users | ✓ | — | — |

## Navigation

**Dashboard**, **Subnets**, **IP Addresses**, **VLANs**, **Capacity Planner**, **DHCP Leases**, **DNS Records**, **Routes**, **Conflicts**, **Alerts**, **Logs**. **Settings** appears only for admins.

Settings has a section bar at the top with **Common** (General, Security, Data, Notifications, User Keys, System — the same in every pkt* app) and **pktIPAM** (SNMP Credentials, Sites, Collectors). The tab row below shows one section at a time, so switch sections if a tab looks missing. Links that point straight at a tab pick the section for you.

## Subnets

Each subnet holds a CIDR, optional VLAN link, site, gateway, and optional parent subnet (for hierarchy). Click a subnet to open its detail view: the full IP grid for that block, utilization, and per-IP history.

## IP Addresses

Browse and search IPs across a subnet. Each IP shows its current status:

- **free** — nothing currently sees this IP
- **dhcp** — an active dynamic lease
- **reserved** — a DHCP server's own fixed/reservation config, kept distinct from a plain dynamic lease
- **static** — a manual reservation you or another admin/analyst made
- **used** — only a DNS record points here, with no lease/ARP corroboration
- **conflict** — something's wrong (see Conflicts below)

Click an IP with a history marker to see its full change timeline — first seen, changed (MAC/hostname differs from last known), or released (disappeared from every source).

**Mass IP update**: select a set of IPs within one subnet and apply status, owner, description, and/or tags to all of them at once — each field has its own apply toggle, so you can change just the owner without touching status, for example.

## Capacity Planner

Given a required host count, calculates the smallest CIDR block that fits, shows candidate locations across your existing subnets, and reserves the chosen block in one step — no manual IP-by-IP reservation needed.

## VLANs

A simple catalog: tag, name, site, description — unique per site. Picking a VLAN on a subnet auto-fills that subnet's description from the VLAN's own description the first time (editing it manually afterward stops future overwrites).

## DHCP Leases / DNS Records

Read-only views of what your DHCP and DNS collectors have observed. Some DNS records (marked distinctly) are **synthetic** — synthesized from a DHCP lease's own hostname when the DHCP server (Pi-hole/dnsmasq) doesn't separately expose that resolution as a DNS record; these disappear automatically when the underlying lease does.

## Routes

Shows discovered routing-table entries, grouped by destination + next-hop so the same physical route reported by multiple devices doesn't show up as noisy duplicates. Includes a "subnet gateway" column sourced from your admin-configured gateway on the Subnets page, separate from what was actually observed on the wire.

## Conflicts

Active/History tabs, same pattern as Alerts. Conflict types: duplicate IP (two MACs claiming the same address), duplicate MAC (one MAC on two IPs at once), static/DHCP mismatch, stale DNS, overlapping subnets, an unrouted subnet, or a subnet whose configured gateway doesn't match any discovered route. Resolve individually or in bulk ("Resolve all"); resolving acknowledges the conflict, it doesn't fix the underlying data — a conflict whose cause is still present will reopen on the next check.

## Alerts

Active/History/Rules tabs. Built-in condition types: subnet nearing exhaustion, IP conflict detected, DHCP pool exhausted, DNS PTR mismatch, collector down. Ack or resolve if your role allows.

## Looking up an IP address

Any IP shown in the app is clickable, opening a lookup using your own per-user API keys (Settings → User Keys) — same pattern as the rest of the pkt suite.

## Getting help in the app

A **?** button near most page headings and Settings sections opens a short explainer.

For longer-form documentation, click **Documentation** in the sidebar (just above your account info) — it opens this guide, the Administrator Guide, and the Collector Setup guide as in-app tabs, so you don't need the repo checked out to read them.
