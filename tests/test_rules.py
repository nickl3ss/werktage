"""Rules (docs/specification.md section 3). One test per rule, fictitious people."""
from __future__ import annotations

import datetime as dt

import pytest

from custom_components.werktage import rules
from custom_components.werktage.rules import (
    Calendar,
    CombineRule,
    DayInfo,
    DayType,
    EveningMode,
    History,
    House,
    Household,
    MorningMode,
    Reason,
    Resident,
    Role,
    Room,
    SchoolHolidays,
    Step,
    combine,
    default_day,
    effective_day,
    evening_mode,
    morning_mode,
    normalize_exception,
)

d = dt.date.fromisoformat
FOREVER = d("2010-01-01")


@pytest.fixture
def calendar() -> Calendar:
    """October 2026 in a German state: 3 Oct public holiday, autumn break 5–16 Oct."""
    return Calendar(
        public_holidays={d("2026-10-03"): "German Unity Day", d("2026-12-25"): "Christmas Day"},
        school_holidays=SchoolHolidays(
            periods=((d("2026-10-05"), d("2026-10-16"), "Autumn break"),
                     (d("2026-12-23"), d("2027-01-08"), "Christmas break"),
                     (d("2027-06-28"), d("2027-08-06"), "Summer break")),
            known_from=d("2026-01-01"), known_to=d("2027-12-31"),
        ),
    )


@pytest.fixture
def household(calendar: Calendar) -> Household:
    def roles(role: Role) -> History[Role]:
        return History((Step(FOREVER, role),))

    return Household(
        calendar=calendar,
        residents={
            "anna": Resident("anna", "A", roles(Role.ADULT), 0),
            "ben": Resident("ben", "B", roles(Role.ADULT), 1),
            "clara": Resident("clara", "C", roles(Role.PUPIL), 2),
        },
        rooms={
            "bedroom": Room("bedroom", History((Step(FOREVER, frozenset({"anna", "ben"})),))),
            "clara": Room("clara", History((Step(FOREVER, frozenset({"clara"})),))),
        },
        house=House(),
    )


# --- 3.1 default ---------------------------------------------------------------

def test_weekend_is_off_for_everyone(calendar):
    saturday = d("2026-10-10")
    for role in (Role.ADULT, Role.PUPIL):
        info = default_day(role, saturday, calendar)
        assert info.day_type is DayType.DAY_OFF and info.reason is Reason.WEEKEND


def test_public_holiday_is_off_and_names_the_holiday(calendar):
    info = default_day(Role.ADULT, d("2026-12-25"), calendar)
    assert (info.day_type, info.reason, info.holiday_name) == (
        DayType.DAY_OFF, Reason.PUBLIC_HOLIDAY, "Christmas Day")


def test_public_holiday_on_a_weekend_reports_the_holiday(calendar):
    assert default_day(Role.PUPIL, d("2026-10-03"), calendar).reason is Reason.PUBLIC_HOLIDAY   # a Saturday


def test_school_holidays_only_for_pupils(calendar):
    monday = d("2026-10-05")
    assert default_day(Role.PUPIL, monday, calendar) == DayInfo(
        DayType.DAY_OFF, Reason.SCHOOL_HOLIDAY, "Autumn break", Role.PUPIL)
    assert default_day(Role.ADULT, monday, calendar) == DayInfo(DayType.WORKDAY, Reason.WORKDAY, None, Role.ADULT)


def test_ordinary_weekday_is_a_workday(calendar):
    assert default_day(Role.PUPIL, d("2026-10-20"), calendar).reason is Reason.WORKDAY


def test_christmas_eve_is_a_workday_for_adults(calendar):
    """P25: 24 December is a workday unless the subdivision lists it as a public holiday."""
    assert default_day(Role.ADULT, d("2026-12-24"), calendar).is_workday


# --- 3.2 exceptions and unknown days -------------------------------------------

def test_exception_overrides_default_in_both_directions(calendar):
    saturday, tuesday = d("2026-10-10"), d("2026-10-20")
    work = effective_day(Role.ADULT, saturday, calendar, DayType.WORKDAY)
    off = effective_day(Role.ADULT, tuesday, calendar, DayType.DAY_OFF)
    assert (work.day_type, work.reason) == (DayType.WORKDAY, Reason.EXCEPTION_WORKDAY)
    assert (off.day_type, off.reason) == (DayType.DAY_OFF, Reason.EXCEPTION_DAY_OFF)


def test_exception_keeps_the_holiday_name(calendar):
    info = effective_day(Role.PUPIL, d("2026-10-05"), calendar, DayType.WORKDAY)
    assert info.holiday_name == "Autumn break" and info.is_workday


def test_unknown_school_holidays_count_as_workday_with_reason_unknown(calendar):
    """P5: a pupil's day outside the known range is a workday, flagged unknown."""
    info = default_day(Role.PUPIL, d("2028-03-06"), calendar)
    assert info.is_workday and info.reason is Reason.UNKNOWN and not info.is_known
    # weekends and public holidays are known regardless of the school holiday source
    assert default_day(Role.PUPIL, d("2028-03-04"), calendar).reason is Reason.WEEKEND


def test_source_none_means_pupils_have_no_school_holidays():
    calendar = Calendar(school_holidays=SchoolHolidays())
    info = default_day(Role.PUPIL, d("2030-07-15"), calendar)
    assert info.is_workday and info.is_known


def test_normalize_exception_drops_what_equals_the_default(calendar):
    assert normalize_exception(Role.ADULT, d("2026-10-10"), calendar, DayType.DAY_OFF) is None      # Saturday
    assert normalize_exception(Role.ADULT, d("2026-10-10"), calendar, DayType.WORKDAY) is DayType.WORKDAY
    assert normalize_exception(Role.PUPIL, d("2026-10-05"), calendar, DayType.DAY_OFF) is None      # school holiday
    assert normalize_exception(Role.ADULT, d("2026-10-05"), calendar, DayType.DAY_OFF) is DayType.DAY_OFF
    assert normalize_exception(Role.ADULT, d("2026-10-05"), calendar, None) is None


# --- 3.3 modes ---------------------------------------------------------------------

def test_modes_follow_the_day_type():
    work = DayInfo(DayType.WORKDAY, Reason.WORKDAY)
    off = DayInfo(DayType.DAY_OFF, Reason.WEEKEND)
    assert (morning_mode(work), morning_mode(off)) == (MorningMode.WORKDAY, MorningMode.DAY_OFF)
    assert (evening_mode(work), evening_mode(off)) == (EveningMode.BEFORE_WORKDAY, EveningMode.BEFORE_DAY_OFF)


@pytest.mark.parametrize("anna, ben, morning, evening", [
    ("workday", "workday", "workday", "before_workday"),
    ("day_off", "workday", "day_off", "before_workday"),
    ("day_off", "day_off", "day_off", "before_day_off"),
])
def test_room_rules_table_from_section_3_3(anna, ben, morning, evening):
    days = [DayInfo(DayType(anna), Reason.WORKDAY), DayInfo(DayType(ben), Reason.WORKDAY)]
    assert combine(days, CombineRule.DAY_OFF_WINS).day_type.value == morning
    assert evening_mode(combine(days, CombineRule.WORKDAY_WINS)).value == evening


def test_combine_without_residents_is_unknown_and_a_workday():
    info = combine([], CombineRule.DAY_OFF_WINS)
    assert info.is_workday and info.reason is Reason.UNKNOWN


def test_combine_keeps_the_reason_of_the_deciding_resident():
    days = [DayInfo(DayType.WORKDAY, Reason.WORKDAY), DayInfo(DayType.DAY_OFF, Reason.PUBLIC_HOLIDAY, "Easter Monday")]
    assert combine(days, CombineRule.DAY_OFF_WINS).holiday_name == "Easter Monday"


# --- 3.4 history ---------------------------------------------------------------------

def test_history_uses_the_step_valid_on_the_day():
    h = History((Step(d("2010-01-01"), Role.PUPIL), Step(d("2027-08-01"), Role.ADULT)))
    assert h.value_on(d("2009-06-01")) is None
    assert h.value_on(d("2027-07-31")) is Role.PUPIL
    assert h.value_on(d("2027-08-01")) is Role.ADULT


def test_history_add_replace_remove():
    h = History((Step(d("2010-01-01"), Role.PUPIL),))
    h2 = h.with_step(d("2027-08-01"), Role.ADULT).with_step(d("2027-08-01"), Role.NONE)
    assert [s.value for s in h2.steps] == [Role.PUPIL, Role.NONE]
    assert h2.without_step(d("2027-08-01")) == h
    with pytest.raises(ValueError):
        History((Step(d("2020-01-01"), 1), Step(d("2019-01-01"), 2)))


def test_role_none_ends_membership_without_touching_the_past(household):
    clara = household.residents["clara"]
    left = Resident("clara", "C", clara.roles.with_step(d("2026-11-01"), Role.NONE))
    h = Household(household.calendar, {**household.residents, "clara": left}, household.rooms)
    assert h.day_of("clara", d("2026-10-20")) is not None
    assert h.day_of("clara", d("2026-11-02")) is None
    assert household.room_day("clara", d("2026-11-02")).reason is not Reason.UNKNOWN
    assert h.room_day("clara", d("2026-11-02")).reason is Reason.UNKNOWN


def test_role_change_applies_from_its_date_and_the_house_follows(household):
    """A pupil who becomes an adult on 1 Aug counts for the house from that day."""
    clara = household.residents["clara"]
    grown = Resident("clara", "C", clara.roles.with_step(d("2027-08-01"), Role.ADULT))
    h = Household(household.calendar, {**household.residents, "clara": grown}, household.rooms)
    assert h.day_of("clara", d("2027-07-30")).reason is Reason.SCHOOL_HOLIDAY      # summer break still counts
    assert h.house_residents_on(d("2027-07-31")) == ["anna", "ben"]
    assert h.house_residents_on(d("2027-08-01")) == ["anna", "ben", "clara"]


def test_room_assignment_has_a_history(household):
    """Ben moves into Clara's room on 1 March; February is unchanged."""
    room = household.rooms["clara"]
    moved = Room("clara", room.residents.with_step(d("2027-03-01"), frozenset({"clara", "ben"})))
    h = Household(household.calendar, household.residents, {**household.rooms, "clara": moved},
                  exceptions={d("2027-02-15"): {"ben": DayType.DAY_OFF}, d("2027-03-15"): {"ben": DayType.DAY_OFF}})
    assert h.room_day("clara", d("2027-02-15")).is_workday        # Ben not yet there
    assert not h.room_day("clara", d("2027-03-15")).is_workday    # Ben's day off wins in the morning


# --- household lookups -------------------------------------------------------------------

def test_household_modes_for_person_room_and_house(household):
    friday = d("2026-10-02")   # Friday before the public holiday on Saturday
    assert household.resident_modes("anna", friday) == (MorningMode.WORKDAY, EveningMode.BEFORE_DAY_OFF)
    assert household.room_modes("bedroom", friday) == (MorningMode.WORKDAY, EveningMode.BEFORE_DAY_OFF)
    assert household.house_modes(friday) == (MorningMode.WORKDAY, EveningMode.BEFORE_DAY_OFF)
    assert household.resident_modes("nobody", friday) is None


def test_house_workday_wins_rule(household):
    """H11-style house: one adult working in the morning makes it a workday."""
    h = Household(household.calendar, household.residents, household.rooms,
                  House(morning_rule=CombineRule.WORKDAY_WINS),
                  exceptions={d("2026-10-20"): {"anna": DayType.DAY_OFF}})
    assert h.house_modes(d("2026-10-20"))[0] is MorningMode.WORKDAY
    assert household.house_modes(d("2026-10-20"))[0] is MorningMode.WORKDAY   # default: nobody off
    default_off = Household(household.calendar, household.residents, household.rooms, House(),
                            exceptions={d("2026-10-20"): {"anna": DayType.DAY_OFF}})
    assert default_off.house_modes(d("2026-10-20"))[0] is MorningMode.DAY_OFF


def test_house_ignores_pupils_by_default(household):
    assert household.house_residents_on(d("2026-10-20")) == ["anna", "ben"]
    assert household.house_day(d("2026-10-05")).is_workday          # autumn break is Clara's only


def test_next_workday_and_next_day_off(household):
    thursday = d("2026-10-01")
    assert household.next_day("anna", thursday, workday=False) == d("2026-10-03")   # public holiday
    assert household.next_day("anna", d("2026-10-02"), workday=True) == d("2026-10-05")
    assert household.next_day("clara", d("2026-10-02"), workday=True) == d("2026-10-19")   # after the break
    empty = Household(household.calendar, {"x": Resident("x", "X")})
    assert empty.next_day("x", thursday, workday=True) is None


def test_next_day_is_scanned_once_per_household_and_question(household, monkeypatch):
    thursday = d("2026-10-01")
    first = household.next_day("anna", thursday, workday=True)
    monkeypatch.setattr(Household, "_scan_next_day", lambda *_: pytest.fail("scanned again"))
    assert household.next_day("anna", thursday, workday=True) == first == d("2026-10-02")
    assert household.next_day("anna", thursday, workday=True) is first
    with pytest.raises(pytest.fail.Exception):            # a different question is a different scan
        household.next_day("anna", d("2026-10-02"), workday=True)


def test_midnight_boundary_evening_looks_at_the_next_calendar_day(household):
    """P6: at 00:30 on Saturday the evening mode already refers to Sunday."""
    assert household.resident_modes("anna", d("2026-10-09"))[1] is EveningMode.BEFORE_DAY_OFF   # Fri → Sat
    assert household.resident_modes("anna", d("2026-10-11"))[1] is EveningMode.BEFORE_WORKDAY   # Sun → Mon


# --- changing exceptions -----------------------------------------------------------

def test_with_exceptions_over_a_range_including_the_weekend(household):
    h = household.with_exceptions(["anna"], d("2026-10-09"), d("2026-10-12"), DayType.WORKDAY)
    assert h.exception_for("anna", d("2026-10-09")) is None                 # Friday: default already workday
    assert h.exception_for("anna", d("2026-10-10")) is DayType.WORKDAY      # Saturday (P20: every day)
    assert h.exception_for("anna", d("2026-10-11")) is DayType.WORKDAY
    assert h.exception_for("anna", d("2026-10-12")) is None
    assert household.exceptions == {}                                       # the original is untouched


def test_with_exceptions_default_clears_and_removes_empty_days(household):
    h = household.with_exceptions(["anna", "ben"], d("2026-10-20"), d("2026-10-21"), DayType.DAY_OFF)
    assert set(h.exceptions[d("2026-10-20")]) == {"anna", "ben"}
    cleared = h.with_exceptions(["anna", "ben"], d("2026-10-20"), d("2026-10-21"), None)
    assert cleared.exceptions == {}


def test_with_exceptions_skips_residents_without_a_role(household):
    h = household.with_exceptions(["clara"], d("2009-05-04"), d("2009-05-04"), DayType.DAY_OFF)
    assert h.exceptions == {}


def test_changes_for_counts_only_real_changes(household):
    counts = household.changes_for(["anna", "clara"], d("2026-10-05"), d("2026-10-11"), DayType.DAY_OFF)
    assert counts == {"anna": 5, "clara": 0}    # Clara already has the autumn break; Anna: Mon–Fri
    with pytest.raises(ValueError):
        household.with_exceptions(["anna"], d("2026-10-11"), d("2026-10-10"), DayType.DAY_OFF)


def test_exceptions_survive_a_role_change(household):
    """P26: exceptions belong to person and day, not to the role."""
    h = household.with_exceptions(["clara"], d("2027-09-06"), d("2027-09-06"), DayType.DAY_OFF)
    grown = Resident("clara", "C", h.residents["clara"].roles.with_step(d("2027-08-01"), Role.ADULT))
    h2 = Household(h.calendar, {**h.residents, "clara": grown}, h.rooms, exceptions=h.exceptions)
    assert h2.day_of("clara", d("2027-09-06")).reason is Reason.EXCEPTION_DAY_OFF


def test_year_boundary_inside_the_christmas_break(household):
    assert household.day_of("clara", d("2026-12-31")).reason is Reason.SCHOOL_HOLIDAY
    assert household.day_of("clara", d("2027-01-04")).reason is Reason.SCHOOL_HOLIDAY
    assert household.day_of("clara", d("2027-01-11")).reason is Reason.WORKDAY


def test_public_api_names_are_english():
    """P16: every enum value is an English key."""
    for enum in (Role, DayType, Reason, MorningMode, EveningMode, CombineRule):
        for member in enum:
            assert member.value.isascii() and member.value == member.value.lower()
    assert frozenset({5, 6}) == rules.DEFAULT_WEEKEND


# --- personal weekly days off, house residents, holiday corrections ------------------------

def test_personal_off_weekdays_override_the_household_weekend(household):
    """Ben works Monday to Thursday: Friday is his day off, Saturday and Sunday still are."""
    ben = household.residents["ben"]
    part_time = Resident("ben", "B", ben.roles, ben.order, History((Step(d("2026-10-01"), frozenset({4, 5, 6})),)))
    h = Household(household.calendar, {**household.residents, "ben": part_time}, household.rooms)
    assert h.day_of("ben", d("2026-10-02")).reason is Reason.WEEKEND         # Friday after the change
    assert h.day_of("ben", d("2026-09-25")).is_workday                       # Friday before the change
    assert h.day_of("anna", d("2026-10-02")).is_workday                      # Anna keeps the household weekend
    assert h.room_modes("bedroom", d("2026-10-02"))[0] is MorningMode.DAY_OFF   # day_off_wins with Ben off
    # a workday exception on Ben's Friday is stored; a day-off exception equals his default and is not
    h2 = h.with_exceptions(["ben"], d("2026-10-09"), d("2026-10-09"), DayType.DAY_OFF)
    assert h2.exceptions == {}
    h3 = h.with_exceptions(["ben"], d("2026-10-09"), d("2026-10-09"), DayType.WORKDAY)
    assert h3.day_of("ben", d("2026-10-09")).reason is Reason.EXCEPTION_WORKDAY


def test_house_uses_assigned_residents_when_there_is_an_assignment(household):
    """Without an assignment the house follows the roles; with one, exactly the assigned residents count."""
    assert household.house_residents_on(d("2026-10-20")) == ["anna", "ben"]
    house = House(residents=History((Step(d("2026-10-01"), frozenset({"anna", "clara"})),)))
    h = Household(household.calendar, household.residents, household.rooms, house)
    assert h.house_residents_on(d("2026-09-30")) == ["anna", "ben"]          # before the assignment: roles
    assert h.house_residents_on(d("2026-10-20")) == ["anna", "clara"]
    assert h.house_day(d("2026-10-05")).reason is Reason.SCHOOL_HOLIDAY       # Clara's autumn break now counts
    gone = House(residents=History((Step(d("2026-10-01"), frozenset({"anna", "nobody"})),)))
    assert Household(household.calendar, household.residents, household.rooms, gone).house_residents_on(d("2026-10-20")) == ["anna"]


def test_holiday_corrections(calendar):
    """A company holiday is added, an official holiday removed."""
    corrected = Calendar(calendar.public_holidays, calendar.school_holidays, calendar.weekend,
                         extra_holidays={d("2026-10-20"): "Company holiday"}, removed_holidays=frozenset({d("2026-12-25")}))
    added = default_day(Role.ADULT, d("2026-10-20"), corrected)
    assert (added.day_type, added.reason, added.holiday_name) == (DayType.DAY_OFF, Reason.PUBLIC_HOLIDAY, "Company holiday")
    assert default_day(Role.ADULT, d("2026-12-25"), corrected).is_workday       # a Friday, holiday removed
    assert default_day(Role.ADULT, d("2026-10-03"), corrected).reason is Reason.PUBLIC_HOLIDAY   # untouched
