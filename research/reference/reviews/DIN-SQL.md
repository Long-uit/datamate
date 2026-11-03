# DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with Self-Correction

| Thông tin | Chi tiết |
|---|---|
| **Tác giả** | Mohammadreza Pourreza, Davood Rafiei |
| **Năm / Nguồn** | arXiv:2304.11015v3, 2 Nov 2023 |
| **Loại bài** | Phương pháp prompt-based Text-to-SQL |
| **Nguồn chính** | [PDF gốc](../papers/DIN-SQL.pdf) · [arXiv](https://arxiv.org/abs/2304.11015) |

## 1. Tóm tắt nhanh (TL;DR)

DIN-SQL chia Text-to-SQL thành các bước schema linking, phân loại/khai triển câu hỏi, sinh SQL và tự sửa lỗi. Trong các thử nghiệm của bài, cấu hình GPT-4 đạt 85,3% execution accuracy trên Spider test và 55,9% trên BIRD test. Đây là baseline hữu ích để hiểu task decomposition, nhưng kết quả chính dựa trên API GPT-4 và không thể triển khai trực tiếp trong challenge offline.

## 2. Bối cảnh & Vấn đề nghiên cứu

Few-shot prompting có thể suy giảm trên câu hỏi cần nhiều phép nối, truy vấn lồng nhau hoặc schema linking khó. Tác giả nghiên cứu xem việc chia bài toán thành bước nhỏ hơn có giúp mô hình sinh SQL chính xác hơn không.

## 3. Phương pháp / Nội dung chính

1. **Schema linking:** trích xuất bảng, cột, thực thể và giá trị liên quan từ câu hỏi/schema.
2. **Phân loại và phân rã:** nhận diện độ phức tạp, tạo biểu diễn trung gian và các bước cần thiết.
3. **Sinh SQL:** chọn prompt phù hợp với nhóm truy vấn.
4. **Self-correction:** dùng phản hồi của mô hình để sửa SQL đã sinh.

Sơ đồ tổng thể nằm ở PDF p. 4; phần phương pháp ở §§4.1–4.4, pp. 4–6.

## 4. Thực nghiệm & Kết quả chính

> **Cách đọc số liệu:** Các kết quả thuộc benchmark, split, metric và phiên bản mô hình của bài báo. Không so trực tiếp SQL execution accuracy với PA của challenge.

Tác giả thử nghiệm trên Spider và BIRD với GPT-4 và Codex Davinci qua API. DIN-SQL + GPT-4 đạt 85,3% EX trên Spider test; trên BIRD test đạt 55,9% EX và 59,44 VES (PDF pp. 7–9, Tables 2–3). Các kết quả thuộc benchmark và phiên bản mô hình nêu trong bài, không phải kết quả trên dữ liệu DataMate.

## 5. Tính mới & Đóng góp

- Trình bày một pipeline decomposition có thể đọc và kiểm tra từng bước.
- Ablation trên Spider dev cho thấy schema linking, phân loại/độ phức tạp và self-correction đóng góp khác nhau vào kết quả (PDF p. 10, Table 5).
- Cung cấp một baseline lịch sử để đối chiếu với các kiến trúc multi-agent xuất hiện sau này.

## 6. Hạn chế

- Thử nghiệm chính gọi OpenAI API; không đáp ứng điều kiện inference offline và trọng số mở của challenge.
- Bài báo ghi nhận cấu hình GPT-4 tốn khoảng 0,5 USD và khoảng 60 giây cho một câu hỏi Spider tại thời điểm thử nghiệm (PDF p. 10). Chi phí/thời gian này không thể chuyển trực tiếp sang phần cứng challenge.
- Prompt và ví dụ được thiết kế thủ công; bài báo nêu đây là giới hạn, cùng chi phí và độ trễ của pipeline.
- Tác vụ đầu ra là SQL; challenge yêu cầu trả lời theo kiểu number, percent, date, list, table hoặc abstain.

## 7. Ý nghĩa ứng dụng

> **Phân biệt nguồn:** Khuyến nghị dưới đây là suy luận ứng dụng cho DataMate; bài báo không đánh giá trực tiếp trên challenge.

Có thể tham khảo nguyên tắc tách việc hiểu câu hỏi, chọn dữ liệu và xác minh kết quả thành các bước kiểm tra được. Không nên sao chép phụ thuộc API, prompt GPT-4 hay số bước agent; DataMate cần chạy offline và chấm PA với đáp án có kiểu dữ liệu chính xác.

> Các ý kiến áp dụng cho DataMate trong mục này là suy luận của review; bài báo không đánh giá trên bộ dữ liệu challenge.

## 8. Từ khóa

Text-to-SQL, task decomposition, schema linking, in-context learning, self-correction.

## 9. Mức độ phù hợp với challenge DataMate

**Phân nhóm: Tham khảo.** Hữu ích khi cần baseline về phân rã tác vụ hoặc đọc tiếp MAC-SQL. Mức chuyển giao thấp hơn các bài spreadsheet/abstention vì benchmark là SQL và hệ thống chính dùng API đóng; nên giữ trong nhóm tham khảo thay vì bộ đọc triển khai.

## 10. Nguồn và truy nguyên kết quả

- Kiến trúc và phương pháp: PDF pp. 4–6.
- Benchmark và setup: PDF p. 7.
- Kết quả Spider/BIRD: PDF pp. 8–9, Tables 2–3.
- Ablation: PDF p. 10, Table 5. Hạn chế về chi phí/độ trễ: PDF p. 10, §7.

