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
    
    Args:
        question (str): Câu hỏi của người dùng.
        as_of_date_str (str): Ngày tham chiếu mốc (YYYY-MM-DD).
        calendar_path (str, optional): Đường dẫn tệp calendar.csv nếu có.
        
    Returns:
        Dict[str, Any]: Chứa các trường:
            - as_of_date: ngày tham chiếu (str)
            - start_date: ngày bắt đầu (str hoặc None)
            - end_date: ngày kết thúc (str hoặc None)
            - description: mô tả diễn giải ngắn cho prompt
            - code_hint: gợi ý câu lệnh lọc dữ liệu trong pandas
    """
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

    # 2. Nhóm đa bảng / tra cứu hoạt chất, thuốc kê đơn, quy đổi đơn vị (ưu tiên cao vì cần kỹ thuật JOIN)
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

    # 6. Mặc định là tính tổng / đếm (aggregation)
    return "aggregation"


# ==============================================================================
# 3. THƯ VIỆN VÍ DỤ TINH GỌN (DYNAMIC FEW-SHOT LIBRARY)
# ==============================================================================

FEW_SHOT_LIBRARY: Dict[str, str] = {
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

    "multitable_join": """--- VÍ DỤ MẪU: TRA CỨU ĐA BẢNG (JOIN) ---
Câu hỏi: "Thuốc có hoạt chất Paracetamol tháng này bán được bao nhiêu tiền?" (as_of_date = "2026-05-25")
```python
def solution(data):
    # 1. Tìm bảng danh mục thuốc chứa hoạt chất
    df_med = None
    act_col = None
    code_med_col = None
    for name, df in data.items():
        cols = df.columns.tolist()
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['hoạt chất', 'hoatchat', 'thanhphanchinh'])), None)
        c_c = next((c for c in cols if any(k in str(c).lower() for k in ['mã thuốc', 'mã hàng', 'ma_thuoc', 'mã sku', 'mahanghoa'])), None)
        if a_c and c_c:
            df_med = df.copy()
            act_col = a_c
            code_med_col = c_c
            break
    if df_med is None:
        return "unanswerable"

    matched_meds = df_med[df_med[act_col].astype(str).str.lower().str.contains('paracetamol')]
    if matched_meds.empty:
        return "unanswerable"
    target_codes = set(matched_meds[code_med_col].astype(str))

    # 2. Tìm bảng bán hàng chi tiết
    df_sales = None
    d_col = None
    amt_col = None
    sales_code_col = None
    for name, df in data.items():
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền', 'trigia']) and 'thuế' not in str(c).lower()), None)
        c_c = next((c for c in cols if any(k in str(c).lower() for k in ['mã thuốc', 'mã hàng', 'ma_thuoc', 'mã sku', 'mahanghoa'])), None)
        if d_c and a_c and c_c:
            df_sales = df.copy()
            d_col = d_c
            amt_col = a_c
            sales_code_col = c_c
            break
    if df_sales is None:
        return "unanswerable"

    # Lọc thời gian và mã thuốc
    df_sales[d_col] = pd.to_datetime(df_sales[d_col], dayfirst=True, errors='coerce')
    df_sales = df_sales[(df_sales[d_col] >= pd.Timestamp("2026-05-01")) & (df_sales[d_col] <= pd.Timestamp("2026-05-25"))]
    df_sales = df_sales[df_sales[sales_code_col].astype(str).isin(target_codes)]

    total = pd.to_numeric(df_sales[amt_col].astype(str).str.replace(',', '').str.replace(' ', ''), errors='coerce').fillna(0).sum()
    return int(round(total))
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
   - `data` là dictionary chứa các DataFrame: `{tên_bảng: DataFrame}`.
   - Hãy kiểm tra danh sách bảng và cột thực tế của shop trong prompt để chọn đúng bảng.
   - Bảng bán hàng / hóa đơn: thường có cả cột ngày và cột thành tiền/giá bán (ví dụ: 'DonHang_ChiTiet', 'BanHang_HoaDon', 'SoBanHang', 'pos'...).
   - Bảng nhập hàng: thường có chữ 'nhap' ('DonNhapHang', 'SoNhapHang'...).
   - Bảng sản phẩm / thuốc / danh mục: 'SanPham', 'Thuoc', 'HangHoa', 'DanhMuc'...
   - Bảng khách hàng: 'KhachHang', 'Khach'...

2. XỬ LÝ CỘT VÀ KIỂU DỮ LIỆU:
   - Cột ngày: tìm cột có chữ 'ngày', 'date', 'ngaylap', 'thời gian'. Chuyển đổi an toàn:
     `df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')`
   - Cột tiền: bỏ dấu phẩy phân cách nghìn và khoảng trắng trước khi tính tổng:
     `pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace(' ', ''), errors='coerce').fillna(0)`
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
        return_messages (bool): Nếu True, trả về tuple (system_prompt, user_prompt) cho ChatML.
        
    Returns:
        str hoặc Tuple[str, str]: Prompt hoàn chỉnh.
    """
    # 1. Phân loại ý định câu hỏi và chọn Few-shot động
    intent = classify_intent(question)
    few_shot_block = select_few_shots(intent)

    # 2. Giải mã thời gian tự động
    temporal_info = resolve_temporal_context(question, as_of_date)
    temporal_text = (
        f"MỐC THỜI GIAN THAM CHIẾU (as_of_date / hôm nay): {temporal_info['as_of_date']}\n"
        f"KHOẢNG THỜI GIAN ĐÃ ĐƯỢC GIẢI MÃ: {temporal_info['description']}\n"
        f"GỢI Ý LỌC PANDAS: {temporal_info['code_hint']}"
    )

    # 3. Khối Rulebook tóm tắt (nếu có)
    rulebook_block = ""
    if rulebook_content and rulebook_content.strip():
        rulebook_block = f"""
==================== QUY TẮC NGHIỆP VỤ BẮT BUỘC (THEO RULEBOOK CỦA SPLIT NÀY) ====================
{rulebook_content.strip()}
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

CÂU HỎI CỦA NGƯỜI DÙNG:
"{question}"

YÊU CẦU THỰC HIỆN:
1. Quan sát kỹ danh sách bảng và cột ở trên để chọn đúng bảng và cột.
2. Áp dụng khoảng thời gian đã được giải mã và mốc as_of_date để lọc dữ liệu.
3. Chỉ viết duy nhất một hàm `def solution(data):` trả về kết quả, không viết giải thích bên ngoài.
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
