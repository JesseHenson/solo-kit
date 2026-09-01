# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2.0", "pytest"]
# ///
"""Covers the arithmetic and date parsing — the parts that can be quietly wrong."""

from datetime import date

import pytest
from server import resolve_window, round_minutes, select, summarize

WED = date(2026, 8, 26)  # a Wednesday


def entry(client, minutes, day, project=None):
    return {"client": client, "project": project,
            "start": f"{day}T09:00:00-05:00", "minutes": minutes}


def test_round_minutes_rounds_up_to_the_increment():
    assert round_minutes(31, 15) == 45
    assert round_minutes(45, 15) == 45
    assert round_minutes(0.5, 15) == 15
    assert round_minutes(31.4, 1) == 31


@pytest.mark.parametrize("phrase,expected", [
    ("today", (date(2026, 8, 26), date(2026, 8, 26))),
    ("yesterday", (date(2026, 8, 25), date(2026, 8, 25))),
    ("this week", (date(2026, 8, 24), date(2026, 8, 30))),
    ("last week", (date(2026, 8, 17), date(2026, 8, 23))),
    ("this month", (date(2026, 8, 1), date(2026, 8, 31))),
    ("last month", (date(2026, 7, 1), date(2026, 7, 31))),
    ("2026-01-09", (date(2026, 1, 9), date(2026, 1, 9))),
])
def test_resolve_window(phrase, expected):
    assert resolve_window(phrase, None, WED) == expected


def test_until_narrows_the_far_end():
    assert resolve_window("this week", "2026-08-26", WED)[1] == date(2026, 8, 26)


def test_select_filters_by_client_case_insensitively_and_by_date():
    rows = [entry("Acme", 60, "2026-08-26"), entry("Other", 60, "2026-08-26"),
            entry("Acme", 60, "2026-08-01")]
    got = select(rows, "acme", None, date(2026, 8, 24), date(2026, 8, 30))
    assert len(got) == 1 and got[0]["minutes"] == 60


def test_summarize_rounds_each_group_not_the_total():
    rows = [entry("Acme", 10, "2026-08-26", "a"), entry("Acme", 10, "2026-08-26", "b")]
    s = summarize(rows, 15)
    assert s["total"] == 30  # two lines rounded to 15 each, not one 20 rounded to 30
    assert s["count"] == 2
