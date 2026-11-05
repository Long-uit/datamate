# Báo Cáo Hiện Trạng, Đánh Giá Hệ Thống & Hướng Phát Triển — DataMate
**Dự án:** DataMate — Zalo AI Challenge 2026 (Track: Phân tích Dữ liệu Bán lẻ & Tự động Sinh mã)  
**Thời điểm đánh giá:** Ngày 04/11/2026 (Giữa Phase 2 — Sprint 17 ngày)  
**Tiêu chí đánh giá:** Trung thực, minh bạch kỹ thuật, phản ánh đúng thực trạng mã nguồn, không nói quá hay thổi phồng kết quả.

---

## 1. Mục Tiêu Dự Án & Bản Chất Thách Thức Kỹ Thuật

DataMate là hệ thống tự động trả lời câu hỏi nghiệp vụ kinh doanh dựa trên dữ liệu bán lẻ đa định dạng (CSV, Excel nhiều sheet, SQLite, JSON) của các hộ kinh doanh và doanh nghiệp nhỏ tại Việt Nam.

Đặc thù cốt lõi của cuộc thi là chỉ số chấm điểm **Penalized Accuracy (PA)**:
$$\text{PA} = \frac{\text{Correct} - \text{Incorrect}}{\text{Total}}$$
- **Đúng:** $+1$ điểm.
- **Sai:** $-1$ điểm *(phạt rất nặng: sai một câu làm mất 2 điểm so với câu đúng)*.
- **Từ chối trả lời (`abstain`):** $0$ điểm *(bảo toàn điểm số, không bị phạt)*.
- **Phát hiện câu hỏi bất khả thi (`unanswerable`):** $+1$ điểm.

Do cơ chế phạt điểm âm, một hệ thống LLM chỉ "đoán mò" hoặc sinh mã có tỷ lệ lỗi cao sẽ nhanh chóng bị điểm âm hoặc tụt hạng thê thảm trên Leaderboard. Vì vậy, kiến trúc DataMate được định hướng: **Ưu tiên các lá chắn quy tắc tất định (Deterministic Shields) để triệt tiêu lỗi phạt điểm, kết hợp mô hình ngôn ngữ lớn (Qwen2.5-Coder) và cơ chế tự sửa lỗi (Self-Correction).**

---

## 2. Hệ Thống Đã Đạt Đến Bước Nào? (Hiện Trạng Tiến Độ)

Đối chiếu với Kế hoạch triển khai trong [`Timeline_and_Contribution.md`](file:///d:/Company/Agentic%20AI/datamate/docs/Timeline_and_Contribution.md), tiến độ thực tế của hệ thống tính đến ngày 04/11/2026 như sau:

```
[Phase 1: Fast Pipeline]       -> HOÀN THÀNH 100% (Mốc 02/11)
[Phase 2: Deterministic Shields] -> ĐANG THỰC HIỆN (~80% mã nguồn, CHƯA tích hợp xong)
[Phase 3: Core Enhancement]     -> CHƯA BẮT ĐẦU (Kế hoạch: 07/11 - 12/11)
[Phase 4: Docker & Submission]  -> CHƯA BẮT ĐẦU (Kế hoạch: 13/11 - 16/11)
```

### 2.1. Giai đoạn 1: Fast Pipeline (Đã hoàn thành 100%)
- Đã dựng thành công khung suy luận đầu-cuối (E2E) trong [`predict.py`](file:///d:/Company/Agentic%20AI/datamate/predict.py):
  1. Đọc dữ liệu câu hỏi từ `questions.jsonl`.
  2. Nạp dữ liệu doanh nghiệp và tạo cấu trúc tóm tắt schema.
  3. Xây dựng prompt kèm thông tin thời gian tham chiếu.
  4. Nạp mô hình LLM vào GPU với lượng tử hóa 4-bit NF4.
  5. Sinh mã Python, thực thi và thu thập kết quả thô.
  6. Chuẩn hóa định dạng và xuất file `submission.jsonl` kèm log chi tiết theo từng câu hỏi.
- Đã hoàn tất dry-run trên 1.000 câu hỏi tập `public_test`. Tệp đầu ra tuân thủ 100% quy chuẩn Ban Tổ Chức (được kiểm định bởi hàm `validate_submission`, 0 lỗi định dạng).

### 2.2. Giai đoạn 2: Deterministic Shields & Rulebook Engines (Tiến độ thực tế ~80%)
Giai đoạn này diễn ra từ 03/11 đến 06/11. Tình trạng thực tế như sau:
- **Đã hoàn thành và đã cắm vào pipeline chạy chính:**
  - **Module 3 (Deterministic Feasibility Gate - [`feasibility.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/llm/feasibility.py)):** Hoàn chỉnh. Đã phát hiện chính xác 70/70 câu `unanswerable` trong tập train (Recall 100%, Precision 100%), bao gồm cả Điều 7 (ngày hỏi ngoài khoảng dữ liệu của shop) và câu hỏi đòi hỏi thuộc tính chủ quan/thiếu bảng nghiệp vụ.
  - **Module 6 (Format Normalizer & Tie-Breaker - [`normalizer.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/output/normalizer.py)):** Hoàn chỉnh. Chuẩn hóa chặt chẽ 8 kiểu dữ liệu của BTC, xử lý đồng hạng theo Điều 9, ngăn chặn lỗi nhân đôi 100 đối với tỷ lệ nhỏ $\le 1\%$, làm tròn tiền VND số nguyên.
  - **Cơ chế Runtime Self-Correction:** Đã tích hợp trong `predict.py`. Khi lượt 1 gặp lỗi thực thi, hệ thống gửi lỗi cho LLM tự sửa lại mã 1 lần trước khi chuyển về `abstain`.
  - **Chuyển đổi backbone sang 7B:** Toàn bộ hệ thống (`config/default.yaml`, `config.py`, `client.py`, `predict.py`) đã chuyển từ model 3B sang `Qwen/Qwen2.5-Coder-7B-Instruct`.
  - **Bộ công cụ Benchmark nội bộ:** Đã viết xong [`split.py`](file:///d:/Company/Agentic%20AI/datamate/benchmark/split.py) (tạo 5-fold cross validation độc lập theo doanh nghiệp), [`evaluate.py`](file:///d:/Company/Agentic%20AI/datamate/benchmark/evaluate.py) (chấm điểm PA chuẩn) và [`error_analysis.py`](file:///d:/Company/Agentic%20AI/datamate/benchmark/error_analysis.py) (phân loại 8 nhóm lỗi).

- **ĐÃ VIẾT XONG MÃ NGUỒN NHƯNG CHƯA ĐƯỢC TÍCH HỢP VÀO PIPELINE CHÍNH:**
  - **Module 1 (Rule 8 Data Cleaner - [`cleaner.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/ingestion/cleaner.py)):** Đã viết logic forward-fill ô trống cấp đơn hàng và khử trùng lặp dòng POS lỗi, có unit test đầy đủ, **nhưng chưa được gọi trong `predict.py`**. Hiện tại dữ liệu đưa vào cho LLM và SQLite vẫn là dữ liệu thô!
  - **Module 1 (In-Memory SQLite Mirror - [`sqlite_mirror.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/ingestion/sqlite_mirror.py)):** Đã viết hàm đánh index tự động cho các bảng, nhưng trong `predict.py` cờ `clean` vẫn để mặc định `False`.
  - **Module 2 (Temporal Grounder - [`grounding/temporal.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/grounding/temporal.py)):** Đã viết logic giải mã lịch âm, ngày lễ, Tết, nửa đầu/cuối tháng, chuỗi tháng liên tiếp, **nhưng trong `prompt_builder.py` lại đang dùng một hàm độc lập đơn giản hơn với bảng Tết hard-coded**.
  - **Module 2 (Entity Linker - [`entity_linker.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/grounding/entity_linker.py)):** Đã viết bộ xử lý viết tắt tiếng Việt ("cf", "sp", "dthu", "hnay") và fuzzy match tên sản phẩm/khách hàng, **nhưng chưa được kết nối vào `predict.py` hay `prompt_builder.py`**.
  - **Module 5 (Execution Sandbox - [`execution/sandbox.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/execution/sandbox.py)):** Đã viết bộ chạy subprocess cô lập có timeout, **nhưng trong `predict.py` vẫn đang dùng `exec()` nội bộ trực tiếp**.

### 2.3. Giai đoạn 3 & 4: Chưa thực hiện
- **Phase 3:** Chưa sinh 15.000 – 20.000 dữ liệu tổng hợp; chưa tiến hành Fine-tuning SFT/DPO; chưa viết file `train.sh` (tệp hiện tại 0 bytes).
- **Phase 4:** Chưa đóng gói Docker offline (`Dockerfile` hiện tại 0 bytes); chưa xây dựng bộ đo độ tin cậy $C$ và quét ngưỡng từ chối tối ưu $\tau^*$.

---

## 3. Bảng Tổng Hợp Trạng Thái Chi Tiết Các Module

| Module & Tệp mã nguồn | Phụ trách | Tình trạng mã nguồn | Tình trạng tích hợp (`predict.py`) | Đánh giá thực tế |
|---|:---:|:---:|:---:|---|
| **Loader & Parser**<br>[`ingestion/loader.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/ingestion/loader.py) | Phát | Hoàn thành | **Đã tích hợp** | Đọc tốt CSV, XLSX đa sheet, SQLite, sửa lỗi font mojibake, gộp sheet tháng tốt. |
| **Rule 8 Data Cleaner**<br>[`ingestion/cleaner.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/ingestion/cleaner.py) | Phát | Hoàn thành (có test) | **CHƯA TÍCH HỢP** | Chưa được gọi trong pipeline. Dữ liệu nạp vào LLM vẫn còn ô trống chưa forward-fill. |
| **SQLite Mirror & Indexing**<br>[`ingestion/sqlite_mirror.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/ingestion/sqlite_mirror.py) | Phát | Hoàn thành | Tích hợp một phần | Đã nạp SQLite in-memory, nhưng chưa bật cờ `clean=True`. |
| **Metadata Extractor**<br>[`ingestion/metadata.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/ingestion/metadata.py) | Phát | Cần sửa lỗi | **CHƯA TÍCH HỢP** | Dính lỗi `.head(2000)` cắt cụt ngày giao dịch; chưa được dùng để xây sơ đồ quan hệ bảng (Join Graph). |
| **Temporal Grounder**<br>[`grounding/temporal.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/grounding/temporal.py) | Phát | Hoàn thành | **CHƯA TÍCH HỢP** | Code tốt nhưng bị tách rời; `prompt_builder.py` đang dùng hàm giải mã riêng đơn giản hơn. |
| **Entity Linker**<br>[`grounding/entity_linker.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/grounding/entity_linker.py) | Phát | Hoàn thành | **CHƯA TÍCH HỢP** | Nằm độc lập, chưa giúp prompt ánh xạ các từ viết tắt/tên mờ của sản phẩm. |
| **LLM Client & Inference**<br>[`llm/client.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/llm/client.py) | Long | Hoàn thành | **Đã tích hợp** | Chạy tốt Qwen2.5-Coder 7B 4-bit, Greedy Decoding ($T=0$), kiểm tra cú pháp AST an toàn. |
| **Feasibility Gate (Shield)**<br>[`llm/feasibility.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/llm/feasibility.py) | Long | Hoàn thành | **Đã tích hợp** | Hoạt động xuất sắc (100% precision/recall trên tập train), bắt đúng câu hỏi ngoài phạm vi. |
| **Prompt Builder & Few-Shot**<br>[`llm/prompt_builder.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/llm/prompt_builder.py) | Long | Hoàn thành | **Đã tích hợp** | Phân loại intent tốt, chọn dynamic few-shot, truyền rulebook và business notes đầy đủ. |
| **Format Normalizer**<br>[`output/normalizer.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/output/normalizer.py) | Long | Hoàn thành | **Đã tích hợp** | Hoạt động chính xác, bao phủ tốt 8 định dạng, giải quyết đồng hạng Điều 9, làm tròn chuẩn. |
| **Submission Writer**<br>[`output/submission.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/output/submission.py) | Phát | Hoàn thành | **Đã tích hợp** | Ghi tệp an toàn (flush + fsync), có hàm validate format tuân thủ 100% quy chế. |
| **Execution Sandbox**<br>[`execution/sandbox.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/execution/sandbox.py) | Phát | Hoàn thành | **CHƯA TÍCH HỢP** | `predict.py` vẫn dùng `exec()` nội bộ không timeout, sandbox chưa được gọi. |
| **Benchmark Suite**<br>[`benchmark/*.py`](file:///d:/Company/Agentic%20AI/datamate/benchmark/) | Cả 2 | Hoàn thành | Sẵn sàng chạy | Đã sinh xong dữ liệu 5 fold của `business_holdout_v1`. Đang chờ chạy đánh giá. |
| **Dockerfile & predict.sh** | Phát | Sơ khai | **CHƯA HOÀN THIỆN** | `Dockerfile` 0 bytes, `train.sh` 0 bytes. `predict.sh` mới chỉ có khung gọi python cơ bản. |

---

## 4. Đánh Giá Hệ Thống Hiện Tại: Ưu Điểm & Nhược Điểm Thực Tế

### 4.1. Những ưu điểm thực tế (Đã làm tốt)
1. **Kiến trúc phân tầng đúng đắn đối với cơ chế phạt điểm:**
   - Hệ thống không để LLM "tự do" quyết định mọi việc. Tầng quy tắc tất định (Deterministic Feasibility Gate và Format Normalizer) kiểm soát chặt chẽ đầu vào và đầu ra.
   - Nhờ đó, 100% các câu hỏi thuộc nhóm `unanswerable` (do thiếu bảng, thiếu cột, câu hỏi cảm tính, hoặc kỳ hỏi nằm ngoài phạm vi dữ liệu theo Điều 7) đều được giải quyết dứt điểm mà không tốn tài nguyên GPU, mang lại điểm cộng an toàn (+1).
2. **Khả năng chuẩn hóa đầu ra cực kỳ vững vàng:**
   - `normalizer.py` được thiết kế có chiều sâu: nhận diện đúng bản chất kiểu dữ liệu, bảo vệ cấu trúc `list`/`table`, phân biệt số phần trăm với nồng độ hóa chất/thuốc (như *Otrivin 0,1%*), bảo vệ các tỷ lệ nhỏ không bị nhân đôi 100, và tuân thủ chặt chẽ quy tắc làm tròn tiền VND (`ROUND_HALF_UP`).
3. **Pipeline suy luận đầu-cuối đã vận hành trơn tru:**
   - Đã kiểm chứng qua Dry-run trên toàn bộ 1.000 câu của `public_test`. Tệp kết quả xuất ra hợp lệ 100% và không có lỗi crash giữa chừng.
   - Cơ chế bộ nhớ đệm (In-Memory Cache theo shop) hoạt động tốt, giúp các câu hỏi cùng shop không phải đọc lại đĩa.
   - Đã tích hợp 1 lượt **Runtime Self-Correction**: nếu mã sinh ra bị lỗi thực thi (`KeyError`, `IndexError`...), hệ thống tự động đưa lỗi vào context và yêu cầu LLM viết lại hàm `solution(data)`.
4. **Hạ tầng đo lường độc lập, khách quan:**
   - Bộ split `business_holdout_v1` chia dữ liệu theo nguyên tắc chia theo doanh nghiệp (các shop ở tập validation hoàn toàn không xuất hiện ở tập train). Điều này phản ánh chính xác bài toán thi đấu thực tế (mô hình phải suy luận trên các shop chưa từng thấy).

---

### 4.2. Những nhược điểm, lỗ hổng và rủi ro kỹ thuật (Cần nhìn thẳng vào sự thật)
1. **Sự phân mảnh nghiêm trọng giữa mã nguồn thành phần và pipeline chính:**
   - Đây là vấn đề lớn nhất hiện tại: **Một nửa số module được viết ra rất công phu nhưng đang nằm "đắp chiếu", không tham gia vào luồng chạy chính của `predict.py`:**
     - `cleaner.py` (Rule 8) không được gọi. Do đó, nếu bảng dữ liệu có các dòng gộp ô bị khuyết thông tin cấp đơn hàng hoặc có dòng trùng lặp do lỗi POS xuất file, mã của LLM truy vấn sẽ bị thiếu dữ liệu hoặc tính thừa doanh thu.
     - `entity_linker.py` không được gọi. Khi người dùng hỏi bằng tiếng lóng, viết tắt (*"cf", "sp", "dthu", "hnay"*) hoặc tên sản phẩm không dấu, LLM phải tự xoay xở mà không nhận được sự trợ giúp chuẩn hóa từ tầng tiền xử lý.
     - `grounding/temporal.py` không được dùng trong prompt. `prompt_builder.py` lại đang dùng một hàm riêng thô sơ hơn và một bảng tra cứu ngày Tết hard-coded.
2. **Rủi ro thực thi lớn khi dùng `exec()` trực tiếp trong `predict.py`:**
   - Trong `predict.py`, hàm `execute_solution` chạy mã nguồn bằng lệnh `exec(executable_code, exec_globals)` ngay trong tiến trình chính.
   - **Hậu quả rủi ro:**
     - **Không có cơ chế Timeout cứng:** Nếu LLM sinh ra một đoạn mã có vòng lặp vô hạn (`while True` hoặc logic `while` không có điều kiện dừng) hoặc một phép JOIN Cartesian làm cạn RAM, toàn bộ tiến trình suy luận 1.000 câu sẽ bị treo cứng vĩnh viễn!
     - **Nguy cơ làm bẩn In-Memory Cache:** Nếu mã của LLM vô tình thực hiện thao tác sửa đổi DataFrame trực tiếp tại chỗ (in-place) như `data['orders'].drop(...)` hoặc gán lại cột, dữ liệu của shop đó trong bộ nhớ RAM sẽ bị sai lệch, làm hỏng kết quả của tất cả các câu hỏi tiếp theo của cùng shop đó.
3. **Lỗi logic cắt dòng trong `ingestion/metadata.py`:**
   - Hàm `_try_parse_dates` đang áp dụng `.head(2000)` để dò tìm mốc thời gian. Đối với các cửa hàng lớn có hàng chục nghìn dòng giao dịch trong nhiều năm, mốc `max_date` sẽ bị cắt cụt ở dòng thứ 2.000, khiến thông tin khoảng thời gian của shop bị sai lệch nghiêm trọng.
4. **Kho ví dụ Few-shot trong `prompt_builder.py` còn thiếu các bài toán đặc thù:**
   - Chưa có ví dụ hướng dẫn bài toán tính tồn kho theo lô nhập/bán/trả và quy đổi đơn vị (ví dụ: chia lấy dư `divmod` để trả về danh sách `[số hộp chẵn, số viên lẻ]`).
   - Chưa có ví dụ mẫu cho bài toán chuỗi thời gian nhiều tháng (xác định xu hướng tăng liên tục hoặc tỷ lệ tăng trưởng so với tháng liền trước).
5. **Hạ tầng đóng gói Docker và Huấn luyện mô hình đang ở con số 0:**
   - `Dockerfile` và `train.sh` hoàn toàn rỗng.
   - Chưa hề có một trọng số mô hình tinh chỉnh (fine-tuned checkpoint) nào. Toàn bộ hệ thống hiện đang chạy suy luận dạng Zero-shot / Few-shot trên mô hình gốc của hãng (`Qwen2.5-Coder-7B-Instruct`).

---

## 5. Kế Hoạch & Hướng Giải Pháp Tương Lai (Lộ Trình Minh Bạch)

Để hoàn thiện hệ thống và đạt kết quả cao trong cuộc thi, các bước triển khai tiếp theo cần tập trung giải quyết triệt để các vấn đề nêu trên theo lộ trình:

```
[BƯỚC 1: HÀN GẮN PHÂN MẢNH] -> [BƯỚC 2: CHẠY BENCHMARK ĐO PA] -> [BƯỚC 3: FINE-TUNING & DATA SYNTH] -> [BƯỚC 4: DOCKER & SUBMISSION]
   (04/11 - 05/11)                  (06/11)                          (07/11 - 12/11)                      (13/11 - 16/11)
```

---

### Bước 1: Hàn gắn sự phân mảnh & Gia cố an toàn thực thi (04/11 – 05/11)
Đây là việc cần làm ngay lập tức trước khi tiến hành chạy bất kỳ thử nghiệm benchmark nào:

1. **Tích hợp Rule 8 Cleaner vào `predict.py`:**
   - Trong hàm `load_business_data` của `predict.py`, gọi `clean_business(bd)` để dữ liệu nạp vào `data_dict` và `to_sqlite(bd, clean=True)` đều là dữ liệu đã được forward-fill ô trống và khử trùng lặp theo đúng Quy tắc 8.
2. **Thay thế `exec()` nội bộ bằng cơ chế thực thi an toàn có Timeout:**
   - Đưa cơ chế timeout (10 giây/câu) vào việc thực thi hàm `solution(data)`. Có thể dùng `multiprocessing` / subprocess cô lập từ `execution/sandbox.py` hoặc luồng kiểm soát thời gian.
   - Trước khi truyền `data_dict` vào cho mã của LLM thực thi, tạo bản sao nông (shallow copy) hoặc cấm ghi để tránh việc mã làm biến dạng dữ liệu cache của shop.
3. **Thống nhất bộ giải mã thời gian:**
   - Loại bỏ hàm duplicate trong `prompt_builder.py`. Cho `prompt_builder.py` gọi trực tiếp `datamate.grounding.temporal.resolve_temporal` để tận dụng đầy đủ khả năng giải mã lịch âm, ngày lễ, Tết, nửa đầu/cuối tháng.
4. **Kết nối `entity_linker.py` vào prompt:**
   - Bổ sung bước tra cứu thực thể: nếu câu hỏi chứa từ viết tắt (*"cf"*, *"sp"*, *"dthu"*) hoặc tên sản phẩm viết thiếu dấu, bóc tách và cung cấp gợi ý tên bảng/cột/giá trị khớp nhất vào prompt gửi cho LLM.
5. **Sửa lỗi trích xuất ngày trong `ingestion/metadata.py`:**
   - Loại bỏ `.head(2000)` trong `_try_parse_dates`, lấy mẫu đại diện thông minh hơn (ví dụ kết hợp 500 dòng đầu và 500 dòng cuối) hoặc tính trực tiếp trên toàn bộ cột ngày giao dịch chính.

---

### Bước 2: Chạy Benchmark Nội bộ & Phân Tích Lỗi Thực Nghiệm (Mốc 06/11)
- **Mục tiêu:** Đạt Milestone 2 của Phase 2 — đo đạc chỉ số PA nội bộ trên tập validation của `business_holdout_v1` (khoảng 600 câu hỏi trên các doanh nghiệp chưa từng thấy).
- **Hành động cụ thể:**
  1. Chạy `predict.py` trên tập `benchmark/splits/business_holdout_v1/fold_0/val_questions.jsonl`.
  2. Dùng `benchmark/evaluate.py` để tính điểm số Penalized Accuracy thực tế (mục tiêu: $\text{PA} \ge 0.50$).
  3. Dùng `benchmark/error_analysis.py` để xuất báo cáo phân loại lỗi: bao nhiêu câu đúng (+1), bao nhiêu câu sai (-1), bao nhiêu câu `unanswerable` bắt đúng, và các nguyên nhân gây mất điểm chính (do lỗi cú pháp, sai công thức, hay sai định dạng).

---

### Bước 3: Core Enhancement & Huấn Luyện Mô Hình (Phase 3: 07/11 – 12/11)
- **1. Sinh dữ liệu tổng hợp (Data Augmentation - Phát chủ trì):**
  - Từ 3.000 câu tập train, sinh thêm 15.000 – 20.000 mẫu đa dạng:
    + Paraphrase ngôn ngữ tự nhiên (teencode, câu không dấu, viết tắt thực tế).
    + Các câu hỏi về mùa vụ Tết âm lịch và so sánh kỳ liền trước.
    + Các câu hỏi `unanswerable` có chủ đích (hỏi dữ liệu ngoài khoảng năm, hỏi thông tin không có trong POS).
- **2. Fine-tuning Mô hình Backbone (Long chủ trì):**
  - Viết `train.sh` thực hiện SFT (Supervised Fine-Tuning) bằng LoRA/QLoRA cho mô hình `Qwen2.5-Coder-7B` (hoặc `14B` nếu tài nguyên cho phép).
  - Dạy mô hình tuân thủ tuyệt đối quy tắc Rulebook: loại đơn hủy/trả khi tính doanh thu, áp dụng công thức làm tròn số nguyên cho tiền VND, tự động sort mã tăng dần khi có đồng hạng (Điều 9).
- **3. Nén Schema & Hoàn thiện Few-shot:**
  - Nén cấu trúc bảng (schema compression) để tiết kiệm token ngữ cảnh.
  - Bổ sung 2 ví dụ few-shot trọng tâm: tính tồn kho theo lô quy đổi đơn vị (`divmod`) và phân tích chuỗi thời gian nhiều kỳ.

---

### Bước 4: Calibrated Abstention, Đóng Gói Docker & Nộp Bài (Phase 4: 13/11 – 16/11)
- **1. Hiệu chuẩn Cổng Từ chối (Calibrated Abstention Gate - Long):**
  - Xây dựng điểm tin cậy $C \in [0, 1]$ cho mỗi đáp án dựa trên: độ tin cậy thực thi, tính hợp lý của dữ liệu (không âm, không rỗng), và độ khớp thực thể.
  - Quét tìm ngưỡng tối ưu $\tau^*$ trên tập validation. Những câu có $C < \tau^*$ sẽ tự động xuất `abstain` (nhận 0 điểm an toàn, cứu vãn toàn bộ bảng xếp hạng trước các ca đoán mò).
- **2. Đóng gói Docker Offline 100% (Phát):**
  - Viết hoàn thiện `Dockerfile` đóng gói toàn bộ mã nguồn, môi trường PyTorch/vLLM/CUDA và trọng số mô hình đã nạp sẵn cục bộ trong container.
  - Đảm bảo kiểm thử thành công với cờ `--network none` (hoàn toàn không gọi mạng Internet khi chạy thi đấu).
  - Tối ưu thời gian chạy toàn bộ tập kiểm thử dưới 4 giờ (dưới trần 6 giờ của BTC).
- **3. Bàn giao & Nộp bài trước hạn chót:**
  - Ngày 15/11: Hoàn tất đóng gói image, tính mã băm SHA256 Checksum, upload Google Drive công khai.
  - Trước 18:00 ngày 16/11: Nộp bài chính thức lên hệ thống Zalo AI Challenge (sớm hơn hạn chót 23:59 ít nhất 6 tiếng để loại trừ mọi rủi ro về đường truyền).

---

## 6. Lời Kết

Hệ thống DataMate hiện tại đã có một **bộ khung nền tảng rất tốt và đúng hướng**: các lá chắn quy tắc nghiệp vụ (Feasibility Gate và Normalizer) được xây dựng kỹ lưỡng và hoạt động chuẩn xác; pipeline suy luận đã thông suốt và chuyển đổi thành công sang mô hình 7B.

Tuy nhiên, **nút thắt lớn nhất lúc này là sự phân mảnh**: mã nguồn của Phát và Long đã viết rất nhiều nhưng chưa được kết nối hoàn chỉnh vào tiến trình chạy chính `predict.py`. Việc giải quyết triệt để nút thắt tích hợp này trong 24–48 giờ tới là điều kiện tiên quyết để hệ thống có thể bước vào giai đoạn chạy Benchmark nội bộ (06/11) và bước vào chiến dịch Fine-tuning nâng cao (07/11 – 12/11) một cách vững chắc nhất.

