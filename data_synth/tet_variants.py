"""
tet_variants.py — Sinh biến thể câu hỏi và kịch bản tính toán mùa vụ Tết âm lịch.

Áp dụng Điều 2 Rulebook và bộ tra cứu `LunarCalendar`:
- Tết năm Y: Từ 23 tháng Chạp (năm âm Y-1) đến hết mùng 10 tháng Giêng (năm âm Y).
- So với trước Tết: Cùng số ngày ngay trước ngày 23 tháng Chạp.
"""

from __future__ import annotations

from typing import Any, Optional

from datamate.grounding.lunar_calendar import LunarCalendar, get_calendar


def generate_tet_questions(
    business_id: str,
    as_of_date: str,
    year: int = 2024,
    calendar: Optional[LunarCalendar] = None,
) -> list[dict[str, Any]]:
    """Sinh các câu hỏi và khung code mẫu liên quan đến dịp Tết và trước Tết."""
    if calendar is None:
        calendar = get_calendar()

    results: list[dict[str, Any]] = []

    try:
        if calendar is not None:
            t_start, t_end = calendar.get_tet_window(year)
            pre_start, pre_end = calendar.get_pre_tet_window(year)
        else:
            t_start, t_end = f"{year}-02-02", f"{year}-02-19"
            pre_start, pre_end = f"{year}-01-15", f"{year}-02-01"
    except Exception:
        t_start, t_end = f"{year}-02-02", f"{year}-02-19"
        pre_start, pre_end = f"{year}-01-15", f"{year}-02-01"

    # Mẫu 1: Doanh thu dịp Tết
    q1 = f"Doanh thu của cửa hàng trong dịp Tết năm {year} là bao nhiêu?"
    code1 = f"""
# Tết năm {year}: {t_start} đến {t_end}
def solution(dfs):
    df_orders = None
    for name, df in dfs.items():
        if any('mã đơn' in c.lower() for c in df.columns):
            df_orders = df
            break
    if df_orders is None:
        return 0
    # Lọc ngày và bỏ đơn hủy/trả
    mask = (df_orders['Ngày'] >= '{t_start}') & (df_orders['Ngày'] <= '{t_end}')
    if 'Trạng thái' in df_orders.columns:
        mask &= ~df_orders['Trạng thái'].str.lower().isin(['huỷ', 'hủy', 'trả hàng'])
    return int(df_orders[mask]['Tổng tiền'].sum())
FINAL_RESULT = solution(dfs)
"""
    results.append({
        "business_id": business_id,
        "as_of_date": as_of_date,
        "question": q1,
        "window": {"start": t_start, "end": t_end, "label": f"tet_{year}"},
        "synthetic_code": code1.strip(),
        "type": "number",
    })

    # Mẫu 2: So với trước Tết
    q2 = f"Số lượng đơn hàng bán trong dịp Tết năm {year} so với trước Tết tăng hay giảm bao nhiêu đơn?"
    results.append({
        "business_id": business_id,
        "as_of_date": as_of_date,
        "question": q2,
        "window_tet": {"start": t_start, "end": t_end},
        "window_pre_tet": {"start": pre_start, "end": pre_end},
        "type": "number",
    })

    return results

