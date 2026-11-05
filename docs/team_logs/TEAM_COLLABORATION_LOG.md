# Nhật Ký Làm Việc Nhóm & Phối Hợp Kỹ Thuật (Team Collaboration Log)
**Dự án:** DataMate — Zalo AI Challenge 2026  
**Thành viên:** **Long** (AI Architect & Model Lead) & **Phát** (Data Engineer & System Lead)  
**Nguyên tắc làm việc:** Song song, minh bạch kỹ thuật, kiểm thử chéo (Cross-Support), tôn trọng hợp đồng giao diện API (API Contracts).

---

## 📅 SPRINT 1: FAST PIPELINE & FIRST SUBMISSION (31/10 – 02/11/2026)

### 🗓️ Daily Standup: 31/10/2026
- **Long:** 
  - Đã xong: Khởi tạo module `llm/client.py` nạp mô hình qua `bitsandbytes` 4-bit (NF4). Thiết lập Greedy Decoding ($T=0$) để đảm bảo tính tái lập.
  - Kế hoạch: Viết prompt template cơ bản nạp schema và câu hỏi.
  - Cần Phát hỗ trợ: Cung cấp 10 câu hỏi mẫu tiêu biểu từ tập train để kiểm tra prompt.
- **Phát:**
  - Đã xong: Dựng cấu trúc thư mục repo chuẩn (`src/`, `config/`, `docs/`, `tests/`). Viết parser đọc thô dữ liệu CSV, XLSX, SQLite.
  - Kế hoạch: Viết `SubmissionWriter` xuất file `submission.jsonl` đúng chuẩn format BTC.
  - Cần Long hỗ trợ: Xác nhận định dạng dictionary trả về của hàm `solution(data)`.
- **Thỏa thuận chung (API Contract):**
  - Hàm do mô hình sinh ra phải có chữ ký duy nhất: `def solution(data):` nhận vào `data` là dictionary `{table_name: DataFrame}` và trả về đáp án thô.

---

### 🗓️ Daily Standup: 01/11/2026
- **Long:**
  - Đã xong: Hoàn thành bộ bóc tách mã nguồn `extract_code_block` trong `client.py`, tích hợp kiểm tra cú pháp AST để loại bỏ các đoạn văn bản thừa của mô hình.
  - Kế hoạch: Ghép với runner thực thi của Phát.
- **Phát:**
  - Đã xong: Hoàn thành `SubmissionWriter` với cơ chế ghi từng dòng kèm `flush()` và `os.fsync()`, không lo mất dữ liệu nếu bị ngắt tiến trình đột ngột.
  - Đang vướng: Một số file Excel có hàng tiêu đề POS bị lệch ở dòng 2 hoặc 3 khiến đọc bảng bị lỗi tên cột.
  - Hướng xử lý: Phát sẽ viết thuật toán dò tự động hàng tiêu đề (`header_row_detected`) trong `loader.py`.

---

### 🗓️ Review & Milestone 1: 02/11/2026
- **Biên bản nghiệm thu Milestone 1 (Tối 02/11):**
  - Long và Phát chạy thử nghiệm E2E pipeline trên `public_test` (1.000 câu).
  - Kết quả: `validate_submission` trả về 0 lỗi định dạng format.
  - Nộp bài lần đầu tiên thành công lên hệ thống Zalo AI Challenge. Ghi nhận mốc điểm Baseline đầu tiên làm căn cứ đo đạc cải tiến.

---

## 📅 SPRINT 2: DETERMINISTIC SHIELDS & RULEBOOK ENGINES (03/11 – 06/11/2026)

### 🗓️ Daily Standup: 03/11/2026
- **Long:**
  - Đã xong: Xây dựng Module 3 (`feasibility.py` - Deterministic Feasibility Gate). Bắt trọn 70/70 câu `unanswerable` trên tập train (Recall 100%, Precision 100%), bao gồm cả Điều 7 (ngoài khoảng ngày) và câu hỏi cảm tính/thiếu bảng.
  - Đã xong: Xây dựng Module 6 (`normalizer.py` - Format Normalizer & Tie-Breaker). Xử lý chuẩn 8 kiểu dữ liệu và xếp hạng phụ theo mã code tăng dần theo Điều 9 Rulebook.
- **Phát:**
  - Đã xong: Xây dựng Module 1 (`cleaner.py` - Quy tắc 8): Group forward-fill các ô trống cấp đơn hàng và khử trùng lặp dòng lỗi POS xuất file.
  - Đã xong: Xây dựng Module 2 (`grounding/temporal.py` và `lunar_calendar.py`): Tra cứu lịch âm, ngày Tết, rằm, mùng 1.
  - Đã xong: Viết `benchmark/split.py` (5-fold business holdout) và `benchmark/evaluate.py` (chấm điểm PA chuẩn BTC).

---

### 🗓️ Technical Sync & Code Review: 04/11/2026 (Giữa Phase 2)
> **Mục tiêu phiên họp:** Rà soát mã nguồn toàn diện và xử lý sự phân mảnh giữa các module độc lập với pipeline chạy chính `predict.py`.

#### 1. Phát hiện & Phản hồi kỹ thuật (Code Review Feedback):
- **Long phản hồi mã nguồn của Phát:**
  1. `loader.py` và `cleaner.py`: Module `cleaner.py` của Phát viết rất tốt nhưng hàm `load_business_data` trong `predict.py` chưa gọi `clean_business(bd)`, khiến dữ liệu đưa vào LLM vẫn còn ô trống chưa forward-fill.
  2. `ingestion/metadata.py`: Phát hiện lỗi `.head(2000)` trong `_try_parse_dates` làm cắt cụt ngày kết thúc của các shop có nhiều hơn 2.000 giao dịch. Cần Phát sửa trong hôm nay.
  3. `execution/sandbox.py`: Danh sách `ALLOWED_MODULES` còn thiếu `calendar`, `operator`, `copy`. Cần bổ sung trước khi thay lệnh `exec()` nội bộ.
- **Phát phản hồi mã nguồn của Long:**
  1. `prompt_builder.py`: Long đang tự viết một hàm `resolve_temporal_context` riêng có bảng Tết tĩnh, chưa tận dụng được module `grounding/temporal.py` và `lunar_calendar.py` của Phát.
  2. Few-shot library: Cần bổ sung ví dụ về tồn kho theo lô quy đổi đơn vị (`divmod`) và chuỗi thời gian nhiều kỳ (`time_series`).
  3. Sanity check: Cần có cơ chế kiểm tra kết quả sau thực thi để phát hiện số âm bất thường hoặc số 0 vô lý cho câu hỏi xếp hạng, chủ động ép về `abstain` (0 điểm) thay vì đoán sai bị phạt -1 điểm.

#### 2. Kế hoạch hành động thống nhất (Action Items) & Kết quả xử lý:
| Đầu việc | Người phụ trách | Trạng thái | Ghi chú kỹ thuật |
|---|:---:|:---:|---|
| Chuyển toàn bộ hệ thống sang Qwen2.5-Coder 7B | **Long** | ✅ **Xong** | 4-bit NF4, VRAM ~5.5GB, cập nhật `config`, `client.py`, `predict.py`. |
| Tích hợp `grounding.temporal` vào `prompt_builder.py` | **Long** | ✅ **Xong** | Hỗ trợ nửa đầu/cuối tháng, 10 ngày đầu/giữa/cuối, rằm/mùng 1 âm; hiển thị cả Kỳ chính và Kỳ đối chiếu. |
| Bổ sung few-shot `inventory_unit_conversion` & `time_series` | **Long** | ✅ **Xong** | Đã thêm vào `FEW_SHOT_LIBRARY`, cập nhật intent classifier, 19/19 test pass. |
| Xây dựng Sanity Check & Self-Correction trong `predict.py` | **Long** | ✅ **Xong** | Viết `check_result_sanity`, bắt số âm doanh thu/số lượng, ép về abstain an toàn. |
| Xây dựng Module Calibrated Abstention Gate | **Long** | ✅ **Xong** | Viết `src/datamate/output/abstention.py` kèm unit test 4/4 pass. |
| Viết kịch bản huấn luyện SFT / QLoRA (`train.py`, `train.sh`) | **Long** | ✅ **Xong** | Dry-run thành công trên 2.406 mẫu fold 0, sẵn sàng cho Phase 3. |
| Tích hợp Rule 8 Cleaner vào `predict.py` | **Phát** | ⏳ Đang làm | Nối `clean_business` vào `load_business_data` trong `predict.py`. |
| Sửa lỗi `.head(2000)` trong `metadata.py` | **Phát** | ⏳ Đang làm | Loại bỏ `.head(2000)` khi dò ngày giao dịch. |
| Bổ sung whitelist và timeout cho Sandbox | **Phát** | ⏳ Đang làm | Thêm `calendar` vào `ALLOWED_MODULES`, thay thế `exec()` trong `predict.py`. |

---

## 📅 SPRINT 3: CORE ENHANCEMENT & FINE-TUNING PREPARATION (07/11 – 12/11/2026)

### 📋 Biên bản thỏa thuận giao diện & Dữ liệu (Handover Contract):
- **Phát (Bàn giao dữ liệu):**
  - Phát chịu trách nhiệm sinh 15.000 – 20.000 cặp câu hỏi-code tổng hợp (`synthetic_train.jsonl`):
    + 60% câu hỏi nghiệp vụ thông thường (paraphrase teencode, viết tắt: *"dthu", "hnay", "bnhiu"*).
    + 20% câu hỏi mùa vụ Tết âm lịch và so sánh kỳ liền trước.
    + 20% câu hỏi bất khả thi (`unanswerable`) có chủ đích.
  - Yêu cầu chất lượng từ Long: Phát phải lọc sạch 100% dữ liệu trước khi bàn giao (chạy qua syntax check AST và kiểm tra không vi phạm công thức doanh thu Rulebook).
- **Long (Tiếp nhận & Huấn luyện):**
  - Long đã chuẩn bị sẵn `train.py` và `train.sh`. Ngay khi nhận được `synthetic_train.jsonl` từ Phát:
    + Chạy SFT QLoRA 4-bit trên GPU (`epochs=3`, `lr=2e-4`, `rank=16`, `alpha=32`).
    + Đo điểm PA nội bộ trên tập validation Fold 0 của `business_holdout_v1`.
    + Khóa checkpoint mô hình tốt nhất vào ngày 12/11 (Mục tiêu: $\text{PA} \ge 0.70 - 0.80+$).

---

## 📅 SPRINT 4: DOCKER CONTAINERIZATION & SUBMISSION (13/11 – 16/11/2026)

### 📋 Checklist Nghiệm Thu Cuối Cùng (Final Verification Checklist):
- [ ] **Docker 100% Offline (Phát):**
  - Kiểm thử container với cờ `--network none`. Không thực hiện bất kỳ lệnh tải mạng nào khi chạy.
  - Image tương thích GPU RTX 5090 (PyTorch, CUDA 12.8+, vLLM / transformers).
- [ ] **Calibrated Abstention (Long):**
  - Chạy `find_optimal_threshold` trên tập validation để chọn ngưỡng $\tau^*$ tối ưu, bảo vệ bảng xếp hạng khỏi các câu hỏi rủi ro đoán sai.
- [ ] **Tính tái lập tuyệt đối (Long & Phát):**
  - Cố định random seed, chạy 2 lần độc lập: $|PA_1 - PA_2| = 0$, đảm bảo thỏa mãn quy chế $|PA_{uploaded} - PA_{rerun}| \le 0.03$.
- [ ] **Bàn giao nộp bài (Phát chủ trì, Long review):**
  - Upload image lên Google Drive công khai, tính mã SHA256 checksum chính xác.
  - Nộp bài trước **18:00 ngày 16/11/2026** (trước hạn chót 23:59 ít nhất 6 giờ).

