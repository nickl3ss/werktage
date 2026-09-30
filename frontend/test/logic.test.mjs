// node --test frontend/test
import { test } from "node:test";
import { strict as assert } from "node:assert";
import {
  DAY_OFF, WORKDAY, activeResidents, addDays, allState, allToggleStatus, dayClasses, daysBetween, isoWeek,
  mondayOf, moveInList, proposeShortName, retroactiveDays, shortDate, startsMonth, texts, toggleStatus,
  validRange, weekRows, esc,
} from "../src/logic.js";

test("dates: monday, add, between, iso week", () => {
  assert.equal(mondayOf("2026-10-01"), "2026-09-28");     // Thursday → Monday
  assert.equal(mondayOf("2026-09-28"), "2026-09-28");
  assert.equal(mondayOf("2026-10-04"), "2026-09-28");     // Sunday belongs to the same week
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
  assert.equal(daysBetween("2026-10-01", "2026-10-05"), 4);
  assert.equal(isoWeek("2026-09-28"), 40);
  assert.equal(isoWeek("2027-01-04"), 1);
  assert.equal(isoWeek("2026-01-01"), 1);
});

test("short date follows the language", () => {
  assert.equal(shortDate("2026-10-03", "de"), "03.10.26");
  assert.equal(shortDate("2026-10-03", "de-DE"), "03.10.26");
  assert.match(shortDate("2026-10-03", "en-US"), /10\/03\/26/);
  assert.equal(startsMonth("2026-10-01"), true);
  assert.equal(startsMonth("2026-10-02"), false);
});

const residents = [{ id: "a", short_name: "A" }, { id: "b", short_name: "B" }];
const day = (a, b) => ({ date: "2026-10-05", weekend: false, public_holiday: null, school_holiday: "Autumn",
  persons: { ...(a && { a: { effective: a } }), ...(b && { b: { effective: b } }) } });

test("All state and toggles (P18)", () => {
  assert.equal(allState(day(DAY_OFF, DAY_OFF), residents), "all");
  assert.equal(allState(day(WORKDAY, WORKDAY), residents), "none");
  assert.equal(allState(day(DAY_OFF, WORKDAY), residents), "some");
  assert.equal(allState(day(null, null), residents), "empty");
  assert.equal(allToggleStatus(day(DAY_OFF, DAY_OFF), residents), WORKDAY);
  assert.equal(allToggleStatus(day(DAY_OFF, WORKDAY), residents), DAY_OFF);
  assert.equal(allToggleStatus(day(WORKDAY, WORKDAY), residents), DAY_OFF);
  assert.equal(toggleStatus({ effective: DAY_OFF }), WORKDAY);
  assert.equal(toggleStatus({ effective: WORKDAY }), DAY_OFF);
});

test("week rows and cell classes", () => {
  const days = Array.from({ length: 14 }, (_, i) => ({ date: addDays("2026-09-28", i), weekend: i % 7 >= 5, public_holiday: i === 5 ? "Unity Day" : null, school_holiday: i >= 7 ? "Autumn" : null, persons: {} }));
  const rows = weekRows(days);
  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map((r) => r.week), [40, 41]);
  assert.deepEqual(dayClasses(days[5], "2026-10-03"), ["weekend", "public-holiday", "today"]);
  assert.deepEqual(dayClasses(days[7], "2026-10-03"), ["school-holiday"]);
});

test("period validation", () => {
  assert.equal(validRange("2026-10-01", "2026-10-01"), null);
  assert.equal(validRange("2026-10-02", "2026-10-01"), "end_before_start");
  assert.equal(validRange("2026-01-01", "2027-12-31"), "too_long");
  assert.equal(validRange("", "2026-10-01"), "missing");
});

test("residents helpers", () => {
  assert.equal(retroactiveDays("2026-09-01", "2026-10-01"), 30);
  assert.equal(retroactiveDays("2026-10-01", "2026-10-01"), 0);
  assert.equal(retroactiveDays("2026-11-01", "2026-10-01"), 0);
  const overview = { persons: [
    { id: "c", name: "Clara", role_today: "pupil", order: 2 }, { id: "a", name: "Anna", role_today: "adult", order: 0 },
    { id: "x", name: "Guest", role_today: null }, { id: "n", name: "Nils", role_today: "none", order: 1 }] };
  assert.deepEqual(activeResidents(overview).map((p) => p.id), ["a", "c"]);
  assert.equal(proposeShortName("Anna", []), "A");
  assert.equal(proposeShortName("Alex", ["A"]), "AL");
  assert.equal(proposeShortName("Alex", ["A", "AL"]), "A2");
  assert.deepEqual(moveInList(["a", "b", "c"], "b", -1), ["b", "a", "c"]);
  assert.deepEqual(moveInList(["a", "b", "c"], "a", -1), ["a", "b", "c"]);
  assert.deepEqual(moveInList(["a", "b", "c"], "c", 1), ["a", "b", "c"]);
});

test("texts and escaping", () => {
  assert.equal(texts("de").all, "Alle");
  assert.equal(texts("de-DE").role.pupil, "Schüler");
  assert.equal(texts("en").all, "All");
  assert.equal(texts(undefined).changes(1), "1 day change");
  assert.equal(texts("de").changes(3), "3 Tage ändern sich");
  assert.equal(esc(`<b>"x" & 'y'</b>`), "&lt;b&gt;&quot;x&quot; &amp; &#39;y&#39;&lt;/b&gt;");
});
