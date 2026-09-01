# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2.0", "pytest"]
# ///
"""Covers the arithmetic and date parsing — the parts that can be quietly wrong."""

import pathlib
from datetime import date

import pytest
from server import (as_tuple, budget_lines, logged_hours, money, rate_for, resolve_client,
                    resolve_project, resolve_window, round_minutes, select, summarize,
                    unknown_client_note, unknown_project_note)

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


# --- roster ---------------------------------------------------------------

ROSTER = {"clients": [{"name": "Acme Industries", "aliases": ["Acme", "acme llc"]},
                      {"name": "Beta Co", "aliases": []}],
          "default_round_to": 15}


@pytest.mark.parametrize("typed,expected", [
    ("Acme Industries", "Acme Industries"),
    ("acme industries", "Acme Industries"),
    ("Acme", "Acme Industries"),
    ("ACME LLC", "Acme Industries"),
    ("  Beta Co ", "Beta Co"),
    ("Gamma", None),
])
def test_resolve_client_collapses_spellings(typed, expected):
    assert resolve_client(typed, ROSTER) == expected


def test_unknown_client_note_names_the_roster():
    note = unknown_client_note("Gamma", ROSTER)
    assert "Gamma" in note and "Acme Industries" in note and "Beta Co" in note


def test_unknown_client_note_is_silent_on_an_empty_roster():
    assert unknown_client_note("Gamma", {"clients": [], "default_round_to": 1}) == ""


ROSTER_PROJECTS = {"clients": [{"name": "Acme Industries", "aliases": ["Acme"],
                                "projects": [{"name": "Redesign", "budget_hours": None},
                                             {"name": "Retainer", "budget_hours": 20}]},
                               {"name": "Beta Co", "aliases": [], "projects": []}],
                   "default_round_to": 1}


@pytest.mark.parametrize("client,typed,expected", [
    ("Acme Industries", "Redesign", "Redesign"),
    ("Acme", "redesign", "Redesign"),
    ("acme", "RETAINER", "Retainer"),
    ("Acme", "SEO", None),
    ("Beta Co", "anything", None),
])
def test_resolve_project_is_scoped_to_the_client(client, typed, expected):
    assert resolve_project(client, typed, ROSTER_PROJECTS) == expected


def test_unknown_project_note_only_fires_for_a_client_that_uses_projects():
    assert "SEO" in unknown_project_note("Acme", "SEO", ROSTER_PROJECTS)
    assert unknown_project_note("Beta Co", "anything", ROSTER_PROJECTS) == ""
    assert unknown_project_note("Acme", "redesign", ROSTER_PROJECTS) == ""


@pytest.mark.parametrize("older,newer", [
    ("0.3.0", "v0.4.0"), ("v0.9.0", "0.10.0"), ("1.0.0", "1.0.1"), ("0.1.0", "1.0.0"),
])
def test_version_comparison_orders_releases(older, newer):
    assert as_tuple(older) < as_tuple(newer)


def test_same_version_is_not_an_update():
    assert not (as_tuple("v0.4.0") > as_tuple("0.4.0"))


ROSTER_RATES = {"clients": [{"name": "Acme", "aliases": ["acme llc"], "rate_per_hour": 150.0},
                            {"name": "Beta Co", "aliases": []}],
                "default_round_to": 1}


def test_rate_for_follows_aliases_and_tolerates_no_rate():
    assert rate_for("acme llc", ROSTER_RATES) == 150.0
    assert rate_for("Beta Co", ROSTER_RATES) is None
    assert rate_for("Nobody", ROSTER_RATES) is None


def test_money_formats_with_separators_and_cents():
    assert money(1837.5) == "$1,837.50"
    assert money(0) == "$0.00"


BUDGETED = {"clients": [{"name": "Acme", "aliases": [],
                         "projects": [{"name": "Redesign", "budget_hours": 10},
                                      {"name": "Retainer", "budget_hours": None}]}],
            "default_round_to": 1}
LOGGED = [{"client": "Acme", "project": "Redesign", "minutes": 300, "start": "2026-09-01T09:00:00-06:00"},
          {"client": "Acme", "project": "Redesign", "minutes": 240, "start": "2026-09-01T09:00:00-06:00"},
          {"client": "Acme", "project": "Retainer", "minutes": 60, "start": "2026-09-01T09:00:00-06:00"},
          {"client": "Other", "project": "Redesign", "minutes": 600, "start": "2026-09-01T09:00:00-06:00"}]


def test_logged_hours_counts_only_this_client_and_project():
    assert logged_hours("Acme", "Redesign", LOGGED) == 9.0


def test_budget_lines_skips_projects_without_a_budget():
    rows = budget_lines(BUDGETED, LOGGED)
    assert [r["project"] for r in rows] == ["Redesign"]
    assert rows[0]["left"] == 1.0
    assert rows[0]["fraction"] == 0.9


def test_budget_lines_reports_an_overrun_as_negative_headroom():
    over = LOGGED + [{"client": "Acme", "project": "Redesign", "minutes": 180,
                      "start": "2026-09-01T09:00:00-06:00"}]
    assert budget_lines(BUDGETED, over)[0]["left"] == -2.0


def test_a_roster_written_by_an_older_version_still_loads(tmp_path, monkeypatch):
    monkeypatch.setenv("TIME_LOG_DIR", str(tmp_path))
    import importlib, server as s
    importlib.reload(s)
    (tmp_path / "clients.json").write_text(
        '{"clients": [{"name": "Acme", "aliases": [], "projects": ["Redesign"]}],'
        ' "default_round_to": 15}')
    roster = s.load_roster()
    assert roster["clients"][0]["projects"] == [{"name": "Redesign", "budget_hours": None}]
    assert s.resolve_project("Acme", "redesign", roster) == "Redesign"


# --- regressions ----------------------------------------------------------

def test_a_roster_client_never_triggers_the_unknown_note(tmp_path, monkeypatch):
    """start_timer warned about clients that were on the roster (fixed in 0.10.0)."""
    monkeypatch.setenv("TIME_LOG_DIR", str(tmp_path))
    import importlib, server as s
    importlib.reload(s)
    s.add_client("Acme Industries", aliases=["Acme"])
    assert "NOTE" not in s.start_timer("Acme")
    s.stop_timer()
    assert "NOTE" in s.start_timer("Gamma Ltd")


def test_the_timer_outlives_the_process_that_started_it(tmp_path, monkeypatch):
    """The timer is a file; a new conversation has to be able to pick it up."""
    monkeypatch.setenv("TIME_LOG_DIR", str(tmp_path))
    import importlib, server as s
    importlib.reload(s)
    s.add_client("Acme")
    s.start_timer("Acme", "Redesign")

    importlib.reload(s)  # stands in for a fresh conversation
    assert "Acme" in s.current_timer()
    assert "A timer is running" in s.running_note()
    assert "0.00h for Acme" in s.stop_timer()
    assert s.running_note() == ""


def test_an_existing_log_is_not_orphaned_by_the_new_default(tmp_path, monkeypatch):
    """Changing the default folder must never strand someone's existing hours."""
    monkeypatch.delenv("TIME_LOG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    import importlib, server as s
    importlib.reload(s)
    assert s.data_dir() == tmp_path / "Documents" / "Time Log"

    legacy = tmp_path / ".time-log"
    legacy.mkdir(exist_ok=True)
    (legacy / "entries.jsonl").write_text("{}\n")
    assert s.data_dir() == legacy
