"""Weekly and monthly report aggregation.

Python owns date ranges and week numbers.
The LLM only summarizes evidence into narrative sections.
Progress board lives in the Progress tab — not in report Markdown.
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import date
from typing import Any, Optional

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jalali import (
    JalaliMonth,
    WorkWeek,
    previous_work_week,
    work_week_for,
    jalali_month_for,
)
from app.reports.formatting import (
    _actions_from_report,
    build_day_summaries_from_dicts,
    extract_explicit_percentage,
    final_pct_for_people,
    format_monthly_markdown,
    format_weekly_markdown,
)
from app.reports.retrieval import search_reports

logger = logging.getLogger(__name__)


def _client() -> OpenAI:
    settings = get_settings()
    settings.validate_for_llm()
    return OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )


def _reports_to_dicts(reports) -> list[dict[str, Any]]:
    return [r.to_dict() for r in reports]


def _distinct_people(dicts: list[dict]) -> list[str]:
    seen: list[str] = []
    for d in dicts:
        p = d.get("person") or "unknown"
        if p not in seen:
            seen.append(p)
    return seen


def _llm_narrative(
    *,
    kind: str,
    person: str | None,
    period_label: str,
    context: str,
    client: OpenAI | None,
) -> dict[str, list[str]]:
    settings = get_settings()
    next_key = "next_week" if kind == "weekly" else "next_month"
    system = (
        "You summarize team daily reports into structured English sections. "
        "Respond with JSON only, no markdown fences. Schema:\n"
        '{\n'
        '  "assigned": ["..."],\n'
        '  "completed": ["..."],\n'
        '  "in_progress": ["..."],\n'
        f'  "{next_key}": ["..."],\n'
        '  "blockers": ["..."],\n'
        '  "suggestions": ["..."],\n'
        '  "goals": {"PersonName": "goal text"}\n'
        "}\n"
        "Rules:\n"
        "- Use ONLY facts present in the reports.\n"
        "- Do NOT invent activities or percentages.\n"
        "- Keep each item short (one sentence).\n"
        "- Output English only.\n"
        "- If a section has no evidence, use an empty list.\n"
    )
    user = f"Period: {period_label}\nFocus person: {person or 'all team'}\n\nReports:\n{context}"
    empty = {
        "assigned": [],
        "completed": [],
        "in_progress": [],
        next_key: [],
        "blockers": [],
        "suggestions": [],
        "goals": {},
    }
    try:
        llm = client or _client()
        response = llm.chat.completions.create(
            model=settings.openrouter_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=1200,
        )
        raw = (response.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        for k in empty:
            if k == "goals":
                if not isinstance(data.get("goals"), dict):
                    data["goals"] = {}
            else:
                if not isinstance(data.get(k), list):
                    data[k] = []
        return data
    except Exception as exc:
        logger.warning("%s narrative LLM failed: %s", kind, exc)
        return empty


def _context_from_dicts(dicts: list[dict]) -> str:
    parts = []
    for d in dicts:
        parts.append(
            f"Person: {d.get('person')} | Date: {d.get('report_date')}\n"
            f"Generated:\n{d.get('generated_report') or ''}\n"
            f"Raw:\n{(d.get('raw_text') or '')[:500]}"
        )
    return "\n\n---\n\n".join(parts) if parts else "No reports."


def generate_weekly_markdown(
    session: Session,
    *,
    week: WorkWeek,
    person: str | None = None,
    client: OpenAI | None = None,
) -> str:
    """Full weekly Markdown narrative only (progress board is in Progress tab)."""
    reports = search_reports(
        session, person=person, date_from=week.start, date_to=week.end, limit=200
    )
    dicts = _reports_to_dicts(reports)
    if not dicts:
        return (
            f"#weekly # {person or 'team'}\n\n"
            f"Week {week.week_number}\n"
            f"{week.label()}\n\n"
            "No reports found for this period."
        )
    people = _distinct_people(dicts)
    day_summaries = build_day_summaries_from_dicts(dicts, week)
    narrative = _llm_narrative(
        kind="weekly",
        person=person,
        period_label=week.label(persian_digits=False),
        context=_context_from_dicts(dicts),
        client=client,
    )
    goals = narrative.pop("goals", {}) if isinstance(narrative.get("goals"), dict) else {}
    for p in people:
        goals.setdefault(p, "—")
    if not narrative.get("completed"):
        narrative["completed"] = []
        for p, days in day_summaries.items():
            for d, s in days.items():
                if s and s != "—":
                    narrative["completed"].append(f"{p} ({d}): {s}")
    return format_weekly_markdown(
        person=person,
        week=week,
        day_summaries=day_summaries,
        narrative=narrative,
        goals=goals,
        final_pct={p: "N/A" for p in people},
        people=people,
    )


def generate_monthly_markdown(
    session: Session,
    *,
    month: JalaliMonth,
    person: str | None = None,
    client: OpenAI | None = None,
) -> str:
    reports = search_reports(
        session, person=person, date_from=month.start, date_to=month.end, limit=500
    )
    dicts = _reports_to_dicts(reports)
    label = month.label()
    if not dicts:
        return (
            f"#monthly # {person or 'team'}\n\n"
            f"Month: {label}\n\n"
            "No reports found for this period."
        )
    people = _distinct_people(dicts)
    narrative = _llm_narrative(
        kind="monthly",
        person=person,
        period_label=month.label(persian_digits=False),
        context=_context_from_dicts(dicts),
        client=client,
    )
    goals = narrative.pop("goals", {}) if isinstance(narrative.get("goals"), dict) else {}
    if not narrative.get("completed"):
        by_person: dict[str, list[dict]] = defaultdict(list)
        for d in dicts:
            by_person[d.get("person") or "unknown"].append(d)
        completed_items: list[str] = []
        for p in people:
            acts: list[str] = []
            for d in by_person[p]:
                acts.extend(
                    _actions_from_report(
                        d.get("raw_text") or "", d.get("generated_report")
                    )[:2]
                )
            if acts:
                completed_items.append(f"{p}: " + "; ".join(acts[:3]))
        narrative["completed"] = completed_items
    return format_monthly_markdown(
        person=person,
        month_label=label,
        narrative=narrative,
        table_rows=[],
    )


def list_available_dates(session: Session, *, limit: int = 90) -> list[date]:
    reports = search_reports(session, limit=limit * 3)
    seen: set[date] = set()
    dates: list[date] = []
    for r in reports:
        if r.report_date not in seen:
            seen.add(r.report_date)
            dates.append(r.report_date)
    dates.sort(reverse=True)
    return dates[:limit]


def list_available_weeks(session: Session, *, limit: int = 26) -> list[WorkWeek]:
    dates = list_available_dates(session, limit=200)
    weeks: list[WorkWeek] = []
    seen: set[date] = set()
    for d in dates:
        ww = work_week_for(d)
        if ww.start not in seen:
            seen.add(ww.start)
            weeks.append(ww)
    weeks.sort(key=lambda w: w.start, reverse=True)
    return weeks[:limit]


def list_available_months(session: Session, *, limit: int = 18) -> list[JalaliMonth]:
    dates = list_available_dates(session, limit=400)
    months: list[JalaliMonth] = []
    seen: set[tuple[int, int]] = set()
    for d in dates:
        m = jalali_month_for(d)
        key = (m.year, m.month)
        if key not in seen:
            seen.add(key)
            months.append(m)
    months.sort(key=lambda m: (m.year, m.month), reverse=True)
    return months[:limit]


def generate_daily_markdown_for_date(
    session: Session,
    *,
    report_date: date,
    person: str | None = None,
) -> str:
    reports = search_reports(
        session, person=person, date_from=report_date, date_to=report_date, limit=50
    )
    if not reports:
        return f"No daily reports found for {report_date.isoformat()}."
    parts = []
    for r in reports:
        if r.generated_report and r.generated_report.strip().startswith("#daily"):
            parts.append(r.generated_report.strip())
        else:
            from app.reports.formatting import format_daily_markdown
            acts = _actions_from_report(r.raw_text or "", r.generated_report)
            parts.append(
                format_daily_markdown(
                    person=r.person,
                    report_date=r.report_date,
                    start_time=r.start_time,
                    end_time=r.end_time,
                    actions=acts or ["(see raw notes)"],
                )
            )
    return "\n\n---\n\n".join(parts)
