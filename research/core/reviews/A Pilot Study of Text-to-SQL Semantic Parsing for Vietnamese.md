# A Pilot Study of Text-to-SQL Semantic Parsing for Vietnamese

| Thông tin | Chi tiết |
|---|---|
| **Tác giả** | Anh Tuan Nguyen, Mai Hoang Dao, Dat Quoc Nguyen |
| **Năm / Venue** | Findings of EMNLP 2020, tr. 4079–4085; DOI: 10.18653/v1/2020.findings-emnlp.364 |
| **Loại bài** | Benchmark và nghiên cứu thực nghiệm Text-to-SQL tiếng Việt |
| **Nguồn chính** | [PDF gốc](../papers/A%20Pilot%20Study%20of%20Text-to-SQL%20Semantic%20Parsing%20for%20Vietnamese.pdf) · [ACL Anthology](https://aclanthology.org/2020.findings-emnlp.364/) |

## 1. Tóm tắt nhanh (TL;DR)

Bài báo xây dựng một bộ dữ liệu Text-to-SQL tiếng Việt bằng cách dịch thủ công Spider, sau đó đánh giá EditSQL và IRNet cùng các cấu hình tách từ, liên kết schema và encoder tiếng Việt. IRNet dùng PhoBERT đạt 53,2% exact match trên test; kết quả cho thấy các lựa chọn tiền xử lý và biểu diễn ngôn ngữ ảnh hưởng đáng kể đến hiệu năng trong thiết lập này. Đây là tài liệu nền phù hợp để hiểu các khó khăn tiếng Việt, nhưng dữ liệu dịch từ Spider không đại diện đầy đủ cho câu hỏi đời thường về cửa hàng Việt Nam.

## 2. Bối cảnh & Vấn đề nghiên cứu

Phần lớn benchmark Text-to-SQL tại thời điểm bài báo tập trung vào tiếng Anh. Tiếng Việt có ranh giới từ khác biệt: khoảng trắng thường tách âm tiết, không nhất thiết tách từ. Điều này ảnh hưởng đến biểu diễn câu hỏi và việc nối các cụm từ với tên cột hoặc giá trị trong cơ sở dữ liệu.

## 3. Phương pháp / Nội dung chính

- Tạo bộ dữ liệu bằng cách dịch thủ công các câu hỏi và SQL của Spider sang tiếng Việt; bộ dữ liệu có 9.691 câu hỏi, 5.263 truy vấn SQL và 166 database. Split test có 1.906 câu hỏi trên 42 database (PDF, p. 2).
- Đánh giá hai parser có mã nguồn là EditSQL và IRNet.
- So sánh biểu diễn theo âm tiết và theo từ; thử nghiệm đặc trưng cú pháp tiềm ẩn từ parser tiếng Việt và NPMI để liên kết giá trị ô với cột.
- So sánh các encoder XLM-R và PhoBERT. Các cấu hình và số liệu được trình bày trong PDF, pp. 3–4.

## 4. Thực nghiệm & Kết quả chính

> **Cách đọc số liệu:** Các kết quả thuộc benchmark, split, metric và phiên bản mô hình của bài báo. Không so trực tiếp exact match với PA của challenge.

Trên test, IRNet-PhoBERT đạt 53,2% exact match; EditSQL-PhoBERT đạt 52,6% (Table 3, PDF p. 4). IRNet dùng word segmentation đạt 43,6%, so với 38,2% ở cấu hình syllable-level. Bỏ NPMI schema linking làm giảm hơn 6 điểm phần trăm exact match của IRNet trên dev và test. Các con số này thuộc split, mô hình và giao thức của bài báo; chúng không phải PA và không so sánh trực tiếp với challenge.

## 5. Tính mới & Đóng góp

- Cung cấp benchmark Text-to-SQL công khai đầu tiên cho tiếng Việt tại thời điểm xuất bản.
- Đánh giá có kiểm soát vai trò của tách từ, đặc trưng cú pháp, NPMI schema linking và encoder đơn ngữ.
- Phân tích lỗi trên dev cho thấy lỗi liên kết cột, cấu trúc truy vấn phức tạp và toán tử ngôn ngữ là các nguồn sai thường gặp (PDF, pp. 4–5).

## 6. Hạn chế

- Câu hỏi được dịch từ Spider, không được thu thập từ chủ cửa hàng Việt Nam; cách diễn đạt, tên riêng, đơn vị tiền và quy tắc nghiệp vụ đời thực có thể khác.
- Schema và SQL kế thừa thiết kế của Spider; kết quả không đo khả năng đọc workbook nhiều sheet, CSV lộn xộn hoặc rulebook theo doanh nghiệp.
- Thực nghiệm dùng các parser seq2seq và encoder tại thời điểm 2020, nên không thể dùng điểm số để dự báo hiệu năng của LLM hiện nay.
- Tập dữ liệu hữu ích cho nghiên cứu ngôn ngữ, nhưng không thay thế tập validation nội bộ theo challenge.

## 7. Ý nghĩa ứng dụng

> **Phân biệt nguồn:** Khuyến nghị dưới đây là suy luận ứng dụng cho DataMate; bài báo không đánh giá trực tiếp trên challenge.

- Giữ lại các bài kiểm tra tiếng Việt cụ thể: tách từ có làm hỏng tên sản phẩm/địa danh không, đồng nghĩa có nối được với tiêu đề cột không, và câu hỏi có dấu/không dấu được xử lý ra sao.
- NPMI và PhoBERT là các kết quả trong thiết lập của bài báo, không phải yêu cầu phải dùng đúng thành phần đó trong DataMate.

> Các ý kiến áp dụng cho DataMate trong mục này là suy luận của review; bài báo không đánh giá trên bộ dữ liệu challenge.

## 8. Từ khóa

Vietnamese NLP, Text-to-SQL, word segmentation, schema linking, PhoBERT, Spider.

## 9. Mức độ phù hợp với challenge DataMate

**Phân nhóm: Cốt lõi — tài liệu ngôn ngữ tiếng Việt.** Nên dùng để lập danh sách lỗi ngôn ngữ và thiết kế kiểm tra tiếng Việt. Không nên xem đây là bằng chứng rằng parser SQL hoặc các kết quả năm 2020 sẽ chuyển nguyên trạng sang DataMate: challenge có workbook/CSV/SQLite, quy tắc kinh doanh riêng và chấm câu trả lời có kiểu dữ liệu chính xác.

## 10. Nguồn và truy nguyên kết quả

- Dataset và cách chia split: PDF p. 2.
- Phương pháp và cấu hình: PDF pp. 3–4.
- Kết quả chính (Tables 3–4), NPMI và phân tích lỗi: PDF pp. 4–5.
- Kết luận: PDF p. 5. DOI và bản xuất bản chính thức có tại ACL Anthology ở phần thông tin nguồn.

