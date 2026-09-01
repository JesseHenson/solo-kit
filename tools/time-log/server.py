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
    return first_run_banner() + text.strip() + roster_summary()


def roster_summary() -> str:
    """Appended to the instructions, so the roster is known without a tool call."""
    roster = load_roster()
    if not roster["clients"]:
        return ""
    lines = ["\n\n## This user's roster\n"]
    for c in roster["clients"]:
        bits = [c["name"]]
        if c.get("aliases"):
            bits.append("also called " + ", ".join(c["aliases"]))
        if c.get("rate_per_hour"):
            bits.append(f"${c['rate_per_hour']}/hr")
        lines.append("- " + " — ".join(bits))
    rounding = roster["default_round_to"]
    lines.append(f"\nDefault rounding: {rounding} minute(s)"
                 + (" — i.e. exact time." if rounding <= 1 else ", applied unless asked otherwise."))
    lines.append("Use these spellings. Don't ask for a client name you can infer from this list.")
    return "\n".join(lines)


def first_run_banner() -> str:
    """Told at connect time, so a fresh install onboards without being asked."""
    f = entries_file()
    if (f.exists() and f.read_text().strip()) or load_roster()["clients"]:
        return ""
    return ("STATUS: nothing has ever been logged — this is a fresh install. "
            "Follow the First run section below before anything else.\n\n")


mcp = MCPServer(name="time-log", version="0.2.0", instructions=usage_instructions())


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


def hours(minutes: float) -> str:
    return f"{minutes / 60:.2f}"


# ------------------------------------------------------------------ tools

@mcp.tool()
def add_client(name: str, aliases: list[str] | None = None,
               rate_per_hour: float | None = None) -> str:
    """Add a client to the roster, or update one that's already on it.

    `aliases` are other spellings that should collapse into this name — a short
    form, an old trading name, whatever the user actually types.
    """
    roster = load_roster()
    existing = resolve_client(name, roster)
    target = next((c for c in roster["clients"] if c["name"] == existing), None)
    if target is None:
        target = {"name": name.strip(), "aliases": [], "rate_per_hour": None}
        roster["clients"].append(target)
    for a in aliases or []:
        if a.strip() and a.strip().lower() != target["name"].lower() and a not in target["aliases"]:
            target["aliases"].append(a.strip())
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
        if c.get("rate_per_hour"):
            bits.append(f"${c['rate_per_hour']}/hr")
        lines.append(" — ".join(bits))
    r = roster["default_round_to"]
    lines.append(f"\nDefault rounding: {r} minute(s)" + (" (exact time)" if r <= 1 else ""))
    return "\n".join(lines)


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
    client = resolve_client(client, roster) or client
    rec = {"client": client, "project": project, "notes": notes, "start": now().isoformat()}
    running_file().write_text(json.dumps(rec, indent=2))
    return (f"Started {client}" + (f" / {project}" if project else "") + f" at {rec['start']}."
            + unknown_client_note(client, roster))


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
    return f"Logged {hours(minutes)}h for {entry['client']}" + (
        f" / {entry['project']}" if entry["project"] else "")


@mcp.tool()
def current_timer() -> str:
    """Report what the timer is on right now, and for how long."""
    if not running_file().exists():
        return "No timer running."
    rec = json.loads(running_file().read_text())
    elapsed = (now() - datetime.fromisoformat(rec["start"])).total_seconds() / 60
    return f"{rec['client']}" + (f" / {rec['project']}" if rec.get("project") else "") + \
        f" — running {hours(elapsed)}h (since {rec['start']})."


@mcp.tool()
def log_entry(client: str, minutes: float, project: str | None = None,
              notes: str | None = None, day: str | None = None) -> str:
    """Log time after the fact. `day` is YYYY-MM-DD, defaulting to today."""
    roster = load_roster()
    resolved = resolve_client(client, roster)
    note = "" if resolved else unknown_client_note(client, roster)
    client = resolved or client
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
    return f"Logged {hours(minutes)}h for {client} on {when.date()}." + note


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
    start, end = resolve_window(since, until, now().date())
    rows = select(read_entries(), client, project, start, end)
    if not rows:
        return f"No entries for {since or 'all time'}."
    s = summarize(rows, round_to)
    lines = [f"{start} to {end} — {s['count']} entries, {hours(s['total'])}h total", ""]
    lines.append("| Client | Project | Hours |")
    lines.append("|---|---|---|")
    for (c, p), m in sorted(s["groups"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {c} | {p} | {hours(m)} |")
    return "\n".join(lines)


@mcp.prompt(title="Set up time tracking")
def getting_started() -> str:
    """Onboard someone who just installed this."""
    return ("Set up my time tracking. Tell me what this does in a sentence, ask "
            "who I bill and whether I bill in increments, then start my first timer.")


if __name__ == "__main__":
    mcp.run("stdio")
