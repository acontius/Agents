"""Jalali (Persian/Shamsi) calendar utilities.

PostgreSQL stores Gregorian dates. All user-facing dates use Jalali.
Week boundaries follow the Iranian work week: Saturday to Thursday.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

JALALI_MONTHS = (
    "",
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
)

WEEKDAY_NAMES_EN = (
    "Saturday",
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
)

_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def to_persian_digits(text: str) -> str:
    return str(text).translate(_PERSIAN_DIGITS)


def gregorian_to_jalali(g: date) -> tuple[int, int, int]:
    gy, gm, gd = g.year, g.month, g.day
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        - 80
        + gd
        + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> date:
    if jy > 979:
        gy = 1600
        jy -= 979
    else:
        gy = 621
    days = 365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + 78 + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += (jm - 7) * 30 + 186
    gy += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    sal_a = [
        0,
        31,
        29 if (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0) else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]
    gm = 1
    while gm <= 12 and gd > sal_a[gm]:
        gd -= sal_a[gm]
        gm += 1
    return date(gy, gm, gd)


def format_jalali(g: date, *, persian_digits: bool = True) -> str:
    jy, jm, jd = gregorian_to_jalali(g)
    text = f"{jd} {JALALI_MONTHS[jm]} {jy}"
    return to_persian_digits(text) if persian_digits else text


def format_jalali_month(g: date, *, persian_digits: bool = True) -> str:
    jy, jm, _ = gregorian_to_jalali(g)
    text = f"{JALALI_MONTHS[jm]} {jy}"
    return to_persian_digits(text) if persian_digits else text


def format_time_display(t, *, persian_digits: bool = True) -> str:
    if t is None:
        return "—"
    if hasattr(t, "strftime"):
        text = t.strftime("%H:%M")
    else:
        text = str(t)[:5]
    return to_persian_digits(text) if persian_digits else text


def saturday_of_week(g: date) -> date:
    return g - timedelta(days=(g.weekday() + 2) % 7)


def thursday_of_week(g: date) -> date:
    return saturday_of_week(g) + timedelta(days=5)


@dataclass(frozen=True)
class WorkWeek:
    week_number: int
    start: date
    end: date
    jalali_year: int

    def label(self, *, persian_digits: bool = True) -> str:
        rng = (
            f"{format_jalali(self.start, persian_digits=False)}"
            f" تا {format_jalali(self.end, persian_digits=False)}"
        )
        text = f"Week {self.week_number} — {rng}"
        return to_persian_digits(text) if persian_digits else text

    def day_dates(self) -> dict[str, date]:
        return {
            name: self.start + timedelta(days=i)
            for i, name in enumerate(WEEKDAY_NAMES_EN[:6])
        }


def jalali_week_number(g: date) -> int:
    jy, _, _ = gregorian_to_jalali(g)
    farvardin_1 = jalali_to_gregorian(jy, 1, 1)
    week1_sat = saturday_of_week(farvardin_1)
    this_sat = saturday_of_week(g)
    delta = (this_sat - week1_sat).days
    return max(1, delta // 7 + 1)


def work_week_for(g: date) -> WorkWeek:
    start = saturday_of_week(g)
    end = start + timedelta(days=5)
    jy, _, _ = gregorian_to_jalali(start)
    return WorkWeek(
        week_number=jalali_week_number(g),
        start=start,
        end=end,
        jalali_year=jy,
    )


def previous_work_week(ww: WorkWeek) -> WorkWeek:
    prev_thu = ww.start - timedelta(days=1)
    return work_week_for(prev_thu)


@dataclass(frozen=True)
class JalaliMonth:
    year: int
    month: int

    @property
    def start(self) -> date:
        return jalali_to_gregorian(self.year, self.month, 1)

    @property
    def end(self) -> date:
        if self.month == 12:
            next_start = jalali_to_gregorian(self.year + 1, 1, 1)
        else:
            next_start = jalali_to_gregorian(self.year, self.month + 1, 1)
        return next_start - timedelta(days=1)

    def label(self, *, persian_digits: bool = True) -> str:
        text = f"{JALALI_MONTHS[self.month]} {self.year}"
        return to_persian_digits(text) if persian_digits else text


def jalali_month_for(g: date) -> JalaliMonth:
    jy, jm, _ = gregorian_to_jalali(g)
    return JalaliMonth(year=jy, month=jm)


def parse_choice_key(choice: str) -> Optional[str]:
    if not choice:
        return None
    if "||" in choice:
        return choice.split("||", 1)[1].strip()
    return choice.strip()


def make_choice(display: str, key: str) -> str:
    return f"{display}||{key}"
