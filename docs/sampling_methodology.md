# Phương Pháp Lấy Mẫu Tập Kiểm Chứng (Sampling Methodology for Validation Set)

## 1. Bối cảnh & Mục tiêu

Trong hệ thống đánh giá của DataMate phục vụ cuộc thi, việc đánh giá hiệu năng mô hình một cách khách quan, chống hiện tượng nhìn trước dữ liệu (data leakage) và overfit vào tập chẩn đoán là điều kiện tiên quyết.

- **Tập Batch 50 (`reports/sample_50_ids.json`)**: Là tập 50 câu hỏi ngẫu nhiên được trích xuất ban đầu từ `competition_data/train/questions.jsonl` (seed=42) để phục vụ khảo sát chẩn đoán lỗi chuyên sâu (`reports/diagnosis/batch50_diagnosis.md`). Điểm PA ban đầu trên tập này là $-0.4400$ (3 Đúng, 25 Sai, 22 Từ chối).
- **Yêu cầu tập kiểm chứng (Validation Set ~100 câu)**: Cần một tập kiểm chứng độc lập hoàn toàn gồm đúng 100 câu hỏi, chưa từng được phân tích hay nhìn thấy trong quá trình chẩn đoán Batch 50, dùng làm thước đo quyết định (ground-truth decision metric) cho mọi cải tiến mã nguồn.

---

## 2. Phân tích Cấu trúc & Mâu thuẫn Thực tế

Yêu cầu ban đầu (R2.1) đề cập: *"Chọn ~100 câu từ tập train gồm các shop KHÔNG xuất hiện trong batch 50 (tách độc lập theo business_id)"*.

Tuy nhiên, qua khảo sát cấu trúc thực tế của dữ liệu:

1. Tập dữ liệu huấn luyện `competition_data/train` gồm đúng **30 cửa hàng** (`biz_101` đến `biz_130`) với tổng cộng 3,000 câu hỏi.
2. Tập Batch 50 (`reports/sample_50_ids.json`) được tạo ra với tiêu chí phân bổ đều trên toàn bộ các cửa hàng: **20 shop có 2 câu** và **10 shop có 1 câu**. Do đó, toàn bộ 30 cửa hàng đều đã xuất hiện trong Batch 50.
3. Vì vậy, tập hợp các shop trong tập train *không xuất hiện trong Batch 50* là **tập rỗng** ($\emptyset$).

### Giải pháp Phương pháp luận: Question Holdout Stratified Sampling

Để đảm bảo tính khách quan và thỏa mãn trọn vẹn tinh thần của yêu cầu:

- Ta lấy tập ứng viên gồm **2,950 câu hỏi còn lại** trong tập train nằm ngoài Batch 50.
- Thực hiện lấy mẫu phân tầng ngẫu nhiên (Stratified Sampling) có kiểm soát đảm bảo tính rời rạc tuyệt đối:
  $$
  Q_{\text{val}} \cap Q_{\text{batch50}} = \emptyset
  $$
- Không một câu hỏi nào trong tập kiểm chứng 100 câu từng xuất hiện trong Batch 50.
- Mẫu kiểm chứng phủ trọn vẹn toàn bộ 30 cửa hàng và 5 nhóm ngành kinh doanh, đồng thời phân tầng chuẩn xác theo đúng tỷ lệ 8 dạng đáp án của toàn bộ tập train.

---

## 3. Tiêu chí & Quy trình Lấy Mẫu Phân Tầng

### 3.1. Phân bổ theo 8 Kiểu Đáp án Chuẩn (Answer Types)

Tập 100 câu được phân bổ theo đúng tỷ lệ xuất hiện của 3,000 câu trong `competition_data/train/answers.jsonl`:

| Kiểu đáp án (Gold Type) | Số câu trong Train (3,000 câu) | Tỷ lệ Train (%) | Số câu trong Val 100 | Tỷ lệ Val (%) | Ghi chú nghiệp vụ                                                   |
| :-------------------------- | :-------------------------------: | :---------------: | :--------------------: | :--------------: | :--------------------------------------------------------------------- |
| **number**            |               1,884               |      62.80%      |      **63**      |      63.0%      | Gồm 23 Doanh thu, 8 Đếm (count), 32 Tổng gộp/Tính toán          |
| **percent**           |                578                |      19.27%      |      **19**      |      19.0%      | Tỷ lệ tăng trưởng, tỷ lệ hủy đơn, tỷ trọng doanh thu       |
| **list**              |                193                |       6.43%       |      **6**      |       6.0%       | Danh sách mặt hàng, danh sách khách hàng, danh sách đơn       |
| **date**              |                145                |       4.83%       |      **5**      |       5.0%       | Ngày bán chạy nhất, ngày phát sinh giao dịch                    |
| **string**            |                88                |       2.93%       |      **3**      |       3.0%       | Tên mặt hàng bán chạy, tên khách hàng chi tiêu nhiều nhất   |
| **unanswerable**      |                70                |       2.33%       |      **2**      |       2.0%       | Câu hỏi ngoài dữ liệu / thiếu bảng, kiểm thử Feasibility Gate |
| **boolean**           |                23                |       0.77%       |      **1**      |       1.0%       | Kiểm tra điều kiện đúng/sai (True/False)                         |
| **table**             |                19                |       0.63%       |      **1**      |       1.0%       | Bảng kết quả tổng hợp nhiều cột / nhiều dòng                  |
| **Tổng cộng**       |          **3,000**          | **100.0%** |     **100**     | **100.0%** | **Khớp chính xác tỷ lệ phân bố tổng thể**               |

### 3.2. Phân tầng chi tiết nhóm `number` (63 câu)

- **Doanh thu (Revenue - 23 câu)**: Các câu hỏi về doanh thu định kỳ (ngày, tuần, tháng, quý, năm, từ đầu năm đến nay, Tết).
- **Đếm số lượng/đơn (Count - 8 câu)**: Các câu hỏi "mấy đơn", "bao nhiêu đơn hủy", "bao nhiêu mặt hàng", "đếm số lần".
- **Tổng gộp / Tính toán khác (Aggregation - 32 câu)**: Tổng giá trị nhập hàng, tổng tiền nợ, giá trị trung bình, tổng số lượng hàng bán.

---

## 4. Bảng Phân Bố Tập Kiểm Chứng 100 Câu (Val 100)

### 4.1. Phân bố theo Nhóm Ngành Kinh Doanh (Business Sectors)

| Nhóm ngành kinh doanh                            | Danh sách cửa hàng                                                  | Số lượng câu hỏi |    Tỷ trọng    |
| :------------------------------------------------- | :--------------------------------------------------------------------- | :-------------------: | :--------------: |
| **F&B / Đồ uống / Tiệm bánh**           | biz_104, biz_105, biz_106, biz_125, biz_126, biz_128, biz_130          |          29          |      29.0%      |
| **Bách hóa / Tạp hóa / Siêu thị mini** | biz_101, biz_102, biz_103, biz_107, biz_108, biz_109, biz_110, biz_112 |          22          |      22.0%      |
| **Nhà thuốc / Dược phẩm**               | biz_119, biz_120, biz_121, biz_122, biz_123, biz_124                   |          22          |      22.0%      |
| **Dịch vụ / Bán lẻ khác**               | biz_111, biz_118, biz_127, biz_129                                     |          14          |      14.0%      |
| **Vật liệu xây dựng & Điện nước**    | biz_113, biz_114, biz_115, biz_116, biz_117                            |          13          |      13.0%      |
| **Tổng cộng**                              | **30 cửa hàng**                                                |     **100**     | **100.0%** |

### 4.2. Phân bố chi tiết theo từng Cửa Hàng (Shops)

Tất cả 30 cửa hàng (`biz_101` đến `biz_130`) đều có ít nhất 2 câu hỏi trong tập kiểm chứng:

|       STT       | Cửa hàng        | Nhóm ngành                          | Số câu Val |  Tỷ trọng (%)  |
| :-------------: | :---------------- | :------------------------------------ | :-----------: | :--------------: |
|        1        | `biz_101`       | Bách hóa / Tạp hóa                |       2       |       2.0%       |
|        2        | `biz_102`       | Bách hóa / Tạp hóa                |       2       |       2.0%       |
|        3        | `biz_103`       | Bách hóa / Tạp hóa                |       6       |       6.0%       |
|        4        | `biz_104`       | F&B / Đồ uống / Tiệm bánh        |       3       |       3.0%       |
|        5        | `biz_105`       | F&B / Đồ uống / Tiệm bánh        |       4       |       4.0%       |
|        6        | `biz_106`       | F&B / Đồ uống / Tiệm bánh        |       2       |       2.0%       |
|        7        | `biz_107`       | Bách hóa / Tạp hóa                |       2       |       2.0%       |
|        8        | `biz_108`       | Bách hóa / Tạp hóa                |       2       |       2.0%       |
|        9        | `biz_109`       | Bách hóa / Tạp hóa                |       3       |       3.0%       |
|       10       | `biz_110`       | Bách hóa / Tạp hóa                |       2       |       2.0%       |
|       11       | `biz_111`       | Dịch vụ / Bán lẻ khác            |       3       |       3.0%       |
|       12       | `biz_112`       | Bách hóa / Tạp hóa                |       3       |       3.0%       |
|       13       | `biz_113`       | Vật liệu xây dựng & Điện nước |       2       |       2.0%       |
|       14       | `biz_114`       | Vật liệu xây dựng & Điện nước |       2       |       2.0%       |
|       15       | `biz_115`       | Vật liệu xây dựng & Điện nước |       3       |       3.0%       |
|       16       | `biz_116`       | Vật liệu xây dựng & Điện nước |       4       |       4.0%       |
|       17       | `biz_117`       | Vật liệu xây dựng & Điện nước |       2       |       2.0%       |
|       18       | `biz_118`       | Dịch vụ / Bán lẻ khác            |       3       |       3.0%       |
|       19       | `biz_119`       | Nhà thuốc / Dược phẩm            |       4       |       4.0%       |
|       20       | `biz_120`       | Nhà thuốc / Dược phẩm            |       7       |       7.0%       |
|       21       | `biz_121`       | Nhà thuốc / Dược phẩm            |       3       |       3.0%       |
|       22       | `biz_122`       | Nhà thuốc / Dược phẩm            |       3       |       3.0%       |
|       23       | `biz_123`       | Nhà thuốc / Dược phẩm            |       2       |       2.0%       |
|       24       | `biz_124`       | Nhà thuốc / Dược phẩm            |       3       |       3.0%       |
|       25       | `biz_125`       | F&B / Đồ uống / Tiệm bánh        |       2       |       2.0%       |
|       26       | `biz_126`       | F&B / Đồ uống / Tiệm bánh        |       2       |       2.0%       |
|       27       | `biz_127`       | Dịch vụ / Bán lẻ khác            |       3       |       3.0%       |
|       28       | `biz_128`       | F&B / Đồ uống / Tiệm bánh        |       8       |       8.0%       |
|       29       | `biz_129`       | Dịch vụ / Bán lẻ khác            |       5       |       5.0%       |
|       30       | `biz_130`       | F&B / Đồ uống / Tiệm bánh        |       8       |       8.0%       |
| **Tổng** | **30 shop** | **5 nhóm ngành**              | **100** | **100.0%** |

---

## 5. Dữ liệu Xuất & Tích Hợp

Các tệp dữ liệu đã được xuất và lưu trữ đúng theo quy chuẩn:

1. `competition_data/val_100_questions.jsonl`: Danh sách đúng 100 câu hỏi kiểm chứng kèm `as_of_date` và `business_id`.
2. `competition_data/val_100_answers.jsonl`: Danh sách đúng 100 đáp án chuẩn tương ứng (`id`, `type`, `answer`, `alias`).
3. `reports/batch_50_questions.jsonl`: 50 câu hỏi của Batch 50 đã chuẩn hóa.
4. `reports/batch_50_answers.jsonl`: 50 đáp án của Batch 50 tương ứng.

Script tái lập: `scripts/create_val_dataset.py`.
Toàn bộ quá trình đảm bảo tính tái lập (deterministic) và tính toàn vẹn 100%.
