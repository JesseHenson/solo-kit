# Reviewing the week

Read this when the user asks how their week or month went, where time went, or
whether anything is missing. The point is a decision, not a data dump.

## What to pull

`timesheet_report(since="this week")` for the shape of it, then per-client
reports only if a number looks off. `current_timer` first if they might have one
running — an open timer means the totals are already stale.

## What to say

Lead with the total and the split, in three lines or fewer. Then the one thing
worth acting on:

- **A day with nothing logged.** Usually forgotten time, not a day off. Ask.
- **A client that dropped off.** Compare to `since="last week"` before saying
  it — one quiet week is noise.
- **A long unbroken session.** A nine-hour entry is usually a timer left
  running overnight. Offer to correct it rather than reporting it as fact.
- **Time with no project** on a client that uses projects — it won't group on
  the invoice.

## What not to do

Don't editorialize about how hard they worked, don't compare them to a target
they never set, and don't suggest they track more. They asked what happened.
