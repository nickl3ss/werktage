/**
 * Pure logic of the Werktags cards: dates, grid, "All" state, texts.
 * No DOM, no Home Assistant — testable with plain Node.
 */

export const DAY_OFF = "day_off";
export const WORKDAY = "workday";
export const DEFAULT = "default";
export const MS_PER_DAY = 86400000;

// --- dates ---------------------------------------------------------------------------

/** "2026-10-01" → Date at UTC midnight (UTC keeps arithmetic free of DST). */
export function parseDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

export function toIso(date) {
  return date.toISOString().slice(0, 10);
}

export function addDays(iso, days) {
  return toIso(new Date(parseDate(iso).getTime() + days * MS_PER_DAY));
}

export function daysBetween(fromIso, toIso_) {
  return Math.round((parseDate(toIso_) - parseDate(fromIso)) / MS_PER_DAY);
}

/** Monday of the week containing the day. */
export function mondayOf(iso) {
  const date = parseDate(iso);
  const weekday = (date.getUTCDay() + 6) % 7; // Monday = 0
  return addDays(iso, -weekday);
}

export function todayIso(now = new Date()) {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

/** ISO week number (1–53). */
export function isoWeek(iso) {
  const date = parseDate(iso);
  const thursday = new Date(date.getTime() + ((4 - ((date.getUTCDay() + 6) % 7 + 1)) * MS_PER_DAY));
  const yearStart = Date.UTC(thursday.getUTCFullYear(), 0, 1);
  return Math.ceil(((thursday - yearStart) / MS_PER_DAY + 1) / 7);
}

/** Short date for the calendar cell: TT.MM.JJ in German, locale default otherwise. */
export function shortDate(iso, language) {
  const [y, m, d] = iso.split("-");
  if ((language || "en").toLowerCase().startsWith("de")) return `${d}.${m}.${y.slice(2)}`;
  return new Intl.DateTimeFormat(language || "en", { day: "2-digit", month: "2-digit", year: "2-digit", timeZone: "UTC" })
    .format(parseDate(iso));
}

export function longDate(iso, language) {
  return new Intl.DateTimeFormat(language || "en", { weekday: "short", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })
    .format(parseDate(iso));
}

/** Short weekday names Monday..Sunday in the user's language (e.g. "Mo", "Tue"). */
export function weekdayNames(language) {
  const fmt = new Intl.DateTimeFormat(language || "en", { weekday: "short", timeZone: "UTC" });
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(Date.UTC(2024, 0, 1 + i))));   // 2024-01-01 is a Monday
}

/** True if two lists hold the same members regardless of order. */
export function sameMembers(a, b) {
  const x = [...a].sort().join(","), y = [...b].sort().join(",");
  return x === y;
}

export function monthName(iso, language) {
  return new Intl.DateTimeFormat(language || "en", { month: "long", timeZone: "UTC" }).format(parseDate(iso));
}

// --- grid ----------------------------------------------------------------------------

/** The days of a get_days response as rows of seven, each day with its ISO week. */
export function weekRows(days) {
  const rows = [];
  for (let i = 0; i < days.length; i += 7) {
    const week = days.slice(i, i + 7);
    rows.push({ week: isoWeek(week[0].date), days: week });
  }
  return rows;
}

/** State of the "All" toggle for one day: "all" | "none" | "some" | "empty". */
export function allState(day, residents) {
  const infos = residents.map((r) => day.persons[r.id]).filter(Boolean);
  if (!infos.length) return "empty";
  const off = infos.filter((p) => p.effective === DAY_OFF).length;
  return off === infos.length ? "all" : off === 0 ? "none" : "some";
}

/**
 * What tapping a resident's toggle should set: the opposite of today's effective day.
 * Returns the `status` for set_days.
 */
export function toggleStatus(personInfo) {
  return personInfo.effective === DAY_OFF ? WORKDAY : DAY_OFF;
}

/** What tapping "All" should set (P18): all off unless everybody is off already, then all workday. */
export function allToggleStatus(day, residents) {
  return allState(day, residents) === "all" ? WORKDAY : DAY_OFF;
}

/** CSS classes for a day cell. */
export function dayClasses(day, todayIso_) {
  const classes = [];
  if (day.weekend) classes.push("weekend");
  if (day.public_holiday) classes.push("public-holiday");
  if (day.school_holiday) classes.push("school-holiday");
  if (day.date === todayIso_) classes.push("today");
  return classes;
}

/** True when the day's date is the first of a month (a month label is shown). */
export function startsMonth(iso) {
  return iso.slice(8) === "01";
}

// --- period card -------------------------------------------------------------------------

export function validRange(start, end, maxDays = 366) {
  if (!start || !end) return "missing";
  if (daysBetween(start, end) < 0) return "end_before_start";
  if (daysBetween(start, end) + 1 > maxDays) return "too_long";
  return null;
}

// --- residents / rooms ---------------------------------------------------------------

/** Days a change "valid from" would rewrite in the past (0 if the date is today or later). */
export function retroactiveDays(validFrom, todayIso_) {
  const days = daysBetween(validFrom, todayIso_);
  return days > 0 ? days : 0;
}

/** Residents with a role today, in card order. */
export function activeResidents(overview) {
  return overview.persons
    .filter((p) => p.role_today && p.role_today !== "none")
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || a.name.localeCompare(b.name));
}

/** Short name proposal for a new resident: first letter, made unique among the taken ones. */
export function proposeShortName(name, taken) {
  const base = (name.trim()[0] || "?").toUpperCase();
  if (!taken.includes(base)) return base;
  const second = (name.trim().slice(0, 2) || base).toUpperCase();
  if (!taken.includes(second)) return second;
  for (let i = 2; i < 10; i += 1) if (!taken.includes(base + i)) return base + i;
  return base;
}

/** Move an id one step up or down in a list; returns a new list. */
export function moveInList(ids, id, direction) {
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
    rule_hint: { day_off_wins: "one resident off is enough", workday_wins: "one resident working is enough" },
    rules_need_residents: "rules appear once residents are assigned",
    legend: "Legend", legend_off: "day off", legend_work: "workday", legend_exc: "exception", legend_school: "school holidays",
    legend_weekend: "weekend / public holiday", legend_unknown: "unknown (counts as workday)",
    reset_day: "Everyone to default", confirm_all_work: "Set everyone to workday on a day off?",
    no_residents_yet: "No residents yet. Add them on the “Residents” page.",
    known_until: (d) => `School holidays known until ${d}`, not_fetched: "School holidays not fetched yet",
    title: "Title", weeks: "Weeks", date_changed_hint: "Role from",
    what: "What?", who: "Who?", when: "When?", from: "From", to: "To", apply: "Apply", cancel: "Cancel",
    preview: "Preview", changes: (n) => `${n} day${n === 1 ? "" : "s"} change`, nothing_changes: "nothing changes",
    applied: "Applied.", error: "Failed", end_before_start: "The last day lies before the first day.",
    too_long: "At most 366 days.", missing: "Choose first and last day.", choose_person: "Choose at least one person.",
    person: "Person", short_name: "Short", role_today: "Role today", since: "since", new_role: "New role", valid_from: "valid from",
    history: "History", remove: "Remove", retro: (n) => `Changes ${n} day${n === 1 ? "" : "s"} retroactively — apply?`,
    yes: "Yes", room: "Room", residents: "Residents", morning: "Morning", evening: "Evening", change_from: "Change from",
    add: "Add", no_residents: "no residents", house: "House", house_hint: "House roles and rules are set in the integration options.",
    house_by_role: "by role — remove everyone to return to it", house_chosen: "chosen residents",
    weekly: "Days off every week", weekly_household: "household weekend", weekly_personal: "personal",
    weekly_reset: "Household weekend",
    loading: "Loading…", not_set_up: "Werktags is not set up.", school_holidays: "School holidays",
    known_to: "known until", fetched: "fetched", never: "never", no_role: "No role", order: "Order",
  },
  de: {
    all: "Alle", today: "Heute", week: "KW", prev_weeks: "Früher", next_weeks: "Später",
    workday: "Werktag", day_off: "Frei", default: "Standard (Ausnahmen entfernen)",
    before_workday: "Abend vor Werktag", before_day_off: "Abend vor freiem Tag",
    reason: { workday: "Werktag", weekend: "Wochenende", public_holiday: "Feiertag", school_holiday: "Schulferien",
      exception_day_off: "Ausnahme: frei", exception_workday: "Ausnahme: Werktag", unknown: "Unbekannt (gilt als Werktag)" },
    role: { pupil: "Schüler", adult: "Erwachsener", none: "Keine" }, not_resident: "kein Bewohner",
    rule: { day_off_wins: "Frei gewinnt", workday_wins: "Arbeit gewinnt" },
    rule_hint: { day_off_wins: "ein Bewohner mit freiem Tag genügt", workday_wins: "ein arbeitender Bewohner genügt" },
    rules_need_residents: "Regeln erscheinen, sobald Bewohner zugeordnet sind",
    legend: "Legende", legend_off: "frei", legend_work: "Werktag", legend_exc: "Ausnahme", legend_school: "Schulferien",
    legend_weekend: "Wochenende / Feiertag", legend_unknown: "unbekannt (gilt als Werktag)",
    reset_day: "Alle auf Standard", confirm_all_work: "Alle an einem freien Tag auf Werktag setzen?",
    no_residents_yet: "Noch keine Bewohner. Lege sie auf der Seite „Bewohner“ an.",
    known_until: (d) => `Schulferien bekannt bis ${d}`, not_fetched: "Schulferien noch nicht abgerufen",
    title: "Titel", weeks: "Wochen", date_changed_hint: "Rolle ab",
    what: "Was?", who: "Wer?", when: "Wann?", from: "Von", to: "Bis", apply: "Übernehmen", cancel: "Abbrechen",
    preview: "Vorschau", changes: (n) => `${n} Tag${n === 1 ? "" : "e"} ändern sich`, nothing_changes: "nichts ändert sich",
    applied: "Übernommen.", error: "Fehlgeschlagen", end_before_start: "Der letzte Tag liegt vor dem ersten.",
    too_long: "Höchstens 366 Tage.", missing: "Ersten und letzten Tag wählen.", choose_person: "Mindestens eine Person wählen.",
    person: "Person", short_name: "Kürzel", role_today: "Rolle heute", since: "seit", new_role: "Neue Rolle", valid_from: "gültig ab",
    history: "Verlauf", remove: "Löschen", retro: (n) => `Ändert ${n} Tag${n === 1 ? "" : "e"} rückwirkend — übernehmen?`,
    yes: "Ja", room: "Raum", residents: "Bewohner", morning: "Morgens", evening: "Abends", change_from: "Ändern ab",
    add: "Hinzufügen", no_residents: "keine Bewohner", house: "Haus", house_hint: "Rollen und Regeln des Hauses werden in den Optionen der Integration eingestellt.",
    house_by_role: "nach Rolle — alle entfernen, um dorthin zurückzukehren", house_chosen: "gewählte Bewohner",
    weekly: "Freie Wochentage", weekly_household: "Wochenende des Haushalts", weekly_personal: "persönlich",
    weekly_reset: "Wochenende des Haushalts",
    loading: "Lade…", not_set_up: "Werktags ist nicht eingerichtet.", school_holidays: "Schulferien",
    known_to: "bekannt bis", fetched: "abgerufen", never: "nie", no_role: "Keine Rolle", order: "Reihenfolge",
  },
};

export function texts(language) {
  return (language || "en").toLowerCase().startsWith("de") ? TEXTS.de : TEXTS.en;
}

/** Escape text for innerHTML. */
export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
