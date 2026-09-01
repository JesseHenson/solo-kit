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

mcp = MCPServer(name="time-log", version="0.1.0")


# ---------------------------------------------------------------- storage

def data_dir() -> Path:
    d = Path(os.environ.get("TIME_LOG_DIR", Path.home() / ".time-log"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def entries_file() -> Path:
    return data_dir() / "entries.jsonl"


def running_file() -> Path:
    return data_dir() / "running.json"


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
def start_timer(client: str, project: str | None = None, notes: str | None = None) -> str:
    """Start the timer for a client. Fails if one is already running."""
    if running_file().exists():
        cur = json.loads(running_file().read_text())
        return f"Timer already running for {cur['client']} since {cur['start']}. Stop it first."
    rec = {"client": client, "project": project, "notes": notes, "start": now().isoformat()}
    running_file().write_text(json.dumps(rec, indent=2))
    return f"Started {client}" + (f" / {project}" if project else "") + f" at {rec['start']}."


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
    return f"Logged {hours(minutes)}h for {client} on {when.date()}."


@mcp.tool()
def timesheet_report(client: str | None = None, project: str | None = None,
                     since: str | None = None, until: str | None = None,
                     round_to: int = 1) -> str:
    """Summarize logged time.

    `since` takes a phrase (today, yesterday, this week, last week, this month,
    last month, all) or a YYYY-MM-DD date; `until` narrows the far end.
    `round_to` rounds each line up to that many minutes (e.g. 15 or 6).
    """
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


if __name__ == "__main__":
    mcp.run("stdio")
