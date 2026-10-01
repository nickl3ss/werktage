"""Setup in five short steps: country, region, school holidays, house, access.

The school holiday step tests the source before the entry is created
(quality scale: test-before-configure). The options flow is a menu: the same
settings steps (the entry reloads when done) or a form to add a resident, a
room or the residents of the house without a dashboard card.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    AreaSelector,
    BooleanSelector,
    CountrySelector,
    CountrySelectorConfig,
    DateSelector,
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from . import sources
from .const import (
    CONF_ADD_HOLIDAYS,
    CONF_ADMIN_ONLY,
    CONF_CALENDAR_ENTITY,
    CONF_COUNTRY,
    CONF_HOUSE_EVENING_RULE,
    CONF_HOUSE_MORNING_RULE,
    CONF_HOUSE_ROLES,
    CONF_REMOVE_HOLIDAYS,
    CONF_SCHOOL_HOLIDAY_SOURCE,
    CONF_SUBDIVISION,
    CONF_WEEKEND,
    DEFAULT_WEEKEND_DAYS,
    DOMAIN,
    NAME,
    SOURCE_CALENDAR,
    SOURCE_NONE,
    SOURCE_OPENHOLIDAYS,
    SOURCES,
)
from .coordinator import WerktagsCoordinator, WerktagsError, async_probe_openholidays
from .openholidays import OpenHolidaysError
from .rules import DEFAULT_EVENING_RULE, DEFAULT_MORNING_RULE, CombineRule, Role

WEEKDAYS = ["0", "1", "2", "3", "4", "5", "6"]
OPENHOLIDAYS_COUNTRIES = {   # countries the OpenHolidays API covered on 2026-09-29
    "AD", "AL", "AT", "BE", "BG", "BY", "CH", "CZ", "DE", "EE", "ES", "FR", "HR", "HU", "IE", "IT", "LI", "LT",
    "LU", "LV", "MC", "MD", "MT", "NL", "PL", "PT", "RO", "RS", "SE", "SI", "SK", "SM", "UA", "VA",
}
STEP_COUNTRY, STEP_REGION, STEP_SCHOOL_HOLIDAYS, STEP_HOUSE, STEP_ACCESS = (
    "user", "region", "school_holidays", "house", "access")
# options flow: the settings chain starts at "settings"; "house" is the residents form there
STEP_SETTINGS, STEP_HOUSE_RULES, STEP_RESIDENT, STEP_ROOM = "settings", "house_rules", "resident", "room"
NextStep = Callable[[], Awaitable[ConfigFlowResult]]


def _select(options: list[str] | list[SelectOptionDict], *, multiple: bool = False,
            translation_key: str | None = None) -> SelectSelector:
    config = SelectSelectorConfig(options=options, multiple=multiple, mode=SelectSelectorMode.DROPDOWN)
    if translation_key:
        config["translation_key"] = translation_key
    return SelectSelector(config)


def country_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_COUNTRY, default=defaults.get(CONF_COUNTRY, "DE")): CountrySelector(
            CountrySelectorConfig(countries=sources.supported_countries())),
    })


def region_schema(defaults: dict[str, Any], country: str) -> vol.Schema:
    """Subdivision by name (only if the country has any) plus the weekend days."""
    fields: dict[Any, Any] = {}
    options = [SelectOptionDict(value=f"{country}-{code}", label=name)
               for code, name in sources.subdivision_names(country).items()]
    if options:
        default = defaults.get(CONF_SUBDIVISION) or vol.UNDEFINED
        fields[vol.Optional(CONF_SUBDIVISION, default=default)] = _select(options)
    fields[vol.Required(CONF_WEEKEND, default=defaults.get(CONF_WEEKEND, DEFAULT_WEEKEND_DAYS))] = _select(
        WEEKDAYS, multiple=True, translation_key="weekday")
    lines = TextSelector(TextSelectorConfig(multiple=True))
    fields[vol.Optional(CONF_ADD_HOLIDAYS, default=defaults.get(CONF_ADD_HOLIDAYS) or [])] = lines
    fields[vol.Optional(CONF_REMOVE_HOLIDAYS, default=defaults.get(CONF_REMOVE_HOLIDAYS) or [])] = lines
    return vol.Schema(fields)


def holiday_lines_valid(lines: list[str]) -> bool:
    """Added holidays are ``YYYY-MM-DD`` optionally followed by a name."""
    for line in lines:
        try:
            dt.date.fromisoformat(str(line).strip().split(" ", 1)[0])
        except ValueError:
            return False
    return True


def _date_or_today(value: str | None, today: dt.date) -> dt.date:
    return dt.date.fromisoformat(value) if value else today


def source_schema(defaults: dict[str, Any], country: str) -> vol.Schema:
    default_source = defaults.get(CONF_SCHOOL_HOLIDAY_SOURCE,
                                  SOURCE_OPENHOLIDAYS if country in OPENHOLIDAYS_COUNTRIES else SOURCE_NONE)
    return vol.Schema({
        vol.Required(CONF_SCHOOL_HOLIDAY_SOURCE, default=default_source): _select(
            SOURCES, translation_key="school_holiday_source"),
        vol.Optional(CONF_CALENDAR_ENTITY, default=defaults.get(CONF_CALENDAR_ENTITY) or vol.UNDEFINED): EntitySelector(
            EntitySelectorConfig(domain="calendar")),
    })


def house_schema(defaults: dict[str, Any]) -> vol.Schema:
    rules = _select([r.value for r in CombineRule], translation_key="combine_rule")
    return vol.Schema({
        vol.Required(CONF_HOUSE_ROLES, default=defaults.get(CONF_HOUSE_ROLES, [Role.ADULT.value])): _select(
            [Role.ADULT.value, Role.PUPIL.value], multiple=True, translation_key="role"),
        vol.Required(CONF_HOUSE_MORNING_RULE,
                     default=defaults.get(CONF_HOUSE_MORNING_RULE, DEFAULT_MORNING_RULE.value)): rules,
        vol.Required(CONF_HOUSE_EVENING_RULE,
                     default=defaults.get(CONF_HOUSE_EVENING_RULE, DEFAULT_EVENING_RULE.value)): rules,
    })


def access_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema({vol.Required(CONF_ADMIN_ONLY, default=defaults.get(CONF_ADMIN_ONLY, False)): BooleanSelector()})


class _Steps:
    """The steps shared by setup and options; ``self._data`` collects the answers."""

    hass: Any
    _data: dict[str, Any]

    def _country(self) -> str:
        return str(self._data.get(CONF_COUNTRY, "DE"))

    # The ``holidays`` library is synchronous and walks its country modules: keep it off the event loop.
    async def _country_schema(self, defaults: dict[str, Any]) -> vol.Schema:
        schema: vol.Schema = await self.hass.async_add_executor_job(country_schema, defaults)
        return schema

    async def _region_schema(self) -> vol.Schema:
        schema: vol.Schema = await self.hass.async_add_executor_job(region_schema, dict(self._data), self._country())
        return schema

    def _show(self, step_id: str, schema: vol.Schema, errors: dict[str, str] | None = None) -> ConfigFlowResult:
        result: ConfigFlowResult = self.async_show_form(  # type: ignore[attr-defined]
            step_id=step_id, data_schema=schema, errors=errors or {},
            description_placeholders={"country": self._country()})
        return result

    async def _test_source(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Check the school holiday source before accepting it (test-before-configure)."""
        source = user_input.get(CONF_SCHOOL_HOLIDAY_SOURCE)
        if source == SOURCE_CALENDAR:
            entity_id = user_input.get(CONF_CALENDAR_ENTITY)
            if not entity_id:
                return {CONF_CALENDAR_ENTITY: "calendar_required"}
            if self.hass.states.get(entity_id) is None:
                return {CONF_CALENDAR_ENTITY: "calendar_missing"}
        if source == SOURCE_OPENHOLIDAYS:
            try:
                periods = await async_probe_openholidays(self.hass, self._country(),
                                                         self._data.get(CONF_SUBDIVISION) or None)
            except OpenHolidaysError:
                return {"base": "cannot_connect"}
            if not periods:
                return {"base": "not_covered"}
        return {}

    async def _step_region(self, user_input: dict[str, Any] | None, next_step: NextStep) -> ConfigFlowResult:
        if user_input is not None:
            subdivision = user_input.get(CONF_SUBDIVISION) or ""      # the selector only offers this country's
            if not holiday_lines_valid(user_input.get(CONF_ADD_HOLIDAYS) or []):
                return self._show(STEP_REGION, await self._region_schema(),
                                  {CONF_ADD_HOLIDAYS: "holiday_format"})
            self._data.update(user_input)
            self._data[CONF_SUBDIVISION] = subdivision
            return await next_step()
        return self._show(STEP_REGION, await self._region_schema())

    async def _step_school_holidays(self, user_input: dict[str, Any] | None, next_step: NextStep) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._test_source(user_input)
            if not errors:
                self._data.update(user_input)
                if user_input.get(CONF_SCHOOL_HOLIDAY_SOURCE) != SOURCE_CALENDAR:
                    self._data[CONF_CALENDAR_ENTITY] = None
                return await next_step()
        return self._show(STEP_SCHOOL_HOLIDAYS, source_schema(self._data, self._country()), errors)

    async def _step_house(self, user_input: dict[str, Any] | None, next_step: NextStep,
                          step_id: str = STEP_HOUSE) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await next_step()
        return self._show(step_id, house_schema(self._data))


class WerktagsConfigFlow(_Steps, ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_region()
        return self._show(STEP_COUNTRY, await self._country_schema({CONF_COUNTRY: self.hass.config.country or "DE"}))

    async def async_step_region(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step_region(user_input, self.async_step_school_holidays)

    async def async_step_school_holidays(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step_school_holidays(user_input, self.async_step_house)

    async def async_step_house(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step_house(user_input, self.async_step_access)

    async def async_step_access(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title=NAME, data=self._data)
        return self._show(STEP_ACCESS, access_schema(self._data))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> WerktagsOptionsFlow:
        return WerktagsOptionsFlow()


def resident_schema() -> vol.Schema:
    return vol.Schema({
        vol.Required("person"): EntitySelector(EntitySelectorConfig(domain="person")),
        vol.Required("role", default=Role.ADULT.value): _select([r.value for r in Role], translation_key="role"),
        vol.Optional("short_name"): TextSelector(),
        vol.Optional("off_weekdays"): _select(WEEKDAYS, multiple=True, translation_key="weekday"),
        vol.Optional("valid_from"): DateSelector(),
    })


def room_schema() -> vol.Schema:
    rules = _select([r.value for r in CombineRule], translation_key="combine_rule")
    return vol.Schema({
        vol.Required("area"): AreaSelector(),
        vol.Optional("person"): EntitySelector(EntitySelectorConfig(domain="person", multiple=True)),
        vol.Required("morning_rule", default=DEFAULT_MORNING_RULE.value): rules,
        vol.Required("evening_rule", default=DEFAULT_EVENING_RULE.value): rules,
        vol.Optional("valid_from"): DateSelector(),
    })


def house_residents_schema() -> vol.Schema:
    return vol.Schema({
        vol.Optional("person"): EntitySelector(EntitySelectorConfig(domain="person", multiple=True)),
        vol.Optional("valid_from"): DateSelector(),
    })


class WerktagsOptionsFlow(_Steps, OptionsFlowWithReload):
    """A menu: the settings (same steps as the setup, then the entry reloads) or
    a resident, a room or the residents of the house, written straight into
    the store (no reload, no dashboard card needed)."""

    def __init__(self) -> None:
        self._data = {}

    @property
    def _coordinator(self) -> WerktagsCoordinator:
        coordinator: WerktagsCoordinator = self.config_entry.runtime_data
        return coordinator

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init",
                                    menu_options=[STEP_SETTINGS, STEP_RESIDENT, STEP_ROOM, STEP_HOUSE])

    # -- settings chain ---------------------------------------------------------
    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self._data:
            self._data = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            if user_input[CONF_COUNTRY] != self._data.get(CONF_COUNTRY):
                self._data[CONF_SUBDIVISION] = ""          # the old region belongs to the old country
            self._data.update(user_input)
            return await self.async_step_region()
        return self._show(STEP_SETTINGS, await self._country_schema(dict(self._data)))

    async def async_step_region(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step_region(user_input, self.async_step_school_holidays)

    async def async_step_school_holidays(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step_school_holidays(user_input, self.async_step_house_rules)

    async def async_step_house_rules(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step_house(user_input, self.async_step_access, STEP_HOUSE_RULES)

    async def async_step_access(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="", data=self._data)
        return self._show(STEP_ACCESS, access_schema(self._data))

    # -- residents, rooms, house ------------------------------------------------
    def _resident_ids(self, entity_ids: list[str]) -> list[str]:
        """Person ids of the given person entities; ValueError if one is not a resident."""
        ids = [self._coordinator.person_id_of(e) for e in entity_ids]
        if any(pid not in self._coordinator.data.residents for pid in ids):
            raise ValueError("not a resident")
        return ids

    async def async_step_resident(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        c, errors = self._coordinator, {}
        if user_input is not None:
            person_id = c.person_id_of(user_input["person"])
            valid_from = _date_or_today(user_input.get("valid_from"), c.today())
            try:
                await c.async_set_role(person_id, Role(user_input["role"]), valid_from,
                                       (user_input.get("short_name") or "").strip() or None)
            except ValueError:
                errors["short_name"] = "short_name_taken"
            else:
                weekdays = user_input.get("off_weekdays")
                if weekdays:
                    await c.async_set_weekly(person_id, frozenset(int(d) for d in weekdays), valid_from)
                elif c.data.residents[person_id].off_weekdays.steps:
                    await c.async_set_weekly(person_id, None, valid_from)
                return self.async_abort(reason="resident_saved")
        return self.async_show_form(step_id=STEP_RESIDENT, data_schema=resident_schema(), errors=errors)

    async def async_step_room(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        c, errors = self._coordinator, {}
        if user_input is not None:
            try:
                person_ids = self._resident_ids(user_input.get("person") or [])
            except ValueError:
                errors["person"] = "not_resident"
            else:
                try:
                    await c.async_set_room(user_input["area"], person_ids,
                                           _date_or_today(user_input.get("valid_from"), c.today()),
                                           CombineRule(user_input["morning_rule"]),
                                           CombineRule(user_input["evening_rule"]))
                except WerktagsError as err:
                    errors["person" if err.key == "room_without_residents" else "area"] = err.key
                else:
                    return self.async_abort(reason="room_saved")
        return self.async_show_form(step_id=STEP_ROOM, data_schema=room_schema(), errors=errors)

    async def async_step_house(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        c, errors = self._coordinator, {}
        if user_input is not None:
            try:
                person_ids = self._resident_ids(user_input.get("person") or [])
            except ValueError:
                errors["person"] = "not_resident"
            else:
                await c.async_set_house(person_ids or None, _date_or_today(user_input.get("valid_from"), c.today()))
                return self.async_abort(reason="house_saved")
        return self.async_show_form(step_id=STEP_HOUSE, data_schema=house_residents_schema(), errors=errors)
