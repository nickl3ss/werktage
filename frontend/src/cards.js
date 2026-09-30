/**
 * Werktags dashboard cards: calendar, period, residents, rooms.
 *
 * Plain custom elements, no framework, no external library. They talk to the
 * integration only through its services (get_days, get_overview, preview_days
 * with responses; set_* for writes), see docs/specification.md section 6.
 */
import {
  DAY_OFF, WORKDAY, DEFAULT, activeResidents, addDays, allState, allToggleStatus, dayClasses, esc,
  longDate, mondayOf, monthName, moveInList, proposeShortName, retroactiveDays, shortDate, startsMonth,
  texts, todayIso, toggleStatus, validRange, weekRows,
} from "./logic.js";

const DOMAIN = "werktags";
const NARROW_PX = 600;
const CHANGE_SENSOR = "sensor.house_morning";   // updated on every change → tells the cards to reload

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
  button.icon { min-width: 32px; }
  input, select { font: inherit; padding: 4px 6px; border-radius: 6px; border: 1px solid var(--divider-color, #ddd);
                  background: var(--card-background-color, #fff); color: var(--primary-text-color); }
  .msg { margin-top: 8px; font-size: 0.9em; }
  .msg.error { color: var(--error-color, #b00020); }
  .msg.ok { color: var(--success-color, #2e7d32); }
  .muted { color: var(--secondary-text-color); }
  .hint { color: var(--secondary-text-color); font-size: 0.9em; margin: 4px 0 8px; }
  table { border-collapse: collapse; width: 100%; }
  th, td { text-align: left; padding: 6px 6px; border-bottom: 1px solid var(--divider-color, #eee); vertical-align: top; }
  th { font-weight: 500; color: var(--secondary-text-color); font-size: 0.85em; }
  .chip { display: inline-flex; align-items: center; gap: 4px; border-radius: 14px; padding: 2px 8px; margin: 2px;
          border: 1px solid var(--divider-color, #ddd); font-size: 0.9em; }
  .chip.on { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  .chip button { border: none; background: none; padding: 0 2px; color: inherit; }
  .confirm { border: 1px solid var(--warning-color, #ffa000); border-radius: 6px; padding: 6px 8px; margin: 6px 0; }
  .legend { display: flex; flex-wrap: wrap; gap: 10px; font-size: 0.8em; color: var(--secondary-text-color); margin: 0 0 8px; align-items: center; }
  .legend .sw { display: inline-block; width: 14px; height: 14px; border-radius: 4px; border: 1px solid var(--divider-color, #ddd); vertical-align: middle; margin-right: 3px; }
  .legend .sw.off { background: var(--primary-color); border-color: var(--primary-color); }
  .legend .sw.exc { outline: 2px solid var(--warning-color, #ffa000); outline-offset: -2px; }
  .legend .sw.sh { border: 2px solid var(--info-color, #1e88e5); }
  .legend .sw.we { background: rgba(127, 127, 127, 0.25); }
  .legend .sw.unk { border-style: dashed; }
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
  .tg.unk { border-style: dashed; }
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
  .block { border-bottom: 1px solid var(--divider-color, #eee); padding: 8px 0; }
  .block .name { font-weight: 600; margin-bottom: 4px; }
  .block .row { margin: 4px 0; }
  .field { display: inline-flex; flex-direction: column; gap: 2px; font-size: 0.85em; color: var(--secondary-text-color); }
  .field > * { font-size: 1rem; color: var(--primary-text-color); }
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
    this._narrow = false;
    this._seen = null;                      // last_updated of CHANGE_SENSOR when we loaded
    this._observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect?.width || 0;
      const narrow = width > 0 && width < NARROW_PX;
      if (narrow !== this._narrow) { this._narrow = narrow; this.render(); }
    });
    this.shadowRoot.addEventListener("click", (event) => this._delegate(event, "click"));
    this.shadowRoot.addEventListener("change", (event) => this._delegate(event, "change"));
    this.shadowRoot.addEventListener("input", (event) => this._delegate(event, "input"));
  }

  connectedCallback() { this._observer.observe(this); }
  disconnectedCallback() { this._observer.disconnect(); }

  setConfig(config) {
    if (config.weeks !== undefined && !(Number(config.weeks) >= 1 && Number(config.weeks) <= 26)) {
      throw new Error("weeks must be between 1 and 26");
    }
    this._config = { ...this.constructor.defaults, ...config };
    this.render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    const stamp = hass?.states?.[CHANGE_SENSOR]?.last_updated || null;
    if (first) { this._seen = stamp; this.load(); return; }
    if (stamp && stamp !== this._seen) { this._seen = stamp; this.load(); }   // somebody else changed data
  }

  get hass() { return this._hass; }
  get lang() { return this._hass?.locale?.language || this._hass?.language || "en"; }
  get t() { return texts(this.lang); }
  get today() { return todayIso(); }
  getCardSize() { return 6; }

  /** Elements carry data-action; handlers are methods named on_<action>. */
  _delegate(event, kind) {
    const target = event.composedPath().find((el) => el.dataset && el.dataset.action && el.dataset.on === kind);
    if (!target) return;
    const method = this[`on_${target.dataset.action}`];
    if (typeof method === "function") method.call(this, target, event);
  }

  /** Service with response through the websocket; the same message the frontend uses. */
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
    const notSetUp = text.includes("not set up") || text.includes("nicht eingerichtet");
    this._message = { kind: "error", text: notSetUp ? this.t.not_set_up : `${this.t.error}: ${text}` };
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
    this._info = null;
    this._confirmAll = null;                // date awaiting confirmation for "All → workday"
  }

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

  _day(date) { return this._data.days.find((d) => d.date === date); }

  on_prev() { this._start = addDays(this._start, -7); this.load(); }
  on_next() { this._start = addDays(this._start, 7); this.load(); }
  on_today() { this._start = mondayOf(this.today); this.load(); }
  on_info(el) { this._info = this._info === el.dataset.date ? null : el.dataset.date; this._confirmAll = null; this.render(); }
  on_close_info() { this._info = null; this.render(); }
  on_cancel_all() { this._confirmAll = null; this.render(); }

  async on_toggle(el) {
    const { date, person } = el.dataset;
    const info = this._day(date)?.persons[person];
    if (!info) return;
    const resident = this._data.residents.find((r) => r.id === person);
    const status = toggleStatus(info);
    info.effective = status;   // optimistic
    this.render();
    await this.write("set_days", { person: resident.entity_id, start: date, status });
  }

  async on_all(el) {
    const day = this._day(el.dataset.date);
    const residents = this._data.residents.filter((r) => day.persons[r.id]);
    if (!residents.length) return;
    const status = allToggleStatus(day, residents);
    // Making everybody work on a weekend or public holiday is rarely meant: ask first (P18 stays intact).
    if (status === WORKDAY && (day.weekend || day.public_holiday) && this._confirmAll !== day.date) {
      this._confirmAll = day.date; this._info = day.date; this.render(); return;
    }
    this._confirmAll = null;
    residents.forEach((r) => { day.persons[r.id].effective = status; });
    this.render();
    await this.write("set_days", { person: residents.map((r) => r.entity_id), start: day.date, status });
  }

  async on_reset_day(el) {
    const day = this._day(el.dataset.date);
    const residents = this._data.residents.filter((r) => day.persons[r.id]);
    if (!residents.length) return;
    this._info = null;
    await this.write("set_days", { person: residents.map((r) => r.entity_id), start: day.date, status: DEFAULT });
  }

  _toggleHtml(day, resident) {
    const info = day.persons[resident.id];
    if (!info) return `<button class="tg" disabled title="${esc(this.t.no_role)}">${esc(resident.short_name)}</button>`;
    const off = info.effective === DAY_OFF;
    const classes = ["tg", off ? "off" : "on"];
    if (info.exception) classes.push("exc");
    if (info.reason === "unknown") classes.push("unk");
    if (info.role === "pupil" && day.school_holiday) classes.push("sh");
    const title = `${resident.name}: ${this.t[info.effective]} — ${this.t.reason[info.reason] || info.reason}`;
    return `<button class="${classes.join(" ")}" role="switch" aria-checked="${off}" aria-label="${esc(title)}" data-action="toggle" data-on="click" data-date="${day.date}" data-person="${esc(resident.id)}" title="${esc(title)}">${esc(resident.short_name)}</button>`;
  }

  _allHtml(day) {
    const state = allState(day, this._data.residents);
    const cls = state === "all" ? "off" : state === "some" ? "some" : "on";
    const mark = state === "all" ? "☑" : state === "some" ? "▣" : "☐";
    return `<button class="tg all ${cls}" data-action="all" data-on="click" data-date="${day.date}" aria-label="${esc(this.t.all)}" ${state === "empty" ? "disabled" : ""}>${mark} ${esc(this.t.all)}</button>`;
  }

  _holidayHtml(day) {
    const name = day.public_holiday || day.school_holiday;
    return name ? `<div class="holiday" title="${esc(name)}">${esc(name)}</div>` : "";
  }

  _dateButton(day) {
    const month = startsMonth(day.date) ? `<span class="month">${esc(monthName(day.date, this.lang))}</span>` : "";
    return `<div class="date"><button data-action="info" data-on="click" data-date="${day.date}" aria-label="${esc(longDate(day.date, this.lang))}">${esc(shortDate(day.date, this.lang))}</button>${month}</div>`;
  }

  _infoHtml() {
    if (!this._info || !this._data) return "";
    const day = this._day(this._info);
    if (!day) return "";
    const t = this.t;
    const rows = this._data.residents.map((r) => {
      const info = day.persons[r.id];
      const text = info
        ? `${t[info.effective]} — ${t.reason[info.reason] || info.reason}${info.holiday_name ? ` (${esc(info.holiday_name)})` : ""}`
        : t.no_role;
      return `<div><b>${esc(r.name)}</b>: ${text}</div>`;
    }).join("");
    const confirm = this._confirmAll === day.date
      ? `<div class="confirm">${esc(t.confirm_all_work)}
          <button class="primary" data-action="all" data-on="click" data-date="${day.date}">${esc(t.yes)}</button>
          <button data-action="cancel_all" data-on="click">${esc(t.cancel)}</button></div>` : "";
    return `<div class="info"><h3>${esc(longDate(day.date, this.lang))}</h3>${rows}${confirm}
      <div class="row"><button data-action="reset_day" data-on="click" data-date="${day.date}">${esc(t.reset_day)}</button>
      <button class="icon" data-action="close_info" data-on="click" aria-label="${esc(t.cancel)}">✕</button></div></div>`;
  }

  _legendHtml() {
    const t = this.t;
    const item = (cls, label) => `<span><span class="sw ${cls}"></span>${esc(label)}</span>`;
    return `<div class="legend">${item("off", t.legend_off)}${item("", t.legend_work)}${item("exc", t.legend_exc)}${item("sh", t.legend_school)}${item("we", t.legend_weekend)}${item("unk", t.legend_unknown)}</div>`;
  }

  _statusHtml() {
    const t = this.t;
    const status = this._data.status || {};
    if (status.school_holiday_source === "none") return "";
    const sh = status.school_holidays;
    const text = sh && sh.known_to ? t.known_until(shortDate(sh.known_to, this.lang)) : t.not_fetched;
    const attribution = status.attribution ? ` · ${esc(status.attribution)}` : "";
    return `<div class="status">${esc(text)}${attribution}</div>`;
  }

  render() {
    const t = this.t;
    if (!this._data) { this.card(this._config.title, `<div class="muted">${t.loading}</div>`); return; }
    const rows = weekRows(this._data.days);
    const first = rows[0], last = rows[rows.length - 1];
    const range = `${t.week} ${first.week} – ${t.week} ${last.week} (${shortDate(first.days[0].date, this.lang)} – ${shortDate(last.days[6].date, this.lang)})`;
    const bar = `<div class="bar"><button class="icon" data-action="prev" data-on="click" aria-label="${esc(t.prev_weeks)}" title="${esc(t.prev_weeks)}">‹</button>
      <button class="icon" data-action="next" data-on="click" aria-label="${esc(t.next_weeks)}" title="${esc(t.next_weeks)}">›</button><span class="range">${esc(range)}</span>
      <button data-action="today" data-on="click">${esc(t.today)}</button></div>`;
    const empty = this._data.residents.length ? "" : `<div class="hint">${esc(t.no_residents_yet)}</div>`;
    const body = this._narrow ? this._listHtml(rows) : this._gridHtml(rows);
    this.card(this._config.title, bar + this._legendHtml() + empty + this._infoHtml() + body + this._statusHtml());
  }

  _weekday(date) {
    return new Intl.DateTimeFormat(this.lang, { weekday: "short", timeZone: "UTC" }).format(new Date(date));
  }

  _gridHtml(rows) {
    const heads = rows[0].days.map((d) => `<div class="head">${esc(this._weekday(d.date))}</div>`).join("");
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
      return `<div class="day ${dayClasses(day, this._data.today).join(" ")}"><div class="date"><button data-action="info" data-on="click" data-date="${day.date}">${esc(this._weekday(day.date))} ${esc(shortDate(day.date, this.lang))}</button>${this._holidayHtml(day)}</div>
        <div class="toggles">${this._allHtml(day)}${toggles}</div></div>`;
    }).join("")).join("")}</div>`;
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

  disconnectedCallback() { super.disconnectedCallback(); clearTimeout(this._timer); }

  async load() {
    if (!this._hass) return;
    try { this._overview = await this.callWithResponse("get_overview", {}); } catch (err) { this.fail(err); return; }
    this.render();
    this._schedulePreview();
  }

  get residents() { return this._overview ? activeResidents(this._overview) : []; }

  on_status(el) { this._status = el.value; this._schedulePreview(); }
  on_start(el) { this._start = el.value; if (this._end < this._start) this._end = this._start; this.render(); this._schedulePreview(); }
  on_end(el) { this._end = el.value; this.render(); this._schedulePreview(); }
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
    const residents = this.residents;
    if (!residents.length) { this.card(this._config.title, `<div class="hint">${esc(t.no_residents_yet)}</div>`); return; }
    const radio = [DAY_OFF, WORKDAY, DEFAULT].map((s) => `<label><input type="radio" name="status" value="${s}" data-action="status" data-on="change" ${this._status === s ? "checked" : ""}> ${esc(t[s])}</label>`).join(" ");
    const chips = residents.map((r) => `<button class="chip ${this._selected.has(r.id) ? "on" : ""}" aria-pressed="${this._selected.has(r.id)}" data-action="person" data-on="click" data-id="${esc(r.id)}" title="${esc(r.name)}">${esc(r.short_name || r.name)}</button>`).join("");
    const everyone = `<button class="chip ${this._selected.size === residents.length ? "on" : ""}" data-action="everyone" data-on="click">${esc(t.all)}</button>`;
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
        <label class="field">${esc(t.from)}<input type="date" value="${this._start}" data-action="start" data-on="change"></label>
        <label class="field">${esc(t.to)}<input type="date" value="${this._end}" min="${this._start}" data-action="end" data-on="change"></label></div>
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
    this._forms = {};      // person id → {role, valid_from, short_name, confirm, dirty}
  }

  async load() {
    if (!this._hass) return;
    try { this._overview = await this.callWithResponse("get_overview", {}); } catch (err) { this.fail(err); return; }
    this._forms = {};
    this.render();
  }

  _person(id) { return this._overview.persons.find((p) => p.id === id); }

  _form(id) {
    if (!this._forms[id]) {
      const person = this._person(id);
      const taken = this._overview.persons.map((p) => p.short_name).filter(Boolean);
      const resident = person.role_today && person.role_today !== "none";
      this._forms[id] = { role: resident ? person.role_today : "adult", valid_from: this.today,
        short_name: person.short_name || proposeShortName(person.name, taken), confirm: false, dirty: false };
    }
    return this._forms[id];
  }

  _touch(el) { const form = this._form(el.dataset.id); form.dirty = true; form.confirm = false; return form; }
  on_form_role(el) { this._touch(el).role = el.value; this.render(); }
  on_form_date(el) { this._touch(el).valid_from = el.value; this.render(); }
  on_form_short(el) { this._touch(el).short_name = el.value; }
  on_form_cancel(el) { delete this._forms[el.dataset.id]; this.render(); }
  on_cancel_confirm(el) { this._form(el.dataset.id).confirm = false; this.render(); }

  async on_set_role(el) {
    const person = this._person(el.dataset.id);
    const form = this._form(person.id);
    const isResident = person.role_today && person.role_today !== "none";
    const roleChanged = !isResident || form.role !== person.role_today;
    const shortChanged = form.short_name.trim() !== (person.short_name || "");
    const data = { person: person.entity_id };
    if (roleChanged) {
      const retro = retroactiveDays(form.valid_from, this.today);
      if (retro > 0 && !form.confirm) { form.confirm = true; this.render(); return; }
      data.role = form.role; data.valid_from = form.valid_from;
    } else {
      const first = person.roles[0];             // only the short name changed: rewrite the first entry as it is
      data.role = first.role; data.valid_from = first.valid_from;
    }
    if (shortChanged || !isResident) data.short_name = form.short_name.trim();
    delete this._forms[person.id];
    await this.write("set_role", data, this.t.applied);
  }

  async on_remove_step(el) {
    await this.write("remove_role", { person: this._person(el.dataset.id).entity_id, valid_from: el.dataset.date });
  }

  async on_move(el) {
    const ordered = activeResidents(this._overview).map((r) => r.id);
    const moved = moveInList(ordered, el.dataset.id, Number(el.dataset.dir));
    await this.write("set_order", { person: moved.map((id) => this._person(id).entity_id) });
  }

  _parts(person, index, count) {
    const t = this.t;
    const isResident = person.role_today && person.role_today !== "none";
    const past = person.roles.filter((s) => s.valid_from <= this.today);
    const current = past.length ? past[past.length - 1] : null;
    const form = this._form(person.id);
    const id = esc(person.id);
    const roleOptions = ["pupil", "adult", "none"].map((r) => `<option value="${r}" ${form.role === r ? "selected" : ""}>${esc(t.role[r])}</option>`).join("");
    const status = isResident && current
      ? `${esc(t.role[person.role_today])} <span class="muted">${esc(t.since)} ${esc(shortDate(current.valid_from, this.lang))}</span>`
      : `<span class="muted">${esc(t.not_resident)}</span>`;
    const roleChanged = form.dirty && (!isResident || form.role !== person.role_today);
    const editor = `<label class="field">${esc(t.short_name)}<input size="2" maxlength="2" value="${esc(form.short_name)}" data-action="form_short" data-on="input" data-id="${id}"></label>
      <label class="field">${esc(t.new_role)}<select data-action="form_role" data-on="change" data-id="${id}">${roleOptions}</select></label>
      ${roleChanged ? `<label class="field">${esc(t.valid_from)}<input type="date" value="${form.valid_from}" data-action="form_date" data-on="change" data-id="${id}"></label>` : ""}
      ${form.dirty ? `<button class="primary" data-action="set_role" data-on="click" data-id="${id}">${esc(t.apply)}</button>
      <button data-action="form_cancel" data-on="click" data-id="${id}">${esc(t.cancel)}</button>` : ""}`;
    const confirm = form.confirm ? `<div class="confirm">${esc(t.retro(retroactiveDays(form.valid_from, this.today)))}
        <button class="primary" data-action="set_role" data-on="click" data-id="${id}">${esc(t.yes)}</button>
        <button data-action="cancel_confirm" data-on="click" data-id="${id}">${esc(t.cancel)}</button></div>` : "";
    const history = person.roles.length ? `<details><summary>${esc(t.history)}</summary>${person.roles.map((s, i) =>
      `<div class="step"><span>${esc(t.since)} ${esc(shortDate(s.valid_from, this.lang))}: ${esc(t.role[s.role])}</span>${i > 0 ? `<button data-action="remove_step" data-on="click" data-id="${id}" data-date="${s.valid_from}">${esc(t.remove)}</button>` : ""}</div>`).join("")}</details>` : "";
    const order = isResident ? `<button class="icon" data-action="move" data-on="click" data-id="${id}" data-dir="-1" aria-label="${esc(t.order)} ↑" ${index === 0 ? "disabled" : ""}>↑</button>
      <button class="icon" data-action="move" data-on="click" data-id="${id}" data-dir="1" aria-label="${esc(t.order)} ↓" ${index === count - 1 ? "disabled" : ""}>↓</button>` : "";
    return { status, editor, confirm, history, order };
  }

  render() {
    const t = this.t;
    if (!this._overview) { this.card(this._config.title, `<div class="muted">${t.loading}</div>`); return; }
    const active = activeResidents(this._overview);
    const others = this._overview.persons.filter((p) => !active.includes(p));
    const persons = [...active, ...others];
    let body;
    if (this._narrow) {
      body = persons.map((p) => {
        const x = this._parts(p, active.indexOf(p), active.length);
        return `<div class="block"><div class="name">${esc(p.name)} <span class="muted">— ${x.status}</span></div>
          <div class="row">${x.editor}</div>${x.confirm}<div class="row">${x.order}</div>${x.history}</div>`;
      }).join("");
    } else {
      const rows = persons.map((p) => {
        const x = this._parts(p, active.indexOf(p), active.length);
        return `<tr><td><b>${esc(p.name)}</b><br>${x.status}</td><td><div class="row">${x.editor}</div>${x.confirm}${x.history}</td><td>${x.order}</td></tr>`;
      }).join("");
      body = `<table><thead><tr><th>${esc(t.person)}</th><th>${esc(t.short_name)} · ${esc(t.new_role)}</th><th>${esc(t.order)}</th></tr></thead><tbody>${rows}</tbody></table>`;
    }
    this.card(this._config.title, body);
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
    this._forms = {};      // area id → {residents, valid_from, morning_rule, evening_rule, confirm, dirty}
  }

  async load() {
    if (!this._hass) return;
    try { this._overview = await this.callWithResponse("get_overview", {}); } catch (err) { this.fail(err); return; }
    this._forms = {};
    this.render();
  }

  _room(id) { return this._overview.rooms.find((r) => r.id === id); }
  _person(id) { return this._overview.persons.find((p) => p.id === id); }

  _form(room) {
    if (!this._forms[room.id]) {
      this._forms[room.id] = { residents: room.residents_today.slice(), valid_from: this.today,
        morning_rule: room.morning_rule || "day_off_wins", evening_rule: room.evening_rule || "workday_wins",
        confirm: false, dirty: false };
    }
    return this._forms[room.id];
  }

  _touch(el) { const form = this._form(this._room(el.dataset.area)); form.dirty = true; form.confirm = false; return form; }
  on_room_remove(el) { const f = this._touch(el); f.residents = f.residents.filter((id) => id !== el.dataset.id); this.render(); }
  on_room_add(el) { if (!el.value) return; this._touch(el).residents.push(el.value); this.render(); }
  on_room_date(el) { this._touch(el).valid_from = el.value; this.render(); }
  on_room_rule(el) { this._touch(el)[el.dataset.rule] = el.value; this.render(); }
  on_room_cancel(el) { delete this._forms[el.dataset.area]; this.render(); }

  _residentsChanged(room, form) {
    const before = room.residents_today.slice().sort().join(","), after = form.residents.slice().sort().join(",");
    return before !== after;
  }

  async on_room_apply(el) {
    const room = this._room(el.dataset.area);
    const form = this._form(room);
    const data = { area: room.id };
    if (this._residentsChanged(room, form)) {
      const retro = retroactiveDays(form.valid_from, this.today);
      if (retro > 0 && !form.confirm) { form.confirm = true; this.render(); return; }
      data.person = form.residents.map((id) => this._person(id).entity_id);
      data.valid_from = form.valid_from;
    }
    if (form.morning_rule !== (room.morning_rule || "day_off_wins")) data.morning_rule = form.morning_rule;
    if (form.evening_rule !== (room.evening_rule || "workday_wins")) data.evening_rule = form.evening_rule;
    await this.write("set_room", data, this.t.applied);
  }

  async on_room_remove_step(el) {
    await this.write("remove_room_assignment", { area: el.dataset.area, valid_from: el.dataset.date });
  }

  _ruleSelect(room, form, key) {
    const t = this.t;
    return `<label class="field">${esc(key === "morning_rule" ? t.morning : t.evening)}<select data-action="room_rule" data-on="change" data-area="${esc(room.id)}" data-rule="${key}" title="${esc(t.rule_hint[form[key]])}">${["day_off_wins", "workday_wins"].map((r) => `<option value="${r}" ${form[key] === r ? "selected" : ""}>${esc(t.rule[r])} — ${esc(t.rule_hint[r])}</option>`).join("")}</select></label>`;
  }

  _parts(room) {
    const t = this.t;
    const form = this._form(room);
    const area = esc(room.id);
    const chips = form.residents.map((id) => `<span class="chip on">${esc(this._person(id)?.name || id)}<button data-action="room_remove" data-on="click" data-area="${area}" data-id="${esc(id)}" aria-label="${esc(t.remove)}" title="${esc(t.remove)}">✕</button></span>`).join("");
    const candidates = activeResidents(this._overview).filter((r) => !form.residents.includes(r.id));
    const add = `<select data-action="room_add" data-on="change" data-area="${area}" aria-label="${esc(t.add)}"><option value="">+ ${esc(t.add)}</option>${candidates.map((r) => `<option value="${esc(r.id)}">${esc(r.name)}</option>`).join("")}</select>`;
    const residentsChanged = form.dirty && this._residentsChanged(room, form);
    const apply = form.dirty ? `<div class="row">${residentsChanged ? `<label class="field">${esc(t.change_from)}<input type="date" value="${form.valid_from}" data-action="room_date" data-on="change" data-area="${area}"></label>` : ""}
        <button class="primary" data-action="room_apply" data-on="click" data-area="${area}">${esc(t.apply)}</button>
        <button data-action="room_cancel" data-on="click" data-area="${area}">${esc(t.cancel)}</button></div>` : "";
    const confirm = form.confirm ? `<div class="confirm">${esc(t.retro(retroactiveDays(form.valid_from, this.today)))}
        <button class="primary" data-action="room_apply" data-on="click" data-area="${area}">${esc(t.yes)}</button>
        <button data-action="room_cancel" data-on="click" data-area="${area}">${esc(t.cancel)}</button></div>` : "";
    const history = room.assignments.length ? `<details><summary>${esc(t.history)}</summary>${room.assignments.map((s, i) =>
      `<div class="step"><span>${esc(t.since)} ${esc(shortDate(s.valid_from, this.lang))}: ${esc(s.residents.map((id) => this._person(id)?.name || id).join(", ") || t.no_residents)}</span>${i > 0 ? `<button data-action="room_remove_step" data-on="click" data-area="${area}" data-date="${s.valid_from}">${esc(t.remove)}</button>` : ""}</div>`).join("")}</details>` : "";
    const rules = this._ruleSelect(room, form, "morning_rule") + this._ruleSelect(room, form, "evening_rule");
    return { chips: chips || `<span class="muted">${esc(t.no_residents)}</span>`, add, apply, confirm, history, rules };
  }

  render() {
    const t = this.t;
    if (!this._overview) { this.card(this._config.title, `<div class="muted">${t.loading}</div>`); return; }
    const rooms = [...this._overview.rooms].sort((a, b) => (b.residents_today.length > 0) - (a.residents_today.length > 0) || a.name.localeCompare(b.name));
    const house = this._overview.house;
    const houseChips = house.residents_today.map((id) => `<span class="chip on">${esc(this._person(id)?.name || id)}</span>`).join("") || `<span class="muted">${esc(t.no_residents)}</span>`;
    const houseInfo = `<span class="muted">${esc(house.roles.map((r) => t.role[r]).join(", "))} · ${esc(t.morning)}: ${esc(t.rule[house.morning_rule])} · ${esc(t.evening)}: ${esc(t.rule[house.evening_rule])} — ${esc(t.house_hint)}</span>`;
    const empty = activeResidents(this._overview).length ? "" : `<div class="hint">${esc(t.no_residents_yet)}</div>`;
    let body;
    if (this._narrow) {
      body = rooms.map((room) => { const x = this._parts(room); return `<div class="block"><div class="name">${esc(room.name)}</div><div>${x.chips} ${x.add}</div>${x.apply}${x.confirm}<div class="row">${x.rules}</div>${x.history}</div>`; }).join("")
        + `<div class="block"><div class="name">${esc(t.house)}</div><div>${houseChips}</div>${houseInfo}</div>`;
    } else {
      const rows = rooms.map((room) => { const x = this._parts(room); return `<tr><td><b>${esc(room.name)}</b></td><td>${x.chips} ${x.add}${x.apply}${x.confirm}${x.history}</td><td><div class="row">${x.rules}</div></td></tr>`; }).join("");
      body = `<table><thead><tr><th>${esc(t.room)}</th><th>${esc(t.residents)}</th><th>${esc(t.morning)} / ${esc(t.evening)}</th></tr></thead><tbody>${rows}
        <tr><td><b>${esc(t.house)}</b></td><td>${houseChips}<br>${houseInfo}</td><td></td></tr></tbody></table>`;
    }
    this.card(this._config.title, empty + body);
  }
}

// --- editor ----------------------------------------------------------------------------------

class WerktagsCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) { this._hass = hass; this._render(); }

  _render() {
    if (!this._config) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const t = texts(this._hass?.locale?.language || this._hass?.language);
    const showWeeks = this._config.type === "custom:werktags-calendar";
    this.shadowRoot.innerHTML = `<style>label { display: block; margin: 8px 0; } input { font: inherit; padding: 4px; }</style>
      <label>${esc(t.title)} <input id="title" value="${esc(this._config.title || "")}"></label>
      ${showWeeks ? `<label>${esc(t.weeks)} <input id="weeks" type="number" min="1" max="26" value="${Number(this._config.weeks) || 5}"></label>` : ""}`;
    this.shadowRoot.querySelectorAll("input").forEach((input) => input.addEventListener("change", () => this._changed()));
  }

  _changed() {
    const title = this.shadowRoot.getElementById("title").value;
    const weeks = this.shadowRoot.getElementById("weeks");
    const config = { ...this._config, title };
    if (weeks) config.weeks = Math.min(26, Math.max(1, Number(weeks.value) || 5));
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
  }
}

// --- registration ---------------------------------------------------------------------------

const CARDS = [
  ["werktags-calendar", WerktagsCalendarCard, "Werktags: calendar", "Weeks of days off per resident; tap to change."],
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
