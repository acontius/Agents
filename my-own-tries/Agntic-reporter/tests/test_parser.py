"""Tests for the tolerant report parser."""

from datetime import date, time

import pytest

from app.reports.parser import (
    extract_activities,
    extract_times,
    extract_urls,
    parse_report,
)


def test_extract_times_persian_labels():
    text = "ورود: 08:30\nخروج: 17:15\nکارها: ..."
    start, end = extract_times(text)
    assert start == time(8, 30)
    assert end == time(17, 15)


def test_extract_times_english_labels():
    text = "entry: 9:00\nexit: 18:00"
    start, end = extract_times(text)
    assert start == time(9, 0)
    assert end == time(18, 0)


def test_extract_times_missing():
    start, end = extract_times("just some text without times")
    assert start is None
    assert end is None


def test_extract_urls():
    text = "read this https://example.com/article and also http://foo.bar/x"
    urls = extract_urls(text)
    assert "https://example.com/article" in urls
    assert "http://foo.bar/x" in urls


def test_extract_urls_ignores_invalid():
    assert extract_urls("no urls here") == []
    assert extract_urls("see ftp://bad") == []


def test_extract_activities_bullets():
    text = """
کارها:
- روی Agentic کار کردم
• Tool Calling
* OpenRouter
1. something else
"""
    acts = extract_activities(text)
    assert any("Agentic" in a for a in acts)
    assert any("Tool Calling" in a for a in acts)


def test_parse_report_preserves_raw_text():
    raw = "ورود: 08:30\nخروج: 17:00\n- کار A\n- کار B"
    parsed = parse_report(raw, person="Amin", report_date=date(2026, 9, 22))
    assert parsed.raw_text == raw
    assert parsed.person == "Amin"
    assert parsed.report_date == date(2026, 9, 22)
    assert parsed.start_time == time(8, 30)
    assert parsed.end_time == time(17, 0)
    assert len(parsed.activities) >= 2


def test_parse_report_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_report("", person="Amin")


def test_parse_report_missing_person_raises():
    with pytest.raises(ValueError, match="Person"):
        parse_report("some text", person="")


def test_explicit_times_override_extracted():
    raw = "ورود: 08:00\nخروج: 16:00"
    parsed = parse_report(
        raw,
        person="Amin",
        start_time=time(9, 0),
        end_time=time(18, 0),
    )
    assert parsed.start_time == time(9, 0)
    assert parsed.end_time == time(18, 0)
