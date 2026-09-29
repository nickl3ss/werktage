"""Setup and options: country and subdivision, weekend, school holiday source, house rules."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
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
from .rules import DEFAULT_EVENING_RULE, DEFAULT_MORNING_RULE, CombineRule, Role

WEEKDAYS = ["0", "1", "2", "3", "4", "5", "6"]
OPENHOLIDAYS_COUNTRIES = {   # countries the OpenHolidays API covered on 2026-09-29
    "AD", "AL", "AT", "BE", "BG", "BY", "CH", "CZ", "DE", "EE", "ES", "FR", "HR", "HU", "IE", "IT", "LI", "LT",
    "LU", "LV", "MC", "MD", "MT", "NL", "PL", "PT", "RO", "RS", "SE", "SI", "SK", "SM", "UA", "VA",
}


def _select(options: list[str], *, multiple: bool = False, translation_key: str | None = None) -> SelectSelector:
    config = SelectSelectorConfig(options=options, multiple=multiple, mode=SelectSelectorMode.DROPDOWN)
    if translation_key:
        config["translation_key"] = translation_key
    return SelectSelector(config)


def _country_options() -> list[SelectOptionDict]:
    return [SelectOptionDict(value=code, label=code) for code in sorted(sources.supported_countries())]


def _subdivision_options(country: str) -> list[str]:
    return [""] + [f"{country}-{code}" for code in sources.supported_subdivisions(country)]


def location_schema(defaults: dict[str, Any]) -> vol.Schema:
    country = str(defaults.get(CONF_COUNTRY, "DE"))
    return vol.Schema({
        vol.Required(CONF_COUNTRY, default=country): SelectSelector(SelectSelectorConfig(
            options=_country_options(), mode=SelectSelectorMode.DROPDOWN)),
        vol.Optional(CONF_SUBDIVISION, default=defaults.get(CONF_SUBDIVISION, "")): _select(
            _subdivision_options(country)),
        vol.Required(CONF_WEEKEND, default=defaults.get(CONF_WEEKEND, DEFAULT_WEEKEND_DAYS)): _select(
            WEEKDAYS, multiple=True, translation_key="weekday"),
    })


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
        vol.Required(CONF_ADMIN_ONLY, default=defaults.get(CONF_ADMIN_ONLY, False)): BooleanSelector(),
    })


def _validate_source(user_input: dict[str, Any]) -> dict[str, str]:
    if user_input.get(CONF_SCHOOL_HOLIDAY_SOURCE) == SOURCE_CALENDAR and not user_input.get(CONF_CALENDAR_ENTITY):
        return {CONF_CALENDAR_ENTITY: "calendar_required"}
    return {}


class WerktagsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Three steps: location, school holidays, house."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        defaults = self._data or {CONF_COUNTRY: (self.hass.config.country or "DE")}
        if user_input is not None:
            self._data.update(user_input)
            if not self._data.get(CONF_SUBDIVISION):
                self._data[CONF_SUBDIVISION] = ""
            return await self.async_step_school_holidays()
        return self.async_show_form(step_id="user", data_schema=location_schema(defaults))

    async def async_step_school_holidays(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_source(user_input)
            if not errors:
                self._data.update(user_input)
                return await self.async_step_house()
        return self.async_show_form(step_id="school_holidays", errors=errors,
                                    data_schema=source_schema(self._data, str(self._data.get(CONF_COUNTRY, ""))))

    async def async_step_house(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title=NAME, data=self._data)
        return self.async_show_form(step_id="house", data_schema=house_schema(self._data))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> WerktagsOptionsFlow:
        return WerktagsOptionsFlow()


class WerktagsOptionsFlow(OptionsFlow):
    """The same three steps, prefilled with the current values."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options, **self._data}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            if not self._data.get(CONF_SUBDIVISION):
                self._data[CONF_SUBDIVISION] = ""
            return await self.async_step_school_holidays()
        return self.async_show_form(step_id="init", data_schema=location_schema(self._current()))

    async def async_step_school_holidays(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_source(user_input)
            if not errors:
                self._data.update(user_input)
                return await self.async_step_house()
        current = self._current()
        return self.async_show_form(step_id="school_holidays", errors=errors,
                                    data_schema=source_schema(current, str(current.get(CONF_COUNTRY, ""))))

    async def async_step_house(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="", data=self._current())
        return self.async_show_form(step_id="house", data_schema=house_schema(self._current()))
