"""
Module: prompt_builder.py
Mục đích: Xây dựng Prompt kỹ thuật cao (Few-shot Prompt Engineering) hướng dẫn mô hình 
          Qwen2.5-Coder-3B-Instruct sinh mã Python/Pandas chính xác.
          HỖ TRỢ ĐỌC ĐỘNG file rulebook.md theo từng split (Train / Public Test / Private Test)
          để mô hình tự thích ứng với các ngành mới và quy tắc mới của BTC.
Tác giả: Long (AI Architect & Model Lead)
"""

import os
import sys
from pathlib import Path

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi Unicode
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_rulebook(split_dir: str = "competition_data/train") -> str:
    """
    Đọc tự động file rulebook.md của split hiện tại.
    
    Args:
        split_dir (str): Đường dẫn thư mục split (ví dụ: 'competition_data/train', 'competition_data/public_test' hoặc '/data')
        
    Returns:
        str: Nội dung toàn bộ file rulebook.md (hoặc chuỗi rỗng nếu không tìm thấy)
    """
    rulebook_path = Path(split_dir) / "rulebook.md"
    if rulebook_path.exists():
        try:
            return rulebook_path.read_text(encoding="utf-8-sig", errors="replace").strip()
        except Exception as e:
            print(f"[CẢNH BÁO] Không đọc được {rulebook_path}: {e}")
            return ""
    return ""


SYSTEM_INSTRUCTION = """Bạn là một chuyên gia lập trình phân tích dữ liệu kinh doanh Python/Pandas cao cấp.
Nhiệm vụ duy nhất của bạn là viết một hàm Python:
```python
def solution(data):
    # logic tính toán
    return result
```

==================== NGUYÊN TẮC THIẾT KẾ MÃ NGUỒN ====================
1. THAM SỐ `data`:
   - `data` là một Python dictionary chứa sẵn các bảng dữ liệu dưới dạng `pandas.DataFrame`.
   - Cú pháp truy cập bảng: `df = data["Tên_Bảng"]` (chính xác theo danh sách bảng được cung cấp).
   - TUYỆT ĐỐI KHÔNG sử dụng `pd.read_csv()`, `pd.read_excel()` hay đọc file từ ổ đĩa. Mọi dữ liệu đã nằm trên RAM trong `data`.

2. XỬ LÝ DỮ LIỆU THỰC TẾ (DATA WRANGLING CHUẨN XÁC):
   - [Ngày tháng]: Cột ngày có thể ở định dạng 'DD/MM/YYYY' hoặc 'YYYY-MM-DD'. Luôn chuyển đổi an toàn:
     `df['Ngày'] = pd.to_datetime(df['Ngày'], dayfirst=True, errors='coerce')`
   - [Số tiền / Số lượng]: Nếu cột số bị dính dấu phẩy hoặc chấm phân cách hàng nghìn dạng chuỗi (ví dụ: '35,000'), phải làm sạch:
     `df['Cột_Số'] = pd.to_numeric(df['Cột_Số'].astype(str).str.replace(',', '').str.replace(' ', ''), errors='coerce').fillna(0)`

3. ĐỊNH DẠNG GIÁ TRỊ TRẢ VỀ (RETURN FORMAT):
   - Tiền tệ VND / Số đếm nguyên: Trả về kiểu số nguyên `int` (ví dụ: `4500000`, `12`).
   - Tỉ lệ / Phần trăm: Trả về số thực `float` làm tròn 2 chữ số thập phân, KHÔNG kèm ký hiệu '%' (ví dụ: `15.25`).
   - Danh sách Top K: Trả về kiểu `list` Python chuẩn (ví dụ: `['Sản phẩm A', 'Sản phẩm B']`).
   - Ngày tháng: Trả về chuỗi chuẩn ISO (ví dụ: `'2025-05-15'` hoặc `'2025-05'`).
   - Đúng / Sai: Trả về boolean `True` hoặc `False`.
   - Không thể trả lời do thiếu dữ liệu / ngoài kỳ: Trả về chuỗi `"unanswerable"`.
"""

FEW_SHOT_DEMONSTRATIONS = """
==================== CÁC VÍ DỤ MẪU (FEW-SHOT EXAMPLES) ====================

--- VÍ DỤ 1: Tính tổng doanh thu tháng (Bỏ đơn hủy, chuẩn hóa tiền VND) ---
Câu hỏi: "Tổng doanh thu trong tháng 5 năm 2025 là bao nhiêu?" (as_of_date = "2025-06-01")
Code chuẩn:
```python
def solution(data):
    df = data[list(data.keys())[0]].copy()
    
    # 1. Chuẩn hóa ngày và lọc tháng 5/2025
    date_col = [c for c in df.columns if 'ngày' in c.lower() or 'date' in c.lower()][0]
    df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
    mask_time = (df[date_col].dt.year == 2025) & (df[date_col].dt.month == 5)
    
    # 2. Loại bỏ đơn hủy / trả
    status_cols = [c for c in df.columns if 'trạng thái' in c.lower() or 'status' in c.lower()]
    if status_cols:
        s_col = status_cols[0]
        mask_valid = ~df[s_col].astype(str).str.lower().str.contains('hủy|huỷ|trả|cancel')
    else:
        mask_valid = pd.Series(True, index=df.index)
        
    df_filtered = df[mask_time & mask_valid]
    
    # 3. Tính tổng tiền
    amount_col = [c for c in df.columns if any(k in c.lower() for k in ['thành tiền', 'tổng tiền', 'doanh thu', 'tiền'])][0]
    total_rev = pd.to_numeric(df_filtered[amount_col].astype(str).str.replace(',', ''), errors='coerce').sum()
    return int(round(total_rev))
```

--- VÍ DỤ 2: Top 3 mặt hàng bán chạy nhất (Theo số lượng, trả về list) ---
Câu hỏi: "Top 3 sản phẩm bán chạy nhất trong tháng 3/2026 là những gì?" (as_of_date = "2026-04-01")
Code chuẩn:
```python
def solution(data):
    df = data[list(data.keys())[0]].copy()
    
    # Lọc thời gian và đơn hợp lệ
    date_col = [c for c in df.columns if 'ngày' in c.lower() or 'date' in c.lower()][0]
    df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
    df = df[(df[date_col].dt.year == 2026) & (df[date_col].dt.month == 3)]
    
    status_cols = [c for c in df.columns if 'trạng thái' in c.lower()]
    if status_cols:
        df = df[~df[status_cols[0]].astype(str).str.lower().str.contains('hủy|huỷ|trả')]
        
    # Gom nhóm theo tên sản phẩm và tính tổng số lượng
    item_col = [c for c in df.columns if 'tên' in c.lower() and ('sản phẩm' in c.lower() or 'hàng' in c.lower() or 'món' in c.lower())][0]
    qty_col = [c for c in df.columns if 'số lượng' in c.lower() or 'sl' in c.lower()][0]
    df[qty_col] = pd.to_numeric(df[qty_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    top3 = df.groupby(item_col)[qty_col].sum().sort_values(ascending=False).head(3)
    return list(top3.index)
```

--- VÍ DỤ 3: Khách hàng chi tiêu nhiều nhất (Loại bỏ khách lẻ / vãng lai) ---
Câu hỏi: "Khách hàng nào chi tiêu nhiều tiền nhất trong tháng 1/2026?" (as_of_date = "2026-02-01")
Code chuẩn:
```python
def solution(data):
    df = data[list(data.keys())[0]].copy()
    
    # Lọc đơn hợp lệ theo tháng
    date_col = [c for c in df.columns if 'ngày' in c.lower() or 'date' in c.lower()][0]
    df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
    df = df[(df[date_col].dt.year == 2026) & (df[date_col].dt.month == 1)]
    
    # LOẠI BỎ KHÁCH LẺ (bắt buộc theo Rulebook)
    cust_col = [c for c in df.columns if 'khách' in c.lower()][0]
    invalid_cust = df[cust_col].astype(str).str.strip().str.lower().isin(['lẻ', 'khách lẻ', 'kl', '', 'nan', 'none'])
    df = df[~invalid_cust]
    
    amount_col = [c for c in df.columns if any(k in c.lower() for k in ['tổng tiền', 'thành tiền', 'tiền'])][0]
    df[amount_col] = pd.to_numeric(df[amount_col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    top_cust = df.groupby(cust_col)[amount_col].sum().sort_values(ascending=False)
    if top_cust.empty:
        return "unanswerable"
    return str(top_cust.index[0])
```
"""


def build_prompt(
    schema_str: str,
    as_of_date: str,
    question: str,
    rulebook_content: str = None,
    business_note: str = None
) -> str:
    """
    Ráp nối toàn bộ thông tin thành Prompt hoàn chỉnh cho mô hình Qwen2.5-Coder-3B.
    
    Args:
        schema_str (str): Mô tả danh sách bảng, tên cột và kiểu dữ liệu (từ data_loader của Phát).
        as_of_date (str): Ngày mốc tham chiếu "hôm nay" (YYYY-MM-DD).
        question (str): Câu hỏi tự nhiên bằng tiếng Việt từ questions.jsonl.
        rulebook_content (str, optional): Nội dung toàn văn file rulebook.md của split hiện tại.
        business_note (str, optional): Ghi chú bổ sung từ README.md của shop (nếu có).
        
    Returns:
        str: Chuỗi prompt hoàn chỉnh sẵn sàng nạp vào llm_client.generate_code()
    """
    # 1. Khối Rulebook động theo Split
    rulebook_block = ""
    if rulebook_content and rulebook_content.strip():
        rulebook_block = f"""
==================== QUY TẮC NGHIỆP VỤ BẮT BUỘC (THEO RULEBOOK CỦA SPLIT NÀY) ====================
{rulebook_content.strip()}
"""

    # 2. Khối ghi chú riêng của doanh nghiệp (README.md)
    biz_context = ""
    if business_note and business_note.strip():
        biz_context = f"\nGHI CHÚ RIÊNG CỦA DOANH NGHIỆP (README.MD):\n{business_note.strip()}\n"

    # 3. Khối thông tin truy vấn cụ thể
    user_query_block = f"""
==================== DỮ LIỆU ĐẦU VÀO CHO BÀI TOÁN CẦN GIẢI ====================
DANH SÁCH BẢNG VÀ CỘT DỮ LIỆU CÓ SẴN TRONG `data`:
{schema_str}
{biz_context}
MỐC THỜI GIAN THAM CHIẾU (as_of_date / hôm nay): {as_of_date}

CÂU HỎI CỦA NGƯỜI DÙNG:
"{question}"

CHỈ DẪN CUỐI CÙNG:
- Áp dụng các định nghĩa và luật nghiệp vụ trong Rulebook ở trên để tính toán chính xác.
- Hãy viết hàm `def solution(data):` giải quyết bài toán.
- Chỉ trả về khối code Python duy nhất, không viết bất kỳ lời giải thích nào bên ngoài.
```python
"""

    full_prompt = f"{SYSTEM_INSTRUCTION}\n{rulebook_block}\n{FEW_SHOT_DEMONSTRATIONS}\n{user_query_block}"
    return full_prompt


# Cho phép chạy thử trực tiếp file này để kiểm tra
if __name__ == "__main__":
    current_rulebook = load_rulebook("competition_data/train")
    sample_schema = "Bảng 'DonHang': [Mã đơn hàng, Ngày đặt hàng, Trạng thái, Tên khách hàng, Tổng tiền]"
    prompt = build_prompt(
        schema_str=sample_schema,
        as_of_date="2025-06-01",
        question="Tổng doanh thu tháng 5 năm 2025 là bao nhiêu?",
        rulebook_content=current_rulebook
    )
    print(f"-> Tạo prompt thành công! Độ dài: {len(prompt)} ký tự (~{len(prompt)//4} tokens).")
