# Kế hoạch Triển khai & Phân bổ Công việc (Timeline & Contribution)
## Dự án: DataMate — Zalo AI Challenge 2026

> **Thời gian thực hiện:** 31/10/2026 – 16/11/2026 (17 ngày sprint)  
> **Thành viên đội thi (2 người):** **Long** & **Phát**  
> **Nguyên tắc cốt lõi:** Làm việc song song (Parallel execution), hỗ trợ chéo đa tầng (Mutual Cross-Support) — không để bất kỳ giai đoạn nào chỉ có một người gánh vác, tập trung tối đa vào nâng cao chất lượng mô hình và điểm số Penalized Accuracy (PA).

---

## 👥 1. Hồ sơ Năng lực & Phân công Vai trò (Team Profile & Roles)

Đội thi gồm **2 thành viên** phối hợp chặt chẽ theo mô hình cộng tác song song:

### 1. Long — AI Architect & Model Lead
- **Thế mạnh chuyên môn:** Mô hình ngôn ngữ lớn (LLM), kỹ thuật Prompting nâng cao, Fine-tuning (SFT / DPO / RLVR), tối ưu inference với vLLM, đánh giá độ tin cậy mô hình (Evaluation & Calibration).
- **Nhiệm vụ chính (Primary Ownership):**
  - Thiết kế prompt chuyên sâu và chiến lược In-Context Demonstration.
  - Tinh chỉnh mô hình backbone $\le 15\text{B}$ tham số (`Qwen2.5-Coder-14B-Instruct`).
  - Xây dựng Module 3: Deterministic Feasibility Gate (lá chắn tự động phát hiện câu hỏi ngoài phạm vi để trả về `unanswerable`).
  - Xây dựng Module 6: Format Normalizer (chuẩn hóa 8 kiểu dữ liệu của BTC) và Calibrated Abstention Gate (tính độ tin cậy để chủ động từ chối `abstain` tránh bị phạt).
  - Thiết lập vòng lặp tự sửa lỗi (Self-Correction Loop) trong sandbox.
- **Nhiệm vụ hỗ trợ Phát (Cross-Support):**
  - Hướng dẫn cấu trúc dữ liệu đầu vào cho mô hình, review logic nghiệp vụ của Rulebook.
  - Hỗ trợ viết test script kiểm tra tính toàn vẹn của mô hình trong container Docker.

### 2. Phát — Data Engineer & System Lead
- **Thế mạnh chuyên môn:** Xử lý dữ liệu bảng tính (ETL, Pandas, Openpyxl, Polars), CSDL quan hệ (SQLite, DuckDB, Indexing), hiểu sâu quy tắc Rulebook và có nền tảng xây dựng mô hình AI cơ bản, Docker containerization.
- **Nhiệm vụ chính (Primary Ownership):**
  - Xây dựng Module 1: Ingestion & Rule 8 Cleaner (tự động forward-fill ô trống theo nhóm dòng và khử trùng lặp dòng lỗi POS).
  - Xây dựng Module 1: In-Memory SQLite Mirror (nạp toàn bộ dữ liệu sạch vào RAM và đánh index các khóa ngoại).
  - Xây dựng Module 2: Temporal Grounder (giải mã thời gian tương đối kết hợp `calendar.csv` và lịch âm/dương Tết).
  - Xây dựng Module 2: Entity Linker (BM25 + Fuzzy matching tiếng Việt).
  - Sinh dữ liệu tổng hợp (Data Augmentation 15.000 – 20.000 mẫu).
  - Đóng gói Docker hoàn toàn offline (`--network none`, tương thích RTX 5090) và viết script `predict.sh`.
- **Nhiệm vụ hỗ trợ Long (Cross-Support):**
  - Lọc sạch (Data Cleaning) bộ dữ liệu tổng hợp trước khi nạp vào huấn luyện SFT.
  - Hỗ trợ chạy benchmark kiểm thử song song các checkpoint mô hình trên các tập dữ liệu doanh nghiệp khác nhau.

---

## 📅 2. Tổng quan 4 Giai đoạn Sprint (Timeline Overview)

| Giai đoạn | Thời gian | Trọng tâm công việc | Mốc nghiệm thu (Milestone) |
|---|---|---|---|
| **Phase 1: Fast Pipeline** | 31/10 – 02/11<br>*(3 ngày)* | Dựng khung mã nguồn đầu-cuối tối giản (E2E), thông luồng chạy từ đọc dữ liệu $\to$ sinh code $\to$ xuất file nộp. | **Milestone 1 (Tối 02/11):** Nộp bài lần đầu tiên lên Public Leaderboard để kiểm tra hệ thống và lấy điểm Baseline. |
| **Phase 2: Deterministic Shields** | 03/11 – 06/11<br>*(4 ngày)* | Xây dựng lá chắn quy tắc nghiệp vụ: Rule 8 forward-fill, SQLite RAM mirror, Temporal Grounder (lịch Tết) và Feasibility Gate (chống phạt điểm âm). | **Milestone 2 (06/11):** Hoàn thiện bộ đánh giá nội bộ (Internal Benchmark) trên 3.000 câu tập train, PA nội bộ $\ge 0.50$. |
| **Phase 3: Core Enhancement**<br>*(Chiếm 60% thời gian)* | 07/11 – 12/11<br>*(6 ngày)* | Sinh 15k–20k dữ liệu tổng hợp, Fine-tune `Qwen2.5-Coder-14B` (SFT/DPO), tối ưu hóa prompt, nén schema và vòng lặp tự sửa lỗi Sandbox. | **Milestone 3 (12/11):** Khóa trọng số mô hình tốt nhất (Best Model Weights), PA nội bộ $\ge 0.70 - 0.80+$. |
| **Phase 4: Polish, Docker & Submit** | 13/11 – 16/11<br>*(4 ngày)* | Hiệu chuẩn cổng từ chối $\tau$, cố định random seed tái lập, đóng gói Docker 100% offline và nộp bài trước hạn chót. | **Milestone 4 (16/11):** Đóng gói Docker hoàn tất ngày 15/11; nộp bài chính thức trước 18:00 ngày 16/11 (trước hạn chót 23:59). |

---

## 📋 3. Chi tiết Phân bổ Công việc & Kết quả Đầu ra theo Từng Giai đoạn

---

### GIAI ĐOẠN 1: Fast Pipeline & First Submission (31/10 – 02/11 · 3 ngày)
> **Mục tiêu then chốt:** Dựng khung mã nguồn đầu-cuối tối giản, thông luồng nộp bài và có điểm Public Leaderboard đầu tiên trong 48h. Tuyệt đối không sa đà vào vẽ giao diện hay tranh cãi ý tưởng.

| Thành viên | Nhiệm vụ chính (Primary Tasks) | Nhiệm vụ hỗ trợ (Cross-Support Tasks) |
|---|---|---|
| **Long** | - Dựng baseline gọi mô hình mã nguồn mở có sẵn (`Qwen2.5-Coder-7B` hoặc `14B` zero-shot) sinh code Python/SQL.<br/>- Viết prompt template cơ bản nạp schema và câu hỏi.<br/>- Đảm bảo cơ chế Greedy Decoding ($T=0$). | - Hỗ trợ Phát kiểm tra cú pháp đầu ra của mô hình để hoàn thiện runner thực thi.<br/>- Review format file JSONL nộp bài theo đúng tài liệu BTC. |
| **Phát** | - Viết parser nạp dữ liệu thô (đọc các file `.xlsx`, `.csv`, `.sqlite` trong `competition_data`).<br/>- Viết execution runner tối giản chạy code Python và bắt kết quả thô.<br/>- Xây dựng module xuất file `submission.jsonl` đúng chuẩn format. | - Trích xuất 10 câu hỏi mẫu tiêu biểu từ tập train (đủ các dạng tiền tệ, ngày tháng, tên sản phẩm) gửi cho Long kiểm tra prompt.<br/>- Chuẩn bị môi trường code dùng chung (git repo, conda environment). |
| **Phối hợp chung** | **Milestone 1 (Hạn: Tối 02/11):** Chạy pipeline trên `public_test`, xuất `submission.jsonl` và **nộp lần đầu tiên** lên hệ thống Zalo AI Challenge để kiểm tra hệ thống chấm và ghi nhận mốc điểm Baseline ban đầu. | |

#### 🎯 Kết quả Đầu ra Kỳ vọng (Expected Outputs — Phase 1):
1. **Pipeline E2E hoạt động ổn định:** Toàn bộ luồng từ đọc dữ liệu $\to$ LLM sinh code $\to$ thực thi Python $\to$ ghi kết quả file JSONL chạy mượt mà không crash.
2. **File submission hợp lệ:** Xuất file `submission.jsonl` cho `public_test` được hệ thống Zalo AI Challenge chấp nhận chấm điểm thành công (0 lỗi định dạng format).
3. **Mốc điểm Baseline:** Có điểm số Public Leaderboard đầu tiên làm thước đo đối chứng trước khi thực hiện các cải tiến nâng cao.
4. **Môi trường thống nhất:** Repo Git chuẩn cấu trúc (`src/`, `docs/`, `config/`), môi trường conda/venv đồng bộ giữa Long và Phát.

---

### GIAI ĐOẠN 2: Deterministic Shields & Rulebook Engines (03/11 – 06/11 · 4 ngày)
> **Mục tiêu then chốt:** Xây dựng các lá chắn quy tắc nghiệp vụ tất định. Ngăn chặn hoàn toàn việc bị trừ -1 điểm và ăn trọn +1 điểm trên các câu hỏi `unanswerable`.

| Thành viên | Nhiệm vụ chính (Primary Tasks) | Nhiệm vụ hỗ trợ (Cross-Support Tasks) |
|---|---|---|
| **Long** | - **Xây dựng Module 3 (Deterministic Feasibility Gate):** Tự động phát hiện câu hỏi ngoài phạm vi ngày $\to$ trả về `unanswerable` (+1 điểm, không để LLM đoán mò).<br/>- **Xây dựng Module 6 (Format Normalizer):** Chuẩn hóa tuyệt đối 8 định dạng (tiền tệ VND số nguyên, percent không dấu %, string giữ nguyên dấu, boolean, date ISO).<br/>- Viết logic Rule 9 giải quyết đồng hạng (sort theo mã code tăng dần). | - Hỗ trợ Phát viết bộ test tự động (unit tests) cho SQLite In-Memory và Temporal Grounder.<br/>- Rà soát các trường hợp biên của Rulebook (đơn hủy, trả hàng, giá vốn lô bình quân). |
| **Phát** | - **Xây dựng Module 1 (Rule 8 Data Cleaner):** Tự động group forward-fill các ô trống cấp đơn hàng; khử trùng lặp dòng lỗi xuất file.<br/>- **In-Memory SQLite Mirror:** Nạp toàn bộ sheet vào SQLite RAM disk, đánh index khóa chính/ngoại (`Mã đơn`, `Ngày`, `SKU`, `Khách hàng`).<br/>- **Xây dựng Module 2 (Temporal Grounder):** Xử lý `as_of_date` và `calendar.csv`: giải mã "hôm nay", "tuần này", "Tết năm Y", lọc bỏ dữ liệu sau ngày mốc. | - Cung cấp hàm trích xuất Metadata ($[\text{min\_date}, \text{max\_date}]$, danh sách cột của từng shop) để nạp thẳng vào Feasibility Gate của Long.<br/>- Cùng Long kiểm tra các case lệch múi giờ hoặc sai lịch âm. |
| **Phối hợp chung** | **Milestone 2 (Hạn: 06/11):** Xây dựng bộ công cụ **Internal Benchmark**: Tách 3.000 câu tập train thành 2.400 câu train và 600 câu validation để đo điểm Penalized Accuracy nội bộ tự động sau mỗi lần commit. | |

#### 🎯 Kết quả Đầu ra Kỳ vọng (Expected Outputs — Phase 2):
1. **Module Rule 8 Cleaner:** 100% các ô trống forward-fill cấp đơn hàng được điền chuẩn xác; không còn dòng trùng lặp do lỗi xuất file POS.
2. **SQLite In-Memory Mirror:** Thời gian nạp dữ liệu toàn bộ bảng tính của một doanh nghiệp vào RAM $< 1\text{s}$, truy vấn SQL mili-giây.
3. **Temporal Grounder:** Chuyển đổi chính xác 100% các mốc thời gian ("hôm nay", "tuần này", "tháng trước", "Tết năm 2025/2026") sang khoảng ngày cụ thể; lọc triệt để dữ liệu tương lai $> \text{as\_of\_date}$.
4. **Feasibility Gate (Shield chống phạt):** Phát hiện chính xác câu hỏi nằm ngoài khoảng ngày của shop $\to$ Trả về `unanswerable`, đạt 100% độ chính xác cho nhóm câu này.
5. **Format Normalizer & Tie-Breaker:** Đầu ra tuân thủ tuyệt đối định dạng BTC, tự động xếp hạng phụ theo mã code tăng dần khi có đồng hạng.
6. **Internal Benchmark Suite:** Bộ script tự động đánh giá tập dev (600 câu) xuất ra báo cáo chi tiết: Số câu đúng (+1), số câu sai (-1), số câu unanswerable đúng, và điểm PA tổng thể.
7. **Mục tiêu điểm số:** Điểm PA nội bộ đạt mốc **$\ge 0.50$**.

---

### GIAI ĐOẠN 3: Core Enhancement & Fine-Tuning Sprint (07/11 – 12/11 · 6 ngày)
> **Mục tiêu then chốt:** Dành tới **60% tổng nguồn lực** vào giai đoạn này để tạo ra bước đột phá vượt bậc. Tập trung tối đa vào Fine-Tuning mô hình $\le 15\text{B}$, làm giàu dữ liệu và hoàn thiện vòng lặp tự sửa lỗi.

| Thành viên | Nhiệm vụ chính (Primary Tasks) | Nhiệm vụ hỗ trợ (Cross-Support Tasks) |
|---|---|---|
| **Long** | - **Fine-tuning Mô hình Backbone $\le 15\text{B}$:** Tinh chỉnh `Qwen2.5-Coder-14B-Instruct` qua SFT (học cú pháp sinh code chuẩn Rulebook) và DPO nếu đủ tài nguyên GPU.<br/>- **Schema Compression & Few-shot RAG:** Nén cấu trúc bảng (chỉ nạp tên cột, kiểu dữ liệu, 3 dòng mẫu) và tự động chọn 2-3 ví dụ in-context tương đồng.<br/>- **Xây dựng Self-Correction Loop trong Sandbox:** Bắt ngoại lệ runtime/syntax, gửi traceback về cho LLM sửa (tối đa 2 vòng). | - Hướng dẫn Phát viết prompt sinh dữ liệu tổng hợp chuẩn xác.<br/>- Chia sẻ checkpoint mô hình để Phát cùng tham gia kiểm thử suy luận.<br/>- Cùng Phát phân tích các câu hỏi bị phạt điểm (-1) sau mỗi vòng eval. |
| **Phát** | - **Sinh Dữ liệu Huấn luyện Mở rộng (Data Augmentation):** Từ 3.000 câu train, sinh thêm 15.000 – 20.000 mẫu:<br/>  + Paraphrase tiếng Việt (teencode, viết tắt: "dthu", "hnay", "bnhiu", câu không dấu).<br/>  + Sinh các câu hỏi `unanswerable` có chủ đích (hỏi ngoài khoảng năm, hỏi thông tin shop không có).<br/>  + Mở rộng các câu hỏi liên quan đến mùa vụ Tết âm lịch.<br/>- **Xây dựng Entity Linker:** Thuật toán BM25 + Fuzzy matching tiếng Việt chuẩn hóa để map chính xác tên sản phẩm, size cà phê, khách hàng. | - Lọc sạch (Data Cleaning) bộ dữ liệu tổng hợp: loại bỏ các mẫu sinh bị sai đáp án hoặc sai quy định Rulebook trước khi nạp vào train SFT.<br/>- Hỗ trợ Long chạy benchmark song song trên các split doanh nghiệp khác nhau.<br/>- Đóng vai trò phản biện (tester) kiểm tra các case code sinh ra chạy quá thời gian (timeout). |
| **Phối hợp chung** | **Milestone 3 (Hạn: 12/11):** Thực hiện **Error Analysis hàng ngày**. Chốt phiên bản prompt và **khóa checkpoint mô hình tốt nhất (Best Model Weights)** đạt PA cao nhất trên tập validation. Nộp bài tối ưu lên Public Leaderboard. | |

#### 🎯 Kết quả Đầu ra Kỳ vọng (Expected Outputs — Phase 3):
1. **Tập dữ liệu tổng hợp (Synthetic Dataset):** 15.000 – 20.000 cặp câu hỏi-code đã được kiểm tra chất lượng (không bị sai công thức doanh thu, đơn hủy).
2. **Checkpoint Mô hình Tinh chỉnh:** Mô hình `Qwen2.5-Coder-14B-Instruct-DataMate` chạy offline bằng vLLM, hiểu sâu tiếng Việt đời thường và quy tắc Rulebook.
3. **Bộ Entity Linker tiếng Việt:** Độ chính xác khớp tên sản phẩm/khách hàng viết tắt, teencode, thiếu dấu đạt $\ge 90\%$.
4. **Vòng lặp Self-Correction trong Sandbox:** Tự sửa thành công $\ge 60\%$ các lỗi cú pháp SQL/Python ngay trong vòng thử thứ 2.
5. **Nhật ký Phân tích Lỗi (Daily Error Log):** Xác định và triệt tiêu toàn bộ các lỗi làm mất điểm lặp đi lặp lại.
6. **Mục tiêu điểm số:** Điểm PA nội bộ đạt mốc **$\ge 0.70 - 0.80+$**.

---

### GIAI ĐOẠN 4: Calibrated Abstention, Docker Offline & Submission (13/11 – 16/11 · 4 ngày)
> **Mục tiêu then chốt:** Bảo vệ điểm phạt bằng cơ chế từ chối có hiệu chuẩn, đóng gói Docker khép kín 100% offline và nộp bài trước hạn chót ít nhất 6–12 giờ để loại bỏ hoàn toàn rủi ro kỹ thuật.

| Thành viên | Nhiệm vụ chính (Primary Tasks) | Nhiệm vụ hỗ trợ (Cross-Support Tasks) |
|---|---|---|
| **Long** | - **Hiệu chuẩn Cổng Từ chối (Calibrated Abstention Gate):**<br/>  + Xây dựng bộ đo độ tin cậy $C = f(\text{Execution Health}, \text{Data Plausibility}, \text{Entity Score})$.<br/>  + Quét tìm ngưỡng $\tau^*$ tối ưu trên tập dev. Những câu có $C < \tau^*$ xuất `abstain` (nhận 0 điểm an toàn, cứu toàn bộ bảng xếp hạng).<br/>- **Đảm bảo Tính tái lập (Reproducibility):** Cố định toàn bộ random seed, Greedy Decoding ($T=0$), đảm bảo $|PA_1 - PA_2| = 0$ để đạt tiêu chí $|PA_{up} - PA_{re}| \le 0.03$. | - Kiểm tra tính toàn vẹn của model weights bên trong Docker container (đủ file weights, cấu hình vLLM offline, FP8/BF16).<br/>- Hỗ trợ Phát kiểm tra logs chi tiết theo từng câu hỏi tại `/result/logs/<question_id>.json`. |
| **Phát** | - **Đóng gói Docker Container:**<br/>  + Viết `Dockerfile` đầy đủ weights, source code và thư viện tương thích kiến trúc Blackwell RTX 5090 (PyTorch, vLLM, CUDA 12.8+).<br/>  + Hoàn thiện script `predict.sh` đọc từ `/data` (chế độ chỉ đọc) và ghi kết quả vào `/result/submission.jsonl`.<br/>- **Kiểm thử Offline Tuyệt đối:** Chạy thử container với cờ `--network none` để đảm bảo hệ thống không thực hiện bất kỳ lệnh tải mạng nào.<br/>- **Đo Thời gian Suy luận (Latency):** Đảm bảo tốc độ xử lý toàn bộ test set $< 4\text{h}$ (dưới trần 6h). | - Cùng Long kiểm tra chéo file kết quả `submission.jsonl` đảm bảo đủ số dòng, đúng question ID, không bị sót câu.<br/>- Tính mã băm SHA256 checksum và upload file image lên Google Drive công khai. |
| **Phối hợp chung** | **Milestone 4 (Hạn chót: 16/11):**<br/>- **Ngày 15/11:** Hoàn tất toàn bộ việc đóng gói Docker, upload Drive, kiểm tra link tải và checksum.<br/>- **Ngày 16/11 (Trước 18:00):** Nộp bài chính thức qua form của BTC (sớm hơn hạn chót 23:59 ít nhất 6 tiếng để đề phòng nghẽn mạng). | |

#### 🎯 Kết quả Đầu ra Kỳ vọng (Expected Outputs — Phase 4):
1. **Bộ đo Độ tin cậy & Ngưỡng $\tau^*$ tối ưu:** Cổng Abstention tự động loại bỏ các câu hỏi có rủi ro đoán sai cao $\to$ Tối đa hóa chỉ số PA cuối cùng.
2. **Tính Tái lập Tuyệt đối (Reproducibility):** Kết quả chạy 2 lần độc lập cho ra cùng 1 đáp án $|PA_1 - PA_2| = 0$, đảm bảo thỏa mãn điều kiện BTC $|PA_{\text{uploaded}} - PA_{\text{rerun}}| \le 0.03$.
3. **Docker Image Offline 100%:** Chạy thử nghiệm thành công với lệnh:
   ```bash
   docker run --gpus all --network none -v /data:/data -v /result:/result <image_name> /app/predict.sh
   ```
4. **Hệ thống Logging chuẩn quy chế:** Toàn bộ log từng câu hỏi được xuất đầy đủ ra `/result/logs/<question_id>.json` với đủ thông tin Question ID, mã sinh ra, kết quả thô, latency và câu trả lời cuối cùng.
5. **Thời gian chạy (Latency):** Tổng thời gian chạy toàn bộ test set $\le 3 - 4$ giờ (dưới giới hạn tối đa 6 giờ của BTC).
6. **Bàn giao Nộp bài Hoàn tất:** File nộp có đầy đủ: Đường dẫn Google Drive công khai có quyền tải, mã SHA256 Checksum chính xác, README giải pháp. Nộp thành công trước **18:00 ngày 16/11/2026**.

---

## 🎯 4. Bảng Ma trận Trách nhiệm & Deadline (RACI Matrix)

*Ký hiệu: **R** (Responsible - Người thực hiện chính), **A** (Accountable - Người chịu trách nhiệm kết quả), **C** (Consulted - Người hỗ trợ/phối hợp).*

| Đầu việc cụ thể (Deliverables) | Long | Phát | Deadline |
|---|:---:|:---:|:---:|
| Khung E2E Pipeline & First Submission | **R / A** | **R** | 02/11 (23:59) |
| Rule 8 Cleaner (Forward-fill & Deduplicate) | C | **R / A** | 04/11 (18:00) |
| In-Memory SQLite Mirror & Indexing | C | **R / A** | 04/11 (23:59) |
| Temporal Grounder (Lịch âm, Tết, as_of_date) | C | **R / A** | 05/11 (18:00) |
| Feasibility Gate (Shield chống phạt điểm âm) | **R / A** | C | 05/11 (23:59) |
| Format Normalizer (8 định dạng) & Tie-Breaker | **R / A** | C | 06/11 (18:00) |
| Internal Eval Benchmark (PA Metric) | **R** | **R / A** | 06/11 (23:59) |
| Sinh dữ liệu tổng hợp (15k–20k mẫu) | C | **R / A** | 08/11 (18:00) |
| Fine-tuning Qwen2.5-Coder-14B (SFT / DPO) | **R / A** | C | 11/11 (23:59) |
| Self-Correction Loop trong Sandbox | **R / A** | C | 12/11 (18:00) |
| Phân tích lỗi (Error Analysis) hàng ngày | **R** | **R** | 07/11 – 12/11 |
| Hiệu chuẩn Cổng Từ chối ($\tau$ Tuning) | **R / A** | C | 13/11 (23:59) |
| Script `predict.sh` & Logging `/result/logs/` | C | **R / A** | 14/11 (18:00) |
| Dockerfile Offline 100% (`--network none`) | C | **R / A** | 15/11 (12:00) |
| Kiểm thử Tái lập Reproducibility & Latency | **R / A** | **R** | 15/11 (23:59) |
| **Nộp bài Hoàn chỉnh (Docker + Checksum)** | **R / A** | **R / A** | **16/11 (Trước 18:00)** |

---

## 💡 5. Lời khuyên Điều phối Giúp Long & Phát Đi Nhanh & Vững

1. **Họp Stand-up 15 phút mỗi sáng (09:00):**
   - Hôm qua Long & Phát đã làm được gì? Điểm PA trên tập validation có tăng không?
   - Hôm nay Long làm gì, Phát làm gì? Có bị nghẽn (blocker) ở khâu nào không?
   - Cần đồng đội hỗ trợ task nào ngay lập tức?
2. **Không phân chia độc lập hoàn toàn:** Khi Phát làm Data Ingestion hay Rulebook, Long phải review ngay để đảm bảo dữ liệu đưa vào prompt vừa vặn context length của mô hình. Ngược lại, khi Long train model, Phát phải tham gia chạy thử và lọc các mẫu dữ liệu lỗi.
3. **Mọi cải tiến phải quy ra điểm PA:** Bất kỳ thay đổi nào (thêm rule mới, đổi prompt, train epoch mới) đều phải chạy qua bộ Internal Benchmark trên tập train/val. Nếu điểm PA không tăng hoặc làm tăng số câu bị phạt (-1), hãy rollback ngay lập tức.

---

## 📚 6. Lộ trình Đọc & Khai thác Nghiên cứu (Paper & Review Roadmap)

Thư mục `research/reviews/` chứa 35 bản tóm tắt phân tích chuyên sâu các công trình nghiên cứu SOTA thế giới về Text-to-SQL, bảng tính và độ tin cậy mô hình. Để tránh việc đọc dàn trải và tối ưu hóa thời gian thực thi, các tài liệu được phân loại và chỉ định chính xác cho **Long** và **Phát** theo từng giai đoạn:

### GIAI ĐOẠN 1: Fast Pipeline & First Submission (31/10 – 02/11)
> **Mục tiêu đọc:** Nắm vững cơ chế tính điểm phạt của cuộc thi và kiến trúc tối giản chuyển câu hỏi thành mã Python/SQL.

- **Tài liệu đọc chung (Long & Phát):**
  - [Benchmarking Text-to-SQL Reliability with Penalty-Based Scoring.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/Benchmarking%20Text-to-SQL%20Reliability%20with%20Penalty-Based%20Scoring.md) (**TrustSQL**): Bản lề lý thuyết của thước đo Penalized Accuracy ($PA = +1 / 0 / -1$). Cả hai cần hiểu tại sao đoán mò là "tự sát" ($E[s] < 0$ khi confidence $< 0.5$) và kiêng trả lời (*abstain*) là chiến lược sống còn.
  - [A Survey of Text-to-SQL in the Era of LLMs.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/A%20Survey%20of%20Text-to-SQL%20in%20the%20Era%20of%20LLMs.md): Nắm bức tranh toàn cảnh về quy trình Text-to-SQL hiện đại (Schema Linking $\to$ Code Generation $\to$ Execution).

- **Tài liệu dành cho Long (AI Architect & Model Lead):**
  - [SheetBrain.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/SheetBrain.md): Học cách thiết kế prompt hướng dẫn LLM đóng vai trò lập trình viên phân tích dữ liệu, sinh mã Python/Pandas thực thi tất định thay vì để LLM tự tính toán nhẩm số học.
  - [Towards Building Open-source Language Models for Text-to-SQL.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/Towards%20Building%20Open-source%20Language%20Models%20for%20Text-to-SQL.md) (**CodeS**): Đánh giá năng lực các mô hình Coder chuyên trách phân khúc nhỏ ($\le 15\text{B}$ tham số) như Qwen2.5-Coder và thiết lập tham số suy luận chuẩn (Greedy Decoding $T=0$).

- **Tài liệu dành cho Phát (Data Engineer & System Lead):**
  - [Encoding Spreadsheets for Large Language Models.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/Encoding%20Spreadsheets%20for%20Large%20Language%20Models.md) (**SpreadSheetLLM**): Tìm hiểu đặc thù cấu trúc bảng tính (ô trống, ô gộp, đa bảng) để thiết kế parser nạp dữ liệu thô ban đầu không làm thất thoát thông tin.
  - [Can LLM Already Serve as A Database Interface.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/Can%20LLM%20Already%20Serve%20as%20A%20Database%20Interface.md): Kỹ thuật ánh xạ dữ liệu file phẳng (CSV, Excel) vào cấu trúc bảng cơ sở dữ liệu quan hệ tối giản.

---

### GIAI ĐOẠN 2: Deterministic Shields & Rulebook Engines (03/11 – 06/11)
> **Mục tiêu đọc:** Xây dựng lá chắn phát hiện câu hỏi bất khả thi (`unanswerable`), xử lý dữ liệu bảng bẩn và chuẩn hóa thực thể tiếng Việt.

- **Tài liệu đọc chung (Long & Phát):**
  - [A Practical Text-to-SQL Benchmark for Electronic Health Records.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/A%20Practical%20Text-to-SQL%20Benchmark%20for%20Electronic%20Health%20Records.md) (**EHRSQL**): Nghiên cứu cách phân loại câu hỏi không thể trả lời (*unanswerable questions*) trong thực tế (thiếu dữ liệu, hỏi ngoài phạm vi thời gian) để cả hai thống nhất ranh giới giữa trả lời và từ chối.

- **Tài liệu dành cho Long (AI Architect & Model Lead):**
  - [AbstentionBench.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/AbstentionBench.md): **Cảnh báo cốt tử:** Các mô hình Reasoning bị ảo giác tự tin (+24%) trên câu hỏi bất khả thi. *Long áp dụng:* Kiên quyết dùng **Deterministic Feasibility Gate** (kiểm tra code logic cứng về Date Range và cột thiếu) để gán nhãn `unanswerable` ăn +1 điểm, tuyệt đối không để LLM đoán mò.
  - [Query Carefully.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/Query%20Carefully.md): Kỹ thuật nhận diện các câu hỏi vi phạm ràng buộc dữ liệu hoặc hỏi vượt quá dữ liệu hiện có của doanh nghiệp.
  - [Disambiguate First, Parse Later.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/Disambiguate%20First,%20Parse%20Later.md) & [AmbiSQL.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/AmbiSQL.md): Kỹ thuật giải quyết sự đa nghĩa của câu hỏi bằng cách đối chiếu với từ điển quy tắc (Rulebook Injection).

- **Tài liệu dành cho Phát (Data Engineer & System Lead):**
  - [Large Language Models for Spreadsheets.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/Large%20Language%20Models%20for%20Spreadsheets.md) & [FinSheet-Bench.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/FinSheet-Bench.md): Kỹ thuật làm sạch bảng tính (Rule 8: Group forward-fill các ô trống cấp đơn hàng, lọc trùng lặp) và ánh xạ các công thức nghiệp vụ tài chính.
  - [Contextual Harnessing for Efficient SQL Synthesis.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/Contextual%20Harnessing%20for%20Efficient%20SQL%20Synthesis.md) (**CHESS**): Áp dụng kỹ thuật Candidate Values Retrieval (kết hợp BM25 + Jaro-Winkler) để xây dựng Entity Linker nhận diện tên sản phẩm, size cà phê, tên khách hàng viết tắt/teencode.
  - [SchemaGraphSQL.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/SchemaGraphSQL.md) & [LinkAlign.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/LinkAlign.md): Cách xây dựng đồ thị liên kết bảng (Schema Linking) và đánh chỉ mục (Index) trên SQLite In-Memory để tăng tốc độ JOIN bảng lên hàng trăm lần.

---

### GIAI ĐOẠN 3: Core Enhancement & Fine-Tuning Sprint (07/11 – 12/11)
> **Mục tiêu đọc:** Tối ưu hóa kỹ thuật Fine-Tuning mô hình Coder $\le 15\text{B}$, tạo dữ liệu tổng hợp quy mô lớn và thiết lập cơ chế tự sửa lỗi trong Sandbox.

- **Tài liệu đọc chung (Long & Phát):**
  - [Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/Evaluating%20Language%20Models%20on%20Real-World%20Enterprise%20Text-to-SQL%20Workflows.md) (**BIRD**): Nghiên cứu phương pháp Error Analysis trong các workflow cơ sở dữ liệu doanh nghiệp phức tạp để cùng phân tích các câu bị phạt (-1) trên dev set hàng ngày.

- **Tài liệu dành cho Long (AI Architect & Model Lead):**
  - [Simple Rewards, Strong Reasoning in Text-to-SQL.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/Simple%20Rewards,%20Strong%20Reasoning%20in%20Text-to-SQL.md) (**Arctic-Text2SQL-R1**): Kỹ thuật huấn luyện suy luận sâu với phần thưởng thực thi (Execution Feedback DPO/GRPO): Thưởng +1 khi script chạy khớp đáp án, phạt -1 khi script lỗi cú pháp hoặc tính sai.
  - [A Multi-Agent Collaborative Framework for Text-to-SQL.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/A%20Multi-Agent%20Collaborative%20Framework%20for%20Text-to-SQL.md) (**MAC-SQL**) & [MAGIC.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/MAGIC.md): Cách thiết lập vòng lặp tự sửa lỗi (Self-Correction Loop) trong Execution Sandbox: bắt traceback lỗi runtime/syntax và đưa lại cho LLM sửa (giới hạn tối đa 2 vòng).
  - [ExCoT.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/ExCoT.md) (Execution-guided Chain-of-Thought): Kỹ thuật sinh mã từng bước gắn liền với kết quả thực thi trung gian.
  - [Encoding Spreadsheets for Large Language Models.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/Encoding%20Spreadsheets%20for%20Large%20Language%20Models.md) (Phần **SheetCompressor**): Kỹ thuật nén schema (chỉ nạp tên bảng, danh sách cột, kiểu dữ liệu, từ điển phân loại và 3 dòng mẫu) giúp tiết kiệm context window và tăng tốc suy luận.

- **Tài liệu dành cho Phát (Data Engineer & System Lead):**
  - [Synthesizing High-quality Text-to-SQL Data at Scale.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/Synthesizing%20High-quality%20Text-to-SQL%20Data%20at%20Scale.md) (**SynSQL**): Kỹ thuật sinh dữ liệu tổng hợp (Synthetic Data) chất lượng cao: mở rộng 15.000 – 20.000 mẫu câu hỏi tiếng Việt có/không dấu, teencode ("dthu", "hnay"), biến thể mùa vụ Tết và các câu hỏi unanswerable gài bẫy.
  - [ReAcTable.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/ReAcTable.md): Phân chia kiến trúc Dual-Engine: đẩy các tác vụ lọc/nhóm/tính tổng cho SQLite xử lý tốc độ cao, và dùng Python xử lý các logic phức tạp (quy đổi đơn vị đa tầng, xử lý lịch âm).
  - [AutoLink.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/AutoLink.md): Kỹ thuật liên kết thực thể tự động giữa ngôn ngữ tự nhiên và cơ sở dữ liệu để lọc sạch dữ liệu huấn luyện SFT.

---

### GIAI ĐOẠN 4: Calibrated Abstention, Docker Offline & Submission (13/11 – 16/11)
> **Mục tiêu đọc:** Hiệu chuẩn ngưỡng từ chối an toàn $\tau^*$ để tối đa hóa điểm PA, tối ưu hóa runtime offline và hoàn thiện hệ thống khép kín.

- **Tài liệu đọc chung (Long & Phát):**
  - [WorkstreamBench.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/WorkstreamBench.md): Bài học về kiểm thử độ ổn định (Reliability) và tính tái lập (Reproducibility) trong các hệ thống phân tích tự hành doanh nghiệp.

- **Tài liệu dành cho Long (AI Architect & Model Lead):**
  - [LatentRefusal.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/LatentRefusal.md) & [AbstentionBench.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/AbstentionBench.md): Cơ chế hiệu chuẩn độ bất định (Uncertainty Estimation) để xây dựng **Calibrated Abstention Gate**: tính điểm tin cậy $C \in [0, 1]$ và quét tìm ngưỡng $\tau^*$ tối ưu trên tập dev. Những câu có $C < \tau^*$ tự động xuất `abstain` (nhận 0 điểm an toàn, bảo vệ toàn bộ điểm số).
  - [Benchmarking Text-to-SQL Reliability with Penalty-Based Scoring.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/Benchmarking%20Text-to-SQL%20Reliability%20with%20Penalty-Based%20Scoring.md) (Phần **Reliability Calibration & Decision Boundary**): Thiết lập ranh giới quyết định toán học giữa 3 trạng thái: Trả lời giá trị / Unanswerable / Abstain.

- **Tài liệu dành cho Phát (Data Engineer & System Lead):**
  - [A Survey on Employing Large Language Models for.md](file:///d:/Projects/AI%20%20project/datamate/research/reviews/A%20Survey%20on%20Employing%20Large%20Language%20Models%20for.md) (Phần **Tabular Deployment & Efficiency**): Kỹ thuật tối ưu hóa bộ nhớ RAM và IO khi nạp toàn bộ CSDL vào In-Memory SQLite RAM disk (`/dev/shm`), đảm bảo thời gian suy luận toàn bộ Private Test chỉ mất $< 4$ giờ (xa dưới mức trần 6 giờ của BTC).
  - Quy chuẩn Docker từ [DataMate_Zalo_AI_Challenge_2026.md](file:///d:/Projects/AI%20%20project/datamate/docs/DataMate_Zalo_AI_Challenge_2026.md): Thiết lập Dockerfile cô lập 100% offline (`--network none`), tích hợp vLLM và PyTorch tối ưu cho kiến trúc Blackwell 2x NVIDIA RTX 5090 (CUDA 12.8+).

