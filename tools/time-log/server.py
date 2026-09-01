#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2.0"]
# ///
"""time-log — a timer and timesheet over one plaintext JSONL file.

Data lives outside this repo so `git pull` can never touch it:

    ~/.time-log/entries.jsonl   one JSON object per finished session
    ~/.time-log/running.json    the timer currently running, if any

Override the directory with TIME_LOG_DIR.
"""

from __future__ import annotations

import json
import os
import urllib.request
import subprocess
import sys
import time
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path

from mcp.server.mcpserver import MCPServer



# ---------------------------------------------------------------- storage

def data_dir() -> Path:
    d = Path(os.environ.get("TIME_LOG_DIR", Path.home() / ".time-log"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def entries_file() -> Path:
    return data_dir() / "entries.jsonl"


def running_file() -> Path:
    return data_dir() / "running.json"


def roster_file() -> Path:
    return data_dir() / "clients.json"


def load_roster() -> dict:
    f = roster_file()
    data = json.loads(f.read_text()) if f.exists() else {}
    data.setdefault("clients", [])
    data.setdefault("default_round_to", 1)
    for c in data["clients"]:
        c["projects"] = [{"name": p, "budget_hours": None} if isinstance(p, str) else p
                         for p in c.get("projects", [])]
    return data


def save_roster(roster: dict) -> None:
    roster_file().write_text(json.dumps(roster, indent=2) + "\n")


def resolve_client(name: str, roster: dict) -> str | None:
    """The roster's spelling of `name`, matched on the name or any alias.

    Reports filter on an exact string, so "acme" and "Acme LLC" have to collapse
    into one name at write time — after the fact there is nothing to join on.
    """
    n = name.strip().lower()
    for c in roster["clients"]:
        if c["name"].strip().lower() == n:
            return c["name"]
        if any(a.strip().lower() == n for a in c.get("aliases", [])):
            return c["name"]
    return None


def client_record(name: str, roster: dict) -> dict | None:
    canonical = resolve_client(name, roster)
    return next((c for c in roster["clients"] if c["name"] == canonical), None)


def resolve_project(client: str, project: str, roster: dict) -> str | None:
    """The client's spelling of one of its projects, matched case-insensitively."""
    rec = client_record(client, roster)
    if not rec:
        return None
    p = project.strip().lower()
    return next((x["name"] for x in rec.get("projects", []) if x["name"].strip().lower() == p), None)


def unknown_project_note(client: str, project: str, roster: dict) -> str:
    """Silent for a client with no projects on file — plenty of people don't use them."""
    rec = client_record(client, roster)
    if not rec or not rec.get("projects"):
        return ""
    if resolve_project(client, project, roster):
        return ""
    known = ", ".join(x["name"] for x in rec["projects"])
    return (f"\nNOTE: '{project}' isn't one of {rec['name']}'s projects ({known}). New "
            "project, or another spelling of one of those? Add it with add_client's "
            "projects argument once they confirm.")


def unknown_client_note(name: str, roster: dict) -> str:
    if not roster["clients"]:
        return ""
    known = ", ".join(c["name"] for c in roster["clients"])
    return (f"\nNOTE: '{name}' is not on the roster ({known}). If it's a new client, "
            "call add_client. If it's a different spelling of one of those, say so "
            "and log it under the roster spelling instead.")


def read_entries() -> list[dict]:
    f = entries_file()
    if not f.exists():
        return []
    out = []
    for line in f.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def append_entry(entry: dict) -> None:
    with entries_file().open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def _version() -> str:
    """From the manifest, so a release bumps one number in one file."""
    try:
        return json.loads((Path(__file__).parent / "manifest.json").read_text())["version"]
    except Exception:
        return "0"


VERSION = _version()
RELEASES = "https://api.github.com/repos/JesseHenson/solo-kit/releases/latest"
DOWNLOAD = "https://github.com/JesseHenson/solo-kit/releases/latest/download/time-log.mcpb"


def as_tuple(v: str) -> tuple:
    return tuple(int(x) for x in v.strip().lstrip("v").split(".") if x.isdigit())


def update_note() -> str:
    """Check GitHub for a newer release, at most once a day.

    A bundle install has no update path — the host never checks — so without
    this a user simply never learns a newer version exists. It only ever reads
    a public release tag: nothing about them or their log leaves the machine.
    Set TIME_LOG_NO_UPDATE_CHECK=1 to switch it off.
    """
    if os.environ.get("TIME_LOG_NO_UPDATE_CHECK"):
        return ""
    cache = data_dir() / ".update-check.json"
    latest = ""
    try:
        seen = json.loads(cache.read_text())
        fresh = (datetime.now().timestamp() - seen["at"]) < 86400
        latest = seen["latest"] if fresh else ""
    except Exception:
        pass
    if not latest:
        try:
            req = urllib.request.Request(RELEASES, headers={"Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=2) as r:
                latest = json.load(r).get("tag_name", "")
            cache.write_text(json.dumps({"latest": latest, "at": datetime.now().timestamp()}))
        except Exception:
            return ""  # offline, rate-limited, whatever — never block startup
    try:
        if as_tuple(latest) <= as_tuple(VERSION):
            return ""
    except Exception:
        return ""
    return (f"\n\n## Update available\n\nThey're running {VERSION}; {latest} is out. Mention it "
            f"once, in a sentence, then carry on with what they asked: download {DOWNLOAD} "
            "and open it, and Claude Desktop replaces the tool. Their log is untouched. "
            "Don't raise it again in this conversation.")


def usage_instructions() -> str:
    """The skill file, minus its frontmatter, is what this server tells clients.

    One source for both surfaces: Claude Code loads skill/SKILL.md as a skill,
    and a bundle install gets the same text over MCP, where there is no skill.
    """
    f = Path(__file__).parent / "skill" / "SKILL.md"
    if not f.exists():
        return "Track billable time in a plaintext log. Call timesheet_report for totals."
    text = f.read_text()
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return first_run_banner() + text.strip() + REFERENCES + roster_summary() + budget_note() + running_note() + stale_timer_note() + update_note()


REFERENCES = """

## Deeper guidance, read only when it applies

- `guide://invoicing` — before drafting an invoice or working out what someone
  is owed. Covers rates, line grouping, and what never to invent.
- `guide://reviewing` — before reading a week or month back to the user.
- `guide://budgets` — before setting a budget, or if they ask to be checked on
  a schedule.

Read the one that applies before you start, not after. Don't read either for an
ordinary timer or report question."""


def roster_summary() -> str:
    """Appended to the instructions, so the roster is known without a tool call."""
    roster = load_roster()
    if not roster["clients"]:
        names = sorted({e.get("client") for e in read_entries() if e.get("client")})
        if not names:
            return ""
        return ("\n\n## No roster yet\n\nNothing is on the roster, but the log already "
                "has entries for: " + ", ".join(names) + ". Offer once to put those on the "
                "roster with add_client so they stop being retyped and can't drift into two "
                "spellings. If they decline, drop it and don't ask again.")
    lines = ["\n\n## This user's roster\n"]
    for c in roster["clients"]:
        bits = [c["name"]]
        if c.get("aliases"):
            bits.append("also called " + ", ".join(c["aliases"]))
        if c.get("projects"):
            bits.append("projects: " + ", ".join(
                x["name"] + (f" (budget {x['budget_hours']:g}h)" if x.get("budget_hours") else "")
                for x in c["projects"]))
        if c.get("rate_per_hour"):
            bits.append(f"${c['rate_per_hour']}/hr")
        lines.append("- " + " — ".join(bits))
    rounding = roster["default_round_to"]
    lines.append(f"\nDefault rounding: {rounding} minute(s)"
                 + (" — i.e. exact time." if rounding <= 1 else ", applied unless asked otherwise."))
    lines.append("Use these spellings. Don't ask for a client name you can infer from this list.")
    return "\n".join(lines)


STALE_HOURS = 8


def budget_note() -> str:
    """Projects already near their limit, named before the user starts adding to them."""
    try:
        rows = [b for b in budget_lines(load_roster(), read_entries())
                if b["fraction"] >= BUDGET_WARN_AT]
    except Exception:
        return ""
    if not rows:
        return ""
    lines = ["\n\n## Budgets worth knowing about\n"]
    for b in sorted(rows, key=lambda x: -x["fraction"]):
        state = (f"{abs(b['left']):.2f}h over" if b["left"] < 0
                 else f"{b['left']:.2f}h left of {b['budget']:g}h")
        lines.append(f"- {b['client']} / {b['project']} — {state} ({b['fraction']:.0%})")
    lines.append("\nMention this once if they log to one of these. Don't open with it.")
    return "\n".join(lines)


def running_note() -> str:
    """The timer lives in a file, so it outlives the conversation that started it."""
    if not running_file().exists():
        return ""
    try:
        rec = json.loads(running_file().read_text())
        elapsed = (now() - datetime.fromisoformat(rec["start"])).total_seconds() / 3600
    except Exception:
        return ""
    if elapsed >= STALE_HOURS:
        return ""  # the stale warning below says it louder
    who = rec["client"] + (f" / {rec['project']}" if rec.get("project") else "")
    return (f"\n\n## A timer is running\n\n{who}, {elapsed:.2f}h so far, started "
            f"{rec['start']}. It may have been started in another conversation — the timer "
            "is a file, not chat history. Don't start another; stop this one or ask.")


def stale_timer_note() -> str:
    """A timer left running overnight is the commonest way this data goes wrong."""
    if not running_file().exists():
        return ""
    try:
        rec = json.loads(running_file().read_text())
        elapsed = (now() - datetime.fromisoformat(rec["start"])).total_seconds() / 3600
    except Exception:
        return ""
    if elapsed < STALE_HOURS:
        return ""
    return (f"\n\n## A timer has been running {elapsed:.0f} hours\n\n"
            f"{rec['client']}, started {rec['start']}. That's usually a timer left on "
            "overnight, not real work. Say so before doing anything else, and offer to stop "
            "it with the right end time using stop_timer, or to correct it with log_entry.")


def first_run_banner() -> str:
    """Told at connect time, so a fresh install onboards without being asked."""
    f = entries_file()
    if (f.exists() and f.read_text().strip()) or load_roster()["clients"]:
        return ""
    return ("STATUS: nothing has ever been logged — this is a fresh install. "
            "Follow the First run section below before anything else.\n\n")


mcp = MCPServer(name="time-log", version=VERSION, instructions=usage_instructions())


# ------------------------------------------------------------ pure helpers

def now() -> datetime:
    return datetime.now().astimezone()


def round_minutes(minutes: float, increment: int) -> float:
    """Round up to the next `increment` — how billable time is normally cut."""
    if increment <= 1:
        return round(minutes)
    return float(increment * -(-minutes // increment))


def resolve_window(since: str | None, until: str | None, today: date) -> tuple[date, date]:
    """Turn a phrase or ISO date into an inclusive [start, end] pair of dates.

    Accepts: today, yesterday, this week, last week, this month, last month,
    all, or any YYYY-MM-DD. `since` phrases set both ends; `until` narrows.
    """
    monday = today - timedelta(days=today.weekday())
    phrase = (since or "all").strip().lower()

    if phrase in ("all", "", "everything"):
        start, end = date.min, date.max
    elif phrase == "today":
        start = end = today
    elif phrase == "yesterday":
        start = end = today - timedelta(days=1)
    elif phrase == "this week":
        start, end = monday, monday + timedelta(days=6)
    elif phrase == "last week":
        start, end = monday - timedelta(days=7), monday - timedelta(days=1)
    elif phrase == "this month":
        start = today.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    elif phrase == "last month":
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    else:
        start = end = date.fromisoformat(phrase)

    if until:
        end = date.fromisoformat(until)
    return start, end


def entry_date(entry: dict) -> date:
    return datetime.fromisoformat(entry["start"]).date()


def select(entries: list[dict], client: str | None, project: str | None,
           start: date, end: date) -> list[dict]:
    out = []
    for e in entries:
        if client and e.get("client", "").lower() != client.lower():
            continue
        if project and (e.get("project") or "").lower() != project.lower():
            continue
        if not (start <= entry_date(e) <= end):
            continue
        out.append(e)
    return out


def summarize(entries: list[dict], increment: int = 1) -> dict:
    """Total and per-client/project minutes, each rounded at the line it bills on."""
    by_group: dict[tuple[str, str], float] = {}
    for e in entries:
        key = (e.get("client", "(none)"), e.get("project") or "-")
        by_group[key] = by_group.get(key, 0.0) + float(e["minutes"])
    rounded = {k: round_minutes(v, increment) for k, v in by_group.items()}
    return {"groups": rounded, "total": sum(rounded.values()), "count": len(entries)}


BUDGET_WARN_AT = 0.8


def logged_hours(client: str, project: str, entries: list[dict]) -> float:
    """Everything ever logged to this project — a budget spans the job, not a week."""
    return sum(float(e["minutes"]) for e in entries
               if e.get("client") == client and (e.get("project") or "") == project) / 60


def budget_lines(roster: dict, entries: list[dict], only: str | None = None) -> list[dict]:
    out = []
    for c in roster["clients"]:
        if only and c["name"] != only:
            continue
        for pj in c.get("projects", []):
            if not pj.get("budget_hours"):
                continue
            used = logged_hours(c["name"], pj["name"], entries)
            budget = float(pj["budget_hours"])
            out.append({"client": c["name"], "project": pj["name"], "budget": budget,
                        "used": used, "left": budget - used,
                        "fraction": used / budget if budget else 0.0})
    return out


def budget_warning(client: str, project: str | None, roster: dict) -> str:
    """Said at the moment time is logged, which is the moment it can still matter."""
    if not project:
        return ""
    rows = [b for b in budget_lines(roster, read_entries(), client) if b["project"] == project]
    if not rows or rows[0]["fraction"] < BUDGET_WARN_AT:
        return ""
    b = rows[0]
    if b["left"] < 0:
        return (f"\nBUDGET: {b['project']} is {abs(b['left']):.2f}h over its {b['budget']:g}h "
                "budget. Say so now — this is work they may not be able to bill.")
    return (f"\nBUDGET: {b['project']} is at {b['used']:.2f} of {b['budget']:g}h "
            f"({b['fraction']:.0%}), {b['left']:.2f}h left. Mention it once.")


def rate_for(client: str, roster: dict) -> float | None:
    rec = client_record(client, roster)
    return rec.get("rate_per_hour") if rec else None


def money(amount: float) -> str:
    return f"${amount:,.2f}"


def hours(minutes: float) -> str:
    return f"{minutes / 60:.2f}"


# ------------------------------------------------------------------ tools

@mcp.tool()
def add_client(name: str, aliases: list[str] | None = None,
               rate_per_hour: float | None = None,
               projects: list[str] | None = None) -> str:
    """Add a client to the roster, or update one that's already on it.

    `aliases` are other spellings that should collapse into this name — a short
    form, an old trading name, whatever the user actually types. `projects` are
    the pieces of work billed under them; they're optional, and only clients
    that have some get asked about an unfamiliar one.
    """
    roster = load_roster()
    existing = resolve_client(name, roster)
    target = next((c for c in roster["clients"] if c["name"] == existing), None)
    if target is None:
        target = {"name": name.strip(), "aliases": [], "rate_per_hour": None, "projects": []}
        roster["clients"].append(target)
    for a in aliases or []:
        if a.strip() and a.strip().lower() != target["name"].lower() and a not in target["aliases"]:
            target["aliases"].append(a.strip())
    for pj in projects or []:
        names = [x["name"].lower() for x in target.setdefault("projects", [])]
        if pj.strip() and pj.strip().lower() not in names:
            target["projects"].append({"name": pj.strip(), "budget_hours": None})
    if rate_per_hour is not None:
        target["rate_per_hour"] = float(rate_per_hour)
    save_roster(roster)
    return f"Roster: " + ", ".join(c["name"] for c in roster["clients"])


@mcp.tool()
def list_clients() -> str:
    """The client roster and the default rounding."""
    roster = load_roster()
    if not roster["clients"]:
        return "No clients on the roster yet. Add one with add_client."
    lines = []
    for c in roster["clients"]:
        bits = [c["name"]]
        if c.get("aliases"):
            bits.append("also: " + ", ".join(c["aliases"]))
        if c.get("projects"):
            bits.append("projects: " + ", ".join(
                x["name"] + (f" (budget {x['budget_hours']:g}h)" if x.get("budget_hours") else "")
                for x in c["projects"]))
        if c.get("rate_per_hour"):
            bits.append(f"${c['rate_per_hour']}/hr")
        lines.append(" — ".join(bits))
    r = roster["default_round_to"]
    lines.append(f"\nDefault rounding: {r} minute(s)" + (" (exact time)" if r <= 1 else ""))
    return "\n".join(lines)


def notify(title: str, message: str, sound: bool = True) -> bool:
    """A real Notification Center banner. macOS only; silent no-op elsewhere.

    The dashboard can't do this itself — a file:// page has an opaque origin, so
    browsers refuse it notification permission however many times you click.
    """
    if sys.platform != "darwin":
        return False
    script = (f'display notification {json.dumps(message)} with title {json.dumps(title)}'
              + (' sound name "Ping"' if sound else ""))
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=15)
        return True
    except Exception:
        return False


def watch_loop() -> None:
    """Poll while a timer runs, buzz once per threshold, exit when it stops.

    Runs as a detached child of the server so alerts arrive with nobody asking.
    It holds no state of its own: kill it any time and nothing is lost.
    """
    fired: set[str] = set()
    deadline = time.time() + 12 * 3600
    while time.time() < deadline:
        time.sleep(60)
        if not running_file().exists():
            break
        try:
            rec = json.loads(running_file().read_text())
            elapsed = (now() - datetime.fromisoformat(rec["start"])).total_seconds() / 3600
        except Exception:
            break
        key = rec["start"]
        if elapsed >= STALE_HOURS and f"{key}:stale" not in fired:
            fired.add(f"{key}:stale")
            notify("Timer still running", f"{rec['client']} — {elapsed:.0f} hours. Left on?")
        if not rec.get("project"):
            continue
        rows = [b for b in budget_lines(load_roster(), read_entries(), rec["client"])
                if b["project"] == rec["project"]]
        if not rows:
            continue
        live = rows[0]["used"] + elapsed
        budget = rows[0]["budget"]
        if live >= budget and f"{key}:over" not in fired:
            fired.add(f"{key}:over")
            notify(f"{rec['project']} over budget",
                   f"{live:.2f}h against a {budget:g}h budget.")
        elif live / budget >= BUDGET_WARN_AT and f"{key}:warn" not in fired:
            fired.add(f"{key}:warn")
            notify(f"{rec['project']} at {live / budget:.0%}",
                   f"{budget - live:.2f}h left of {budget:g}h.")
    pidfile = data_dir() / ".watch.pid"
    if pidfile.exists():
        pidfile.unlink(missing_ok=True)


def start_watcher() -> str:
    """One watcher at a time, and never one for a timer that isn't running."""
    if not running_file().exists():
        return "no timer running, so nothing to watch"
    pidfile = data_dir() / ".watch.pid"
    if pidfile.exists():
        try:
            os.kill(int(pidfile.read_text()), 0)
            return "already watching"
        except Exception:
            pidfile.unlink(missing_ok=True)
    try:
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--watch"],
                                start_new_session=True, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        pidfile.write_text(str(proc.pid))
        return "watching — it'll buzz at 80% and again at the limit, and stop when you do"
    except Exception as e:
        return f"couldn't start the watcher ({e})"


@mcp.tool()
def dashboard(open_now: bool = True, watch: bool = True, as_artifact: bool = False) -> str:
    """Write a live dashboard — running clock, budget burn, today's total — and open it.

    The page ticks the running timer in the browser and counts it against the
    budget as it goes, so someone watching sees the limit coming instead of
    being told after they've passed it. It refreshes itself every minute.

    `as_artifact` returns the HTML instead of writing it, for a client that can
    render it inline. That copy can't refresh itself — it shows the log as of
    now — so prefer the file when they want to leave it open all day.
    """
    roster = load_roster()
    entries = read_entries()
    running = None
    if running_file().exists():
        rec = json.loads(running_file().read_text())
        budget = next((b for b in budget_lines(roster, entries, rec["client"])
                       if b["project"] == rec.get("project")), None)
        running = {"client": rec["client"], "project": rec.get("project"),
                   "start": rec["start"],
                   "budget_hours": budget["budget"] if budget else None,
                   "used_hours": budget["used"] if budget else 0.0}
    today = [e for e in entries if entry_date(e) == now().date()]
    data = {
        "generated": now().isoformat(),
        "warn_at": BUDGET_WARN_AT,
        "running": running,
        "budgets": [{"client": b["client"], "project": b["project"],
                     "used": round(b["used"], 2), "budget": b["budget"]}
                    for b in sorted(budget_lines(roster, entries), key=lambda x: -x["fraction"])],
        "today": {"total_hours": round(sum(float(e["minutes"]) for e in today) / 60, 2),
                  "entries": [{"client": e["client"], "project": e.get("project"),
                               "hours": round(float(e["minutes"]) / 60, 2)} for e in today]},
    }
    data["mode"] = "artifact" if as_artifact else "file"
    template = (Path(__file__).parent / "assets" / "dashboard.html").read_text()
    page = template.replace("/*__DATA__*/{}", json.dumps(data))
    if as_artifact:
        return ("Publish the HTML below as an artifact, verbatim — it is self-contained and "
                "already tested, so don't rewrite, restyle, or summarize it. The clock ticks "
                "and counts the running session against the budget, but an artifact can't "
                "re-read the log: it shows the log as of now, so regenerate it if they log "
                "more time. Alerts: " + (start_watcher() if watch else "not watching")
                + ".\n\n" + page)
    out = data_dir() / "dashboard.html"
    out.write_text(page)
    if open_now:
        try:
            webbrowser.open(out.as_uri())
        except Exception:
            pass
    watching = start_watcher() if watch else "not watching"
    return (f"Dashboard written to {out}" + (" and opened." if open_now else ".")
            + " It ticks the running timer against the budget and refreshes every minute."
            + f" Alerts: {watching}. Say that in a few words — a real Notification Centre "
            "banner arrives at 80% and at the limit, whether or not the page is open.")


@mcp.tool()
def set_budget(client: str, project: str, hours: float) -> str:
    """Budget a project in hours. Adds the project if it isn't on the client yet."""
    roster = load_roster()
    rec = client_record(client, roster)
    if not rec:
        return f"'{client}' isn't on the roster. Add the client first with add_client."
    canonical = resolve_project(client, project, roster)
    if canonical:
        pj = next(x for x in rec["projects"] if x["name"] == canonical)
    else:
        pj = {"name": project.strip(), "budget_hours": None}
        rec["projects"].append(pj)
    pj["budget_hours"] = float(hours)
    save_roster(roster)
    used = logged_hours(rec["name"], pj["name"], read_entries())
    return (f"{pj['name']} budgeted at {float(hours):g}h for {rec['name']}. "
            f"Already logged: {used:.2f}h.")


@mcp.tool()
def budget_status(client: str | None = None) -> str:
    """How every budgeted project stands. Warns at 80% and again once it's over."""
    roster = load_roster()
    only = resolve_client(client, roster) if client else None
    rows = budget_lines(roster, read_entries(), only)
    if not rows:
        return ("No project budgets set." if not client else
                f"No budgets set for {only or client}.") + " Set one with set_budget."
    rows.sort(key=lambda b: -b["fraction"])
    out = ["| Client | Project | Used | Budget | Left | |", "|---|---|---|---|---|---|"]
    for b in rows:
        flag = "OVER" if b["left"] < 0 else ("!" if b["fraction"] >= BUDGET_WARN_AT else "")
        out.append(f"| {b['client']} | {b['project']} | {b['used']:.2f}h | {b['budget']:g}h "
                   f"| {b['left']:.2f}h | {flag} |")
    return "\n".join(out)


@mcp.tool()
def remove_project(client: str, project: str) -> str:
    """Take a project off a client. Entries already logged are untouched."""
    roster = load_roster()
    rec = client_record(client, roster)
    if not rec:
        return f"'{client}' isn't on the roster."
    canonical = resolve_project(client, project, roster)
    if not canonical:
        return f"'{project}' isn't one of {rec['name']}'s projects."
    rec["projects"] = [x for x in rec["projects"] if x["name"] != canonical]
    save_roster(roster)
    return f"Removed {canonical} from {rec['name']}."


@mcp.tool()
def remove_client(name: str) -> str:
    """Take a client off the roster. Entries already logged are untouched."""
    roster = load_roster()
    canonical = resolve_client(name, roster)
    if not canonical:
        return f"'{name}' isn't on the roster."
    roster["clients"] = [c for c in roster["clients"] if c["name"] != canonical]
    save_roster(roster)
    return f"Removed {canonical}. Past entries still carry that name."


@mcp.tool()
def set_default_rounding(minutes: int) -> str:
    """Round every report to this increment by default. 1 means exact time."""
    roster = load_roster()
    roster["default_round_to"] = max(1, int(minutes))
    save_roster(roster)
    r = roster["default_round_to"]
    return f"Reports now round up to {r} minute(s)" + (" — exact time." if r <= 1 else ".")


@mcp.tool()
def start_timer(client: str, project: str | None = None, notes: str | None = None) -> str:
    """Start the timer for a client. Fails if one is already running."""
    if running_file().exists():
        cur = json.loads(running_file().read_text())
        return f"Timer already running for {cur['client']} since {cur['start']}. Stop it first."
    roster = load_roster()
    resolved = resolve_client(client, roster)
    note = "" if resolved else unknown_client_note(client, roster)
    client = resolved or client
    if project:
        note += unknown_project_note(client, project, roster)
        project = resolve_project(client, project, roster) or project
    rec = {"client": client, "project": project, "notes": notes, "start": now().isoformat()}
    running_file().write_text(json.dumps(rec, indent=2))
    return (f"Started {client}" + (f" / {project}" if project else "") + f" at {rec['start']}."
            + note)


@mcp.tool()
def stop_timer(notes: str | None = None) -> str:
    """Stop the running timer and write the session to the log."""
    if not running_file().exists():
        return "No timer running."
    rec = json.loads(running_file().read_text())
    end = now()
    start = datetime.fromisoformat(rec["start"])
    minutes = round((end - start).total_seconds() / 60, 2)
    entry = {
        "client": rec["client"],
        "project": rec.get("project"),
        "start": rec["start"],
        "end": end.isoformat(),
        "minutes": minutes,
        "notes": notes or rec.get("notes"),
    }
    append_entry(entry)
    running_file().unlink()
    return (f"Logged {hours(minutes)}h for {entry['client']}"
            + (f" / {entry['project']}" if entry["project"] else "")
            + budget_warning(entry["client"], entry["project"], load_roster()))


@mcp.tool()
def current_timer() -> str:
    """Report what the timer is on right now, and for how long."""
    if not running_file().exists():
        return "No timer running."
    rec = json.loads(running_file().read_text())
    elapsed = (now() - datetime.fromisoformat(rec["start"])).total_seconds() / 60
    out = f"{rec['client']}" + (f" / {rec['project']}" if rec.get("project") else "") + \
        f" — running {hours(elapsed)}h (since {rec['start']})."
    roster = load_roster()
    if rec.get("project"):
        rows = [b for b in budget_lines(roster, read_entries(), rec["client"])
                if b["project"] == rec["project"]]
        if rows:
            b = rows[0]
            projected = b["used"] + elapsed / 60
            out += (f"\nBudget: {projected:.2f} of {b['budget']:g}h counting this session"
                    f" ({projected / b['budget']:.0%}).")
    if elapsed / 60 >= STALE_HOURS:
        out += (f"\nNOTE: {elapsed / 60:.0f} hours is long enough to be a timer left on by "
                "mistake. Check before logging it as worked time.")
    return out


@mcp.tool()
def log_entry(client: str, minutes: float, project: str | None = None,
              notes: str | None = None, day: str | None = None) -> str:
    """Log time after the fact. `day` is YYYY-MM-DD, defaulting to today."""
    roster = load_roster()
    resolved = resolve_client(client, roster)
    note = "" if resolved else unknown_client_note(client, roster)
    client = resolved or client
    if project:
        note += unknown_project_note(client, project, roster)
        project = resolve_project(client, project, roster) or project
    when = datetime.fromisoformat(day) if day else now()
    if when.tzinfo is None:
        when = when.replace(tzinfo=now().tzinfo)
    entry = {
        "client": client,
        "project": project,
        "start": when.isoformat(),
        "end": (when + timedelta(minutes=minutes)).isoformat(),
        "minutes": float(minutes),
        "notes": notes,
    }
    append_entry(entry)
    return (f"Logged {hours(minutes)}h for {client} on {when.date()}." + note
            + budget_warning(client, entry["project"], roster))


@mcp.tool()
def timesheet_report(client: str | None = None, project: str | None = None,
                     since: str | None = None, until: str | None = None,
                     round_to: int | None = None) -> str:
    """Summarize logged time.

    `since` takes a phrase (today, yesterday, this week, last week, this month,
    last month, all) or a YYYY-MM-DD date; `until` narrows the far end.
    `round_to` rounds each line up to that many minutes (e.g. 15 or 6); left
    out, it uses the default set with set_default_rounding.
    """
    roster = load_roster()
    if round_to is None:
        round_to = roster["default_round_to"]
    if client:
        client = resolve_client(client, roster) or client
        if project:
            project = resolve_project(client, project, roster) or project
    start, end = resolve_window(since, until, now().date())
    rows = select(read_entries(), client, project, start, end)
    if not rows:
        return f"No entries for {since or 'all time'}."
    s = summarize(rows, round_to)
    lines = [f"{start} to {end} — {s['count']} entries, {hours(s['total'])}h total", ""]
    rates = {c: rate_for(c, roster) for c, _ in s["groups"]}
    priced = any(rates.values())
    lines.append("| Client | Project | Hours |" + (" Amount |" if priced else ""))
    lines.append("|---|---|---|" + ("---|" if priced else ""))
    billable = 0.0
    for (c, p), m in sorted(s["groups"].items(), key=lambda kv: -kv[1]):
        row = f"| {c} | {p} | {hours(m)} |"
        if priced:
            rate = rates.get(c)
            if rate:
                amount = float(hours(m)) * rate
                billable += amount
                row += f" {money(amount)} |"
            else:
                row += " — |"
        lines.append(row)
    if priced:
        lines.append("")
        lines.append(f"Billable at the rates on file: {money(billable)}"
                     + ("" if all(rates.values()) else " — clients marked — have no rate set."))
    return "\n".join(lines)


def reference(name: str) -> str:
    f = Path(__file__).parent / "skill" / "references" / f"{name}.md"
    return f.read_text() if f.exists() else f"No reference named {name}."


@mcp.resource("guide://invoicing", name="Invoicing from the log",
              description="How to turn logged time into invoice lines, and what not to invent.",
              mime_type="text/markdown")
def invoicing_guide() -> str:
    return reference("invoicing")


@mcp.resource("guide://reviewing", name="Reviewing the week",
              description="How to read a period back to someone, and what's worth flagging.",
              mime_type="text/markdown")
def reviewing_guide() -> str:
    return reference("reviewing")


@mcp.resource("guide://budgets", name="Budgets and watching them",
              description="Setting project budgets, and when a scheduled check is worth it.",
              mime_type="text/markdown")
def budgets_guide() -> str:
    return reference("budgets")


@mcp.prompt(title="Open my timer dashboard")
def open_dashboard() -> str:
    """Put the running clock and budget burn on screen."""
    return ("Open my time-log dashboard so I can watch the clock and my budget while I work.")


@mcp.prompt(title="Watch my project budgets")
def watch_budgets() -> str:
    """Set up a recurring check against project budgets."""
    return ("Read guide://budgets, then set up a recurring Claude Desktop task that watches my "
            "project budgets. Tell me first what the tool already warns me about without any "
            "schedule, and what the schedule adds, so I can decide whether it's worth it. If I "
            "want it, make it say nothing unless a project is at 80% or over, or a timer has "
            "been running more than eight hours.")


@mcp.prompt(title="Draft an invoice")
def draft_invoice() -> str:
    """Turn a period's logged time into invoice lines."""
    return ("Draft an invoice from my time log. Read guide://invoicing first, then ask me "
            "which client and which period before you pull any numbers.")


@mcp.prompt(title="Review my week")
def review_week() -> str:
    """Read the week back, and flag what needs fixing."""
    return ("Show me how this week went in my time log. Read guide://reviewing first, and "
            "tell me anything that looks like forgotten or mis-logged time.")


@mcp.prompt(title="Set up time tracking")
def getting_started() -> str:
    """Onboard someone who just installed this."""
    return ("Set up my time tracking. Tell me what this does in a sentence, ask "
            "who I bill and whether I bill in increments, then start my first timer.")


if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch_loop()
    else:
        mcp.run("stdio")
