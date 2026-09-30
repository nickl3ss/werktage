// node --test frontend/test — the built bundle in a minimal DOM stand-in, fed with fictitious data.
import { test } from "node:test";
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../../custom_components/werktags/www/werktags-cards.js", import.meta.url), "utf8");

// --- DOM stand-in ------------------------------------------------------------------------------
class FakeShadowRoot {
  constructor() { this.innerHTML = ""; this._listeners = {}; }
  addEventListener(kind, fn) { this._listeners[kind] = fn; }
  querySelectorAll() { return []; }
  getElementById() { return { value: "" }; }
}
class FakeElement {
  constructor() { this.dataset = {}; }
  attachShadow() { this.shadowRoot = new FakeShadowRoot(); return this.shadowRoot; }
  dispatchEvent() {}
}
class FakeResizeObserver { observe() {} disconnect() {} }
const defined = {};
const registry = [];
const env = {
  customElements: { define: (tag, cls) => { defined[tag] = cls; } },
  window: { customCards: registry },
  HTMLElement: FakeElement,
  ResizeObserver: FakeResizeObserver,
  document: { createElement: (tag) => new (defined[tag])() },
  CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init?.detail; } },
  setTimeout: (fn) => { fn(); return 1; },
  clearTimeout: () => {},
};
new Function(...Object.keys(env), source)(...Object.values(env));

// --- fictitious responses ----------------------------------------------------------------------
const residents = [
  { id: "p_a", name: "Anna", short_name: "A", entity_id: "person.anna" },
  { id: "p_c", name: "Clara", short_name: "C", entity_id: "person.clara" },
];
const days = Array.from({ length: 35 }, (_, i) => {
  const date = new Date(Date.UTC(2026, 8, 28 + i)).toISOString().slice(0, 10);
  const weekend = i % 7 >= 5;
  const holiday = date === "2026-10-03" ? "Unity Day" : null;
  const school = date >= "2026-10-05" && date <= "2026-10-16" ? "Autumn" : null;
  const off = (role) => weekend || holiday || (role === "pupil" && school);
  return { date, weekend, public_holiday: holiday, school_holiday: school, persons: {
    p_a: { effective: off("adult") ? "day_off" : "workday", default: off("adult") ? "day_off" : "workday", exception: null, reason: holiday ? "public_holiday" : weekend ? "weekend" : "workday", holiday_name: holiday, role: "adult" },
    p_c: { effective: off("pupil") ? "day_off" : "workday", default: off("pupil") ? "day_off" : "workday", exception: null, reason: school ? "school_holiday" : weekend ? "weekend" : "workday", holiday_name: school, role: "pupil" },
  } };
});
const getDays = { start: "2026-09-28", end: "2026-11-01", today: "2026-10-01", residents, days };
const overview = {
  today: "2026-10-01", weekend: [5, 6],
  persons: [
    { id: "p_a", entity_id: "person.anna", name: "Anna", short_name: "A", order: 0, role_today: "adult", roles: [{ valid_from: "2010-01-01", role: "adult" }], off_weekdays: null, off_weekdays_history: [] },
    { id: "p_c", entity_id: "person.clara", name: "Clara", short_name: "C", order: 1, role_today: "pupil", roles: [{ valid_from: "2010-01-01", role: "pupil" }, { valid_from: "2027-08-01", role: "adult" }] },
    { id: "p_g", entity_id: "person.guest", name: "Guest", short_name: null, order: null, role_today: null, roles: [] },
  ],
  rooms: [
    { id: "bedroom", name: "Bedroom", residents_today: ["p_a"], morning_rule: "day_off_wins", evening_rule: "workday_wins", assignments: [{ valid_from: "2010-01-01", residents: ["p_a"] }] },
    { id: "kitchen", name: "Kitchen", residents_today: [], morning_rule: null, evening_rule: null, assignments: [] },
  ],
  house: { roles: ["adult"], residents_today: ["p_a"], by_role: true, assignments: [], morning_rule: "day_off_wins", evening_rule: "workday_wins" },
  status: {},
};

function fakeHass(language, calls) {
  return {
    locale: { language },
    connection: { sendMessagePromise: async (msg) => {
      calls.push(msg);
      if (msg.service === "get_days") return { response: JSON.parse(JSON.stringify(getDays)) };
      if (msg.service === "get_overview") return { response: JSON.parse(JSON.stringify(overview)) };
      if (msg.service === "preview_days") return { response: { changes: [{ id: "p_a", name: "Anna", days: 5 }] } };
      throw new Error("unexpected " + msg.service);
    } },
    callService: async (domain, service, data) => { calls.push({ type: "write", domain, service, service_data: data }); },
  };
}

const tick = () => new Promise((r) => setImmediate(r));

test("all four cards and the editor are registered", () => {
  for (const tag of ["werktags-calendar", "werktags-period", "werktags-residents", "werktags-rooms", "werktags-card-editor"]) assert.ok(defined[tag], tag);
  assert.equal(registry.length, 4);
  assert.ok(defined["werktags-calendar"].getStubConfig().weeks === 5);
});

test("calendar renders five weeks with toggles, German dates and holiday marks", async () => {
  const calls = [];
  const card = new defined["werktags-calendar"]();
  card.setConfig({ type: "custom:werktags-calendar", weeks: 5 });
  card.hass = fakeHass("de", calls);
  await tick(); await tick();
  const html = card.shadowRoot.innerHTML;
  assert.equal(calls[0].service, "get_days");
  assert.deepEqual(calls[0].service_data, { start: "2026-09-28", weeks: 5 });
  assert.match(html, /KW 40 – KW 44/);
  assert.match(html, /03\.10\.26/);                               // TT.MM.JJ
  assert.match(html, /Unity Day/);
  assert.equal((html.match(/data-action="toggle"/g) || []).length, 70);   // 35 days × 2 residents
  assert.equal((html.match(/class="tg all off"/g) || []).length, 10);    // ten weekend days (the public holiday is a Saturday)
  assert.match(html, /class="cell school-holiday/);
  assert.match(html, /class="cell weekend public-holiday/);
  assert.match(html, /class="cell today/);
});

test("tapping a toggle sets the opposite day and calls set_days", async () => {
  const calls = [];
  const card = new defined["werktags-calendar"]();
  card.setConfig({});
  card.hass = fakeHass("en", calls);
  await tick(); await tick();
  await card.on_toggle({ dataset: { date: "2026-10-01", person: "p_a" } });      // Thursday, workday → day_off
  const write = calls.find((c) => c.type === "write");
  assert.deepEqual(write.service_data, { person: "person.anna", start: "2026-10-01", status: "day_off" });
  await card.on_all({ dataset: { date: "2026-10-03" } });                         // everybody off on a holiday → asks first
  assert.equal(calls.filter((c) => c.type === "write").length, 1);
  assert.match(card.shadowRoot.innerHTML, /Set everyone to workday on a day off\?/);
  await card.on_all({ dataset: { date: "2026-10-03" } });                         // confirmed → all workday
  const all = calls.filter((c) => c.type === "write").pop();
  assert.deepEqual(all.service_data, { person: ["person.anna", "person.clara"], start: "2026-10-03", status: "workday" });
  await card.on_all({ dataset: { date: "2026-10-01" } });                         // workday: everybody off, no question
  assert.equal(calls.filter((c) => c.type === "write").pop().service_data.status, "day_off");
});

test("narrow width switches to one row per day", async () => {
  const card = new defined["werktags-calendar"]();
  card.setConfig({});
  card.hass = fakeHass("de", []);
  await tick(); await tick();
  card._narrow = true; card.render();
  assert.match(card.shadowRoot.innerHTML, /class="list"/);
  assert.match(card.shadowRoot.innerHTML, /class="week">KW 40/);
});

test("period card previews and applies a range", async () => {
  const calls = [];
  const card = new defined["werktags-period"]();
  card.setConfig({});
  card.hass = fakeHass("de", calls);
  await tick(); await tick();
  card.on_everyone();
  card.on_start({ value: "2026-10-05" }); card.on_end({ value: "2026-10-11" });
  await tick(); await tick();
  assert.match(card.shadowRoot.innerHTML, /Vorschau:.*Anna 5 Tage ändern sich/);
  card.on_end({ value: "2026-10-01" });
  await tick();
  assert.match(card.shadowRoot.innerHTML, /Der letzte Tag liegt vor dem ersten/);
  card.on_end({ value: "2026-10-11" });
  await card.on_apply();
  const write = calls.find((c) => c.type === "write");
  assert.deepEqual(write.service_data, { person: ["person.anna", "person.clara"], start: "2026-10-05", end: "2026-10-11", status: "day_off" });
});

test("residents card lists everyone and asks before a retroactive role change", async () => {
  const calls = [];
  const card = new defined["werktags-residents"]();
  card.setConfig({});
  card.hass = fakeHass("de", calls);
  await tick(); await tick();
  const html = card.shadowRoot.innerHTML;
  assert.match(html, /Anna/); assert.match(html, /Guest/); assert.match(html, /kein Bewohner/);
  assert.match(html, /seit 01\.01\.10: Schüler/);
  assert.match(html, /Schüler <span class="muted">seit 01\.01\.10/);             // the current entry, not the future one
  card.on_form_date({ dataset: { id: "p_c" }, value: "2026-09-01" });
  card.on_form_role({ dataset: { id: "p_c" }, value: "adult" });
  await card.on_set_role({ dataset: { id: "p_c" } });
  assert.match(card.shadowRoot.innerHTML, /Ändert \d+ Tage rückwirkend/);   // days depend on the real clock
  assert.equal(calls.filter((c) => c.type === "write").length, 0);
  await card.on_set_role({ dataset: { id: "p_c" } });
  const write = calls.find((c) => c.type === "write");
  assert.deepEqual(write.service_data, { person: "person.clara", role: "adult", valid_from: "2026-09-01" });
});

test("residents card sets personal days off every week and returns to the household weekend", async () => {
  const calls = [];
  const card = new defined["werktags-residents"]();
  card.setConfig({});
  card.hass = fakeHass("en", calls);
  await tick(); await tick();
  assert.match(card.shadowRoot.innerHTML, /household weekend/);
  card.on_form_day({ dataset: { id: "p_a", day: "4" } });                          // Friday off too
  assert.match(card.shadowRoot.innerHTML, /\(personal\)/);
  await card.on_set_role({ dataset: { id: "p_a" } });
  let write = calls.filter((c) => c.type === "write").pop();
  assert.equal(write.service, "set_weekly");
  assert.deepEqual(write.service_data, { person: "person.anna", valid_from: card.today, weekdays: [4, 5, 6] });
  card.on_form_day({ dataset: { id: "p_a", day: "4" } });
  card.on_form_day({ dataset: { id: "p_a", day: "4" } });                          // back to Saturday+Sunday
  card.on_form_weekly_reset({ dataset: { id: "p_a" } });
  card.on_form_day({ dataset: { id: "p_a", day: "0" } });
  card.on_form_weekly_reset({ dataset: { id: "p_a" } });
  await card.on_set_role({ dataset: { id: "p_a" } });
  write = calls.filter((c) => c.type === "write").pop();
  assert.deepEqual(write.service_data, { person: "person.anna", valid_from: card.today, household: true });
});

test("rooms card lets the house follow chosen residents or the roles again", async () => {
  const calls = [];
  const card = new defined["werktags-rooms"]();
  card.setConfig({});
  card.hass = fakeHass("de", calls);
  await tick(); await tick();
  assert.match(card.shadowRoot.innerHTML, /nach Rolle/);
  card.on_house_add({ value: "p_c" });
  await card.on_house_apply();
  let write = calls.filter((c) => c.type === "write").pop();
  assert.equal(write.service, "set_house");
  assert.deepEqual(write.service_data, { valid_from: card.today, person: ["person.anna", "person.clara"] });
  card.on_house_remove({ dataset: { id: "p_a" } });
  card.on_house_remove({ dataset: { id: "p_c" } });
  card.on_house_date({ value: "2026-01-01" });
  await card.on_house_apply();
  assert.match(card.shadowRoot.innerHTML, /rückwirkend/);
  await card.on_house_apply();
  write = calls.filter((c) => c.type === "write").pop();
  assert.deepEqual(write.service_data, { valid_from: "2026-01-01", by_role: true });
});

test("rooms card edits residents with a date and changes rules directly", async () => {
  const calls = [];
  const card = new defined["werktags-rooms"]();
  card.setConfig({});
  card.hass = fakeHass("en", calls);
  await tick(); await tick();
  assert.match(card.shadowRoot.innerHTML, /Kitchen/); assert.match(card.shadowRoot.innerHTML, /House/);
  card.on_room_add({ dataset: { area: "bedroom" }, value: "p_c" });
  assert.match(card.shadowRoot.innerHTML, /Change from/);
  await card.on_room_apply({ dataset: { area: "bedroom" } });
  let write = calls.find((c) => c.type === "write");
  assert.deepEqual(write.service_data, { area: "bedroom", person: ["person.anna", "person.clara"], valid_from: card.today });
  card.on_room_rule({ dataset: { area: "kitchen", rule: "morning_rule" }, value: "workday_wins" });
  assert.equal(calls.filter((c) => c.type === "write").length, 1);                 // nothing written yet
  await card.on_room_apply({ dataset: { area: "kitchen" } });
  write = calls.filter((c) => c.type === "write").pop();
  assert.deepEqual(write.service_data, { area: "kitchen", morning_rule: "workday_wins" });
});

test("a missing integration is reported in words", async () => {
  const card = new defined["werktags-calendar"]();
  card.setConfig({});
  card.hass = { locale: { language: "de" }, connection: { sendMessagePromise: async () => { throw new Error("Werktags is not set up yet."); } } };
  await tick(); await tick();
  assert.match(card.shadowRoot.innerHTML, /Werktags ist nicht eingerichtet/);
});
