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

## Updating

A bundle install has no update channel — the MCPB spec has no update URL and
the host never checks — so the server checks GitHub for a newer release once a
day and has Claude mention it in passing. Updating is then the same two clicks
as installing: download the file again and open it. Your log is untouched.

The check reads a public release tag and sends nothing about you or your log.
Set `TIME_LOG_NO_UPDATE_CHECK=1` to turn it off. A clone install skips all of
this — `git pull` and the change is live.

## Data

    ~/Documents/Time Log/entries.jsonl   one JSON object per finished session
    ~/Documents/Time Log/running.json    the timer in flight, if any
    ~/Documents/Time Log/clients.json    your roster: clients, projects, rates, budgets

Set `TIME_LOG_DIR` to put them elsewhere — a Dropbox folder, or a git repo of
your own if you want the log versioned.

    {"client": "Acme", "project": "redesign", "start": "2026-08-31T09:00:00-06:00",
     "end": "2026-08-31T10:30:00-06:00", "minutes": 90.0, "notes": "wireframes"}

## Not included

GPS and screenshot monitoring, payroll integration, and manager approval
workflows. Those need a backend and other people's accounts — the reason
QuickBooks Time ties itself to a $75/mo QuickBooks Online plan.

## Tests

    npm install && npm test
