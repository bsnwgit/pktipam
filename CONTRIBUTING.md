# Contributing to pktIPAM

## Branch strategy

| Branch | Purpose |
|---|---|
| `main` | Production-ready code — reflects what is deployed |
| `feature/<name>` / `fix/<name>` | Individual features or bug fixes, branched from `main` |

## Workflow

### Starting new work

```bash
cd pktipam

# Make sure you're up to date
git checkout main
git pull

# Create a feature branch
git checkout -b feature/your-feature-name
```

### Committing changes

```bash
git add -A
git commit -m "short description of what changed"
git push -u origin feature/your-feature-name
```

### Opening a PR

```bash
# PR from feature branch directly into main
gh pr create --base main --head feature/your-feature-name --title "Your feature title"
```

### Deploying after merge

```bash
# On the server:
cd pktipam && git pull && cd frontend && npm ci && npm run build && cd .. && bash install.sh
```

Always cut a brand-new branch off `main` for each round of work — don't reuse a
branch name across unrelated changes, since a previously merged branch name
can be silently re-merged as a no-op.

## Deployment rules

- **Never deploy directly from a feature branch** — merge to `main` first
- **Deployment/diagnostic helper scripts are environment-specific** — keep
  them in a local, untracked `scripts/` directory (already excluded via
  `.gitignore`); they are not part of this repository
- **No source file hardcodes an absolute install path** — `install_dir` is
  resolved at runtime and every other path derives from it (see
  `app/config.py`); don't reintroduce a literal path in a template or
  shipped config
- **`install.sh` always runs as the normal user, never `sudo ./install.sh`**
  — it calls `sudo` internally wherever it actually needs root

## Adding a new collector

Each collector category (`dhcp`, `dns`, `device`) lives under
`app/ipam/collectors/<category>/`. To add one:

1. Write a `*Collector` subclass in that category's package — see the
   category's `base.py` for the reading dataclass shape it must return.
2. Register it in that category's `registry.py` with a `label` and a
   `fields` list built from the helpers in
   `app/ipam/collectors/field_schema.py` (`text`, `password`, `number`,
   `toggle`, `select`, `multiselect`, `string_list`, `host_list`,
   `site_select`, `credential_select`, `pktsnmp_select`) — this is what
   drives the Collectors UI form, not a raw JSON textarea.
3. If the collector needs SNMP auth, use `credential_select` against the
   [SNMP Credential Library](README.md#snmp-credential-library) rather
   than adding inline community-string/v3 fields.

See [`docs/collector-setup.md`](docs/collector-setup.md) for the full
field reference of every currently-shipped collector.

## Commit message style

```
type: short description (imperative, lowercase)

Examples:
  feat: add PowerDNS zone collector
  fix: correct Infoblox WAPI paging on large grids
  chore: update requirements.txt
  docs: expand collector setup guide
```
