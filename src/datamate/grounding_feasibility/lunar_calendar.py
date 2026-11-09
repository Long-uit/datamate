"""
lunar_calendar.py — Re-export từ temporal.py để đảm bảo tính tương thích ngược (Backward Compatibility).

Tất cả logic tra cứu lịch âm, mốc Tết và calendar.csv đã được hợp nhất
vào Single Source of Truth duy nhất: `datamate.grounding_feasibility.temporal`.
"""

from __future__ import annotations

from .temporal import (
    LunarCalendar,
    get_calendar,
    find_calendar_file,
    _CALENDAR_CACHE,
)

__all__ = [
    "LunarCalendar",
    "get_calendar",
    "find_calendar_file",
    "_CALENDAR_CACHE",
]
