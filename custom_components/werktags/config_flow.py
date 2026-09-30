"""Setup and options in five short steps: country, region, school holidays, house, access.

The school holiday step tests the source before the entry is created
(quality scale: test-before-configure). Options use the same steps and reload
the entry when done.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    CountrySelector,
    CountrySelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from . import sources
from .const import (
    CONF_ADMIN_ONLY,
    CONF_CALENDAR_ENTITY,
    CONF_COUNTRY,
    CONF_HOUSE_EVENING_RULE,
    CONF_HOUSE_MORNING_RULE,
    CONF_HOUSE_ROLES,
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
from .coordinator import async_probe_openholidays
from .openholidays import OpenHolidaysError
from .rules import DEFAULT_EVENING_RULE, DEFAULT_MORNING_RULE, CombineRule, Role

WEEKDAYS = ["0", "1", "2", "3", "4", "5", "6"]
OPENHOLIDAYS_COUNTRIES = {   # countries the OpenHolidays API covered on 2026-09-29
    "AD", "AL", "AT", "BE", "BG", "BY", "CH", "CZ", "DE", "EE", "ES", "FR", "HR", "HU", "IE", "IT", "LI", "LT",
    "LU", "LV", "MC", "MD", "MT", "NL", "PL", "PT", "RO", "RS", "SE", "SI", "SK", "SM", "UA", "VA",
}
STEP_COUNTRY, STEP_REGION, STEP_SCHOOL_HOLIDAYS, STEP_HOUSE, STEP_ACCESS = (
    "user", "region", "school_holidays", "house", "access")
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
    return vol.Schema(fields)


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
            subdivision = user_input.get(CONF_SUBDIVISION) or ""
            if subdivision and subdivision not in sources.supported_subdivision_codes(self._country()):
                return self._show(STEP_REGION, region_schema(self._data, self._country()),
                                  {CONF_SUBDIVISION: "invalid_subdivision"})
            self._data.update(user_input)
            self._data[CONF_SUBDIVISION] = subdivision
            return await next_step()
        return self._show(STEP_REGION, region_schema(self._data, self._country()))

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

    async def _step_house(self, user_input: dict[str, Any] | None, next_step: NextStep) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await next_step()
        return self._show(STEP_HOUSE, house_schema(self._data))


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
        return self._show(STEP_COUNTRY, country_schema({CONF_COUNTRY: self.hass.config.country or "DE"}))

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


class WerktagsOptionsFlow(_Steps, OptionsFlowWithReload):
    """Same steps, prefilled; the entry reloads afterwards."""

    def __init__(self) -> None:
        self._data = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self._data:
            self._data = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            if user_input[CONF_COUNTRY] != self._data.get(CONF_COUNTRY):
                self._data[CONF_SUBDIVISION] = ""          # the old region belongs to the old country
            self._data.update(user_input)
            return await self.async_step_region()
        return self._show("init", country_schema(self._data))

    async def async_step_region(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step_region(user_input, self.async_step_school_holidays)

    async def async_step_school_holidays(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step_school_holidays(user_input, self.async_step_house)

    async def async_step_house(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._step_house(user_input, self.async_step_access)

    async def async_step_access(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="", data=self._data)
        return self._show(STEP_ACCESS, access_schema(self._data))
