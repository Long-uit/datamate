# DataMate — Zalo AI Challenge 2026

---

## Tuyên bố Sứ mệnh (Mission Statement)

> *"Millions of Vietnamese shop owners, teachers, clinics and small offices keep their records in spreadsheets and simple databases — but few can write a query. DataMate challenges you to build an AI agent that answers everyday questions in Vietnamese directly on messy, real-world tabular data: multi-sheet Excel exports, inconsistent product names, colloquial phrasing, and business logic like cost of goods or overdue debt. Your agent must find the right answer on its own — and know when the data cannot answer at all. Correct answers score, wrong answers cost, silence is free: build a system that is right when it speaks."*

---

> Tài liệu tổng hợp thông tin cuộc thi từ các phần **Description, Data, Evaluation và Rules** được cung cấp.

## Mục lục

1. [Description — Mô tả bài toán](#1-description--mô-tả-bài-toán)
2. [Data — Dữ liệu](#2-data--dữ-liệu)
3. [Evaluation — Đánh giá](#3-evaluation--đánh-giá)
4. [Rules — Quy định và các vòng thi](#4-rules--quy-định-và-các-vòng-thi)

---

# 1. Description — Mô tả bài toán

## 1.1. Bối cảnh

Bảng tính và các cơ sở dữ liệu đơn giản là những hệ thống lưu trữ dữ liệu được sử dụng rộng rãi. Nhiều cá nhân và tổ chức có dữ liệu nhưng không có khả năng viết truy vấn để khai thác dữ liệu đó.

DataMate hướng đến khả năng cho phép người dùng đặt câu hỏi bằng tiếng Việt tự nhiên và nhận được câu trả lời chính xác trực tiếp từ dữ liệu có cấu trúc.

## 1.2. Mục tiêu cuộc thi

Xây dựng một **AI Agent** có khả năng:

- Nhận dữ liệu có cấu trúc từ các tệp CSV, Excel và SQLite.
- Hiểu câu hỏi bằng tiếng Việt tự nhiên.
- Phân tích dữ liệu để tạo câu trả lời chính xác.
- Từ chối trả lời khi dữ liệu không đủ cơ sở để trả lời câu hỏi.

Dữ liệu cuộc thi tập trung vào các hộ kinh doanh nhỏ tại Việt Nam. Tuy nhiên, năng lực mà hệ thống cần đạt được có tính tổng quát: **hỏi đáp bằng ngôn ngữ tự nhiên trên dữ liệu dạng bảng**.

## 1.3. Đầu vào (Input)

Mỗi yêu cầu gồm các thành phần:

| Thành phần          | Nội dung                                                                                                                                          |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Data package          | Gói dữ liệu của một doanh nghiệp, gồm một hoặc nhiều tệp `.csv`, `.xlsx`, `.sqlite` và tệp `README.md` mô tả doanh nghiệp. |
| Question              | Câu hỏi bằng tiếng Việt đời thường.                                                                                                       |
| As-of date            | Ngày tham chiếu dùng để xác định mốc “hôm nay” khi xử lý các biểu thức thời gian tương đối.                                  |
| Rulebook              | Bộ quy tắc nghiệp vụ áp dụng cho split.                                                                                                      |
| Solar–lunar calendar | Lịch dương – âm dùng chung cho các doanh nghiệp trong split.                                                                               |

## 1.4. Đầu ra (Output)

Mỗi câu hỏi có một câu trả lời cuối cùng thuộc một trong các loại được quy định trong phần Evaluation:

- Giá trị: `number`, `percent`, `string`, `date`, `boolean`.
- Nhiều giá trị: `list`, `table`.
- Không thể trả lời do dữ liệu không hỗ trợ: `unanswerable`.
- Agent chủ động không trả lời: `abstain`.

---

# 2. Data — Dữ liệu

## 2.1. Các loại hình kinh doanh

Dữ liệu bao phủ nhiều loại hình doanh nghiệp nhỏ tại Việt Nam, gồm:

- Cửa hàng tạp hóa.
- Quán cà phê và trà sữa.
- Nhà hàng.
- Nhà thuốc.
- Cửa hàng vật liệu xây dựng.
- Cửa hàng sửa chữa xe máy.
- Cửa hàng mẹ và bé.
- Các loại hình kinh doanh khác.

Private test có các loại hình kinh doanh không xuất hiện trong training data hoặc public test data.

## 2.2. Đặc điểm dữ liệu của mỗi doanh nghiệp

| Thuộc tính       | Mô tả                                                                                          |
| ------------------ | ------------------------------------------------------------------------------------------------ |
| Khoảng thời gian | 12–30 tháng hoạt động.                                                                      |
| Quy mô            | Từ vài trăm đến khoảng 300.000 dòng.                                                      |
| Tính mùa vụ     | Có các yếu tố mùa vụ như Tết, Trung thu, ngày lễ, ngày nhận lương và cuối tuần. |
| Định dạng       | Một hoặc nhiều tệp CSV, XLSX hoặc SQLite.                                                   |
| Tài liệu mô tả | Mỗi doanh nghiệp có `README.md`; chất lượng và mức độ chi tiết không đồng đều. |

`README.md` có thể chứa đầy đủ từ điển dữ liệu, một số ghi chú không chính thức hoặc rất ít thông tin.

## 2.3. Cấu trúc package

```text
<split>/
├── data/<business_id>/
│   ├── *.csv | *.xlsx | *.sqlite
│   └── README.md
├── rulebook.md
├── calendar.csv
├── questions.jsonl
└── answers.jsonl
```

| Thành phần                                  | Nội dung                                                                   |
| --------------------------------------------- | --------------------------------------------------------------------------- |
| `data/<business_id>/`                       | Thư mục dữ liệu của từng doanh nghiệp.                               |
| Các tệp `*.csv`, `*.xlsx`, `*.sqlite` | Một hoặc nhiều tệp dữ liệu của doanh nghiệp.                        |
| `README.md`                                 | Mô tả doanh nghiệp và các ghi chú liên quan đến dữ liệu.         |
| `rulebook.md`                               | Các quy tắc mặc định và từ vựng nghiệp vụ của split.             |
| `calendar.csv`                              | Lịch dương – âm, phục vụ xử lý các mốc lịch như Tết.          |
| `questions.jsonl`                           | Mỗi dòng chứa một câu hỏi.                                            |
| `answers.jsonl`                             | Chứa đáp án tham chiếu cho training; không có trong các split test. |

## 2.4. Questions và Answers

### `questions.jsonl`

Mỗi dòng là một đối tượng câu hỏi, có các trường:

| Trường        | Ý nghĩa                                                    |
| --------------- | ------------------------------------------------------------ |
| `id`          | Định danh câu hỏi.                                       |
| `business_id` | Định danh doanh nghiệp chứa dữ liệu cần phân tích.  |
| `question`    | Nội dung câu hỏi bằng ngôn ngữ tự nhiên.             |
| `as_of_date`  | Ngày tham chiếu để diễn giải thời gian tương đối. |

### `answers.jsonl`

- Chỉ training businesses có `answers.jsonl`.
- Mỗi đáp án được liên kết với câu hỏi thông qua trường `id`.
- Mỗi dòng tuân theo cấu trúc đáp án dùng khi nộp bài và có thêm trường `alias`.
- `alias` liệt kê các dạng tên khác được chấp nhận, gồm cách viết khác của tên có trong dữ liệu và mã mặt hàng.
- Với câu hỏi không thể trả lời, trường `answer` có giá trị `null`.
- Khi nộp bài, không cần trường `alias`.

## 2.5. Splits và Rulebook

Mỗi split có `rulebook.md` riêng. Rulebook quy định cách diễn giải mặc định cho các thuật ngữ thông dụng khi câu hỏi không nêu cách hiểu khác.

**Agent phải đọc và áp dụng rulebook của chính split đang được xử lý; rulebook có thể khác nhau giữa các split.**

Các quy tắc mặc định được mô tả trong tài liệu dữ liệu gồm:

| Thuật ngữ             | Cách diễn giải mặc định                                                                                                         |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Doanh thu               | Tổng giá trị các dòng hàng sau chiết khấu ở cấp dòng; không trừ voucher cấp đơn; không gồm VAT và phí giao hàng. |
| Đơn bị loại         | Loại đơn đã hủy và đơn có bất kỳ mặt hàng nào bị trả lại.                                                           |
| “Bán chạy”          | Xếp hạng theo số lượng bán.                                                                                                     |
| Tuần                   | Từ thứ Hai đến Chủ Nhật.                                                                                                        |
| “Tháng này”         | Tháng chứa `as_of_date`, tính đến và bao gồm chính ngày đó.                                                              |
| Giá vốn mặc định   | Giá vốn bình quân gia quyền theo lô hàng.                                                                                      |
| Khoảng thời gian Tết | Từ ngày 23 tháng Chạp đến mùng 10 tháng Giêng âm lịch.                                                                     |

## 2.6. Submission file

Trong cả hai vòng, đội thi nộp tệp `submission.jsonl`, gồm một đối tượng JSON trên mỗi dòng.

Các loại đáp án được hỗ trợ:

| `type`         | Nội dung trường `answer`                                                                             |
| ---------------- | --------------------------------------------------------------------------------------------------------- |
| `string`       | Chuỗi văn bản.                                                                                         |
| `number`       | Giá trị số.                                                                                            |
| `percent`      | Giá trị phần trăm.                                                                                    |
| `date`         | Ngày ở định dạng ISO.                                                                                |
| `boolean`      | Giá trị `true` hoặc `false`.                                                                       |
| `list`         | Danh sách có thứ tự.                                                                                  |
| `table`        | Bảng gồm tên cột và các dòng dữ liệu.                                                            |
| `unanswerable` | Kết quả cho biết dữ liệu không có thông tin cần thiết để trả lời; có thể kèm `reason`. |
| `abstain`      | Agent quyết định không trả lời.                                                                     |

- Trường `reason` của `unanswerable` là tùy chọn.
- Câu hỏi không có trong tệp nộp được chấm là `abstain`.
- Số lần nộp mỗi ngày tuân theo quy định chung của cuộc thi.

## 2.7. Docker image và log đầu ra

Docker image phải chứa:

- Source code training và inference.
- Model weights.
- Tệp `predict.sh`.
- README.

Yêu cầu đối với `predict.sh`:

- Đọc test set từ `/data`.
- Ghi kết quả vào `/result/submission.jsonl`.

Hệ thống phải ghi log theo từng câu hỏi vào `/result/logs/`. Log có thể ở bất kỳ định dạng nào nhưng tối thiểu phải có:

- Question ID.
- Câu trả lời cuối cùng.
- Thời gian thực thi.

Log có thể chứa thêm thông tin thể hiện quá trình tạo ra câu trả lời, chẳng hạn mã được sinh ra và kết quả thực thi.

---

# 3. Evaluation — Đánh giá

## 3.1. Trạng thái chấm điểm

Mỗi câu trả lời được chấm theo một trong ba trạng thái:

| Trạng thái | Điểm | Ý nghĩa               |
| ------------ | -----: | ----------------------- |
| Correct      |     +1 | Câu trả lời đúng.  |
| Abstain      |      0 | Agent không trả lời. |
| Wrong        |     -1 | Câu trả lời sai.     |

Không có điểm một phần (partial credit).

- Nếu câu trả lời có `type` là `abstain`, hoặc câu hỏi bị thiếu trong tệp nộp, kết quả được tính là abstain.
- Mọi câu trả lời khác chỉ đúng khi cả `type` và giá trị đều khớp với đáp án tham chiếu theo quy tắc tương ứng.
- Một câu hỏi có đáp án tham chiếu là `unanswerable` sẽ bị tính sai nếu Agent đưa ra bất kỳ câu trả lời nào khác.
- `unanswerable` chỉ đúng khi đáp án tham chiếu cũng là `unanswerable`.
- `abstain` luôn được tính là abstain, không phụ thuộc đáp án tham chiếu.

## 3.2. Quy tắc đối chiếu theo từng kiểu dữ liệu

| Type             | Quy tắc so khớp                                                                                                                                                                                                             |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `number`       | Khớp chính xác. Giá trị tham chiếu thường là số nguyên đối với tiền VND, số đếm và số lượng; hoặc được làm tròn đến 2 chữ số thập phân.                                                     |
| `percent`      | So khớp chính xác sau khi làm tròn đến 2 chữ số thập phân; dấu âm/dương phải chính xác.                                                                                                                     |
| `string`       | Câu trả lời và các dạng được chấp nhận của đáp án tham chiếu được chuẩn hóa rồi so sánh bằng nhau tuyệt đối.                                                                                       |
| `date`         | Khớp chính xác theo `yyyy-mm-dd`; câu hỏi về tháng dùng `yyyy-mm`.                                                                                                                                                |
| `boolean`      | Khớp chính xác `true` hoặc `false`.                                                                                                                                                                                   |
| `list`         | Các phần tử phải đúng thứ tự và khớp theo vị trí. Thứ tự theo yêu cầu câu hỏi hoặc mặc định trong rulebook.                                                                                             |
| `table`        | Tên cột được đối chiếu sau chuẩn hóa; nếu tên cột không khớp thì đối chiếu theo vị trí. Các hàng được so khớp như một tập hợp; ô tên dùng quy tắc string và ô số dùng quy tắc number. |
| `unanswerable` | Chỉ đúng nếu đáp án tham chiếu cũng là `unanswerable`.                                                                                                                                                            |
| `abstain`      | Luôn được chấm là abstain.                                                                                                                                                                                              |

### Chuẩn hóa `string`

Quy trình chuẩn hóa chuỗi gồm:

1. Chuẩn hóa Unicode NFC.
2. Chuyển chữ thành chữ thường.
3. Thay mọi ký tự không phải chữ cái, chữ số hoặc khoảng trắng bằng một khoảng trắng.
4. Xóa khoảng trắng ở đầu và cuối.
5. Gộp các chuỗi nhiều khoảng trắng liên tiếp thành một khoảng trắng.

Dấu tiếng Việt không bị loại bỏ. Mỗi đáp án tham chiếu có danh sách các dạng được chấp nhận, gồm các cách viết của tên xuất hiện trong dữ liệu doanh nghiệp và mã mặt hàng; các dạng này được chuẩn hóa trước khi so sánh.

## 3.3. Ranking questions

Các câu hỏi yêu cầu xếp hạng được xử lý theo các quy tắc:

- Sử dụng tiêu chí được nêu trong câu hỏi.
- Nếu câu hỏi không nêu tiêu chí, sử dụng tiêu chí mặc định trong rulebook.
- Sắp xếp giảm dần hoặc tăng dần theo yêu cầu.
- Các phần tử có giá trị bằng nhau được sắp xếp theo mã code tăng dần.
- Những câu hỏi có đáp án tham chiếu bị đồng hạng tại ranh giới Top-K, hoặc đồng hạng ở hạng 1 đối với câu hỏi dạng “... nhất”, được loại khỏi test set.
- Nếu số ứng viên ít hơn K, đáp án tham chiếu là tất cả ứng viên hiện có.

## 3.4. Chỉ số đánh giá: Penalized Accuracy (PA)

Chỉ số leaderboard là **Penalized Accuracy (PA)** trên tổng số câu hỏi `N` của test set:

\[
PA = \frac{1}{N}\sum_{i=1}^{N}s_i
\]

Trong đó:

\[
s_i =
\begin{cases}
+1 & \text{nếu câu trả lời đúng}0 & \text{nếu abstain}-1 & \text{nếu câu trả lời sai}
\end{cases}
\]

- Mọi câu hỏi có trọng số bằng nhau.
- Bất kỳ câu trả lời nào cho câu hỏi có đáp án tham chiếu `unanswerable` đều bị tính sai, trừ khi Agent cũng trả về `unanswerable`.
- Khi hai đội bằng điểm ở thứ hạng cuối cùng, thứ hạng được phân định bằng tổng thời gian inference trong lần chạy lại của ban tổ chức; nếu vẫn bằng nhau, đội nộp bài sớm hơn được xếp trước.

---

# 4. Rules — Quy định và các vòng thi

## 4.1. Các vòng thi

### Round 1 — Public Test Round (26/10–16/11/2026)

- Các đội xây dựng giải pháp, chạy trên public test set và nộp tệp kết quả JSONL qua mục Submission trên cổng Zalo AI Challenge.
- Mỗi đội được nộp tối đa 5 lần mỗi ngày.
- Hạn mức nộp được đặt lại vào cuối mỗi ngày.
- Điểm số và thứ hạng được hiển thị trên public leaderboard; điểm số này chỉ có tính tham khảo trong quá trình phát triển.

### Final Solution Submission — 16/11/2026

- Trước hạn cuối, các đội phải nộp giải pháp hoàn chỉnh dưới dạng Docker package qua biểu mẫu “Solution Submission” trên cổng Zalo AI Challenge.
- Gói giải pháp gồm training code, inference code và data.
- Do Docker file thường có dung lượng lớn, đội thi cần cung cấp checksum và đường dẫn Google Drive công khai để ban tổ chức tải xuống.
- Mỗi đội được nộp tối đa 2 lần; ban tổ chức chỉ đánh giá lần nộp cuối cùng.
- Hạn cuối: **23:59 (GMT+7), ngày 16/11/2026**.

### Round 2 — Private Test Round (20/11–23/11/2026)

- Ban tổ chức phát hành private test set lúc **09:00 ngày 20/11/2026**.
- Các đội chạy giải pháp đã nộp trên private test set và nộp tệp kết quả JSONL qua mục Submission.
- Hạn cuối nộp kết quả: **23:59 (GMT+7), ngày 23/11/2026**.
- Private leaderboard hiển thị theo thứ tự thời gian nộp bài.
- Ban tổ chức đánh giá các giải pháp đã nộp để xác minh kết quả, xem xét source code và phát hiện gian lận.
- Top 2 đội được công bố vào **02/12/2026**.

## 4.2. Đội thi và điều kiện tham gia

Đội thi và điều kiện tham gia tuân theo quy định chung của Zalo AI Challenge 2026.

## 4.3. Quy định về mô hình (Models)

- Được sử dụng các mô hình có weights được công khai trước ngày **01/10/2026**, với giấy phép cho phép hình thức sử dụng đó.
- Được phép fine-tune các mô hình.
- Tổng số tham số của tất cả mô hình được sử dụng khi inference không được vượt quá **15 tỷ tham số**.
- Giới hạn tổng tham số bao gồm language models, embedding models, rerankers, classifiers và các mô hình khác được dùng khi inference, bất kể chúng có được nạp đồng thời hay không.
- Với mô hình Mixture-of-Experts (MoE), tính toàn bộ tham số.
- Được phép quantization.
- Các mô hình được sử dụng phải được khai báo trong README của giải pháp.

## 4.4. Không sử dụng dịch vụ bên ngoài (No External Services)

Inference phải chạy hoàn toàn offline bên trong Docker image:

- Không gọi các commercial LLM API.
- Không tải xuống tài nguyên trong quá trình inference.
- Không truy cập mạng dưới bất kỳ hình thức nào.
- Docker image được chạy trong môi trường tắt network.

## 4.5. Không có con người can thiệp (No Human in the Loop)

- Hệ thống phải tự tạo câu trả lời mà không cần can thiệp thủ công.
- Không được hard-code đáp án.
- Không được xây dựng logic phụ thuộc vào question ID hoặc business ID.

## 4.6. Thực thi mã (Code Execution)

- Agent được phép sinh và thực thi mã bên trong container; việc này được kỳ vọng nhưng không bắt buộc.
- Thư mục dữ liệu được mount tại `/data` và ở chế độ chỉ đọc.
- Các tệp tạm phải được ghi ở vị trí khác, không ghi vào thư mục dữ liệu.

## 4.7. Quy định về dữ liệu (Data)

Được phép sử dụng:

- Training data do ban tổ chức cung cấp.
- Dữ liệu tự tổng hợp (synthetic data).
- Dataset và model công khai.

Không được phép:

- Sử dụng public test data hoặc private test data để training.
- Thu thập đáp án của các câu hỏi test bằng bất kỳ phương thức nào.

## 4.8. Môi trường tính toán tham chiếu (Compute Reference)

Giải pháp được kiểm tra trên máy có cấu hình:

| Thành phần        | Cấu hình                                       |
| ------------------- | ------------------------------------------------ |
| GPU                 | 2 × NVIDIA RTX 5090                             |
| VRAM                | 32 GB mỗi GPU; tổng cộng 64 GB                |
| RAM                 | 512 GB                                           |
| Thời gian tối đa | 6 giờ wall-clock cho toàn bộ private test set |

- Giới hạn 6 giờ bao gồm cả thời gian nạp model.
- Blackwell GPU yêu cầu CUDA từ phiên bản 12.8 trở lên và bản build PyTorch/vLLM tương thích.
- Docker guideline quy định base image cần sử dụng.

## 4.9. Điểm cuối cùng và khả năng tái lập (Final Score and Reproducibility)

- Điểm cuối cùng là điểm từ lần ban tổ chức chạy lại Docker image đã nộp trên private test set.
- Tệp `submission.jsonl` đội thi upload trong giai đoạn private test chỉ quyết định leaderboard tạm thời và đội nào được chạy lại.
- Giải pháp được xem là có tính tái lập nếu:

\[
\left|PA_{uploaded}-PA_{rerun}\right| \leq 0.03
\]

- Nếu độ chênh lệch vượt quá `0.03`, ban tổ chức sẽ kiểm tra logs do Docker image ghi ra; có thể chạy image thêm một lần và có thể yêu cầu đội thi cung cấp thêm thông tin.
- Nếu không giải thích được chênh lệch, đội thi có thể bị loại.
- Nếu lần chạy lại vượt thời gian quy định hoặc kết thúc sớm, chỉ các đáp án đã được ghi vào `/result/submission.jsonl` trước thời điểm dừng được chấm; các câu còn lại được tính là abstain.

---

## Tóm tắt các mốc và giới hạn chính

| Hạng mục                      | Quy định                                           |
| ------------------------------- | ---------------------------------------------------- |
| Public Test Round               | 26/10–16/11/2026                                    |
| Số lần nộp public            | Tối đa 5 lần/ngày                                |
| Hạn nộp Docker                | 23:59 (GMT+7), 16/11/2026                            |
| Số lần nộp Docker            | Tối đa 2 lần; chỉ bản cuối được đánh giá |
| Private Test phát hành        | 09:00, 20/11/2026                                    |
| Hạn nộp private result        | 23:59 (GMT+7), 23/11/2026                            |
| Công bố Top 2                 | 02/12/2026                                           |
| Tổng tham số inference        | Không quá 15 tỷ                                   |
| Chế độ inference             | Offline, không có network                          |
| Máy tham chiếu                | 2 × RTX 5090, 512 GB RAM                            |
| Thời gian xử lý private test | Tối đa 6 giờ, bao gồm nạp model                 |
| Điều kiện reproducibility    | Chênh lệch PA không quá 0.03                     |
