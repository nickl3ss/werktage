# Changelog

## 0.1.0 — 2026-09-29 (unreleased)

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
