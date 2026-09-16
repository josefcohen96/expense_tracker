"""Hebrew labels for dates relative to today, shared by the mobile screens."""
from __future__ import annotations

from datetime import date
from typing import Optional

HEBREW_MONTHS = (
    "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
    "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר",
)
HEBREW_MONTHS_SHORT = (
    "ינו׳", "פבר׳", "מרץ", "אפר׳", "מאי", "יוני",
    "יולי", "אוג׳", "ספט׳", "אוק׳", "נוב׳", "דצמ׳",
)
# date.weekday(): Monday == 0
HEBREW_WEEKDAYS = ("שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון")


def parse_iso(value: object) -> Optional[date]:
    """Parse a stored YYYY-MM-DD (or datetime prefix) value; None when unusable."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def weekday_name(d: date) -> str:
    return HEBREW_WEEKDAYS[d.weekday()]


def long_date(d: date) -> str:
    """'4 באוקטובר'"""
    return f"{d.day} ב{HEBREW_MONTHS[d.month - 1]}"


def short_month_date(d: date) -> str:
    """'16 בספט׳'"""
    return f"{d.day} ב{HEBREW_MONTHS_SHORT[d.month - 1]}"


def dotted_date(d: date, with_year: bool = False) -> str:
    """'20.9' or '12.12.2026'"""
    return f"{d.day}.{d.month}.{d.year}" if with_year else f"{d.day}.{d.month}"


def overdue_label(days_late: int) -> str:
    """How late something is: 'באיחור ביומיים'."""
    if days_late <= 1:
        return "באיחור ביום"
    if days_late == 2:
        return "באיחור ביומיים"
    if days_late < 7:
        return f"באיחור ב-{days_late} ימים"
    if days_late < 14:
        return "באיחור בשבוע"
    if days_late < 21:
        return "באיחור בשבועיים"
    if days_late < 60:
        return f"באיחור ב-{days_late // 7} שבועות"
    return f"באיחור ב-{days_late // 30} חודשים"


def due_label(d: date, today: date) -> str:
    """When something is due, phrased relative to today."""
    delta = (d - today).days
    if delta < 0:
        return overdue_label(-delta)
    if delta == 0:
        return "היום"
    if delta == 1:
        return "עד מחר"
    if delta < 7:
        return f"יום {weekday_name(d)}"
    return long_date(d)


def in_days_label(delta: int) -> str:
    """'בעוד 4 ימים' for a future offset, the overdue phrase for a past one."""
    if delta < 0:
        return overdue_label(-delta)
    if delta == 0:
        return "היום"
    if delta == 1:
        return "מחר"
    if delta == 2:
        return "בעוד יומיים"
    return f"בעוד {delta} ימים"


def weeks_and_days(days: int) -> str:
    """'12 שבועות ו-3 ימים'"""
    weeks, rest = divmod(max(days, 0), 7)
    if weeks == 0:
        return "יום אחד" if rest == 1 else f"{rest} ימים"
    week_part = "שבוע" if weeks == 1 else ("שבועיים" if weeks == 2 else f"{weeks} שבועות")
    if rest == 0:
        return week_part
    day_part = "יום" if rest == 1 else f"{rest} ימים"
    return f"{week_part} ו-{day_part}"


def relative_day(d: date, today: date) -> str:
    """Short 'when' for a past record: היום / אתמול / 3.9."""
    delta = (today - d).days
    if delta == 0:
        return "היום"
    if delta == 1:
        return "אתמול"
    return dotted_date(d)


def offset_label(offset_days: int, short: bool = False) -> str:
    """Offset from the wedding: '-6 חודשים', '-12 שבועות' (short: '-6 ח׳')."""
    if offset_days == 0:
        return "יום החתונה"
    sign = "-" if offset_days < 0 else "+"
    n = abs(offset_days)
    if n >= 30 and n % 30 == 0:
        count, unit, one, many = n // 30, "ח׳", "חודש", "חודשים"
    elif n % 7 == 0:
        count, unit, one, many = n // 7, "ש׳", "שבוע", "שבועות"
    else:
        count, unit, one, many = n, "י׳", "יום", "ימים"
    if short:
        return f"{sign}{count} {unit}"
    return f"{sign}{count} {one if count == 1 else many}"
