"""Tests for Jalali calendar utilities."""

from datetime import date

from app.jalali import (
    WorkWeek,
    format_jalali,
    gregorian_to_jalali,
    jalali_month_for,
    jalali_to_gregorian,
    jalali_week_number,
    make_choice,
    parse_choice_key,
    previous_work_week,
    saturday_of_week,
    work_week_for,
)


def test_gregorian_to_jalali_known():
    # 2025-09-27 → 5 Mehr 1404 (approx; verify round-trip)
    g = date(2025, 9, 27)
    jy, jm, jd = gregorian_to_jalali(g)
    assert jy >= 1400
    assert 1 <= jm <= 12
    assert 1 <= jd <= 31
    back = jalali_to_gregorian(jy, jm, jd)
    assert back == g


def test_format_jalali_contains_month_name():
    g = date(2025, 9, 27)
    text = format_jalali(g, persian_digits=False)
    assert any(m in text for m in ("مهر", "شهریور", "آبان"))


def test_work_week_saturday_to_thursday():
    g = date(2025, 9, 24)  # a Wednesday
    ww = work_week_for(g)
    assert ww.start.weekday() == 5  # Saturday
    assert (ww.end - ww.start).days == 5
    assert ww.week_number >= 1


def test_previous_work_week():
    ww = work_week_for(date(2025, 9, 24))
    prev = previous_work_week(ww)
    assert prev.end < ww.start
    assert prev.week_number == ww.week_number - 1 or prev.jalali_year < ww.jalali_year


def test_jalali_month():
    m = jalali_month_for(date(2025, 9, 27))
    assert m.month >= 1
    assert m.start <= date(2025, 9, 27) <= m.end


def test_choice_roundtrip():
    c = make_choice("۵ مهر ۱۴۰۴", "2025-09-27")
    assert parse_choice_key(c) == "2025-09-27"


def test_saturday_of_week():
    # 2025-09-27 is Saturday in Gregorian
    s = saturday_of_week(date(2025, 9, 27))
    assert s.weekday() == 5
