# Nhật Ký Công Việc & Báo Cáo Kỹ Thuật Từng Phase — Long (AI Architect & Model Lead)
**Dự án:** DataMate — Zalo AI Challenge 2026 (Track: Phân tích Dữ liệu Bán lẻ & Tự động Sinh mã)  
**Tác giả:** Long (AI Architect & Model Lead)  
**Phối hợp cùng:** Phát (Data Engineer & System Lead)

---

## 📌 Tổng Quan Trách Nhiệm Của Long (Primary Ownership)
1. **Mô hình & Suy luận LLM:** Quản lý nạp mô hình Qwen2.5-Coder (lượng tử hóa 4-bit NF4, Greedy Decoding $T=0$, dọn bộ nhớ VRAM tự động, AST syntax checking).
2. **Kỹ thuật Prompting & In-Context Learning:** Phân loại ý định (Intent Classification), lựa chọn ví dụ mẫu động (Dynamic Few-shot), tích hợp Rulebook và ghi chú doanh nghiệp (ChatML).
3. **Module 3 — Deterministic Feasibility Gate:** Lá chắn phát hiện câu hỏi ngoài phạm vi ngày theo Điều 7, câu hỏi đòi hỏi thuộc tính chủ quan/y khoa ngoài dữ liệu POS hoặc thiếu bảng nghiệp vụ để trả về `unanswerable` (+1 điểm, 0s GPU).
4. **Module 6 — Format Normalizer & Tie-Breaker:** Chuẩn hóa đầu ra về 8 kiểu dữ liệu của BTC, xếp hạng phụ theo mã code tăng dần khi bằng điểm (Điều 9 Rulebook), bảo vệ tỷ lệ nhỏ không bị nhân đôi 100.
5. **Vòng lặp tự sửa lỗi & Sanity Check:** Runtime Self-Correction và kiểm tra tính hợp lý hậu thực thi (bắt số âm bất thường, số 0 vô lý cho câu hỏi xếp hạng) để chủ động ép về `abstain` an toàn (0 điểm).
6. **Module 6.2 — Calibrated Abstention Gate:** Tính điểm độ tin cậy $C = f(\text{Execution Health}, \text{Data Plausibility}, \text{Code Completeness})$ và quét tìm ngưỡng tối ưu $\tau^*$ trên tập dev.
7. **Huấn luyện mô hình (SFT / QLoRA):** Viết pipeline `train.py` và `train.sh` phục vụ tinh chỉnh Qwen2.5-Coder trên dữ liệu tổng hợp.

---

## 🚀 PHASE 1: Fast Pipeline & Baseline Submission (31/10 – 02/11/2026)
> **Mục tiêu:** Dựng khung mã nguồn đầu-cuối tối giản, thông luồng gọi LLM sinh code Python và xuất file `submission.jsonl` hợp lệ lần đầu tiên.

### 1. Nhật ký công việc chi tiết
- **31/10/2026:**
  - Khởi tạo module `src/datamate/llm/client.py`: Tích hợp thư viện `transformers` nạp `Qwen2.5-Coder` dạng lượng tử hóa 4-bit qua `bitsandbytes` (NF4).
  - Cấu hình suy luận tất định: Thiết lập bắt buộc `do_sample=False`, `temperature=0.0` để triệt tiêu tính ngẫu nhiên, thỏa mãn điều kiện tái lập $|PA_1 - PA_2| = 0$ của BTC.
- **01/11/2026:**
  - Viết module `src/datamate/llm/prompt_builder.py` phiên bản ban đầu: Dựng khung ChatML (System Prompt và User Prompt) truyền schema rút gọn và câu hỏi.
  - Xây dựng bộ bóc tách mã nguồn `extract_code_block`: Trích xuất hàm `def solution(data):` nằm giữa các cặp markdown ```python ... ``` và cắt bỏ các khối mã lặp phía sau.
- **02/11/2026:**
  - Phối hợp cùng Phát hoàn thiện pipeline chạy thử nghiệm E2E trong `predict.py`.
  - Kiểm tra thẩm định định dạng đầu ra với bộ quy chuẩn của BTC. Xuất file nộp bài đầu tiên trên `public_test` (1.000 câu) hoàn thành Milestone 1.

### 2. Kết quả nghiệm thu Phase 1
- File `submission.jsonl` tạo ra đạt chuẩn 100% (0 lỗi định dạng format).
- Pipeline thông suốt không crash, ghi nhận mốc điểm Baseline đầu tiên của đội thi.

---

## 🛡️ PHASE 2: Deterministic Shields & Rulebook Engines (03/11 – 06/11/2026)
> **Mục tiêu:** Xây dựng các lá chắn quy tắc nghiệp vụ tất định. Ăn trọn điểm câu `unanswerable` (+1 điểm) và ngăn chặn việc bị trừ -1 điểm.

### 1. Nhật ký công việc chi tiết
- **03/11/2026:**
  - **Module 3 — Deterministic Feasibility Gate (`feasibility.py`):**
    + Hiện thực hóa Điều 7 Rulebook: Tự động so sánh khoảng ngày câu hỏi $[q_{start}, q_{end}]$ và kỳ đối chiếu $[cmp_{start}, cmp_{end}]$ với $[min_{date}, max_{date}]$ của shop. Nếu nằm HOÀN TOÀN ngoài khoảng dữ liệu $\to$ Trả về `unanswerable`.
    + Lọc triệt để câu hỏi đòi hỏi thuộc tính cảm tính/chủ quan (tay nghề, thái độ, chu đáo, quý mến, khách khen...) hoặc kiến thức y khoa ngoài dữ liệu POS.
    + Nhận diện các câu hỏi hỏi về bảng/cột nghiệp vụ mà shop không hề có (tồn kho, hạn dùng, giá nhập, công nợ, chi phí mặt bằng...).
    + Đạt độ chính xác 100% trên 3.000 câu tập train: Bắt đúng 70/70 câu `unanswerable` (Recall 100%, Precision 100%).
  - **Module 6 — Format Normalizer & Tie-Breaker (`normalizer.py`):**
    + Chuẩn hóa 8 kiểu dữ liệu: Tiền VND làm tròn số nguyên, tỷ lệ % trả về float [0–100], ngày ISO YYYY-MM-DD, boolean, string giữ nguyên dấu tiếng Việt NFC.
    + Cơ chế bảo vệ tỷ lệ nhỏ ($\le 1\%$): Nếu code của LLM đã có `* 100` thì không nhân đôi lần hai.
    + Hiện thực hóa Điều 9 Rulebook (Tie-Breaker): Xếp hạng phụ theo mã code tăng dần khi bằng điểm.
- **04/11/2026 (Nâng cấp toàn diện theo phản hồi đánh giá hệ thống):**
  - **Chuyển đổi backbone sang 7B:** Cập nhật `config/default.yaml`, `config.py`, `client.py` và `predict.py` sang mô hình `Qwen/Qwen2.5-Coder-7B-Instruct` (4-bit NF4 tiêu tốn ~5.5GB VRAM).
  - **Tích hợp Temporal Grounder của Phát vào Prompt:**
    + Nối trực tiếp `datamate.grounding.temporal.resolve_temporal` vào `resolve_temporal_context`.
    + Bổ sung khả năng giải mã: nửa đầu/cuối tháng (01–15 và 16–cuối tháng), 10 ngày đầu/giữa/cuối tháng, rằm (15 âm) và mùng 1 âm lịch tra cứu qua calendar.
    + Đưa cả **Kỳ chính** (`start_date`, `end_date`) và **Kỳ đối chiếu** (`comparison_start`, `comparison_end`) vào prompt khi câu hỏi yêu cầu so sánh với tháng trước.
  - **Bổ sung 2 ví dụ Few-shot chuyên biệt vào `FEW_SHOT_LIBRARY`:**
    + `inventory_unit_conversion`: Hướng dẫn tính tồn kho theo lô và dùng `divmod` để trả về định dạng `list` `[hộp chẵn, viên lẻ]`.
    + `time_series`: Hướng dẫn lọc doanh thu kỳ chính và kỳ đối chiếu, tính tỷ lệ tăng trưởng `pct_change` so với tháng liền trước.
  - **Bộ kiểm tra tính hợp lý hậu thực thi (Sanity Check):**
    + Viết hàm `check_result_sanity` trong `normalizer.py`.
    + Bắt số âm bất thường cho các câu hỏi doanh thu/số lượng, bắt số 0 hoặc chuỗi rỗng vô lý cho câu hỏi xếp hạng/bán chạy nhất.
    + Tích hợp vào `predict.py`: Lượt 1 gửi phản hồi lỗi cho LLM tự sửa mã qua Self-Correction; Lượt 2 nếu vẫn vi phạm thì chủ động ép về `abstain` an toàn (0 điểm) để tránh bị phạt -1 điểm.

### 2. Kết quả nghiệm thu Phase 2
- Bộ unit tests của Long đạt 100% PASS:
  + `tests/llm/test_prompt_builder.py`: 19/19 tests ĐẠT.
  + `tests/output/test_normalizer.py`: 10/10 tests ĐẠT.
  + `tests/llm/test_feasibility.py`: 11/11 tests ĐẠT.
  + `tests/llm/test_client.py`: 15/15 tests ĐẠT.
  + `tests/test_config.py`: 3/3 tests ĐẠT.

---

## ⚡ PHASE 3: Core Enhancement & Fine-Tuning Pipeline (07/11 – 12/11/2026)
> **Mục tiêu:** Chuẩn bị sẵn sàng hạ tầng huấn luyện mô hình tinh chỉnh (SFT) để nạp bộ dữ liệu 15k–20k của Phát và nén schema prompt.

### 1. Nhật ký công việc chi tiết
- **Thiết lập pipeline huấn luyện SFT / QLoRA (`train.py` & `train.sh`):**
  - Xây dựng `train.py`: Hỗ trợ nạp mô hình `Qwen/Qwen2.5-Coder-7B-Instruct` dạng 4-bit (NF4, bfloat16), chuẩn bị model qua `prepare_model_for_kbit_training`.
  - Cấu hình LoRA adapter tối ưu cho tác vụ sinh code:
    `LoraConfig(r=16, lora_alpha=32, target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"], lora_dropout=0.05, bias="none", task_type="CAUSAL_LM")`.
  - Hỗ trợ cờ `--dry_run` để kiểm định toàn vẹn dữ liệu trước khi train GPU.
  - Viết hoàn thiện script thực thi `train.sh` với cấu hình batch size=2, grad_accum=8, lr=2e-4, epochs=3.
- **Nghiệm thu Dry-Run Huấn luyện:**
  - Chạy `train.py --dry_run` thành công trên 2.406 mẫu câu hỏi fold 0, tạo thư mục `weights/qwen2.5-coder-7b-datamate/` và lưu `training_manifest.json` đầy đủ.

### 2. Kế hoạch phối hợp cùng Phát trong Phase 3
- Khi Phát hoàn thành sinh 15.000 – 20.000 dữ liệu tổng hợp (Data Augmentation) và làm sạch, Long sẽ đưa trực tiếp vào `train.sh` để chạy SFT LoRA.
- Khóa checkpoint mô hình tốt nhất đạt PA cao nhất trên tập validation vào ngày 12/11.

---

## 🎯 PHASE 4: Calibrated Abstention Gate & Reproducibility (13/11 – 16/11/2026)
> **Mục tiêu:** Xây dựng cổng từ chối có hiệu chuẩn $\tau^*$ để tối đa hóa điểm số Penalized Accuracy và đảm bảo tính tái lập tuyệt đối.

### 1. Nhật ký công việc chi tiết
- **Module 6.2 — Calibrated Abstention Gate (`src/datamate/output/abstention.py`):**
  - Xây dựng hàm `compute_confidence_score`:
    $$C = 0.40 \times \text{Execution Health} + 0.35 \times \text{Data Plausibility} + 0.25 \times \text{Code Completeness}$$
    + Bị phạt điểm nặng nếu: có lỗi thực thi, runtime quá dài (> 5s), vi phạm sanity check, hoặc code thiếu cấu trúc return.
  - Xây dựng hàm `apply_abstention_gate(sub_ans, confidence, threshold)`:
    Tự động chuyển các câu có $C < \tau^*$ thành `{"type": "abstain", "answer": None}` để bảo vệ an toàn bảng xếp hạng.
  - Xây dựng hàm `find_optimal_threshold`:
    Quét tự động ngưỡng $\tau^* \in [0.20, 0.80]$ trên tập validation nội bộ để tìm ra giá trị $\tau$ mang lại chỉ số Penalized Accuracy (PA) cao nhất.
- **Unit test xác thực:**
  - Viết `tests/output/test_abstention.py` kiểm tra 4 kịch bản: tính điểm tin cậy khỏe mạnh ($\ge 0.90$), tính điểm lỗi ($0.0$), cổng từ chối theo ngưỡng, và thuật toán quét $\tau^*$ tối ưu. Kết quả: 4/4 tests ĐẠT (OK).
- **Đảm bảo tính tái lập tuyệt đối (Reproducibility):**
  - Cố định toàn bộ seed = 42, giữ `do_sample=False`, `temperature=0.0`. Chạy 2 lần độc lập cho ra cùng 1 đáp án $|PA_1 - PA_2| = 0$, đảm bảo thỏa mãn điều kiện BTC $|PA_{uploaded} - PA_{rerun}| \le 0.03$.

---

## 📊 Bảng Tổng Kết Trạng Thái Các Module Của Long

| Module | Tệp mã nguồn | Trạng thái kỹ thuật | Test coverage |
|---|---|:---:|:---:|
| **LLM Client & 4-bit Engine** | `src/datamate/llm/client.py` | Hoàn thành 100% | 15/15 PASS |
| **Deterministic Feasibility Gate** | `src/datamate/llm/feasibility.py` | Hoàn thành 100% | 11/11 PASS |
| **Prompt Builder & Few-Shot RAG** | `src/datamate/llm/prompt_builder.py` | Hoàn thành 100% | 19/19 PASS |
| **Format Normalizer & Tie-Breaker** | `src/datamate/output/normalizer.py` | Hoàn thành 100% | 10/10 PASS |
| **Calibrated Abstention Gate** | `src/datamate/output/abstention.py` | Hoàn thành 100% | 4/4 PASS |
| **Training Pipeline (SFT / QLoRA)** | `train.py` & `train.sh` | Hoàn thành 100% | Dry-run PASS |
| **Pipeline Integration & Sanity Check**| `predict.py` | Hoàn thành 100% | Dry-run 1000 câu PASS |

