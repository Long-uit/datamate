# Đề xuất điều chỉnh thư mục benchmark

> **Trạng thái:** đề xuất đã được duyệt và triển khai. Evaluator/splitter, README, test cases và các split materialized đã được cập nhật. Bộ test chưa được chạy. Kiểm tra dữ liệu xác nhận split within-business khớp ID legacy; các fold giữ doanh nghiệp không giao `business_id` giữa train và validation.  
> **Nguồn quy tắc:** mục 9 của [rulebook train](../competition_data/train/rulebook.md) và [rulebook public_test](../competition_data/public_test/rulebook.md). Hai mục 9 có cùng quy tắc chấm; khác biệt giữa hai split nằm chủ yếu ở các quy tắc nghiệp vụ theo ngành.

## 1. Đề xuất được khuyến nghị

Chia điều chỉnh thành hai phần:

1. **Sửa evaluator trước**, vì PA hiện tại có thể chấm sai định dạng, boolean, chuỗi, list và bảng.
2. **Giữ nguyên split 2.392/608 hiện có**, đồng thời bổ sung split giữ nguyên doanh nghiệp để đo khả năng tổng quát hóa. Không ghi đè các ID hiện tại để giữ khả năng so sánh các kết quả cũ.

Đánh giá dữ liệu đã có: train/val không trùng ID; các câu và đáp án validation khớp nguồn. Validation có 608 mẫu nhưng chỉ 5 boolean và 2 table, nên PA của hai type này rất bất ổn; báo cáo phải luôn kèm số mẫu. Điểm yếu hiện tại nằm ở cách chấm và phạm vi đo, không phải tính toàn vẹn của các file ID đang dùng.

## 2. Phạm vi file dự kiến

| File | Thay đổi dự kiến |
|---|---|
| `benchmark/evaluate.py` | Viết lại kiểm tra input, so khớp từng answer type theo rulebook, tính PA và báo cáo. Giữ CLI tương thích nếu có thể. |
| `benchmark/split.py` | Thêm kiểm tra dữ liệu, tham số chiến lược split, manifest, và đầu ra materialized train/val cho từng split mới. |
| `benchmark/README.md` | Hướng dẫn tạo split, chấm kết quả, định nghĩa các chỉ số và cảnh báo không đưa validation gold vào inference image. |
| `benchmark/splits/` | Chứa manifest, ID, và các file câu hỏi/đáp án train-val cho từng split; không thay các file validation hiện hành ở thư mục gốc. |
| `tests/benchmark/test_evaluate.py` | Mở rộng test so khớp/PA theo rulebook. |
| `tests/benchmark/test_split.py` | Thêm test tính ổn định, không rò ID, kiểm tra đầu vào và manifest. |

Không đổi `benchmark/__init__.py`. Không sửa file dữ liệu hiện tại trừ khi quá trình sinh lại được duyệt riêng.

## 3. Hành vi cần có trong evaluator

### 3.1. Đọc và kiểm tra submission

- Dòng JSONL hỏng, thiếu ID, ID trùng hoặc dữ liệu gold không đầy đủ phải gây lỗi rõ kèm file và số dòng; không âm thầm bỏ qua hoặc ghi đè bản ghi.
- Mỗi eval ID phải có đúng một gold record. Thiếu prediction là `abstain` và được tính 0; prediction có ID ngoài tập được báo riêng, không tham gia PA.
- Một prediction có mặt nhưng sai type/format là sai (-1), theo quy tắc “mỗi type có một format duy nhất”.
- Trường `reason` của `unanswerable`/`abstain`, nếu có, phải là string. Nếu `reason` không phải string, xử lý là abstain theo rulebook.
- Prediction JSON hợp lệ nhưng có type không được hỗ trợ được tính sai (-1); không dùng fallback so chuỗi cho type lạ. Lỗi cú pháp JSON/ID trùng là lỗi input và phải dừng với thông báo rõ.
- Tổng `correct + wrong + abstain` phải bằng `total`. Mẫu số PA là số eval ID đã xác thực, không phải số ID yêu cầu nhưng thiếu gold.

### 3.2. Quy tắc so khớp theo type

| Type | Hành vi đề xuất |
|---|---|
| `number` | Chỉ nhận JSON number; loại boolean và chuỗi số. Tiền/số đếm nguyên so chính xác. Với giá trị thập phân, áp dụng độ chính xác đã ghi trong gold/rulebook; chỉ dung sai sai số biểu diễn float rất nhỏ, không dùng epsilon cố định `1e-4`. Dùng Decimal khi đọc JSON để tránh ép kiểu sớm. |
| `percent` | Chỉ nhận JSON number biểu diễn số phần trăm, không phải tỷ lệ 0–1 hay chuỗi có dấu `%`. So ở 2 chữ số thập phân theo chính sách làm tròn được ghi rõ và có case kiểm tra biên. |
| `boolean` | Chỉ nhận JSON `true`/`false`; không dùng `bool(value)` và không chấp nhận chuỗi như `"false"` hoặc số 0/1. |
| `date` | Chỉ nhận string đúng `YYYY-MM-DD` hoặc `YYYY-MM` và là ngày/tháng hợp lệ; so chính xác. |
| `string` | Chuẩn hóa NFC, không phân biệt hoa thường, coi dấu câu và khoảng trắng theo cùng quy tắc, gộp khoảng trắng; giữ nguyên dấu tiếng Việt. So với đáp án chuẩn và các alias phẳng của string. |
| `list` | Cả hai phải là JSON array cùng độ dài; so theo vị trí, giữ thứ tự. String dùng chuẩn hóa string; number dùng quy tắc number. Alias lồng theo vị trí trong trường `alias` cũng được so. |
| `table` | Kiểm tra object `columns`/`rows`, số cột và độ rộng từng dòng. Nếu tên cột khớp sau chuẩn hóa thì căn theo tên; nếu không khớp thì căn theo vị trí như rulebook. So sánh hàng không phụ thuộc thứ tự, nhưng vẫn giữ số lần xuất hiện của hàng trùng. Ô tên dùng string/alias; ô số dùng number. |
| `unanswerable` | Đúng khi type khớp gold. `reason` có thể vắng mặt; nếu có phải là string. Chấp nhận `answer` vắng mặt hoặc null để tương thích schema submission hiện tại. |
| `abstain` | Luôn 0 điểm, bất kể gold. Prediction thiếu cũng 0 điểm. |

Rulebook không nêu rõ quy tắc xử lý trường hợp phần trăm đúng nửa đơn vị ở chữ số thứ ba. Benchmark cố định quy ước `ROUND_HALF_UP` trong README và evaluator; đây là quy ước nội bộ để kết quả nhất quán, không phải nội dung rulebook.

### 3.3. Alias cho list và table

Dữ liệu hiện lưu alias lồng theo phần tử/đối tượng, ví dụ list có một danh sách alias cho mỗi phần tử; table có danh sách alias ứng với các hàng/tên đối tượng. Evaluator cần xác thực số alias không lệch số phần tử/hàng. Khi so bảng không phụ thuộc thứ tự hàng, alias phải đi theo gold row tương ứng, không đi theo index của prediction.

Nếu alias sai schema, evaluator nên dừng với lỗi dữ liệu gold thay vì bỏ alias âm thầm và làm sai điểm.

### 3.4. Báo cáo và CLI

Báo cáo đề xuất có:

- PA, accuracy, tổng đúng/sai/abstain và tỷ lệ từng loại;
- PA theo answer type cùng số mẫu của type đó;
- missing/extra/duplicate IDs, số dòng lỗi, invalid format;
- tùy chọn xuất JSON chi tiết cho từng câu gồm trạng thái và lý do so khớp;
- xử lý tập rỗng không crash; mặc định báo “không có câu để chấm” thay cho phần trăm chia cho 0.

Giữ các tham số hiện có `--pred`, `--gold`, `--val-ids`; bổ sung `--report-json` và `--strict-input` nếu cần. Chế độ mặc định nên strict để không đưa ra PA sai vì dữ liệu lỗi.

## 4. Đề xuất cho split

### 4.1. Giữ split hiện hành

Giữ nguyên `train_ids.json`, `val_ids.json`, `val_questions.jsonl`, `val_answers.jsonl` như một phiên bản `within_business_v1`. Tên này mô tả đúng: câu được giữ lại ngẫu nhiên trong từng doanh nghiệp, nên mọi doanh nghiệp xuất hiện ở cả train và val.

Mã hiện ghi dự kiến 2.400/600, nhưng artifact là 2.392/608 do làm tròn riêng trong từng nhóm doanh nghiệp. Sửa docstring/thông báo để ghi tỷ lệ mục tiêu xấp xỉ 80/20 và số thực tế, không ép đổi lại ID cũ.

### 4.2. Thêm split giữ doanh nghiệp

Thêm chiến lược `business_holdout` hoặc 5-fold GroupKFold theo `business_id`:

- ID của một doanh nghiệp chỉ thuộc train hoặc val trong một fold, không nằm ở cả hai.
- Ghi danh sách doanh nghiệp mỗi fold vào manifest.
- Cân bằng số câu và loại câu trong khả năng có thể, nhưng không phá nguyên tắc giữ nguyên doanh nghiệp.
- Nếu chưa có nhãn ngành đáng tin cậy, không gọi split này là “industry holdout”. Chỉ làm leave-one-industry-out sau khi có bảng ánh xạ ngành được kiểm tra.

Đây là chỉ số tổng quát hóa bổ sung; không thay thế validation 608 câu hiện hành vì hai split trả lời hai câu hỏi đánh giá khác nhau.

### 4.3. Manifest và bảo vệ train/val

Mỗi split materialized cần sinh đủ bốn file, giống cấu trúc câu hỏi/đáp án hiện có của validation:

```text
benchmark/splits/within_business_v1/
├── train_ids.json
├── train_questions.jsonl
├── train_answers.jsonl
├── val_ids.json
├── val_questions.jsonl
├── val_answers.jsonl
└── manifest.json
```

Với split theo doanh nghiệp, mỗi fold có cùng bộ file trong thư mục riêng, ví dụ `benchmark/splits/business_holdout_v1/fold_0/`. Tập train chỉ chứa ID không nằm trong validation của fold đó; các file answers phải được lọc theo đúng danh sách ID tương ứng.

Mỗi split mới nên có `manifest.json` gồm:

- version/strategy/seed/fold/validation ratio;
- SHA-256 của source questions và answers;
- counts tổng, train, val; phân bố theo business và answer type;
- hash hoặc danh sách ID của từng partition;
- phiên bản code tạo split.

Thêm kiểm tra `val_ratio` trong khoảng hợp lệ, ID trùng, trường bắt buộc thiếu, questions/answers lệch ID, alias sai cấu trúc. Ghi file tạm rồi rename để tránh split dở dang. Tạo `train_questions.jsonl` và `train_answers.jsonl` đã lọc theo train IDs để pipeline huấn luyện không phải đọc nhầm toàn bộ 3.000 đáp án; validation gold giữ riêng và loại khỏi inference image.

## 5. Test đã bổ sung (chưa chạy)

Mở rộng `tests/benchmark/test_evaluate.py` để bao phủ:

- JSON type đúng/sai cho từng type, gồm bool không bị coi là number;
- epsilon float nhỏ so với sai số có ý nghĩa; tiền nguyên phải khớp từng đồng;
- phần trăm ở biên làm tròn, âm/dương và format 0–100;
- string dấu câu, khoảng trắng, dấu tiếng Việt và alias;
- list sai thứ tự, alias theo vị trí, type phần tử;
- table đổi thứ tự hàng, đổi thứ tự cột có tên khớp, fallback theo vị trí, cell sai, alias, hàng trùng;
- unanswerable/abstain, reason hợp lệ và reason sai type;
- duplicate/missing/extra ID, JSONL lỗi, gold thiếu, eval set rỗng và báo cáo.

`tests/benchmark/test_split.py` bao phủ seed cố định, coverage/overlap, group holdout, manifest và hành vi khi source lỗi. Các test cases đã được thêm/cập nhật cùng implementation; chưa chạy test suite.

## 6. Tiêu chí nghiệm thu sau khi được duyệt

1. Điểm PA không thể tăng chỉ vì dự đoán bảng có đúng số hàng.
2. Giá trị sai format không được chấm đúng do ép kiểu.
3. Không câu nào biến mất âm thầm khỏi mẫu số.
4. Các artifact split cũ không đổi hash/ID.
5. Split theo doanh nghiệp chứng minh được không có business overlap trong từng fold.
6. Báo cáo cho biết chính xác lý do một câu được tính đúng, sai hoặc abstain.
7. README chỉ rõ dữ liệu gold nào được dùng khi train, validation và inference.

## 7. Phạm vi không nằm trong lần triển khai này

- Không sửa file nguồn trong `competition_data`; các split mới chỉ materialize bản sao đã lọc.
- Không thay đổi hoặc ghi đè split lịch sử trong `benchmark/`; split mới có version và thư mục riêng.
- Không tạo industry holdout vì chưa có ánh xạ ngành được kiểm tra; business holdout chỉ giữ nguyên `business_id`.
- Chưa chạy test suite; cần chạy trước khi dùng evaluator để ra quyết định chọn model.
