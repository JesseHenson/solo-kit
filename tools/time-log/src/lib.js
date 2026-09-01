// Everything that isn't MCP wiring: storage, the roster, and the arithmetic.
// Kept apart from server.js so the parts that can be quietly wrong are testable.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export const STALE_HOURS = 8;
export const BUDGET_WARN_AT = 0.8;

// ------------------------------------------------------------------ storage

export function dataDir() {
  // A hidden dotfolder is invisible in Finder, which makes "your data is yours"
  // a claim rather than a fact. New installs get a folder people can find;
  // anyone with a log in the old place keeps it, untouched.
  const override = process.env.TIME_LOG_DIR;
  let dir;
  if (override) {
    dir = override;
  } else {
    const legacy = path.join(os.homedir(), ".time-log");
    dir = fs.existsSync(path.join(legacy, "entries.jsonl"))
      ? legacy
      : path.join(os.homedir(), "Documents", "Time Log");
  }
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

export const entriesFile = () => path.join(dataDir(), "entries.jsonl");
export const runningFile = () => path.join(dataDir(), "running.json");
export const rosterFile = () => path.join(dataDir(), "clients.json");

export function readEntries() {
  const f = entriesFile();
  if (!fs.existsSync(f)) return [];
  return fs.readFileSync(f, "utf8").split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l));
}

export function appendEntry(entry) {
  fs.appendFileSync(entriesFile(), JSON.stringify(entry) + "\n");
}

export function readRunning() {
  try {
    return JSON.parse(fs.readFileSync(runningFile(), "utf8"));
  } catch {
    return null;
  }
}

export function writeRunning(rec) {
  fs.writeFileSync(runningFile(), JSON.stringify(rec, null, 2));
}

export function clearRunning() {
  try {
    fs.unlinkSync(runningFile());
  } catch {}
}

export function loadRoster() {
  let data = {};
  try {
    data = JSON.parse(fs.readFileSync(rosterFile(), "utf8"));
  } catch {}
  data.clients ??= [];
  data.default_round_to ??= 1;
  // Older versions stored projects as bare strings; normalise on read so the
  // rest of the code only ever sees records.
  for (const c of data.clients) {
    c.projects = (c.projects ?? []).map((p) =>
      typeof p === "string" ? { name: p, budget_hours: null } : p);
    c.aliases ??= [];
  }
  return data;
}

export function saveRoster(roster) {
  fs.writeFileSync(rosterFile(), JSON.stringify(roster, null, 2) + "\n");
}

// --------------------------------------------------------------------- time

export function isoLocal(d = new Date()) {
  // Local time with its offset, so a log read months later still says when.
  const pad = (n) => String(Math.floor(Math.abs(n))).padStart(2, "0");
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}` +
    `${sign}${pad(off / 60)}:${pad(off % 60)}`;
}

export const dayKey = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export const entryDay = (entry) => dayKey(new Date(entry.start));

export function roundMinutes(minutes, increment) {
  // Up to the next increment, which is how billable time is normally cut.
  if (increment <= 1) return Math.round(minutes);
  return increment * Math.ceil(minutes / increment);
}

export function resolveWindow(since, until, today) {
  // A phrase or an ISO date becomes an inclusive [start, end] pair of day keys.
  const at = (y, m, d) => new Date(y, m, d);
  const monday = at(today.getFullYear(), today.getMonth(),
    today.getDate() - ((today.getDay() + 6) % 7));
  const phrase = (since ?? "all").trim().toLowerCase();
  let start;
  let end;

  if (["all", "", "everything"].includes(phrase)) {
    start = at(1970, 0, 1);
    end = at(9999, 11, 31);
  } else if (phrase === "today") {
    start = end = today;
  } else if (phrase === "yesterday") {
    start = end = at(today.getFullYear(), today.getMonth(), today.getDate() - 1);
  } else if (phrase === "this week") {
    start = monday;
    end = at(monday.getFullYear(), monday.getMonth(), monday.getDate() + 6);
  } else if (phrase === "last week") {
    start = at(monday.getFullYear(), monday.getMonth(), monday.getDate() - 7);
    end = at(monday.getFullYear(), monday.getMonth(), monday.getDate() - 1);
  } else if (phrase === "this month") {
    start = at(today.getFullYear(), today.getMonth(), 1);
    end = at(today.getFullYear(), today.getMonth() + 1, 0);
  } else if (phrase === "last month") {
    start = at(today.getFullYear(), today.getMonth() - 1, 1);
    end = at(today.getFullYear(), today.getMonth(), 0);
  } else {
    const [y, m, d] = phrase.split("-").map(Number);
    start = end = at(y, m - 1, d);
  }
  if (until) {
    const [y, m, d] = until.split("-").map(Number);
    end = at(y, m - 1, d);
  }
  return [dayKey(start), dayKey(end)];
}

// ------------------------------------------------------------------- roster

export function resolveClient(name, roster) {
  const n = name.trim().toLowerCase();
  for (const c of roster.clients) {
    if (c.name.trim().toLowerCase() === n) return c.name;
    if (c.aliases.some((a) => a.trim().toLowerCase() === n)) return c.name;
  }
  return null;
}

export function clientRecord(name, roster) {
  const canonical = resolveClient(name, roster);
  return roster.clients.find((c) => c.name === canonical) ?? null;
}

export function resolveProject(client, project, roster) {
  const rec = clientRecord(client, roster);
  if (!rec) return null;
  const p = project.trim().toLowerCase();
  return rec.projects.find((x) => x.name.trim().toLowerCase() === p)?.name ?? null;
}

export function unknownClientNote(name, roster) {
  if (!roster.clients.length) return "";
  const known = roster.clients.map((c) => c.name).join(", ");
  return `\nNOTE: '${name}' is not on the roster (${known}). If it's a new client, call ` +
    "add_client. If it's a different spelling of one of those, say so and log it under the " +
    "roster spelling instead.";
}

export function unknownProjectNote(client, project, roster) {
  // Silent for a client with no projects on file, since plenty of people bill
  // straight to a client and should not be nagged about a concept they skipped.
  const rec = clientRecord(client, roster);
  if (!rec || !rec.projects.length) return "";
  if (resolveProject(client, project, roster)) return "";
  const known = rec.projects.map((x) => x.name).join(", ");
  return `\nNOTE: '${project}' isn't one of ${rec.name}'s projects (${known}). New project, or ` +
    "another spelling of one of those? Add it with add_client's projects argument once they confirm.";
}

// ------------------------------------------------------------------ reports

export function select(entries, client, project, start, end) {
  return entries.filter((e) => {
    if (client && (e.client ?? "").toLowerCase() !== client.toLowerCase()) return false;
    if (project && (e.project ?? "").toLowerCase() !== project.toLowerCase()) return false;
    const d = entryDay(e);
    return d >= start && d <= end;
  });
}

export function summarize(entries, increment = 1) {
  // Each line rounds where it bills; rounding an already-rounded total drifts.
  const groups = new Map();
  for (const e of entries) {
    const key = JSON.stringify([e.client ?? "(none)", e.project || "-"]);
    groups.set(key, (groups.get(key) ?? 0) + Number(e.minutes));
  }
  const rounded = [...groups].map(([key, m]) => {
    const [client, project] = JSON.parse(key);
    return { client, project, minutes: roundMinutes(m, increment) };
  });
  return {
    groups: rounded,
    total: rounded.reduce((a, g) => a + g.minutes, 0),
    count: entries.length,
  };
}

export const hours = (minutes) => (minutes / 60).toFixed(2);

export const money = (amount) =>
  "$" + amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function rateFor(client, roster) {
  return clientRecord(client, roster)?.rate_per_hour ?? null;
}

// ------------------------------------------------------------------ budgets

export function loggedHours(client, project, entries) {
  // Everything ever logged to this project: a budget spans the job, not a week.
  return entries
    .filter((e) => e.client === client && (e.project ?? "") === project)
    .reduce((a, e) => a + Number(e.minutes), 0) / 60;
}

export function budgetLines(roster, entries, only = null) {
  const out = [];
  for (const c of roster.clients) {
    if (only && c.name !== only) continue;
    for (const pj of c.projects) {
      if (!pj.budget_hours) continue;
      const used = loggedHours(c.name, pj.name, entries);
      const budget = Number(pj.budget_hours);
      out.push({
        client: c.name,
        project: pj.name,
        budget,
        used,
        left: budget - used,
        fraction: budget ? used / budget : 0,
      });
    }
  }
  return out;
}

export function budgetWarning(client, project, roster, entries) {
  // Said at the moment time is logged, which is the moment it can still matter.
  if (!project) return "";
  const b = budgetLines(roster, entries, client).find((x) => x.project === project);
  if (!b || b.fraction < BUDGET_WARN_AT) return "";
  if (b.left < 0) {
    return `\nBUDGET: ${b.project} is ${Math.abs(b.left).toFixed(2)}h over its ${b.budget}h ` +
      "budget. Say so now, this is work they may not be able to bill.";
  }
  return `\nBUDGET: ${b.project} is at ${b.used.toFixed(2)} of ${b.budget}h ` +
    `(${Math.round(b.fraction * 100)}%), ${b.left.toFixed(2)}h left. Mention it once.`;
}

export function versionCompare(a, b) {
  const parse = (v) => v.trim().replace(/^v/, "").split(".").map((x) => parseInt(x, 10) || 0);
  const [x, y] = [parse(a), parse(b)];
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) < (y[i] ?? 0) ? -1 : 1;
  }
  return 0;
}
