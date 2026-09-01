---
name: time-log
description: Track billable time and answer questions about it — starting and stopping a timer, logging time after the fact, and producing timesheet or invoice-ready summaries ("what did I bill Acme this week", "how many hours on the redesign last month", "log 90 minutes to Beta Co"). Use whenever the user talks about hours worked, billing a client, or a timesheet.
---

# time-log

Time tracking over one plaintext file. The `time-log` MCP server owns the data;
this skill decides which tool to call and how to present what comes back.

## The tools

| Tool | Use it when |
|---|---|
| `start_timer(client, project, notes)` | "starting on Acme now" |
| `stop_timer(notes)` | "done", "stop the timer" |
| `current_timer()` | "what am I on?", or before starting a second one |
| `log_entry(client, minutes, project, notes, day)` | time already spent — "put 90 minutes on Acme yesterday" |
| `timesheet_report(client, project, since, until, round_to)` | any question about totals |

`since` takes `today`, `yesterday`, `this week`, `last week`, `this month`,
`last month`, `all`, or `YYYY-MM-DD`. `until` narrows the far end.

## How to use them

**One timer at a time.** `start_timer` refuses while another is running. If the
user starts something new without stopping, call `current_timer`, tell them what
is still running, and ask before stopping it — the elapsed time is unrecoverable
once you guess wrong about where it belonged.

**Rounding is a billing decision, not a default.** `round_to` defaults to 1
(no rounding). Pass `15` or `6` only when the user says their contract bills
that way. Never round a report the user asked to check their own hours against.

**Ask for the client, don't invent one.** Every entry needs a client string, and
a typo makes a whole second client in every future report. When the user is
vague ("log an hour"), ask which client rather than picking the last one used.

**Report what the log says.** The totals come from the tool. Don't recompute
hours in your head or adjust them to match what the user expected — if a number
looks wrong, show the entries and say so.

## Where the data lives

`~/.time-log/entries.jsonl`, one JSON object per session, plus `running.json`
for the timer in flight. Plain files the user can read, grep, edit, or back up.
Set `TIME_LOG_DIR` to move them.
