"""Parsing and plausibility, offline. The fixture mimics the API's shape with made-up data."""
from __future__ import annotations

import datetime as dt

import pytest
from openholidays import Holiday, InvalidResponse, is_plausible, parse_countries, parse_holidays, parse_subdivisions

d = dt.date.fromisoformat

FIXTURE = [
    {"id": "b1", "startDate": "2031-10-06", "endDate": "2031-10-17", "type": "School",
     "name": [{"language": "DE", "text": "Herbstferien"}, {"language": "EN", "text": "Autumn Holidays"}],
     "regionalScope": "Regional", "temporalScope": "FullDay", "nationwide": False,
     "subdivisions": [{"code": "XX-AA", "shortName": "AA"}]},
    {"id": "a1", "startDate": "2031-06-30", "endDate": "2031-08-08", "type": "School",
     "name": [{"language": "DE", "text": "Sommerferien"}, {"language": "EN", "text": "Summer Holidays"}],
     "nationwide": False, "subdivisions": [{"code": "XX-AA", "shortName": "AA"}]},
    {"id": "p1", "startDate": "2031-01-01", "endDate": "2031-01-01", "type": "Public",
     "name": [{"language": "EN", "text": "New Year's Day"}], "nationwide": True, "subdivisions": []},
]


def test_parse_holidays_sorts_and_maps_fields():
    holidays = parse_holidays(FIXTURE)
    assert [h.id for h in holidays] == ["p1", "a1", "b1"]
    autumn = holidays[2]
    assert (autumn.start, autumn.end, autumn.days) == (d("2031-10-06"), d("2031-10-17"), 12)
    assert autumn.type == "School" and not autumn.nationwide and autumn.subdivisions == ("XX-AA",)
    assert autumn.name("DE") == "Herbstferien"
    assert autumn.name("FR") == "Autumn Holidays"          # falls back to English
    assert autumn.name() == "Autumn Holidays"
    assert autumn.covers(d("2031-10-10")) and not autumn.covers(d("2031-10-18"))
    assert holidays[0].nationwide and holidays[0].subdivisions == ()


def test_parse_holidays_falls_back_to_first_name_without_english():
    holiday = parse_holidays([{"startDate": "2031-05-01", "endDate": "2031-05-01",
                               "name": [{"language": "DE", "text": "Tag der Arbeit"}]}])[0]
    assert holiday.name("EN") == "Tag der Arbeit" and holiday.id == ""


@pytest.mark.parametrize("broken", [
    {"not": "a list"},
    ["not an object"],
    [{"startDate": "2031-01-01", "name": []}],                                       # missing endDate
    [{"startDate": "2031-13-01", "endDate": "2031-01-02", "name": []}],              # bad date
    [{"startDate": "2031-01-05", "endDate": "2031-01-02", "name": []}],              # end before start
    [{"startDate": "2031-01-01", "endDate": "2031-01-02", "name": [{"text": "x"}]}],  # no language
])
def test_parse_holidays_rejects_broken_input(broken):
    with pytest.raises(InvalidResponse):
        parse_holidays(broken)


def test_parse_subdivisions_and_countries():
    subdivisions = parse_subdivisions([{"code": "XX-AA", "isoCode": "XX-AA", "shortName": "AA",
                                        "name": [{"language": "EN", "text": "Alpha"}]}])
    assert subdivisions[0].code == "XX-AA" and subdivisions[0].name() == "Alpha"
    countries = parse_countries([{"isoCode": "XX", "name": [{"language": "EN", "text": "Xland"}]}])
    assert countries[0].code == "XX" and countries[0].name("DE") == "Xland"
    with pytest.raises(InvalidResponse):
        parse_subdivisions([{"name": []}])
    with pytest.raises(InvalidResponse):
        parse_countries("nope")


def test_is_plausible_needs_a_long_block_in_every_year():
    holidays = parse_holidays(FIXTURE)
    assert is_plausible(holidays, [2031])
    assert not is_plausible(holidays, [2031, 2032])       # nothing known for 2032
    assert not is_plausible([], [2031])
    short_only = [Holiday("s", d("2032-10-06"), d("2032-10-17"), {"EN": "Autumn"}, "School", False, ())]
    assert not is_plausible(short_only, [2032])
    spanning = [Holiday("s", d("2032-12-20"), d("2033-01-20"), {"EN": "Winter"}, "School", False, ())]
    assert is_plausible(spanning, [2032, 2033])           # a block counts for both years it touches
