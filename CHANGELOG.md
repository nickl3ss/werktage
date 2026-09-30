# Changelog

## 0.1.0 — 2026-09-29 (unreleased)

- Gaps from the product audit: personal days off every week per resident
  (`set_weekly`, history), the house follows chosen residents instead of
  roles (`set_house`, history), extra and removed public holidays in the
  region step, `binary_sensor.<x>_workday` for residents, rooms and the
  house, two automation blueprints (cover in the morning, lights off in the
  evening), an options menu that adds residents, rooms and house residents
  without any dashboard card. Store version 2. Brand icon from the
  household's artwork (`brand/icon.png` in 256 px and a 2× variant in 512 px).
- Cards: weekday chips per resident with a reset to the household weekend;
  the house row on the rooms card is editable (empty = by role). 17 card
  tests, 84 Python tests.
- Library: ranges longer than 1095 days (the API's maximum, e.g. four
  calendar years with a leap year) are fetched in consecutive windows. Found
  on the first live run; before, every monthly fetch of the
  integration would have failed with HTTP 400.
- Quality scale Bronze complete except the brands pull request (needs a
  public repository): `quality_scale.yaml`, manifest key order and
  `CONFIG_SCHEMA` as hassfest requires (hassfest passes locally), config flow
  tested to 100 %, README with installation parameters, options, removal
  and every action, CI workflow (hassfest, HACS, ruff, mypy, pytest with
  coverage, card tests). 100 Python tests.

- Integration: config flow with three steps and options, store with
  versioned JSON, coordinator (midnight rebuild, monthly school holiday
  fetch from the OpenHolidays API or a calendar entity, plausibility check,
  repair issues), morning/evening enum sensors per resident, room and house,
  a days-off calendar per resident, ten services (six writing, three with
  response, one refresh), diagnostics, English and German translations,
  optional card serving (`frontend.py`). Tested against Home Assistant
  2026.9.4 with `pytest-homeassistant-custom-component` (24 tests).
- Cards `werktags-calendar`, `werktags-period`, `werktags-residents`,
  `werktags-rooms` with a visual editor, in plain JavaScript without a
  framework; bundled by `tools/build_cards.py` into
  `custom_components/werktags/www/werktags-cards.js` and served by the
  integration. 15 browserless tests (`node --test`).
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
