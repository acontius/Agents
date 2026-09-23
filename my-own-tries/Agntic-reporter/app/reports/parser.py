"""Tolerant parser for free-form daily reports.

Extracts person (caller-supplied), date, start/end times and preserves
the entire original text. Does NOT require JSON or rigid formatting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Optional
from urllib.parse import urlparse

# Persian / English labels for entry & exit times
_TIME_PATTERNS = [
    # ورود: 08:30  |  ورود : 8:30
    re.compile(
        r"(?:ورود|entry|start|از)\s*[:：]?\s*(\d{1,2})[:：.](\d{2})",
        re.IGNORECASE,
    ),
    # خروج: 17:15
    re.compile(
        r"(?:خروج|exit|end|تا)\s*[:：]?\s*(\d{1,2})[:：.](\d{2})",
        re.IGNORECASE,
    ),
]

_URL_RE = re.compile(
    r"https?://[^\s<>\"')\]]+",
    re.IGNORECASE,
)

_DATE_PATTERNS = [
    re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})"),
    re.compile(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})"),
]


@dataclass
class ParsedReport:
    """Structured view of a free-form daily report."""

    person: str
    report_date: date
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    raw_text: str = ""
    urls: list[str] = field(default_factory=list)
    activities: list[str] = field(default_factory=list)

    def working_hours_str(self) -> str:
        if self.start_time and self.end_time:
            return f"{self.start_time.strftime('%H:%M')} تا {self.end_time.strftime('%H:%M')}"
        if self.start_time:
            return f"از {self.start_time.strftime('%H:%M')}"
        if self.end_time:
            return f"تا {self.end_time.strftime('%H:%M')}"
        return "ساعت کاری مشخص نشده"


def _parse_time(hour: str, minute: str) -> time:
    h, m = int(hour), int(minute)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"Invalid time: {h}:{m}")
    return time(h, m)


def extract_times(text: str) -> tuple[Optional[time], Optional[time]]:
    """Extract start and end times from labels like ورود/خروج."""
    start: Optional[time] = None
    end: Optional[time] = None
    for i, pattern in enumerate(_TIME_PATTERNS):
        match = pattern.search(text)
        if match:
            try:
                t = _parse_time(match.group(1), match.group(2))
                if i == 0:
                    start = t
                else:
                    end = t
            except ValueError:
                continue
    # Fallback: first two HH:MM occurrences if labels missing
    if start is None or end is None:
        loose = re.findall(r"\b(\d{1,2})[:：.](\d{2})\b", text)
        times: list[time] = []
        for h, m in loose:
            try:
                times.append(_parse_time(h, m))
            except ValueError:
                continue
        if start is None and times:
            start = times[0]
        if end is None and len(times) > 1:
            end = times[1]
    return start, end


def extract_urls(text: str) -> list[str]:
    """Return unique, syntactically valid http(s) URLs."""
    found = _URL_RE.findall(text)
    urls: list[str] = []
    for u in found:
        u = u.rstrip(".,;:)")
        try:
            parsed = urlparse(u)
            if parsed.scheme in ("http", "https") and parsed.netloc:
                if u not in urls:
                    urls.append(u)
        except Exception:
            continue
    return urls


def extract_activities(text: str) -> list[str]:
    """Heuristic extraction of bullet-point style activities."""
    activities: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Common bullet markers
        cleaned = re.sub(r"^[-•*–—]\s*", "", line)
        cleaned = re.sub(r"^\d+[.)]\s*", "", cleaned)
        if cleaned != line and len(cleaned) > 3:
            activities.append(cleaned)
    return activities


def parse_date_from_text(text: str, fallback: date | None = None) -> date:
    """Try to find a date in the text; otherwise use fallback or today."""
    for pattern in _DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            groups = m.groups()
            try:
                if len(groups[0]) == 4:  # YYYY-MM-DD
                    y, mo, d = int(groups[0]), int(groups[1]), int(groups[2])
                else:  # DD-MM-YYYY
                    d, mo, y = int(groups[0]), int(groups[1]), int(groups[2])
                return date(y, mo, d)
            except ValueError:
                continue
    return fallback or date.today()


def parse_report(
    raw_text: str,
    person: str,
    report_date: date | None = None,
    start_time: time | None = None,
    end_time: time | None = None,
) -> ParsedReport:
    """Parse free-form report text into a structured ParsedReport.

    Explicitly provided fields (date, times) take precedence over
    anything extracted from the text.
    """
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Report text is empty")
    if not person or not person.strip():
        raise ValueError("Person name is required")

    extracted_start, extracted_end = extract_times(text)
    final_start = start_time or extracted_start
    final_end = end_time or extracted_end
    final_date = report_date or parse_date_from_text(text)

    return ParsedReport(
        person=person.strip(),
        report_date=final_date,
        start_time=final_start,
        end_time=final_end,
        raw_text=text,
        urls=extract_urls(text),
        activities=extract_activities(text),
    )
