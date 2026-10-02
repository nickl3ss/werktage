# Changelog

## 0.2.0 — 2026-10-02

- **Breaking: domain renamed from `werktags` to `werktage`**, repository
  moved to `nickl3ss/werktage`. HACS removes the string `tags/` from every
  download URL (meant for the Git ref `tags/<version>`), so a repository or
  directory called `werktags/` was mangled to `werk` and neither the HACS
  validation nor an installation through HACS could work. The product name
  stays *Werktags*; the cards keep their names (`custom:werktags-calendar`
  …); entity ids do not change because they come from person and area
  names. Actions are now `werktage.*`, the card script is served at
  `/werktage_static/`, the store is `.storage/werktage.data`. Migrating an
  existing installation: remove the old entry, install the new version, set
  it up again and re-create residents, rooms and exceptions (see README).
  The HACS bug is reported upstream with a one-line fix.
- Unloading the entry after boot logged "Unable to remove unknown job
  listener": the one-time start listener had already removed itself.

## 0.1.0 — 2026-10-02

- Brand icon ships inside the integration (`brand/`), as Home Assistant
  2026.3 and later expects for custom integrations; no brands pull request.

- Release preparation: minimum Home Assistant 2026.1 (tested in CI next to
  the current release; `hacs.json` said 2025.2, which never worked),
  installation through HACS documented, the HACS check in CI is binding,
  extension ideas moved to GitHub issues.
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
- School holidays are fetched for three calendar years (this year and the two
  after) instead of four; earlier years stay in the cache. The setup dialog
  probes the API with the same range as the monthly fetch.
- Every rejected change has its own translated error message (English and
  German) instead of a generic one carrying English text.
- Silver: test coverage 99 % (CI fails below 95 %). Gold documentation: use
  cases, supported functions, data updates, known limitations,
  troubleshooting.
- A room is its residents: a rule alone no longer creates a room (and three
  unavailable entities), removing the last assignment removes the room, and
  rooms without residents written by earlier versions are dropped on load.
  The rooms card shows the rules once residents are assigned.
- Blueprints are validated with Home Assistant's blueprint schema in the
  tests; their later time now acts in any case, catching up a missed run.
- Cards: the reload-on-change watched `sensor.house_morning`, which only
  exists in English installations; the cards now find the Werktags sensors
  by platform. The script URL carries a hash of the bundle instead of the
  version, so a new build bypasses browser caches. README explains the
  one-time browser reload after setup (*Configuration error* on a card).
- Platinum rules: the setup dialog builds its country and region lists in the
  executor (the `holidays` library took about 0.2 s in the event loop on a
  Raspberry Pi); only two-letter country codes are offered. Every rule in
  `quality_scale.yaml` is now done or exempt except `brands`.
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
  `custom_components/werktage/www/werktags-cards.js` and served by the
  integration. 15 browserless tests (`node --test`).
- `deploy.sh <config dir>` copies the integration into an installation;
  `tools/sync_vendor.py` keeps the vendored `openholidays` copy in sync.

- Rules engine `custom_components/werktage/rules.py`: default day by role,
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
