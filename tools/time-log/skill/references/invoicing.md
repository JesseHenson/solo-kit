# Turning the log into an invoice

Read this when the user asks to bill someone, draft an invoice, or work out
what they're owed. Don't summarize it into a report — produce lines they can
paste into whatever they actually invoice with.

## Get the numbers right first

1. `list_clients` for the rate and the roster spelling. No rate on file means
   ask once, then `add_client(name, rate_per_hour=...)` so it's there next time.
2. `timesheet_report(client=..., since=..., until=...)` for the period. Leave
   `round_to` alone — the default is the increment they told you they bill at.
3. Read the row count back to them. A period with three entries when they
   expected thirty means the client name or the dates are wrong, not the math.

## Lines

One line per project, not per session — nobody wants a fourteen-row invoice for
a week. Sessions become the line's description.

| Project | Hours | Rate | Amount |
|---|---|---|---|
| Redesign | 12.25 | $150 | $1,837.50 |

Hours come from the report, already rounded. Multiply, don't re-round: rounding
a rounded number is how totals drift from the timesheet the client asked to see.

Then state the total, the period covered in plain dates, and the number of
sessions behind it. If they want detail, offer the per-session breakdown as a
second table rather than putting it in the invoice body.

## What not to do

- **Don't invent line items.** If they want a deposit, expenses, or a discount,
  those aren't in the log — ask for the amount.
- **Don't guess at tax.** Rates and registration vary by country and by client;
  ask what to add, or leave it off and say you did.
- **Don't mark anything as billed.** The log has no billed/unbilled flag. If
  they need one, say so plainly rather than implying the invoice changed state.
- **Don't quietly drop the no-project entries.** Time logged without a project
  still belongs on the invoice; give it a line and ask what to call it.
