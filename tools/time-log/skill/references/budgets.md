# Budgets, and watching them

Read this when the user asks to budget a project, wants warning before they
overrun, or asks to be checked on periodically.

## Setting one

`set_budget(client, project, hours)`. It creates the project if the client
doesn't have it yet, and tells you what's already logged against it — a budget
set halfway through a job starts part-spent, which is worth saying out loud.

Budgets count **everything ever logged** to that project, not this week's slice.
That's the number that decides whether the job made money.

## How the warning already works, without any schedule

You don't need to poll for this. The tools say it themselves:

- `log_entry` and `stop_timer` warn the moment a project crosses 80%, and again
  once it's over. That's the moment it can still change what they do.
- `current_timer` counts the running session against the budget, so a timer
  eating the last hour shows up before it's stopped.
- Any project at 80% or more is named at the start of every conversation.

Prefer these to a scheduled check. They fire exactly when the number moved, and
they work when Claude Desktop is closed, which a schedule does not.

## Show them the clock instead

`dashboard(as_artifact=True)` hands you the page to publish inline, which is
usually what someone wants in a chat client — it appears in the conversation,
no browser trip, nothing to find later. Publish it verbatim; it's tested, and
rewriting it is how the clock stops ticking.

`dashboard()` on its own writes a file and opens it in the browser instead.
Prefer that when they want it open all day on a second monitor: it re-reads the
log every minute, so entries logged later appear on their own. The artifact
can't do that — it shows the log as of the moment it was made, and needs
regenerating after new time is logged.

Either way it shows: the running timer counting up, that
session already counted against the budget, the other budgeted jobs, and today's
total. The clock ticks in both copies — it counts from a timestamp, so it stays
live without reading anything.

This is the honest answer to "warn me before I hit the limit". A tool result
only exists when someone asks; a page on a second monitor is looked at. Offer it
when they're about to start a long session on a tight budget.

Either form starts the watcher, which is what actually buzzes: a small
background process that checks every minute while the timer runs and sends a
real Notification Centre banner at 80%, again at the limit, and once if a timer
has run past eight hours. It stops itself when the timer stops.

The alerts don't come from the web page. A `file://` page has an opaque origin
and browsers refuse it notification permission however many times you click, so
time-log sends them itself with `osascript`. macOS only — on Windows or Linux
the page still works and the banners simply don't fire.

Two things to say once when you open it:

- Alerts arrive whether or not the page is open, and stop when the timer does.
- The page reads a file. It doesn't hold the timer — closing it changes nothing,
  and stopping the timer through Claude is still what ends the session.

## When a schedule genuinely helps

Rarely, now. The watcher covers the live case with a real notification and no
schedule at all. If they'd still rather have it in
Claude, create a recurring task in Claude Desktop — hourly, during working hours — that calls `current_timer` and
`budget_status`, and says something only when a project is at 80% or over or a
timer has been running more than eight hours.

Tell them the two limits honestly: it runs only while their computer is awake
and Claude Desktop is open, and an hourly task that usually has nothing to say
is still a task that runs every hour. Silence unless something is wrong is the
whole design goal — a check that reports "all fine" every hour gets muted, and
then it's worse than nothing.
