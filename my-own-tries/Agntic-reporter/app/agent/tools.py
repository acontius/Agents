"""Tool definitions and Python implementations for the agent.

Each tool is a plain function that receives a DB session (or no session
for web fetch) and returns a JSON-serializable string result.
The LLM only sees the JSON schemas; execution stays in Python.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.models import Report
from app.reports.retrieval import (
    format_reports_for_llm,
    get_person_activity,
    get_project_activity,
    get_report_by_id,
    get_reports_by_date_range,
    search_reports,
)
from app.web.search import fetch_url_summary

logger = logging.getLogger(__name__)


def _parse_date(value: str | None) -> Optional[date]:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Could not parse date: {value!r}. Use YYYY-MM-DD.")


def tool_search_reports(
    session: Session,
    person: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    text_query: Optional[str] = None,
    limit: int = 30,
) -> str:
    """Search reports with optional person, date range and free-text filters."""
    reports = search_reports(
        session,
        person=person,
        date_from=_parse_date(date_from),
        date_to=_parse_date(date_to),
        text_query=text_query,
        limit=min(limit, 50),
    )
    return format_reports_for_llm(reports)


def tool_get_person_activity(
    session: Session,
    person: str,
    days: int = 7,
) -> str:
    """Get activity for a person over the last N days."""
    reports = get_person_activity(session, person, days=days)
    return format_reports_for_llm(reports)


def tool_get_project_activity(
    session: Session,
    project_keyword: str,
    days: Optional[int] = None,
) -> str:
    """Get reports that mention a project or keyword."""
    reports = get_project_activity(session, project_keyword, days=days)
    return format_reports_for_llm(reports)


def tool_get_reports_by_date_range(
    session: Session,
    date_from: str,
    date_to: str,
    person: Optional[str] = None,
) -> str:
    """Get all reports in an inclusive date range."""
    reports = get_reports_by_date_range(
        session,
        date_from=_parse_date(date_from),  # type: ignore[arg-type]
        date_to=_parse_date(date_to),  # type: ignore[arg-type]
        person=person,
    )
    return format_reports_for_llm(reports)


def tool_get_report_by_id(session: Session, report_id: int) -> str:
    """Fetch a single report by its id."""
    report = get_report_by_id(session, int(report_id))
    if not report:
        return f"No report found with id={report_id}"
    return format_reports_for_llm([report])


def tool_fetch_url(url: str) -> str:
    """Fetch and briefly summarize an external URL that appeared in a report."""
    return fetch_url_summary(url)


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_reports",
            "description": (
                "Search stored daily reports. Filter by person name, date range "
                "(YYYY-MM-DD), and/or free-text keyword that appears in the report."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "person": {"type": "string", "description": "Person name (partial match ok)"},
                    "date_from": {"type": "string", "description": "Start date YYYY-MM-DD"},
                    "date_to": {"type": "string", "description": "End date YYYY-MM-DD"},
                    "text_query": {"type": "string", "description": "Keyword / project name"},
                    "limit": {"type": "integer", "description": "Max results (default 30)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_person_activity",
            "description": "Get a person's activity over the last N days (default 7).",
            "parameters": {
                "type": "object",
                "properties": {
                    "person": {"type": "string", "description": "Person name"},
                    "days": {"type": "integer", "description": "Number of days including today"},
                },
                "required": ["person"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_activity",
            "description": "Find reports that mention a project or keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_keyword": {"type": "string"},
                    "days": {"type": "integer", "description": "Optional day window"},
                },
                "required": ["project_keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_reports_by_date_range",
            "description": "All reports between two inclusive dates (YYYY-MM-DD).",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string"},
                    "date_to": {"type": "string"},
                    "person": {"type": "string"},
                },
                "required": ["date_from", "date_to"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_report_by_id",
            "description": "Fetch one report by its numeric id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "report_id": {"type": "integer"},
                },
                "required": ["report_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": (
                "Fetch a URL that appeared in a report and return a short text excerpt. "
                "Use only when extra context about a linked article is useful."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                },
                "required": ["url"],
            },
        },
    },
]


TOOL_DISPATCH: dict[str, Callable[..., str]] = {
    "search_reports": tool_search_reports,
    "get_person_activity": tool_get_person_activity,
    "get_project_activity": tool_get_project_activity,
    "get_reports_by_date_range": tool_get_reports_by_date_range,
    "get_report_by_id": tool_get_report_by_id,
    "fetch_url": tool_fetch_url,
}

SESSION_TOOLS = {
    "search_reports",
    "get_person_activity",
    "get_project_activity",
    "get_reports_by_date_range",
    "get_report_by_id",
}


def execute_tool(name: str, arguments: dict[str, Any], session: Session | None) -> str:
    """Run a tool by name. Returns a string result (or error message)."""
    logger.info("tool call: %s args=%s", name, arguments)
    fn = TOOL_DISPATCH.get(name)
    if fn is None:
        return f"Error: unknown tool '{name}'"
    try:
        if name in SESSION_TOOLS:
            if session is None:
                return "Error: database session not available"
            result = fn(session, **arguments)
        else:
            result = fn(**arguments)
        return result
    except TypeError as exc:
        return f"Error: bad arguments for {name}: {exc}"
    except Exception as exc:
        logger.exception("tool %s failed", name)
        return f"Error executing {name}: {type(exc).__name__}: {exc}"
