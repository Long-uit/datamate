# Báo Cáo Công Việc Phase 2 — Long (AI Architect & Model Lead)

- **Ngày thực hiện**: 03/11/2026
- **Người thực hiện**: Long (AI Architect & Model Lead)
- **Giai đoạn**: Phase 2 — Xây dựng lá chắn tất định & chuẩn hóa đầu ra (Deterministic Shields & Normalization)
- **Trạng thái**: Đã hoàn thành toàn bộ phần code, nâng cấp toàn diện trên dữ liệu thực tế và kiểm thử tự động (chờ chạy benchmark thực nghiệm vào ngày 06/11 theo lộ trình).

---

## 1. Mục tiêu công việc ở Phase 2

Trong cơ chế chấm điểm Penalized Accuracy (PA) của cuộc thi:
- Trả lời đúng: **+1 điểm**
- Bỏ qua (`abstain`): **0 điểm**
- Trả lời sai (hoặc sai định dạng kiểu dữ liệu): **-1 điểm**

Mục tiêu của Long trong Phase 2 là hoàn thiện hai chốt chặn tất định ở hai đầu mô hình LLM (`src/datamate/llm/feasibility.py` ở đầu vào và `src/datamate/output/normalizer.py` ở đầu ra), nâng cấp `src/datamate/llm/prompt_builder.py` và tích hợp đồng bộ vào `predict.py`:
1. **Chốt chặn đầu vào (Module 3 — Feasibility Gate)**: Phát hiện sớm các câu hỏi không thể trả lời từ dữ liệu (`unanswerable`) để lấy điểm cộng (+1) mà không tốn thời gian chạy GPU.
2. **Chốt chặn đầu ra (Module 6 — Format Normalizer & Tie-Breaker)**: Ép kiểu kết quả thực thi của mô hình về đúng 8 định dạng chuẩn của Ban Tổ Chức và xử lý trường hợp đồng hạng theo Điều 9 Rulebook.
3. **Nâng cấp điều phối suy luận (`predict.py` & `prompt_builder.py`)**: Bổ sung ngữ cảnh `README.md` của cửa hàng vào prompt, lưu đệm `shop_meta` theo từng cửa hàng, và tích hợp cơ chế tự sửa mã 1 lượt (Runtime Self-Correction) khi gặp lỗi thực thi.

---

## 2. Chi tiết các hạng mục đã triển khai và nâng cấp

### 2.1. Module 3: Bộ lọc khả thi tất định (`src/datamate/llm/feasibility.py`)
- **Hàm `extract_shop_metadata(business_obj, data_dict, readme_text)`**:
  - Quét toàn bộ cột ngày giao dịch thực tế để xác định `[min_date, max_date]` của cửa hàng (đã khắc phục triệt để lỗi cắt `.head(2000)` khiến các bảng trên 2.000 dòng bị thiếu ngày cuối).
  - Loại trừ các cột ngày phi giao dịch (`hạn sử dụng`, `hạn thanh toán`, `ngày tạo khách`, `ngày áp dụng`) và các bảng danh mục tĩnh khi tính `[min_date, max_date]`.
  - Bóc tách mốc ngày đóng sổ từ `README.md` (`Dữ liệu có đến hết DD/MM/YYYY`), danh sách cột trong `## Cột trong...` và tên các sheet tháng gộp (`merged_sheets`).
  - Nhận diện các cờ năng lực nghiệp vụ của cửa hàng: bảng nhập hàng (`has_import_table`), giá nhập (`has_import_price`), tồn kho & theo dõi lô hàng theo Điều 5 Rulebook (`has_inventory`), hạn sử dụng (`has_expiry_date`), công nợ (`has_debt_table`), sổ chi phí (`has_cost_data`), giá vốn (`has_cogs`), thông tin khách hàng (`has_customer_info`, `has_customer_group`, `has_customer_address`, `has_customer_gender`), kênh bán (`has_sales_channel`), phương thức thanh toán (`has_payment_method`), và lý do hủy/trả (`has_cancel_return_reason`).
- **Hàm `extract_query_date_range(question, as_of_date_str)` & `_extract_comparison_date_range(...)`**:
  - Bóc tách khoảng ngày `[start_date, end_date]` của kỳ hỏi chính và kỳ đối chiếu bắt buộc (ví dụ: `"so với tháng liền trước"` / `"so vs thang lien trc"`).
- **Hàm `check_feasibility(question, as_of_date, shop_meta)`**:
  - **Rào chắn 1**: Chặn các câu hỏi mang tính đánh giá chủ quan hoặc kiến thức ngoài dữ liệu POS (`tay nghề`, `lành nghề`, `thái độ`, `tận tâm`, `lễ phép`, `chu đáo`, `khách khen`, `ưa chuộng`, `thời tiết`, `uống mỗi lần mấy viên`...).
  - **Rào chắn 2 (Điều 7 Rulebook)**: Nếu khoảng thời gian của câu hỏi hoặc kỳ đối chiếu bắt buộc nằm hoàn toàn ngoài `[min_date, max_date]` của cửa hàng thì trả về ngay `unanswerable`. Nếu gối một phần vào khoảng dữ liệu của shop thì vẫn cho phép tính toán bình thường.
  - **Rào chắn 3**: Chặn 14 nhóm câu hỏi đòi hỏi bảng/cột mà cửa hàng không ghi nhận (nhà cung cấp, giá nhập, lãi ròng/chi phí, lãi gộp/giá vốn, tồn kho khi không có cả kho lẫn lô hàng, hạn dùng, công nợ, nhóm khách thân thiết, địa chỉ khách, giới tính khách, định danh khách, kênh bán, phương thức thanh toán, lý do hủy/trả).

### 2.2. Module 6: Bộ chuẩn hóa định dạng và xử lý đồng hạng (`src/datamate/output/normalizer.py`)
- **Xác định kiểu dữ liệu thông minh (`normalize_output` & `infer_expected_type`)**:
  - Ưu tiên cấu trúc thực tế của giá trị trả về (`bool` -> `boolean`, `DataFrame`/`dict(columns, rows)` -> `table`, `list`/`Series` -> `list`, `date`/`Timestamp` -> `date`, `str` tên riêng -> `string`) trước khi áp dụng từ khóa câu hỏi, tránh lỗi từ khóa `"bao nhiêu"` hoặc `"tiền"` làm hỏng đáp án dạng `list`, `table`, `string`.
  - Sử dụng biểu thức chính quy `PCT_PATTERN` (`(?<!\d)%|...`) để phân biệt câu hỏi phần trăm với nồng độ thuốc trong tên sản phẩm (`"Otrivin 0,1%"`, `"Povidine 10%"`, `"Natri clorid 0,9%"`).
- **Chuẩn hóa 8 kiểu dữ liệu theo Điều 6 & Điều 9 Rulebook**:
  1. `number`: Làm tròn tiền tệ về số nguyên VND (`ROUND_HALF_UP`, bỏ phần `.0000` của POS); làm tròn số trung bình không phải tiền về 2 chữ số thập phân.
  2. `percent`: Tự động nhân 100 cho tỉ lệ thô trong `[-1.0, 1.0]` khi mã nguồn chưa nhân 100, đồng thời kiểm tra `code_text` để **không nhân 100 lần thứ hai** đối với các đáp án phần trăm nhỏ ($\le 1\%$, ví dụ `0.91%`, `-0.8%`) khi code của LLM đã có phép `* 100`.
  3. `date`: Đưa về chuẩn ISO `YYYY-MM-DD` hoặc `YYYY-MM`.
  4. `boolean`: Đưa về `True` / `False` thuần.
  5. `string`: Chuẩn hóa Unicode NFC, loại bỏ khoảng trắng thừa và dấu ngoặc bọc ngoài.
  6. `list`: Đưa `Series`/`tuple`/`set` về mảng JSON có thứ tự và chuẩn hóa từng phần tử.
  7. `table`: Chuyển `DataFrame`, `list[dict]` hoặc `dict` về dạng `{"columns": [...], "rows": [[...], ...]}`.
  8. `unanswerable` & `abstain`: Đưa về `{"type": "...", "answer": None}`.
- **Xử lý đồng hạng (`apply_tie_breaker`)**:
  - Sắp xếp theo tiêu chí chính; khi bằng nhau thì xếp theo **mã tăng dần**, nếu không có mã thì xếp theo **tên tăng dần** (Điều 9 Rulebook).

### 2.3. Tích hợp và nâng cấp điều phối trong `predict.py` & `src/datamate/llm/prompt_builder.py`
- Lưu đệm `shop_meta` cùng dữ liệu cửa hàng trong `_BUSINESS_CACHE` để chỉ trích xuất metadata đúng 1 lần cho mỗi cửa hàng.
- Truyền `business_note=bd.readme_text` vào `build_prompt` để LLM nắm được bảng quy đổi đơn vị (`1 thùng = 24 lon`, `1 hộp = 6 cái`...) và quy ước cột riêng của từng shop.
- Bổ sung hàm `apply_tie_breaker` vào môi trường thực thi `exec_globals`.
- Bổ sung cơ chế **1-Turn Runtime Self-Correction**: Nếu mã nguồn sinh ra ở lượt 1 gặp ngoại lệ thực thi (`KeyError`, `ValueError`, `TypeError`...), tự động gửi thông báo lỗi kèm đoạn mã lỗi để LLM sửa lại 1 lần trước khi fallback về `abstain`.

---

## 3. Kết quả kiểm thử tự động & đối chiếu trên tập Train

1. **Kiểm thử Feasibility Gate trên toàn bộ 3.000 câu hỏi tập `competition_data/train`**:
   - **True Positives (Bắt đúng câu `unanswerable`)**: **70 / 70 câu (Recall = 100.0%)**
   - **False Positives (Chặn nhầm câu trả lời được)**: **0 / 2.930 câu (Precision = 100.0%)**
2. **Kiểm thử phân biệt `percent` và `number` (`PCT_PATTERN`) trên 2.462 câu số học tập `train`**:
   - Đạt độ chính xác **100% (0 False Positives, 0 False Negatives)**, xử lý đúng toàn bộ các câu hỏi chứa nồng độ thuốc (`0,1%`, `0,9%`, `10%`).
3. **Kiểm thử Unit Tests**:
   - `tests/llm/test_feasibility.py`: **11/11 bài kiểm thử ĐẠT (100% PASS)**.
   - `tests/output/test_normalizer.py`: **9/9 bài kiểm thử ĐẠT (100% PASS)**.
   - `tests/llm/test_prompt_builder.py`: **15/15 bài kiểm thử ĐẠT (100% PASS)**.

---

## 4. Danh sách tệp tạo mới và cập nhật

1. `src/datamate/llm/feasibility.py` (Tạo mới & nâng cấp toàn diện — Module 3)
2. `src/datamate/output/normalizer.py` (Tạo mới & nâng cấp toàn diện — Module 6)
3. `src/datamate/llm/prompt_builder.py` (Cập nhật `classify_intent`, `resolve_temporal_context`, `SYSTEM_INSTRUCTION`)
4. `predict.py` (Cập nhật tích hợp Module 3, Module 6, cache `shop_meta`, truyền `readme_text` và 1-turn Self-Correction)
5. `tests/llm/test_feasibility.py` (11 unit tests)
6. `tests/output/test_normalizer.py` (9 unit tests)
7. `logs/commit_20261103_long_phase2_deterministic_shields.md` (Báo cáo kỹ thuật Phase 2)
