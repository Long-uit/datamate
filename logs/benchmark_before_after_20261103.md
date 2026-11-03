# Nhật ký thay đổi Benchmark DataMate

- **Ngày ghi nhận:** 2026-11-03
- **Phạm vi:** `benchmark/evaluate.py`, `benchmark/split.py`, `benchmark/README.md`, `benchmark/splits/` và test cases trong `tests/benchmark/`.
- **Mục tiêu:** làm cho cách chấm sát rulebook hơn, tạo partition train/validation hoàn chỉnh và có thể truy vết, đồng thời ghi lại cách vận hành benchmark.

## Tóm tắt

Benchmark được nâng từ evaluator và splitter tối giản thành luồng gồm kiểm tra nguồn, materialize partition có manifest, chấm theo output contract và xuất report có breakdown theo answer type và lý do theo từng ID.

## Trước khi chỉnh sửa

### Split và dữ liệu

- `split.py` ghi các file trực tiếp vào thư mục `benchmark/`, tạo `train_ids.json`, `val_ids.json`, `val_questions.jsonl`, `val_answers.jsonl`.
- Chưa có `train_questions.jsonl` và `train_answers.jsonl` đã lọc riêng để huấn luyện.
- Kiểm tra JSONL, ID lặp, quan hệ một-một giữa questions/answers và schema alias còn hạn chế; answer thiếu có thể bị bỏ qua khi ghi output.
- Chưa có manifest lưu hash nguồn, hash partition, phân bố doanh nghiệp/type hoặc chiến lược tạo split.
- Chỉ có cách chia câu hỏi trong từng `business_id`; chưa có holdout theo nguyên doanh nghiệp.

### Evaluator

- Loader bỏ qua JSONL lỗi và ID không hợp lệ thay vì dừng với vị trí dòng; ID trùng có thể bị ghi đè trong mapping.
- Boolean có thể bị ép qua `bool(value)`; số dùng dung sai cố định; phần trăm dùng `round()` mặc định.
- Kiểm tra bảng mới dừng ở số hàng, chưa xác minh đầy đủ từng ô; report chưa nêu rõ missing/extra prediction và lý do từng ID.
- Tập eval thiếu gold có thể làm mẫu biến mất khỏi phép cộng điểm nhưng vẫn nằm trong mẫu số.

## Sau khi chỉnh sửa

### 1. Evaluator: `benchmark/evaluate.py`

- Đọc JSONL nghiêm ngặt; lỗi cú pháp, record không phải object, ID trống/trùng hoặc gold sai schema gây lỗi rõ ràng.
- Xác thực mọi eval ID có gold. Prediction thiếu tính abstain; prediction ngoài tập được liệt kê nhưng không vào PA.
- So type và format nghiêm ngặt: boolean không nhận số/string; number không nhận chuỗi số; date phải là ISO hợp lệ.
- Số thập phân được đọc bằng `Decimal`; số nguyên so chính xác; chỉ chấp nhận dung sai tối đa một ULP nhỏ hơn một đơn vị cho sai số biểu diễn.
- Percent làm tròn hai chữ số theo quy ước nội bộ `ROUND_HALF_UP`; rulebook không chỉ định mode ở trường hợp tie.
- String chuẩn hóa Unicode NFC/casefold, bỏ dấu câu và khoảng trắng nhưng giữ dấu tiếng Việt; alias chỉ lấy từ gold.
- List so đúng độ dài/thứ tự và alias theo vị trí. Table so cấu trúc, từng ô, cột theo tên hoặc vị trí, hàng không phụ thuộc thứ tự nhưng vẫn giữ số lần lặp.
- Report có PA, accuracy, coverage, đúng/sai/abstain, invalid format, missing/extra IDs, breakdown theo type và chi tiết trạng thái/lý do từng eval ID.

### 2. Splitter: `benchmark/split.py`

- Kiểm tra source JSONL, ID duy nhất, question-answer khớp một-một, answer type/schema và alias trước khi chia.
- Output được staging rồi rename; thư mục đích đã tồn tại thì không ghi đè.
- Mỗi partition materialize đủ bảy file: `train_ids.json`, `train_questions.jsonl`, `train_answers.jsonl`, `val_ids.json`, `val_questions.jsonl`, `val_answers.jsonl`, `manifest.json`.
- Manifest ghi chiến lược/seed/version generator, hash source, số lượng, hash IDs, phân bố theo business và answer type.

### 3. Các artifact đã tạo

#### `benchmark/splits/within_business_v1/`

- 2.392 mẫu train và 608 validation trên 3.000 câu; tỷ lệ validation 20% là mục tiêu được làm tròn riêng theo từng doanh nghiệp.
- Chia câu hỏi trong từng doanh nghiệp nên cùng doanh nghiệp có mặt ở train và validation; phép đo nhắm tới câu mới trên doanh nghiệp đã thấy.
- Tập ID train/validation được đối chiếu là trùng chính xác với split lịch sử trước đó.

#### `benchmark/splits/business_holdout_v1/fold_0..fold_4/`

- Năm fold giữ `business_id` nguyên vẹn; doanh nghiệp validation của một fold không xuất hiện trong train của chính fold đó.
- Train/validation lần lượt: `fold_0` 2.406/594; `fold_1` 2.409/591; `fold_2` 2.407/593; `fold_3` 2.409/591; `fold_4` 2.369/631.
- Mỗi doanh nghiệp được giữ lại làm validation đúng một lần qua năm fold. Đây là business holdout, không phải industry holdout.

### 4. Tài liệu và test cases

- `benchmark/README.md` mô tả kiến trúc, schema, hai chiến lược split, manifest, metric, lệnh tạo/chấm và giới hạn diễn giải.
- `tests/benchmark/test_evaluate.py` được mở rộng cho format/type, alias, PA, report và input lỗi.
- `tests/benchmark/test_split.py` được thêm cho tính xác định, cặp Q/A, group holdout, manifest và chống ghi đè.

## Kiểm tra đã thực hiện

- Đọc/validate source: 3.000 questions và 3.000 answers.
- Đối chiếu ID legacy với `within_business_v1`: khớp chính xác.
- Đối chiếu mỗi partition: số dòng IDs/questions/answers khớp, train và validation không giao ID; các fold không giao `business_id` train/validation.
- Kiểm tra CLI help cho evaluator và splitter; kiểm tra whitespace bằng `git diff --check`.
- **Chưa chạy test suite.**

## Lưu ý trạng thái file legacy

Trong working tree tại thời điểm ghi log, Git đánh dấu các file legacy sau ở gốc `benchmark/` là đã xóa so với HEAD: `train_ids.json`, `val_ids.json`, `val_questions.jsonl`, `val_answers.jsonl`. Các artifact mới có bản materialize dưới `benchmark/splits/within_business_v1/`, nhưng evaluator hiện vẫn có giá trị mặc định trỏ tới hai file legacy `benchmark/val_answers.jsonl` và `benchmark/val_ids.json`. Vì vậy cần truyền tường minh `--gold` và `--val-ids` khi chấm bằng split mới; trạng thái xóa legacy cần được xem xét riêng nếu cần giữ tương thích với lệnh cũ.

