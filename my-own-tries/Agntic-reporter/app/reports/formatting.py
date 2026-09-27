"""Markdown formatters for daily / weekly / monthly English reports.

No database IDs appear in any user-facing output.
Final % is never invented — only emitted when evidence exists.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, time
from typing import Any, Optional, Sequence

from app.jalali import (
    WEEKDAY_NAMES_EN,
    WorkWeek,
    format_jalali,
    format_jalali_month,
    format_time_display,
    jalali_month_for,
    previous_work_week,
    work_week_for,
)


def _username(person: str) -> str:
    return (person or "unknown").strip().lower().replace(" ", "")


def _safe_cell(text: str, max_len: int = 80) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = t.replace("|", "/")
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t or "—"


def _actions_from_report(raw: str, generated: str | None) -> list[str]:
    source = generated or raw or ""
    actions: list[str] = []
    for line in source.splitlines():
        line = line.strip()
        m = re.match(r"^[-•*]\s+(.+)", line)
        if m:
            actions.append(m.group(1).strip())
            continue
        m = re.match(r"^\d+[.)]\s+(.+)", line)
        if m:
            actions.append(m.group(1).strip())
    return actions


def format_daily_markdown(
    *,
    person: str,
    report_date: date,
    start_time: Optional[time],
    end_time: Optional[time],
    actions: list[str],
) -> str:
    uname = _username(person)
    jdate = format_jalali(report_date)
    entered = format_time_display(start_time)
    done = format_time_display(end_time)
    lines = [
        f"#daily # {uname}",
        "",
        f"{uname} — {jdate}",
        "",
        f"entered at = {entered}",
        f"done at = {done}",
        "",
        "actions:",
    ]
    if actions:
        for a in actions:
            lines.append(f"- {a}")
    else:
        lines.append("- (no actions extracted)")
    return "\n".join(lines)


def extract_explicit_percentage(texts: Sequence[str]) -> Optional[str]:
    pattern = re.compile(
        r"(?:progress|completion|complete[d]?|done|نهایی|پیشرفت|درصد)\s*[:=]?\s*(\d{1,3})\s*%",
        re.IGNORECASE,
    )
    pattern2 = re.compile(r"\b(\d{1,3})\s*%\s*(?:complete|done|finished|progress)?", re.I)
    found: list[int] = []
    for text in texts:
        if not text:
            continue
        for pat in (pattern, pattern2):
            for m in pat.finditer(text):
                val = int(m.group(1))
                if 0 <= val <= 100:
                    found.append(val)
    if not found:
        return None
    return f"{found[-1]}%"


def format_weekly_markdown(
    *,
    person: str | None,
    week: WorkWeek,
    day_summaries: dict[str, dict[str, str]],
    narrative: dict[str, list[str]],
    goals: dict[str, str],
    final_pct: dict[str, str],
    people: list[str],
) -> str:
    uname = _username(person) if person else "team"
    lines = [
        f"#weekly # {uname}",
        "",
        f"Week {week.week_number}",
        format_jalali(week.start) + " — " + format_jalali(week.end),
        "",
        "### Assigned Tasks",
    ]
    tasks = narrative.get("assigned", [])
    if tasks:
        for i, t in enumerate(tasks, 1):
            lines.append(f"{i}. {t}")
    else:
        lines.append("1. (not specified in reports)")
    lines.append("")
    lines.append("### Completed Work")
    completed = narrative.get("completed", [])
    if completed:
        for i, t in enumerate(completed, 1):
            lines.append(f"{i}. {t}")
    else:
        lines.append("1. (not specified in reports)")
    lines.append("")
    lines.append("### In Progress")
    for t in narrative.get("in_progress", []) or ["-"]:
        lines.append(f"- {t}" if not str(t).startswith("-") else str(t))
    lines.append("")
    lines.append("### Next Week Plan")
    for t in narrative.get("next_week", []) or ["-"]:
        lines.append(f"- {t}" if not str(t).startswith("-") else str(t))
    lines.append("")
    lines.append("### Challenges / Blockers")
    for t in narrative.get("blockers", []) or ["-"]:
        lines.append(f"- {t}" if not str(t).startswith("-") else str(t))
    lines.append("")
    lines.append("### Suggestions / Improvements")
    for t in narrative.get("suggestions", []) or ["-"]:
        lines.append(f"- {t}" if not str(t).startswith("-") else str(t))
    lines.append("")
    lines.append(
        "| Person | Saturday | Sunday | Monday | Tuesday | Wednesday | Thursday | Goal | Final % |"
    )
    lines.append(
        "| ------ | -------- | ------ | ------ | ------- | --------- | -------- | ---- | ------- |"
    )
    for p in people:
        days = day_summaries.get(p, {})
        cells = [
            _safe_cell(p, 20),
            *(_safe_cell(days.get(d, "—"), 40) for d in WEEKDAY_NAMES_EN[:6]),
            _safe_cell(goals.get(p, "—"), 30),
            _safe_cell(final_pct.get(p, "N/A"), 12),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def format_monthly_markdown(
    *,
    person: str | None,
    month_label: str,
    narrative: dict[str, list[str]],
    table_rows: list[dict[str, str]],
) -> str:
    uname = _username(person) if person else "team"
    lines = [
        f"#monthly # {uname}",
        "",
        f"Month: {month_label}",
        "",
        "### Assigned Tasks",
    ]
    for i, t in enumerate(narrative.get("assigned", []) or ["(not specified)"], 1):
        lines.append(f"{i}. {t}")
    lines.append("")
    lines.append("### Completed Work")
    for i, t in enumerate(narrative.get("completed", []) or ["(not specified)"], 1):
        lines.append(f"{i}. {t}")
    lines.append("")
    lines.append("### In Progress")
    for t in narrative.get("in_progress", []) or ["-"]:
        lines.append(f"- {t}" if not str(t).startswith("-") else str(t))
    lines.append("")
    lines.append("### Next Month Plan")
    for t in narrative.get("next_month", []) or ["-"]:
        lines.append(f"- {t}" if not str(t).startswith("-") else str(t))
    lines.append("")
    lines.append("### Challenges / Blockers")
    for t in narrative.get("blockers", []) or ["-"]:
        lines.append(f"- {t}" if not str(t).startswith("-") else str(t))
    lines.append("")
    lines.append("### Suggestions / Improvements")
    for t in narrative.get("suggestions", []) or ["-"]:
        lines.append(f"- {t}" if not str(t).startswith("-") else str(t))
    lines.append("")
    lines.append("| Person | Completed Work | In Progress | Goal | Final % |")
    lines.append("| ------ | -------------- | ----------- | ---- | ------- |")
    for row in table_rows:
        cells = [
            _safe_cell(row.get("person", "—"), 20),
            _safe_cell(row.get("completed", "—"), 50),
            _safe_cell(row.get("in_progress", "—"), 40),
            _safe_cell(row.get("goal", "—"), 30),
            _safe_cell(row.get("final_pct", "N/A"), 12),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_day_summaries_from_dicts(
    report_dicts: list[dict[str, Any]],
    week: WorkWeek,
) -> dict[str, dict[str, str]]:
    day_map = week.day_dates()
    date_to_day = {v: k for k, v in day_map.items()}
    by_person_day: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for r in report_dicts:
        rd = r.get("report_date")
        if isinstance(rd, str):
            rd = date.fromisoformat(rd)
        if rd not in date_to_day:
            continue
        day_name = date_to_day[rd]
        person = r.get("person") or "unknown"
        acts = _actions_from_report(r.get("raw_text") or "", r.get("generated_report"))
        if acts:
            by_person_day[person][day_name].extend(acts[:3])
        else:
            snippet = (r.get("generated_report") or r.get("raw_text") or "")[:60]
            if snippet:
                by_person_day[person][day_name].append(snippet)
    result: dict[str, dict[str, str]] = {}
    for person, days in by_person_day.items():
        result[person] = {
            d: _safe_cell("; ".join(items), 50) for d, items in days.items()
        }
    return result


def final_pct_for_people(
    report_dicts: list[dict[str, Any]],
    prev_week: WorkWeek,
) -> dict[str, str]:
    result: dict[str, str] = {}
    by_person: dict[str, list[str]] = defaultdict(list)
    for r in report_dicts:
        rd = r.get("report_date")
        if isinstance(rd, str):
            rd = date.fromisoformat(rd)
        if rd is None or not (prev_week.start <= rd <= prev_week.end):
            continue
        person = r.get("person") or "unknown"
        by_person[person].append(r.get("generated_report") or "")
        by_person[person].append(r.get("raw_text") or "")
    for person, texts in by_person.items():
        pct = extract_explicit_percentage(texts)
        result[person] = pct if pct else "N/A"
    return result
