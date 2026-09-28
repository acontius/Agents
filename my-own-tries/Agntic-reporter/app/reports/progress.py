"""Progress board: structured path tracking (NOT a Markdown report).

Python owns week numbers, day columns, and percentage calculation.
Percentages are deterministic — never invented by the LLM.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jalali import WEEKDAY_NAMES_EN, WorkWeek, work_week_for
from app.models import DEFAULT_PATHS, ProgressPath, Report
from app.reports.formatting import _actions_from_report, extract_explicit_percentage
from app.reports.retrieval import search_reports

logger = logging.getLogger(__name__)

_CELL_MAX = 28


def ensure_default_paths(session: Session) -> None:
    """Insert default ProgressPath rows when the table is empty."""
    existing = session.scalar(select(ProgressPath).limit(1))
    if existing is not None:
        return
    for name, desc, total in DEFAULT_PATHS:
        session.add(
            ProgressPath(name=name, description=desc, total_items=total)
        )
    session.flush()
    logger.info("seeded default progress paths")


def list_path_names(session: Session) -> list[str]:
    ensure_default_paths(session)
    rows = session.scalars(
        select(ProgressPath).order_by(ProgressPath.name)
    ).all()
    return [r.name for r in rows]


def get_path(session: Session, name: str) -> Optional[ProgressPath]:
    ensure_default_paths(session)
    return session.scalar(
        select(ProgressPath).where(ProgressPath.name == name)
    )


def _short(text: str, max_len: int = _CELL_MAX) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t or "—"


def _count_actions_for_path(
    report_dicts: list[dict[str, Any]],
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for r in report_dicts:
        person = r.get("person") or "unknown"
        acts = _actions_from_report(
            r.get("raw_text") or "", r.get("generated_report")
        )
        counts[person] += max(1, len(acts)) if (r.get("raw_text") or r.get("generated_report")) else 0
    return dict(counts)


def _percentage_for_person(
    *,
    person: str,
    path: Optional[ProgressPath],
    all_path_dicts: list[dict[str, Any]],
    week_dicts: list[dict[str, Any]],
) -> str:
    week_texts: list[str] = []
    all_texts: list[str] = []
    for r in week_dicts:
        if (r.get("person") or "unknown") != person:
            continue
        week_texts.append(r.get("generated_report") or "")
        week_texts.append(r.get("raw_text") or "")
    for r in all_path_dicts:
        if (r.get("person") or "unknown") != person:
            continue
        all_texts.append(r.get("generated_report") or "")
        all_texts.append(r.get("raw_text") or "")

    pct = extract_explicit_percentage(week_texts)
    if pct:
        return pct
    pct = extract_explicit_percentage(all_texts)
    if pct:
        return pct

    if path is not None and path.total_items and path.total_items > 0:
        counts = _count_actions_for_path(all_path_dicts)
        done = counts.get(person, 0)
        val = min(100, int(round(100.0 * done / path.total_items)))
        return f"{val}%"

    return "N/A"


def build_progress_board(
    session: Session,
    *,
    path_name: str,
    week: WorkWeek | None = None,
) -> tuple[str, str, list[list[str]]]:
    ensure_default_paths(session)
    ww = week or work_week_for(date.today())
    path = get_path(session, path_name) if path_name else None
    path_label = path_name or "—"
    week_label = f"Week {ww.week_number}"

    week_reports = search_reports(
        session,
        date_from=ww.start,
        date_to=ww.end,
        limit=200,
    )
    week_dicts = [r.to_dict() for r in week_reports]
    if path_name:
        week_dicts = [
            d for d in week_dicts
            if (d.get("path") or "") == path_name
        ]

    if path_name:
        all_path_reports = session.scalars(
            select(Report)
            .where(Report.path == path_name)
            .order_by(Report.report_date.desc())
            .limit(500)
        ).all()
        all_path_dicts = [r.to_dict() for r in all_path_reports]
    else:
        all_path_dicts = week_dicts

    day_map = ww.day_dates()
    date_to_day = {v: k for k, v in day_map.items()}

    by_person_day: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    people: list[str] = []
    for d in week_dicts:
        person = d.get("person") or "unknown"
        if person not in people:
            people.append(person)
        rd = d.get("report_date")
        if isinstance(rd, str):
            rd = date.fromisoformat(rd)
        if rd not in date_to_day:
            continue
        day_name = date_to_day[rd]
        acts = _actions_from_report(
            d.get("raw_text") or "", d.get("generated_report")
        )
        if acts:
            by_person_day[person][day_name].append(_short(acts[0]))
        else:
            snippet = (d.get("generated_report") or d.get("raw_text") or "")[:_CELL_MAX]
            if snippet:
                by_person_day[person][day_name].append(_short(snippet))

    for d in all_path_dicts:
        person = d.get("person") or "unknown"
        if person not in people:
            people.append(person)

    rows: list[list[str]] = []
    for person in people:
        days = by_person_day.get(person, {})
        day_cells = [
            _short("; ".join(days.get(dn, [])) or "—")
            for dn in WEEKDAY_NAMES_EN[:6]
        ]
        goal = "—"
        for dn in WEEKDAY_NAMES_EN[:6]:
            if days.get(dn):
                goal = days[dn][0]
                break
        pct = _percentage_for_person(
            person=person,
            path=path,
            all_path_dicts=all_path_dicts,
            week_dicts=week_dicts,
        )
        rows.append([person, *day_cells, goal, pct])

    return path_label, week_label, rows


PROGRESS_COLUMNS = [
    "Person",
    "Saturday",
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Goal",
    "Final %",
]


def empty_progress_rows() -> list[list[str]]:
    return []
