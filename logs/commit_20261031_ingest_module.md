# Nhật ký Thay đổi (Changelog / Commit Log)
**Thời gian:** 31/10/2026  
**Tác giả:** Phát (Data Engineer & System Lead)  
**Nhánh (Branch):** `phat_commit`  
**Giai đoạn:** Phase 1 — Fast Pipeline & First Submission

---

## 🎯 Mục tiêu Lần Commit
Hoàn thành task đầu tiên của Phase 1 theo phân công tại `docs/Timeline_and_Contribution.md`:
> *"Viết parser nạp dữ liệu thô (đọc các file `.xlsx`, `.csv`, `.sqlite` trong `competition_data`)"*

---

## 📦 Nội dung Chi tiết Đã Thực Hiện

### 1. Xây dựng Module Nạp Dữ liệu Thô (`src/ingest.py`)
- **Khái quát hóa toàn diện:** Không hard-code `business_id`, tên file, tên sheet hay tên cột. Tự sinh `table_id` an toàn chuẩn ASCII (`t_01`, `t_02`, ...).
- **Đọc đa định dạng:**
  - **CSV:** Hỗ trợ danh sách encoding luân phiên (`utf-8-sig`, `utf-8`, `cp1258`, `cp1252`, `latin1`), tự khử ký tự BOM (`\ufeff`), đọc theo chunk (`chunksize=50_000`) để xử lý file lớn (> 100k dòng).
  - **Excel (`.xlsx`):** Mở workbook một lần bằng `openpyxl(read_only=True)` để tối ưu RAM; thuật toán heuristic tự dò dòng header thật trong 10 dòng đầu; tự nhận diện và gộp các sheet cùng cấu trúc theo tháng (bổ sung cột `_source_sheet`).
  - **SQLite:** Đọc kết nối chỉ đọc an toàn (`Path.resolve().as_uri() + "?mode=ro"`), xử lý tốt đường dẫn chứa khoảng trắng trên Windows; tự lọc bỏ các bảng hệ thống `sqlite_*`.
  - **README.md:** Đọc mô tả nghiệp vụ của từng shop bằng `utf-8-sig`.
- **Bảo toàn dữ liệu gốc:** Toàn bộ giá trị đọc dưới dạng `str`/`object`, giữ nguyên định dạng ngày/tiền/đơn vị đo; đồng nhất chuỗi rỗng và khoảng trắng thành `pd.NA`.
- **Xử lý bất thường:** Hàm `fix_mojibake()` phục hồi tên file tiếng Việt bị lỗi mã hóa ký tự (cp437/cp850 -> utf-8).
- **Công cụ hỗ trợ mô hình (LLM & Sandbox):**
  - `to_sqlite(business)`: Nạp toàn bộ các bảng vào SQLite ảo in-memory (`:memory:`) kèm bảng siêu dữ liệu `_table_map`, sẵn sàng cho module thực thi truy vấn.
  - `describe_schema(business, max_sample=3)`: Tự động trích xuất schema ngắn gọn kèm mẫu dữ liệu để chèn thẳng vào prompt LLM.
- **Khả năng chịu lỗi cao:** Bọc try/catch riêng cho từng file/sheet; file lỗi được ghi vào `BusinessData.errors`, không làm gián đoạn toàn bộ hệ thống.
- **CLI chạy thử nghiệm:** Tích hợp giao diện dòng lệnh `python src/ingest.py --data_dir <path>` với hỗ trợ UTF-8 console Windows.

### 2. Xây dựng Bộ Kiểm thử Tự động (`tests/test_ingest.py`)
- Bộ 32 test case độc lập trên `pytest` bao phủ toàn bộ các tình huống dữ liệu biên bằng dữ liệu giả lập (`tmp_path`):
  - Khử BOM trong CSV, kiểm tra fallback encoding.
  - Xử lý header lệch dòng trong Excel (dòng 2, 3).
  - Gộp sheet cùng cấu trúc theo tháng và giữ riêng sheet khác cấu trúc.
  - Kết nối SQLite read-only và lọc bảng hệ thống.
  - Chuẩn hóa tên cột Unicode NFC, loại bỏ khoảng trắng và đánh số chống trùng tên cột.
  - Kiểm tra khả năng phục hồi khi gặp file hỏng mà không gây crash chương trình.
- **Kết quả:** `32/32 PASSED` (100%) trong 1.92s.

### 3. Cập nhật Tài liệu Kế hoạch (`docs/Timeline_and_Contribution.md`)
- Cập nhật toàn bộ các đường dẫn tuyệt đối sang đường dẫn tương đối (đặc biệt trong mục 6: Roadmap đọc nghiên cứu `research/reviews/*.md` và `docs/DataMate_Zalo_AI_Challenge_2026.md`) để đồng đội tải repo về máy khác có thể mở đọc trực tiếp.

---

## 🧪 Kết quả Kiểm thử Thực tế trên Dữ liệu Cuộc thi
- Đã chạy kiểm thử trên toàn bộ 30 shop của tập train (`competition_data/train/data`):
  - **Tổng số business:** 30/30 (100% thành công)
  - **Tổng số bảng trích xuất:** 137 bảng
  - **Tổng số dòng dữ liệu:** 3,536,269 dòng
  - **Nạp SQLite In-Memory:** ~0.66s cho ~172.000 dòng.

