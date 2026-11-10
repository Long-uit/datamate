# 📊 Báo cáo Đánh giá Toàn diện Hệ thống DataMate (Batch Evaluation Report)

- **Mô hình sử dụng (`model_id`)**: `Qwen/Qwen2.5-Coder-7B-Instruct`
- **Tổng số câu hỏi đánh giá**: `30` câu
- **Tổng thời gian thực thi**: `6206.06s` (Trung bình `206.87s/câu`)

## 1. Tổng hợp Điểm Penalized Accuracy (PA)

| Chỉ số Đánh giá | Giá trị | Tỷ lệ / Ghi chú |
| :--- | :---: | :--- |
| **Penalized Accuracy (PA)** | **`-0.2000`** | Công thức: $(Correct - Wrong) / N$ |
| **Số câu Đúng (+1 điểm)** | `7` | `23.3%` |
| **Số câu Sai (-1 điểm)** | `13` | `43.3%` |
| **Số câu Từ chối / Abstain (0 điểm)** | `10` | `33.3%` |
| **Accuracy (khi trả lời)** | `35.0%` | $Correct / (Correct + Wrong)$ |
| **Coverage (Độ bao phủ trả lời)** | `66.7%` | $(Correct + Wrong) / N$ |

## 2. Phân rã Kết quả theo Kiểu Đáp án (Answer Type Breakdown)

| Kiểu đáp án (`type`) | Tổng số câu | Đúng (+1) | Sai (-1) | Abstain (0) | Điểm PA | Độ trễ TB (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `boolean` | 1 | 1 | 0 | 0 | **`+1.000`** | 122727.0 |
| `list` | 1 | 0 | 0 | 1 | **`+0.000`** | 824101.0 |
| `number` | 22 | 5 | 8 | 9 | **`-0.136`** | 267522.2 |
| `percent` | 4 | 0 | 4 | 0 | **`-1.000`** | 180405.2 |
| `string` | 1 | 0 | 1 | 0 | **`-1.000`** | 203850.0 |
| `unanswerable` | 1 | 1 | 0 | 0 | **`+1.000`** | 33601.0 |

## 3. Thống kê Nguyên nhân Lỗi & Lý do Từ chối (Error & Abstention Taxonomy)

| Nguyên nhân / Chẩn đoán | Số lượng câu |
| :--- | :---: |
| Runtime/Sanity Error: Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền | `5` |
| Runtime/Sanity Error: Không tìm thấy cột cần thiết trong bảng tồn kho | `1` |
| Runtime/Sanity Error: Không tìm thấy cột ngày trong bảng BaoCaoTonKho [Bảng tìm kiếm: 'BaoCaoTonKho'] | `1` |
| Runtime/Sanity Error: Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng | `1` |
| Runtime/Sanity Error: Không tìm thấy cột ngày hoặc cột thành tiền | `1` |

---

## 4. Báo cáo Phân tích Chi tiết Từng Câu hỏi (Per-Question Analysis)

### ❌ Câu 1: `q_23401b31d098` (`unknown`) — Điểm PA: `-1.0` (SAI LỆCH ĐÁP ÁN (WRONG - -1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `2932` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `66` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    order_col = None
    date_col = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        if any(k in n_clean for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        o_c = next((c for c in cols if any(k in str(c).lower() for k in ['mã đơn', 'ma don', 'mã hóa đơn', 'mã hd', 'order_id', 'order id', 'mã chứng từ', 'mã giao dịch', 'mã phiếu', 'mã'])), None)
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian', 'ngày tạo', 'ngày đặt'])), None)
        if o_c and d_c:
            df_sales = df.copy()
            order_col, date_col = o_c, d_c
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột mã đơn và ngày", table_name="bán hàng", available_tables=list(data.keys()))

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    mask = (df_sales['clean_date'].dt.year == 2025) & (df_sales['clean_date'].dt.month == 5)
    df_filtered = df_sales[mask]
    if df_filtered.empty:
        return 0
    return int(df_filtered[order_col].dropna().nunique())
```
</details>

### 🛡️ Câu 2: `q_5e92228fd206` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=['DonHang_ChiTiet'] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `70712` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    sales_df = data.get('DonHang_ChiTiet')
    if sales_df is None:
        return 0
```
</details>

### ❌ Câu 3: `q_e0bed6042dfe` (`unknown`) — Điểm PA: `-1.0` (SAI LỆCH ĐÁP ÁN (WRONG - -1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `6501500` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `6405500` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền")

    cols_s = df_sales.columns.tolist()
    date_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    amt_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|cancel', regex=True, na=False)]

    mask = (df_sales['clean_date'].dt.year == 2025) & (df_sales['clean_date'].dt.month == 7) & (df_sales['clean_date'].dt.day == 24)
    df_sales = df_sales[mask]

    if df_sales.empty:
        return 0
    return int(round(clean_num(df_sales[amt_col]).sum()))
```
</details>

### ❌ Câu 4: `q_20cfa482235e` (`unknown`) — Điểm PA: `-1.0` (SAI LỆCH ĐÁP ÁN (WRONG - -1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `Cty Vũ Sơn` (Kiểu: `string`) | **Đáp án Chuẩn (Gold)**: `Cty Thân Ngọc` (Kiểu: `string`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_nhap = next((df.copy() for name, df in data.items() if 'nhap' in re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())), None)
    if df_nhap is None:
        raise DataNotFoundError("Không tìm thấy bảng nhập hàng trong dữ liệu", table_name="nhập hàng", available_tables=list(data.keys()))

    cols = df_nhap.columns.tolist()
    d_c = next((c for c in cols if any(k in str(c).lower() for k in ['thời gian', 'ngày', 'date', 'ngaylap'])), None)
    amt_col = next((c for c in cols if any(k in str(c).lower() for k in ['cần trả ncc', 'tổng tiền', 'tong tien', 'thành tiền', 'giá trị']) and 'trả hàng' not in str(c).lower()), None)
    if not d_c or not amt_col:
        raise DataNotFoundError("Bảng nhập hàng thiếu cột ngày hoặc cột tiền", column_name="ngày/tiền", available_columns=cols)

    df_nhap['clean_date'] = clean_date(df_nhap[d_c])
    df_nhap = df_nhap[(df_nhap['clean_date'] >= pd.Timestamp('2026-05-01')) & (df_nhap['clean_date'] <= pd.Timestamp('2026-05-31 23:59:59'))]

    st_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'ghi chú', 'cancel'])), None)
    if st_c:
        df_nhap = df_nhap[~df_nhap[st_c].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|cancel')]

    top_ncc = df_nhap.groupby('Nhà cung cấp')[amt_col].sum().idxmax()
    return top_ncc
```
</details>

### ✅ Câu 5: `q_c26a816e7c91` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date', 'clean_amt']
- **Dự đoán (Pred)**: `False` (Kiểu: `boolean`) | **Đáp án Chuẩn (Gold)**: `False` (Kiểu: `boolean`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    dfs = [df for n, df in data.items() if 'SoBanHang' in n]
    if not dfs:
        raise DataNotFoundError("Bảng SoBanHang không tồn tại")

    df_sales = pd.concat(dfs, ignore_index=True)
    cols = df_sales.columns.tolist()
    d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    amt_col = next((c for c in cols if any(k in str(c).lower() for k in ['trị giá', 'thành tiền', 'tổng tiền', 'tiền']) and 'thuế' not in str(c).lower()), None)
    st_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status'])), None)

    df_sales['clean_date'] = clean_date(df_sales[d_c])
    df_sales['clean_amt'] = clean_num(df_sales[amt_col])

    if st_c:
        df_sales = df_sales[~df_sales[st_c].astype(str).str.contains(r'hủy|huỷ|huy|trả|tra|hoàn|hoan|cancel', case=False, na=False)]

    r7 = df_sales[(df_sales['clean_date'].dt.year == 2025) & (df_sales['clean_date'].dt.month == 7)]['clean_amt'].sum()
    r8 = df_sales[(df_sales['clean_date'].dt.year == 2025) & (df_sales['clean_date'].dt.month == 8)]['clean_amt'].sum()
    r9 = df_sales[(df_sales['clean_date'].dt.year == 2025) & (df_sales['clean_date'].dt.month == 9)]['clean_amt'].sum()

    return bool(r7 < r8 < r9)
```
</details>

### 🛡️ Câu 6: `q_0794a9a26cef` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=['BaoCaoTonKho'] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `[13, 2]` (Kiểu: `list`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Không tìm thấy cột cần thiết trong bảng tồn kho`
- **🛡️ Lý do Cổng Abstention**: `Runtime Error: Không tìm thấy cột cần thiết trong bảng tồn kho`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_stock = data.get('BaoCaoTonKho')
    if df_stock is None:
        raise DataNotFoundError("Không tìm thấy bảng tồn kho trong dữ liệu", table_name="BaoCaoTonKho")

    prod_col = next((c for c in df_stock.columns if any(k in str(c).lower() for k in ['tên hàng', 'sản phẩm', 'mặt hàng', 'product'])), None)
    remain_col = next((c for c in df_stock.columns if any(k in str(c).lower() for k in ['tồn cuối', 'số lượng tồn', 'tồn kho', 'soluongton', 'tồn thực'])), None)
    date_col = next((c for c in df_stock.columns if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    unit_col = next((c for c in df_stock.columns if any(k in str(c).lower() for k in ['quy cách', 'đơn vị', 'đvt'])), None)

    if prod_col is None or remain_col is None or date_col is None:
        raise DataNotFoundError("Không tìm thấy cột cần thiết trong bảng tồn kho")

    df_stock = filter_valid_sales(df_stock, date_col, '2026-09-14', '2026-09-14 23:59:59')

    matched = df_stock[(df_stock[prod_col].astype(str).str.lower() == 'bánh croissant') & (df_stock[date_col] == pd.to_datetime('2026-09-14').date())]
    if matched.empty:
        raise DataNotFoundError("Không tìm thấy mặt hàng trong bảng tồn kho", column_name=prod_col)

    total_units = int(round(clean_num(matched[remain_col]).iloc[0]))
    packing_size = 100
    if unit_col and not matched[unit_col].isna().all():
        val = matched[unit_col].iloc[0]
        m = re.search(r"\d+", str(val))
        if m:
            packing_size = int(m.group(0))

    boxes, pills = divmod(total_units, packing_size)
    return [int(boxes), int(pills)]
```
</details>

### 🛡️ Câu 7: `q_30d639b40362` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `4064300` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`
- **🛡️ Lý do Cổng Abstention**: `Runtime Error: Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền")

    cols_s = df_sales.columns.tolist()
    date_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    amt_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    if df_sales.empty:
        return 0

    mask = df_sales['clean_date'].dt.date == pd.to_datetime('2025-10-24').date()
    df_sales = df_sales[mask]

    if df_sales.empty:
        return 0
    return int(round(clean_num(df_sales[amt_col]).sum()))
```
</details>

### 🛡️ Câu 8: `q_cea1b708d80a` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=['DuLieuBanHang', 'DuLieuBanHang_BaoCaoTonKho'] | Cột=['clean_date', 'Tồn cuối kỳ']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `3` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Không tìm thấy cột ngày trong bảng BaoCaoTonKho [Bảng tìm kiếm: 'BaoCaoTonKho']`
- **🛡️ Lý do Cổng Abstention**: `Runtime Error: Không tìm thấy cột ngày trong bảng BaoCaoTonKho [Bảng tìm kiếm: 'BaoCaoTonKho']`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df = data.get('DuLieuBanHang_BaoCaoTonKho')
    if df is None:
        raise DataNotFoundError("Không tìm thấy bảng BaoCaoTonKho", table_name="BaoCaoTonKho")

    cols = df.columns.tolist()
    date_col = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    if date_col is None:
        raise DataNotFoundError("Không tìm thấy cột ngày trong bảng BaoCaoTonKho", table_name="BaoCaoTonKho")

    df['clean_date'] = clean_date(df[date_col])
    target_date = pd.to_datetime("2026-08-05").date()
    df = df[(df['clean_date'].dt.date == target_date)]

    prod_col = next((c for c in cols if any(k in str(c).lower() for k in ['hàng', 'tên món', 'tên hàng', 'sản phẩm', 'món', 'mặt hàng', 'product', 'item'])), None)
    if prod_col is None:
        raise DataNotFoundError("Không tìm thấy cột tên hàng trong bảng BaoCaoTonKho", table_name="BaoCaoTonKho")

    df = df[df[prod_col].astype(str).str.contains('Kem đánh răng P/S 180g', case=False, na=False)]
    if df.empty:
        return 0

    return int(round(clean_num(df['Tồn cuối kỳ']).sum()))
```
</details>

### ❌ Câu 9: `q_4d7fc53fcc41` (`unknown`) — Điểm PA: `-1.0` (SAI LỆCH ĐÁP ÁN (WRONG - -1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `7426334` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `1828785` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền")

    cols_s = df_sales.columns.tolist()
    date_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    amt_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|cancel', regex=True, na=False)]

    mask = (df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month == 8) & (df_sales['clean_date'].dt.day == 19)
    df_sales = df_sales[mask]

    if df_sales.empty:
        return 0
    return int(round(clean_num(df_sales[amt_col]).sum()))
```
</details>

### ❌ Câu 10: `q_e390c3cb0b3b` (`unknown`) — Điểm PA: `-1.0` (SAI LỆCH ĐÁP ÁN (WRONG - -1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `18748333` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `10792500` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    date_col = amt_col = status_col = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian', 'ngày tạo'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower() and 'giảm' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            date_col, amt_col = d_c, a_c
            status_col = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng'])), None)
            break

    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền", table_name="bán hàng")

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|tra|hoàn|hoan|cancel|return')]

    target_date = pd.to_datetime("2025-09-28").date()
    df_sales = df_sales[(df_sales['clean_date'].dt.date >= target_date) & (df_sales['clean_date'].dt.date <= target_date + pd.Timedelta(days=1))]
    if df_sales.empty:
        return 0

    return int(round(clean_num(df_sales[amt_col]).sum()))
```
</details>

### ✅ Câu 11: `q_ebf285497536` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `unanswerable`) | **Đáp án Chuẩn (Gold)**: `None` (Kiểu: `unanswerable`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Feasibility Gate: Unanswerable detected deterministically
```
</details>

### ❌ Câu 12: `q_f3d30bcd1487` (`unknown`) — Điểm PA: `-1.0` (SAI LỆCH ĐÁP ÁN (WRONG - -1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date', 'Thành tiền']
- **Dự đoán (Pred)**: `0` (Kiểu: `percent`) | **Đáp án Chuẩn (Gold)**: `7.04` (Kiểu: `percent`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_ord = None
    date_col = None
    prod_col = None
    for name, df in data.items():
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        p_c = next((c for c in cols if any(k in str(c).lower() for k in ['hàng', 'tên món', 'tên hàng', 'sản phẩm', 'món', 'mặt hàng', 'product', 'item'])), None)
        if d_c and p_c:
            df_ord = df.copy()
            date_col = d_c
            prod_col = p_c
            break

    if df_ord is None:
        raise DataNotFoundError("Không tìm thấy bảng có cột ngày và tên hàng", table_name="đơn hàng", available_tables=list(data.keys()))

    df_ord['clean_date'] = clean_date(df_ord[date_col])
    mask = (df_ord['clean_date'] >= pd.Timestamp('2025-09-04')) & (df_ord['clean_date'] <= pd.Timestamp('2025-09-04 23:59:59'))
    df_period = df_ord[mask]
    df_period = df_period[df_period[prod_col].astype(str).str.contains('Sinh tố xoài \(L\)', case=False, na=False)]
    total_sales = clean_num(df_period['Thành tiền']).sum()
    return int(round(total_sales))
```
</details>

### 🛡️ Câu 13: `q_083211e2c80c` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `2496270800` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`
- **🛡️ Lý do Cổng Abstention**: `Runtime Error: Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền")

    cols_s = df_sales.columns.tolist()
    date_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    amt_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    mask = (df_sales['clean_date'].dt.year == 2025) & (df_sales['clean_date'].dt.month >= 1) & (df_sales['clean_date'].dt.month <= 3)
    df_sales = df_sales[mask]

    if df_sales.empty:
        return 0
    return int(round(clean_num(df_sales[amt_col]).sum()))
```
</details>

### 🛡️ Câu 14: `q_d2b32a2c57d8` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=['Bảng kê phiếu giao hàng'] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `36868000` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    for name, df in data.items():
        if 'Bảng kê phiếu giao hàng' in name:
            df_sales = df.copy()
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền")

    cols_s = df_sales.columns.tolist()
    date_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    amt_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
    item_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['hàng', 'tên món', 'tên hàng', 'sản phẩm', 'mặt hàng'])), None)

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    mask = (df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month == 2)
    df_sales = df_sales[mask]

    if item_col:
        mask_prod = df_sales[item_col].astype(str).str.contains('gas petrolimex 12kg', case=False, na=False)
        df_sales = df_sales[mask_prod]

    if df_sales.empty:
        return 0
    return int(round(clean_num(df_sales[amt_col]).sum()))
```
</details>

### ❌ Câu 15: `q_4befa8de665c` (`unknown`) — Điểm PA: `-1.0` (SAI LỆCH ĐÁP ÁN (WRONG - -1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `1219` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `26` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    order_col = None
    date_col = None
    status_col = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        if any(k in n_clean for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        o_c = next((c for c in cols if any(k in str(c).lower() for k in ['mã đơn', 'ma don', 'mã hoá đơn', 'mã hd', 'order_id', 'order id', 'mã chứng từ', 'mã giao dịch', 'mã phiếu', 'mã'])), None)
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian', 'ngày tạo', 'ngày đặt'])), None)
        st_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng', 'xử lý'])), None)
        if o_c and d_c and st_c:
            df_sales = df.copy()
            order_col, date_col, status_col = o_c, d_c, st_c
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột mã đơn, ngày và trạng thái", table_name="bán hàng", available_tables=list(data.keys()))

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    mask = (df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month == 3)
    df_filtered = df_sales[mask]
    if df_filtered.empty:
        return 0
    return int(df_filtered[order_col].dropna().nunique())
```
</details>

### ❌ Câu 16: `q_94fd5882870e` (`unknown`) — Điểm PA: `-1.0` (SAI LỆCH ĐÁP ÁN (WRONG - -1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `0` (Kiểu: `percent`) | **Đáp án Chuẩn (Gold)**: `13.53` (Kiểu: `percent`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_ord = None
    date_col = None
    prod_col = None
    amt_col = None
    for name, df in data.items():
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        p_c = next((c for c in cols if any(k in str(c).lower() for k in ['hàng', 'tên món', 'tên hàng', 'sản phẩm', 'món', 'mặt hàng', 'product', 'item'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'amount', 'giá', 'price'])), None)
        if d_c and p_c and a_c:
            df_ord = df.copy()
            date_col = d_c
            prod_col = p_c
            amt_col = a_c
            break

    if df_ord is None:
        raise DataNotFoundError("Không tìm thấy bảng có cột ngày, tên hàng và thành tiền", table_name="đơn hàng", available_tables=list(data.keys()))

    df_ord['clean_date'] = clean_date(df_ord[date_col])
    mask = (df_ord['clean_date'] >= pd.Timestamp('2026-08-01')) & (df_ord['clean_date'] <= pd.Timestamp('2026-08-31 23:59:59'))
    df_period = df_ord[mask]
    if df_period.empty:
        return 0

    df_cátđá = df_period[df_period[prod_col] == 'cát đá']
    total_revenue = clean_num(df_period[amt_col]).sum()
    cátđá_revenue = clean_num(df_cátđá[amt_col]).sum()
    ratio = (cátđá_revenue / total_revenue) * 100
    return int(round(ratio))
```
</details>

### ❌ Câu 17: `q_9602e7257869` (`unknown`) — Điểm PA: `-1.0` (SAI LỆCH ĐÁP ÁN (WRONG - -1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date', 'clean_amt']
- **Dự đoán (Pred)**: `0` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `1371362` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.95` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    sales_dfs = []
    for name, df in data.items():
        n_low = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        if any(k in n_low for k in ['nhap', 'kho', 'chiphi', 'ncc', 'thekho', 'banggia', 'danhmuc', 'quydoi']):
            continue
        cols = [str(c).lower() for c in df.columns]
        if any(k in c for c in cols for k in ['ngày', 'date', 'thời gian']) or any(k in c for c in cols for k in ['tiền', 'doanh thu', 'trị giá']):
            sales_dfs.append(df.copy())

    if not sales_dfs:
        return 0
    df_sales = pd.concat(sales_dfs, ignore_index=True) if len(sales_dfs) > 1 else sales_dfs[0]

    cols = df_sales.columns.tolist()
    d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian', 'ngaylap', 'ngày đặt'])), None)
    amt_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tongtien', 'tiền bán', 'doanh thu', 'trị giá', 'tiền']) and 'thuế' not in str(c).lower() and 'giá lẻ' not in str(c).lower() and 'đơn giá' not in str(c).lower()), None)
    st_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng', 'xử lý'])), None)

    if not d_c or not amt_c:
        return 0

    df_sales['clean_date'] = clean_date(df_sales[d_c])
    if st_c:
        df_sales = df_sales[~df_sales[st_c].astype(str).str.contains(r'hủy|huỷ|huy|trả|tra|hoàn|hoan|cancel|return', case=False, na=False)]

    mask = (df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month == 5) & (df_sales['clean_date'].dt.day >= 27) & (df_sales['clean_date'].dt.day <= 3)
    df_period = df_sales[mask]
    if df_period.empty:
        return 0

    df_period['clean_amt'] = clean_num(df_period[amt_c])
    aov = df_period['clean_amt'].mean()
    return int(round(aov))
```
</details>

### ✅ Câu 18: `q_0a626a4c76d0` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `78584` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `78584` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền")

    cols_s = df_sales.columns.tolist()
    date_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    amt_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|cancel', regex=True, na=False)]

    mask = (df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month == 3)
    df_sales = df_sales[mask]

    if df_sales.empty:
        return 0
    return int(round(clean_num(df_sales[amt_col]).sum() / len(df_sales)))
```
</details>

### ✅ Câu 19: `q_bbf707d184af` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `104880600` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `104880600` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_nhap = next((df for name, df in data.items() if 'nhap' in name.lower() and 'chitiet' not in name.lower()), None)
    if df_nhap is None:
        raise DataNotFoundError("Không tìm thấy bảng nhập hàng trong dữ liệu", table_name="nhập hàng", available_tables=list(data.keys()))

    cols = df_nhap.columns.tolist()
    d_c = next((c for c in cols if any(k in str(c).lower() for k in ['thời gian', 'ngày', 'date', 'ngaylap'])), None)
    amt_col = next((c for c in cols if any(k in str(c).lower() for k in ['cần trả ncc', 'tổng tiền', 'tong tien', 'thành tiền', 'giá trị']) and 'trả hàng' not in str(c).lower()), None)
    if not d_c or not amt_col:
        raise DataNotFoundError("Bảng nhập hàng thiếu cột ngày hoặc cột tiền", column_name="ngày/tiền", available_columns=cols)

    df_nhap['clean_date'] = clean_date(df_nhap[d_c])
    df_nhap = df_nhap[(df_nhap['clean_date'] >= pd.Timestamp('2026-01-01')) & (df_nhap['clean_date'] <= pd.Timestamp('2026-01-31 23:59:59'))]

    st_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'ghi chú', 'cancel'])), None)
    if st_c:
        df_nhap = df_nhap[~df_nhap[st_c].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|cancel')]

    return int(round(clean_num(df_nhap[amt_col]).sum()))
```
</details>

### ❌ Câu 20: `q_5412252566a0` (`unknown`) — Điểm PA: `-1.0` (SAI LỆCH ĐÁP ÁN (WRONG - -1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `8807500` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `327` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        amt_col = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and amt_col:
            df_sales = df.copy()
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền")

    cols_s = df_sales.columns.tolist()
    date_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    amt_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|cancel', regex=True, na=False)]

    mask = (df_sales['clean_date'].dt.date == pd.to_datetime('2025-10-23').date())
    df_sales = df_sales[mask]

    return int(round(clean_num(df_sales[amt_col]).sum()))
```
</details>

### ❌ Câu 21: `q_260318057077` (`unknown`) — Điểm PA: `-1.0` (SAI LỆCH ĐÁP ÁN (WRONG - -1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `803177000` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `797461200` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền")

    cols_s = df_sales.columns.tolist()
    date_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    amt_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|cancel', regex=True, na=False)]

    mask = (df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month >= 4) & (df_sales['clean_date'].dt.month <= 6)
    df_sales = df_sales[mask]

    if df_sales.empty:
        return 0
    return int(round(clean_num(df_sales[amt_col]).sum()))
```
</details>

### ❌ Câu 22: `q_f95fc735e3bc` (`unknown`) — Điểm PA: `-1.0` (SAI LỆCH ĐÁP ÁN (WRONG - -1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `0` (Kiểu: `percent`) | **Đáp án Chuẩn (Gold)**: `-36.41` (Kiểu: `percent`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_dct = None
    date_col = None
    prod_col = None
    amt_col = None
    for name, df in data.items():
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        p_c = next((c for c in cols if any(k in str(c).lower() for k in ['hàng', 'tên món', 'tên hàng', 'sản phẩm', 'món', 'mặt hàng', 'product', 'item'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['số lượng', 'sl', 'quantity'])), None)
        if d_c and p_c and a_c:
            df_dct = df.copy()
            date_col = d_c
            prod_col = p_c
            amt_col = a_c
            break

    if df_dct is None:
        raise DataNotFoundError("Không tìm thấy bảng có cột ngày, tên hàng và số lượng", table_name="đơn hàng", available_tables=list(data.keys()))

    df_dct['clean_date'] = clean_date(df_dct[date_col])
    mask = (df_dct['clean_date'] >= pd.Timestamp('2026-03-05')) & (df_dct['clean_date'] <= pd.Timestamp('2026-03-05 23:59:59'))
    df_period = df_dct[mask]
    df_period = df_period[df_period[prod_col] == 'Strepsils Cool hộp 2 vỉ x 12 viên']
    total_amount = clean_num(df_period[amt_col]).sum()
    return int(round(total_amount))
```
</details>

### 🛡️ Câu 23: `q_0983ff49fa23` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=['ban_hang'] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `67` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Không tìm thấy cột ngày hoặc cột thành tiền`
- **🛡️ Lý do Cổng Abstention**: `Runtime Error: Không tìm thấy cột ngày hoặc cột thành tiền`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = data.get('ban_hang')
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng")

    cols = df_sales.columns.tolist()
    date_col = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    amt_col = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
    if date_col and amt_col:
        df_sales['clean_date'] = clean_date(df_sales[date_col])
        mask = (df_sales['clean_date'].dt.year == 2025) & (df_sales['clean_date'].dt.month == 11)
        df_sales = df_sales[mask]
        return int(round(clean_num(df_sales[amt_col]).sum()))
    else:
        raise DataNotFoundError("Không tìm thấy cột ngày hoặc cột thành tiền")
```
</details>

### ✅ Câu 24: `q_af1ea83ef086` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `571124700` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `571124700` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền")

    cols_s = df_sales.columns.tolist()
    date_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    amt_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|cancel', regex=True, na=False)]

    mask = (df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month == 1)
    df_sales = df_sales[mask]

    if df_sales.empty:
        return 0
    return int(round(clean_num(df_sales[amt_col]).sum()))
```
</details>

### 🛡️ Câu 25: `q_507a4f0e1ee9` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `25578000` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`
- **🛡️ Lý do Cổng Abstention**: `Runtime Error: Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền")

    cols_s = df_sales.columns.tolist()
    date_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    amt_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)

    df_sales['clean_date'] = clean_date(df_sales[date_col])

    mask = (df_sales['clean_date'].dt.year == 2025) & (df_sales['clean_date'].dt.month == 4) & (df_sales['clean_date'].dt.day == 30)
    df_sales = df_sales[mask]

    if df_sales.empty:
        return 0
    return int(round(clean_num(df_sales[amt_col]).sum()))
```
</details>

### 🛡️ Câu 26: `q_bc10815b2bf1` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `3478999` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`
- **🛡️ Lý do Cổng Abstention**: `Runtime Error: Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        amt_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and amt_c:
            df_sales = df.copy()
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền")

    cols_s = df_sales.columns.tolist()
    date_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    amt_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|cancel', regex=True, na=False)]

    mask = (df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month == 3)
    df_sales = df_sales[mask]

    if df_sales.empty:
        return 0
    return int(round(clean_num(df_sales[amt_col]).sum()))
```
</details>

### ✅ Câu 27: `q_1eca36df20a0` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `53` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `53` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.90` | **Số vòng tự sửa lỗi (Self-Correction)**: `1`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    order_col = date_col = None
    for name, df in data.items():
        n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
        if any(k in n_clean for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho', 'khachhang']):
            continue
        cols = df.columns.tolist()
        o_c = next((c for c in cols if any(k in str(c).lower() for k in ['mã đơn', 'ma don', 'mã hóa đơn', 'mã hd', 'order_id', 'order id', 'mã chứng từ', 'mã giao dịch'])), None)
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian', 'ngày tạo'])), None)
        if o_c and d_c:
            df_sales = df.copy()
            order_col, date_col = o_c, d_c
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột mã đơn và cột ngày", table_name="bán hàng", available_tables=list(data.keys()))

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    # Mặc định loại bỏ đơn hủy/trả hàng trừ khi được hỏi rõ (diacritic-insensitive)
    cols_s = df_sales.columns.tolist()
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng', 'xử lý'])), None)
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|tra|cancel|return')]

    # Lọc theo kỳ câu hỏi yêu cầu (hôm qua)
    mask = (df_sales['clean_date'] >= pd.Timestamp('2025-06-06')) & (df_sales['clean_date'] <= pd.Timestamp('2025-06-06 23:59:59'))
    df_filtered = df_sales[mask]
    if df_filtered.empty:
        return 0
    # BẮT BUỘC dùng nunique() thay vì len() vì một đơn hàng có thể có nhiều dòng sản phẩm
    return int(df_filtered[order_col].dropna().nunique())
```
</details>

### ✅ Câu 28: `q_44ab47ab8b70` (`unknown`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `307548300` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `307548300` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_nhap = next((df for name, df in data.items() if 'nhap' in name.lower() and 'chitiet' not in name.lower()), None)
    if df_nhap is None:
        raise DataNotFoundError("Không tìm thấy bảng nhập hàng trong dữ liệu", table_name="nhập hàng", available_tables=list(data.keys()))

    cols = df_nhap.columns.tolist()
    d_c = next((c for c in cols if any(k in str(c).lower() for k in ['thời gian', 'ngày', 'date', 'ngaylap'])), None)
    a_c = next((c for c in cols if any(k in str(c).lower() for k in ['cần trả ncc', 'tổng tiền', 'tong tien', 'thành tiền', 'giá trị']) and 'trả hàng' not in str(c).lower()), None)
    if not d_c or not a_c:
        raise DataNotFoundError("Bảng nhập hàng thiếu cột ngày hoặc cột tiền", column_name="ngày/tiền", available_columns=cols)

    df_nhap['clean_date'] = clean_date(df_nhap[d_c])
    df_nhap = df_nhap[(df_nhap['clean_date'] >= pd.Timestamp("2025-12-01")) & (df_nhap['clean_date'] <= pd.Timestamp("2025-12-31 23:59:59"))]

    st_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'ghi chú', 'cancel'])), None)
    if st_c:
        df_nhap = df_nhap[~df_nhap[st_c].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|cancel')]

    return int(round(clean_num(df_nhap[a_c]).sum()))
```
</details>

### 🛡️ Câu 29: `q_9de78b7e6230` (`unknown`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `532524` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`
- **🛡️ Lý do Cổng Abstention**: `Runtime Error: Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_sales = None
    for name, df in data.items():
        if any(k in str(name).lower() for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
            continue
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
        if d_c and a_c:
            df_sales = df.copy()
            break
    if df_sales is None:
        raise DataNotFoundError("Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền")

    cols_s = df_sales.columns.tolist()
    date_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
    amt_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)

    df_sales['clean_date'] = clean_date(df_sales[date_col])
    status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'tt', 'ghi chú'])), None)
    if status_col:
        df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains(r'hủy|huỷ|huy|trả|cancel', regex=True, na=False)]

    mask = (df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month == 6)
    df_sales = df_sales[mask]

    if df_sales.empty:
        return 0
    return int(round(clean_num(df_sales[amt_col]).sum() / len(df_sales)))
```
</details>

### ❌ Câu 30: `q_4cb3efa8bd01` (`unknown`) — Điểm PA: `-1.0` (SAI LỆCH ĐÁP ÁN (WRONG - -1.0))
- **Câu hỏi gốc**: 
- **Ngữ cảnh**: `as_of_date = ` | `intent = ` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `-94` (Kiểu: `percent`) | **Đáp án Chuẩn (Gold)**: `38.88` (Kiểu: `percent`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    df_ord = None
    date_col = None
    amt_col = None
    for name, df in data.items():
        cols = df.columns.tolist()
        d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'thời gian'])), None)
        a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'amount', 'tổng tiền'])), None)
        if d_c and a_c:
            df_ord = df.copy()
            date_col = d_c
            amt_col = a_c
            break

    if df_ord is None:
        raise DataNotFoundError("Không tìm thấy bảng có cột ngày và thành tiền", table_name="đơn hàng", available_tables=list(data.keys()))

    df_ord['clean_date'] = clean_date(df_ord[date_col])
    mask_current = (df_ord['clean_date'] >= pd.Timestamp('2025-03-15')) & (df_ord['clean_date'] <= pd.Timestamp('2025-03-15 23:59:59'))
    mask_previous = (df_ord['clean_date'] >= pd.Timestamp('2025-02-01')) & (df_ord['clean_date'] <= pd.Timestamp('2025-02-15 23:59:59'))
    total_current = clean_num(df_ord.loc[mask_current, amt_col]).sum()
    total_previous = clean_num(df_ord.loc[mask_previous, amt_col]).sum()

    if total_previous == 0:
        return 0

    percentage_increase = ((total_current - total_previous) / total_previous) * 100
    return int(round(percentage_increase))
```
</details>
