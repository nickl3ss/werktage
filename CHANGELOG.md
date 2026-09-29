# Changelog

## 0.1.0 — 2026-09-29 (unreleased)

- Integration: config flow with three steps and options, store with
  versioned JSON, coordinator (midnight rebuild, monthly school holiday
  fetch from the OpenHolidays API or a calendar entity, plausibility check,
  repair issues), morning/evening enum sensors per resident, room and house,
  a days-off calendar per resident, ten services (six writing, three with
  response, one refresh), diagnostics, English and German translations,
  optional card serving (`frontend.py`). Tested against Home Assistant
  2026.9.4 with `pytest-homeassistant-custom-component` (24 tests).
- `deploy.sh <config dir>` copies the integration into an installation;
  `tools/sync_vendor.py` keeps the vendored `openholidays` copy in sync.

- Rules engine `custom_components/werktags/rules.py`: default day by role,
  exceptions in both directions, unknown days count as workdays, morning and
  evening modes, room and house combination rules, histories for roles and
  room assignments, range changes with preview. 34 tests, no Home Assistant
  dependency.
- Library `lib/openholidays`: async client for the OpenHolidays API with
  offline parsers and a plausibility check. 15 tests against a local test
  server. Verified once against the live API.
- Tooling: `pyproject.toml` with pytest, mypy (strict) and ruff; all clean.

## 0.0.1 — 2026-09-29

- Repository created: layout, license (MIT), data source notice, HACS and
  manifest metadata, pre-publication check. No integration code yet.
