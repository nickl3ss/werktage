"""Constants of the Werktags integration."""
from __future__ import annotations

DOMAIN = "werktags"
NAME = "Werktags"

STORAGE_KEY = f"{DOMAIN}.data"
STORAGE_VERSION = 1

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

SOURCE_OPENHOLIDAYS = "openholidays"
SOURCE_CALENDAR = "calendar"
SOURCE_NONE = "none"

# Attribution required by the ODbL 1.0 license of the OpenHolidays data (see NOTICE)
ATTRIBUTION_OPENHOLIDAYS = "School holidays: OpenHolidays API (openholidaysapi.org), ODbL 1.0"
