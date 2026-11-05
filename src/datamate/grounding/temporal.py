"""
temporal.py — Giải mã biểu thức thời gian tương đối theo Điều 2 Rulebook và lọc dữ liệu tương lai.

Quy tắc thời gian (Điều 2 Rulebook):
- Ngày mốc (as_of_date): D
- Hôm nay: D
- Hôm qua: D - 1 ngày
- Tuần này: Từ thứ Hai đầu tuần chứa D đến hết ngày D.
- Tuần trước / tuần rồi: Từ thứ Hai đến Chủ Nhật của tuần ngay trước tuần chứa D.
- Tháng này: Từ ngày 01 của tháng chứa D đến hết ngày D.
- Tháng trước: Trọn vẹn từ ngày đầu đến ngày cuối của tháng ngay trước tháng chứa D.
- Tháng M, quý Q không ghi năm: Của năm nay nếu không sau hôm nay; sau hôm nay thì của năm trước.
- Từ đầu năm, từ đầu năm tới nay: Từ 01/01 của năm nay đến hết hôm nay.
- N ngày gần nhất / N ngày qua: Khoảng [D - N + 1, D] (gồm N ngày liền nhau kết thúc tại D).
- Tết năm Y, dịp Tết: Tra cứu calendar.csv từ 23 tháng Chạp (năm Y-1) đến mùng 10 tháng Giêng (năm Y).
- So với trước Tết: Cùng số ngày ngay trước ngày 23 tháng Chạp.
- Lọc tương lai: Mọi bản ghi có ngày phát sinh > D được lọc bỏ.
"""

from __future__ import annotations

import calendar as pycalendar
from datetime import date, datetime, timedelta
import re
import unicodedata
from typing import Optional

try:
    import pandas as pd
except ImportError:
    pd = None

from datamate.grounding.lunar_calendar import LunarCalendar, get_calendar
from datamate.types import TimeWindow


def _normalize_text(text: str) -> str:
    """Chuẩn hóa tiếng Việt (NFC, chữ thường, gộp khoảng trắng)."""
    text = unicodedata.normalize("NFC", str(text)).lower()
    return re.sub(r"\s+", " ", text).strip()


def parse_date(date_str: str) -> date:
    """Chuyển đổi chuỗi ngày YYYY-MM-DD sang date object."""
    date_str = str(date_str).strip()[:10]
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def get_month_end(year: int, month: int) -> date:
    """Lấy ngày cuối cùng của một tháng."""
    last_day = pycalendar.monthrange(year, month)[1]
    return date(year, month, last_day)


def resolve_temporal(
    question: str,
    as_of_date: str,
    calendar: Optional[LunarCalendar] = None,
) -> list[TimeWindow]:
    """
    Phân tích câu hỏi tiếng Việt kết hợp ngày mốc as_of_date và calendar.csv
    để trích xuất các cửa sổ thời gian (TimeWindow) theo Điều 2 Rulebook.
    """
    d = parse_date(as_of_date)
    q = _normalize_text(question)
    windows: list[TimeWindow] = []

    if calendar is None:
        calendar = get_calendar()

    # 1. Hôm nay / ngày mốc
    if re.search(r"\bh[oô]m nay\b|\bng[aà]y m[oố]c\b", q):
        windows.append(TimeWindow(
            start_date=d.isoformat(),
            end_date=d.isoformat(),
            label="today",
            description=f"Hôm nay ({d.isoformat()})",
        ))

    # 2. Hôm qua
    if re.search(r"\bh[oô]m qua\b", q):
        yesterday = d - timedelta(days=1)
        windows.append(TimeWindow(
            start_date=yesterday.isoformat(),
            end_date=yesterday.isoformat(),
            label="yesterday",
            description=f"Hôm qua ({yesterday.isoformat()})",
        ))

    # 3. Tuần này (Thứ Hai đầu tuần chứa D đến hết D)
    if re.search(r"\btu[aầ]n n[aà]y\b|\btrong tu[aầ]n n[aà]y\b", q):
        # Python weekday(): Thứ Hai là 0, Chủ Nhật là 6
        monday = d - timedelta(days=d.weekday())
        windows.append(TimeWindow(
            start_date=monday.isoformat(),
            end_date=d.isoformat(),
            label="this_week",
            description=f"Tuần này (từ {monday.isoformat()} đến {d.isoformat()})",
        ))

    # 4. Tuần trước / tuần rồi (Thứ Hai đến Chủ Nhật của tuần ngay trước)
    if re.search(r"\btu[aầ]n tr[uư][oớ]c\b|\btu[aầ]n r[oồ]i\b", q):
        last_week_monday = d - timedelta(days=d.weekday() + 7)
        last_week_sunday = last_week_monday + timedelta(days=6)
        windows.append(TimeWindow(
            start_date=last_week_monday.isoformat(),
            end_date=last_week_sunday.isoformat(),
            label="last_week",
            description=f"Tuần trước (từ {last_week_monday.isoformat()} đến {last_week_sunday.isoformat()})",
        ))

    # 5. Tháng này (Từ 01 của tháng chứa D đến hết D)
    has_this_month = bool(re.search(r"\bth[aá]ng n[aà]y\b|\btrong th[aá]ng n[aà]y\b", q))
    if has_this_month:
        month_start = d.replace(day=1)
        windows.append(TimeWindow(
            start_date=month_start.isoformat(),
            end_date=d.isoformat(),
            label="this_month",
            description=f"Tháng này (từ {month_start.isoformat()} đến {d.isoformat()})",
        ))

    # 6. Tháng trước / tháng rồi
    if re.search(r"\bth[aá]ng tr[uư][oớ]c\b|\bth[aá]ng r[oồ]i\b", q):
        if d.month == 1:
            lm_year = d.year - 1
            lm_month = 12
        else:
            lm_year = d.year
            lm_month = d.month - 1
        lm_start = date(lm_year, lm_month, 1)
        lm_end_full = get_month_end(lm_year, lm_month)

        # Rulebook Điều 2: "Tháng này: từ ngày 1 đến hết hôm nay.
        # So với tháng trước thì lấy cùng số ngày của tháng trước: từ ngày 1 đến hết ngày trùng số
        # với hôm nay; tháng trước không có ngày đó thì đến hết tháng trước"
        is_comparison = bool(
            has_this_month
            or re.search(r"so\s*(v[oớ]i|s[aá]nh)?\s*th[aá]ng\s*(tr[uư][oớ]c|r[oồ]i)", q)
            or re.search(r"(t[aă]ng|gi[aả]m|ch[eê]nh\s*l[eệ]ch|thay\s*đ[oổ]i)\b.*th[aá]ng\s*(tr[uư][oớ]c|r[oồ]i)", q)
        )

        if is_comparison:
            cmp_day = min(d.day, lm_end_full.day)
            lm_end_cmp = date(lm_year, lm_month, cmp_day)
            windows.append(TimeWindow(
                start_date=lm_start.isoformat(),
                end_date=lm_end_cmp.isoformat(),
                label="last_month_compared",
                description=f"Tháng trước kỳ so sánh (từ {lm_start.isoformat()} đến {lm_end_cmp.isoformat()})",
            ))
        else:
            windows.append(TimeWindow(
                start_date=lm_start.isoformat(),
                end_date=lm_end_full.isoformat(),
                label="last_month",
                description=f"Tháng trước (tháng {lm_month}/{lm_year})",
            ))

    # 7. Từ đầu năm / từ đầu năm tới nay / từ đầu năm đến nay
    if re.search(r"t[uừ]\s*đ[aầ]u\s*n[aă]m(\s*(t[oớ]i|đ[eế]n)\s*nay)?", q):
        year_start = date(d.year, 1, 1)
        windows.append(TimeWindow(
            start_date=year_start.isoformat(),
            end_date=d.isoformat(),
            label="year_to_date",
            description=f"Từ đầu năm đến hôm nay ({year_start.isoformat()} - {d.isoformat()})",
        ))

    # 8. N ngày gần nhất / N ngày qua / N ngày vừa qua / N ngày gần đây
    m_ndays = re.search(r"(\d+)\s*ng[aà]y\s*(g[aầ]n\s*nh[aấ]t|qua|v[uừ]a\s*qua|g[aầ]n\s*đ[aâ]y)", q)
    if m_ndays:
        n = int(m_ndays.group(1))
        start_ndays = d - timedelta(days=n - 1)
        windows.append(TimeWindow(
            start_date=start_ndays.isoformat(),
            end_date=d.isoformat(),
            label=f"{n}_days_recent",
            description=f"{n} ngày gần nhất (từ {start_ndays.isoformat()} đến {d.isoformat()})",
        ))

    # 9. Tháng M (có hoặc không ghi năm)
    # Ví dụ: "tháng 3", "tháng 12/2024", "tháng 10 năm 2025"
    m_month = re.search(r"\bth[aá]ng\s*(\d{1,2})(?:\s*(?:/|n[aă]m)\s*(\d{4}))?\b", q)
    if m_month and not re.search(r"\bth[aá]ng\s*(n[aà]y|tr[uư][oớ]c|r[oồ]i)\b", m_month.group(0)) and not re.search(r"n[uử]a\s*(đ[aầ]u|cu[oố]i)|10\s*ng[aà]y\s*(đ[aầ]u|gi[uữ]a|cu[oố]i)|\b(r[aăằ]m|ram|m[uù]ng\s*1)\b", q):
        m_val = int(m_month.group(1))
        if 1 <= m_val <= 12:
            if m_month.group(2):
                y_val = int(m_month.group(2))
            else:
                # Quy tắc: của năm nay nếu không sau hôm nay; sau hôm nay thì của năm trước
                # So sánh ngày 01 của tháng M năm nay với d
                if date(d.year, m_val, 1) <= d:
                    y_val = d.year
                else:
                    y_val = d.year - 1

            m_start = date(y_val, m_val, 1)
            m_end = get_month_end(y_val, m_val)
            windows.append(TimeWindow(
                start_date=m_start.isoformat(),
                end_date=m_end.isoformat(),
                label=f"month_{y_val}_{m_val:02d}",
                description=f"Tháng {m_val}/{y_val}",
            ))

    # 9.1. Nửa đầu tháng / Nửa cuối tháng
    m_half = re.search(r"n[uử]a\s*(đ[aầ]u|cu[oố]i)\s*th[aá]ng(?:\s*(\d{1,2})(?:\s*(?:/|n[aă]m)\s*(\d{4}))?|\s*n[aà]y)?", q)
    if m_half:
        which_half = "first" if "đầu" in m_half.group(1).lower() or "dau" in _normalize_text(m_half.group(1)) else "second"
        if m_half.group(2):
            hm_month = int(m_half.group(2))
            hm_year = int(m_half.group(3)) if m_half.group(3) else (d.year if date(d.year, hm_month, 1) <= d else d.year - 1)
        else:
            hm_month = d.month
            hm_year = d.year

        hm_end_full = get_month_end(hm_year, hm_month)
        if which_half == "first":
            h_start = date(hm_year, hm_month, 1)
            h_end = date(hm_year, hm_month, 15)
            h_desc = f"Nửa đầu tháng {hm_month}/{hm_year} (từ 01 đến 15)"
        else:
            h_start = date(hm_year, hm_month, 16)
            h_end = hm_end_full
            if hm_year == d.year and hm_month == d.month and d < hm_end_full:
                h_end = max(h_start, d)
            h_desc = f"Nửa cuối tháng {hm_month}/{hm_year} (từ 16 đến {h_end.day:02d})"

        windows.append(TimeWindow(
            start_date=h_start.isoformat(),
            end_date=h_end.isoformat(),
            label=f"half_{which_half}_{hm_year}_{hm_month:02d}",
            description=h_desc,
        ))

    # 9.2. 10 ngày đầu tháng / giữa tháng / cuối tháng
    m_tendays = re.search(r"10\s*ng[aà]y\s*(đ[aầ]u|gi[uữ]a|cu[oố]i)\s*th[aá]ng(?:\s*(\d{1,2})(?:\s*(?:/|n[aă]m)\s*(\d{4}))?|\s*n[aà]y)?", q)
    if m_tendays:
        pos = m_tendays.group(1).lower()
        which_ten = "first" if "đầu" in pos else ("middle" if "giữa" in pos else "last")
        if m_tendays.group(2):
            tm_month = int(m_tendays.group(2))
            tm_year = int(m_tendays.group(3)) if m_tendays.group(3) else (d.year if date(d.year, tm_month, 1) <= d else d.year - 1)
        else:
            tm_month = d.month
            tm_year = d.year

        tm_end_full = get_month_end(tm_year, tm_month)
        if which_ten == "first":
            t_start = date(tm_year, tm_month, 1)
            t_end = date(tm_year, tm_month, 10)
            t_desc = f"10 ngày đầu tháng {tm_month}/{tm_year} (01 đến 10)"
        elif which_ten == "middle":
            t_start = date(tm_year, tm_month, 11)
            t_end = date(tm_year, tm_month, 20)
            t_desc = f"10 ngày giữa tháng {tm_month}/{tm_year} (11 đến 20)"
        else:
            t_start = date(tm_year, tm_month, 21)
            t_end = tm_end_full
            t_desc = f"10 ngày cuối tháng {tm_month}/{tm_year} (21 đến {tm_end_full.day:02d})"

        windows.append(TimeWindow(
            start_date=t_start.isoformat(),
            end_date=t_end.isoformat(),
            label=f"tendays_{which_ten}_{tm_year}_{tm_month:02d}",
            description=t_desc,
        ))

    # 9.3. Rằm (15 âm lịch) và Mùng 1 âm lịch
    m_lunar_day = re.search(r"\b(r[aăằ]m|ram|r[aà]m|m[uù]ng\s*1)\b(?:\s*(?:th[aá]ng|thg)?\s*(\d{1,2}|gi[eê]ng|ch[aạ]p|b[aả]y|t[aá]m|ch[ií]n|m[uư][oờ]i))?", q)
    if m_lunar_day and calendar is not None:
        target_ld = 15 if any(k in _normalize_text(m_lunar_day.group(1)) for k in ["răm", "rằm", "ram", "ràm"]) else 1
        l_month_raw = m_lunar_day.group(2)
        if l_month_raw:
            lm_raw_norm = _normalize_text(l_month_raw)
            month_map = {"gieng": 1, "chap": 12, "bay": 7, "tam": 8, "chin": 9, "muoi": 10}
            if lm_raw_norm.isdigit():
                target_lm = int(lm_raw_norm)
            else:
                target_lm = month_map.get(lm_raw_norm, 1)
        else:
            target_lm = d.month

        solar_date_found = None
        for test_year in (d.year, d.year - 1, d.year + 1):
            s_d = calendar.get_solar_date(test_year, target_lm, target_ld)
            if s_d:
                if parse_date(s_d) <= d:
                    solar_date_found = s_d
                    break
                elif solar_date_found is None:
                    solar_date_found = s_d

        if solar_date_found:
            day_label = "Rằm (15 âm)" if target_ld == 15 else "Mùng 1 âm"
            windows.append(TimeWindow(
                start_date=solar_date_found,
                end_date=solar_date_found,
                label=f"lunar_{target_ld}_{target_lm}",
                description=f"{day_label} tháng {target_lm} âm lịch (ngày dương {solar_date_found})",
            ))

    # 10. Quý Q (có hoặc không ghi năm)
    # Ví dụ: "quý 1", "quý 2 năm 2024", "quý 3/2025"
    m_quarter = re.search(r"\bqu[yý]\s*([1-4])(?:\s*(?:/|n[aă]m)\s*(\d{4}))?\b", q)
    if m_quarter:
        q_val = int(m_quarter.group(1))
        start_month = (q_val - 1) * 3 + 1
        end_month = q_val * 3

        if m_quarter.group(2):
            q_year = int(m_quarter.group(2))
        else:
            # Quý không ghi năm: của năm nay nếu không sau hôm nay; sau hôm nay thì của năm trước
            if date(d.year, start_month, 1) <= d:
                q_year = d.year
            else:
                q_year = d.year - 1

        q_start = date(q_year, start_month, 1)
        q_end = get_month_end(q_year, end_month)
        windows.append(TimeWindow(
            start_date=q_start.isoformat(),
            end_date=q_end.isoformat(),
            label=f"quarter_{q_year}_Q{q_val}",
            description=f"Quý {q_val}/{q_year}",
        ))

    # 11. Tết năm Y / dịp Tết / mùa Tết / trước Tết
    m_tet = re.search(r"(so\s*v[oớ]i\s*)?(tr[uư][oớ]c\s*)?(d[iị]p\s*|m[uù]a\s*)?t[eế]t(\s*n[aă]m\s*(\d{4}))?", q)
    if m_tet and calendar is not None:
        if m_tet.group(5):
            tet_year = int(m_tet.group(5))
        else:
            # Nếu không ghi năm: lấy Tết của năm d hoặc năm gần nhất
            tet_year = d.year

        is_pre_tet = bool(m_tet.group(2) or m_tet.group(1))

        try:
            if is_pre_tet:
                pre_start, pre_end = calendar.get_pre_tet_window(tet_year)
                windows.append(TimeWindow(
                    start_date=pre_start,
                    end_date=pre_end,
                    label=f"pre_tet_{tet_year}",
                    description=f"Giai đoạn trước Tết năm {tet_year} ({pre_start} đến {pre_end})",
                ))
            else:
                tet_start, tet_end = calendar.get_tet_window(tet_year)
                windows.append(TimeWindow(
                    start_date=tet_start,
                    end_date=tet_end,
                    label=f"tet_{tet_year}",
                    description=f"Tết năm {tet_year} (từ 23 Chạp đến mùng 10 Giêng: {tet_start} đến {tet_end})",
                ))
        except Exception:
            pass

    return windows


def find_status_col(columns: list[str]) -> Optional[str]:
    """Tìm cột trạng thái đơn trong danh sách cột."""
    for col in columns:
        norm = _normalize_text(col)
        if re.search(r"tr[aạ]ng\s*th[aá]i|t[iì]nh\s*tr[aạ]ng|status", norm):
            return col
    return None


def filter_future_data(
    df: pd.DataFrame,
    date_col: str,
    as_of_date: str,
    status_col: Optional[str] = None,
    preserve_returns: bool = True,
) -> pd.DataFrame:
    """
    Lọc bỏ các bản ghi có ngày phát sinh > as_of_date theo Điều 2 Rulebook:
    'Mọi bản ghi có ngày phát sinh > D được lọc bỏ (coi như chưa xảy ra),
    ngoại trừ trạng thái huỷ/trả của đơn (lấy theo trạng thái ghi trên đơn,
    kể cả khi phiếu trả ghi ngày sau hôm nay).'
    
    Tham số:
    - preserve_returns: Nếu True, giữ lại các bản ghi ghi nhận huỷ / trả hàng
      dù ngày phát sinh > as_of_date để các phép tính doanh thu và công nợ
      không tính nhầm đơn đã huỷ/trả thành đơn thành công.
    """
    if df.empty or date_col not in df.columns:
        return df.copy()

    d_cutoff = str(as_of_date).strip()[:10]

    # Chuẩn hóa cột ngày sang chuỗi ISO YYYY-MM-DD
    dates = df[date_col].astype(str).str.strip().str[:10]
    valid_dates = pd.to_datetime(dates, format="%Y-%m-%d", errors="coerce")
    cutoff_dt = pd.to_datetime(d_cutoff, format="%Y-%m-%d")

    # Mặc định: giữ các dòng có date <= cutoff hoặc không xác định được date
    mask = valid_dates.isna() | (valid_dates <= cutoff_dt)

    # Ngoại lệ Rulebook: bảo toàn các dòng ghi nhận đơn huỷ / trả hàng
    if preserve_returns:
        if status_col is None or status_col not in df.columns:
            status_col = find_status_col(list(df.columns))

        if status_col is not None and status_col in df.columns:
            status_norm = df[status_col].astype(str).str.lower()
            is_return_or_cancel = status_norm.str.contains(
                r"hu[yỷ]|tr[aả]\s*h[aà]ng|cancel|return",
                regex=True,
                na=False,
            )
            mask = mask | is_return_or_cancel

    return df[mask].copy().reset_index(drop=True)
