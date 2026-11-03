# Đánh Giá Hệ Thống & Hướng Nâng Cấp — Long (AI Architect & Model Lead)

- **Người thực hiện**: Long
- **Vai trò**: AI Architect & Model Lead
- **Thời điểm**: Hoàn thành Phase 2 (03/11/2026)
- **Các module phụ trách chính**:
  - `src/datamate/llm/client.py` (Quản lý và suy luận LLM Qwen2.5-Coder)
  - `src/datamate/llm/prompt_builder.py` (Phân loại ý định, xây dựng prompt, few-shot động)
  - `src/datamate/llm/feasibility.py` (Module 3 — Deterministic Feasibility Gate)
  - `src/datamate/output/normalizer.py` (Module 6 — Format Normalizer & Tie-Breaker)
  - `predict.py` (Pipeline điều phối suy luận chính)

---

## 1. Ưu điểm trong hệ thống hiện tại

1. **Kiểm soát tốt tính tái lập và tài nguyên phần cứng**:
   - `LLMClient` được cấu hình chặt chẽ (`do_sample=False`, `temperature=0.0`), nạp mô hình dạng lượng tử hóa 4-bit (NF4) kèm quản lý dọn bộ nhớ cache VRAM tự động.
   - Quá trình suy luận chạy ổn định, bóc tách code block từ phản hồi của mô hình an toàn.
2. **Lá chắn tất định bảo vệ điểm số hiệu quả**:
   - `feasibility.py` (Module 3) hoạt động chính xác trên 3.000 câu tập `train`: bắt đúng **70/70 câu `unanswerable` (Recall 100%)** và **không chặn nhầm câu nào (Precision 100%)**.
   - Bắt trọn vẹn các câu hỏi thiếu dữ liệu (thuộc tính chủ quan, kỳ hỏi ngoài khoảng ngày theo Điều 7, thiếu bảng/cột nghiệp vụ) giúp lấy trọn điểm cộng (+1) mà không tốn tài nguyên GPU.
3. **Bộ chuẩn hóa đầu ra bao phủ tốt các bẫy dữ liệu**:
   - `normalizer.py` (Module 6) ưu tiên cấu trúc thực tế của giá trị trả về trước khi suy đoán theo từ khóa câu hỏi, tránh làm hỏng các kiểu `list`, `table`, `string`.
   - Phân biệt chính xác câu hỏi phần trăm với nồng độ thuốc (`PCT_PATTERN` đạt 100% trên 2.462 câu số học).
   - Cơ chế bảo vệ `code_text` trong `normalize_percent` ngăn chặn việc nhân đôi 100 đối với các đáp án phần trăm nhỏ ($\le 1\%$).
   - Tuân thủ đúng quy tắc làm tròn tiền tệ (`ROUND_HALF_UP`) và xử lý đồng hạng theo mã/tên (Điều 9 Rulebook).
4. **Cơ chế tự sửa lỗi thực thi (Runtime Self-Correction)**:
   - Trong `predict.py`, khi code sinh ra ở lượt 1 gặp ngoại lệ (`KeyError`, `ValueError`...), hệ thống tự động gửi phản hồi lỗi để LLM viết lại mã 1 lần trước khi chuyển về `abstain`, giúp tăng tỷ lệ thực thi thành công.

---

## 2. Nhược điểm và hạn chế hiện tại

1. **Bộ giải mã thời gian trong `prompt_builder.py` còn đơn giản**:
   - Hàm `resolve_temporal_context` hiện mới giải mã được các mốc thông thường (tháng cụ thể, quý, hôm nay/hôm qua, tuần này/tuần trước, N ngày gần nhất, dịp Tết).
   - Chưa xử lý được các mốc thời gian phức tạp hơn như: *"nửa đầu/cuối tháng"*, *"10 ngày cuối tháng"*, *"3 tháng liền nhau kết thúc ở tháng X"*, *"rằm/mùng 1 âm lịch"* (trong khi Phát đã xây dựng các hàm này trong `grounding/temporal.py`).
2. **Môi trường thực thi trong `predict.py` chưa có giới hạn thời gian (timeout)**:
   - Hiện tại hàm `execute_solution` trong `predict.py` vẫn dùng `exec()` trực tiếp trên tiến trình chính, chưa có cơ chế timeout để ngắt nếu mô hình sinh vòng lặp vô hạn hoặc truy vấn quá nặng.
3. **Thư viện Few-shot còn thiếu một số dạng bài toán đặc thù**:
   - Chưa có ví dụ mẫu hướng dẫn bài toán tính tồn kho theo lô (`Nhập - Bán + Trả`) kết hợp quy đổi đơn vị dạng `divmod` để trả về `[số hộp chẵn, số viên lẻ]`.
   - Chưa có ví dụ mẫu chuyên biệt cho bài toán chuỗi thời gian nhiều tháng (kiểm tra tăng liên tục hoặc tính tỷ lệ thay đổi so với tháng liền trước).

---

## 3. Hướng nâng cấp cho Long

1. **Tích hợp bộ giải mã thời gian của Phát vào `prompt_builder.py`**:
   - Gọi trực tiếp module `grounding.temporal.resolve_temporal` để tận dụng khả năng giải mã lịch âm, nửa đầu/cuối tháng và chuỗi tháng liên tiếp.
   - Đưa cả kỳ chính (`start_date`, `end_date`) và kỳ đối chiếu (`comparison_start`, `comparison_end`) vào prompt khi câu hỏi yêu cầu so sánh với tháng liền trước.
2. **Bổ sung 2 ví dụ Few-shot chuyên biệt vào `FEW_SHOT_LIBRARY`**:
   - `inventory_unit_conversion`: Hướng dẫn cách tính tồn kho từ thẻ kho hoặc đơn nhập/bán/trả theo lô và dùng `divmod` để trả về định dạng `list` `[hộp chẵn, lẻ]`.
   - `time_series`: Hướng dẫn gom nhóm theo tháng, sắp xếp theo thời gian và tính toán biến động doanh thu giữa các kỳ liên tiếp.
3. **Bổ sung bộ kiểm tra tính hợp lý hậu thực thi (Sanity Check)**:
   - Ở lượt Self-Correction, nếu kết quả trả về là số âm bất thường hoặc số 0 vô lý cho các câu hỏi doanh thu/số lượng thì chủ động ép về `abstain` (0 điểm) thay vì gửi đáp án sai để tránh bị phạt -1 điểm.

