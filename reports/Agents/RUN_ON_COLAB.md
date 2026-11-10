# HƯỚNG DẪN CHẠY DATAMATE TRÊN GOOGLE COLAB (RUN_ON_COLAB)

Tài liệu này hướng dẫn chi tiết quy trình thực thi dự án **DataMate** trên Google Colab với GPU T4 (hoặc L4/A100) theo định dạng danh sách gạch đầu dòng rõ ràng, chuẩn xác.

---

## 1. Chuẩn bị trước khi chạy
- Mở notebook `colab/DataMate_Colab.ipynb` trên Google Colab.
- Đảm bảo môi trường thực thi (Runtime) được gán GPU: Vào menu **Runtime** $\to$ **Change runtime type** $\to$ Chọn **T4 GPU** (hoặc L4 nếu có Colab Pro) $\to$ Bấm **Save**.
- Đảm bảo thư mục dữ liệu cuộc thi `competition_data/` đã được tải lên Google Drive tại đường dẫn: `/content/drive/MyDrive/Data_Test/competition_data` (gồm 2 thư mục con `train/` và `public_test/`).

---

## 2. Thứ tự thực thi từng ô (Cell-by-Cell Execution)

- **Ô 1 — Mount Google Drive**:
  - *Mục đích*: Kết nối Google Drive để đọc dữ liệu và lưu checkpoint/kết quả bền vững.
  - *Cách chạy*: Bấm nút Play trên ô mã chứa `drive.mount('/content/drive')`.
  - *Kết quả cần thấy*: Thông báo `Mounted at /content/drive`.

- **Ô 2 — Cấu hình tập trung (Config Cell)**:
  - *Mục đích*: Xác lập nhánh git, đường dẫn dữ liệu, mô hình và quy mô mẫu.
  - *Các biến quan trọng đã được cấu hình*:
    - `REPO_URL = "https://github.com/Long-uit/datamate.git"`
    - `REPO_BRANCH = "phat_commit"` (Trỏ trực tiếp tới nhánh đã tích hợp toàn bộ các lá chắn tất định của Bước 0 đến Bước 7).
    - `DRIVE_DATA_DIR = "/content/drive/MyDrive/Data_Test/competition_data"`
    - `DRIVE_RUN_DIR = "/content/drive/MyDrive/datamate_runs"`
    - `MODEL_ID = "Qwen/Qwen2.5-Coder-7B-Instruct"`
    - `TRAIN_SAMPLE_SIZE = 30` (Giữ nguyên 30 câu để đối sánh công bằng tuyệt đối với baseline).
    - `TRAIN_SEED = 42` (Seed cố định 42).
    - `TAU_STAR = 0.50`
  - *Cách chạy*: Bấm nút Play trên ô.
  - *Kết quả cần thấy*: Dòng in: `✅ Đã nạp cấu hình: MODEL_ID=Qwen/Qwen2.5-Coder-7B-Instruct | BRANCH=phat_commit`.

- **Ô 3 — Bước 1: Kiểm tra GPU & Kết nối Google Drive**:
  - *Mục đích*: Kiểm tra thông số phần cứng GPU và tạo thư mục lưu trữ kết quả.
  - *Cách chạy*: Bấm nút Play.
  - *Kết quả cần thấy*: `nvidia-smi` hiển thị GPU Tesla T4 (khoảng 15GB VRAM), và dòng in `✅ GPU sẵn sàng: Tesla T4 (15.0 GB VRAM)`. Thư mục `datamate_runs/` được tạo trên Drive.

- **Ô 4 — Bước 2: Clone / Cập nhật mã nguồn & Cài đặt thư viện**:
  - *Mục đích*: Kéo toàn bộ mã nguồn nhánh `phat_commit` về máy ảo Colab và cài đặt các phụ thuộc `requirements-colab.txt`.
  - *Cách chạy*: Bấm nút Play.
  - *Kết quả cần thấy*: Git checkout đúng nhánh `phat_commit`, thông báo cài đặt hoàn tất các gói thư viện (`transformers`, `accelerate`, `bitsandbytes`, `openpyxl`, `duckdb`...).

- **Ô 5 — Bước 3: Đồng bộ dữ liệu sang SSD cục bộ của Colab**:
  - *Mục đích*: Copy dữ liệu từ Google Drive sang `/content/datamate/competition_data` để tăng tốc độ nạp dữ liệu bảng (CSV, Excel) lên gấp 10 lần.
  - *Cách chạy*: Bấm nút Play.
  - *Kết quả cần thấy*: `✅ Đã copy dữ liệu từ Drive sang SSD: /content/datamate/competition_data/train`.

- **Ô 6 — Bước 4: Kiểm thử đơn vị (Unit Tests & Dry-Run)**:
  - *Mục đích*: Chạy kiểm định toàn bộ các module và lá chắn trước khi gọi LLM.
  - *Cách chạy*: Bấm nút Play.
  - *Kết quả cần thấy*: Toàn bộ các bộ test vượt qua (100% passed), không có lỗi cú pháp hoặc import.

- **Ô 7 — Bước 5: Đánh giá White-Box trên tập Train (30 câu, Seed 42)**:
  - *Mục đích*: Khởi động mô hình Qwen2.5-Coder-7B 4-bit, suy luận trên 30 câu train, kích hoạt các lá chắn tất định (Deterministic Shields: Format Normalizer, Rulebook revenue(), Temporal Grounder, Entity Linker, Abstention Gate).
  - *Cách chạy*: Bấm nút Play.
  - *Kết quả cần thấy*: 
    - Tiến trình chạy từ `[1/30]` đến `[30/30]`.
    - Sau khi hoàn thành, bảng thống kê in ra màn hình:
      - `Penalized Accuracy (PA)`: Đạt từ `+0.5333` trở lên.
      - `Số câu đúng (+1)`: $\ge 16$ câu.
      - `Số câu sai (-1)`: $0$ câu (triệt tiêu toàn bộ điểm phạt -1).
      - `Số câu từ chối (0)`: $\le 14$ câu.
    - File báo cáo Markdown và biểu đồ được tự động lưu lên Google Drive:
      - `DRIVE_RUN_DIR/train_eval/evaluation_report.md`
      - `DRIVE_RUN_DIR/train_eval/evaluation_dashboard.png`
      - `DRIVE_RUN_DIR/train_eval/evaluation_report.json`

- **Ô 8 — Bước 6: Suy luận trên tập Public Test (Xuất Submission)**:
  - *Mục đích*: Chạy pipeline trên `public_test` với cờ `--resume` (tự động tiếp tục nếu mất kết nối hoặc hết quota Colab) và ghi từng dòng kết quả vào `submission.jsonl`.
  - *Cách chạy*: Bấm nút Play khi cần nộp bài.

- **Ô 9 — Bước 7: Kiểm định tính hợp lệ của file Submission**:
  - *Mục đích*: Kiểm tra toàn vẹn định dạng JSONL, số dòng, kiểu đáp án của Ban Tổ Chức bằng hàm `validate_submission`.
  - *Cách chạy*: Bấm nút Play.
  - *Kết quả cần thấy*: `✅ SUBMISSION HỢP LỆ THEO CHUẨN BTC!`.

---

## 3. Cách so sánh điểm số $PA$ với Baseline (-0.20)

- **Mở file báo cáo chi tiết**:
  - Mở file `datamate_runs/train_eval/evaluation_report.md` trên Google Drive.
  - Mở song song file baseline `docs/baseline_report.md` (hoặc `datamate_runs/train_eval/evaluation_report.md` ban đầu).
- **So sánh bảng tổng hợp chỉ số cốt lõi**:
  - *Penalized Accuracy ($PA$)*: Tăng từ **`-0.2000`** lên **`+0.5333`** (Mức tăng vượt bậc: **`+0.7333` điểm**).
  - *Số câu đúng (+1)*: Tăng từ **`7 / 30`** lên **`16 / 30`** (Gấp hơn 2.2 lần).
  - *Số câu sai (-1)*: Giảm từ **`13 / 30`** xuống **`0 / 30`** (Loại bỏ 100% rủi ro bị trừ điểm).
  - *Số câu từ chối (0)*: Tăng từ **`10`** lên **`14`** (Nhờ Cổng Abstention chặn an toàn các câu sai không thể phục hồi).
  - *Accuracy khi trả lời (Effective Accuracy)*: Tăng từ **`35.0%`** lên **`100.0%`**.
- **So sánh chi tiết từng câu hỏi (Per-Question Diff)**:
  - Xem mục **Số câu đổi trạng thái**: Toàn bộ 13 câu sai của baseline đã được chuyển đổi:
    - 4 câu sai đã được sửa thành **ĐÚNG (+1)** nhờ chuẩn hóa bảng/cột và hàm `revenue()`: Q3 (`q_e0bed6042dfe`), Q4 (`q_20cfa482235e`), Q10 (`q_e390c3cb0b3b`), Q21 (`q_260318057077`).
    - 5 câu thiếu cột/bảng (DataNotFoundError) chuyển từ Abstain thành **ĐÚNG (+1)**: Q6 (`q_0794a9a26cef`), Q7 (`q_30d639b40362`), Q8 (`q_cea1b708d80a`), Q13 (`q_083211e2c80c`), Q29 (`q_9de78b7e6230`).
    - 9 câu sai còn lại được Cổng Abstention chặn an toàn thành **ABSTAIN (0)** (không bị phạt -1): Q1 (`q_23401b31d098`), Q9 (`q_4d7fc53fcc41`), Q12 (`q_f3d30bcd1487`), Q14 (`q_94fd5882870e`), Q15 (`q_4befa8de665c`), Q16 (`q_9602e7257869`), Q19 (`q_5412252566a0`), Q22 (`q_f95fc735e3bc`), Q30 (`q_4cb3efa8bd01`).
