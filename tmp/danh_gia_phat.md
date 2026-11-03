# Đánh Giá Hệ Thống & Hướng Nâng Cấp — Phát (Data Engineer & System/Ops Lead)

- **Người thực hiện**: Phát
- **Vai trò**: Data Engineer & System/Ops Lead
- **Thời điểm**: Hoàn thành Phase 2 (03/11/2026)
- **Các module phụ trách chính**:
  - `src/datamate/ingestion/loader.py` (Đọc dữ liệu đa định dạng, phát hiện header POS, gộp sheet tháng)
  - `src/datamate/ingestion/metadata.py` (Trích xuất cấu trúc bảng, cột, kiểu dữ liệu, sơ đồ nối bảng)
  - `src/datamate/grounding/temporal.py` (Giải mã thời gian tiếng Việt, lịch âm - dương)
  - `src/datamate/grounding/rulebook.py` (Trích xuất quy tắc nghiệp vụ liên quan từ Rulebook)
  - `src/datamate/execution/sandbox.py` (Môi trường thực thi mã an toàn, giới hạn tài nguyên)
  - `src/datamate/output/submission.py` (Quản lý ghi file submission.jsonl, flush/fsync, validate)
  - `benchmark/evaluate.py` & `benchmark/split.py` (Chấm điểm chuẩn Penalized Accuracy và chia tập validation)

---

## 1. Ưu điểm trong hệ thống hiện tại

1. **Bộ nạp dữ liệu hoạt động mạnh mẽ và linh hoạt**:
   - `loader.py` xử lý tốt các bảng tính Excel phức tạp trong thực tế: tự động dò hàng tiêu đề POS bị lệch, tự động gộp các sheet cùng định dạng chia theo tháng (`merged_sheets`).
   - Hỗ trợ đầy đủ các định dạng file của cuộc thi (CSV, XLSX, SQLite, JSON) và chuyển đổi đồng bộ sang SQLite in-memory phục vụ truy vấn.
2. **Bộ giải mã thời gian và quy tắc nghiệp vụ chi tiết**:
   - `grounding/temporal.py` bao quát nhiều dạng mốc thời gian đặc thù tại Việt Nam (Tết Nguyên Đán, Rằm, Mùng 1, các ngày lễ dương lịch, nửa đầu/cuối tháng, chuỗi tháng).
   - `grounding/rulebook.py` trích xuất đúng các điều khoản liên quan trong Rulebook dựa trên ngữ cảnh câu hỏi, cung cấp công thức tính trực tiếp cho mô hình.
3. **Cơ sở hạ tầng đo lường và kiểm thử đáng tin cậy**:
   - `evaluate.py` bám sát 100% công thức chấm điểm Penalized Accuracy (PA) và schema của Ban Tổ Chức.
   - `split.py` hỗ trợ chia tập train/val theo 2 chiến lược (`within_business` và `business_holdout`), quản lý hash SHA-256 chặt chẽ để đảm bảo không rò rỉ dữ liệu.
4. **Cơ chế ghi kết quả an toàn**:
   - `SubmissionWriter` trong `submission.py` thực hiện ghi từng dòng kèm `flush()` và `os.fsync()` tức thì, đảm bảo dữ liệu không bị mất nếu có sự cố ngắt tiến trình đột ngột.

---

## 2. Nhược điểm và hạn chế hiện tại

1. **Lỗi cắt giới hạn dòng (`.head(2000)`) trong `ingestion/metadata.py`**:
   - Tại hàm `_try_parse_dates` (dòng 65), việc lấy mẫu `series.dropna().head(2000)` để xác định `date_min` và `date_max` khiến các bảng có nhiều hơn 2.000 dòng bị cắt cụt mốc ngày kết thúc, dẫn đến thông tin khoảng ngày của bảng trong `TableInfo` bị sai lệch.
2. **Danh sách whitelist trong `execution/sandbox.py` còn thiếu thư viện thông dụng**:
   - Biến `ALLOWED_MODULES` trong `sandbox.py` hiện chưa cấp phép cho `calendar` (thư viện LLM rất hay dùng để lấy số ngày trong tháng qua `calendar.monthrange`), `operator`, `copy`, `string`, `fractions`. Khi mã nguồn của LLM gọi các thư viện này, sandbox sẽ từ chối thực thi.
3. **Chưa tích hợp toàn diện vào pipeline chính `predict.py`**:
   - Các module hữu ích đã xây dựng như `temporal.py`, `rulebook.py`, `metadata.py` và `sandbox.py` hiện chưa được gọi trực tiếp trong `predict.py`, khiến pipeline chính chưa tận dụng được hết các tính năng an toàn này.

---

## 3. Hướng nâng cấp cho Phát

1. **Sửa lỗi trích xuất ngày trong `ingestion/metadata.py`**:
   - Loại bỏ `.head(2000)` trong `_try_parse_dates`, đồng thời loại trừ các cột ngày phi giao dịch (`hạn sử dụng`, `ngày áp dụng`, `ngày tạo khách`) để thông tin `date_min`, `date_max` của từng bảng được ghi nhận chính xác.
2. **Cập nhật và đưa `sandbox.py` vào sử dụng trong `predict.py`**:
   - Bổ sung các module `calendar`, `operator`, `copy`, `string`, `fractions` vào `ALLOWED_MODULES`.
   - Bổ sung hàm `apply_tie_breaker` vào môi trường chạy của sandbox.
   - Thay thế lệnh `exec()` trực tiếp trong `predict.py` bằng `execute_code` của `sandbox.py` để áp dụng cơ chế bảo vệ `timeout_sec=10`, tránh rủi ro treo tiến trình khi chạy benchmark hàng loạt câu hỏi.
3. **Bổ sung thông tin gợi ý khóa ngoại (Join Graph) vào schema prompt**:
   - Tận dụng hàm `build_metadata_prompt` hoặc phân tích khóa ngoại từ `metadata.py` để thêm gợi ý các cột liên kết (ví dụ: `Mã hóa đơn`, `Mã hàng`, `Mã lô`) vào phần mô tả schema gửi cho LLM, hỗ trợ mô hình viết câu lệnh JOIN chính xác trên các cửa hàng có nhiều bảng phức tạp.

