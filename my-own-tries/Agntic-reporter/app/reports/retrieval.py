"""Retrieval layer over the reports table.

Isolated so it can later be upgraded (e.g. full-text or embeddings)
without touching the agent tools.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Report

logger = logging.getLogger(__name__)


def search_reports(
    session: Session,
    *,
    person: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    text_query: Optional[str] = None,
    limit: int = 50,
) -> list[Report]:
    """Flexible filter + simple text search on raw_text and generated_report."""
    stmt = select(Report).order_by(Report.report_date.desc(), Report.id.desc())

    if person:
        stmt = stmt.where(Report.person.ilike(f"%{person.strip()}%"))
    if date_from:
        stmt = stmt.where(Report.report_date >= date_from)
    if date_to:
        stmt = stmt.where(Report.report_date <= date_to)
    if text_query and text_query.strip():
        q = f"%{text_query.strip()}%"
        stmt = stmt.where(
            or_(
                Report.raw_text.ilike(q),
                Report.generated_report.ilike(q),
                Report.person.ilike(q),
            )
        )

    stmt = stmt.limit(limit)
    results = list(session.scalars(stmt).all())
    logger.info(
        "retrieved %d reports (person=%s, from=%s, to=%s, q=%s)",
        len(results),
        person,
        date_from,
        date_to,
        text_query,
    )
    return results


def get_report_by_id(session: Session, report_id: int) -> Optional[Report]:
    return session.get(Report, report_id)


def get_reports_by_ids(session: Session, ids: Sequence[int]) -> list[Report]:
    if not ids:
        return []
    stmt = select(Report).where(Report.id.in_(list(ids))).order_by(Report.report_date.desc())
    return list(session.scalars(stmt).all())


def get_person_activity(
    session: Session,
    person: str,
    *,
    days: int = 7,
    limit: int = 50,
) -> list[Report]:
    """Activity for a person over the last N days (including today)."""
    today = date.today()
    date_from = today - timedelta(days=days - 1)
    return search_reports(
        session,
        person=person,
        date_from=date_from,
        date_to=today,
        limit=limit,
    )


def get_project_activity(
    session: Session,
    project_keyword: str,
    *,
    days: int | None = None,
    limit: int = 50,
) -> list[Report]:
    """Reports that mention a project / keyword."""
    date_from = None
    if days is not None:
        date_from = date.today() - timedelta(days=days - 1)
    return search_reports(
        session,
        text_query=project_keyword,
        date_from=date_from,
        limit=limit,
    )


def get_reports_by_date_range(
    session: Session,
    date_from: date,
    date_to: date,
    *,
    person: Optional[str] = None,
    limit: int = 100,
) -> list[Report]:
    return search_reports(
        session,
        person=person,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


def format_reports_for_llm(reports: list[Report], *, include_raw: bool = True) -> str:
    """Serialize reports into a compact string the agent can reason over."""
    if not reports:
        return "No reports found."
    parts: list[str] = []
    for r in reports:
        block = [
            f"[Report id={r.id}]",
            f"Person: {r.person}",
            f"Date: {r.report_date.isoformat()}",
        ]
        if r.start_time or r.end_time:
            st = r.start_time.strftime("%H:%M") if r.start_time else "?"
            et = r.end_time.strftime("%H:%M") if r.end_time else "?"
            block.append(f"Hours: {st} – {et}")
        if r.generated_report:
            block.append(f"Generated:\n{r.generated_report}")
        if include_raw and r.raw_text:
            block.append(f"Raw:\n{r.raw_text}")
        parts.append("\n".join(block))
    return "\n\n---\n\n".join(parts)
