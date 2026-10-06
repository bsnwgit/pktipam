# pktIPAM — Troubleshooting

Symptom, cause, and the command that proves which cause it is.

`<INSTALL_DIR>` is the install directory (`/opt/pktipam` by default).
Collector setup itself is in [collector-setup.md](collector-setup.md).

---

## Contents

- [The first five minutes](#the-first-five-minutes)
- [The service will not start](#the-service-will-not-start)
- [The service runs but nothing answers](#the-service-runs-but-nothing-answers)
- [The UI is blank, stale, or 404](#the-ui-is-blank-stale-or-404)
- [Login and accounts](#login-and-accounts)
- [A collector will not poll](#a-collector-will-not-poll)
- [Per-collector-type failures](#per-collector-type-failures)
- [Data is missing or wrong](#data-is-missing-or-wrong)
- [Conflicts](#conflicts)
- [Alerts and notifications](#alerts-and-notifications)
- [A config change did not take effect](#a-config-change-did-not-take-effect)
- [TLS / HTTPS](#tls--https)
- [Backup and restore](#backup-and-restore)
- [Upgrades and migrations](#upgrades-and-migrations)
- [Performance and disk](#performance-and-disk)
- [Uninstalling and reinstalling](#uninstalling-and-reinstalling)
- [What to capture before reporting a problem](#what-to-capture-before-reporting-a-problem)

---

## The first five minutes

```bash
sudo systemctl status pktipam --no-pager
```

```bash
sudo journalctl -u pktipam -n 100 --no-pager
```

```bash
sudo tail -n 100 <INSTALL_DIR>/logs/pktipam.log
```

```bash
sudo ss -ltnp | grep 8761
```

```bash
curl -s http://127.0.0.1:8761/api/health
```

| What you see | Go to |
|---|---|
| `inactive (dead)` or `failed` | [The service will not start](#the-service-will-not-start) |
| Running, nothing on 8761 | [The service runs but nothing answers](#the-service-runs-but-nothing-answers) |
| Health 200, UI blank or 404 | [The UI is blank, stale, or 404](#the-ui-is-blank-stale-or-404) |
| Health 200, no addresses or leases | [A collector will not poll](#a-collector-will-not-poll) |

Almost every "pktIPAM is empty" report is a collector that is disabled, failing,
or has never run. The Collectors page shows `status` and `last_error` per
collector — read those before anything else.

---

## The service will not start

```bash
sudo journalctl -u pktipam -n 200 --no-pager
sudo tail -n 200 <INSTALL_DIR>/logs/pktipam.log
```

Reproduce in the foreground:

```bash
sudo -u <service-user> \
  PKTIPAM_CONFIG=<INSTALL_DIR>/config.yaml \
  PKTIPAM_INSTALL_DIR=<INSTALL_DIR> \
  <INSTALL_DIR>/venv/bin/python -m app.server
```

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` | venv missing packages, or built against a different Python | `<INSTALL_DIR>/venv/bin/pip install -r requirements.txt`; rebuild the venv if Python was upgraded |
| `yaml.scanner.ScannerError` | `config.yaml` is not valid YAML | `python3 -c "import yaml; yaml.safe_load(open('<INSTALL_DIR>/config.yaml'))"` |
| Complaint about `secret_key` / `credential_key` | Left at `CHANGE_ME_…` | `openssl rand -hex 32`; and `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `Address already in use` | Something else holds 8761 | `sudo ss -ltnp \| grep 8761` |
| Fernet `InvalidToken` | `credential_key` changed after collector credentials were stored | **Every collector's config is encrypted with it** — see [A config change did not take effect](#a-config-change-did-not-take-effect) |
| `Permission denied` on DB or logs | Install dir not owned by the service user | `sudo chown -R <service-user>:<service-group> <INSTALL_DIR>` |

The unit uses `Restart=on-failure` with a burst limit of 3 in 60s. After that
systemd stops trying and leaves it `failed` — read the *first* failure, not just
the last.

---

## The service runs but nothing answers

```bash
sudo ss -ltnp | grep 8761
```

`host:` and `port:` come from `config.yaml` at every process start, so a port
change needs only a restart, never a unit edit. Bound to `127.0.0.1` means
loopback only — set `host: "0.0.0.0"`.

```bash
curl -sv http://127.0.0.1:8761/api/health
```

If loopback works and nothing else does, it is the firewall, the bind address,
or routing — not the app.

---

## The UI is blank, stale, or 404

| Symptom | Cause | Fix |
|---|---|---|
| `{"detail":"Not Found"}` at the root | The frontend was never built | `cd frontend && npm install && npm run build`, then restart. Node.js 20.x LTS is a prerequisite `install.sh` does not install |
| Blank page, console 404s on `/assets/*` | `dist` stale or half-built | Rebuild, then hard-refresh |
| Old UI after an upgrade | Cached `index.html` pinning old hashed bundles | Hard refresh (Ctrl/Cmd-Shift-R) |
| Every API call 401 | Session expired | See [Login and accounts](#login-and-accounts) |
| CORS errors | Frontend on a different origin from the API | `cors_origins` defaults to this app's own origin. Only change it if you host the frontend separately; never `"*"` with credentialed requests |

---

## Login and accounts

bcrypt plus JWT. Roles `admin` / `analyst` / `viewer` — note that conflict
resolution requires **analyst** or above, so a `viewer` seeing no resolve
buttons is correct.

| Symptom | Cause | Fix |
|---|---|---|
| "Too many failed sign-in attempts from this address" (HTTP 429) | The address made too many failed sign-ins and is blocked for a while, even with correct credentials. Behind a proxy on another host every user shares the proxy's address | It ends by itself (the message says how long). Raise *Failed sign-ins per address* under Settings -> Security -> Auth if real users are hitting it |
| "This account is locked after repeated failed logins" | Too many failed logins: locked 30 minutes the first time, until an admin unlocks it the second time | An admin clicks the unlock icon on Settings -> Security -> Users, or run `scripts/unlock_user.py <username>` on the server |
| 401 immediately after logging in | Clock skew invalidates the token's `exp` | `timedatectl`; fix NTP |
| Cannot resolve or acknowledge a conflict | Role is `viewer` | Needs `analyst` or `admin` |
| Cannot see or edit collectors | Collector read/write is admin-only | Needs `admin` |
| Locked out of every account | No admin session left | Reset the hash against SQLite using the app's own venv for bcrypt |

```bash
<INSTALL_DIR>/venv/bin/python -c "import bcrypt; print(bcrypt.hashpw(b'NewPassword1!', bcrypt.gensalt()).decode())"
```

---

## A collector will not poll

Start here, always:

- **Collectors page → `last_error`.** Every failure is recorded there.
- **Poll Now** (`POST /api/collectors/{id}/poll-now`) runs it immediately and
  returns the full error. The error deliberately includes the exception type
  name, so you never get an empty message.

| Symptom | Cause | Fix |
|---|---|---|
| `status: error` | Whatever `last_error` says | Work that error, not the symptom |
| Never polls, no error | The collector is **disabled** | Enable it. A disabled collector is silent, not failing |
| Poll Now returns "Collector type is not implemented yet" | The type exists in the registry but has no working class | Every shipped type is implemented; if you see this, the registry and the code have diverged |
| `Unknown collector_type '<x>' for category '<y>'` on save | The type is not valid for that category | DHCP, DNS and device are separate registries — a DNS type cannot be saved under DHCP |
| Polls succeed but nothing appears | The poll worked and returned nothing | See [Data is missing or wrong](#data-is-missing-or-wrong) |
| Every collector fails after a restore or key change | Collector config is Fernet-encrypted with `credential_key` | If that key changed, the stored configs are unrecoverable — re-enter them |

---

## Per-collector-type failures

Collector config is stored encrypted, so the credentials in the UI are the only
copy. Each type fails in its own way.

### DHCP

| Type | Common failures |
|---|---|
| **ISC Kea** (Control Agent API) | Control Agent not running or not listening; the API endpoint requires auth the collector was not given; the Kea instance is a DHCPv6 server when v4 leases were expected |
| **Windows Server DHCP** (WinRM) | WinRM not enabled on the server; HTTP vs HTTPS listener mismatch; the account lacks DHCP-read rights; domain vs local account format |
| **ISC dhcpd (legacy)** (SSH + lease file) | SSH auth; the lease file path is wrong; the SSH user cannot read it; the file is mid-rotation |
| **Infoblox NIOS DHCP** (WAPI) | WAPI version mismatch in the URL; certificate verification against a self-signed grid; the account lacks WAPI permissions |
| **Pi-hole** (v6 REST API) | This is the **v6** REST API — a Pi-hole v5 host does not expose it; wrong app password |

### DNS

| Type | Common failures |
|---|---|
| **Generic AXFR** | The zone transfer is refused — the server must explicitly allow AXFR from this host's IP. This is the single most common DNS collector failure |
| **PowerDNS API** | API not enabled, wrong API key, or the webserver is bound to loopback on the PowerDNS host |
| **Windows Server DNS** (WinRM) | As Windows DHCP above, plus the account needing DNS-read rights |
| **Infoblox NIOS DNS** (WAPI) | As Infoblox DHCP above |
| **Pi-hole** (v6 REST, local DNS records) | Only returns Pi-hole's *local* DNS records — it is not a full zone |

### Device

| Type | Common failures |
|---|---|
| **Generic SNMP** (ARP / IP-MIB walk) | Community or v3 credentials wrong; an ACL on the device restricting which source IPs may poll; the device does not expose the ARP table to SNMP |
| **pktSNMP** (suite-token aggregation) | The suite connection to pktSNMP is wrong, disabled, or its token was rotated on the pktSNMP side; TLS verification against a self-signed sibling |

Device collectors are also what populate the `routes` table, which
[`subnet_unrouted`](#conflicts) depends on.

---

## Data is missing or wrong

| Symptom | Cause |
|---|---|
| A lease you expect is absent | The collector that should see it is disabled, failing, or polled before the lease existed. Check its last successful poll time |
| An address shows no hostname | No DNS collector has a record for it, or the DNS collector's zone does not cover that subnet |
| A device is in ARP but not DHCP | Correct — a static host has no lease. That is what the manual/static entry type is for |
| Subnet utilisation looks wrong | Check the subnet definition itself before the data. A wrong prefix length changes every number on the page |
| Everything is stale | Reconciliation runs on a tick. A collector that polls hourly cannot produce minute-fresh data |
| Data appeared then vanished | A collector returned an empty result and the reconcile pass rewrote from it. Check that collector's last error |

---

## Conflicts

Seven types are detected each reconcile tick. Knowing what each one actually
asserts is most of the work:

| Conflict | What it means |
|---|---|
| `duplicate_ip` | The same IP has leases from more than one distinct MAC, possibly across different DHCP collectors |
| `duplicate_mac` | The same MAC is bound to more than one IP concurrently, counting DHCP leases and ARP sightings together |
| `static_dhcp_mismatch` | A manual static reservation's MAC differs from the MAC on an active DHCP lease for that IP |
| `dns_mismatch` | A DNS A/AAAA record points at an IP with **no** corroborating lease, ARP sighting or manual entry — stale DNS |
| `subnet_overlap` | Two subnet rows have overlapping CIDRs |
| `subnet_unrouted` | No discovered route exists for that subnet's exact CIDR from any device-collector routing-table walk |
| `route_gateway_mismatch` | A subnet has a configured gateway, a route for its exact CIDR exists, and none of that route's discovered next-hops match the configured gateway |

Behaviour worth knowing:

- Conflicts are upserted on `(conflict_type, ip_address, subnet_id)`. They are
  re-detected every tick while they persist.
- **A conflict not re-detected this tick is left alone.** Your manual resolution
  is not clobbered just because the underlying data briefly vanished from one
  poll.
- `subnet_unrouted` is only evaluated once at least one route has been
  discovered *anywhere*. An install with no routing-capable device collector
  does not flag every subnet as unrouted.

| Symptom | Cause |
|---|---|
| A resolved conflict came back | It was re-detected — the underlying disagreement is still there |
| Every subnet flags `subnet_unrouted` | One device collector discovered a few routes, so the check activated, but does not cover your whole estate |
| `dns_mismatch` on hosts you know exist | They are static and not in ARP either — add a manual entry, or accept that DNS is the only evidence |
| `duplicate_ip` across two DHCP servers | Two scopes genuinely overlap, or the same scope is served by two servers not sharing lease state |
| Conflicts never appear at all | Reconciliation has nothing to compare — one source only |

---

## Alerts and notifications

Channels are in-app, Email (SMTP), Slack, PagerDuty, generic Webhook and
Tracecat. Senders are written never to raise, so **a failing channel looks like
nothing happening**. Use Send Test for the real error.

| Symptom | Cause |
|---|---|
| No alerts at all | Nothing to evaluate — no collector is returning data |
| Conflict alerts never fire | The rule is not enabled, or no conflict of that type is being detected |
| Email never arrives | SMTP host, port (default 587), TLS, credentials, or the relay refusing the sender |
| Slack 4xx | Webhook revoked or malformed |
| Webhook target sees nothing | Method, headers, or the Jinja2 payload template failing to render |

---

## A config change did not take effect

**Wrong file.** Env vars beat `config.yaml` silently:

```bash
systemctl show pktipam -p Environment
```

**Not restarted.** Nothing in `config.yaml` is re-read live, and restoring a
backed-up `config.yaml` never restarts the service.

**The setting is not in `config.yaml`.** That file holds startup and
infrastructure only: host, port, workers, secrets, paths. Collectors, alert
rules, notification channels and the outbound pktSNMP integration all live in
**SQLite** and are managed in the UI.

### `credential_key` changed or was lost

Every collector's config — DHCP and DNS credentials, SNMP communities and v3
keys, SSH keys, WAPI and API passwords — is Fernet-encrypted with
`credential_key`. Change it and all of them become undecryptable. Restore the
old key, or re-enter every collector. This is why `uninstall.sh` keeps
`config.yaml` by default.

---

## TLS / HTTPS

`ssl_dir` defaults to `<INSTALL_DIR>/ssl`.

| Symptom | Cause | Fix |
|---|---|---|
| Still HTTP after uploading a cert | Not restarted | Restart |
| Will not start after upload | Key does not match the cert, or is unreadable by the service user | Compare `openssl x509 -noout -modulus -in cert.pem \| openssl md5` with `openssl rsa -noout -modulus -in key.pem \| openssl md5` |
| Certificate warning | Self-signed, or the SAN does not cover the hostname used | Expected for self-signed |
| The pktSNMP device collector fails on TLS | Suite calls verify the target's certificate | Fix pktSNMP's cert, or clear verify-TLS for that connection |

```bash
curl -k https://127.0.0.1:8761/api/health
```

---

## Backup and restore

| Symptom | Cause |
|---|---|
| No backups appearing | Schedule off, or settings unset — they live in SQLite |
| Backups fail | Backup root not writable, or disk full |
| Restore "worked" but nothing changed | A restored `config.yaml` never restarts the service |
| Restored elsewhere and every collector fails | `credential_key` differs — restore `config.yaml` too |

**Never copy a live SQLite database with `cp`.** Take `pktipam.db`, `-wal` and
`-shm` with the service stopped, or use `sqlite3 … ".backup"`.

---

## Upgrades and migrations

Numbered `.sql` files, run on startup, tracked in `_migrations`, safe to re-run.

```bash
git pull
cd frontend && npm install && npm run build && cd ..
sudo systemctl restart pktipam
```

Re-running `install.sh` is better when a release drops or renames a file. Data is
kept, and the port you enter is applied to the existing `config.yaml` without
touching another line. `PKTIPAM_REMOVE_EXISTING=1` (or `0`) answers that prompt
from a script.

| Symptom | Cause |
|---|---|
| `no such column` / `no such table` | Migrations did not run — the app failed earlier in startup |
| A migration fails | Compare `SELECT * FROM _migrations` against `ls migrations/`. Restore from backup first |
| App upgraded, UI did not | Frontend not rebuilt, or browser cache |
| `VERSION` looks wrong | Bumped by `scripts/bump_version.py`, never by hand |

---

## Performance and disk

```bash
df -h
du -sh <INSTALL_DIR>/*
```

| Symptom | Where to look |
|---|---|
| Disk filling | `pktipam.db`, `logs/`, `backups/`. IP address history accumulates by design |
| Reconciliation slow | Number of addresses times number of sources. A very large estate with many collectors is genuinely expensive |
| A poll takes minutes | AXFR of a huge zone, or an SNMP walk of a large ARP table. Raise that collector's interval rather than fighting it |
| UI slow on the addresses page | Filter to a subnet rather than listing everything |

---

## Uninstalling and reinstalling

```bash
bash <INSTALL_DIR>/uninstall.sh
```

Stops and removes the service, deletes the code and the venv. **Data is kept by
default** — `config.yaml`, `pktipam.db` and its `-wal`/`-shm`, `logs/`,
`backups/` and `ssl/`. It asks separately, defaulting to no.

| Flag | Effect |
|---|---|
| *(none)* | Remove service, code and venv; keep data |
| `--purge` | Also delete config, database, logs, backups and TLS material. Not recoverable |
| `--dry-run` | Print what would be removed |
| `--yes` | Skip prompts |
| `--dir PATH` | Install directory, if the unit is already gone |

**Never mirror over an install directory with `rsync --delete`.** That destroys
the database, the encrypted collector configs, and the address history together.

---

## What to capture before reporting a problem

1. `VERSION`, and how it was installed.
2. `systemctl status pktipam` plus the last 200 lines of **both** the journal and
   `logs/pktipam.log`.
3. `config.yaml` **with `secret_key`, `credential_key` and passwords removed**.
4. For a collector problem: its type, its `last_error`, and the output of
   **Poll Now**.
5. Whether the same operation works outside pktIPAM from this host — `snmpwalk`,
   `dig axfr`, a WinRM or WAPI call. That splits "pktIPAM cannot" from "this host
   cannot".
6. For a conflict question: the conflict type, and which sources claim the
   address.

Never paste real credentials, community strings, API keys, or an unredacted
`config.yaml`.
