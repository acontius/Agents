"""Progress board: structured path table (not Markdown reports)."""

from __future__ import annotations

from datetime import date, time

from app.jalali import work_week_for
from app.models import ProgressPath, Report
from app.reports.progress import (
    PROGRESS_COLUMNS,
    build_progress_board,
    ensure_default_paths,
    list_path_names,
)
from app.reports.service import create_report


def test_default_paths_seeded(db_session):
    names = list_path_names(db_session)
    assert "Agentic AI Course" in names
    assert "Hack The Box" in names
    assert "General" in names


def test_progress_columns():
    assert "Person" in PROGRESS_COLUMNS
    assert "Saturday" in PROGRESS_COLUMNS
    assert "Final %" in PROGRESS_COLUMNS
    assert "Goal" in PROGRESS_COLUMNS


def test_progress_board_empty(db_session):
    path, week, rows = build_progress_board(
        db_session, path_name="Agentic AI Course"
    )
    assert path == "Agentic AI Course"
    assert week.startswith("Week ")
    assert rows == []


def test_progress_board_after_daily_report(db_session, mock_llm_client):
    create_report(
        db_session,
        person="Amin",
        raw_text="- Implemented tool calling\nprogress: 40%",
        report_date=date.today(),
        start_time=time(9, 0),
        end_time=time(17, 0),
        path="Agentic AI Course",
        generate=True,
        client=mock_llm_client,
    )
    db_session.commit()

    path, week, rows = build_progress_board(
        db_session, path_name="Agentic AI Course"
    )
    assert path == "Agentic AI Course"
    assert week.startswith("Week ")
    assert len(rows) >= 1
    row = rows[0]
    assert row[0] == "Amin"
    assert len(row) == len(PROGRESS_COLUMNS)
    final_pct = row[-1]
    assert final_pct in ("40%", "N/A") or final_pct.endswith("%")
    for cell in row:
        assert "id=" not in str(cell).lower()


def test_percentage_from_total_items(db_session, mock_llm_client):
    from sqlalchemy import select

    ensure_default_paths(db_session)
    path = db_session.scalar(
        select(ProgressPath).where(ProgressPath.name == "PortSwigger")
    )
    assert path is not None
    assert path.total_items is not None and path.total_items > 0

    create_report(
        db_session,
        person="Sara",
        raw_text="- Completed SSRF lab\n- Authentication challenge",
        report_date=date.today(),
        path="PortSwigger",
        generate=False,
    )
    db_session.commit()

    _, _, rows = build_progress_board(db_session, path_name="PortSwigger")
    sara_rows = [r for r in rows if r[0] == "Sara"]
    assert sara_rows
    pct = sara_rows[0][-1]
    assert pct == "N/A" or (pct.endswith("%") and pct[:-1].isdigit())


def test_no_id_in_progress_cells(db_session, mock_llm_client):
    create_report(
        db_session,
        person="Amin",
        raw_text="- Work item",
        report_date=date.today(),
        path="General",
        generate=False,
    )
    db_session.commit()
    _, _, rows = build_progress_board(db_session, path_name="General")
    blob = " ".join(" ".join(r) for r in rows).lower()
    assert "id=" not in blob
    assert "<report" not in blob
