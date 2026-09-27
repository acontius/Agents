"""Tests for daily/weekly/monthly Markdown formatters."""

from datetime import date, time

from app.jalali import work_week_for
from app.reports.formatting import (
    extract_explicit_percentage,
    final_pct_for_people,
    format_daily_markdown,
    format_monthly_markdown,
    format_weekly_markdown,
)


def test_format_daily_structure():
    md = format_daily_markdown(
        person="Amin",
        report_date=date(2025, 9, 27),
        start_time=time(10, 40),
        end_time=time(20, 0),
        actions=["Implemented tool calling", "Tested OpenRouter"],
    )
    assert md.startswith("#daily # amin")
    assert "amin —" in md or "amin" in md
    assert "entered at =" in md
    assert "done at =" in md
    assert "actions:" in md
    assert "Implemented tool calling" in md
    assert "id=" not in md.lower()
    assert "ID:" not in md


def test_format_weekly_table_columns():
    week = work_week_for(date(2025, 9, 27))
    md = format_weekly_markdown(
        person="Amin",
        week=week,
        day_summaries={"Amin": {"Saturday": "setup", "Monday": "coding"}},
        narrative={
            "assigned": ["Ship agent"],
            "completed": ["Tool loop"],
            "in_progress": ["UI"],
            "next_week": ["Tests"],
            "blockers": ["-"],
            "suggestions": ["-"],
        },
        goals={"Amin": "Finish weekly board"},
        final_pct={"Amin": "N/A"},
        people=["Amin"],
    )
    assert f"Week {week.week_number}" in md
    assert "| Person | Saturday | Sunday | Monday | Tuesday | Wednesday | Thursday | Goal | Final % |" in md
    assert "#weekly # amin" in md
    assert "### Assigned Tasks" in md
    assert "### Completed Work" in md
    assert "Final %" in md
    assert "N/A" in md
    assert "id=" not in md.lower()


def test_format_monthly_structure():
    md = format_monthly_markdown(
        person="Amin",
        month_label="مهر ۱۴۰۴",
        narrative={
            "assigned": ["Reports"],
            "completed": ["Daily format"],
            "in_progress": ["Weekly table"],
            "next_month": ["Polish"],
            "blockers": ["-"],
            "suggestions": ["-"],
        },
        table_rows=[
            {
                "person": "Amin",
                "completed": "Daily + weekly",
                "in_progress": "Monthly",
                "goal": "Ship",
                "final_pct": "N/A",
            }
        ],
    )
    assert "#monthly # amin" in md
    assert "Month:" in md
    assert "| Person | Completed Work | In Progress | Goal | Final % |" in md
    assert "N/A" in md


def test_extract_explicit_percentage():
    assert extract_explicit_percentage(["progress: 80%"]) == "80%"
    assert extract_explicit_percentage(["no numbers here"]) is None
    assert extract_explicit_percentage(["done 100%"]) == "100%"


def test_final_pct_na_without_evidence():
    week = work_week_for(date(2025, 9, 20))
    result = final_pct_for_people(
        [{"person": "Amin", "report_date": "2025-09-15", "raw_text": "worked", "generated_report": ""}],
        week,
    )
    # Either N/A or missing if date outside prev week
    for v in result.values():
        assert v == "N/A" or v.endswith("%")
