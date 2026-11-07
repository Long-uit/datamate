"""
Module: prompt_builder.py
Mục đích: Xây dựng Prompt cho mô hình Qwen2.5-Coder sinh mã Python/Pandas để phân tích dữ liệu.
Các cải tiến kỹ thuật chính:
1. Phân loại ý định câu hỏi (Intent Classification) để chọn ví dụ mẫu (Few-shot) phù hợp,
   giúp prompt ngắn gọn, giảm độ trễ và tránh gây nhiễu cho mô hình.
2. Giải mã thời gian tự động (Temporal Grounding) dựa trên câu hỏi, as_of_date và lịch âm,
   chuyển các mốc như Tết, N ngày gần nhất, tháng này thành ngày dương lịch cụ thể.
3. Hướng dẫn kiểm tra và chọn bảng theo cấu trúc cột thực tế (cột ngày, cột tiền, cột trạng thái)
   thay vì tìm kiếm cứng nhắc theo tên bảng.
4. Đảm bảo quy tắc nghiệp vụ theo Rulebook: loại đơn hủy/trả hàng, làm sạch số tiền,
   loại bỏ khách lẻ, quy tắc đồng hạng (Điều 9) và giới hạn dữ liệu không vượt quá as_of_date.
Tác giả: Long (AI Architect & Model Lead)
"""

import os
import sys
import re
from datamate.llm.few_shot_retriever import retrieve_dynamic_few_shot
import calendar
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

try:
    from datamate.grounding.rulebook import load_rulebook
except ImportError:
    def load_rulebook(split_dir: Optional[str] = None) -> str:
        if split_dir:
            p = Path(split_dir) / "rulebook.md"
            if p.exists():
                return p.read_text(encoding="utf-8")
        return ""

try:
    from datamate.grounding.temporal import resolve_temporal, parse_date
    from datamate.grounding.lunar_calendar import get_calendar
except ImportError:
    resolve_temporal = None
    get_calendar = None

try:
    from datamate.grounding.entity_linker import (
        link_entities,
        expand_abbreviations,
        Candidate,
        EntityMatch,
    )
except ImportError:
    link_entities = None
    expand_abbreviations = None
    Candidate = None
    EntityMatch = None

# Cấu hình encoding chuẩn trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# (load_rulebook đã được chuyển sang datamate.grounding.rulebook)


# ==============================================================================
# 1. BỘ GIẢI MÃ THỜI GIAN (TEMPORAL GROUNDING)
# ==============================================================================

# Bảng đối chiếu mốc ngày dương lịch của các dịp Tết âm lịch theo Rulebook
# (từ ngày 23 tháng Chạp năm trước đến hết mùng 10 tháng Giêng năm đó)
TET_SOLAR_RANGES: Dict[int, Tuple[str, str]] = {
    2024: ("2024-02-02", "2024-02-19"),
    2025: ("2025-01-22", "2025-02-07"),
    2026: ("2026-02-10", "2026-02-26"),
    2027: ("2027-01-30", "2027-02-16"),
}


def get_tet_dates_from_calendar(year: int, calendar_path: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """Tra cứu mốc ngày dương lịch của Tết năm Y từ tệp calendar.csv động."""
    candidates = []
    if calendar_path:
        candidates.append(Path(calendar_path))
    candidates.extend([
        Path("competition_data/train/calendar.csv"),
        Path("competition_data/public_test/calendar.csv"),
        Path("/data/calendar.csv"),
    ])
    for cp in candidates:
        if cp.exists():
            try:
                import csv
                with open(cp, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    s_d, e_d = None, None
                    for row in reader:
                        ly = int(row.get("lunar_year", 0))
                        lm = int(row.get("lunar_month", 0))
                        ld = int(row.get("lunar_day", 0))
                        d = row.get("date")
                        if ly == year - 1 and lm == 12 and ld == 23:
                            s_d = d
                        if ly == year and lm == 1 and ld == 10:
                            e_d = d
                    if s_d and e_d:
                        return s_d, e_d
            except Exception:
                pass
    return TET_SOLAR_RANGES.get(year)


def resolve_temporal_context(
    question: str,
    as_of_date_str: str,
    calendar_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Phân tích câu hỏi và as_of_date để xác định khoảng thời gian cụ thể (ngày dương ISO).
    Tích hợp trực tiếp module grounding.temporal và lunar_calendar của Phát,
    hỗ trợ kỳ chính, kỳ đối chiếu (so sánh tháng trước/trước Tết), nửa đầu/cuối tháng,
    10 ngày đầu/giữa/cuối tháng và rằm/mùng 1 âm lịch.
    """
    q_lower = question.lower()
    
    # 1. Gọi module grounding.temporal nếu có
    if resolve_temporal is not None:
        try:
            cal = get_calendar(calendar_path) if get_calendar is not None else None
            wins = resolve_temporal(question, as_of_date=as_of_date_str, calendar=cal)
            if wins:
                comp_win = next((w for w in wins if any(k in w.label for k in ["compared", "pre_tet", "last_month_compared"])), None)
                primary_win = next((w for w in wins if w != comp_win), wins[0])

                if comp_win is not None and primary_win is not None:
                    desc = f"Kỳ chính: {primary_win.description} | Kỳ đối chiếu: {comp_win.description}"
                    code_hint = (
                        f"# Kỳ chính: (df[date_col].dt.date >= pd.to_datetime('{primary_win.start_date}').date()) & (df[date_col].dt.date <= pd.to_datetime('{primary_win.end_date}').date())\n"
                        f"# Kỳ so sánh: (df[date_col].dt.date >= pd.to_datetime('{comp_win.start_date}').date()) & (df[date_col].dt.date <= pd.to_datetime('{comp_win.end_date}').date())"
                    )
                    return {
                        "as_of_date": as_of_date_str,
                        "start_date": primary_win.start_date,
                        "end_date": primary_win.end_date,
                        "comparison_start": comp_win.start_date,
                        "comparison_end": comp_win.end_date,
                        "comparison_desc": comp_win.description,
                        "description": desc,
                        "code_hint": code_hint,
                    }
                elif primary_win is not None:
                    # Gợi ý pandas theo loại kỳ
                    if primary_win.start_date == primary_win.end_date:
                        code_hint = f"df[date_col].dt.date == pd.to_datetime('{primary_win.start_date}').date()"
                    else:
                        code_hint = f"(df[date_col].dt.date >= pd.to_datetime('{primary_win.start_date}').date()) & (df[date_col].dt.date <= pd.to_datetime('{primary_win.end_date}').date())"
                    return {
                        "as_of_date": as_of_date_str,
                        "start_date": primary_win.start_date,
                        "end_date": primary_win.end_date,
                        "comparison_start": None,
                        "comparison_end": None,
                        "comparison_desc": None,
                        "description": primary_win.description,
                        "code_hint": code_hint,
                    }
        except Exception:
            pass
    
    q_lower = question.lower()
    try:
        as_of = datetime.strptime(as_of_date_str, "%Y-%m-%d").date()
    except Exception:
        return {
            "as_of_date": as_of_date_str,
            "start_date": None,
            "end_date": as_of_date_str,
            "description": f"Mốc thời gian tham chiếu (hôm nay): {as_of_date_str}",
            "code_hint": f"df = df[df[date_col] <= '{as_of_date_str}']"
        }

    # 1. Dịp Tết âm lịch
    tet_match = re.search(r"(?:dịp\s*tết|mùa\s*tết|tết)\s*(?:năm\s*)?(202[4-9]|203[0-5])", q_lower)
    if tet_match:
        year = int(tet_match.group(1))
        tet_dates = get_tet_dates_from_calendar(year, calendar_path)
        if tet_dates:
            s_d, e_d = tet_dates
            return {
                "as_of_date": as_of_date_str,
                "start_date": s_d,
                "end_date": e_d,
                "description": f"Dịp Tết {year} (lịch âm quy đổi): từ ngày '{s_d}' đến hết ngày '{e_d}'",
                "code_hint": f"(df[date_col].dt.date >= pd.to_datetime('{s_d}').date()) & (df[date_col].dt.date <= pd.to_datetime('{e_d}').date())"
            }

    # 2. N ngày gần nhất (kể cả hôm nay, ngày cuối là hôm nay)
    recent_match = re.search(r"(\d+)\s*ng[aà]y\s*gần\s*nhất", q_lower)
    if recent_match:
        n_days = int(recent_match.group(1))
        start_d = (as_of - timedelta(days=n_days - 1)).isoformat()
        end_d = as_of.isoformat()
        return {
            "as_of_date": as_of_date_str,
            "start_date": start_d,
            "end_date": end_d,
            "description": f"{n_days} ngày gần nhất kết thúc tại hôm nay: từ ngày '{start_d}' đến ngày '{end_d}'",
            "code_hint": f"(df[date_col].dt.date >= pd.to_datetime('{start_d}').date()) & (df[date_col].dt.date <= pd.to_datetime('{end_d}').date())"
        }

    # 3. Tháng M/YYYY cụ thể (ví dụ: tháng 9/2025, thang 6/2026, tháng 1 năm 2025)
    month_match = re.search(r"th(?:áng|ang|angs)\s*(\d{1,2})[\s/\-]+(?:n(?:ăm|am)\s*)?(\d{4})", q_lower)
    if month_match:
        m = int(month_match.group(1))
        y = int(month_match.group(2))
        if 1 <= m <= 12:
            last_day = calendar.monthrange(y, m)[1]
            start_d = f"{y:04d}-{m:02d}-01"
            end_d = f"{y:04d}-{m:02d}-{last_day:02d}"
            return {
                "as_of_date": as_of_date_str,
                "start_date": start_d,
                "end_date": end_d,
                "description": f"Cả tháng {m}/{y}: từ ngày '{start_d}' đến hết ngày '{end_d}'",
                "code_hint": f"(df[date_col].dt.year == {y}) & (df[date_col].dt.month == {m})"
            }

    # 4. Quý Q/YYYY cụ thể (ví dụ: quý 2/2026, quý 1 năm 2025)
    quarter_match = re.search(r"qu[yý]\s*([1-4])[\s/\-]+(?:n(?:ăm|am)\s*)?(\d{4})", q_lower)
    if quarter_match:
        q = int(quarter_match.group(1))
        y = int(quarter_match.group(2))
        m_start = (q - 1) * 3 + 1
        m_end = q * 3
        last_day = calendar.monthrange(y, m_end)[1]
        start_d = f"{y:04d}-{m_start:02d}-01"
        end_d = f"{y:04d}-{m_end:02d}-{last_day:02d}"
        return {
            "as_of_date": as_of_date_str,
            "start_date": start_d,
            "end_date": end_d,
            "description": f"Quý {q}/{y}: từ ngày '{start_d}' đến hết ngày '{end_d}'",
            "code_hint": f"(df[date_col].dt.date >= pd.to_datetime('{start_d}').date()) & (df[date_col].dt.date <= pd.to_datetime('{end_d}').date())"
        }

    # 5. "Tháng này" (theo as_of_date, từ ngày 1 đến hết hôm nay)
    if "tháng này" in q_lower or "thang nay" in q_lower:
        start_d = f"{as_of.year:04d}-{as_of.month:02d}-01"
        end_d = as_of.isoformat()
        return {
            "as_of_date": as_of_date_str,
            "start_date": start_d,
            "end_date": end_d,
            "description": f"Tháng này (từ đầu tháng đến hết hôm nay): từ ngày '{start_d}' đến ngày '{end_d}'",
            "code_hint": f"(df[date_col].dt.date >= pd.to_datetime('{start_d}').date()) & (df[date_col].dt.date <= pd.to_datetime('{end_d}').date())"
        }

    # 6. "Hôm nay" / "hnay"
    if any(k in q_lower for k in ["hôm nay", "hnay", "hom nay"]):
        return {
            "as_of_date": as_of_date_str,
            "start_date": as_of_date_str,
            "end_date": as_of_date_str,
            "description": f"Đúng ngày hôm nay: '{as_of_date_str}'",
            "code_hint": f"df[date_col].dt.date == pd.to_datetime('{as_of_date_str}').date()"
        }

    # 7. "Hôm qua"
    if "hôm qua" in q_lower or "hom qua" in q_lower:
        yesterday = (as_of - timedelta(days=1)).isoformat()
        return {
            "as_of_date": as_of_date_str,
            "start_date": yesterday,
            "end_date": yesterday,
            "description": f"Đúng ngày hôm qua: '{yesterday}'",
            "code_hint": f"df[date_col].dt.date == pd.to_datetime('{yesterday}').date()"
        }

    # 8. "Tuần này" (từ thứ 2 đầu tuần đến hết hôm nay)
    if "tuần này" in q_lower or "tuan nay" in q_lower:
        monday = (as_of - timedelta(days=as_of.weekday())).isoformat()
        return {
            "as_of_date": as_of_date_str,
            "start_date": monday,
            "end_date": as_of_date_str,
            "description": f"Tuần này (từ thứ 2 đến hôm nay): từ ngày '{monday}' đến ngày '{as_of_date_str}'",
            "code_hint": f"(df[date_col] >= '{monday}') & (df[date_col] <= '{as_of_date_str}')"
        }

    # 9. "Tuần trước" / "tuần rồi" (trọn vẹn từ thứ 2 đến Chủ nhật)
    if any(k in q_lower for k in ["tuần trước", "tuần rồi", "tuan truoc", "tuan roi"]):
        monday_prev = (as_of - timedelta(days=as_of.weekday() + 7)).isoformat()
        sunday_prev = (as_of - timedelta(days=as_of.weekday() + 1)).isoformat()
        return {
            "as_of_date": as_of_date_str,
            "start_date": monday_prev,
            "end_date": sunday_prev,
            "description": f"Tuần trước (trọn tuần T2 đến CN): từ ngày '{monday_prev}' đến ngày '{sunday_prev}'",
            "code_hint": f"(df[date_col] >= '{monday_prev}') & (df[date_col] <= '{sunday_prev}')"
        }

    # 10. Ngày cụ thể DD/MM/YYYY (ví dụ: ngày 14/07/2025)
    specific_day = re.search(r"ng[aà]y\s*(\d{1,2})/(\d{1,2})/(\d{4})", q_lower)
    if specific_day:
        d_val = f"{int(specific_day.group(3)):04d}-{int(specific_day.group(2)):02d}-{int(specific_day.group(1)):02d}"
        return {
            "as_of_date": as_of_date_str,
            "start_date": d_val,
            "end_date": d_val,
            "description": f"Đúng ngày '{d_val}'",
            "code_hint": f"df[date_col].dt.date == pd.to_datetime('{d_val}').date()"
        }

    # Mặc định: dữ liệu không vượt quá as_of_date
    return {
        "as_of_date": as_of_date_str,
        "start_date": None,
        "end_date": as_of_date_str,
        "description": f"Mốc hôm nay là '{as_of_date_str}', chỉ lấy dữ liệu phát sinh <= hôm nay",
        "code_hint": f"df = df[df[date_col] <= '{as_of_date_str}']"
    }


# ==============================================================================
# 2. PHÂN LOẠI Ý ĐỊNH CÂU HỎI (INTENT CLASSIFICATION)
# ==============================================================================

def classify_intent(question: str) -> str:
    """
    Phân loại câu hỏi thành các nhóm nghiệp vụ chính:
    - unanswerable_suspect: câu hỏi hỏi thông tin ngoài phạm vi ghi chép
    - multitable_join: tra cứu sản phẩm, hoạt chất, quy đổi giữa các bảng
    - rate_percentage: tính phần trăm, tỉ lệ
    - time_series: so sánh theo chuỗi thời gian, tăng liên tục
    - ranking_topk: tìm phần tử nhiều nhất, ít nhất, xếp hạng Top K
    - aggregation: tính tổng doanh thu, số tiền, đếm số đơn (mặc định)
    """
    q_lower = question.lower()

    # 1. Nhóm câu hỏi nghi ngờ unanswerable (hỏi thông tin không thuộc hồ sơ dữ liệu bán hàng)
    unanswerable_keywords = ["tay nghề", "kinh nghiệm", "sở thích", "thời tiết", "chuyên môn", "bằng cấp"]
    if any(k in q_lower for k in unanswerable_keywords):
        return "unanswerable_suspect"

    # 2. Nhóm tồn kho và quy đổi đơn vị (hộp chẵn, viên lẻ, divmod)
    inv_keywords = [
        "tồn kho", "còn tồn", "tồn cuối", "hộp chẵn", "viên lẻ", "bao nhiêu hộp",
        "hộp và viên", "thùng và chai", "bao và kg", "thẻ kho"
    ]
    if any(k in q_lower for k in inv_keywords):
        return "inventory_unit_conversion"

    # 3. Nhóm đa bảng / tra cứu hoạt chất, thuốc kê đơn, quy đổi đơn vị (ưu tiên cao vì cần kỹ thuật JOIN)
    join_keywords = ["hoạt chất", "kê đơn", "quy đổi", "đơn vị lớn", "hoatchat"]
    if any(k in q_lower for k in join_keywords):
        return "multitable_join"

    # 3. Nhóm tỉ lệ / phần trăm (loại trừ nồng độ thuốc có chữ số đứng ngay trước dấu %, vd 'Otrivin 0,1%')
    if re.search(
        r"(?<!\d)%|ph[ầa]n\s*tr(?:[ăa]m|awm)|\bt[ỉỷi]\s*l[ệe]\b|\bty\s*le\b|\bt[ỉỷi]\s*tr[ọo]ng\b|\bty\s*trong\b",
        q_lower,
    ):
        return "rate_percentage"

    # 4. Nhóm so sánh chuỗi thời gian
    time_keywords = ["tăng liên tục", "tăng giảm", "so với", "thay đổi bao nhiêu", "tăng trưởng"]
    if any(k in q_lower for k in time_keywords):
        return "time_series"

    # 5. Nhóm xếp hạng / Top K
    ranking_keywords = [
        "bán chạy nhất", "bán chạy", "nhiều nhất", "nhiều tiền nhất", "cao nhất",
        "thấp nhất", "lời nhất", "đắt nhất", "top", "xếp thứ", "hot nhất", "giỏi nhất"
    ]
    if any(k in q_lower for k in ranking_keywords):
        return "ranking_topk"

    # 6. Nhóm nhập hàng / phiếu nhập / chi phí mua hàng từ nhà cung cấp
    import_keywords = [
        "nhập hàng", "phiếu nhập", "tiền nhập", "nhap hang", "phieu nhap",
        "phiếu nhập hàng", "phieu nhap hang", "tiền mua hàng", "tien mua hang",
        "giá trị các phiếu nhập", "tong tien hang nhap"
    ]
    if any(k in q_lower for k in import_keywords):
        return "purchase_import"

    # 7. Mặc định là tính tổng / đếm (aggregation)
    return "aggregation"


# ==============================================================================
# 3. THƯ VIỆN VÍ DỤ TINH GỌN (DYNAMIC FEW-SHOT LIBRARY)
# ==============================================================================

FEW_SHOT_LIBRARY: Dict[str, str] = {
    "purchase_import": """--- VÍ DỤ MẪU: TÍNH TỔNG TIỀN / GIÁ TRỊ PHIẾU NHẬP HÀNG ---
Câu hỏi: "tháng này tổng giá trị các phiếu nhập hàng là bao nhiu" (as_of_date = "2026-09-07")
```python
def solution(data):
    # 1. Tìm bảng nhập hàng (ưu tiên bảng tổng hợp phiếu nhập, tránh bảng chi tiết)
    df_nhap = None
    for name, df in data.items():
        if 'nhap' in name.lower() and not any(k in name.lower() for k in ['chitiet', 'chi_tiet', 'detail', 'lohang']):
            df_nhap = df.copy()
            break
    if df_nhap is None:
        df_nhap = next((df.copy() for name, df in data.items() if 'nhap' in name.lower()), None)
    if df_nhap is None:
        return "unanswerable"

    # 2. Tìm cột ngày và cột tiền
    d_c = next((c for c in df_nhap.columns if any(k in str(c).lower() for k in ['thời gian', 'ngày', 'date', 'ngaylap'])), None)
    a_c = next((c for c in df_nhap.columns if any(k in str(c).lower() for k in ['cần trả ncc', 'tổng tiền', 'tong tien', 'thành tiền', 'giá trị']) and 'trả hàng' not in str(c).lower()), None)
    if not d_c or not a_c:
        return "unanswerable"

    # 3. Lọc đúng kỳ tháng này: năm 2026, tháng 9, từ ngày 1 đến hết as_of_date
    df_nhap['clean_date'] = clean_date(df_nhap[d_c])
    df_nhap = df_nhap[(df_nhap['clean_date'].dt.year == 2026) & (df_nhap['clean_date'].dt.month == 9) & (df_nhap['clean_date'].dt.date <= pd.to_datetime("2026-09-07").date())]

    # 4. Loại bỏ phiếu hủy nếu có trạng thái
    st_c = next((c for c in df_nhap.columns if any(k in str(c).lower() for k in ['trạng thái', 'status'])), None)
    if st_c:
        df_nhap = df_nhap[~df_nhap[st_c].astype(str).str.lower().str.contains('hủy|huỷ|cancel')]

    return int(round(clean_num(df_nhap[a_c]).sum()))
```""",

    "aggregation": """--- VÍ DỤ MẪU: TÍNH TỔNG DOANH THU / SỐ TIỀN ---
Câu hỏi: "Tổng doanh thu trong tháng này là bao nhiêu?" (as_of_date = "2026-05-25")
```python
def solution(data):
    # 1. Tìm tất cả các bảng bán hàng / doanh thu (nếu shop chia theo từng năm/tháng/chi nhánh)
    sales_dfs = []
    for name, df in data.items():
        if any(k in name.lower() for k in ['nhap', 'chiphi', 'tonkho', 'kiemke', 'ncc']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            sub = df[[d_c, a_c]].copy()
            sub.columns = ['date', 'amount']
            status_col = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'tình trạng'])), None)
            if status_col:
                sub['status'] = df[status_col]
            sales_dfs.append(sub)
    if not sales_dfs:
        return "unanswerable"

    df_sales = pd.concat(sales_dfs, ignore_index=True)

    # 2. Lọc thời gian theo .dt.date để không sót đơn có giờ
    df_sales['date'] = pd.to_datetime(df_sales['date'], dayfirst=True, errors='coerce')
    df_sales = df_sales[(df_sales['date'].dt.date >= pd.to_datetime("2026-05-01").date()) & (df_sales['date'].dt.date <= pd.to_datetime("2026-05-25").date())]

    # 3. Bỏ đơn huỷ và trả hàng
    if 'status' in df_sales.columns:
        df_sales = df_sales[~df_sales['status'].astype(str).str.lower().str.contains('hủy|huỷ|trả|cancel|return')]

    # 4. Tính tổng tiền đã làm sạch
    total = pd.to_numeric(df_sales['amount'].astype(str).str.replace(',', '').str.replace(' ', ''), errors='coerce').fillna(0).sum()
    return int(round(total))
```""",

    "rate_percentage": """--- VÍ DỤ MẪU: TÍNH TỈ LỆ PHẦN TRĂM (%) ---
Câu hỏi: "Tháng 9/2025 cửa hàng có bao nhiêu % đơn bị huỷ?" (as_of_date = "2026-05-25")
```python
def solution(data):
    # 1. Tìm bảng hóa đơn
    df_orders = None
    date_col = None
    status_col = None
    for name, df in data.items():
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap'])), None)
        s_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status'])), None)
        if d_c and s_c:
            df_orders = df.copy()
            date_col = d_c
            status_col = s_c
            break
    if df_orders is None:
        return "unanswerable"

    # 2. Lọc dữ liệu trong tháng 9/2025
    df_orders[date_col] = pd.to_datetime(df_orders[date_col], dayfirst=True, errors='coerce')
    df_period = df_orders[(df_orders[date_col].dt.year == 2025) & (df_orders[date_col].dt.month == 9)]
    total_orders = len(df_period)
    if total_orders == 0:
        return "unanswerable"

    # 3. Tỉ lệ huỷ đơn = (số đơn huỷ / tổng số đơn trong kỳ) * 100
    cancelled_count = len(df_period[df_period[status_col].astype(str).str.lower().str.contains('hủy|huỷ|cancel')])
    rate = (cancelled_count / total_orders) * 100.0
    return round(float(rate), 2)
```""",

    "ranking_topk": """--- VÍ DỤ MẪU: TÌM ĐỐI TƯỢNG NHIỀU NHẤT / BÁN CHẠY NHẤT ---
Câu hỏi: "Dịp Tết 2026, mặt hàng nào bán chạy nhất?" (as_of_date = "2026-06-28")
```python
def solution(data):
    # 1. Tìm bảng bán hàng chi tiết
    df_sales = None
    date_col = None
    prod_col = None
    qty_col = None
    for name, df in data.items():
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap'])), None)
        p_c = next((c for c in cols if any(k in str(c).lower() for k in ['tên hàng', 'mặt hàng', 'sản phẩm', 'ten_hang', 'tên thuốc'])), None)
        q_c = next((c for c in cols if any(k in str(c).lower() for k in ['số lượng quy đổi', 'slquydoi', 'số lượng', 'soluong', 'sl'])), None)
        if d_c and p_c and q_c:
            df_sales = df.copy()
            date_col = d_c
            prod_col = p_c
            qty_col = q_c
            break
    if df_sales is None:
        return "unanswerable"

    # 2. Lọc thời gian dịp Tết 2026 (từ 2026-02-10 đến 2026-02-26 theo lịch âm)
    df_sales[date_col] = pd.to_datetime(df_sales[date_col], dayfirst=True, errors='coerce')
    df_sales = df_sales[(df_sales[date_col].dt.date >= pd.to_datetime("2026-02-10").date()) & (df_sales[date_col].dt.date <= pd.to_datetime("2026-02-26").date())]

    # 3. Bỏ đơn huỷ và trả hàng
    status_col = next((c for c in df_sales.columns if any(k in str(c).lower() for k in ['trạng thái', 'status'])), None)
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains('hủy|huỷ|trả|cancel')]

    # 4. Gom nhóm và xếp hạng: số lượng giảm dần, nếu bằng nhau thì mã/tên tăng dần (Điều 9 Rulebook)
    df_sales[qty_col] = pd.to_numeric(df_sales[qty_col].astype(str).str.replace(',', '').str.replace(' ', ''), errors='coerce').fillna(0)
    grouped = df_sales.groupby(prod_col, as_index=False)[qty_col].sum()
    grouped = grouped.sort_values(by=[qty_col, prod_col], ascending=[False, True])
    if grouped.empty:
        return "unanswerable"

    return str(grouped.iloc[0][prod_col])
```""",

    "multitable_join": """--- VÍ DỤ MẪU: LIÊN KẾT ĐA BẢNG (JOIN SẢN PHẨM / HOẠT CHẤT / ĐƠN HÀNG) ---
Câu hỏi: "Thuốc có hoạt chất Natri clorid tháng này bán được bao nhiêu tiền?" (as_of_date = "2026-05-25")
```python
def solution(data):
    # 1. Tìm bảng danh mục thuốc chứa hoạt chất
    df_prod = next((df.copy() for name, df in data.items() if any('hoạt chất' in str(c).lower() for c in df.columns)), None)
    if df_prod is None: return "unanswerable"
    act_c = next((c for c in df_prod.columns if 'hoạt chất' in str(c).lower()), None)
    code_c = next((c for c in df_prod.columns if any(k in str(c).lower() for k in ['mã hàng', 'ma hang', 'mã hh', 'ma hh', 'mã thuốc', 'mã sp', 'sku'])), None)
    if not act_c or not code_c: return "unanswerable"
    matched = df_prod[df_prod[act_c].astype(str).str.lower().str.contains('natri clorid', na=False)]
    if matched.empty: return 0
    target_codes = set(matched[code_c].dropna().astype(str))

    # 2. Tìm bảng đơn hàng lọc ngày tháng 5/2026 và bỏ đơn hủy
    df_ord = next((df.copy() for name, df in data.items() if any(k in str(c).lower() for c in df.columns for k in ['thời gian', 'ngày', 'ngay ban']) and not any(k in name.lower() for k in ['nhap', 'chitiet'])), None)
    valid_orders = None
    if df_ord is not None:
        d_c = next((c for c in df_ord.columns if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian', 'ngay ban'])), None)
        if d_c:
            df_ord['clean_date'] = clean_date(df_ord[d_c])
            df_ord = df_ord[(df_ord['clean_date'].dt.year == 2026) & (df_ord['clean_date'].dt.month == 5) & (df_ord['clean_date'].dt.date <= pd.to_datetime("2026-05-25").date())]
            st_c = next((c for c in df_ord.columns if any(k in str(c).lower() for k in ['trạng thái', 'status'])), None)
            if st_c: df_ord = df_ord[~df_ord[st_c].astype(str).str.lower().str.contains('hủy|huỷ|trả')]
            oid_c = next((c for c in df_ord.columns if any(k in str(c).lower() for k in ['mã giao dịch', 'mã đơn', 'order id'])), None)
            if oid_c: valid_orders = set(df_ord[oid_c].dropna().astype(str))

    # 3. Tìm bảng chi tiết bán hàng tính tổng tiền cho target_codes (tìm cột cả có dấu và không dấu: 'thanh tien', 'ma hang')
    df_dt = next((df.copy() for name, df in data.items() if any(k in str(c).lower() for k in df.columns for k in ['thành tiền', 'thanh tien', 'tổng tiền', 'tong tien']) and not any(k in name.lower() for k in ['nhap', 'thuoc'])), None)
    if df_dt is None: return "unanswerable"
    amt_c = next((c for c in df_dt.columns if any(k in str(c).lower() for k in ['thành tiền', 'thanh tien', 'tổng tiền', 'tong tien'])), None)
    dt_code_c = next((c for c in df_dt.columns if any(k in str(c).lower() for k in ['mã hàng', 'ma hang', 'mã hh', 'ma hh', 'mã thuốc', 'mã sp'])), None)
    dt_oid_c = next((c for c in df_dt.columns if any(k in str(c).lower() for k in ['mã giao dịch', 'mã đơn', 'order id'])), None)
    if not amt_c or not dt_code_c: return "unanswerable"
    
    df_dt = df_dt[df_dt[dt_code_c].astype(str).isin(target_codes)]
    if valid_orders is not None and dt_oid_c:
        df_dt = df_dt[df_dt[dt_oid_c].astype(str).isin(valid_orders)]
    
    return int(round(clean_num(df_dt[amt_c]).sum()))
```""",

    "inventory_unit_conversion": r"""--- VÍ DỤ MẪU: TỒN KHO & QUY ĐỔI ĐƠN VỊ (HỘP CHẴN, VIÊN LẺ) ---
Câu hỏi: "Hiện tại thuốc Hapacol 650 còn tồn bao nhiêu hộp và viên lẻ?" (as_of_date = "2026-05-25")
```python
def solution(data):
    # 1. Tìm bảng tồn kho / thẻ kho hoặc bảng chi tiết nhập/bán/trả
    # Theo Điều 5 Rulebook: Tồn kho = Tổng nhập - Tổng bán + Tổng trả (hoặc cột tồn cuối kỳ)
    df_stock = None
    prod_col = None
    remain_col = None
    unit_col = None

    for name, df in data.items():
        cols = df.columns.tolist()
        p_c = next((c for c in cols if any(k in str(c).lower() for k in ['tên hàng', 'mặt hàng', 'sản phẩm', 'tên thuốc', 'ten_hang'])), None)
        r_c = next((c for c in cols if any(k in str(c).lower() for k in ['tồn cuối', 'số lượng tồn', 'tồn kho', 'soluongton', 'sl_ton'])), None)
        if p_c and r_c:
            df_stock = df.copy()
            prod_col = p_c
            remain_col = r_c
            unit_col = next((c for c in cols if any(k in str(c).lower() for k in ['quy cách', 'quycach', 'hệ số', 'don_vi_quy_doi'])), None)
            break

    # Nếu không có bảng tồn, tính từ các bảng giao dịch nhập và bán
    if df_stock is None:
        tot_qty = 0
        found = False
        for name, df in data.items():
            cols = df.columns.tolist()
            p_c = next((c for c in cols if any(k in str(c).lower() for k in ['tên hàng', 'mặt hàng', 'sản phẩm', 'tên thuốc'])), None)
            q_c = next((c for c in cols if any(k in str(c).lower() for k in ['số lượng quy đổi', 'slquydoi', 'số lượng', 'sl'])), None)
            if p_c and q_c:
                sub = df[df[p_c].astype(str).str.lower().str.contains('hapacol 650', na=False)]
                if not sub.empty:
                    found = True
                    q_vals = pd.to_numeric(sub[q_c].astype(str).str.replace(',', '').str.replace(' ', ''), errors='coerce').fillna(0).sum()
                    if 'nhap' in name.lower():
                        tot_qty += q_vals
                    else:
                        tot_qty -= q_vals
        if not found:
            return "unanswerable"
        total_units = max(0, int(tot_qty))
        packing_size = 100
        boxes, pills = divmod(total_units, packing_size)
        return [int(boxes), int(pills)]

    # 2. Lọc đúng mặt hàng được hỏi
    matched = df_stock[df_stock[prod_col].astype(str).str.lower().str.contains('hapacol 650', na=False)]
    if matched.empty:
        return "unanswerable"

    total_units = int(pd.to_numeric(matched[remain_col].astype(str).str.replace(',', '').str.replace(' ', ''), errors='coerce').fillna(0).iloc[0])
    packing_size = 100
    if unit_col and not matched[unit_col].isna().all():
        val = matched[unit_col].iloc[0]
        m = re.search(r'\d+', str(val))
        if m:
            packing_size = int(m.group(0))

    # 3. Dùng divmod để trả về [số hộp chẵn, số viên lẻ] chuẩn kiểu list
    boxes, pills = divmod(total_units, packing_size)
    return [int(boxes), int(pills)]
```""",

    "time_series": """--- VÍ DỤ MẪU: PHÂN TÍCH CHUỖI THỜI GIAN & SO SÁNH KỲ LIỀN TRƯỚC ---
Câu hỏi: "Doanh thu tháng này tăng hay giảm bao nhiêu phần trăm so với tháng trước?" (as_of_date = "2026-05-25")
```python
def solution(data):
    # 1. Tìm bảng bán hàng chi tiết
    df_sales = None
    date_col = None
    amt_col = None
    status_col = None

    for name, df in data.items():
        if any(k in name.lower() for k in ['nhap', 'chiphi', 'tonkho', 'ncc']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            date_col = d_c
            amt_col = a_c
            status_col = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status'])), None)
            break

    if df_sales is None:
        return "unanswerable"

    # 2. Chuyển đổi ngày và loại bỏ đơn huỷ / trả
    df_sales[date_col] = pd.to_datetime(df_sales[date_col], dayfirst=True, errors='coerce')
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains('hủy|huỷ|trả|cancel')]

    df_sales['clean_amount'] = pd.to_numeric(df_sales[amt_col].astype(str).str.replace(',', '').str.replace(' ', ''), errors='coerce').fillna(0)

    # 3. Lọc doanh thu kỳ chính (Tháng này: 2026-05-01 đến 2026-05-25)
    # và kỳ đối chiếu (Tháng trước cùng số ngày: 2026-04-01 đến 2026-04-25 theo Điều 2 Rulebook)
    mask_curr = (df_sales[date_col].dt.date >= pd.to_datetime("2026-05-01").date()) & (df_sales[date_col].dt.date <= pd.to_datetime("2026-05-25").date())
    mask_prev = (df_sales[date_col].dt.date >= pd.to_datetime("2026-04-01").date()) & (df_sales[date_col].dt.date <= pd.to_datetime("2026-04-25").date())

    rev_curr = df_sales[mask_curr]['clean_amount'].sum()
    rev_prev = df_sales[mask_prev]['clean_amount'].sum()

    if rev_prev == 0:
        return 0.0

    # 4. Tính tỉ lệ phần trăm thay đổi: ((Hiện tại - Trước) / Trước) * 100
    pct_change = ((rev_curr - rev_prev) / rev_prev) * 100.0
    return round(float(pct_change), 2)
```""",

    "unanswerable_suspect": """--- VÍ DỤ MẪU: CÂU HỎI THIẾU DỮ LIỆU (UNANSWERABLE) ---
Câu hỏi: "Nhân viên nào có tay nghề cao nhất tiệm?" (as_of_date = "2026-07-31")
```python
def solution(data):
    # Kiểm tra xem dữ liệu có ghi chép về thông tin câu hỏi yêu cầu không
    # Dữ liệu chỉ ghi đơn bán hàng, không có bảng hoặc cột nào về 'tay nghề'
    has_skill_col = False
    for name, df in data.items():
        if any('tay nghề' in str(c).lower() or 'trình độ' in str(c).lower() for c in df.columns):
            has_skill_col = True
            break

    if not has_skill_col:
        return "unanswerable"
    return "unanswerable"
```"""
}


def extract_relevant_rulebook_clauses(rulebook_content: str, question: str, max_chars: int = 2500) -> str:
    """
    Trích xuất thông minh các điều khoản Rulebook liên quan trực tiếp đến câu hỏi.
    Thay vì cắt cụt text cứng nhắc ở ký tự 2500 làm mất ngữ cảnh, hàm phân tách
    rulebook thành các điều/mục, chấm điểm mức độ phù hợp và chọn các điều khoản trọng tâm.
    """
    if not rulebook_content or not rulebook_content.strip():
        return ""

    rb_text = rulebook_content.strip()
    if len(rb_text) <= max_chars:
        return rb_text

    # Tách các điều khoản theo tiêu đề markdown (# hoặc ## hoặc Điều X)
    raw_sections = re.split(r"(?=(?:^|\n)(?:#{1,3}\s+|Điều\s+\d+|Mục\s+\d+))", rb_text)
    sections = [s.strip() for s in raw_sections if s.strip()]

    if not sections or len(sections) == 1:
        truncated = rb_text[:max_chars]
        last_nl = truncated.rfind("\n")
        if last_nl > 1500:
            truncated = truncated[:last_nl]
        return truncated + "\n... [Đã rút gọn để tối ưu ngữ cảnh]"

    q_lower = question.lower()

    # Xác định các chủ đề trọng tâm từ câu hỏi
    wants_inventory = any(k in q_lower for k in ["tồn kho", "còn tồn", "hộp", "viên", "chai", "quy đổi", "divmod"])
    wants_customer = any(k in q_lower for k in ["khách hàng", "khách", "khach hang", "mua nhiều nhất"])
    wants_time_compare = any(k in q_lower for k in ["so với", "tháng trước", "tăng trưởng", "tăng hay giảm", "cùng kỳ", "trước tết"])
    wants_pharma = any(k in q_lower for k in ["hoạt chất", "thuốc", "kê đơn", "chỉ định", "dược"])
    wants_ranking = any(k in q_lower for k in ["nhất", "top", "xếp hạng", "cao nhất", "thấp nhất", "nhiều nhất"])
    wants_cancellation = any(k in q_lower for k in ["hủy", "huỷ", "trả hàng", "tỉ lệ hủy", "tỷ lệ huỷ"])

    scored_sections: List[Tuple[float, str]] = []
    for sec in sections:
        sec_low = sec.lower()
        score = 0.0

        # Điều khoản cốt lõi (luôn có điểm nền để ưu tiên)
        if any(k in sec_low for k in ["điều 1", "điều 4", "điều 6", "điều 9", "doanh thu", "đồng hạng"]):
            score += 2.0

        if wants_inventory and any(k in sec_low for k in ["điều 5", "tồn kho", "quy đổi", "hộp chẵn"]):
            score += 5.0
        if wants_customer and any(k in sec_low for k in ["điều 3", "khách lẻ", "khách hàng"]):
            score += 5.0
        if wants_time_compare and any(k in sec_low for k in ["điều 2", "kỳ đối chiếu", "so sánh"]):
            score += 5.0
        if wants_pharma and any(k in sec_low for k in ["điều 7", "hoạt chất", "kê đơn"]):
            score += 5.0
        if wants_ranking and any(k in sec_low for k in ["điều 9", "đồng hạng", "tie-breaker"]):
            score += 4.0
        if wants_cancellation and any(k in sec_low for k in ["hủy", "huỷ", "trả hàng"]):
            score += 4.0

        # Tính thêm overlap từ khóa
        q_words = set(re.findall(r"\w+", q_lower))
        sec_words = set(re.findall(r"\w+", sec_low))
        overlap = len(q_words & sec_words)
        score += overlap * 0.1

        scored_sections.append((score, sec))

    # Sắp xếp các mục theo điểm số giảm dần và gom lại cho tới max_chars
    scored_sections.sort(key=lambda x: x[0], reverse=True)
    selected: List[str] = []
    total_len = 0
    for score, sec in scored_sections:
        if total_len + len(sec) + 2 <= max_chars:
            selected.append(sec)
            total_len += len(sec) + 2
        else:
            remain = max_chars - total_len
            if remain > 200:
                selected.append(sec[:remain].rsplit("\n", 1)[0] + "\n...")
            break

    selected_set = set(selected)
    ordered_selected = [s for s in sections if s in selected_set or any(s.startswith(p[:100]) for p in selected)]
    if not ordered_selected:
        ordered_selected = selected

    return "\n\n".join(ordered_selected)


def select_few_shots(intent: str) -> str:
    """
    Chọn đúng 1 ví dụ phù hợp nhất với ý định của câu hỏi.
    Giúp giảm kích thước prompt xuống mức tối thiểu và tránh gây nhiễu code.
    """
    example = FEW_SHOT_LIBRARY.get(intent)
    if not example:
        example = FEW_SHOT_LIBRARY["aggregation"]

    return f"""==================== VÍ DỤ MINH HỌA PHÙ HỢP NHẤT ====================
{example}
"""


# ==============================================================================
# 4. CHỈ DẪN HỆ THỐNG (SYSTEM INSTRUCTION)
# ==============================================================================

SYSTEM_INSTRUCTION = """Bạn là một lập trình viên phân tích dữ liệu kinh doanh bằng Python/Pandas.
Nhiệm vụ của bạn là viết một hàm duy nhất:
```python
def solution(data):
    # logic tính toán an toàn
    return result
```

NGUYÊN TẮC THIẾT KẾ MÃ NGUỒN:
1. THAM SỐ `data`:
   - `data` là dictionary chứa các DataFrame thô: `{tên_bảng: DataFrame}`.
   - CHÚ Ý CỰC KỲ QUAN TRỌNG:
     + Các DataFrame trong `data` là bảng dữ liệu gốc từ Excel/CSV, KHÔNG CÓ sẵn cột `'clean_date'`!
     + TUYỆT ĐỐI KHÔNG lặp dict comprehension qua toàn bộ `data` để lọc ngày (CẤM VIẾT: `{name: df[...] for name, df in data.items()}`) vì mỗi bảng có cột hoàn toàn khác nhau (bảng sản phẩm/thuốc không có cột ngày!).
     + CHỈ lọc ngày trên đúng DataFrame của bảng giao dịch/hóa đơn có cột ngày sau khi đã tìm được bảng đó.
     + Để lọc theo ngày, bạn PHẢI tìm cột ngày gốc trong bảng:
       `d_c = next((c for c in df.columns if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)`
       Sau đó tự tạo cột:
       `df['clean_date'] = clean_date(df[d_c])`
       rồi mới lọc:
       `df[(df['clean_date'].dt.date >= pd.to_datetime(start_date).date()) & (df['clean_date'].dt.date <= pd.to_datetime(end_date).date())]`
     + BẮT BUỘC lọc đúng cả ngày bắt đầu và ngày kết thúc của kỳ hỏi! TUYỆT ĐỐI KHÔNG chỉ lọc `<= as_of_date` mà quên mốc đầu kỳ!
     + TUYỆT ĐỐI KHÔNG cộng dồn tiền qua nhiều bảng khác nhau trong vòng lặp! Chọn đúng 1 bảng tổng hoặc 1 bảng chi tiết rồi `break` ngay để tránh nhân đôi số tiền!
     + TUYỆT ĐỐI KHÔNG hardcode tên cột cố định như `df['Cần trả NCC']`, `df['Ngày bán']`, `df['Thành tiền']`! LUÔN LUÔN dùng biến cột động đã tìm được: `amt_col = next(...)` rồi dùng `clean_num(df[amt_col])`.
   - Bảng bán hàng / hóa đơn: thường có cả cột ngày và cột thành tiền/giá bán (ví dụ: 'DonHang_ChiTiet', 'BanHang_HoaDon', 'SoBanHang', 'pos'...).
   - Bảng nhập hàng: thường có chữ 'nhap' ('DonNhapHang', 'SoNhapHang', 'DanhSachNhapHang'...).
   - Bảng sản phẩm / thuốc / danh mục: 'SanPham', 'Thuoc', 'HangHoa', 'DanhMuc'...
   - Bảng khách hàng: 'KhachHang', 'Khach'...

2. XỬ LÝ CỘT VÀ TIỆN ÍCH DỰNG SẴN TRONG MÔI TRƯỜNG:
   - CÁC HÀM TIỆN ÍCH ĐÃ CÓ SẴN Ở GLOBAL SCOPE: `clean_num`, `clean_date`, `filter_future_data`, `apply_tie_breaker`.
   - TUYỆT ĐỐI CẤM ĐỊNH NGHĨA LẠI CÁC HÀM NÀY (CẤM VIẾT `def clean_num...` hay `def clean_date...`), việc này làm hao tốn token và gây lỗi cú pháp! Hãy gọi trực tiếp:
     + `clean_num(df[col])`: Tự động làm sạch cột tiền/số chuẩn xác (xử lý chuẩn cả dấu chấm và phẩy của VN '1.250.000', bỏ đ/VND/triệu/k). DÙNG: `clean_num(df[col])`!
     + `clean_date(df[col])`: Chuyển cột ngày thô về chuẩn datetime (dayfirst=True). DÙNG: `clean_date(df[col])`.
   - Không chọn nhầm cột thuế VAT khi tính doanh thu hoặc tổng tiền.

3. QUY TẮC NGHIỆP VỤ BẮT BUỘC THEO RULEBOOK:
   - [Doanh thu hợp lệ]: Chỉ tính các đơn KHÔNG huỷ và KHÔNG trả hàng (`trang_thai NOT IN ('huỷ', 'trả hàng', 'hủy', 'tra_hang')`). Đơn đang giao vẫn tính.
   - [Tỉ lệ huỷ đơn (%)]: (Số đơn huỷ / Tổng số đơn trong kỳ) * 100. Làm tròn 2 số thập phân, trả về float (ví dụ 1.06, không kèm chữ '%').
   - [Bán chạy nhất]: Xếp hạng theo TỔNG SỐ LƯỢNG quy đổi về đơn vị cơ bản.
   - [Khách mua nhiều nhất]: Xếp theo tổng doanh thu (hoặc số đơn nếu câu hỏi nói rõ) của từng khách, loại bỏ khách lẻ ('lẻ', 'khách lẻ', 'kl', 'nan', 'none').
   - [Quy tắc đồng hạng (Điều 9)]: Hai đối tượng bằng nhau ở tiêu chí câu hỏi thì xếp theo MÃ tăng dần (không có mã thì theo TÊN tăng dần). Luôn dùng `sort_values(by=[cot_tieu_chi, cot_ma_hoac_ten], ascending=[False, True])` hoặc hàm `apply_tie_breaker(records, sort_key, code_key, name_key)` có sẵn.
   - [Giới hạn as_of_date]: Mọi bản ghi có ngày > as_of_date coi như chưa xảy ra (loại bỏ khỏi tính toán).
   - [Không đủ dữ liệu]: Nếu dữ liệu shop không có cột/thông tin cần thiết hoặc kỳ hỏi nằm hoàn toàn ngoài dữ liệu shop -> `return "unanswerable"`.

4. ĐỊNH DẠNG ĐÁP ÁN TRẢ VỀ:
   - Số tiền VND / Số đếm: Trả về số nguyên `int` (ví dụ: `4820000`, `12`).
   - Tỉ lệ / Phần trăm: Trả về số thực `float` làm tròn 2 số thập phân (ví dụ: `1.06`, `12.5`).
   - Ngày tháng: Trả về chuỗi ISO `"YYYY-MM-DD"` hoặc `"YYYY-MM"`.
   - Đúng / Sai: Trả về boolean `True` hoặc `False`.
   - Danh sách Top K: Trả về kiểu `list` Python (ví dụ: `['A', 'B']`).
   - Bảng: Trả về dict `{"columns": [...], "rows": [[...], ...]}`.
   - Không thể trả lời: Trả về chuỗi `"unanswerable"`.

5. TỐI ƯU HÓA MÃ NGUỒN:
   - Viết code ngắn gọn, súc tích, đi thẳng vào giải pháp, KHÔNG viết comment rườm rà dài dòng để tránh bị cắt cụt token.
   - Luôn đảm bảo hàm có câu lệnh `return` ở cuối luồng tính toán.
"""


# ==============================================================================
# 5. HÀM TẠO PROMPT CHÍNH (BUILD PROMPT)
# ==============================================================================

def build_prompt(
    schema_str: str,
    as_of_date: str,
    question: str,
    rulebook_content: Optional[str] = None,
    business_note: Optional[str] = None,
    candidates: Optional[List[Any]] = None,
    entity_matches: Optional[List[Any]] = None,
    return_messages: bool = False
) -> Any:
    """
    Ráp nối toàn bộ thông tin thành Prompt hoàn chỉnh cho mô hình Qwen2.5-Coder.
    
    Args:
        schema_str (str): Mô tả danh sách bảng, tên cột và kiểu dữ liệu.
        as_of_date (str): Ngày mốc tham chiếu "hôm nay" (YYYY-MM-DD).
        question (str): Câu hỏi tự nhiên bằng tiếng Việt từ questions.jsonl.
        rulebook_content (str, optional): Nội dung file rulebook.md của split.
        business_note (str, optional): Ghi chú từ README.md của shop.
        candidates (list, optional): Danh sách thực thể tiềm năng từ shop để đối soát.
        entity_matches (list, optional): Kết quả liên kết thực thể đã tìm sẵn từ trước.
        return_messages (bool): Nếu True, trả về tuple (system_prompt, user_prompt) cho ChatML.
        
    Returns:
        str hoặc Tuple[str, str]: Prompt hoàn chỉnh.
    """
    # 1. Phân loại ý định câu hỏi và chọn Few-shot động
    intent = classify_intent(question)
    few_shot_block = retrieve_dynamic_few_shot(question=question, intent=intent, entity_matches=entity_matches)

    # 2. Giải mã thời gian tự động
    temporal_info = resolve_temporal_context(question, as_of_date)
    temporal_lines = [f"MỐC THỜI GIAN THAM CHIẾU (as_of_date / hôm nay): {temporal_info['as_of_date']}"]
    if temporal_info.get("comparison_start") and temporal_info.get("comparison_end"):
        temporal_lines.append(f"KHOẢNG THỜI GIAN KỲ CHÍNH: từ '{temporal_info.get('start_date')}' đến '{temporal_info.get('end_date')}'")
        temporal_lines.append(f"KHOẢNG THỜI GIAN KỲ ĐỐI CHIẾU (SO SÁNH): từ '{temporal_info.get('comparison_start')}' đến '{temporal_info.get('comparison_end')}' ({temporal_info.get('comparison_desc', '')})")
    else:
        temporal_lines.append(f"KHOẢNG THỜI GIAN ĐÃ ĐƯỢC GIẢI MÃ: {temporal_info['description']}")
    temporal_lines.append(f"GỢI Ý LỌC PANDAS: {temporal_info['code_hint']}")
    temporal_text = "\n".join(temporal_lines)

    # 2b. Đối soát thực thể (Entity Linking)
    entity_block = ""
    matches = entity_matches
    if matches is None and candidates and link_entities is not None:
        try:
            matches = link_entities(question, candidates=candidates, threshold=0.55)
        except Exception:
            matches = None

    if matches:
        entity_lines = []
        for m in matches[:5]:
            val = getattr(m, "matched_value", str(m))
            term = getattr(m, "query_term", "")
            meta = getattr(m, "metadata", {}) or {}
            src_tbl = meta.get("source_table", "")
            src_col = meta.get("source_col", "")
            loc = f" (ở bảng '{src_tbl}', cột '{src_col}')" if src_tbl and src_col else ""
            term_note = f" (gợi ý từ '{term}')" if term and term.lower() != val.lower() else ""

            # Trích xuất row_context (mã hàng, SKU, đơn vị tính, quy đổi, hoạt chất...) nếu có
            row_ctx = meta.get("row_context") or {}
            ctx_items = []
            for k, v in row_ctx.items():
                k_clean = str(k).strip()
                v_clean = str(v).strip()
                if not v_clean or v_clean.lower() in ("nan", "none", "null"):
                    continue
                if src_col and k_clean.lower() == src_col.lower():
                    continue
                if k_clean.lower() in ("tên hàng", "tên sản phẩm", "ten_hang", "tên thuốc") and v_clean.lower() == val.lower():
                    continue
                ctx_items.append(f"{k_clean}: {v_clean}")
            ctx_str = f" [Thông tin dòng: {', '.join(ctx_items)}]" if ctx_items else ""

            entity_lines.append(f"- '{val}'{loc}{term_note}{ctx_str}")
        if entity_lines:
            entity_block = (
                "\nTHỰC THỂ ĐỐI SOÁT TRONG CƠ SỞ DỮ LIỆU (ENTITY LINKING):\n"
                "Các giá trị thực tế trong dữ liệu khớp với câu hỏi của người dùng:\n"
                + "\n".join(entity_lines)
                + "\n-> LƯU Ý: Hãy sử dụng chính xác các giá trị chuỗi hoặc Mã hàng / SKU / Quy đổi tương ứng khi lọc điều kiện hoặc tính toán trong code.\n"
            )

    # 3. Khối Rulebook tóm tắt (nếu có)
    rulebook_block = ""
    if rulebook_content and rulebook_content.strip():
        rb_text = extract_relevant_rulebook_clauses(rulebook_content, question, max_chars=2500)
        rulebook_block = f"""
==================== QUY TẮC NGHIỆP VỤ BẮT BUỘC (THEO RULEBOOK CỦA SPLIT NÀY) ====================
{rb_text}
"""

    # 4. Khối ghi chú doanh nghiệp (nếu có)
    biz_context = ""
    if business_note and business_note.strip():
        biz_context = f"\nGHI CHÚ CỦA DOANH NGHIỆP (README.MD):\n{business_note.strip()}\n"

    # 5. Ghép System Prompt
    system_prompt = f"{SYSTEM_INSTRUCTION}\n{rulebook_block}\n{few_shot_block}".strip()

    # 6. Ghép User Prompt
    user_prompt = f"""==================== DỮ LIỆU ĐẦU VÀO CHO BÀI TOÁN CẦN GIẢI ====================
DANH SÁCH BẢNG VÀ CỘT DỮ LIỆU TRONG `data`:
{schema_str}
{biz_context}
CHỈ DẪN MỐC THỜI GIAN:
{temporal_text}
{entity_block}
CÂU HỎI CỦA NGƯỜI DÙNG:
"{question}"

YÊU CẦU THỰC HIỆN:
1. Quan sát kỹ danh sách bảng và cột ở trên để chọn đúng bảng và cột.
2. Áp dụng khoảng thời gian đã được giải mã và mốc as_of_date để lọc dữ liệu.
3. Tuyệt đối không lặp dict comprehension lọc ngày trên toàn bộ `data`. Tìm bảng cụ thể, tìm cột ngày gốc bằng `d_c = next(...)`, tự tạo `df['clean_date'] = clean_date(df[d_c])` và dùng biến cột động `amt_col` thay vì hardcode tên cột.
4. Chỉ viết duy nhất một hàm `def solution(data):` trả về kết quả, không viết giải thích bên ngoài.
5. Viết code ngắn gọn, súc tích, không viết comment dài dòng để tránh bị cắt cụt token.
```python
"""

    if return_messages:
        return system_prompt, user_prompt

    # Trả về dạng chuỗi gộp (tương thích ngược)
    return f"{system_prompt}\n\n{user_prompt}"


if __name__ == "__main__":
    current_rulebook = load_rulebook("competition_data/train")
    sample_schema = "- Bảng 'DonHang_ChiTiet': [Mã đơn, Ngày đặt, Trạng thái, Thành tiền]"
    sys_p, usr_p = build_prompt(
        schema_str=sample_schema,
        as_of_date="2026-06-28",
        question="Dịp Tết 2026, mặt hàng nào bán chạy nhất ạ?",
        rulebook_content=current_rulebook,
        return_messages=True
    )
    print("=== KIỂM TRA TẠO PROMPT ===")
    print("System Prompt Length:", len(sys_p))
    print("User Prompt Snippet:\n", usr_p[:350])
