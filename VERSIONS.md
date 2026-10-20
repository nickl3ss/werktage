# Versions and sources

Register of everything this repository depends on or ships from elsewhere
(standard rules COD-18, SEC-10, REC-06). Data sources and their licences are
listed in [NOTICE](NOTICE).

## Runtime (installed by Home Assistant from `manifest.json`)

| Package | Version | Why | Licence |
|---|---|---|---|
| `holidays` | `>=0.60` (Home Assistant pins the exact version it ships; the `holiday` and `workday` core integrations use the same package) | Public holidays per country and subdivision, computed locally | MIT |
| `aiohttp` | the version Home Assistant ships | HTTP client of the OpenHolidays library; the integration passes Home Assistant's shared session | Apache 2.0 |

## Shipped from this repository

| Part | Source | Version | Check |
|---|---|---|---|
| `custom_components/werktage/openholidays/` | `lib/openholidays/src/openholidays/` (same repository) | `lib/openholidays/pyproject.toml` `version`, currently 0.1.0; rises only when the library changes (P34) | `tools/sync_vendor.py --check` fails when the copy differs from the source (byte-identical) |
| `custom_components/werktage/www/werktags-cards.js` | `frontend/src/{logic.js,cards.js}` | the integration's version from `manifest.json`, written into the bundle header | `tools/build_cards.py` + `git diff --exit-code` in `bin/check` |
| `custom_components/werktage/brand/icon*.png` | `docs/brand/werktags-source.jpg` (own artwork) | — | — |

## Development (`requirements-dev.txt`, pinned; Dependabot keeps them current)

| Package | Why |
|---|---|
| `pytest-homeassistant-custom-component` | Home Assistant test harness; its version decides the Home Assistant version the tests run against (the CI job `minimum-ha` uses the oldest supported one, see `hacs.json`) |
| `pytest-cov` | coverage threshold in `bin/check` and CI |
| `mypy` | strict typing of integration and library |
| `ruff` | lint (120 characters) |
| `holidays` | same package as at run time, for the tests |
| `-e lib/openholidays` | the library itself, editable |

Node: the card tests use only `node --test` from Node 22 or newer; there is no
`package.json` and no `node_modules`.

## GitHub Actions

Generic actions are pinned to a commit with the version as a comment;
Dependabot updates them. `home-assistant/actions/hassfest@master` and
`hacs/action@main` follow the upstream recommendation (exception `SEC-10` in
`standards.yaml`).
