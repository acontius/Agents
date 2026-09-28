"""Daily / weekly / monthly Markdown format tests (no progress tables)."""

from datetime import date, time

from app.jalali import work_week_for
from app.reports.formatting import (
    extract_explicit_percentage,
    format_daily_markdown,
    format_monthly_markdown,
    format_weekly_markdown,
)


def test_daily_markdown_structure():
    md = format_daily_markdown(
        person="Amin",
        report_date=date(2026, 9, 27),
        start_time=time(10, 40),
        end_time=time(20, 0),
        actions=["Implemented tool calling", "Reviewed OpenRouter"],
    )
    assert md.startswith("#daily # amin")
    assert "amin —" in md
    assert "entered at =" in md
    assert "done at =" in md
    assert "actions:" in md
    assert "- Implemented tool calling" in md
    assert "id=" not in md.lower()
    assert "ID:" not in md


def test_weekly_markdown_no_progress_table():
    week = work_week_for(date(2026, 9, 27))
    md = format_weekly_markdown(
        person="Amin",
        week=week,
        day_summaries={"Amin": {"Saturday": "Setup", "Monday": "Coding"}},
        narrative={
            "assigned": ["Ship agent"],
            "completed": ["Setup done"],
            "in_progress": ["Coding"],
            "next_week": ["Tests"],
            "blockers": ["-"],
            "suggestions": ["-"],
        },
        goals={"Amin": "Ship M1"},
        final_pct={"Amin": "N/A"},
        people=["Amin"],
    )
    assert md.startswith("#weekly # amin")
    assert f"Week {week.week_number}" in md
    assert "### Assigned Tasks" in md
    assert "### Completed Work" in md
    assert "| Person | Saturday |" not in md
    assert "Final %" not in md
    assert "id=" not in md.lower()


def test_monthly_markdown_no_progress_table():
    md = format_monthly_markdown(
        person="Amin",
        month_label="مهر ۱۴۰۵",
        narrative={
            "assigned": ["A"],
            "completed": ["B"],
            "in_progress": ["C"],
            "next_month": ["D"],
            "blockers": ["-"],
            "suggestions": ["-"],
        },
        table_rows=[],
    )
    assert md.startswith("#monthly # amin")
    assert "Month:" in md
    assert "| Person | Completed Work |" not in md
    assert "Final %" not in md
    assert "id=" not in md.lower()


def test_extract_percentage_evidence_based():
    assert extract_explicit_percentage(["progress: 70%"]) == "70%"
    assert extract_explicit_percentage(["no numbers here"]) is None
    assert extract_explicit_percentage(["about half done"]) is None


def test_no_fabricated_pct_in_weekly():
    week = work_week_for(date(2026, 9, 27))
    md = format_weekly_markdown(
        person=None,
        week=week,
        day_summaries={"Sara": {}},
        narrative={
            "assigned": [],
            "completed": [],
            "in_progress": [],
            "next_week": [],
            "blockers": [],
            "suggestions": [],
        },
        goals={"Sara": "—"},
        final_pct={"Sara": "N/A"},
        people=["Sara"],
    )
    assert "### Assigned Tasks" in md
    assert "| Sara |" not in md
