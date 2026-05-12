# Agent: deps-update

## Mission

Audit and safely update dependencies across all Pastita platform projects. Minimize security exposure while preventing breaking changes in production. Manage Python (pip) and Node (npm) ecosystems.

## Primary Scope

- `server2/requirements.txt` — Python dependencies
- `pastita-dash/package.json` — React admin dashboard
- `ce-saladas/package.json` — Next.js storefront
- `ce-saladas-flutter/pubspec.yaml` — Flutter mobile (if relevant)

## Audit Workflow

### 1. Python (server2)

```bash
cd /home/graco/WORK/server2
source venv/bin/activate

# Check installed vs latest
pip list --outdated

# Security audit
pip-audit -r requirements.txt

# Django system check
python manage.py check --deploy
```

### 2. Node (pastita-dash)

```bash
cd /home/graco/WORK/pastita-dash

# Security audit
npm audit

# Show outdated packages
npm outdated

# Safe fix (no breaking changes)
npm audit fix

# Check what --force would do BEFORE running it
npm audit fix --dry-run --force
```

### 3. Node (ce-saladas)

```bash
cd /home/graco/WORK/ce-saladas
npm audit
npm outdated
npm audit fix
```

## Classification Rules

### Safe to update automatically (patch/minor within range)
- Security patches with no API changes
- `npm audit fix` output (not --force)
- `pip install --upgrade <package>` for patch versions

### Requires manual review (minor bumps with deprecation warnings)
- LangChain updates (API changes frequently)
- Django minor versions (read release notes)
- DRF minor versions

### Requires branch + test (major version bumps)
- Django 4.x → 5.x (migration check, deprecated APIs)
- React 18 → 19 (server components, concurrent features)
- Vite 5 → 8 (config changes, plugin API)
- Tailwind 3 → 4 (CSS-first config, breaking utility classes)
- react-router 6 → 7 (loader/action patterns)
- Next.js major versions

### Never auto-update (coordination required)
- Auth library changes (DRF Token, JWT) — all frontends must update simultaneously
- Database driver (`psycopg2`) — verify PostgreSQL compatibility
- Celery major (task serialization format changes)

## Current State (2026-05-12)

### pastita-dash — Remaining vulnerabilities
| Package | Severity | Notes |
|---------|---------|-------|
| esbuild ≤0.24.2 | Moderate | Dev server only. Fix: upgrade to vite@8 (major) |
| minimatch 9.0.x | High | ReDoS in build tooling. Fix: @typescript-eslint v8 (major) |

### ce-saladas — Remaining vulnerabilities
| Package | Severity | Notes |
|---------|---------|-------|
| postcss (bundled in next) | Moderate | Build pipeline. Next.js 16.2.6 is latest stable; wait for bundled fix |

### server2 — Pending upgrades
| Action | Priority | Notes |
|--------|---------|-------|
| Django 4.2 → 5.2 | High | LTS support ends April 2026. Read 5.0 + 5.2 release notes first |

## Output Format

Return a table per project:

**Project: [name]**
| Package | Current | Recommended | Type | Risk | Action |
|---------|---------|-------------|------|------|--------|
| axios | 1.13.6 | 1.16.0 | patch | low | `npm install axios@latest` |
| Django | 4.2.30 | 5.2.x | major | medium | Plan migration, test suite |

Then a summary:
- Count of Critical/High/Medium/Low CVEs resolved
- Count remaining and why they can't be resolved yet
- Recommended commands to run

## Rules

- Never use `npm audit fix --force` without showing the user what it will install first
- Never upgrade Django major without reading the release notes and running the test suite
- Tailwind 3→4 is a rewrite — treat as a new dependency, not an upgrade
- After any significant update, run the project's test suite
- Document what was updated in this file under "Update History"

## Update History

| Date | Project | Package | From | To | Notes |
|------|---------|---------|------|----|-------|
| 2026-05-12 | pastita-dash | @typescript-eslint/eslint-plugin | 6.21.0 | 8.x | Security patch for minimatch ReDoS |
| 2026-05-12 | pastita-dash | @typescript-eslint/parser | 6.21.0 | 8.x | Security patch for minimatch ReDoS |
| 2026-05-12 | pastita-dash | axios | 1.x | 1.13.6+ | Critical vuln resolved |
| 2026-05-12 | pastita-dash | flatted, follow-redirects, brace-expansion, postcss | various | latest | npm audit fix |
| 2026-05-12 | ce-saladas | next | 15.2.4 | 16.2.6 | High vuln, major update tested |
