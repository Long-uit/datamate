# Nhật ký thay đổi DataMate — 03/11/2026

- **Người thực hiện:** Long
- **Ngày:** 03/11/2026 (giờ Việt Nam)
- **Phạm vi:** ghi nhận các thay đổi hiện có trong working tree của dự án DataMate trong ngày.

## 1. Benchmark

- Nâng cấp `benchmark/split.py` để kiểm tra dữ liệu đầu vào và tạo các tập train/validation có cấu trúc, manifest và thông tin truy vết.
- Bổ sung hai kiểu phân chia: `within_business` (cùng doanh nghiệp có thể xuất hiện ở train và validation) và `business_holdout` (giữ doanh nghiệp validation ra khỏi train theo từng fold).
- Tạo các artifact cho `within_business_v1` và năm fold `business_holdout_v1` trong `benchmark/splits/`.
- Nâng cấp `benchmark/evaluate.py` để kiểm tra schema/output, tính điểm PA và tạo báo cáo chi tiết.
- Viết tài liệu kiến trúc, cách tạo split, cách đánh giá và giới hạn diễn giải tại `benchmark/README.md`.
- Cập nhật/bổ sung kiểm thử cho splitter và evaluator trong `tests/benchmark/`.
- Các file partition cũ ở gốc `benchmark/` đang được Git ghi nhận là đã xóa; artifact thay thế nằm dưới `benchmark/splits/`. Lệnh evaluator mặc định có thể vẫn trỏ tới đường dẫn cũ, nên cần truyền đường dẫn của split mới khi chạy.

## 2. Research

- Sắp xếp tài liệu thành hai nhóm: `research/core/` (tài liệu trọng tâm) và `research/reference/` (tài liệu tham khảo); mỗi nhóm chứa `papers/` và `reviews/`.
- Chuyển các PDF và review tương ứng vào cấu trúc nhóm nói trên, đồng thời thêm các tài liệu mới hiện có trong nhóm như bài nghiên cứu về Text-to-SQL tiếng Việt và `Same SQL, Different Decision`.
- Viết lại `research/README.md` để giải thích cách tổ chức và định hướng sử dụng tài liệu.
- Những file cũ dưới `research/papers/` và `research/reviews/` xuất hiện là đã xóa trong Git vì vị trí mới được tổ chức dưới `core/` và `reference/`.

## 3. Kiến trúc và tài liệu giải pháp

- Cập nhật tài liệu challenge `docs/DataMate_Zalo_AI_Challenge_2026.md`.
- Thêm `docs/DataMate_Competitive_Solution.md` để trình bày định hướng giải pháp cạnh tranh, gồm các thành phần mô hình/xử lý và các yêu cầu triển khai liên quan.
- Cập nhật `README.md` tổng quan dự án.
- Thêm `docs/Benchmark_Revision_Proposal.md` làm tài liệu đề xuất điều chỉnh benchmark.

## 4. Mã nguồn và kiểm thử liên quan

- Cập nhật `predict.py` để kết nối luồng dự đoán với các thành phần mới.
- Thêm `src/datamate/llm/feasibility.py` cho bước đánh giá câu hỏi có thể trả lời dựa trên dữ liệu/ngữ cảnh hay không.
- Thêm `src/datamate/output/normalizer.py` để chuẩn hóa đầu ra.
- Thêm kiểm thử cho feasibility gate và output normalizer tại `tests/llm/` và `tests/output/`.

## 5. Ghi chú kiểm tra

- Nhật ký benchmark chi tiết trước/sau nằm tại `logs/benchmark_before_after_20261103.md`.
- Các kiểm tra benchmark được liệt kê trong nhật ký đó; test suite tổng thể chưa được xác nhận là đã chạy.
- Danh sách trên phản ánh thay đổi đang có trong working tree khi lập log; trạng thái Git không lưu thời điểm từng chỉnh sửa, do đó đây không phải bằng chứng độc lập về thời điểm phát sinh mọi thay đổi.
