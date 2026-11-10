# 📊 Báo cáo Đánh giá Toàn diện Hệ thống DataMate (Batch Evaluation Report)

- **Mô hình sử dụng (`model_id`)**: `Qwen/Qwen2.5-Coder-7B-Instruct`
- **Tổng số câu hỏi đánh giá**: `30` câu
- **Tổng thời gian thực thi**: `579.28s` (Trung bình `19.31s/câu`)

## 1. Tổng hợp Điểm Penalized Accuracy (PA)

| Chỉ số Đánh giá | Giá trị | Tỷ lệ / Ghi chú |
| :--- | :---: | :--- |
| **Penalized Accuracy (PA)** | **`+0.5333`** | Công thức: $(Correct - Wrong) / N$ |
| **Số câu Đúng (+1 điểm)** | `16` | `53.3%` |
| **Số câu Sai (-1 điểm)** | `0` | `0.0%` |
| **Số câu Từ chối / Abstain (0 điểm)** | `14` | `46.7%` |
| **Accuracy (khi trả lời)** | `100.0%` | $Correct / (Correct + Wrong)$ |
| **Coverage (Độ bao phủ trả lời)** | `53.3%` | $(Correct + Wrong) / N$ |

## 2. Phân rã Kết quả theo Kiểu Đáp án (Answer Type Breakdown)

| Kiểu đáp án (`type`) | Tổng số câu | Đúng (+1) | Sai (-1) | Abstain (0) | Điểm PA | Độ trễ TB (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `boolean` | 1 | 1 | 0 | 0 | **`+1.000`** | 4305.0 |
| `list` | 1 | 1 | 0 | 0 | **`+1.000`** | 47923.0 |
| `number` | 22 | 12 | 0 | 10 | **`+0.545`** | 15105.6 |
| `percent` | 4 | 0 | 0 | 4 | **`+0.000`** | 35996.2 |
| `string` | 1 | 1 | 0 | 0 | **`+1.000`** | 30641.0 |
| `unanswerable` | 1 | 1 | 0 | 0 | **`+1.000`** | 19359.0 |

## 3. Thống kê Nguyên nhân Lỗi & Lý do Từ chối (Error & Abstention Taxonomy)

| Nguyên nhân / Chẩn đoán | Số lượng câu |
| :--- | :---: |
| Runtime/Sanity Error: Câu hỏi đếm đơn bị hủy nhưng code không lọc điều kiện trạng thái hủy | `2` |
| Runtime/Sanity Error: Câu hỏi hỏi về công nợ / tiền trả nợ nhưng code chỉ tính doanh thu bán hàng chung mà không | `2` |
| Runtime/Sanity Error: Câu hỏi yêu cầu tính phần trăm (percent) nhưng code không thực hiện phép chia tỷ lệ | `2` |
| Runtime/Sanity Error: Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng / trung  | `2` |
| Runtime/Sanity Error: Câu hỏi hỏi số lượng món/sản phẩm bán được nhưng code lại cộng cột tiền mà không dùng cột  | `2` |
| Runtime/Sanity Error: Silent Zero: Kết quả phần trăm bằng 0 bất thường | `1` |
| Runtime/Sanity Error: Câu hỏi hỏi 'hôm qua / bữa qua' (as_of_date=2025-04-30) nhưng code lọc nhầm ngày hôm nay ( | `1` |
| Runtime/Sanity Error: Câu hỏi yêu cầu tính 'từ đầu tháng' (as_of_date=2025-03-15) nhưng code chỉ lọc duy nhất 1  | `1` |

---

## 4. Báo cáo Phân tích Chi tiết Từng Câu hỏi (Per-Question Analysis)

### 🛡️ Câu 1: `q_23401b31d098` (`biz_104`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: so don bi huy trong thang 5 nam 2025 la bao nhieu z
- **Ngữ cảnh**: `as_of_date = 2026-06-02` | `intent = cancelled_orders` | Khoảng ngày: `2025-05-01 -> 2025-05-31` (Tháng 5/2025)
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `66` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`21333.7ms` | Grounding=`140.6ms` | LLM=`0.0ms` | Thực thi=`1958.3ms` | Normalizer=`0.0ms` | Retry=`0`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Câu hỏi đếm đơn bị hủy nhưng code không lọc điều kiện trạng thái hủy`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi đếm đơn bị hủy nhưng code không lọc điều kiện trạng thái hủy`

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

### 🛡️ Câu 2: `q_5e92228fd206` (`biz_104`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: Tháng 6/2025 dthu bình quân mỗi đơn là bao nhiêu?
- **Câu hỏi mở rộng viết tắt**: Tháng 6/2025 doanh thu bình quân mỗi đơn là bao nhiêu?
- **Ngữ cảnh**: `as_of_date = 2026-06-02` | `intent = average_order_value` | Khoảng ngày: `2025-06-01 -> 2025-06-30` (Tháng 6/2025)
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=['DonHang_ChiTiet'] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `70712` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`0.0ms` | Grounding=`7.7ms` | LLM=`0.0ms` | Thực thi=`1475.4ms` | Normalizer=`0.1ms` | Retry=`0`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`0%` (Phạt `-0.25`)

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
def solution(data):
    sales_df = data.get('DonHang_ChiTiet')
    if sales_df is None:
        return 0
```
</details>

### ✅ Câu 3: `q_e0bed6042dfe` (`biz_104`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: Hôm qua doanh thu được bao nhiêu?
- **Ngữ cảnh**: `as_of_date = 2025-07-25` | `intent = aggregation` | Khoảng ngày: `2025-07-24 -> 2025-07-24` (Hôm qua (2025-07-24))
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `6405500` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `6405500` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`0.0ms` | Grounding=`6.3ms` | LLM=`0.0ms` | Thực thi=`538.8ms` | Normalizer=`0.5ms` | Retry=`0`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)

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

### ✅ Câu 4: `q_20cfa482235e` (`biz_105`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: coi giùm tháng 5/2026 cuwar hàng nhập nhiều tiền hàng nhất từ nhaf cung cấp nào
- **Câu hỏi mở rộng viết tắt**: coi giùm tháng 5/2026 cửa hàng nhập nhiều tiền hàng nhất từ nhà cung cấp nào
- **Ngữ cảnh**: `as_of_date = 2026-06-24` | `intent = purchase_import` | Khoảng ngày: `2026-05-01 -> 2026-05-31` (Tháng 5/2026)
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `Cty Thân Ngọc` (Kiểu: `string`) | **Đáp án Chuẩn (Gold)**: `Cty Thân Ngọc` (Kiểu: `string`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`29182.6ms` | Grounding=`4.3ms` | LLM=`0.0ms` | Thực thi=`1442.6ms` | Normalizer=`0.5ms` | Retry=`0`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)

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

### ✅ Câu 5: `q_c26a816e7c91` (`biz_105`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: Từ tháng 7/2025 qua tháng 8/2025 rồi tháng 9/2025, doanh thu có tăng liên tục không?
- **Ngữ cảnh**: `as_of_date = 2026-06-24` | `intent = time_series` | Khoảng ngày: `2025-07-01 -> 2025-07-31` (Tháng 7/2025)
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date', 'clean_amt']
- **Dự đoán (Pred)**: `False` (Kiểu: `boolean`) | **Đáp án Chuẩn (Gold)**: `False` (Kiểu: `boolean`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`0.0ms` | Grounding=`4.3ms` | LLM=`0.0ms` | Thực thi=`4297.8ms` | Normalizer=`0.4ms` | Retry=`0`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)

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

### ✅ Câu 6: `q_0794a9a26cef` (`biz_106`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: Cuối ngày hôm nay Bánh croissant còn mấy hộp chẵn, mấy cái lẻ?
- **Ngữ cảnh**: `as_of_date = 2026-09-14` | `intent = inventory_unit_conversion` | Khoảng ngày: `2026-09-14 -> 2026-09-14` (Hôm nay (2026-09-14))
- **Thực thể khớp (Entity Linking)**: `BÁNH CROISSANT`, `bánh`, `Bánh croissant`
- **Bảng & Cột truy vấn**: Bảng=['BaoCaoTonKho'] | Cột=[]
- **Dự đoán (Pred)**: `[13, 2]` (Kiểu: `list`) | **Đáp án Chuẩn (Gold)**: `[13, 2]` (Kiểu: `list`)
- **Độ tin cậy ($C$)**: `0.80` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`46932.5ms` | Grounding=`21.5ms` | LLM=`0.0ms` | Thực thi=`960.3ms` | Normalizer=`0.7ms` | Retry=`2`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)
- **🔄 Nhật ký Tự sửa lỗi (Self-Correction)**:
  - Vòng 1: Lỗi đầu vào `Không tìm thấy bảng tồn kho trong dữ liệu [Bảng tìm kiếm: 'tồn kho'] [Các bảng thực tế có sẵn: BaoCaoTonKho, t_01, DanhSachChiTietNhapHang, t_02, DanhSachDonViTinh, t_03, DanhSachHoaDon, t_04, DanhSachHoaDonChiTiet_1, t_05]` -> Kết quả thử lại: `Không tìm thấy cột cần thiết trong bảng tồn kho`
  - Vòng 2: Lỗi đầu vào `Không tìm thấy cột cần thiết trong bảng tồn kho` -> Kết quả thử lại: `Không tìm thấy cột cần thiết trong bảng tồn kho`

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

### ✅ Câu 7: `q_30d639b40362` (`biz_107`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: ee cho tôi bieets dthu bữa qua
- **Câu hỏi mở rộng viết tắt**: ee cho tôi bieets doanh thu bữa qua
- **Ngữ cảnh**: `as_of_date = 2025-10-25` | `intent = aggregation` | Khoảng ngày: `2025-10-24 -> 2025-10-24` (Hôm qua (2025-10-24))
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `4064300` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `4064300` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.80` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`5617.6ms` | Grounding=`12.6ms` | LLM=`0.0ms` | Thực thi=`1072.1ms` | Normalizer=`0.5ms` | Retry=`2`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)
- **🔄 Nhật ký Tự sửa lỗi (Self-Correction)**:
  - Vòng 1: Lỗi đầu vào `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền` -> Kết quả thử lại: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`
  - Vòng 2: Lỗi đầu vào `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền` -> Kết quả thử lại: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`

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

### ✅ Câu 8: `q_cea1b708d80a` (`biz_109`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: hôm nay kho còn tồn bao nhiu hộp Kem đánh răng P/S 180g lúc cuối ngày
- **Ngữ cảnh**: `as_of_date = 2026-08-05` | `intent = inventory_unit_conversion` | Khoảng ngày: `2026-08-05 -> 2026-08-05` (Hôm nay (2026-08-05))
- **Thực thể khớp (Entity Linking)**: `Kem đánh răng P/S 180g`, `Kem đánh răng P/S 180 g`
- **Bảng & Cột truy vấn**: Bảng=['DuLieuBanHang', 'DuLieuBanHang_BaoCaoTonKho', 'BaoCaoTonKho'] | Cột=['clean_date', 'Tồn cuối kỳ']
- **Dự đoán (Pred)**: `3` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `3` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.80` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`27016.6ms` | Grounding=`105.8ms` | LLM=`0.0ms` | Thực thi=`2904.3ms` | Normalizer=`0.5ms` | Retry=`2`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)
- **🔄 Nhật ký Tự sửa lỗi (Self-Correction)**:
  - Vòng 1: Lỗi đầu vào `Không tìm thấy cột ngày trong bảng BaoCaoTonKho [Bảng tìm kiếm: 'BaoCaoTonKho']` -> Kết quả thử lại: `Không tìm thấy cột ngày trong bảng BaoCaoTonKho [Bảng tìm kiếm: 'BaoCaoTonKho']`
  - Vòng 2: Lỗi đầu vào `Không tìm thấy cột ngày trong bảng BaoCaoTonKho [Bảng tìm kiếm: 'BaoCaoTonKho']` -> Kết quả thử lại: `Không tìm thấy cột ngày trong bảng BaoCaoTonKho [Bảng tìm kiếm: 'BaoCaoTonKho']`

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

### 🛡️ Câu 9: `q_4d7fc53fcc41` (`biz_111`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: tính đến hết ngày 19/08/2026, khách hàng còn nowj cửa hàng tổng cộng bao nhiêu tiền
- **Câu hỏi mở rộng viết tắt**: tính đến hết ngày 19/08/2026, khách hàng còn nợ cửa hàng tổng cộng bao nhiêu tiền
- **Ngữ cảnh**: `as_of_date = 2026-08-19` | `intent = cong_no` | Khoảng ngày: `2026-08-19 -> 2026-08-19` (Ngày 19/08/2026 (2026-08-19))
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `1828785` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`6950.0ms` | Grounding=`21.2ms` | LLM=`0.0ms` | Thực thi=`1658.5ms` | Normalizer=`0.0ms` | Retry=`0`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Câu hỏi hỏi về công nợ / tiền trả nợ nhưng code chỉ tính doanh thu bán hàng chung mà không xét bảng/cột thanh toán hoặc công nợ`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi hỏi về công nợ / tiền trả nợ nhưng code chỉ tính doanh thu bán hàng chung mà không xét bảng/cột thanh toán hoặc công nợ`

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

### ✅ Câu 10: `q_e390c3cb0b3b` (`biz_111`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: Doanh thu hôm nay là bao nhiêu?
- **Ngữ cảnh**: `as_of_date = 2025-09-28` | `intent = aggregation` | Khoảng ngày: `2025-09-28 -> 2025-09-28` (Hôm nay (2025-09-28))
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `10792500` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `10792500` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`0.0ms` | Grounding=`6.2ms` | LLM=`0.0ms` | Thực thi=`1484.6ms` | Normalizer=`0.5ms` | Retry=`0`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)

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

### ✅ Câu 11: `q_ebf285497536` (`biz_112`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: coi giumf tieenf bán Trà vải (L) tháng 3/2025 là bao nhiêu
- **Ngữ cảnh**: `as_of_date = 2026-07-31` | `intent = unanswerable_gate` | Khoảng ngày: `None -> None` ()
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=[]
- **Dự đoán (Pred)**: `None` (Kiểu: `unanswerable`) | **Đáp án Chuẩn (Gold)**: `None` (Kiểu: `unanswerable`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`19356.9ms` | Grounding=`0.0ms` | LLM=`0.0ms` | Thực thi=`0.0ms` | Normalizer=`0.0ms` | Retry=`0`

<details><summary><b>Xem mã nguồn Python sinh ra (Code)</b></summary>

```python
# Feasibility Gate: Unanswerable detected deterministically
```
</details>

### 🛡️ Câu 12: `q_f3d30bcd1487` (`biz_112`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: So số ly Sinh tố xoài (L) bán ra trong 30 ngày kể từ ngày 04/09/2025, ngày tăng giá lên 50.500đ, với 30 ngày ngay trước ngày đó: tăng hay giảm bao nhiêu % nhỉ?
- **Ngữ cảnh**: `as_of_date = 2026-07-31` | `intent = rate_percentage` | Khoảng ngày: `2025-09-04 -> 2025-10-03` (Kỳ chính: 30 ngày kể từ 2025-09-04 (đến 2025-10-03) | Kỳ đối chiếu: 30 ngày ngay trước 2025-09-04 (từ 2025-08-05 đến 2025-09-03)) | Kỳ so sánh: `2025-08-05 -> 2025-09-03` (30 ngày ngay trước 2025-09-04 (từ 2025-08-05 đến 2025-09-03))
- **Thực thể khớp (Entity Linking)**: `Sinh tố xoài (L)`, `sinh tố`, `bánh`, `Sinh tố xoài (M)`, `Sinh tố bơ (L)`, `Sinh tố bơ (M)`
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date', 'Thành tiền']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `7.04` (Kiểu: `percent`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`0.0ms` | Grounding=`90.5ms` | LLM=`0.0ms` | Thực thi=`5793.1ms` | Normalizer=`0.0ms` | Retry=`0`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Câu hỏi yêu cầu tính phần trăm (percent) nhưng code không thực hiện phép chia tỷ lệ`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi yêu cầu tính phần trăm (percent) nhưng code không thực hiện phép chia tỷ lệ`

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

### ✅ Câu 13: `q_083211e2c80c` (`biz_114`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: dthu quý 1/2025 của cửa hàng là bao nhiêu
- **Câu hỏi mở rộng viết tắt**: doanh thu quý 1/2025 của cửa hàng là bao nhiêu
- **Ngữ cảnh**: `as_of_date = 2026-06-21` | `intent = aggregation` | Khoảng ngày: `2025-01-01 -> 2025-03-31` (Quý 1/2025)
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `2496270800` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `2496270800` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.80` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`835.3ms` | Grounding=`19.8ms` | LLM=`0.0ms` | Thực thi=`472.7ms` | Normalizer=`0.5ms` | Retry=`2`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)
- **🔄 Nhật ký Tự sửa lỗi (Self-Correction)**:
  - Vòng 1: Lỗi đầu vào `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền` -> Kết quả thử lại: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`
  - Vòng 2: Lỗi đầu vào `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền` -> Kết quả thử lại: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`

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

### 🛡️ Câu 14: `q_d2b32a2c57d8` (`biz_115`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: tiền bán gas petrolimex 12kg tháng 2/2026 là bn
- **Câu hỏi mở rộng viết tắt**: tiền bán gas petrolimex 12kg tháng 2/2026 là bao nhiêu
- **Ngữ cảnh**: `as_of_date = 2026-05-16` | `intent = aggregation` | Khoảng ngày: `2026-02-01 -> 2026-02-28` (Tháng 2/2026)
- **Thực thể khớp (Entity Linking)**: `Gas Petrolimex 12kg`, `Gas Saigon Petro 12kg`
- **Bảng & Cột truy vấn**: Bảng=['Bảng kê phiếu giao hàng'] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `36868000` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`9052.4ms` | Grounding=`26.8ms` | LLM=`0.0ms` | Thực thi=`1491.0ms` | Normalizer=`0.0ms` | Retry=`2`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng / trung bình`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng / trung bình`
- **🔄 Nhật ký Tự sửa lỗi (Self-Correction)**:
  - Vòng 1: Lỗi đầu vào `Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng` -> Kết quả thử lại: `Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng`
  - Vòng 2: Lỗi đầu vào `Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng` -> Kết quả thử lại: `Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng`

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

### 🛡️ Câu 15: `q_4befa8de665c` (`biz_116`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: tháng 3/2026 có bao nhiêu bill bị huỷ
- **Ngữ cảnh**: `as_of_date = 2026-09-03` | `intent = cancelled_orders` | Khoảng ngày: `2026-03-01 -> 2026-03-31` (Tháng 3/2026)
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `26` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`12732.1ms` | Grounding=`18.8ms` | LLM=`0.0ms` | Thực thi=`950.3ms` | Normalizer=`0.0ms` | Retry=`0`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Câu hỏi đếm đơn bị hủy nhưng code không lọc điều kiện trạng thái hủy`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi đếm đơn bị hủy nhưng code không lọc điều kiện trạng thái hủy`

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

### 🛡️ Câu 16: `q_94fd5882870e` (`biz_118`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: Tỉ trọng của nhóm cát đá trong doanh thu tháng 8/2026 là bao nhiêu %?
- **Ngữ cảnh**: `as_of_date = 2026-09-10` | `intent = rate_percentage` | Khoảng ngày: `2026-08-01 -> 2026-08-31` (Tháng 8/2026)
- **Thực thể khớp (Entity Linking)**: `cát đá`
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `13.53` (Kiểu: `percent`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`22253.8ms` | Grounding=`58.4ms` | LLM=`0.0ms` | Thực thi=`4443.6ms` | Normalizer=`0.0ms` | Retry=`0`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Silent Zero: Kết quả phần trăm bằng 0 bất thường`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Silent Zero: Kết quả phần trăm bằng 0 bất thường`

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

### 🛡️ Câu 17: `q_9602e7257869` (`biz_118`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: Giá trị trung bình một đơn tuần trước là bao nhiêu?
- **Ngữ cảnh**: `as_of_date = 2026-05-05` | `intent = average_order_value` | Khoảng ngày: `2026-04-27 -> 2026-05-03` (Tuần trước (từ 2026-04-27 đến 2026-05-03))
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date', 'clean_amt']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `1371362` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`0.0ms` | Grounding=`21.7ms` | LLM=`0.0ms` | Thực thi=`2761.1ms` | Normalizer=`0.0ms` | Retry=`0`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng / trung bình`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Silent Zero: Kết quả tính toán bằng 0 bất thường cho câu hỏi doanh thu / số lượng / trung bình`

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

### ✅ Câu 18: `q_0a626a4c76d0` (`biz_119`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: Doanh thu trung bình trên một đơn tháng 3/2026 là bao nhiêu?
- **Ngữ cảnh**: `as_of_date = 2026-07-13` | `intent = aggregation` | Khoảng ngày: `2026-03-01 -> 2026-03-31` (Tháng 3/2026)
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `78584` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `78584` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`40895.7ms` | Grounding=`131.7ms` | LLM=`0.0ms` | Thực thi=`937.8ms` | Normalizer=`0.8ms` | Retry=`0`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)

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

### ✅ Câu 19: `q_bbf707d184af` (`biz_119`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: tổng tieenf hangf nhập vào tháng 1/2026 là bao nhiu
- **Câu hỏi mở rộng viết tắt**: tổng tiền hàng nhập vào tháng 1/2026 là bao nhiu
- **Ngữ cảnh**: `as_of_date = 2026-07-13` | `intent = purchase_import` | Khoảng ngày: `2026-01-01 -> 2026-01-31` (Tháng 1/2026)
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `104880600` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `104880600` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`0.0ms` | Grounding=`98.5ms` | LLM=`0.0ms` | Thực thi=`803.7ms` | Normalizer=`0.8ms` | Retry=`0`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)

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

### 🛡️ Câu 20: `q_5412252566a0` (`biz_120`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: Số gói bán được hqua là bao nhiêu, cộng mọi mặt hàng tính theo gói?
- **Câu hỏi mở rộng viết tắt**: Số gói bán được hôm qua là bao nhiêu, cộng mọi mặt hàng tính theo gói?
- **Ngữ cảnh**: `as_of_date = 2025-10-24` | `intent = aggregation` | Khoảng ngày: `2025-10-23 -> 2025-10-23` (Hôm qua (2025-10-23))
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `327` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`55172.3ms` | Grounding=`231.7ms` | LLM=`0.0ms` | Thực thi=`1416.7ms` | Normalizer=`0.0ms` | Retry=`0`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Câu hỏi hỏi số lượng món/sản phẩm bán được nhưng code lại cộng cột tiền mà không dùng cột số lượng`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi hỏi số lượng món/sản phẩm bán được nhưng code lại cộng cột tiền mà không dùng cột số lượng`

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

### ✅ Câu 21: `q_260318057077` (`biz_121`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: xem giúp tổng dthu quý 2/2026 là bn hả
- **Câu hỏi mở rộng viết tắt**: xem giúp tổng doanh thu quý 2/2026 là bao nhiêu hả
- **Ngữ cảnh**: `as_of_date = 2026-09-20` | `intent = aggregation` | Khoảng ngày: `2026-04-01 -> 2026-06-30` (Quý 2/2026)
- **Thực thể khớp (Entity Linking)**: `2,200`
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `797461200` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `797461200` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`33278.5ms` | Grounding=`123.5ms` | LLM=`0.0ms` | Thực thi=`1450.0ms` | Normalizer=`1.5ms` | Retry=`0`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)

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

### 🛡️ Câu 22: `q_f95fc735e3bc` (`biz_122`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: So số viên Strepsils Cool hộp 2 vỉ x 12 viên bán ra trong 30 ngày kể từ ngày 05/03/2026, ngày tăng giá lên 1.800đ, với 30 ngày ngay trước ngày đó: tăng hay giảm bao nhiêu %?
- **Ngữ cảnh**: `as_of_date = 2026-07-17` | `intent = rate_percentage` | Khoảng ngày: `2026-03-05 -> 2026-04-03` (Kỳ chính: 30 ngày kể từ 2026-03-05 (đến 2026-04-03) | Kỳ đối chiếu: 30 ngày ngay trước 2026-03-05 (từ 2026-02-03 đến 2026-03-04)) | Kỳ so sánh: `2026-02-03 -> 2026-03-04` (30 ngày ngay trước 2026-03-05 (từ 2026-02-03 đến 2026-03-04))
- **Thực thể khớp (Entity Linking)**: `Strepsils Cool hộp 2 vỉ x 12 viên`, `12,800`, `800`, `1,800`, `2,800`, `16,800`, `Enervon hộp 10 vỉ x 10 viên`, `Panadol Extra hộp 15 vỉ x 12 viên`, `Alaxan hộp 25 vỉ x 4 viên`, `Decolgen Forte hộp 30 vỉ x 4 viên`, `1,400`, `1,600`, `1,300`, `1,100`, `1,000`, `1,200`, `6,800`, `1,700`, `9,800`, `4,800`, `1,500`, `Eugica hộp 10 vỉ x 10 viên nang`, `Zyrtec 10mg hộp 1 vỉ x 10 viên`, `Clarityne 10mg hộp 1 vỉ x 10 viên`, `12,000`, `20,800`, `40,800`, `Panadol 500mg hộp 10 vỉ x 12 viên`, `Panadol 500mg Hộp 10 Vỉ X 12 Viên`, `PANADOL 500MG HỘP 10 VỈ X 12 VIÊN`, `Panadol Cảm Cúm hộp 15 vỉ x 12 viên`, `Panadol  Cảm Cúm hộp 15 vỉ x 12 viên`, `Tiffy Dey hộp 25 vỉ x 4 viên`, `Augmentin 625mg hộp 2 vỉ x 7 viên`, `Boganic Traphaco hộp 5 vỉ x 20 viên`, `Lorastad 10mg Stella hộp 10 vỉ x 10 viên`, `Lorastad 10mg Stella Hộp 10 Vỉ X 10 Viên`, `2,600`, `2,100`, `2,000`, `2,300`, `2,700`, `2,200`
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `-36.41` (Kiểu: `percent`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`41083.4ms` | Grounding=`1309.5ms` | LLM=`0.0ms` | Thực thi=`8780.7ms` | Normalizer=`0.0ms` | Retry=`0`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Câu hỏi yêu cầu tính phần trăm (percent) nhưng code không thực hiện phép chia tỷ lệ`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi yêu cầu tính phần trăm (percent) nhưng code không thực hiện phép chia tỷ lệ`

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

### 🛡️ Câu 23: `q_0983ff49fa23` (`biz_125`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: so dia ma heo nuong nuoc mam ban duoc trong thang 11/2025 la bao nhieu
- **Ngữ cảnh**: `as_of_date = 2026-05-11` | `intent = aggregation` | Khoảng ngày: `2025-11-01 -> 2025-11-30` (Tháng 11/2025)
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=['ban_hang'] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `67` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`5009.6ms` | Grounding=`9.1ms` | LLM=`0.0ms` | Thực thi=`2491.7ms` | Normalizer=`0.0ms` | Retry=`2`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Câu hỏi hỏi số lượng món/sản phẩm bán được nhưng code lại cộng cột tiền mà không dùng cột số lượng`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi hỏi số lượng món/sản phẩm bán được nhưng code lại cộng cột tiền mà không dùng cột số lượng`
- **🔄 Nhật ký Tự sửa lỗi (Self-Correction)**:
  - Vòng 1: Lỗi đầu vào `Không tìm thấy cột ngày hoặc cột thành tiền` -> Kết quả thử lại: `Không tìm thấy cột ngày hoặc cột thành tiền`
  - Vòng 2: Lỗi đầu vào `Không tìm thấy cột ngày hoặc cột thành tiền` -> Kết quả thử lại: `Không tìm thấy cột ngày hoặc cột thành tiền`

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

### ✅ Câu 24: `q_af1ea83ef086` (`biz_126`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: Cho hỏi tháng 1/2026 cửa hàng bán được tổng cộng bao nhiêu tiền?
- **Ngữ cảnh**: `as_of_date = 2026-06-06` | `intent = aggregation` | Khoảng ngày: `2026-01-01 -> 2026-01-31` (Tháng 1/2026)
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `571124700` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `571124700` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`15377.5ms` | Grounding=`19.1ms` | LLM=`0.0ms` | Thực thi=`1181.5ms` | Normalizer=`0.8ms` | Retry=`0`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)

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

### 🛡️ Câu 25: `q_507a4f0e1ee9` (`biz_127`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: bữa qua cuwar hàng bán đươc bn tiền vaayj
- **Câu hỏi mở rộng viết tắt**: bữa qua cửa hàng bán được bao nhiêu tiền vậy
- **Ngữ cảnh**: `as_of_date = 2025-04-30` | `intent = aggregation` | Khoảng ngày: `2025-04-29 -> 2025-04-29` (Hôm qua (2025-04-29))
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `25578000` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`11126.0ms` | Grounding=`17.8ms` | LLM=`0.0ms` | Thực thi=`4693.0ms` | Normalizer=`0.0ms` | Retry=`2`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Câu hỏi hỏi 'hôm qua / bữa qua' (as_of_date=2025-04-30) nhưng code lọc nhầm ngày hôm nay (dt.day == 30)`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi hỏi 'hôm qua / bữa qua' (as_of_date=2025-04-30) nhưng code lọc nhầm ngày hôm nay (dt.day == 30)`
- **🔄 Nhật ký Tự sửa lỗi (Self-Correction)**:
  - Vòng 1: Lỗi đầu vào `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền` -> Kết quả thử lại: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`
  - Vòng 2: Lỗi đầu vào `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền` -> Kết quả thử lại: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`

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

### 🛡️ Câu 26: `q_bc10815b2bf1` (`biz_127`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: Trong tháng 3/2026, tiền khách trả bớt nợ các đơn mua chịu được bao nhiêu?
- **Ngữ cảnh**: `as_of_date = 2026-07-28` | `intent = aggregation` | Khoảng ngày: `2026-03-01 -> 2026-03-31` (Tháng 3/2026)
- **Thực thể khớp (Entity Linking)**: `Lâm Thắng Thắng`
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `3478999` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`0.0ms` | Grounding=`45.0ms` | LLM=`0.0ms` | Thực thi=`1959.5ms` | Normalizer=`0.0ms` | Retry=`2`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Câu hỏi hỏi về công nợ / tiền trả nợ nhưng code chỉ tính doanh thu bán hàng chung mà không xét bảng/cột thanh toán hoặc công nợ`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi hỏi về công nợ / tiền trả nợ nhưng code chỉ tính doanh thu bán hàng chung mà không xét bảng/cột thanh toán hoặc công nợ`
- **🔄 Nhật ký Tự sửa lỗi (Self-Correction)**:
  - Vòng 1: Lỗi đầu vào `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền` -> Kết quả thử lại: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`
  - Vòng 2: Lỗi đầu vào `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền` -> Kết quả thử lại: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`

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

### ✅ Câu 27: `q_1eca36df20a0` (`biz_128`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: hôm qua cuwar hàng bán dc mấy đơn
- **Câu hỏi mở rộng viết tắt**: hôm qua cửa hàng bán được mấy đơn
- **Ngữ cảnh**: `as_of_date = 2025-06-07` | `intent = count_orders` | Khoảng ngày: `2025-06-06 -> 2025-06-06` (Hôm qua (2025-06-06))
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `53` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `53` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.90` | **Số vòng tự sửa lỗi (Self-Correction)**: `1`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`40114.1ms` | Grounding=`43.2ms` | LLM=`0.0ms` | Thực thi=`611.9ms` | Normalizer=`0.9ms` | Retry=`1`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)
- **🔄 Nhật ký Tự sửa lỗi (Self-Correction)**:
  - Vòng 1: Lỗi đầu vào `Không tìm thấy bảng bán hàng có cột mã đơn và cột ngày [Bảng tìm kiếm: 'bán hàng'] [Các bảng thực tế có sẵn: BaoCaoTonKho, t_01, DanhSachChiTietNhapHang, t_02, DanhSachHoaDon_[gộp: 04.2025, 05.2025, 06.2025...], DanhSachHoaDon, t_03, DanhSachHoaDonChiTiet, t_04, DanhSachHoaDonPhongBan]` -> Kết quả thử lại: `Thành công`

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

### ✅ Câu 28: `q_44ab47ab8b70` (`biz_128`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: Tổng tiền hàng nhập vào tháng 12/2025 là bao nhiêu?
- **Ngữ cảnh**: `as_of_date = 2026-09-07` | `intent = purchase_import` | Khoảng ngày: `2025-12-01 -> 2025-12-31` (Tháng 12/2025)
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `307548300` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `307548300` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `1.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`0.0ms` | Grounding=`36.5ms` | LLM=`0.0ms` | Thực thi=`669.2ms` | Normalizer=`0.7ms` | Retry=`0`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)

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

### ✅ Câu 29: `q_9de78b7e6230` (`biz_129`) — Điểm PA: `+1.0` (HOÀN TOÀN TRÙNG KHỚP (CORRECT - +1.0))
- **Câu hỏi gốc**: Doanh thu trung bình trên một đơn tháng 6/2026 là bao nhiêu?
- **Ngữ cảnh**: `as_of_date = 2026-08-14` | `intent = aggregation` | Khoảng ngày: `2026-06-01 -> 2026-06-30` (Tháng 6/2026)
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `532524` (Kiểu: `number`) | **Đáp án Chuẩn (Gold)**: `532524` (Kiểu: `number`)
- **Độ tin cậy ($C$)**: `0.80` | **Số vòng tự sửa lỗi (Self-Correction)**: `2`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`11409.5ms` | Grounding=`41.2ms` | LLM=`0.0ms` | Thực thi=`1770.4ms` | Normalizer=`1.0ms` | Retry=`2`
- **Độ bám dữ liệu (Grounding)**: Entity Coverage=`100%` (Phạt `-0.00`), Temporal Coverage=`100%` (Phạt `-0.00`)
- **🔄 Nhật ký Tự sửa lỗi (Self-Correction)**:
  - Vòng 1: Lỗi đầu vào `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền` -> Kết quả thử lại: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`
  - Vòng 2: Lỗi đầu vào `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền` -> Kết quả thử lại: `Không tìm thấy bảng bán hàng có cột ngày và cột thành tiền`

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

### 🛡️ Câu 30: `q_4cb3efa8bd01` (`biz_130`) — Điểm PA: `+0.0` (TỪ CHỐI TRẢ LỜI (ABSTAIN - 0.0))
- **Câu hỏi gốc**: tu dau thang nay den het hnay, dthu hon hay kem cung ky thang trc may %
- **Câu hỏi mở rộng viết tắt**: tu dau thang nay den het hôm nay doanh thu hon hay kem cung ky thang trước may %
- **Ngữ cảnh**: `as_of_date = 2025-03-15` | `intent = rate_percentage` | Khoảng ngày: `2025-03-01 -> 2025-03-15` (Kỳ chính: Tháng này (từ 2025-03-01 đến 2025-03-15) | Kỳ đối chiếu: Tháng trước kỳ so sánh (từ 2025-02-01 đến 2025-02-15)) | Kỳ so sánh: `2025-02-01 -> 2025-02-15` (Tháng trước kỳ so sánh (từ 2025-02-01 đến 2025-02-15))
- **Thực thể khớp (Entity Linking)**: *(Không có)*
- **Bảng & Cột truy vấn**: Bảng=[] | Cột=['clean_date']
- **Dự đoán (Pred)**: `None` (Kiểu: `abstain`) | **Đáp án Chuẩn (Gold)**: `38.88` (Kiểu: `percent`)
- **Độ tin cậy ($C$)**: `0.00` | **Số vòng tự sửa lỗi (Self-Correction)**: `0`
- **Thời gian từng pha (ms)**: Nạp dữ liệu=`55836.3ms` | Grounding=`11.0ms` | LLM=`0.0ms` | Thực thi=`4266.2ms` | Normalizer=`0.0ms` | Retry=`0`
- **⚠️ Nguyên nhân Lỗi / Lý do chặn**: `Câu hỏi yêu cầu tính 'từ đầu tháng' (as_of_date=2025-03-15) nhưng code chỉ lọc duy nhất 1 ngày hôm nay (so sánh một ngày với nửa tháng)`
- **🛡️ Lý do Cổng Abstention**: `Sanity Error: Câu hỏi yêu cầu tính 'từ đầu tháng' (as_of_date=2025-03-15) nhưng code chỉ lọc duy nhất 1 ngày hôm nay (so sánh một ngày với nửa tháng)`

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
