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
| `add_client(name, aliases, rate_per_hour, projects)` | a client or project name you haven't seen before |
| `list_clients()` | you need the roster mid-conversation |
| `remove_client(name)` | they stop working with someone |
| `remove_project(client, project)` | a project name was wrong or is finished |
| `set_default_rounding(minutes)` | they say how their contracts bill |
| `set_budget(client, project, hours)` | a project is quoted or capped |
| `budget_status(client)` | "how are we doing against the estimate?" |
| `dashboard(as_artifact=True)` | they want to watch the clock or want alerts — publish the HTML it returns, verbatim |

`since` takes `today`, `yesterday`, `this week`, `last week`, `this month`,
`last month`, `all`, or `YYYY-MM-DD`. `until` narrows the far end.

## First run

When the server reports that nothing has been logged yet, onboard the user
before doing anything else — briefly, in one exchange, not an interview:

1. Say what this does in a sentence: a timer and timesheets over a plain file
   on their own machine, no account and no subscription.
2. Ask the two things that change every later answer — **who they bill**
   (client names, as they want them to read on an invoice) and **whether they
   bill in increments** (6 or 15 minutes) or in exact time.
   Then **write both down**: `add_client` for each name, `set_default_rounding`
   for the increment. They said it once; they should never be asked again.
3. Offer the first action rather than explaining more: start a timer for one of
   the clients they just named, or log time they've already worked today.
4. Tell them the two sentences that cover most use: *"start a timer for X"* and
   *"what did I bill X this week?"*

Don't dump the tool list on them, don't explain the file format unless asked,
and don't ask for anything the tools don't need. If they'd rather just start,
skip the rest and start the timer.

## How to use them

**One timer at a time.** `start_timer` refuses while another is running. If the
user starts something new without stopping, call `current_timer`, tell them what
is still running, and ask before stopping it — the elapsed time is unrecoverable
once you guess wrong about where it belonged.

**Rounding is a billing decision, not a default.** `round_to` defaults to 1
(no rounding). Pass `15` or `6` only when the user says their contract bills
that way. Never round a report the user asked to check their own hours against.

**The roster is the memory, not you.** The clients this user bills are listed at
the end of these instructions, and the tools resolve aliases to the roster
spelling on the way in. Use those names. Don't ask for a client you can infer
from the roster, and don't carry names only in the conversation — a name you
were told but never passed to `add_client` is gone by the next chat.

**Projects work the same way, but quieter.** They hang off a client, and only a
client that already has projects on file gets asked about an unfamiliar one —
plenty of people bill straight to a client and never use projects. Don't push
projects on someone who hasn't mentioned them.

**A new name is a question, not a new client.** If a tool comes back saying a
name isn't on the roster, stop and ask: new client, or another spelling of one
already there? Reports filter on the exact string, so an unnoticed "Acme LLC"
splits Acme's hours across two rows forever. Once they confirm it's new, call
`add_client`; if it's a variant, call `add_client` with it as an alias so it
resolves itself next time.

**When the user is vague** ("log an hour"), ask which client rather than
picking the last one used.

**Amounts come from the roster's rates.** A report shows money only for clients
with a rate on file, and says which ones don't. Never fill a missing rate with a
guess — offer to set it with `add_client`.

**A timer running eight hours or more is suspect.** You'll be told when one is.
Raise it before anything else and offer to correct the end time; don't quietly
log an overnight timer as a working day.

**Show the dashboard as an artifact by default.** `dashboard(as_artifact=True)`
returns a page to publish inline; a file on disk is a worse answer in a chat
window. Use plain `dashboard()` only when they say they want it open all day —
that copy re-reads the log every minute, the artifact doesn't.

**Budget warnings arrive on their own.** Logging time to a project at 80% or
more returns a BUDGET line, and near-limit projects are listed at the start of
each conversation. Pass it on once, plainly, and carry on — don't repeat it
every entry, and don't turn it into advice about how they should work.

**Report what the log says.** The totals come from the tool. Don't recompute
hours in your head or adjust them to match what the user expected — if a number
looks wrong, show the entries and say so.

## Where the data lives

`~/.time-log/entries.jsonl`, one JSON object per session, plus `running.json`
for the timer in flight. Plain files the user can read, grep, edit, or back up.
Set `TIME_LOG_DIR` to move them.
