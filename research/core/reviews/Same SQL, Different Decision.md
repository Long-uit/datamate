# Same SQL, Different Decision: Aggregate Risk Hides Cross-Lingual Instability in Text-to-SQL Verification

| Thông tin | Chi tiết |
|---|---|
| **Tác giả** | Avinash Goutham Aluguvelly |
| **Năm / Venue** | Workshop on Open Reasoning Across Cultures and Languages (ORACLE), ACL Anthology 2026 |
| **Loại bài** | Nghiên cứu thực nghiệm về verifier đa ngôn ngữ và quyết định execute/defer |
| **Nguồn chính** | [PDF gốc](../papers/Same%20SQL,%20Different%20Decision.pdf) · [ACL Anthology](https://aclanthology.org/2026.oracle-main.6/) |

## 1. Tóm tắt nhanh (TL;DR)

Bài báo giữ nguyên database, schema, SQL ứng viên và nhãn đúng/sai dựa trên thực thi, rồi thay đổi ngôn ngữ câu hỏi để kiểm tra verifier. Với bảy ngôn ngữ và hai verifier mở 7B–8B, từ 14% đến 27% quyết định execute/defer bị đổi khi dùng ngưỡng hiệu chỉnh trên tiếng Anh. Với tiếng Việt, tác giả ghi nhận unsafe promotion 16,9% ở Llama-3.1-8B trong tập kiểm tra; họ cũng cảnh báo độ trung thực của literal trong bản dịch tiếng Việt thấp hơn các ngôn ngữ còn lại. Kết quả gợi ý cần kiểm tra verifier trên chính ngôn ngữ triển khai; không thể suy ra cùng mức rủi ro trên DataMate.

## 2. Bối cảnh & Vấn đề nghiên cứu

Verifier thường dùng điểm tin cậy và ngưỡng hiệu chỉnh để quyết định tự thực thi hay trì hoãn một truy vấn. Nếu ngưỡng được hiệu chỉnh bằng câu hỏi tiếng Anh, thay ngôn ngữ câu hỏi có thể làm thay đổi quyết định dù SQL ứng viên và nhãn đúng/sai giữ nguyên. Chỉ nhìn selective risk hoặc coverage tổng hợp có thể che khuất các quyết định sai theo từng ngôn ngữ.

## 3. Phương pháp / Nội dung chính

- Dùng MultiSpider và hai verifier mở: Llama-3.1-8B và Qwen2.5-Coder-7B.
- Tạo SQL ứng viên từ câu tiếng Anh; chấm cùng ứng viên bằng câu hỏi ở tiếng Anh, Đức, Tây Ban Nha, Pháp, Nhật, Việt và Trung.
- Đối chiếu kết quả thực thi với truy vấn chuẩn để tạo nhãn đúng/sai; đặt ngưỡng trên calibration set tiếng Anh với mục tiêu risk 10%, rồi giữ ngưỡng đó khi đổi ngôn ngữ.
- Tách các lần đổi quyết định thành unsafe promotion và lost automation. Quy trình và dữ liệu được mô tả ở PDF pp. 2–4.

## 4. Thực nghiệm & Kết quả chính

> **Cách đọc số liệu:** Các kết quả thuộc benchmark, split, metric và phiên bản mô hình của bài báo. Tỷ lệ risk/decision flip không phải PA.

Trên test, 14%–27% quyết định execute/defer khác nhau giữa tiếng Anh và ngôn ngữ đích dù SQL ứng viên giống nhau (PDF pp. 1, 4, 8). Với Llama, tiếng Việt có unsafe promotion 16,9%; 22,9% các ứng viên sai mà verifier đã defer bằng tiếng Anh lại được execute khi câu hỏi chuyển sang tiếng Việt (PDF p. 5, Table 3). Tác giả phát hiện literal trong câu hỏi tiếng Việt có fidelity thấp: 47,3% ở các mẫu có literal được giữ nguyên trong phép kiểm toán; loại các mismatch phát hiện được làm thay đổi unsafe-promotion tối đa 0,6 điểm phần trăm (PDF p. 4). Vì vậy kết quả tiếng Việt cần được đọc cùng giới hạn dịch thuật đó.

## 5. Tính mới & Đóng góp

- Dùng thiết kế paired/counterfactual để giữ SQL, schema, database và nhãn thực thi cố định khi đổi ngôn ngữ.
- Phân biệt rủi ro do chạy truy vấn sai với việc bỏ lỡ tự động hóa đúng; không gộp mọi decision flip thành một loại lỗi.
- Đánh giá thêm các hướng hiệu chỉnh và độ bền theo cấu hình verifier ở §§6–8 (PDF pp. 6–8).

## 6. Hạn chế

- Chỉ hai họ verifier 7B–8B và benchmark MultiSpider; không đánh giá câu hỏi tự nhiên của cửa hàng Việt Nam hoặc workbook/CSV.
- SQL ứng viên được tạo từ tiếng Anh; đây không phải đánh giá toàn bộ pipeline sinh câu trả lời từ đầu bằng tiếng Việt.
- Bản dịch có lỗi giữ nguyên quoted literals, đặc biệt tiếng Việt; tác giả trình bày kiểm toán và phân tích nhạy cảm, nhưng khái quát hóa vẫn phụ thuộc vào độ tương đương ngữ nghĩa của bản dịch.
- Mục tiêu risk 10% và quyết định execute/defer khác PA của challenge. DataMate cần đánh giá bằng chính tiêu chí đúng/sai/abstain và các kiểu đầu ra được quy định.

## 7. Ý nghĩa ứng dụng

> **Phân biệt nguồn:** Khuyến nghị dưới đây là suy luận ứng dụng cho DataMate; bài báo không đánh giá trực tiếp trên challenge.

Nếu DataMate dùng verifier hoặc cổng abstain, hiệu chỉnh bằng tiếng Anh rồi áp dụng nguyên trạng cho tiếng Việt có thể không an toàn. Cần báo cáo riêng coverage, lỗi trong câu trả lời được chấp nhận, và tỷ lệ trả lời đúng bị từ chối trên tập tiếng Việt. Kết quả bài báo chỉ là lý do để kiểm tra; không phải bằng chứng rằng một ngưỡng cụ thể sẽ phù hợp cho challenge.

> Các ý kiến áp dụng cho DataMate trong mục này là suy luận của review; bài báo không đánh giá trên bộ dữ liệu challenge.

## 8. Từ khóa

Cross-lingual verification, Text-to-SQL, selective prediction, risk-coverage, abstention, Vietnamese.

## 9. Mức độ phù hợp với challenge DataMate

**Phân nhóm: Cốt lõi khi DataMate có verifier/abstention gate; nếu không thì chuyển thành tham khảo.** Đây là bài sát tiếng Việt và kiểm soát quyết định từ chối/chạy truy vấn. Giới hạn chuyển giao quan trọng là test SQL verifier trên MultiSpider không giống chấm đáp án typed JSONL theo PA; cần tự đo trên validation challenge trước khi áp dụng.

## 10. Nguồn và truy nguyên kết quả

- Thiết kế paired, candidate generation và split: PDF pp. 2–4.
- Kết quả flip và kiểm toán literal: PDF pp. 4–5, Tables 1–3.
- Hiệu chỉnh, robustness và giới hạn: PDF pp. 6–9.
- Bản xuất bản và đường tải nằm trên ACL Anthology ở phần thông tin nguồn.

