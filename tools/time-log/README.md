# time-log

A timer and timesheet report over one plaintext file. Replaces the part of
QuickBooks Time a solo operator actually uses.

Install by opening `time-log.mcpb` from a release, or from a clone:

    ./install.sh time-log     # from the repo root

## Tools

| Tool | Arguments |
|---|---|
| `start_timer` | client, project, notes |
| `stop_timer` | notes |
| `current_timer` | — |
| `log_entry` | client, minutes, project, notes, day |
| `timesheet_report` | client, project, since, until, round_to |

`since` accepts `today`, `yesterday`, `this week`, `last week`, `this month`,
`last month`, `all`, or `YYYY-MM-DD`. `round_to` rounds each client/project line
**up** to that many minutes; it defaults to 1, meaning no rounding.

## Data

    ~/.time-log/entries.jsonl    one JSON object per finished session
    ~/.time-log/running.json     the timer in flight, if any

Set `TIME_LOG_DIR` to put them elsewhere — a Dropbox folder, or a git repo of
your own if you want the log versioned.

    {"client": "Acme", "project": "redesign", "start": "2026-08-31T09:00:00-06:00",
     "end": "2026-08-31T10:30:00-06:00", "minutes": 90.0, "notes": "wireframes"}

## Not included

GPS and screenshot monitoring, payroll integration, and manager approval
workflows. Those need a backend and other people's accounts — the reason
QuickBooks Time ties itself to a $75/mo QuickBooks Online plan.

## Tests

    uv run --with mcp --with pytest pytest -q
