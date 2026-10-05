"""Constants of the Werktags integration."""
from __future__ import annotations

DOMAIN = "werktage"
NAME = "Werktags"
VERSION = "0.2.0"  # must match manifest.json, see test_quality
USER_AGENT = f"{DOMAIN}/{VERSION} (+https://github.com/nickl3ss/werktage)"

# Config entry / options keys
CONF_COUNTRY = "country"
CONF_SUBDIVISION = "subdivision"
CONF_WEEKEND = "weekend"
CONF_SCHOOL_HOLIDAY_SOURCE = "school_holiday_source"
CONF_CALENDAR_ENTITY = "calendar_entity"
CONF_HOUSE_ROLES = "house_roles"
CONF_HOUSE_MORNING_RULE = "house_morning_rule"
CONF_HOUSE_EVENING_RULE = "house_evening_rule"
CONF_ADMIN_ONLY = "admin_only"
CONF_ADD_HOLIDAYS = "add_holidays"        # ["2026-10-20", "2026-12-24 Christmas Eve"]
CONF_REMOVE_HOLIDAYS = "remove_holidays"  # ["2026-06-04", "Corpus"] (date or part of a name)

DEFAULT_WEEKEND_DAYS = ["5", "6"]          # Saturday, Sunday as date.weekday() strings (selector values)

SOURCE_OPENHOLIDAYS = "openholidays"
SOURCE_CALENDAR = "calendar"
SOURCE_NONE = "none"
SOURCES = [SOURCE_OPENHOLIDAYS, SOURCE_CALENDAR, SOURCE_NONE]

FETCH_INTERVAL_DAYS = 30
MAX_FETCH_FAILURES = 3

# Attribution required by the ODbL 1.0 license of the OpenHolidays data (see NOTICE)
ATTRIBUTION_OPENHOLIDAYS = "School holidays: OpenHolidays API (openholidaysapi.org), ODbL 1.0"

# Repair issues
ISSUE_SCHOOL_HOLIDAYS_UNREACHABLE = "school_holidays_unreachable"
ISSUE_SCHOOL_HOLIDAYS_INCOMPLETE = "school_holidays_incomplete"
ISSUE_PERSON_MISSING = "person_missing"
ISSUE_AREA_MISSING = "area_missing"

# Services
SERVICE_SET_DAYS = "set_days"
SERVICE_SET_ROLE = "set_role"
SERVICE_REMOVE_ROLE = "remove_role"
SERVICE_SET_ROOM = "set_room"
SERVICE_REMOVE_ROOM_ASSIGNMENT = "remove_room_assignment"
SERVICE_SET_ORDER = "set_order"
SERVICE_SET_WEEKLY = "set_weekly"
SERVICE_SET_HOUSE = "set_house"
SERVICE_GET_DAYS = "get_days"
SERVICE_PREVIEW_DAYS = "preview_days"
SERVICE_GET_OVERVIEW = "get_overview"
SERVICE_REFRESH_SCHOOL_HOLIDAYS = "refresh_school_holidays"

STATUS_DEFAULT = "default"                  # service field value: clear exceptions

HOUSE_ID = "house"
