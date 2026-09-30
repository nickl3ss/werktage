/* Werktags cards v0.1.0 — built from frontend/src by tools/build_cards.py. Do not edit. */
(() => {
"use strict";
/**
 * Pure logic of the Werktags cards: dates, grid, "All" state, texts.
 * No DOM, no Home Assistant — testable with plain Node.
 */

const DAY_OFF = "day_off";
const WORKDAY = "workday";
const DEFAULT = "default";
const MS_PER_DAY = 86400000;

// --- dates ---------------------------------------------------------------------------

/** "2026-10-01" → Date at UTC midnight (UTC keeps arithmetic free of DST). */
function parseDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function toIso(date) {
  return date.toISOString().slice(0, 10);
}

function addDays(iso, days) {
  return toIso(new Date(parseDate(iso).getTime() + days * MS_PER_DAY));
}

function daysBetween(fromIso, toIso_) {
  return Math.round((parseDate(toIso_) - parseDate(fromIso)) / MS_PER_DAY);
}

/** Monday of the week containing the day. */
function mondayOf(iso) {
  const date = parseDate(iso);
  const weekday = (date.getUTCDay() + 6) % 7; // Monday = 0
  return addDays(iso, -weekday);
}

function todayIso(now = new Date()) {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

/** ISO week number (1–53). */
function isoWeek(iso) {
  const date = parseDate(iso);
  const thursday = new Date(date.getTime() + ((4 - ((date.getUTCDay() + 6) % 7 + 1)) * MS_PER_DAY));
  const yearStart = Date.UTC(thursday.getUTCFullYear(), 0, 1);
  return Math.ceil(((thursday - yearStart) / MS_PER_DAY + 1) / 7);
}

/** Short date for the calendar cell: TT.MM.JJ in German, locale default otherwise. */
function shortDate(iso, language) {
  const [y, m, d] = iso.split("-");
  if ((language || "en").toLowerCase().startsWith("de")) return `${d}.${m}.${y.slice(2)}`;
  return new Intl.DateTimeFormat(language || "en", { day: "2-digit", month: "2-digit", year: "2-digit", timeZone: "UTC" })
    .format(parseDate(iso));
}

function longDate(iso, language) {
  return new Intl.DateTimeFormat(language || "en", { weekday: "short", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
    .format(parseDate(iso));
}

function monthName(iso, language) {
  return new Intl.DateTimeFormat(language || "en", { month: "long", timeZone: "UTC" }).format(parseDate(iso));
}

// --- grid ----------------------------------------------------------------------------

/** The days of a get_days response as rows of seven, each day with its ISO week. */
function weekRows(days) {
  const rows = [];
  for (let i = 0; i < days.length; i += 7) {
    const week = days.slice(i, i + 7);
    rows.push({ week: isoWeek(week[0].date), days: week });
  }
  return rows;
}

/** State of the "All" toggle for one day: "all" | "none" | "some" | "empty". */
function allState(day, residents) {
  const infos = residents.map((r) => day.persons[r.id]).filter(Boolean);
  if (!infos.length) return "empty";
  const off = infos.filter((p) => p.effective === DAY_OFF).length;
  return off === infos.length ? "all" : off === 0 ? "none" : "some";
}

/**
 * What tapping a resident's toggle should set: the opposite of today's effective day.
 * Returns the `status` for set_days.
 */
function toggleStatus(personInfo) {
  return personInfo.effective === DAY_OFF ? WORKDAY : DAY_OFF;
}

/** What tapping "All" should set (P18): all off unless everybody is off already, then all workday. */
function allToggleStatus(day, residents) {
  return allState(day, residents) === "all" ? WORKDAY : DAY_OFF;
}

/** CSS classes for a day cell. */
function dayClasses(day, todayIso_) {
  const classes = [];
  if (day.weekend) classes.push("weekend");
  if (day.public_holiday) classes.push("public-holiday");
  if (day.school_holiday) classes.push("school-holiday");
  if (day.date === todayIso_) classes.push("today");
  return classes;
}

/** True when the day's date is the first of a month (a month label is shown). */
function startsMonth(iso) {
  return iso.slice(8) === "01";
}

// --- period card -------------------------------------------------------------------------

function validRange(start, end, maxDays = 366) {
  if (!start || !end) return "missing";
  if (daysBetween(start, end) < 0) return "end_before_start";
  if (daysBetween(start, end) + 1 > maxDays) return "too_long";
  return null;
}

// --- residents / rooms ---------------------------------------------------------------

/** Days a change "valid from" would rewrite in the past (0 if the date is today or later). */
function retroactiveDays(validFrom, todayIso_) {
  const days = daysBetween(validFrom, todayIso_);
  return days > 0 ? days : 0;
}

/** Residents with a role today, in card order. */
function activeResidents(overview) {
  return overview.persons
    .filter((p) => p.role_today && p.role_today !== "none")
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || a.name.localeCompare(b.name));
}

/** Short name proposal for a new resident: first letter, made unique among the taken ones. */
function proposeShortName(name, taken) {
  const base = (name.trim()[0] || "?").toUpperCase();
  if (!taken.includes(base)) return base;
  const second = (name.trim().slice(0, 2) || base).toUpperCase();
  if (!taken.includes(second)) return second;
  for (let i = 2; i < 10; i += 1) if (!taken.includes(base + i)) return base + i;
  return base;
}

/** Move an id one step up or down in a list; returns a new list. */
function moveInList(ids, id, direction) {
  const index = ids.indexOf(id);
  const target = index + direction;
  if (index < 0 || target < 0 || target >= ids.length) return ids.slice();
  const result = ids.slice();
  [result[index], result[target]] = [result[target], result[index]];
  return result;
}

// --- texts ----------------------------------------------------------------------------

const TEXTS = {
  en: {
    all: "All", today: "Today", week: "Week", prev_weeks: "Earlier", next_weeks: "Later",
    workday: "Workday", day_off: "Day off", default: "Default (remove exceptions)",
    before_workday: "Before a workday", before_day_off: "Before a day off",
    reason: { workday: "Workday", weekend: "Weekend", public_holiday: "Public holiday", school_holiday: "School holiday",
      exception_day_off: "Exception: day off", exception_workday: "Exception: workday", unknown: "Unknown (counts as workday)" },
    role: { pupil: "Pupil", adult: "Adult", none: "None" }, not_resident: "not a resident",
    rule: { day_off_wins: "Day off wins", workday_wins: "Workday wins" },
    what: "What?", who: "Who?", when: "When?", from: "From", to: "To", apply: "Apply", cancel: "Cancel",
    preview: "Preview", changes: (n) => `${n} day${n === 1 ? "" : "s"} change`, nothing_changes: "nothing changes",
    applied: "Applied.", error: "Failed", end_before_start: "The last day lies before the first day.",
    too_long: "At most 366 days.", missing: "Choose first and last day.", choose_person: "Choose at least one person.",
    person: "Person", short_name: "Short", role_today: "Role today", since: "since", new_role: "New role", valid_from: "valid from",
    history: "History", remove: "Remove", retro: (n) => `Changes ${n} day${n === 1 ? "" : "s"} retroactively — apply?`,
    yes: "Yes", room: "Room", residents: "Residents", morning: "Morning", evening: "Evening", change_from: "Change from",
    add: "Add", no_residents: "no residents", house: "House", house_hint: "House roles and rules are set in the integration options.",
    loading: "Loading…", not_set_up: "Werktags is not set up.", school_holidays: "School holidays",
    known_to: "known until", fetched: "fetched", never: "never", no_role: "No role", order: "Order",
  },
  de: {
    all: "Alle", today: "Heute", week: "KW", prev_weeks: "Früher", next_weeks: "Später",
    workday: "Werktag", day_off: "Frei", default: "Standard (Ausnahmen entfernen)",
    before_workday: "Abend vor Werktag", before_day_off: "Abend vor freiem Tag",
    reason: { workday: "Werktag", weekend: "Wochenende", public_holiday: "Feiertag", school_holiday: "Schulferien",
      exception_day_off: "Ausnahme: frei", exception_workday: "Ausnahme: Werktag", unknown: "Unbekannt (gilt als Werktag)" },
    role: { pupil: "Schüler", adult: "Erwachsen", none: "Keine" }, not_resident: "kein Bewohner",
    rule: { day_off_wins: "Frei gewinnt", workday_wins: "Arbeit gewinnt" },
    what: "Was?", who: "Wer?", when: "Wann?", from: "Von", to: "Bis", apply: "Übernehmen", cancel: "Abbrechen",
    preview: "Vorschau", changes: (n) => `${n} Tag${n === 1 ? "" : "e"} ändern sich`, nothing_changes: "nichts ändert sich",
    applied: "Übernommen.", error: "Fehlgeschlagen", end_before_start: "Der letzte Tag liegt vor dem ersten.",
    too_long: "Höchstens 366 Tage.", missing: "Ersten und letzten Tag wählen.", choose_person: "Mindestens eine Person wählen.",
    person: "Person", short_name: "Kürzel", role_today: "Rolle heute", since: "seit", new_role: "Neue Rolle", valid_from: "gültig ab",
    history: "Verlauf", remove: "Löschen", retro: (n) => `Ändert ${n} Tag${n === 1 ? "" : "e"} rückwirkend — übernehmen?`,
    yes: "Ja", room: "Raum", residents: "Bewohner", morning: "Morgens", evening: "Abends", change_from: "Ändern ab",
    add: "Hinzufügen", no_residents: "keine Bewohner", house: "Haus", house_hint: "Rollen und Regeln des Hauses werden in den Optionen der Integration eingestellt.",
    loading: "Lade…", not_set_up: "Werktags ist nicht eingerichtet.", school_holidays: "Schulferien",
    known_to: "bekannt bis", fetched: "abgerufen", never: "nie", no_role: "Keine Rolle", order: "Reihenfolge",
  },
};

function texts(language) {
  return (language || "en").toLowerCase().startsWith("de") ? TEXTS.de : TEXTS.en;
}

/** Escape text for innerHTML. */
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/**
 * Werktags dashboard cards: calendar, period, residents, rooms.
 *
 * Plain custom elements, no framework, no external library. They talk to the
 * integration only through its services (get_days, get_overview, preview_days
 * with responses; set_* for writes), see docs/specification.md section 6.
 */

const DOMAIN = "werktags";
const NARROW_PX = 600;

const STYLE = `
  :host { display: block; }
  ha-card { padding: 12px 16px 16px; }
  h2 { margin: 0 0 8px; font-size: 1.1em; font-weight: 500; }
  .bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
  .bar .range { flex: 1; color: var(--secondary-text-color); font-size: 0.9em; }
  button { font: inherit; cursor: pointer; border-radius: 6px; border: 1px solid var(--divider-color, #ddd);
           background: var(--card-background-color, #fff); color: var(--primary-text-color); padding: 4px 10px; }
  button:disabled { opacity: 0.4; cursor: default; }
  button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  input, select { font: inherit; padding: 4px 6px; border-radius: 6px; border: 1px solid var(--divider-color, #ddd);
                  background: var(--card-background-color, #fff); color: var(--primary-text-color); }
  .msg { margin-top: 8px; font-size: 0.9em; }
  .msg.error { color: var(--error-color, #b00020); }
  .msg.ok { color: var(--success-color, #2e7d32); }
  .muted { color: var(--secondary-text-color); }
  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: left; padding: 6px 6px; border-bottom: 1px solid var(--divider-color, #eee); vertical-align: top; }
  th { font-weight: 500; color: var(--secondary-text-color); font-size: 0.85em; }
  .chip { display: inline-flex; align-items: center; gap: 4px; border-radius: 14px; padding: 2px 8px; margin: 2px;
          border: 1px solid var(--divider-color, #ddd); font-size: 0.9em; }
  .chip.on { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  .chip button { border: none; background: none; padding: 0 2px; color: inherit; }
  .confirm { border: 1px solid var(--warning-color, #ffa000); border-radius: 6px; padding: 6px 8px; margin: 6px 0; }
  .grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 3px; }
  .grid .head { text-align: center; font-size: 0.8em; color: var(--secondary-text-color); padding: 2px 0; }
  .cell { border: 1px solid var(--divider-color, #ddd); border-radius: 6px; padding: 4px; min-height: 84px; font-size: 0.8em; }
  .cell.weekend, .cell.public-holiday { background: rgba(127, 127, 127, 0.12); }
  .cell.school-holiday { border-color: var(--info-color, #1e88e5); border-width: 2px; }
  .cell.today { box-shadow: 0 0 0 2px var(--primary-color); }
  .cell .date { display: flex; justify-content: space-between; align-items: baseline; gap: 2px; }
  .cell .date button { border: none; background: none; padding: 0; font-weight: 600; font-size: 1em; }
  .cell .month { font-size: 0.9em; color: var(--primary-color); font-weight: 600; }
  .cell .holiday { color: var(--secondary-text-color); font-size: 0.85em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .toggles { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 4px; }
  .tg { min-width: 28px; height: 26px; padding: 0 6px; border-radius: 6px; font-size: 0.85em; font-weight: 600; }
  .tg.off { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  .tg.exc { outline: 2px solid var(--warning-color, #ffa000); outline-offset: -2px; }
  .tg.all { min-width: 42px; }
  .tg.some { background: repeating-linear-gradient(45deg, var(--primary-color) 0 4px, transparent 4px 8px); color: var(--primary-text-color); }
  .tg.sh { background-color: rgba(30, 136, 229, 0.15); }
  .tg.sh.off { background: var(--primary-color); }
  .list .day { display: flex; align-items: center; gap: 8px; padding: 4px 0; border-bottom: 1px solid var(--divider-color, #eee); }
  .list .day .date { min-width: 96px; }
  .list .day .date button { border: none; background: none; padding: 0; font-weight: 600; }
  .list .week { font-weight: 500; color: var(--secondary-text-color); margin: 8px 0 2px; font-size: 0.85em; }
  .list .day.weekend, .list .day.public-holiday { background: rgba(127, 127, 127, 0.12); }
  .list .day.school-holiday .date { border-left: 3px solid var(--info-color, #1e88e5); padding-left: 4px; }
  .list .day.today .date button { color: var(--primary-color); }
  .info { border: 1px solid var(--divider-color, #ddd); border-radius: 6px; padding: 8px; margin: 8px 0; font-size: 0.9em; }
  .info h3 { margin: 0 0 4px; font-size: 1em; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 6px 0; }
  .label { min-width: 60px; color: var(--secondary-text-color); }
  details summary { cursor: pointer; color: var(--secondary-text-color); font-size: 0.9em; }
  .step { display: flex; gap: 8px; align-items: center; padding: 2px 0; font-size: 0.9em; }
  .status { font-size: 0.85em; color: var(--secondary-text-color); margin-top: 8px; }
`;

// --- base ---------------------------------------------------------------------------------

class WerktagsCard extends HTMLElement {
  static defaults = {};

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._message = null;
    this._loading = false;
    this.shadowRoot.addEventListener("click", (event) => this._delegate(event, "click"));
    this.shadowRoot.addEventListener("change", (event) => this._delegate(event, "change"));
    this.shadowRoot.addEventListener("input", (event) => this._delegate(event, "input"));
  }

  setConfig(config) {
    this._config = { ...this.constructor.defaults, ...config };
    this.render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this.load();
  }

  get hass() { return this._hass; }
  get lang() { return this._hass?.locale?.language || this._hass?.language || "en"; }
  get t() { return texts(this.lang); }
  get today() { return todayIso(); }
  getCardSize() { return 6; }

  /** Elements carry data-action; handlers are methods named on<Action>. */
  _delegate(event, kind) {
    const target = event.composedPath().find((el) => el.dataset && el.dataset.action && el.dataset.on === kind);
    if (!target) return;
    const method = this[`on_${target.dataset.action}`];
    if (typeof method === "function") method.call(this, target, event);
  }

  /** Service with response through the websocket; independent of frontend helpers. */
  async callWithResponse(service, data) {
    const result = await this._hass.connection.sendMessagePromise({
      type: "call_service", domain: DOMAIN, service, service_data: data, return_response: true,
    });
    return result.response;
  }

  async callService(service, data) {
    await this._hass.callService(DOMAIN, service, data);
  }

  /** Run a write, show errors inline, reload afterwards. */
  async write(service, data, okMessage) {
    try {
      await this.callService(service, data);
      this._message = okMessage ? { kind: "ok", text: okMessage } : null;
    } catch (err) {
      this._message = { kind: "error", text: `${this.t.error}: ${err?.message || err}` };
    }
    await this.load();
  }

  async load() { /* overridden */ }

  card(title, body) {
    const heading = title ? `<h2>${esc(title)}</h2>` : "";
    const msg = this._message ? `<div class="msg ${this._message.kind}">${esc(this._message.text)}</div>` : "";
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>${heading}${body}${msg}</ha-card>`;
  }

  fail(err) {
    const text = String(err?.message || err);
    this._message = { kind: "error", text: text.includes("not set up") || text.includes("nicht eingerichtet") ? this.t.not_set_up : `${this.t.error}: ${text}` };
    this.render();
  }

  render() { /* overridden */ }
}

// --- calendar ----------------------------------------------------------------------------

class WerktagsCalendarCard extends WerktagsCard {
  static defaults = { title: "", weeks: 5 };
  static getStubConfig() { return { weeks: 5 }; }
  static getConfigElement() { return document.createElement("werktags-card-editor"); }

  constructor() {
    super();
    this._start = mondayOf(this.today);
    this._data = null;
    this._narrow = false;
    this._info = null;
    this._observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect?.width || 0;
      const narrow = width > 0 && width < NARROW_PX;
      if (narrow !== this._narrow) { this._narrow = narrow; this.render(); }
    });
  }

  connectedCallback() { this._observer.observe(this); }
  disconnectedCallback() { this._observer.disconnect(); }
  getCardSize() { return this._narrow ? 20 : 12; }

  async load() {
    if (!this._hass) return;
    try {
      this._data = await this.callWithResponse("get_days", { start: this._start, weeks: Number(this._config.weeks) || 5 });
      this._message = null;
    } catch (err) {
      this.fail(err);
      return;
    }
    this.render();
  }

  on_prev() { this._start = addDays(this._start, -7); this.load(); }
  on_next() { this._start = addDays(this._start, 7); this.load(); }
  on_today() { this._start = mondayOf(this.today); this.load(); }
  on_info(el) { this._info = this._info === el.dataset.date ? null : el.dataset.date; this.render(); }
  on_close_info() { this._info = null; this.render(); }

  async on_toggle(el) {
    const { date, person } = el.dataset;
    const day = this._data.days.find((d) => d.date === date);
    const info = day?.persons[person];
    if (!info) return;
    const resident = this._data.residents.find((r) => r.id === person);
    const status = toggleStatus(info);
    info.effective = status;   // optimistic
    this.render();
    await this.write("set_days", { person: resident.entity_id, start: date, status });
  }

  async on_all(el) {
    const day = this._data.days.find((d) => d.date === el.dataset.date);
    const residents = this._data.residents.filter((r) => day.persons[r.id]);
    if (!residents.length) return;
    const status = allToggleStatus(day, residents);
    residents.forEach((r) => { day.persons[r.id].effective = status; });
    this.render();
    await this.write("set_days", { person: residents.map((r) => r.entity_id), start: day.date, status });
  }

  _toggleHtml(day, resident) {
    const info = day.persons[resident.id];
    if (!info) return `<button class="tg" disabled title="${esc(this.t.no_role)}">${esc(resident.short_name)}</button>`;
    const classes = ["tg", info.effective === DAY_OFF ? "off" : "on"];
    if (info.exception) classes.push("exc");
    if (info.role === "pupil" && day.school_holiday) classes.push("sh");
    const title = `${resident.name}: ${this.t.reason[info.reason] || info.reason}`;
    return `<button class="${classes.join(" ")}" data-action="toggle" data-on="click" data-date="${day.date}" data-person="${esc(resident.id)}" title="${esc(title)}">${esc(resident.short_name)}</button>`;
  }

  _allHtml(day) {
    const state = allState(day, this._data.residents);
    const cls = state === "all" ? "off" : state === "some" ? "some" : "on";
    return `<button class="tg all ${cls}" data-action="all" data-on="click" data-date="${day.date}" ${state === "empty" ? "disabled" : ""}>${state === "all" ? "☑" : state === "some" ? "▣" : "☐"} ${esc(this.t.all)}</button>`;
  }

  _holidayHtml(day) {
    const name = day.public_holiday || day.school_holiday;
    return name ? `<div class="holiday" title="${esc(name)}">${esc(name)}</div>` : "";
  }

  _dateButton(day, extraClass = "") {
    const month = startsMonth(day.date) ? `<span class="month">${esc(monthName(day.date, this.lang))}</span>` : "";
    return `<div class="date ${extraClass}"><button data-action="info" data-on="click" data-date="${day.date}">${esc(shortDate(day.date, this.lang))}</button>${month}</div>`;
  }

  _infoHtml() {
    if (!this._info || !this._data) return "";
    const day = this._data.days.find((d) => d.date === this._info);
    if (!day) return "";
    const rows = this._data.residents.map((r) => {
      const info = day.persons[r.id];
      const text = info ? `${this.t[info.effective]} — ${this.t.reason[info.reason] || info.reason}${info.holiday_name ? ` (${esc(info.holiday_name)})` : ""}` : this.t.no_role;
      return `<div><b>${esc(r.name)}</b>: ${text}</div>`;
    }).join("");
    return `<div class="info"><h3>${esc(longDate(day.date, this.lang))}</h3>${rows}<div class="row"><button data-action="close_info" data-on="click">✕</button></div></div>`;
  }

  render() {
    const t = this.t;
    if (!this._data) { this.card(this._config.title, `<div class="muted">${t.loading}</div>`); return; }
    const rows = weekRows(this._data.days);
    const first = rows[0], last = rows[rows.length - 1];
    const range = `${t.week} ${first.week} – ${t.week} ${last.week} (${shortDate(first.days[0].date, this.lang)} – ${shortDate(last.days[6].date, this.lang)})`;
    const bar = `<div class="bar"><button data-action="prev" data-on="click" title="${esc(t.prev_weeks)}">‹</button>
      <button data-action="next" data-on="click" title="${esc(t.next_weeks)}">›</button><span class="range">${esc(range)}</span>
      <button data-action="today" data-on="click">${esc(t.today)}</button></div>`;
    const body = this._narrow ? this._listHtml(rows) : this._gridHtml(rows);
    this.card(this._config.title, bar + this._infoHtml() + body + this._statusHtml());
  }

  _gridHtml(rows) {
    const heads = rows[0].days.map((d) => `<div class="head">${esc(new Intl.DateTimeFormat(this.lang, { weekday: "short", timeZone: "UTC" }).format(new Date(d.date)))}</div>`).join("");
    const cells = rows.flatMap((row) => row.days.map((day) => {
      const toggles = this._data.residents.map((r) => this._toggleHtml(day, r)).join("");
      return `<div class="cell ${dayClasses(day, this._data.today).join(" ")}">${this._dateButton(day)}${this._holidayHtml(day)}
        <div class="toggles">${this._allHtml(day)}${toggles}</div></div>`;
    })).join("");
    return `<div class="grid">${heads}${cells}</div>`;
  }

  _listHtml(rows) {
    return `<div class="list">${rows.map((row) => `<div class="week">${esc(this.t.week)} ${row.week}</div>` + row.days.map((day) => {
      const toggles = this._data.residents.map((r) => this._toggleHtml(day, r)).join("");
      const weekday = new Intl.DateTimeFormat(this.lang, { weekday: "short", timeZone: "UTC" }).format(new Date(day.date));
      return `<div class="day ${dayClasses(day, this._data.today).join(" ")}"><div class="date"><button data-action="info" data-on="click" data-date="${day.date}">${esc(weekday)} ${esc(shortDate(day.date, this.lang))}</button>${this._holidayHtml(day)}</div>
        <div class="toggles">${this._allHtml(day)}${toggles}</div></div>`;
    }).join("")).join("")}</div>`;
  }

  _statusHtml() {
    const sh = this._data.school_holidays;
    return sh ? `<div class="status">${esc(sh)}</div>` : "";
  }
}

// --- period ----------------------------------------------------------------------------------

class WerktagsPeriodCard extends WerktagsCard {
  static defaults = { title: "" };
  static getStubConfig() { return {}; }
  static getConfigElement() { return document.createElement("werktags-card-editor"); }

  constructor() {
    super();
    this._overview = null;
    this._status = DAY_OFF;
    this._selected = new Set();
    this._start = this.today;
    this._end = this.today;
    this._preview = null;
    this._timer = null;
  }

  async load() {
    if (!this._hass) return;
    try { this._overview = await this.callWithResponse("get_overview", {}); } catch (err) { this.fail(err); return; }
    this.render();
    this._schedulePreview();
  }

  get residents() { return this._overview ? activeResidents(this._overview) : []; }

  on_status(el) { this._status = el.value; this._schedulePreview(); }
  on_start(el) { this._start = el.value; this._schedulePreview(); }
  on_end(el) { this._end = el.value; this._schedulePreview(); }
  on_person(el) {
    const id = el.dataset.id;
    if (this._selected.has(id)) this._selected.delete(id); else this._selected.add(id);
    this.render(); this._schedulePreview();
  }
  on_everyone() {
    const all = this.residents.map((r) => r.id);
    this._selected = this._selected.size === all.length ? new Set() : new Set(all);
    this.render(); this._schedulePreview();
  }

  _schedulePreview() {
    clearTimeout(this._timer);
    this._timer = setTimeout(() => this._loadPreview(), 300);
  }

  _entityIds() { return this.residents.filter((r) => this._selected.has(r.id)).map((r) => r.entity_id); }

  async _loadPreview() {
    const problem = validRange(this._start, this._end);
    if (problem || !this._selected.size) { this._preview = null; this.render(); return; }
    try {
      this._preview = await this.callWithResponse("preview_days", { person: this._entityIds(), start: this._start, end: this._end, status: this._status });
    } catch (err) { this._preview = null; this.fail(err); return; }
    this.render();
  }

  async on_apply() {
    const problem = validRange(this._start, this._end);
    if (problem) { this._message = { kind: "error", text: this.t[problem] }; this.render(); return; }
    if (!this._selected.size) { this._message = { kind: "error", text: this.t.choose_person }; this.render(); return; }
    await this.write("set_days", { person: this._entityIds(), start: this._start, end: this._end, status: this._status }, this.t.applied);
  }

  render() {
    const t = this.t;
    if (!this._overview) { this.card(this._config.title, `<div class="muted">${t.loading}</div>`); return; }
    const radio = [DAY_OFF, WORKDAY, DEFAULT].map((s) => `<label><input type="radio" name="status" value="${s}" data-action="status" data-on="change" ${this._status === s ? "checked" : ""}> ${esc(t[s])}</label>`).join(" ");
    const residents = this.residents;
    const chips = residents.map((r) => `<button class="chip ${this._selected.has(r.id) ? "on" : ""}" data-action="person" data-on="click" data-id="${esc(r.id)}" title="${esc(r.name)}">${esc(r.short_name || r.name)}</button>`).join("");
    const everyone = `<button class="chip ${this._selected.size === residents.length && residents.length ? "on" : ""}" data-action="everyone" data-on="click">${esc(t.all)}</button>`;
    const problem = validRange(this._start, this._end);
    let preview = "";
    if (problem) preview = `<div class="msg error">${esc(t[problem])}</div>`;
    else if (this._preview) {
      preview = `<div class="msg"><b>${esc(t.preview)}:</b> ` + this._preview.changes.map((c) => `${esc(c.name)} ${c.days ? esc(t.changes(c.days)) : esc(t.nothing_changes)}`).join(" · ") + `</div>`;
    }
    this.card(this._config.title, `
      <div class="row"><span class="label">${esc(t.what)}</span>${radio}</div>
      <div class="row"><span class="label">${esc(t.who)}</span>${everyone}${chips}</div>
      <div class="row"><span class="label">${esc(t.when)}</span>
        ${esc(t.from)} <input type="date" value="${this._start}" data-action="start" data-on="change">
        ${esc(t.to)} <input type="date" value="${this._end}" data-action="end" data-on="change"></div>
      ${preview}
      <div class="row"><button class="primary" data-action="apply" data-on="click" ${problem || !this._selected.size ? "disabled" : ""}>${esc(t.apply)}</button></div>`);
  }
}

// --- residents ---------------------------------------------------------------------------------

class WerktagsResidentsCard extends WerktagsCard {
  static defaults = { title: "" };
  static getStubConfig() { return {}; }
  static getConfigElement() { return document.createElement("werktags-card-editor"); }

  constructor() {
    super();
    this._overview = null;
    this._forms = {};      // person id → {role, valid_from, short_name, confirm}
  }

  async load() {
    if (!this._hass) return;
    try { this._overview = await this.callWithResponse("get_overview", {}); } catch (err) { this.fail(err); return; }
    this.render();
  }

  _form(id) {
    if (!this._forms[id]) {
      const person = this._overview.persons.find((p) => p.id === id);
      const taken = this._overview.persons.map((p) => p.short_name).filter(Boolean);
      this._forms[id] = { role: person.role_today && person.role_today !== "none" ? person.role_today : "pupil",
        valid_from: this.today, short_name: person.short_name || proposeShortName(person.name, taken), confirm: false };
    }
    return this._forms[id];
  }

  on_form_role(el) { this._form(el.dataset.id).role = el.value; }
  on_form_date(el) { this._form(el.dataset.id).valid_from = el.value; this._form(el.dataset.id).confirm = false; this.render(); }
  on_form_short(el) { this._form(el.dataset.id).short_name = el.value; }

  async on_short_save(el) {
    const person = this._overview.persons.find((p) => p.id === el.dataset.id);
    const first = person.roles[0];
    if (!first) return;
    await this.write("set_role", { person: person.entity_id, role: first.role, valid_from: first.valid_from, short_name: el.value.trim() });
  }

  async on_set_role(el) {
    const person = this._overview.persons.find((p) => p.id === el.dataset.id);
    const form = this._form(person.id);
    const retro = retroactiveDays(form.valid_from, this.today);
    if (retro > 0 && !form.confirm) { form.confirm = true; this.render(); return; }
    form.confirm = false;
    const data = { person: person.entity_id, role: form.role, valid_from: form.valid_from };
    if (!person.roles.length && form.short_name) data.short_name = form.short_name.trim();
    delete this._forms[person.id];
    await this.write("set_role", data, this.t.applied);
  }

  on_cancel_confirm(el) { this._form(el.dataset.id).confirm = false; this.render(); }

  async on_remove_step(el) {
    const person = this._overview.persons.find((p) => p.id === el.dataset.id);
    await this.write("remove_role", { person: person.entity_id, valid_from: el.dataset.date });
  }

  async on_move(el) {
    const ordered = activeResidents(this._overview).map((r) => r.id);
    const moved = moveInList(ordered, el.dataset.id, Number(el.dataset.dir));
    const byId = Object.fromEntries(this._overview.persons.map((p) => [p.id, p.entity_id]));
    await this.write("set_order", { person: moved.map((id) => byId[id]) });
  }

  _rowHtml(person, index, count) {
    const t = this.t;
    const isResident = person.role_today && person.role_today !== "none";
    const past = person.roles.filter((s) => s.valid_from <= this.today);
    const current = past.length ? past[past.length - 1] : null;
    const form = this._form(person.id);
    const roleOptions = ["pupil", "adult", "none"].map((r) => `<option value="${r}" ${form.role === r ? "selected" : ""}>${esc(t.role[r])}</option>`).join("");
    const shortCell = isResident
      ? `<input size="2" maxlength="2" value="${esc(person.short_name || "")}" data-action="short_save" data-on="change" data-id="${esc(person.id)}">`
      : `<input size="2" maxlength="2" value="${esc(form.short_name)}" data-action="form_short" data-on="input" data-id="${esc(person.id)}">`;
    const confirm = form.confirm ? `<div class="confirm">${esc(t.retro(retroactiveDays(form.valid_from, this.today)))}
        <button class="primary" data-action="set_role" data-on="click" data-id="${esc(person.id)}">${esc(t.yes)}</button>
        <button data-action="cancel_confirm" data-on="click" data-id="${esc(person.id)}">${esc(t.cancel)}</button></div>` : "";
    const history = person.roles.length > 1 || person.roles.length === 1 ? `<details><summary>${esc(t.history)}</summary>${person.roles.map((s, i) =>
      `<div class="step"><span>${esc(t.since)} ${esc(shortDate(s.valid_from, this.lang))}: ${esc(t.role[s.role])}</span>${i > 0 ? `<button data-action="remove_step" data-on="click" data-id="${esc(person.id)}" data-date="${s.valid_from}">${esc(t.remove)}</button>` : ""}</div>`).join("")}</details>` : "";
    const order = isResident ? `<button data-action="move" data-on="click" data-id="${esc(person.id)}" data-dir="-1" ${index === 0 ? "disabled" : ""}>↑</button>
      <button data-action="move" data-on="click" data-id="${esc(person.id)}" data-dir="1" ${index === count - 1 ? "disabled" : ""}>↓</button>` : "";
    return `<tr><td><b>${esc(person.name)}</b><br><span class="muted">${esc(person.entity_id)}</span></td>
      <td>${shortCell}</td>
      <td>${isResident && current ? `${esc(t.role[person.role_today])}<br><span class="muted">${esc(t.since)} ${esc(shortDate(current.valid_from, this.lang))}</span>` : `<span class="muted">${esc(t.not_resident)}</span>`}</td>
      <td><select data-action="form_role" data-on="change" data-id="${esc(person.id)}">${roleOptions}</select>
          <input type="date" value="${form.valid_from}" data-action="form_date" data-on="change" data-id="${esc(person.id)}">
          <button data-action="set_role" data-on="click" data-id="${esc(person.id)}">${esc(t.apply)}</button>${confirm}${history}</td>
      <td>${order}</td></tr>`;
  }

  render() {
    const t = this.t;
    if (!this._overview) { this.card(this._config.title, `<div class="muted">${t.loading}</div>`); return; }
    const active = activeResidents(this._overview);
    const others = this._overview.persons.filter((p) => !active.includes(p));
    const rows = [...active, ...others].map((p) => this._rowHtml(p, active.indexOf(p), active.length)).join("");
    this.card(this._config.title, `<table><thead><tr><th>${esc(t.person)}</th><th>${esc(t.short_name)}</th><th>${esc(t.role_today)}</th><th>${esc(t.new_role)} · ${esc(t.valid_from)}</th><th>${esc(t.order)}</th></tr></thead><tbody>${rows}</tbody></table>`);
  }
}

// --- rooms ---------------------------------------------------------------------------------

class WerktagsRoomsCard extends WerktagsCard {
  static defaults = { title: "" };
  static getStubConfig() { return {}; }
  static getConfigElement() { return document.createElement("werktags-card-editor"); }

  constructor() {
    super();
    this._overview = null;
    this._forms = {};      // area id → {residents: [ids], valid_from, confirm, dirty}
  }

  async load() {
    if (!this._hass) return;
    try { this._overview = await this.callWithResponse("get_overview", {}); } catch (err) { this.fail(err); return; }
    this._forms = {};
    this.render();
  }

  _form(room) {
    if (!this._forms[room.id]) this._forms[room.id] = { residents: room.residents_today.slice(), valid_from: this.today, confirm: false, dirty: false };
    return this._forms[room.id];
  }

  _room(id) { return this._overview.rooms.find((r) => r.id === id); }
  _person(id) { return this._overview.persons.find((p) => p.id === id); }

  on_room_remove(el) { const f = this._form(this._room(el.dataset.area)); f.residents = f.residents.filter((id) => id !== el.dataset.id); f.dirty = true; this.render(); }
  on_room_add(el) { if (!el.value) return; const f = this._form(this._room(el.dataset.area)); f.residents.push(el.value); f.dirty = true; this.render(); }
  on_room_date(el) { const f = this._form(this._room(el.dataset.area)); f.valid_from = el.value; f.confirm = false; this.render(); }
  on_room_cancel(el) { delete this._forms[el.dataset.area]; this.render(); }

  async on_room_apply(el) {
    const room = this._room(el.dataset.area);
    const form = this._form(room);
    const retro = retroactiveDays(form.valid_from, this.today);
    if (retro > 0 && !form.confirm) { form.confirm = true; this.render(); return; }
    await this.write("set_room", { area: room.id, person: form.residents.map((id) => this._person(id).entity_id), valid_from: form.valid_from }, this.t.applied);
  }

  async on_room_rule(el) {
    await this.write("set_room", { area: el.dataset.area, [el.dataset.rule]: el.value });
  }

  async on_room_remove_step(el) {
    await this.write("remove_room_assignment", { area: el.dataset.area, valid_from: el.dataset.date });
  }

  _ruleSelect(room, key) {
    const value = room[key] || (key === "morning_rule" ? "day_off_wins" : "workday_wins");
    return `<select data-action="room_rule" data-on="change" data-area="${esc(room.id)}" data-rule="${key}">${["day_off_wins", "workday_wins"].map((r) => `<option value="${r}" ${value === r ? "selected" : ""}>${esc(this.t.rule[r])}</option>`).join("")}</select>`;
  }

  _rowHtml(room) {
    const t = this.t;
    const form = this._form(room);
    const chips = form.residents.map((id) => `<span class="chip on">${esc(this._person(id)?.name || id)}<button data-action="room_remove" data-on="click" data-area="${esc(room.id)}" data-id="${esc(id)}" title="${esc(t.remove)}">✕</button></span>`).join("");
    const candidates = activeResidents(this._overview).filter((r) => !form.residents.includes(r.id));
    const add = `<select data-action="room_add" data-on="change" data-area="${esc(room.id)}"><option value="">+ ${esc(t.add)}</option>${candidates.map((r) => `<option value="${esc(r.id)}">${esc(r.name)}</option>`).join("")}</select>`;
    const confirm = form.confirm ? `<div class="confirm">${esc(t.retro(retroactiveDays(form.valid_from, this.today)))}
        <button class="primary" data-action="room_apply" data-on="click" data-area="${esc(room.id)}">${esc(t.yes)}</button>
        <button data-action="room_cancel" data-on="click" data-area="${esc(room.id)}">${esc(t.cancel)}</button></div>` : "";
    const apply = form.dirty ? `<div class="row">${esc(t.change_from)} <input type="date" value="${form.valid_from}" data-action="room_date" data-on="change" data-area="${esc(room.id)}">
        <button class="primary" data-action="room_apply" data-on="click" data-area="${esc(room.id)}">${esc(t.apply)}</button>
        <button data-action="room_cancel" data-on="click" data-area="${esc(room.id)}">${esc(t.cancel)}</button></div>${confirm}` : "";
    const history = room.assignments.length ? `<details><summary>${esc(t.history)}</summary>${room.assignments.map((s, i) =>
      `<div class="step"><span>${esc(t.since)} ${esc(shortDate(s.valid_from, this.lang))}: ${esc(s.residents.map((id) => this._person(id)?.name || id).join(", ") || t.no_residents)}</span>${i > 0 ? `<button data-action="room_remove_step" data-on="click" data-area="${esc(room.id)}" data-date="${s.valid_from}">${esc(t.remove)}</button>` : ""}</div>`).join("")}</details>` : "";
    return `<tr><td><b>${esc(room.name)}</b></td><td>${chips || `<span class="muted">${esc(t.no_residents)}</span>`} ${add}${apply}${history}</td>
      <td>${this._ruleSelect(room, "morning_rule")}</td><td>${this._ruleSelect(room, "evening_rule")}</td></tr>`;
  }

  render() {
    const t = this.t;
    if (!this._overview) { this.card(this._config.title, `<div class="muted">${t.loading}</div>`); return; }
    const rows = this._overview.rooms.map((r) => this._rowHtml(r)).join("");
    const house = this._overview.house;
    const houseRow = `<tr><td><b>${esc(t.house)}</b></td><td>${house.residents_today.map((id) => `<span class="chip on">${esc(this._person(id)?.name || id)}</span>`).join("") || `<span class="muted">${esc(t.no_residents)}</span>`}<br><span class="muted">${esc(house.roles.map((r) => t.role[r]).join(", "))} — ${esc(t.house_hint)}</span></td>
      <td>${esc(t.rule[house.morning_rule])}</td><td>${esc(t.rule[house.evening_rule])}</td></tr>`;
    this.card(this._config.title, `<table><thead><tr><th>${esc(t.room)}</th><th>${esc(t.residents)}</th><th>${esc(t.morning)}</th><th>${esc(t.evening)}</th></tr></thead><tbody>${rows}${houseRow}</tbody></table>`);
  }
}

// --- editor ----------------------------------------------------------------------------------

class WerktagsCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const showWeeks = this._config.type === "custom:werktags-calendar";
    this.shadowRoot.innerHTML = `<style>label { display: block; margin: 8px 0; } input { font: inherit; padding: 4px; }</style>
      <label>Title <input id="title" value="${esc(this._config.title || "")}"></label>
      ${showWeeks ? `<label>Weeks <input id="weeks" type="number" min="1" max="26" value="${Number(this._config.weeks) || 5}"></label>` : ""}`;
    this.shadowRoot.querySelectorAll("input").forEach((input) => input.addEventListener("change", () => this._changed()));
  }

  set hass(hass) { this._hass = hass; }

  _changed() {
    const title = this.shadowRoot.getElementById("title").value;
    const weeks = this.shadowRoot.getElementById("weeks");
    const config = { ...this._config, title };
    if (weeks) config.weeks = Number(weeks.value) || 5;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
  }
}

// --- registration ---------------------------------------------------------------------------

const CARDS = [
  ["werktags-calendar", WerktagsCalendarCard, "Werktags: calendar", "Five weeks of days off per resident; tap to change."],
  ["werktags-period", WerktagsPeriodCard, "Werktags: period", "Set days off or workdays for a date range."],
  ["werktags-residents", WerktagsResidentsCard, "Werktags: residents", "Roles and short names of the residents."],
  ["werktags-rooms", WerktagsRoomsCard, "Werktags: rooms", "Which residents belong to which room."],
];
customElements.define("werktags-card-editor", WerktagsCardEditor);
window.customCards = window.customCards || [];
for (const [tag, cls, name, description] of CARDS) {
  customElements.define(tag, cls);
  window.customCards.push({ type: tag, name, description, preview: false, documentationURL: "https://github.com/nickl3ss/werktags" });
}

})();
