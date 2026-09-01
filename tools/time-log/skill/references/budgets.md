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

## When a schedule genuinely helps

One case: a timer left running against a tight budget, in a long session where
nothing else calls a tool. If they want that watched, create a recurring task in
Claude Desktop — hourly, during working hours — that calls `current_timer` and
`budget_status`, and says something only when a project is at 80% or over or a
timer has been running more than eight hours.

Tell them the two limits honestly: it runs only while their computer is awake
and Claude Desktop is open, and an hourly task that usually has nothing to say
is still a task that runs every hour. Silence unless something is wrong is the
whole design goal — a check that reports "all fine" every hour gets muted, and
then it's worse than nothing.
