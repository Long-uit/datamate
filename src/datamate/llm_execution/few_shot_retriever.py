"""
few_shot_retriever.py — Bộ truy hồi Few-Shot động (Dynamic Few-Shot RAG) cho DataMate.

Chọn 1-2 ví dụ minh họa sát nhất với cấu trúc câu hỏi, kiểu đáp án và thực thể:
- Sử dụng các hàm tiện ích dựng sẵn: clean_num, clean_date, apply_tie_breaker, filter_future_data.
- Hướng dẫn mô hình viết code ngắn gọn, chuẩn xác, không bị bẫy định dạng số/ngày.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

EXEMPLAR_BANK: Dict[str, str] = {
    "cong_no": """--- VÍ DỤ MINH HỌA: TÍNH CÔNG NỢ / TUỔI NỢ / KHÁCH CÒN NỢ ---
Câu hỏi: "Tính đến hết ngày 19/08/2026, có bao nhiêu khách còn nợ cửa hàng?" (as_of_date = "2026-08-19")
```python
def solution(data):
    # 1. Tìm bảng công nợ / sổ nợ (KHÔNG dùng cột thành tiền của bảng bán hàng)
    df_debt = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        cols_low = [str(c).lower() for c in df.columns]
        is_debt_tbl = (
            any(k in n_clean for k in ['congno', 'sono', 'sogop', 'phaithu', 'hanno', 'phieuthu', 'soquy', 'thanhtoan'])
            or any(any(k in c for k in ['còn nợ', 'tiền nợ', 'phải thu', 'hạn trả']) for c in cols_low)
        )
        if is_debt_tbl:
            df_debt = df.copy()
            break
    if df_debt is None:
        raise DataNotFoundError("Không tìm thấy bảng công nợ / sổ nợ trong dữ liệu", table_name="công nợ", available_tables=list(data.keys()))

    cols = df_debt.columns.tolist()
    cust_col = next((c for c in cols if any(k in str(c).lower() for k in ['khách hàng', 'mã khách', 'tenkh', 'tên khách', 'makh', 'so kh'])), None)
    debt_col = next((c for c in cols if any(k in str(c).lower() for k in ['còn nợ', 'tiền nợ', 'phải thu', 'cần thu', 'số tiền', 'tiền']) and 'hạn' not in str(c).lower()), None)
    if not cust_col or not debt_col:
        raise DataNotFoundError("Thiếu cột khách hàng hoặc cột tiền nợ trong bảng công nợ", column_name="còn nợ/khách", available_columns=cols)

    # 2. Lọc thời gian <= as_of_date nếu có cột ngày
    d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian', 'ngaylap', 'hạn trả', 'han tra'])), None)
    if d_c:
        df_debt['clean_date'] = clean_date(df_debt[d_c])
        df_debt = df_debt[df_debt['clean_date'].dt.date <= pd.to_datetime("2026-08-19").date()]

    # 3. Lọc khoản còn nợ (> 0), loại bỏ khách lẻ
    df_debt['clean_debt'] = clean_num(df_debt[debt_col])
    valid_debt = df_debt[(df_debt['clean_debt'] > 0) & (~df_debt[cust_col].astype(str).str.lower().str.contains('lẻ|khách lẻ|nan|none'))]
    if valid_debt.empty:
        return 0

    return int(valid_debt[cust_col].dropna().nunique())
```""",

    "purchase_import": """--- VÍ DỤ MINH HỌA: TÍNH TỔNG TIỀN / GIÁ TRỊ PHIẾU NHẬP HÀNG ---
Câu hỏi: "Tháng này tổng giá trị các phiếu nhập hàng là bao nhiêu?" (as_of_date = "2026-09-07")
```python
def solution(data):
    # 1. Tìm bảng nhập hàng (ưu tiên bảng tổng hợp phiếu nhập, tránh bảng chi tiết)
    df_nhap = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        if 'nhap' in n_clean and not any(k in n_clean for k in ['chitiet', 'chi_tiet', 'detail', 'lohang']):
            df_nhap = df.copy()
            break
    if df_nhap is None:
        df_nhap = next((df.copy() for name, df in data.items() if 'nhap' in re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())), None)
    if df_nhap is None:
        raise DataNotFoundError("Không tìm thấy bảng nhập hàng trong dữ liệu", table_name="nhập hàng", available_tables=list(data.keys()))

    # 2. Tìm cột ngày và cột tiền
    cols = df_nhap.columns.tolist()
    d_c = next((c for c in cols if any(k in str(c).lower() for k in ['thời gian', 'ngày', 'date', 'ngaylap'])), None)
    a_c = next((c for c in cols if any(k in str(c).lower() for k in ['cần trả ncc', 'tổng tiền', 'tong tien', 'thành tiền', 'giá trị']) and 'trả hàng' not in str(c).lower()), None)
    if not d_c or not a_c:
        raise DataNotFoundError("Bảng nhập hàng thiếu cột ngày hoặc cột tiền", column_name="ngày/tiền", available_columns=cols)

    # 3. Lọc đúng kỳ tháng này: năm 2026, tháng 9, từ ngày 1 đến hết as_of_date
    df_nhap['clean_date'] = clean_date(df_nhap[d_c])
    df_nhap = df_nhap[(df_nhap['clean_date'].dt.year == 2026) & (df_nhap['clean_date'].dt.month == 9) & (df_nhap['clean_date'].dt.date <= pd.to_datetime("2026-09-07").date())]

    # 4. Loại bỏ phiếu hủy nếu có trạng thái hoặc ghi chú
    st_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'ghi chú', 'cancel'])), None)
    if st_c:
        df_nhap = df_nhap[~df_nhap[st_c].astype(str).str.lower().str.contains('hủy|huỷ|cancel')]

    return int(round(clean_num(df_nhap[a_c]).sum()))
```""",

    "aggregation": """--- VÍ DỤ MINH HỌA: TÍNH TỔNG DOANH THU / SỐ TIỀN / LƯỢNG BÁN ---
Câu hỏi: "Tháng này tổng giá trị các đơn bán hàng là bao nhiêu?" (as_of_date = "2026-05-25")
```python
def solution(data):
    # 1. Tìm bảng bán hàng chi tiết (bảng có cả cột ngày và cột thành tiền)
    df_sales = None
    date_col = None
    amt_col = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        if any(k in n_clean for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            date_col = d_c
            amt_col = a_c
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền", table_name="bán hàng", available_tables=list(data.keys()))

    # 2. Chuẩn hóa ngày và lọc kỳ chính (tháng này: 2026-05-01 đến 2026-05-25)
    df_sales['clean_date'] = clean_date(df_sales[date_col])
    df_sales = df_sales[(df_sales['clean_date'].dt.date >= pd.to_datetime("2026-05-01").date()) & 
                        (df_sales['clean_date'].dt.date <= pd.to_datetime("2026-05-25").date())]

    # 3. Loại bỏ đơn hủy và trả hàng (Điều 1 Rulebook)
    status_col = next((c for c in df_sales.columns if any(k in str(c).lower() for k in ['trạng thái', 'status', 'tình trạng', 'ghi chú tt', 'ghi chú'])), None)
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains('hủy|huỷ|trả|cancel')]

    # 4. Dùng clean_num xử lý chuẩn mọi định dạng tiền tệ VN
    total_val = clean_num(df_sales[amt_col]).sum()
    return int(round(total_val))
```""",

    "rate_percentage": """--- VÍ DỤ MINH HỌA: TÍNH TỈ LỆ PHẦN TRĂM (%) ---
Câu hỏi: "Tháng 9/2025 cửa hàng có bao nhiêu % đơn bị huỷ?" (as_of_date = "2026-05-25")
```python
def solution(data):
    df_orders = None
    date_col = None
    status_col = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        if any(k in n_clean for k in ['nhap', 'chiphi', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
        s_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'tình trạng', 'ghi chú tt', 'ghi chú', 'note'])), None)
        if d_c and s_c:
            df_orders = df.copy()
            date_col = d_c
            status_col = s_c
            break
    if df_orders is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột trạng thái/ghi chú", table_name="hóa đơn", available_tables=list(data.keys()))

    # Lọc tháng 9/2025
    df_orders['clean_date'] = clean_date(df_orders[date_col])
    df_period = df_orders[(df_orders['clean_date'].dt.year == 2025) & (df_orders['clean_date'].dt.month == 9)]
    
    # Đếm theo mã đơn duy nhất (tránh đếm trùng dòng chi tiết của cùng 1 đơn)
    order_id_col = next((c for c in df_period.columns if any(k in str(c).lower() for k in ['mã đơn', 'ma_don', 'số phiếu', 'order', 'hóa đơn', 'mã hđ', 'mã phiếu'])), None)
    if order_id_col:
        total_orders = df_period[order_id_col].dropna().nunique()
        cancelled_orders = df_period[df_period[status_col].astype(str).str.lower().str.contains('hủy|huỷ|cancel')][order_id_col].dropna().nunique()
    else:
        total_orders = len(df_period)
        cancelled_orders = len(df_period[df_period[status_col].astype(str).str.lower().str.contains('hủy|huỷ|cancel')])

    if total_orders == 0:
        return 0.0

    # Tỉ lệ huỷ = (số đơn huỷ / tổng số đơn trong kỳ) * 100
    rate = (cancelled_orders / total_orders) * 100.0
    return round(float(rate), 2)
```""",

    "average_unit_price": """--- VÍ DỤ MINH HỌA: TÍNH GIÁ NHẬP / BÁN BÌNH QUÂN QUY ĐỔI ---
Câu hỏi: "Trong tháng 1/2025, Mì Omachi sườn hầm nhập vào giá bình quân một thùng là bao nhiêu ạ?" (as_of_date = "2026-08-05")
```python
def solution(data):
    # 1. Tìm bảng nhập hàng
    df_import = None
    for name, df in data.items():
        if any(k in name.lower() for k in ['nhap', 'ncc']):
            df_import = df.copy()
            break
    if df_import is None:
        raise DataNotFoundError("Không tìm thấy bảng nhập hàng trong dữ liệu", table_name="nhập hàng", available_tables=list(data.keys()))

    cols = df_import.columns.tolist()
    date_col = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    prod_col = next((c for c in cols if any(k in str(c).lower() for k in ['mặt hàng', 'tên hàng', 'sản phẩm', 'mã hàng'])), None)
    price_col = next((c for c in cols if any(k in str(c).lower() for k in ['đơn giá', 'giá nhập', 'giá'])), None)
    qty_col = next((c for c in cols if any(k in str(c).lower() for k in ['số lượng', 'sl'])), None)

    # 2. Lọc thời gian tháng 1/2025
    df_import['clean_date'] = clean_date(df_import[date_col])
    df_import = df_import[(df_import['clean_date'].dt.year == 2025) & (df_import['clean_date'].dt.month == 1)]

    # 3. Lọc đúng sản phẩm theo tên hoặc mã hàng
    df_import = df_import[df_import[prod_col].astype(str).str.lower().str.contains('omachi|mì omachi', na=False)]
    if df_import.empty:
        return 0

    df_import['clean_price'] = clean_num(df_import[price_col])
    df_import['clean_qty'] = clean_num(df_import[qty_col]) if qty_col else 1

    # Giá bình quân đơn vị cơ bản = Tổng tiền / Tổng số lượng cơ bản
    total_spent = (df_import['clean_price'] * df_import['clean_qty']).sum()
    total_qty = df_import['clean_qty'].sum()
    avg_price_base = total_spent / total_qty if total_qty > 0 else 0

    # Nếu câu hỏi hỏi theo thùng (thường 30 gói/thùng hoặc lấy theo tỷ lệ quy đổi)
    packing_rate = 30
    return int(round(avg_price_base * packing_rate))
```""",

    "customer_count_threshold": """--- VÍ DỤ MINH HỌA: ĐẾM SỐ KHÁCH HÀNG THỎA ĐIỀU KIỆN ---
Câu hỏi: "Trong số khách đã mua hàng tháng 7/2026, bao nhiêu khách mua từ 8 đơn trở lên?" (as_of_date = "2026-08-29")
```python
def solution(data):
    df_sales = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        if any(k in n_clean for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
        c_c = next((c for c in cols if any(k in str(c).lower() for k in ['khách hàng', 'mã khách', 'tenkh', 'customer', 'tên khách'])), None)
        o_c = next((c for c in cols if any(k in str(c).lower() for k in ['mã đơn', 'số phiếu', 'order', 'hóa đơn', 'mã hđ'])), None)
        if d_c and c_c and o_c:
            df_sales = df.copy()
            date_col, cust_col, order_col = d_c, c_c, o_c
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày, khách và mã đơn", table_name="bán hàng", available_tables=list(data.keys()))

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    df_sales = df_sales[(df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month == 7)]
    
    # Loại bỏ khách lẻ / khách vô danh
    df_sales = df_sales[~df_sales[cust_col].astype(str).str.lower().str.contains('lẻ|khách lẻ|nan|none|null')]
    
    # Đếm số đơn của từng khách
    cust_orders = df_sales.groupby(cust_col)[order_col].nunique()
    qualifying_customers = (cust_orders >= 8).sum()
    return int(qualifying_customers)
```""",

    "ranking_topk": """--- VÍ DỤ MINH HỌA: TÌM ĐỐI TƯỢNG XẾP HẠNG / BÁN CHẠY NHẤT ---
Câu hỏi: "Dịp Tết 2026, mặt hàng nào bán chạy nhất?" (as_of_date = "2026-06-28")
```python
def solution(data):
    df_sales = None
    date_col = None
    prod_col = None
    qty_col = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
        p_c = next((c for c in cols if any(k in str(c).lower() for k in ['tên hàng', 'mặt hàng', 'sản phẩm', 'tên thuốc', 'product'])), None)
        q_c = next((c for c in cols if any(k in str(c).lower() for k in ['số lượng quy đổi', 'slquydoi', 'số lượng', 'soluong', 'sl'])), None)
        if d_c and p_c and q_c:
            df_sales = df.copy()
            date_col = d_c
            prod_col = p_c
            qty_col = q_c
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng chi tiết có cột ngày, sản phẩm và số lượng", table_name="bán hàng chi tiết", available_tables=list(data.keys()))

    # Lọc dịp Tết 2026 (2026-02-10 đến 2026-02-26 theo lịch âm)
    df_sales['clean_date'] = clean_date(df_sales[date_col])
    df_sales = df_sales[(df_sales['clean_date'].dt.date >= pd.to_datetime("2026-02-10").date()) & 
                        (df_sales['clean_date'].dt.date <= pd.to_datetime("2026-02-26").date())]

    # Loại bỏ đơn hủy/trả
    status_col = next((c for c in df_sales.columns if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).lower().str.contains('hủy|huỷ|trả|cancel')]

    # Gom nhóm theo sản phẩm và tính tổng số lượng sạch
    df_sales['clean_qty'] = clean_num(df_sales[qty_col])
    grouped = df_sales.groupby(prod_col, as_index=False)['clean_qty'].sum()
    if grouped.empty:
        raise DataNotFoundError("Không có dữ liệu bán hàng trong kỳ để xếp hạng", table_name="bán hàng")

    # Áp dụng sắp xếp Điều 9: số lượng giảm dần, nếu bằng nhau thì tên tăng dần
    grouped = grouped.sort_values(by=['clean_qty', prod_col], ascending=[False, True])
    return str(grouped.iloc[0][prod_col])
```""",

    "multitable_join": """--- VÍ DỤ MINH HỌA: LIÊN KẾT ĐA BẢNG (JOIN SẢN PHẨM / HOẠT CHẤT / ĐƠN HÀNG) ---
Câu hỏi: "Thuốc có hoạt chất Natri clorid tháng này bán được bao nhiêu tiền?" (as_of_date = "2026-05-25")
```python
def solution(data):
    # 1. Tìm bảng danh mục thuốc chứa hoạt chất
    df_prod = next((df.copy() for name, df in data.items() if any('hoạt chất' in str(c).lower() for c in df.columns)), None)
    if df_prod is None:
        raise DataNotFoundError("Không tìm thấy bảng danh mục thuốc có cột hoạt chất", table_name="danh mục", available_tables=list(data.keys()))
    act_c = next((c for c in df_prod.columns if 'hoạt chất' in str(c).lower()), None)
    code_c = next((c for c in df_prod.columns if any(k in str(c).lower() for k in ['mã hàng', 'ma hang', 'mã hh', 'ma hh', 'mã thuốc', 'mã sp', 'sku'])), None)
    if not act_c or not code_c:
        raise DataNotFoundError("Thiếu cột hoạt chất hoặc mã hàng trong bảng danh mục thuốc", column_name="hoạt chất/mã", available_columns=df_prod.columns.tolist())
    matched = df_prod[df_prod[act_c].astype(str).str.lower().str.contains('natri clorid', na=False)]
    if matched.empty:
        return 0
    target_codes = set(matched[code_c].dropna().astype(str))

    # 2. Tìm bảng đơn hàng lọc ngày tháng 5/2026 và bỏ đơn hủy
    df_ord = next((df.copy() for name, df in data.items() if any(k in str(c).lower() for c in df.columns for k in ['thời gian', 'ngày', 'ngay ban']) and not any(k in name.lower() for k in ['nhap', 'chitiet'])), None)
    valid_orders = None
    if df_ord is not None:
        d_c = next((c for c in df_ord.columns if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian', 'ngay ban'])), None)
        if d_c:
            df_ord['clean_date'] = clean_date(df_ord[d_c])
            df_ord = df_ord[(df_ord['clean_date'].dt.year == 2026) & (df_ord['clean_date'].dt.month == 5) & (df_ord['clean_date'].dt.date <= pd.to_datetime("2026-05-25").date())]
            st_c = next((c for c in df_ord.columns if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)
            if st_c:
                df_ord = df_ord[~df_ord[st_c].astype(str).str.lower().str.contains('hủy|huỷ|trả')]
            oid_c = next((c for c in df_ord.columns if any(k in str(c).lower() for k in ['mã giao dịch', 'mã đơn', 'order id', 'mã phiếu'])), None)
            if oid_c:
                valid_orders = set(df_ord[oid_c].dropna().astype(str))

    # 3. Tìm bảng chi tiết bán hàng tính tổng tiền cho target_codes
    df_dt = next((df.copy() for name, df in data.items() if any(k in str(c).lower() for k in df.columns for k in ['thành tiền', 'thanh tien', 'tổng tiền', 'tong tien', 'tiền']) and not any(k in name.lower() for k in ['nhap', 'thuoc'])), None)
    if df_dt is None:
        raise DataNotFoundError("Không tìm thấy bảng chi tiết bán hàng", table_name="chi tiết bán", available_tables=list(data.keys()))
    amt_c = next((c for c in df_dt.columns if any(k in str(c).lower() for k in ['thành tiền', 'thanh tien', 'tổng tiền', 'tong tien', 'tiền'])), None)
    dt_code_c = next((c for c in df_dt.columns if any(k in str(c).lower() for k in ['mã hàng', 'ma hang', 'mã hh', 'ma hh', 'mã thuốc', 'mã sp'])), None)
    dt_oid_c = next((c for c in df_dt.columns if any(k in str(c).lower() for k in ['mã giao dịch', 'mã đơn', 'order id', 'mã phiếu'])), None)
    if not amt_c or not dt_code_c:
        raise DataNotFoundError("Thiếu cột thành tiền hoặc mã hàng trong bảng chi tiết bán", column_name="thành tiền/mã", available_columns=df_dt.columns.tolist())
    
    df_dt = df_dt[df_dt[dt_code_c].astype(str).isin(target_codes)]
    if valid_orders is not None and dt_oid_c:
        df_dt = df_dt[df_dt[dt_oid_c].astype(str).isin(valid_orders)]
    
    return int(round(clean_num(df_dt[amt_c]).sum()))
```""",

    "inventory_unit_conversion": """--- VÍ DỤ MINH HỌA: QUY ĐỔI ĐƠN VỊ TỒN KHO (HỘP CHẴN, VIÊN LẺ) ---
Câu hỏi: "Sản phẩm Hapacol 650 còn tồn bao nhiêu hộp chẵn và bao nhiêu viên lẻ?" (as_of_date = "2026-07-31")
```python
def solution(data):
    df_stock = None
    prod_col = None
    remain_col = None
    unit_col = None
    for name, df in data.items():
        cols = df.columns.tolist()
        r_c = next((c for c in cols if any(k in str(c).lower() for k in ['tồn cuối', 'số lượng tồn', 'tồn kho', 'soluongton', 'tồn thực'])), None)
        p_c = next((c for c in cols if any(k in str(c).lower() for k in ['tên hàng', 'sản phẩm', 'mặt hàng', 'product'])), None)
        if r_c and p_c:
            df_stock = df.copy()
            remain_col = r_c
            prod_col = p_c
            unit_col = next((c for c in cols if any(k in str(c).lower() for k in ['quy cách', 'đơn vị', 'đvt'])), None)
            break

    if df_stock is None:
        raise DataNotFoundError("Không tìm thấy bảng tồn kho trong dữ liệu", table_name="tồn kho", available_tables=list(data.keys()))

    matched = df_stock[df_stock[prod_col].astype(str).str.lower().str.contains('hapacol 650', na=False)]
    if matched.empty:
        raise DataNotFoundError("Không tìm thấy mặt hàng trong bảng tồn kho", column_name=prod_col)

    total_units = int(round(clean_num(matched[remain_col]).iloc[0]))
    packing_size = 100
    if unit_col and not matched[unit_col].isna().all():
        val = matched[unit_col].iloc[0]
        m = re.search(r'\d+', str(val))
        if m:
            packing_size = int(m.group(0))

    # Dùng divmod trả về [hộp chẵn, viên lẻ] kiểu list
    boxes, pills = divmod(total_units, packing_size)
    return [int(boxes), int(pills)]
```""",

    "time_series": """--- VÍ DỤ MINH HỌA: PHÂN TÍCH CHUỖI THỜI GIAN & SO SÁNH KỲ LIỀN TRƯỚC ---
Câu hỏi: "Doanh thu tháng này tăng hay giảm bao nhiêu phần trăm so với tháng trước?" (as_of_date = "2026-05-25")
```python
def solution(data):
    df_sales = None
    date_col = None
    amt_col = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        if any(k in n_clean for k in ['nhap', 'kho', 'chiphi', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            date_col = d_c
            amt_col = a_c
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền", table_name="bán hàng", available_tables=list(data.keys()))

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    df_sales['clean_amt'] = clean_num(df_sales[amt_col])

    # Kỳ chính: 2026-05-01 đến 2026-05-25 (25 ngày)
    # Kỳ đối chiếu theo Điều 2: 2026-04-01 đến 2026-04-25 (cùng 25 ngày)
    mask_curr = (df_sales['clean_date'].dt.date >= pd.to_datetime("2026-05-01").date()) & (df_sales['clean_date'].dt.date <= pd.to_datetime("2026-05-25").date())
    mask_prev = (df_sales['clean_date'].dt.date >= pd.to_datetime("2026-04-01").date()) & (df_sales['clean_date'].dt.date <= pd.to_datetime("2026-04-25").date())

    rev_curr = df_sales[mask_curr]['clean_amt'].sum()
    rev_prev = df_sales[mask_prev]['clean_amt'].sum()

    if rev_prev == 0:
        return 0.0

    pct_change = ((rev_curr - rev_prev) / rev_prev) * 100.0
    return round(float(pct_change), 2)
```""",

    "unanswerable_suspect": """--- VÍ DỤ MINH HỌA: KIỂM TRA THÔNG TIN THIẾU DỮ LIỆU ---
Câu hỏi: "Nhân viên nào có tay nghề cao nhất tiệm?" (as_of_date = "2026-07-31")
```python
def solution(data):
    # Dữ liệu bán hàng không có bảng hoặc cột nào về 'tay nghề' hoặc 'trình độ'
    has_skill = any('tay nghề' in str(c).lower() or 'trình độ' in str(c).lower() for df in data.values() for c in df.columns)
    if not has_skill:
        raise DataNotFoundError("Dữ liệu không có thông tin về tay nghề hoặc trình độ", column_name="tay nghề")
    return None
```""",
}


def retrieve_dynamic_few_shot(question: str, intent: str, entity_matches: Optional[List[Any]] = None) -> str:
    """
    Truy hồi ví dụ minh họa tối ưu nhất cho câu hỏi.
    Kết hợp phân loại intent và dấu hiệu thực thể liên kết.
    """
    q_low = question.lower()
    
    # 1. Nếu có hoạt chất hoặc tra cứu đa bảng
    if any(k in q_low for k in ["hoạt chất", "thành phần", "hoatchat", "kê đơn"]):
        example = EXEMPLAR_BANK.get("multitable_join")
    elif any(k in q_low for k in ["giá nhập bình quân", "giá một thùng", "giá bình quân", "nhập vào giá", "bình quân một thùng"]):
        example = EXEMPLAR_BANK.get("average_unit_price")
    elif any(k in q_low for k in ["bao nhiêu khách mua", "bn khach mua", "mấy khách mua", "bao nhiêu người mua", "đếm số khách"]):
        example = EXEMPLAR_BANK.get("customer_count_threshold")
    elif any(k in q_low for k in ["hộp chẵn", "viên lẻ", "thùng và chai", "tồn kho"]):
        example = EXEMPLAR_BANK.get("inventory_unit_conversion")
    elif any(k in q_low for k in ["tăng liên tục", "so với", "thay đổi bao nhiêu", "tăng trưởng"]):
        example = EXEMPLAR_BANK.get("time_series")
    elif any(k in q_low for k in ["bán chạy", "nhiều nhất", "top", "cao nhất", "ít nhất", "thấp nhất"]):
        example = EXEMPLAR_BANK.get("ranking_topk")
    elif any(k in q_low for k in ["công nợ", "cong no", "còn nợ", "con no", "tuổi nợ", "hạn nợ", "hạn trả", "phải thu", "khách nợ", "sổ nợ", "chưa trả"]):
        example = EXEMPLAR_BANK.get("cong_no")
    elif any(k in q_low for k in ["nhập hàng", "phiếu nhập", "tiền nhập", "nhap hang", "phieu nhap", "mua hàng", "cần trả ncc", "nhập kho"]):
        example = EXEMPLAR_BANK.get("purchase_import")
    elif any(k in q_low for k in ["%", "phần trăm", "tỉ lệ", "tỷ lệ"]):
        example = EXEMPLAR_BANK.get("rate_percentage")
    elif intent in EXEMPLAR_BANK:
        example = EXEMPLAR_BANK[intent]
    else:
        example = EXEMPLAR_BANK["aggregation"]

    return f"""==================== VÍ DỤ MINH HỌA PHÙ HỢP NHẤT ====================
{example}
"""
