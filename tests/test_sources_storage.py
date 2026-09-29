"""Public holidays from the ``holidays`` library and the store round trip — no Home Assistant."""
from __future__ import annotations

import datetime as dt

import pytest

from custom_components.werktags import sources, storage
from custom_components.werktags.rules import (
    CombineRule,
    DayType,
    History,
    Reason,
    Resident,
    Role,
    Room,
    Step,
    default_day,
)
from custom_components.werktags.sources import SchoolHolidayPeriod

d = dt.date.fromisoformat


# --- public holidays ------------------------------------------------------------

def test_public_holidays_of_a_german_state_include_regional_ones():
    table = sources.public_holidays("DE", "NW", [2026])
    assert table[d("2026-10-03")]                       # nationwide
    assert d("2026-06-04") in table                      # Corpus Christi: regional, in NW
    assert d("2026-08-15") not in table                  # Assumption Day: not in NW
    assert d("2026-12-24") not in table                  # Christmas Eve is not a public holiday (P25)


def test_public_holidays_can_be_named_in_a_language():
    german = sources.public_holidays("DE", "NW", [2026], language="de")
    english = sources.public_holidays("DE", "NW", [2026], language="en_US")
    assert german[d("2026-10-03")] != english[d("2026-10-03")]
    fallback = sources.public_holidays("DE", "NW", [2026], language="xx")   # unsupported → default names
    assert d("2026-10-03") in fallback


def test_subdivision_code_and_support():
    assert sources.subdivision_code("DE", "DE-NW") == "NW"
    assert sources.subdivision_code("DE", "NW") == "NW"
    assert sources.subdivision_code("DE", None) is None
    assert "NW" in sources.supported_subdivisions("DE")
    assert sources.supports_country("DE") and not sources.supports_country("XX")
    assert sources.supported_subdivisions("XX") == []


def test_year_span_and_build_calendar():
    assert sources.year_span(d("2026-09-29")) == (d("2025-01-01"), d("2028-12-31"))
    school = sources.school_holidays_from_periods(
        [SchoolHolidayPeriod(d("2026-10-05"), d("2026-10-16"), "Autumn")], d("2026-01-01"), d("2027-12-31"), "src")
    calendar = sources.build_calendar("DE", "DE-NW", d("2026-09-29"), school_holidays=school)
    assert default_day(Role.PUPIL, d("2026-10-06"), calendar).reason is Reason.SCHOOL_HOLIDAY
    assert default_day(Role.ADULT, d("2025-01-01"), calendar).reason is Reason.PUBLIC_HOLIDAY   # previous year kept
    assert default_day(Role.PUPIL, d("2028-05-02"), calendar).reason is Reason.UNKNOWN           # beyond known_to
    assert calendar.school_holidays.attribution == "src"


# --- storage round trip --------------------------------------------------------------

@pytest.fixture
def data() -> storage.StoredData:
    return storage.StoredData(
        residents={
            "p_anna": Resident("p_anna", "A", History((Step(d("2010-01-01"), Role.ADULT),)), 0),
            "p_clara": Resident("p_clara", "C", History((Step(d("2010-01-01"), Role.PUPIL),
                                                          Step(d("2027-08-01"), Role.ADULT))), 1),
        },
        rooms={"a_bedroom": Room("a_bedroom", History((Step(d("2010-01-01"), frozenset({"p_anna"})),
                                                        Step(d("2027-03-01"), frozenset({"p_anna", "p_clara"})))),
                                 CombineRule.WORKDAY_WINS, CombineRule.WORKDAY_WINS)},
        exceptions={d("2026-10-10"): {"p_anna": DayType.WORKDAY}, d("2026-10-20"): {"p_clara": DayType.DAY_OFF}},
        school_holidays=storage.SchoolHolidayCache(
            "openholidays", (SchoolHolidayPeriod(d("2026-10-05"), d("2026-10-16"), "Autumn"),),
            d("2026-01-01"), d("2027-12-31"), dt.datetime(2026, 9, 29, 21, 0, tzinfo=dt.UTC), 0),
    )


def test_round_trip_is_lossless(data):
    raw = storage.to_dict(data)
    assert raw["version"] == storage.DATA_VERSION
    assert storage.from_dict(raw) == data
    # JSON-compatible: only str keys and plain values
    import json
    assert storage.from_dict(json.loads(json.dumps(raw))) == data


def test_serialized_form_is_readable_and_sorted(data):
    raw = storage.to_dict(data)
    assert raw["residents"]["p_clara"]["roles"] == [
        {"valid_from": "2010-01-01", "value": "pupil"}, {"valid_from": "2027-08-01", "value": "adult"}]
    assert raw["rooms"]["a_bedroom"]["residents"][1]["value"] == ["p_anna", "p_clara"]
    assert raw["exceptions"] == {"2026-10-10": {"p_anna": "workday"}, "2026-10-20": {"p_clara": "day_off"}}
    assert raw["school_holidays"]["fetched_at"] == "2026-09-29T21:00:00+00:00"


def test_empty_and_missing_data():
    assert storage.from_dict(None) == storage.StoredData()
    assert storage.from_dict({}) == storage.StoredData()
    minimal = storage.from_dict({"version": 1, "residents": {"p": {"roles": []}}})
    assert minimal.residents["p"].short_name == "" and minimal.residents["p"].role_on(d("2026-01-01")) is None
    assert storage.from_dict({"version": 1, "exceptions": {"2026-01-01": {}}}).exceptions == {}


def test_newer_version_is_refused():
    with pytest.raises(ValueError):
        storage.from_dict({"version": storage.DATA_VERSION + 1})
