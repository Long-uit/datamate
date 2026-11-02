# Nhật ký Thay đổi (Changelog / Commit Log)
**Thời gian:** 01/11/2026  
**Tác giả:** Phát (Data Engineer & System Lead)  
**Nhánh (Branch):** `phat_commit`  
**Giai đoạn:** Chuyển giao Phase 1 ➔ Phase 2 (Hoàn thành sớm Bước 0: Package Refactor)

---

## 🎯 Mục tiêu Trọng tâm trong Ngày
1. **Hợp nhất mã nguồn (Branch Synchronization):** Đồng bộ và giải quyết xung đột khi tích hợp toàn bộ module Phase 1 của Long (`origin/long-commit`) vào nhánh `phat_commit`.
2. **Xây dựng Lộ trình Kỹ thuật Chi tiết (`docs/DataMate_Source_Roadmap.md`):** Chuẩn hóa kiến trúc mã nguồn từ Phase 1 đến Phase 4, xác định rõ trách nhiệm, ranh giới module, hợp đồng giao tiếp (interfaces) giữa Long & Phát và 7 điểm nợ kỹ thuật cần khắc phục.
3. **Thực hiện sớm Bước 0 — Package Refactoring:** Tái cơ cấu toàn bộ dự án từ cấu trúc phẳng (`src/*.py`) sang chuẩn kiến trúc module `src/datamate/` (Src-Layout) với các subpackages chuyên trách, cập nhật toàn bộ hệ thống test tự động và tài liệu dự án mà không làm thay đổi hành vi logic (Zero Regressions).

---

## 📦 Các Thay đổi Mấu chốt & Phương thức Thực hiện Chính

### 1. Đồng bộ & Cấu hình Môi trường
- **Hợp nhất nhánh `origin/long-commit`:** Đưa các module suy luận của Long (`llm_client.py`, `prompt_builder.py`) và bộ test liên quan vào nhánh làm việc chính.
- **Quản lý môi trường cô lập:** Cập nhật `.gitignore` loại trừ thư mục ảo `.venv/`, `.pytest_cache/`, `competition_data/` và các artifacts phụ trợ nhằm giữ sạch kho lưu trữ git.

### 2. Thiết kế Lộ trình Kiến trúc Mã nguồn (`docs/DataMate_Source_Roadmap.md`)
- Mô tả chi tiết cấu trúc thư mục đích qua từng giai đoạn (Phase 1 ➔ Bước 0 ➔ Phase 2 ➔ Phase 3 ➔ Phase 4).
- Phân định rõ hợp đồng dữ liệu (interfaces):
  - **Phát cung cấp:** `get_metadata` (khoảng ngày, schema), `resolve_temporal` (TimeWindow).
  - **Long tiếp nhận & triển khai:** `feasibility_gate` (chặn `unanswerable`), `normalizer` (chuẩn hóa 8 format), `ranking` (Rule 9).
- Liệt kê và định tuyến giải quyết 7 khoản nợ kỹ thuật (ép kiểu `unanswerable`, nối `solution` vào `FINAL_RESULT`, cache SQLite mirror, side-effects console...).

### 3. Tái cấu trúc Dự án sang Chuẩn Package (`src/datamate/`)
Chuyển đổi triệt để sang mô hình package phân tầng, cài đặt qua `pip install -e . --no-deps` với file cấu hình chuẩn `pyproject.toml`:
- **`datamate.ingestion`:** Đặt file `loader.py` (từ `ingest.py`) chịu trách nhiệm nạp dữ liệu đa định dạng, SQLite in-memory và sinh mô tả schema.
- **`datamate.execution`:** Đặt file `sandbox.py` (từ `runner.py`) chịu trách nhiệm cách ly thực thi subprocess và timeout.
  - *Hiệu chỉnh quan trọng:* Cập nhật chuỗi worker script (`from datamate.ingestion.loader import ...`) và sửa đường dẫn truy xuất `src_dir` lên `parents[2]` để tương thích với cấu trúc package mới.
- **`datamate.llm`:** Chứa `client.py` (từ `llm_client.py`) quản lý mô hình Qwen 4-bit Greedy và `prompt_builder.py` quản lý prompt template, intent classification và dynamic few-shot.
- **`datamate.output`:** Chứa `submission.py` quản lý format đầu ra 9 kiểu, context manager ghi file bền vững (`flush` + `os.fsync`) và bộ kiểm tra hợp lệ 7 tiêu chí.
- **Đóng gói công cụ phụ trợ:**
  - Chuyển mã nguồn EDA sang `notebooks/eda/`.
  - Tách script đánh giá vòng lặp sang `scripts/phase1_loop.py`.

### 4. Tái cơ cấu Hệ thống Kiểm thử Tự động (`tests/`)
Phân bổ lại các tệp test case tương ứng với từng subpackage:
- `tests/ingestion/test_loader.py` (32 unit tests): Khử BOM, lệch header, merge sheet, encoding fallback, sqlite ro.
- `tests/execution/test_sandbox.py` (9 unit tests): Timeout, syntax error, IPC, stdout capture, final result.
- `tests/llm/test_client.py` (15 unit tests): AST validation, code extraction, self-correction fallback.
- `tests/llm/test_prompt_builder.py` (15 unit tests): Intent classification, dynamic few-shot, temporal grounding Tết/relative dates.
- `tests/output/test_submission.py` (17 unit tests): Typing inference, JSON cleanliness, schema validation, submission writer fsync.

---

## 🧪 Kết quả Kiểm định Thực tế
- **Hệ thống Test Tự động:** Chạy toàn bộ test suite thông qua lệnh `pytest`:
  - **Kết quả:** `88/88 PASSED` (**100% thành công**) trong 23.39 giây.
  - Không có bất kỳ lỗi suy giảm chất lượng (regressions) nào sau khi đổi cấu trúc package.
- **Đánh giá Tiến độ:** 
  - Vượt tiến độ dự kiến: Task "Bước 0 — Refactor Package Layout" (vốn được lên lịch vào sáng ngày 03/11) đã được hoàn thành trọn vẹn và ổn định ngay trong ngày 01/11.
