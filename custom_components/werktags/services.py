"""Services: write (set/remove) and read (get/preview, with response).

Registered once in ``async_setup``; they need the single config entry to be
loaded. Every write checks the *administrators only* option.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Coroutine
from typing import Any, cast

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_GET_DAYS,
    SERVICE_GET_OVERVIEW,
    SERVICE_PREVIEW_DAYS,
    SERVICE_REFRESH_SCHOOL_HOLIDAYS,
    SERVICE_REMOVE_ROLE,
    SERVICE_REMOVE_ROOM_ASSIGNMENT,
    SERVICE_SET_DAYS,
    SERVICE_SET_ORDER,
    SERVICE_SET_ROLE,
    SERVICE_SET_ROOM,
    STATUS_DEFAULT,
)
from .coordinator import WerktagsCoordinator
from .rules import ONE_DAY, CombineRule, DayType, Role

MAX_RANGE_DAYS = 366
MAX_WEEKS = 26

PERSONS = vol.All(cv.ensure_list, [cv.entity_domain("person")])
STATUS = vol.In([DayType.DAY_OFF.value, DayType.WORKDAY.value, STATUS_DEFAULT])
RULE = vol.In([r.value for r in CombineRule])

SET_DAYS_SCHEMA = vol.Schema({
    vol.Required("person"): PERSONS, vol.Required("start"): cv.date, vol.Optional("end"): cv.date,
    vol.Required("status"): STATUS,
})
SET_ROLE_SCHEMA = vol.Schema({
    vol.Required("person"): cv.entity_domain("person"), vol.Required("role"): vol.In([r.value for r in Role]),
    vol.Optional("valid_from"): cv.date, vol.Optional("short_name"): cv.string,
})
REMOVE_ROLE_SCHEMA = vol.Schema({
    vol.Required("person"): cv.entity_domain("person"), vol.Required("valid_from"): cv.date,
})
SET_ROOM_SCHEMA = vol.Schema({
    vol.Required("area"): cv.string, vol.Optional("person"): PERSONS, vol.Optional("valid_from"): cv.date,
    vol.Optional("morning_rule"): RULE, vol.Optional("evening_rule"): RULE,
})
REMOVE_ROOM_SCHEMA = vol.Schema({vol.Required("area"): cv.string, vol.Required("valid_from"): cv.date})
SET_ORDER_SCHEMA = vol.Schema({vol.Required("person"): PERSONS})
GET_DAYS_SCHEMA = vol.Schema({
    vol.Optional("start"): cv.date, vol.Optional("weeks", default=5): vol.All(int, vol.Range(1, MAX_WEEKS)),
})
EMPTY_SCHEMA = vol.Schema({})


def _coordinator(hass: HomeAssistant) -> WerktagsCoordinator:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
    coordinator: WerktagsCoordinator = entries[0].runtime_data
    return coordinator


async def _check_permission(hass: HomeAssistant, coordinator: WerktagsCoordinator, call: ServiceCall) -> None:
    if not coordinator.admin_only or call.context.user_id is None:
        return
    user = await hass.auth.async_get_user(call.context.user_id)
    if user is None or not user.is_admin:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="admin_only")


def _person_ids(coordinator: WerktagsCoordinator, entity_ids: list[str]) -> list[str]:
    try:
        return [coordinator.person_id_of(e) for e in entity_ids]
    except ValueError as err:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="unknown_person",
                                     translation_placeholders={"entity_id": str(err).split()[-1]}) from err


def _range(call: ServiceCall) -> tuple[dt.date, dt.date]:
    start: dt.date = call.data["start"]
    end: dt.date = call.data.get("end", start)
    if end < start:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="end_before_start")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="range_too_long",
                                     translation_placeholders={"max": str(MAX_RANGE_DAYS)})
    return start, end


def _status(value: str) -> DayType | None:
    return None if value == STATUS_DEFAULT else DayType(value)


type Handler = Callable[[HomeAssistant, WerktagsCoordinator, ServiceCall], Coroutine[Any, Any, dict[str, Any] | None]]


type Registered = Callable[[ServiceCall], Coroutine[Any, Any, ServiceResponse]]


def _wrap(func: Handler, hass: HomeAssistant, *, write: bool) -> Registered:
    async def handler(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass)
        if write:
            await _check_permission(hass, coordinator, call)
        try:
            return cast(ServiceResponse, await func(hass, coordinator, call))
        except ValueError as err:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="invalid",
                                         translation_placeholders={"message": str(err)}) from err
    return handler


# --- write services ------------------------------------------------------------------

async def _set_days(hass: HomeAssistant, c: WerktagsCoordinator, call: ServiceCall) -> dict[str, Any] | None:
    start, end = _range(call)
    await c.async_set_days(_person_ids(c, call.data["person"]), start, end, _status(call.data["status"]))
    return None


async def _set_role(hass: HomeAssistant, c: WerktagsCoordinator, call: ServiceCall) -> dict[str, Any] | None:
    person_id = _person_ids(c, [call.data["person"]])[0]
    await c.async_set_role(person_id, Role(call.data["role"]), call.data.get("valid_from", c.today()),
                           call.data.get("short_name"))
    return None


async def _remove_role(hass: HomeAssistant, c: WerktagsCoordinator, call: ServiceCall) -> dict[str, Any] | None:
    await c.async_remove_role(_person_ids(c, [call.data["person"]])[0], call.data["valid_from"])
    return None


async def _set_room(hass: HomeAssistant, c: WerktagsCoordinator, call: ServiceCall) -> dict[str, Any] | None:
    persons = _person_ids(c, call.data["person"]) if "person" in call.data else None
    valid_from = call.data.get("valid_from", c.today()) if persons is not None else None
    morning = CombineRule(call.data["morning_rule"]) if "morning_rule" in call.data else None
    evening = CombineRule(call.data["evening_rule"]) if "evening_rule" in call.data else None
    await c.async_set_room(call.data["area"], persons, valid_from, morning, evening)
    return None


async def _remove_room(hass: HomeAssistant, c: WerktagsCoordinator, call: ServiceCall) -> dict[str, Any] | None:
    await c.async_remove_room_assignment(call.data["area"], call.data["valid_from"])
    return None


async def _set_order(hass: HomeAssistant, c: WerktagsCoordinator, call: ServiceCall) -> dict[str, Any] | None:
    await c.async_set_order(_person_ids(c, call.data["person"]))
    return None


async def _refresh(hass: HomeAssistant, c: WerktagsCoordinator, call: ServiceCall) -> dict[str, Any] | None:
    await c.async_refresh_school_holidays(force=True)
    return None


# --- read services -------------------------------------------------------------------

def _monday_of(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


async def _get_days(hass: HomeAssistant, c: WerktagsCoordinator, call: ServiceCall) -> dict[str, Any] | None:
    start = _monday_of(call.data.get("start", c.today()))
    end = start + dt.timedelta(weeks=int(call.data["weeks"])) - ONE_DAY
    household = c.household
    residents = sorted(c.data.residents.values(), key=lambda r: (r.order, r.short_name))
    days = []
    day = start
    while day <= end:
        per_person = {}
        for r in residents:
            info = household.day_of(r.id, day)
            if info is None:
                continue
            default = household.default_of(r.id, day)
            exception = household.exception_for(r.id, day)
            per_person[r.id] = {
                "effective": info.day_type.value, "default": default.day_type.value if default else None,
                "exception": exception.value if exception else None, "reason": info.reason.value,
                "holiday_name": info.holiday_name, "role": info.role.value if info.role else None,
            }
        public = household.calendar.public_holidays.get(day)
        days.append({"date": day.isoformat(), "weekend": day.weekday() in household.calendar.weekend,
                     "public_holiday": public, "school_holiday": household.calendar.school_holidays.name_on(day),
                     "persons": per_person})
        day += ONE_DAY
    return {
        "start": start.isoformat(), "end": end.isoformat(), "today": c.today().isoformat(),
        "residents": [{"id": r.id, "name": c.person_name(r.id), "short_name": r.short_name,
                       "entity_id": c.person_entity_id(r.id)} for r in residents],
        "days": days,
    }


async def _preview_days(hass: HomeAssistant, c: WerktagsCoordinator, call: ServiceCall) -> dict[str, Any] | None:
    start, end = _range(call)
    ids = _person_ids(c, call.data["person"])
    changes = c.household.changes_for(ids, start, end, _status(call.data["status"]))
    return {"changes": [{"id": pid, "name": c.person_name(pid), "days": n} for pid, n in changes.items()]}


async def _get_overview(hass: HomeAssistant, c: WerktagsCoordinator, call: ServiceCall) -> dict[str, Any] | None:
    today = c.today()
    persons = []
    for person_id, entity_id, name in c.all_persons():
        resident = c.data.residents.get(person_id)
        persons.append({
            "id": person_id, "entity_id": entity_id, "name": name,
            "short_name": resident.short_name if resident else None, "order": resident.order if resident else None,
            "role_today": (resident.role_on(today) or Role.NONE).value if resident else None,
            "roles": [{"valid_from": s.valid_from.isoformat(), "role": s.value.value} for s in resident.roles.steps]
            if resident else [],
        })
    rooms = []
    for area_id, name in c.all_areas():
        room = c.data.rooms.get(area_id)
        rooms.append({
            "id": area_id, "name": name,
            "residents_today": sorted(room.residents_on(today)) if room else [],
            "morning_rule": room.morning_rule.value if room else None,
            "evening_rule": room.evening_rule.value if room else None,
            "assignments": [{"valid_from": s.valid_from.isoformat(), "residents": sorted(s.value)}
                            for s in room.residents.steps] if room else [],
        })
    return {"today": today.isoformat(), "persons": persons, "rooms": rooms,
            "house": {"roles": sorted(r.value for r in c.house.roles),
                      "residents_today": c.household.house_residents_on(today),
                      "morning_rule": c.house.morning_rule.value, "evening_rule": c.house.evening_rule.value},
            "status": c.status()}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    writes = [
        (SERVICE_SET_DAYS, _set_days, SET_DAYS_SCHEMA), (SERVICE_SET_ROLE, _set_role, SET_ROLE_SCHEMA),
        (SERVICE_REMOVE_ROLE, _remove_role, REMOVE_ROLE_SCHEMA), (SERVICE_SET_ROOM, _set_room, SET_ROOM_SCHEMA),
        (SERVICE_REMOVE_ROOM_ASSIGNMENT, _remove_room, REMOVE_ROOM_SCHEMA),
        (SERVICE_SET_ORDER, _set_order, SET_ORDER_SCHEMA),
        (SERVICE_REFRESH_SCHOOL_HOLIDAYS, _refresh, EMPTY_SCHEMA),
    ]
    for name, func, schema in writes:
        hass.services.async_register(DOMAIN, name, _wrap(func, hass, write=True), schema=schema)
    reads = [
        (SERVICE_GET_DAYS, _get_days, GET_DAYS_SCHEMA), (SERVICE_PREVIEW_DAYS, _preview_days, SET_DAYS_SCHEMA),
        (SERVICE_GET_OVERVIEW, _get_overview, EMPTY_SCHEMA),
    ]
    for name, func, schema in reads:
        hass.services.async_register(DOMAIN, name, _wrap(func, hass, write=False), schema=schema,
                                     supports_response=SupportsResponse.ONLY)
