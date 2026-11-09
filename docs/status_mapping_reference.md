# TÀI LIỆU THAM CHIẾU PHÂN LOẠI TRẠNG THÁI ĐƠN HÀNG VÀ TRẢ HÀNG

## (Status Mapping & Return Filter Reference Guide for Step 2)

**Trạng thái**: Đã phê duyệt chính thức (Approved)
**Mã commit triển khai**: `cba644f73e876ed5fb8a2ac0408b3afb07406b94`
**Mô-đun nguồn**: `src/datamate/ingestion_schema/cleaner.py`
**Bộ kiểm thử**: `tests/ingestion_schema/test_cleaner.py` (72 tests pass) & `scripts/test_generalization_5shops.py` (100% pass)

---

## 1. MỤC TIÊU & BỐI CẢNH NGHIỆP VỤ

Tài liệu này chuẩn hóa toàn bộ các quy tắc, phân cấp ngữ nghĩa, và thuật toán xử lý trạng thái đơn hàng (huỷ / trả / thành công / đang giao) phục vụ Bước 2 của hệ thống DataMate.

Mọi quy định trong tài liệu này bám sát tuyệt đối:

- **Quy tắc 1 (`rulebook.md`)**: Đơn tính vào doanh thu là đơn không huỷ và không trả hàng. Đơn có trả hàng, kể cả chỉ trả một phần, là đơn trả hàng: **bỏ cả đơn**. Đơn đang giao vẫn tính vào doanh thu. Đơn trả hàng **không phải** đơn huỷ.
- **Quy tắc 8 (`rulebook.md`)**: Đơn huỷ là đơn có trạng thái huỷ. Tính vào chỉ số đơn bị huỷ và tỉ lệ huỷ đơn.
- **Cam kết khái quát hóa (Generalization Guarantee)**: Tuyệt đối không rẽ nhánh theo `business_id`, tên shop, tên bảng/cột cụ thể. Nhận diện cột theo nội dung (content-based), phân loại bằng cụm từ ngữ nghĩa, xử lý giá trị lạ bằng ghi log cảnh báo (không tự đoán).

---

## 2. QUYẾT ĐỊNH PHÊ DUYỆT CHÍNH THỨC CỦA NGƯỜI DÙNG

Căn cứ phản hồi phê duyệt tại mốc `2026-11-08T09:56:46Z` và `2026-11-08T11:53:18Z`:

1. **Cấm tuyệt đối regex `"hoàn"` trần**:
   - Nghiêm cấm dùng biểu thức chính quy dạng `re.search(r"hoàn", ...)` hoặc `status.str.contains("hoàn")` vì sẽ làm sụp đổ hệ thống, xóa sổ nhầm **753,845 dòng doanh thu hợp lệ** (`Đã hoàn thành`, `Hoàn thành`).
   - Bắt buộc phân tách theo cụm ngữ nghĩa:
     * Cụm trả hàng: `"hoàn hàng"`, `"hoàn trả"`, `"hàng hoàn"`, `"hoàn tiền"` -> phân loại `loại (trả)`.
     * Cụm thành công: `"hoàn thành"`, `"hoàn tất"` -> phân loại `giữ`.
2. **"Không giao được"**:
   - Phân loại chính thức: **`loại (huỷ)`**.
   - Lý do: Đơn giao không thành công bị huỷ bỏ giao dịch, chưa thu tiền và không phát sinh doanh thu thực tế.
3. **"Đổi trả"**:
   - Phân loại chính thức: **`loại (trả)`** (ghi chú: đã kiểm chứng trên `biz_127`).
4. **Giá trị rỗng / null / blank**:
   - Phân loại chính thức: **`giữ`** (mặc định giao dịch hoạt động hợp lệ sau khi đã áp dụng Forward-Fill theo mã đơn).
5. **Giá trị lạ chưa từng thấy (Novel / Unseen Values)**:
   - Ghi log cảnh báo `WARNING: UNSEEN STATUS VALUE: '...' does not match any known semantic cluster`.
   - Trả về phân loại `"unknown"`. Tuyệt đối không tự đoán mò.

---

## 3. PHÂN CẤP NGỮ NGHĨA ƯU TIÊN NGHIÊM NGẶT (STRICT PRIORITY HIERARCHY)

Thuật toán phân loại trạng thái được cài đặt trong hàm `classify_status_value(raw_val)` tuân theo thứ tự ưu tiên 5 bậc:

```
[Đầu vào: raw_val]
       │
       ▼
 1. Chuẩn hóa chuỗi (NFKC, lowercase, xóa ký tự đặc biệt lạ, gộp space)
       │
       ├──> Nếu rỗng / null / "nan" / "none" / "rỗng" ──────────> GIỮ (Mặc định hợp lệ)
       │
       ├──> ƯU TIÊN 1: Chứa cụm từ TRẢ HÀNG (RETURN) ───────────> LOẠI (TRẢ)
       │    ("hoàn hàng", "hoàn trả", "hàng hoàn", "hoàn tiền",
       │     "đã hoàn hàng", "trả hàng", "đã trả hàng",
       │     "hàng trả về", "trả lại", "returned", "đổi trả")
       │
       ├──> ƯU TIÊN 2: Chứa cụm từ THÀNH CÔNG (SUCCESS) ─────────> GIỮ
       │    ("hoàn thành", "hoàn tất", "completed", "đã giao",
       │     "thành công", "xong", "đã xong", "đã lấy", "ok", "received")
       │
       ├──> ƯU TIÊN 3: Chứa cụm từ HUỶ ĐƠN (CANCEL) ─────────────> LOẠI (HUỶ)
       │    ("hủy", "huỷ", "đã hủy", "đã huỷ", "hủy đơn", "huỷ đơn",
       │     "đã hủy đơn", "khách hủy", "cancelled", "cancel", "không giao được")
       │
       ├──> ƯU TIÊN 4: Chứa cụm từ ĐANG GIAO / XỬ LÝ (PENDING) ───> GIỮ (Rule 1)
       │    ("đang giao", "đang vận chuyển", "đang xử lý", "đang gửi",
       │     "shipping", "chờ giao", "đang giao dịch", "đang giao hàng")
       │
       └──> ƯU TIÊN 5: Giá trị lạ chưa từng thấy ─────────────────> UNKNOWN (Log Warning)
```

### Tại sao thứ tự này triệt tiêu hoàn toàn bẫy chữ "hoàn"?

- Một trạng thái như `"Đã hoàn hàng"`:
  * Khi duyệt **Ưu tiên 1 (RETURN)**, hệ thống thấy khớp ngay cụm từ `"hoàn hàng"`. Kết quả trả về ngay lập tức là `loại (trả)`.
- Một trạng thái như `"Đã hoàn thành"`:
  * Khi duyệt **Ưu tiên 1 (RETURN)**, không chứa bất kỳ cụm nào trong danh mục trả hàng (`hoàn hàng`, `hoàn trả`...).
  * Chuyển sang **Ưu tiên 2 (SUCCESS)**, khớp ngay cụm từ `"hoàn thành"`. Kết quả trả về là `giữ`.
- Do đó, cả hai trường hợp đều được phân loại chính xác 100% mà không bao giờ gặp xung đột.

---

## 4. BẢNG TRA CỨU CHI TIẾT 42 GIÁ TRỊ TRẠNG THÁI TOÀN TẬP TRAIN

Bảng tổng hợp từ cuộc khảo sát 1,664,524 dòng trên 30 shop (`docs/diagnosis/status_values.md`):

| STT | Giá trị trạng thái gốc |   Phân loại chuẩn   | Nhóm ngữ nghĩa | Số dòng | Số đơn | Số shop | Ghi chú & Cột xuất hiện tiêu biểu                       |
| :-: | --------------------------- | :--------------------: | :---------------: | --------: | --------: | :------: | ------------------------------------------------------------- |
|  1  | `Đã hoàn thành`       |     **giữ**     |      SUCCESS      |   614,246 |   280,888 |    10    | `Trạng thái đơn hàng`, `Trạng thái`                |
|  2  | `xong`                    |     **giữ**     |      SUCCESS      |   151,990 |    96,670 |    4    | `Trạng thái`, `Ghi chú TT`                             |
|  3  | `Hoàn thành`            |     **giữ**     |      SUCCESS      |   139,599 |   111,408 |    5    | `Trạng thái`, `Status`                                  |
|  4  | `Đã giao`               |     **giữ**     |      SUCCESS      |   134,375 |    58,775 |    3    | `Trạng thái`, `Trạng thái đơn`                      |
|  5  | `đã lấy`               |     **giữ**     |      SUCCESS      |   132,925 |    86,723 |    5    | `trang_thai`, `Status`                                    |
|  6  | `completed`               |     **giữ**     |      SUCCESS      |   103,797 |    70,805 |    3    | `TinhTrang`, `Tình trạng đơn`                         |
|  7  | `đã xong`               |     **giữ**     |      SUCCESS      |    93,473 |    53,355 |    2    | `Status`, `Trạng thái`                                  |
|  8  | `Thành công`            |     **giữ**     |      SUCCESS      |    72,255 |    58,850 |    5    | `Trạng thái đơn hàng`                                  |
|  9  | `Xong`                    |     **giữ**     |      SUCCESS      |    53,893 |    21,386 |    1    | `Kết quả` (`biz_101`)                                   |
| 10 | `ok`                      |     **giữ**     |      SUCCESS      |    42,876 |    28,935 |    2    | `Trạng thái`                                              |
| 11 | `received`                |     **giữ**     |      SUCCESS      |       540 |       540 |    1    | `TinhTrang` (`biz_123`)                                   |
| 12 | `Đang giao hàng`        |     **giữ**     |      PENDING      |       124 |        68 |    6    | `Trạng thái`, `Status` (Rule 1: Đang giao vẫn tính)  |
| 13 | `Đang giao dịch`        |     **giữ**     |      PENDING      |       123 |        99 |    6    | `Trạng thái đơn hàng`                                  |
| 14 | `Đang vận chuyển`      |     **giữ**     |      PENDING      |       123 |        71 |    4    | `Trạng thái`, `Ghi chú TT`                             |
| 15 | `Đang xử lý`           |     **giữ**     |      PENDING      |        94 |        50 |    4    | `Trạng thái xử lý`                                      |
| 16 | `Đang giao`              |     **giữ**     |      PENDING      |        93 |        41 |    4    | `Kết quả`, `trang_thai`, `Status`                     |
| 17 | `đang gửi`              |     **giữ**     |      PENDING      |        47 |         2 |    3    | `Trạng thái đơn`, `Ghi chú TT`                       |
| 18 | `shipping`                |     **giữ**     |      PENDING      |        37 |        21 |    3    | `TinhTrang`, `Tình trạng`                               |
| 19 | `Chờ giao`               |     **giữ**     |      PENDING      |        15 |         0 |    1    | `Status` (`biz_110`)                                      |
| 20 | `Đã nhập hàng`        |     **giữ**     |     INGESTION     |     3,132 |         0 |    6    | Thuộc bảng nhập hàng/kho (Rule 5: bỏ phiếu huỷ)        |
| 21 | `Đang hoạt động`      |     **giữ**     |      ENTITY      |     2,040 |         0 |    8    | Thuộc bảng danh mục mặt hàng/đối tác                  |
| 22 | `<TRỐNG / NULL>`         |     **giữ**     |      DEFAULT      |   150,565 |       N/A |    30    | 110k dòng đã được FFill, số còn lại giữ mặc định |
| 23 | `Đã hủy`               | **loại (huỷ)** |      CANCEL      |    12,319 |     6,616 |    10    | `Trạng thái đơn hàng`, `Kết quả`                   |
| 24 | `hủy`                    | **loại (huỷ)** |      CANCEL      |     3,849 |     1,594 |    5    | `Trạng thái`, `Status`                                  |
| 25 | `Đã hủy đơn`         | **loại (huỷ)** |      CANCEL      |     2,957 |     1,823 |    4    | `trang_thai`, `Trạng thái đơn hàng`                  |
| 26 | `Huỷ đơn`              | **loại (huỷ)** |      CANCEL      |     2,074 |       962 |    3    | `Trạng thái xử lý`                                      |
| 27 | `hủy đơn`              | **loại (huỷ)** |      CANCEL      |     1,931 |     1,931 |    4    | `Trạng thái`                                              |
| 28 | `cancelled`               | **loại (huỷ)** |      CANCEL      |     1,753 |     1,404 |    3    | `TinhTrang`, `Tình trạng`                               |
| 29 | `khách hủy`             | **loại (huỷ)** |      CANCEL      |     1,675 |       223 |    3    | `Trạng thái`, `Ghi chú TT`                             |
| 30 | `cancel`                  | **loại (huỷ)** |      CANCEL      |     1,344 |       837 |    1    | `Trạng thái` (`biz_112`)                                |
| 31 | `Đã huỷ`               | **loại (huỷ)** |      CANCEL      |       486 |       486 |    1    | `Trạng thái`                                              |
| 32 | `Hủy`                    | **loại (huỷ)** |      CANCEL      |       330 |       146 |    1    | `Ghi chú TT`                                               |
| 33 | `Không giao được`     | **loại (huỷ)** |      CANCEL      |     2,345 |       804 |    4    | Quyết định người dùng: giao thất bại = huỷ bỏ       |
| 34 | `Đã hoàn hàng`        | **loại (trả)** |      RETURN      |     2,520 |     1,588 |    4    | Chứa "hoàn" nhưng là hoàn hàng!                         |
| 35 | `Đã trả hàng`         | **loại (trả)** |      RETURN      |     2,158 |     1,592 |    9    | `Trạng thái`, `Trạng thái xử lý`                    |
| 36 | `trả hàng`              | **loại (trả)** |      RETURN      |     1,801 |       715 |    6    | `Trạng thái`, `Ghi chú TT`                             |
| 37 | `Đổi trả`              | **loại (trả)** |      RETURN      |     1,555 |       876 |    4    | `Kết quả`, `Status` (Người dùng duyệt: loại trả)  |
| 38 | `Hoàn trả`              | **loại (trả)** |      RETURN      |       775 |       438 |    5    | `Trạng thái đơn hàng`, `Status`                      |
| 39 | `Trả hàng`              | **loại (trả)** |      RETURN      |       687 |       255 |    4    | `trang_thai`, `Trạng thái`                              |
| 40 | `hàng trả về`          | **loại (trả)** |      RETURN      |       576 |       374 |    4    | `Trạng thái đơn hàng`                                  |
| 41 | `trả lại`               | **loại (trả)** |      RETURN      |       443 |       289 |    2    | `Ghi chú TT`, `Trạng thái`                             |
| 42 | `returned`                | **loại (trả)** |      RETURN      |       416 |       143 |    3    | `TinhTrang`, `Tình trạng đơn`                         |

---

## 5. THUẬT TOÁN NHẬN DIỆN CỘT TRẠNG THÁI DỰA TRÊN NỘI DUNG (CONTENT-BASED)

Để không phụ thuộc vào tên cột cụ thể (như `Trạng thái`, `Kết quả`, `TinhTrang`, `trang_thai`), hàm `detect_status_columns(df)` áp dụng các tiêu chí khách quan:

1. **Kiểu dữ liệu**: Cột dạng chuỗi / object / category (loại bỏ kiểu số và kiểu ngày giờ).
2. **Loại trừ tên cột phi trạng thái**: Bỏ qua các cột có tên chứa các từ khóa khách hàng, nhà cung cấp, sản phẩm, phương thức thanh toán, ghi chú:
   ```regex
   NON_STATUS_NAME_PATTERNS = [
       r"tên\s*(sản\s*phẩm|hàng|sp|mặt\s*hàng)|product_name|item_name",
       r"(phương\s*thức|hình\s*thức)\s*thanh\s*toán|payment_method|pttt",
       r"tên\s*khách|customer_name",
       r"tên\s*nhân\s*viên|staff_name|người\s*bán",
       r"ghi\s*chú|note|diễn\s*giải|mô\s*tả|description",
       r"khách\s*hàng|customer|nhân\s*viên|staff",
   ]
   ```
3. **Độ đa dạng thấp (Low Cardinality)**:
   - Số giá trị phân biệt $N_{\text{unique}} \le 25$ HOẶC tỉ lệ $\frac{N_{\text{unique}}}{N_{\text{total}}} < 0.05$.
4. **Độ phủ ngữ nghĩa vòng đời đơn hàng (Semantic Cluster Coverage)**:
   - Chuẩn hóa các giá trị không null, tính tỉ lệ các giá trị chứa bất kỳ cụm từ nào thuộc 4 nhóm (`RETURN`, `SUCCESS`, `CANCEL`, `PENDING`).
   - Ngưỡng tối thiểu: `coverage >= 0.50` (50% giá trị hợp lệ thuộc về vòng đời đơn hàng).
5. **Xếp hạng ưu tiên**:
   - Các cột phát hiện được sắp xếp theo độ phủ giảm dần, sau đó theo số giá trị phân biệt tăng dần.

---

## 6. NHẬN DIỆN VÀ XỬ LÝ TRẢ HÀNG CẤP DÒNG (LINE-LEVEL RETURNS)

Trên 6 shop nhà thuốc/dược phẩm (`biz_119` đến `biz_124`), thông tin trả hàng không nằm ở cột trạng thái đơn mà được ghi nhận ở cấp từng mặt hàng/lô:

### A. Thuật toán nhận diện cột trả hàng cấp dòng (`detect_line_return_columns`)

- Tên cột khớp biểu thức:
  ```regex
  r"(số\s*lượng|sl|tiền|giá\s*trị)\s*(trả|hoàn|trả\s*lại|quy\s*đổi)"
  ```
- Cột có dữ liệu số (hơn 50% số dòng chuyển đổi thành số hợp lệ).
- Chứa ít nhất một giá trị phát sinh trả hàng: `(df[col] > 0).any()`.

### B. Quy tắc loại trừ nguyên đơn (Rule 1 Whole-Order Exclusion)

- **Quy tắc**: "Đơn có trả hàng, kể cả chỉ trả một phần, là đơn trả hàng: **bỏ cả đơn**".
- Nếu một đơn hàng gồm 10 dòng sản phẩm, chỉ cần 1 dòng có `Số lượng trả > 0`, toàn bộ 10 dòng của mã đơn đó phải bị loại bỏ hoàn toàn khỏi tập dữ liệu tính doanh thu.

### C. Công thức hợp tập hợp chống trừ hai lần (Set Union Math)

Để đảm bảo một đơn hàng vừa có trạng thái huỷ/trả vừa có dòng trả hàng không bị trừ hai lần hay gây sai lệch thống kê:

$$
\text{Excluded\_Orders} = \text{Set}(\text{Cancelled\_IDs}) \cup \text{Set}(\text{Status\_Return\_IDs}) \cup \text{Set}(\text{Line\_Return\_IDs})
$$

Hàm lọc dữ liệu:

```python
excluded = cancelled_ids | status_return_ids | line_return_ids
mask_keep = ~df[order_id_col].isin(excluded)
df_clean = df[mask_keep].copy()
```

---

## 7. BẰNG CHỨNG KIỂM CHỨNG KHÁI QUÁT HÓA (GENERALIZATION PROOF)

Đã kiểm chứng độc lập trên 5 shop đa dạng (`biz_101`, `biz_102`, `biz_114`, `biz_120`, `biz_123`) bằng script `scripts/test_generalization_5shops.py`:

1. **Đổi tên cột giả lập**:
   - `biz_101`: `Kết quả` -> `TinhTrang`
   - `biz_102`: `Trạng thái đơn hàng` -> `OrderStatus_Custom`
   - `biz_114`: `trang_thai` -> `TienTrinhDon`
   - `biz_120`: `Trạng thái` -> `Status_GiaoDich`
   - `biz_123`: `TinhTrang` -> `StateOfOrder`
   - **Kết quả**: 100% (5/5) cột đổi tên đều được thuật toán `detect_status_columns` nhận diện chính xác qua phân tích nội dung, hoàn toàn không cần biết trước tên cột.
2. **Tiêm 3 giá trị lạ chưa từng thấy**:
   - Giá trị tiêm: `"Đã bàn giao bưu tá"`, `"Người nhận từ chối nhận hàng"`, `"Xác nhận thất lạc hàng"`.
   - **Kết quả**: 100% giá trị lạ đều kích hoạt cảnh báo `WARNING: UNSEEN STATUS VALUE` và trả về danh mục `"unknown"`, hoàn toàn không suy đoán sai lệch.

---

## 8. HƯỚNG DẪN TÍCH HỢP CHO BƯỚC 2 (STEP 2 INTEGRATION INSTRUCTIONS)

Khi chuyển sang Bước 2 (Pipeline Execution):

1. **Mặc định an toàn**:
   - `clean_dataframe(df, filter_status=False)` giữ nguyên dữ liệu gốc cho các bài toán đếm đơn huỷ / khảo sát trạng thái.
   - Khi thực hiện truy vấn tính **Doanh thu** (Rule 1), gọi `filter_order_status(df, order_id_col=None)` hoặc `clean_dataframe(df, filter_status=True)`.
2. **Bộ nhớ đệm & Tốc độ**:
   - Các tập mã đơn huỷ / trả được tính toán một lần theo từng bảng và lưu trong bộ nhớ xử lý (hoặc SQLite Mirror index).
3. **Không chỉnh sửa ngoài phạm vi**:
   - Không tự ý thêm từ khóa mới vào `STATUS_SEMANTIC_CLUSTERS` trừ khi có giá trị lạ xuất hiện trong log và được người dùng phê duyệt thêm vào bảng tra cứu.
