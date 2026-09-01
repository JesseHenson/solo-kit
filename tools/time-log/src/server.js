#!/usr/bin/env node
// time-log: a timer and timesheets over one plaintext file the user owns.
//
//   <data dir>/entries.jsonl   one JSON object per finished session
//   <data dir>/running.json    the timer in flight, if any
//   <data dir>/clients.json    the roster: clients, projects, rates, budgets
//
// The data dir is Documents/Time Log unless TIME_LOG_DIR says otherwise.
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { execFile, spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  BUDGET_WARN_AT, STALE_HOURS, appendEntry, budgetLines, budgetWarning, clearRunning,
  clientRecord, dataDir, dayKey, entryDay, hours, isoLocal, loadRoster, loggedHours, money,
  rateFor, readEntries, readRunning, resolveClient, resolveProject, resolveWindow, roundMinutes,
  rosterFile, saveRoster, select, summarize, unknownClientNote, unknownProjectNote, versionCompare,
  writeRunning,
} from "./lib.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));

// The tool root is wherever manifest.json is: one level up when running from
// src/, or right here when running the single bundled file.
const ROOT = (() => {
  let dir = HERE;
  for (let i = 0; i < 4; i++) {
    if (fs.existsSync(path.join(dir, "manifest.json"))) return dir;
    dir = path.join(dir, "..");
  }
  return path.join(HERE, "..");
})();
const RELEASES = "https://api.github.com/repos/JesseHenson/solo-kit/releases/latest";
const DOWNLOAD = "https://github.com/JesseHenson/solo-kit/releases/latest/download/time-log.mcpb";

const VERSION = (() => {
  // From the manifest, so a release bumps one number in one file.
  try {
    return JSON.parse(fs.readFileSync(path.join(ROOT, "manifest.json"), "utf8")).version;
  } catch {
    return "0";
  }
})();

const reference = (name) => {
  const f = path.join(ROOT, "skill", "references", `${name}.md`);
  return fs.existsSync(f) ? fs.readFileSync(f, "utf8") : `No reference named ${name}.`;
};

// -------------------------------------------------------------- instructions

// Some clients read only the first few hundred characters of this field, so the
// rules that apply to every call come before anything discursive.
const LEAD = `A timer and timesheets over one plaintext file the user owns. Rules for every call:
one timer at a time; every entry needs a client; pass whatever spelling the user
typed and the server resolves it to the roster below; never round a report unless
they said they bill that way; quote the numbers the tools return rather than
recomputing them. Tools: start_timer, stop_timer, current_timer, log_entry,
timesheet_report, add_client, list_clients, remove_client, remove_project,
set_budget, budget_status, set_default_rounding, dashboard.

`;

const REFERENCES = `

## Deeper guidance, read only when it applies

- \`guide://invoicing\` — before drafting an invoice or working out what someone
  is owed. Covers rates, line grouping, and what never to invent.
- \`guide://reviewing\` — before reading a week or month back to the user.
- \`guide://budgets\` — before setting a budget, or if they ask to be checked on
  a schedule.

Read the one that applies before you start, not after. Don't read either for an
ordinary timer or report question.`;

function skillBody() {
  const f = path.join(ROOT, "skill", "SKILL.md");
  if (!fs.existsSync(f)) return "Track billable time in a plaintext log.";
  let text = fs.readFileSync(f, "utf8");
  if (text.startsWith("---")) text = text.split("---").slice(2).join("---");
  return text.trim();
}

function firstRunBanner() {
  const logged = readEntries().length > 0;
  if (logged || loadRoster().clients.length) return "";
  return "STATUS: nothing has ever been logged — this is a fresh install. " +
    "Follow the First run section below before anything else.\n\n";
}

function rosterSummary() {
  // Appended so the roster is known without a tool call, in every conversation.
  const roster = loadRoster();
  if (!roster.clients.length) {
    const names = [...new Set(readEntries().map((e) => e.client).filter(Boolean))].sort();
    if (!names.length) return "";
    return "\n\n## No roster yet\n\nNothing is on the roster, but the log already has entries " +
      `for: ${names.join(", ")}. Offer once to put those on the roster with add_client so they ` +
      "stop being retyped and can't drift into two spellings. If they decline, drop it.";
  }
  const lines = ["\n\n## This user's roster\n"];
  for (const c of roster.clients) {
    const bits = [c.name];
    if (c.aliases.length) bits.push("also called " + c.aliases.join(", "));
    if (c.projects.length) {
      bits.push("projects: " + c.projects
        .map((x) => x.name + (x.budget_hours ? ` (budget ${x.budget_hours}h)` : ""))
        .join(", "));
    }
    if (c.rate_per_hour) bits.push(`$${c.rate_per_hour}/hr`);
    lines.push("- " + bits.join(" — "));
  }
  const r = roster.default_round_to;
  lines.push(`\nDefault rounding: ${r} minute(s)` +
    (r <= 1 ? " — i.e. exact time." : ", applied unless asked otherwise."));
  lines.push("Use these spellings. Don't ask for a client name you can infer from this list.");
  return lines.join("\n");
}

function budgetNote() {
  const rows = budgetLines(loadRoster(), readEntries()).filter((b) => b.fraction >= BUDGET_WARN_AT);
  if (!rows.length) return "";
  const lines = ["\n\n## Budgets worth knowing about\n"];
  for (const b of rows.sort((a, z) => z.fraction - a.fraction)) {
    const state = b.left < 0
      ? `${Math.abs(b.left).toFixed(2)}h over`
      : `${b.left.toFixed(2)}h left of ${b.budget}h`;
    lines.push(`- ${b.client} / ${b.project} — ${state} (${Math.round(b.fraction * 100)}%)`);
  }
  lines.push("\nMention this once if they log to one of these. Don't open with it.");
  return lines.join("\n");
}

function elapsedHours(rec) {
  return (Date.now() - new Date(rec.start).getTime()) / 3_600_000;
}

function runningNote() {
  // The timer lives in a file, so it outlives the conversation that started it.
  const rec = readRunning();
  if (!rec) return "";
  const elapsed = elapsedHours(rec);
  if (elapsed >= STALE_HOURS) return "";
  const who = rec.client + (rec.project ? ` / ${rec.project}` : "");
  return `\n\n## A timer is running\n\n${who}, ${elapsed.toFixed(2)}h so far, started ` +
    `${rec.start}. It may have been started in another conversation — the timer is a file, ` +
    "not chat history. Don't start another; stop this one or ask.";
}

function staleTimerNote() {
  const rec = readRunning();
  if (!rec) return "";
  const elapsed = elapsedHours(rec);
  if (elapsed < STALE_HOURS) return "";
  return `\n\n## A timer has been running ${Math.round(elapsed)} hours\n\n${rec.client}, ` +
    `started ${rec.start}. That's usually a timer left on overnight, not real work. Say so ` +
    "before doing anything else, and offer to stop it with the right end time using " +
    "stop_timer, or to correct it with log_entry.";
}

async function updateNote() {
  // A bundle install has no update path, so without this someone simply never
  // learns a newer version exists. Reads a public release tag and nothing else.
  if (process.env.TIME_LOG_NO_UPDATE_CHECK) return "";
  const cache = path.join(dataDir(), ".update-check.json");
  let latest = "";
  try {
    const seen = JSON.parse(fs.readFileSync(cache, "utf8"));
    if (Date.now() - seen.at < 86_400_000) latest = seen.latest;
  } catch {}
  if (!latest) {
    try {
      const res = await fetch(RELEASES, {
        headers: { accept: "application/vnd.github+json" },
        signal: AbortSignal.timeout(2000),
      });
      latest = (await res.json()).tag_name ?? "";
      fs.writeFileSync(cache, JSON.stringify({ latest, at: Date.now() }));
    } catch {
      return ""; // offline, rate-limited, whatever: never block startup
    }
  }
  if (!latest || versionCompare(latest, VERSION) <= 0) return "";
  return `\n\n## Update available\n\nThey're running ${VERSION}; ${latest} is out. Mention it ` +
    `once, in a sentence, then carry on with what they asked: download ${DOWNLOAD} and open ` +
    "it, and Claude Desktop replaces the tool. Their log is untouched. Don't raise it again.";
}

async function instructions() {
  return firstRunBanner() + LEAD + skillBody() + REFERENCES +
    rosterSummary() + budgetNote() + runningNote() + staleTimerNote() + await updateNote();
}

// ------------------------------------------------------------ notifications

export function notify(title, message) {
  // A real Notification Centre banner. The dashboard can't do this itself: a
  // file:// page has an opaque origin, so browsers refuse it permission.
  if (process.platform !== "darwin") return false;
  const script = `display notification ${JSON.stringify(message)} with title ` +
    `${JSON.stringify(title)} sound name "Ping"`;
  try {
    execFile("osascript", ["-e", script], { timeout: 15000 }, () => {});
    return true;
  } catch {
    return false;
  }
}

async function watchLoop() {
  // Polls while a timer runs, buzzes once per threshold, exits when it stops.
  const fired = new Set();
  const deadline = Date.now() + 12 * 3_600_000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 60_000));
    const rec = readRunning();
    if (!rec) break;
    const elapsed = elapsedHours(rec);
    const key = rec.start;
    if (elapsed >= STALE_HOURS && !fired.has(`${key}:stale`)) {
      fired.add(`${key}:stale`);
      notify("Timer still running", `${rec.client} — ${Math.round(elapsed)} hours. Left on?`);
    }
    if (!rec.project) continue;
    const b = budgetLines(loadRoster(), readEntries(), rec.client)
      .find((x) => x.project === rec.project);
    if (!b) continue;
    const live = b.used + elapsed;
    if (live >= b.budget && !fired.has(`${key}:over`)) {
      fired.add(`${key}:over`);
      notify(`${rec.project} over budget`, `${live.toFixed(2)}h against a ${b.budget}h budget.`);
    } else if (live / b.budget >= BUDGET_WARN_AT && !fired.has(`${key}:warn`)) {
      fired.add(`${key}:warn`);
      notify(`${rec.project} at ${Math.round((live / b.budget) * 100)}%`,
        `${(b.budget - live).toFixed(2)}h left of ${b.budget}h.`);
    }
  }
  try {
    fs.unlinkSync(path.join(dataDir(), ".watch.pid"));
  } catch {}
}

function startWatcher() {
  // One watcher at a time, and never one for a timer that isn't running.
  if (!readRunning()) return "no timer running, so nothing to watch";
  const pidfile = path.join(dataDir(), ".watch.pid");
  if (fs.existsSync(pidfile)) {
    try {
      process.kill(Number(fs.readFileSync(pidfile, "utf8")), 0);
      return "already watching";
    } catch {
      try { fs.unlinkSync(pidfile); } catch {}
    }
  }
  try {
    const child = spawn(process.execPath, [fileURLToPath(import.meta.url), "--watch"], {
      detached: true, stdio: "ignore",
    });
    child.unref();
    fs.writeFileSync(pidfile, String(child.pid));
    return "watching — it'll buzz at 80% and again at the limit, and stop when you do";
  } catch (e) {
    return `couldn't start the watcher (${e.message})`;
  }
}

// -------------------------------------------------------------------- server

const server = new McpServer(
  { name: "time-log", version: VERSION },
  { instructions: await instructions() },
);

const text = (s) => ({ content: [{ type: "text", text: s }] });

server.registerTool("start_timer", {
  description: "Start the timer for a client. Fails if one is already running.",
  inputSchema: {
    client: z.string(), project: z.string().optional(), notes: z.string().optional(),
  },
}, async ({ client, project, notes }) => {
  const current = readRunning();
  if (current) {
    return text(`Timer already running for ${current.client} since ${current.start}. Stop it first.`);
  }
  const roster = loadRoster();
  const resolved = resolveClient(client, roster);
  let note = resolved ? "" : unknownClientNote(client, roster);
  client = resolved ?? client;
  if (project) {
    note += unknownProjectNote(client, project, roster);
    project = resolveProject(client, project, roster) ?? project;
  }
  const rec = { client, project: project ?? null, notes: notes ?? null, start: isoLocal() };
  writeRunning(rec);
  return text(`Started ${client}${project ? ` / ${project}` : ""} at ${rec.start}.` + note);
});

server.registerTool("stop_timer", {
  description: "Stop the running timer and write the session to the log.",
  inputSchema: { notes: z.string().optional() },
}, async ({ notes }) => {
  const rec = readRunning();
  if (!rec) return text("No timer running.");
  const end = new Date();
  const minutes = Math.round(((end - new Date(rec.start)) / 60_000) * 100) / 100;
  const entry = {
    client: rec.client, project: rec.project, start: rec.start, end: isoLocal(end),
    minutes, notes: notes ?? rec.notes ?? null,
  };
  appendEntry(entry);
  clearRunning();
  return text(`Logged ${hours(minutes)}h for ${entry.client}` +
    (entry.project ? ` / ${entry.project}` : "") +
    budgetWarning(entry.client, entry.project, loadRoster(), readEntries()));
});

server.registerTool("current_timer", {
  description: "Report what the timer is on right now, and for how long.",
  inputSchema: {},
}, async () => {
  const rec = readRunning();
  if (!rec) return text("No timer running.");
  const elapsed = elapsedHours(rec);
  let out = `${rec.client}${rec.project ? ` / ${rec.project}` : ""} — running ` +
    `${elapsed.toFixed(2)}h (since ${rec.start}).`;
  if (rec.project) {
    const b = budgetLines(loadRoster(), readEntries(), rec.client)
      .find((x) => x.project === rec.project);
    if (b) {
      const projected = b.used + elapsed;
      out += `\nBudget: ${projected.toFixed(2)} of ${b.budget}h counting this session ` +
        `(${Math.round((projected / b.budget) * 100)}%).`;
    }
  }
  if (elapsed >= STALE_HOURS) {
    out += `\nNOTE: ${Math.round(elapsed)} hours is long enough to be a timer left on by ` +
      "mistake. Check before logging it as worked time.";
  }
  return text(out);
});

server.registerTool("log_entry", {
  description: "Log time after the fact. `day` is YYYY-MM-DD, defaulting to today.",
  inputSchema: {
    client: z.string(), minutes: z.number(), project: z.string().optional(),
    notes: z.string().optional(), day: z.string().optional(),
  },
}, async ({ client, minutes, project, notes, day }) => {
  const roster = loadRoster();
  const resolved = resolveClient(client, roster);
  let note = resolved ? "" : unknownClientNote(client, roster);
  client = resolved ?? client;
  if (project) {
    note += unknownProjectNote(client, project, roster);
    project = resolveProject(client, project, roster) ?? project;
  }
  const when = day ? new Date(`${day}T00:00:00`) : new Date();
  const entry = {
    client, project: project ?? null, start: isoLocal(when),
    end: isoLocal(new Date(when.getTime() + minutes * 60_000)),
    minutes: Number(minutes), notes: notes ?? null,
  };
  appendEntry(entry);
  return text(`Logged ${hours(minutes)}h for ${client} on ${dayKey(when)}.` + note +
    budgetWarning(client, entry.project, roster, readEntries()));
});

server.registerTool("timesheet_report", {
  description: "Summarize logged time by client, project, and period.",
  inputSchema: {
    client: z.string().optional(), project: z.string().optional(),
    since: z.string().optional(), until: z.string().optional(),
    round_to: z.number().optional(),
  },
}, async ({ client, project, since, until, round_to }) => {
  const roster = loadRoster();
  const increment = round_to ?? roster.default_round_to;
  if (client) {
    client = resolveClient(client, roster) ?? client;
    if (project) project = resolveProject(client, project, roster) ?? project;
  }
  const [start, end] = resolveWindow(since, until, new Date());
  const rows = select(readEntries(), client, project, start, end);
  if (!rows.length) return text(`No entries for ${since ?? "all time"}.`);
  const s = summarize(rows, increment);
  const rates = Object.fromEntries(s.groups.map((g) => [g.client, rateFor(g.client, roster)]));
  const priced = Object.values(rates).some(Boolean);
  const lines = [
    `${start} to ${end} — ${s.count} entries, ${hours(s.total)}h total`, "",
    "| Client | Project | Hours |" + (priced ? " Amount |" : ""),
    "|---|---|---|" + (priced ? "---|" : ""),
  ];
  let billable = 0;
  for (const g of [...s.groups].sort((a, b) => b.minutes - a.minutes)) {
    let row = `| ${g.client} | ${g.project} | ${hours(g.minutes)} |`;
    if (priced) {
      const rate = rates[g.client];
      if (rate) {
        const amount = Number(hours(g.minutes)) * rate;
        billable += amount;
        row += ` ${money(amount)} |`;
      } else {
        row += " — |";
      }
    }
    lines.push(row);
  }
  if (priced) {
    lines.push("", `Billable at the rates on file: ${money(billable)}` +
      (Object.values(rates).every(Boolean) ? "" : " — clients marked — have no rate set."));
  }
  return text(lines.join("\n"));
});

server.registerTool("add_client", {
  description: "Add a client to the roster, or update one already on it.",
  inputSchema: {
    name: z.string(), aliases: z.array(z.string()).optional(),
    rate_per_hour: z.number().optional(), projects: z.array(z.string()).optional(),
  },
}, async ({ name, aliases, rate_per_hour, projects }) => {
  const roster = loadRoster();
  const existing = resolveClient(name, roster);
  let target = roster.clients.find((c) => c.name === existing);
  if (!target) {
    target = { name: name.trim(), aliases: [], rate_per_hour: null, projects: [] };
    roster.clients.push(target);
  }
  for (const a of aliases ?? []) {
    const t = a.trim();
    if (t && t.toLowerCase() !== target.name.toLowerCase() && !target.aliases.includes(t)) {
      target.aliases.push(t);
    }
  }
  for (const pj of projects ?? []) {
    const t = pj.trim();
    if (t && !target.projects.some((x) => x.name.toLowerCase() === t.toLowerCase())) {
      target.projects.push({ name: t, budget_hours: null });
    }
  }
  if (rate_per_hour != null) target.rate_per_hour = Number(rate_per_hour);
  saveRoster(roster);
  return text("Roster: " + roster.clients.map((c) => c.name).join(", "));
});

server.registerTool("list_clients", {
  description: "The client roster and the default rounding.",
  inputSchema: {},
}, async () => {
  const roster = loadRoster();
  if (!roster.clients.length) return text("No clients on the roster yet. Add one with add_client.");
  const lines = roster.clients.map((c) => {
    const bits = [c.name];
    if (c.aliases.length) bits.push("also: " + c.aliases.join(", "));
    if (c.projects.length) {
      bits.push("projects: " + c.projects
        .map((x) => x.name + (x.budget_hours ? ` (budget ${x.budget_hours}h)` : "")).join(", "));
    }
    if (c.rate_per_hour) bits.push(`$${c.rate_per_hour}/hr`);
    return bits.join(" — ");
  });
  const r = roster.default_round_to;
  lines.push(`\nDefault rounding: ${r} minute(s)` + (r <= 1 ? " (exact time)" : ""));
  return text(lines.join("\n"));
});

server.registerTool("remove_client", {
  description: "Take a client off the roster. Entries already logged are untouched.",
  inputSchema: { name: z.string() },
}, async ({ name }) => {
  const roster = loadRoster();
  const canonical = resolveClient(name, roster);
  if (!canonical) return text(`'${name}' isn't on the roster.`);
  roster.clients = roster.clients.filter((c) => c.name !== canonical);
  saveRoster(roster);
  return text(`Removed ${canonical}. Past entries still carry that name.`);
});

server.registerTool("remove_project", {
  description: "Take a project off a client. Entries already logged are untouched.",
  inputSchema: { client: z.string(), project: z.string() },
}, async ({ client, project }) => {
  const roster = loadRoster();
  const rec = clientRecord(client, roster);
  if (!rec) return text(`'${client}' isn't on the roster.`);
  const canonical = resolveProject(client, project, roster);
  if (!canonical) return text(`'${project}' isn't one of ${rec.name}'s projects.`);
  rec.projects = rec.projects.filter((x) => x.name !== canonical);
  saveRoster(roster);
  return text(`Removed ${canonical} from ${rec.name}.`);
});

server.registerTool("set_default_rounding", {
  description: "Round every report to this increment by default. 1 means exact time.",
  inputSchema: { minutes: z.number() },
}, async ({ minutes }) => {
  const roster = loadRoster();
  roster.default_round_to = Math.max(1, Math.floor(minutes));
  saveRoster(roster);
  const r = roster.default_round_to;
  return text(`Reports now round up to ${r} minute(s)` + (r <= 1 ? " — exact time." : "."));
});

server.registerTool("set_budget", {
  description: "Budget a project in hours. Adds the project if the client lacks it.",
  inputSchema: { client: z.string(), project: z.string(), hours: z.number() },
}, async ({ client, project, hours: budgetHours }) => {
  const roster = loadRoster();
  const rec = clientRecord(client, roster);
  if (!rec) return text(`'${client}' isn't on the roster. Add the client first with add_client.`);
  const canonical = resolveProject(client, project, roster);
  let pj = rec.projects.find((x) => x.name === canonical);
  if (!pj) {
    pj = { name: project.trim(), budget_hours: null };
    rec.projects.push(pj);
  }
  pj.budget_hours = Number(budgetHours);
  saveRoster(roster);
  const used = loggedHours(rec.name, pj.name, readEntries());
  return text(`${pj.name} budgeted at ${budgetHours}h for ${rec.name}. ` +
    `Already logged: ${used.toFixed(2)}h.`);
});

server.registerTool("budget_status", {
  description: "How every budgeted project stands. Warns at 80% and again once over.",
  inputSchema: { client: z.string().optional() },
}, async ({ client }) => {
  const roster = loadRoster();
  const only = client ? resolveClient(client, roster) : null;
  const rows = budgetLines(roster, readEntries(), only);
  if (!rows.length) {
    return text((client ? `No budgets set for ${only ?? client}.` : "No project budgets set.") +
      " Set one with set_budget.");
  }
  rows.sort((a, b) => b.fraction - a.fraction);
  const out = ["| Client | Project | Used | Budget | Left | |", "|---|---|---|---|---|---|"];
  for (const b of rows) {
    const flag = b.left < 0 ? "OVER" : (b.fraction >= BUDGET_WARN_AT ? "!" : "");
    out.push(`| ${b.client} | ${b.project} | ${b.used.toFixed(2)}h | ${b.budget}h ` +
      `| ${b.left.toFixed(2)}h | ${flag} |`);
  }
  return text(out.join("\n"));
});

server.registerTool("dashboard", {
  description: "Live dashboard as an inline artifact or a local page, plus desktop alerts.",
  inputSchema: {
    open_now: z.boolean().optional(), watch: z.boolean().optional(),
    as_artifact: z.boolean().optional(),
  },
}, async ({ open_now = true, watch = true, as_artifact = false }) => {
  const roster = loadRoster();
  const entries = readEntries();
  const rec = readRunning();
  let running = null;
  if (rec) {
    const b = budgetLines(roster, entries, rec.client).find((x) => x.project === rec.project);
    running = {
      client: rec.client, project: rec.project, start: rec.start,
      budget_hours: b?.budget ?? null, used_hours: b?.used ?? 0,
    };
  }
  const today = entries.filter((e) => entryDay(e) === dayKey(new Date()));
  const data = {
    generated: isoLocal(), warn_at: BUDGET_WARN_AT, running,
    mode: as_artifact ? "artifact" : "file",
    budgets: budgetLines(roster, entries).sort((a, b) => b.fraction - a.fraction)
      .map((b) => ({
        client: b.client, project: b.project,
        used: Math.round(b.used * 100) / 100, budget: b.budget,
      })),
    today: {
      total_hours: Math.round((today.reduce((a, e) => a + Number(e.minutes), 0) / 60) * 100) / 100,
      entries: today.map((e) => ({
        client: e.client, project: e.project,
        hours: Math.round((Number(e.minutes) / 60) * 100) / 100,
      })),
    },
  };
  const template = fs.readFileSync(path.join(ROOT, "assets", "dashboard.html"), "utf8");
  const page = template.replace("/*__DATA__*/{}", JSON.stringify(data));
  const watching = watch ? startWatcher() : "not watching";
  if (as_artifact) {
    return text("Publish the HTML below as an artifact, verbatim — it is self-contained and " +
      "already tested, so don't rewrite, restyle, or summarize it. The clock ticks and counts " +
      "the running session against the budget, but an artifact can't re-read the log: it shows " +
      "the log as of now, so regenerate it if they log more time. Alerts: " + watching +
      ".\n\n" + page);
  }
  const out = path.join(dataDir(), "dashboard.html");
  fs.writeFileSync(out, page);
  if (open_now && process.platform === "darwin") execFile("open", [out], () => {});
  return text(`Dashboard written to ${out}${open_now ? " and opened." : "."} It ticks the ` +
    `running timer against the budget and refreshes every minute. Alerts: ${watching}. Say ` +
    "that in a few words — a real Notification Centre banner arrives at 80% and at the limit, " +
    "whether or not the page is open.");
});

// --------------------------------------------------------- guides & prompts

for (const [name, title, desc] of [
  ["invoicing", "Invoicing from the log", "How to turn logged time into invoice lines."],
  ["reviewing", "Reviewing the week", "How to read a period back, and what to flag."],
  ["budgets", "Budgets and watching them", "Setting budgets, and when a schedule is worth it."],
]) {
  server.registerResource(name, `guide://${name}`, { title, description: desc, mimeType: "text/markdown" },
    async (uri) => ({ contents: [{ uri: uri.href, text: reference(name) }] }));
}

for (const [name, title, body] of [
  ["open_dashboard", "Open my timer dashboard",
    "Open my time-log dashboard so I can watch the clock and my budget while I work."],
  ["watch_budgets", "Watch my project budgets",
    "Read guide://budgets, then set up a recurring Claude Desktop task that watches my project " +
    "budgets. Tell me first what the tool already warns me about without any schedule, so I can " +
    "decide whether it's worth it. If I want it, make it say nothing unless a project is at 80% " +
    "or over, or a timer has been running more than eight hours."],
  ["draft_invoice", "Draft an invoice",
    "Draft an invoice from my time log. Read guide://invoicing first, then ask me which client " +
    "and which period before you pull any numbers."],
  ["review_week", "Review my week",
    "Show me how this week went in my time log. Read guide://reviewing first, and tell me " +
    "anything that looks like forgotten or mis-logged time."],
  ["getting_started", "Set up time tracking",
    "Set up my time tracking. Tell me what this does in a sentence, ask who I bill and whether " +
    "I bill in increments, then start my first timer."],
]) {
  server.registerPrompt(name, { title }, async () => ({
    messages: [{ role: "user", content: { type: "text", text: body } }],
  }));
}

if (process.argv.includes("--watch")) {
  await watchLoop();
} else {
  await server.connect(new StdioServerTransport());
}
