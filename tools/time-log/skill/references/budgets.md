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

`dashboard()` writes a page and opens it: the running timer counting up, that
session already counted against the budget, the other budgeted jobs, and today's
total. It re-reads the log every minute, so it stays true while they work.

This is the honest answer to "warn me before I hit the limit". A tool result
only exists when someone asks; a page on a second monitor is looked at. Offer it
when they're about to start a long session on a tight budget.

Two things to say once when you open it:

- Click **Enable alerts** for a desktop notification at 80% and again at the
  limit. Browsers only allow that on a real click, so it can't be done for them.
- The page reads a file. It doesn't hold the timer — closing it changes nothing,
  and stopping the timer through Claude is still what ends the session.

## When a schedule genuinely helps

Only if they won't keep the dashboard open. The page already covers the live
case, without a task running every hour. If they'd still rather have it in
Claude, create a recurring task in Claude Desktop — hourly, during working hours — that calls `current_timer` and
`budget_status`, and says something only when a project is at 80% or over or a
timer has been running more than eight hours.

Tell them the two limits honestly: it runs only while their computer is awake
and Claude Desktop is open, and an hourly task that usually has nothing to say
is still a task that runs every hour. Silence unless something is wrong is the
whole design goal — a check that reports "all fine" every hour gets muted, and
then it's worse than nothing.
