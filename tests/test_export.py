"""Export planning (#3): pure functions in export.py."""
from __future__ import annotations

from custom_components.werktage import export
from custom_components.werktage.rules import Reason

from .conftest import d
from .test_rules import calendar, household  # noqa: F401 — the pure household (Anna, Ben, Clara; October 2026)


def test_key_and_description_round_trip():
    event = export.WantedEvent("p_anna/2026-10-07", d("2026-10-07"), "Anna: Day off")
    assert event.description == "werktage:p_anna/2026-10-07"
    assert export.key_of(event.description) == "p_anna/2026-10-07"
    assert export.key_of("Dentist at 9") is None and export.key_of(None) is None and export.key_of("werktage:") is None


def test_plan_creates_missing_deletes_stale_and_replaces_renamed():
    wanted = {
        "a/2026-10-07": export.WantedEvent("a/2026-10-07", d("2026-10-07"), "Anna: Day off"),
        "a/2026-10-08": export.WantedEvent("a/2026-10-08", d("2026-10-08"), "Anna: Day off"),
        "c/2026-10-05": export.WantedEvent("c/2026-10-05", d("2026-10-05"), "Clara: Autumn Holidays"),
    }
    existing = [
        export.OwnEvent("u1", "a/2026-10-07", "Anna: Day off"),          # still true: kept
        export.OwnEvent("u2", "a/2026-10-09", "Anna: Day off"),          # no longer true: deleted
        export.OwnEvent("u3", "c/2026-10-05", "Clara: Herbstferien"),    # renamed: deleted and created again
        export.OwnEvent("u4", "a/2026-10-07", "Anna: Day off"),          # duplicate of u1: deleted
    ]
    to_create, to_delete = export.plan(wanted, existing)
    assert [e.key for e in to_create] == ["a/2026-10-08", "c/2026-10-05"]
    assert [e.uid for e in to_delete] == ["u2", "u3", "u4"]
    assert export.plan({}, []) == ([], [])


def test_wanted_events_skip_weekends_unknown_days_and_workdays(household):   # noqa: F811
    names = {"anna": "Anna", "clara": "Clara"}
    wanted = export.wanted_events(household, ["anna", "clara"], names, d("2026-10-01"), d("2026-10-07"), False, "de")
    anna, clara = export.person_key("anna"), export.person_key("clara")
    assert wanted[f"{anna}/2026-10-03"].summary == "Anna: German Unity Day"
    assert f"{anna}/2026-10-04" not in wanted                                    # Sunday: weekends not wanted
    assert wanted[f"{clara}/2026-10-05"].summary == "Clara: Autumn break"       # school holidays by name
    assert f"{anna}/2026-10-05" not in wanted                                    # a workday
    assert "anna" not in str(wanted) and len(anna) == 12                         # the person id stays at home
    with_weekends = export.wanted_events(household, ["anna"], names, d("2026-10-01"), d("2026-10-07"), True, "en")
    assert with_weekends[f"{anna}/2026-10-04"].summary == "Anna: Weekend"
    # a personal weekly day off (Friday, P29) is always exported; the household weekend only on request
    from dataclasses import replace

    from custom_components.werktage.rules import History, Step
    part_time = replace(household.residents["anna"], off_weekdays=History((Step(d("2026-01-01"), frozenset({4, 5, 6})),)))
    h = replace(household, residents={**household.residents, "anna": part_time})
    wanted = export.wanted_events(h, ["anna"], names, d("2026-10-01"), d("2026-10-07"), False, "en")
    assert wanted[f"{anna}/2026-10-02"].summary == "Anna: Weekend" and f"{anna}/2026-10-04" not in wanted
    assert export.reason_label(Reason.EXCEPTION_DAY_OFF, "de-DE") == "Frei"
    assert export.reason_label(Reason.CALENDAR_DAY_OFF, None) == "Day off"
