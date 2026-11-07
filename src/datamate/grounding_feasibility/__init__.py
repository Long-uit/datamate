"""
datamate.grounding — Module giải mã ngữ nghĩa thời gian và quy tắc nghiệp vụ.
"""

try:
    from .entity_linker import (
        extract_candidates_from_business,
        link_entities,
        normalize_entity_text,
    )
except Exception:
    extract_candidates_from_business = None
    link_entities = None
    normalize_entity_text = None
from .temporal import (
    LunarCalendar,
    get_calendar,
    filter_future_data,
    resolve_temporal,
    resolve_temporal_context,
    extract_query_date_range,
    extract_comparison_date_range,
    TET_SOLAR_RANGES,
    get_tet_dates_from_calendar,
)

__all__ = [
    "LunarCalendar",
    "get_calendar",
    "resolve_temporal",
    "resolve_temporal_context",
    "extract_query_date_range",
    "extract_comparison_date_range",
    "TET_SOLAR_RANGES",
    "get_tet_dates_from_calendar",
    "filter_future_data",
    "link_entities",
    "extract_candidates_from_business",
    "normalize_entity_text",
]
