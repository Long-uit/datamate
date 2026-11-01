# DataMate: Talking To Your Data Through Agentic AI
> **Zalo AI Challenge 2026 — Track DataMate**  
> Xây dựng hệ thống Agentic AI hỏi đáp ngôn ngữ tự nhiên tiếng Việt trên dữ liệu bảng phức tạp của doanh nghiệp nhỏ.

---

## 📌 1. Tổng quan Cuộc thi (Overview)

Bảng tính và các cơ sở dữ liệu đơn giản là những hệ sinh thái lưu trữ thông tin cực kỳ phổ biến đối với hàng triệu chủ tiệm tạp hóa, quán cà phê, nhà thuốc, phòng khám và cơ sở kinh doanh nhỏ tại Việt Nam. Dù sở hữu dữ liệu bán hàng và vận hành hàng ngày, rất ít người có kỹ năng lập trình hoặc viết câu lệnh truy vấn (SQL/code) để khai thác nguồn dữ liệu đó.

**DataMate** đặt ra thách thức xây dựng một **AI Agent tự hành (Agentic AI)** có khả năng:
- **Tiếp nhận dữ liệu bảng thực tế & đa dạng:** Đọc và liên kết các bảng tính Excel nhiều sheet, tệp CSV và SQLite.
- **Thấu hiểu ngôn ngữ tự nhiên:** Xử lý câu hỏi đời thường bằng tiếng Việt, từ ngữ khẩu ngữ, viết tắt, lịch âm/dương và mùa vụ Tết.
- **Suy luận logic nghiệp vụ chính xác:** Tự động tính toán doanh thu, chiết khấu, giá vốn lô hàng, tuổi nợ theo quy định của Rulebook.
- **Biết khi nào dữ liệu không thể trả lời:** Nhận diện các câu hỏi thiếu thông tin (`unanswerable`) và chủ động từ chối (`abstain`) khi độ tự tin thấp để bảo toàn điểm số.

> **Tôn chỉ sống còn:** *"Silence is Free, Guessing is Fatal"* — Đúng ghi điểm (+1), sai bị phạt nặng (-1), im lặng là an toàn (0).

---

## 🗓️ 2. Dòng thời gian Cuộc thi (Timeline)

```mermaid
flowchart LR
    T1["26/10<br/>Start Challenge"] --> T2["16/11<br/>Submit Solutions"]
    T2 --> T3["20/11<br/>Release Private Test"]
    T3 --> T4["23/11<br/>Submit Final Result"]
    T4 --> T5["02/12<br/>Announce Top 2"]
```

| Mốc thời gian | Sự kiện | Chi tiết |
|---|---|---|
| **26/10/2026** | **Start the challenge** | Phát hành bộ Development kit, dữ liệu (`competition_data/train` & `public_test`) và phần mềm đánh giá. Mở nộp bài Public Test (tối đa 5 lần/ngày). |
| **16/11/2026** *(23:59 GMT+7)* | **Submit solutions** | Hạn chót nộp toàn bộ giải pháp Docker hoàn chỉnh (gồm training code, testing/inference code, model weights, Dockerfile và tài liệu). Tối đa 2 lần nộp; BTC đánh giá lần nộp cuối. |
| **20/11/2026** *(09:00 GMT+7)* | **Release private test** | Ban tổ chức phát hành tập dữ liệu Private Test set. Leaderboard ở giai đoạn này là tạm thời dựa trên kết quả tự nộp của các đội. |
| **23/11/2026** *(23:59 GMT+7)* | **Submit the final result** | Hạn chót nộp file kết quả `submission.jsonl` chạy trên tập Private Test set. Hạn chót: 23:59 (GMT+7). |
| **02/12/2026** | **Announce Top 2** | Ban tổ chức công bố Top 2 đội thắng cuộc sau khi chạy lại độc lập kiểm tra tính tái lập (Reproducibility) và xác minh source code. |

---

## 📊 3. Dữ liệu & Cấu trúc Gói Dữ liệu (Dataset Structure)

### 3.1. Đặc điểm Dữ liệu Doanh nghiệp
- **Loại hình kinh doanh:** Tiệm tạp hóa, quán cà phê/trà sữa, nhà hàng, nhà thuốc, vật liệu xây dựng, sửa xe máy, mẹ và bé...
- **Quy mô:** 12–30 tháng hoạt động, từ vài trăm đến ~300.000 dòng dữ liệu cho mỗi doanh nghiệp.
- **Tính chất dữ liệu thực tế:** Dữ liệu xuất từ phần mềm POS (KiotViet, Sapo...) có ô gộp/ô trống theo nhóm dòng (Group Forward-Fill), đơn vị tính quy đổi đa tầng (thùng, lốc, lon, cái), dòng xuất lỗi trùng lặp.

### 3.2. Cấu trúc thư mục dữ liệu chuẩn
```text
<split>/
├── data/<business_id>/
│   ├── *.csv | *.xlsx | *.sqlite     # Các file bảng dữ liệu của doanh nghiệp
│   └── README.md                     # Mô tả doanh nghiệp & từ điển cột
├── rulebook.md                       # Quy tắc nghiệp vụ mặc định của split
├── calendar.csv                      # Lịch đối chiếu Dương lịch - Âm lịch
├── questions.jsonl                   # Danh sách câu hỏi cần trả lời
└── answers.jsonl                     # Đáp án tham chiếu (chỉ có ở tập Train)
```

---

## 🎯 4. Thước đo Đánh giá: Penalized Accuracy (PA)

Điểm số xếp hạng trên Leaderboard được tính bằng **Penalized Accuracy (PA)** trên $N$ câu hỏi:

$$PA = \frac{1}{N} \sum_{i=1}^N s_i$$

Trong đó:
- **Đúng (Correct):** $s_i = +1$ (Khớp chính xác định dạng và nội dung đáp án).
- **Bỏ qua (Abstain):** $s_i = 0$ (Agent chủ động không trả lời khi thiếu tự tin).
- **Sai (Wrong):** $s_i = -1$ (Đoán sai giá trị, hoặc đoán số trên câu hỏi `unanswerable`).

> [!CAUTION]
> Khoảng cách giữa **Đúng (+1)** và **Sai (-1)** là 2 điểm. Việc đoán mò với xác suất tin cậy $< 50\%$ sẽ kéo tụt điểm nhanh chóng. Hệ thống cần ưu tiên từ chối (`abstain`) an toàn khi gặp rủi ro cao.

### Các loại định dạng đáp án hỗ trợ:
| Kiểu dữ liệu | Mô tả & Quy tắc so khớp |
|---|---|
| `number` | Số nguyên cho tiền tệ VND/số lượng đếm; hoặc làm tròn 2 chữ số thập phân. |
| `percent` | Số thực làm tròn 2 chữ số thập phân (ví dụ `12.5`, không có dấu `%`). |
| `string` | Chuỗi văn bản sau khi qua chuẩn hóa: Unicode NFC, chữ thường, bỏ ký tự đặc biệt, giữ nguyên dấu tiếng Việt. |
| `date` | Định dạng ISO `YYYY-MM-DD` (hoặc `YYYY-MM` đối với tháng). |
| `boolean` | Giá trị boolean thuần túy: `true` hoặc `false`. |
| `list` | Mảng JSON có thứ tự: `["item1", "item2", ...]`. |
| `table` | Bảng dữ liệu có tên cột và các dòng: `{"columns": [...], "rows": [...]}`. |
| `unanswerable` | Dữ liệu không đủ cơ sở để trả lời (ví dụ: kỳ hỏi ngoài phạm vi dữ liệu). Chỉ đúng khi đáp án cũng là unanswerable. |
| `abstain` | Agent chủ động không trả lời để nhận 0 điểm an toàn. |

---

## ⚙️ 5. Ràng buộc Kỹ thuật & Môi trường Thi đấu (Rules & Environment)

| Tiêu chí | Ràng buộc từ Ban tổ chức |
|---|---|
| **Giới hạn Mô hình** | Tổng tham số của toàn bộ mô hình (LLM, Embeddings, Reranker, Classifiers) $\le$ **15 tỷ tham số (15B)**. |
| **Trọng số cho phép** | Trọng số được công khai trước ngày **01/10/2026**. Được phép fine-tune. |
| **Chế độ thực thi** | **100% Offline** bên trong Docker container. Không kết nối mạng, cấm gọi external LLM API thương mại. |
| **Không can thiệp thủ công** | Cấm hard-code đáp án, không viết logic phụ thuộc vào `question_id` hoặc `business_id`. |
| **Máy chủ tham chiếu** | 2 × NVIDIA RTX 5090 (64 GB VRAM tổng), 512 GB RAM. |
| **Thời gian tối đa** | $\le$ **6 giờ** wall-clock cho toàn bộ Private Test set (bao gồm cả thời gian nạp mô hình). |
| **Tính tái lập (Reproducibility)** | Chênh lệch điểm giữa kết quả nộp và lần chạy lại của BTC: $\lvert PA_{\text{uploaded}} - PA_{\text{rerun}} \rvert \le 0.03$. |
| **Cơ chế ghi log** | Ghi file log chi tiết cho từng câu hỏi vào `/result/logs/<question_id>.json`. |

---

## 🏗️ 6. Định hướng Kiến trúc Giải pháp (Neuro-Symbolic Agent)

Hệ thống DataMate áp dụng kiến trúc **Tác tử Đa tầng Neuro-Symbolic** gồm 6 module độc lập:

```mermaid
flowchart LR
    M1["1. Unified Ingestion<br/>& Rule 8 Cleaner"] --> M2["2. Semantic Grounding<br/>& Rulebook Compiler"]
    M2 --> M3{"3. Deterministic<br/>Feasibility Gate"}
    M3 -- "Không khả thi" --> ANS_UNANS["unanswerable (+1)"]
    M3 -- "Khả thi" --> M4["4. Code Synthesizer<br/>(Qwen2.5-Coder-14B)"]
    M4 --> M5["5. Dual-Engine Sandbox<br/>(Python + SQLite)"]
    M5 --> M6{"6. Format Normalizer &<br/>Calibrated Abstention Gate"}
    M6 -- "Tin cậy thấp" --> ANS_ABS["abstain (0 điểm an toàn)"]
    M6 -- "Tin cậy cao" --> ANS_SUB["submission.jsonl"]
```

1. **Module 1 (Data Ingestion & Cleaning):** Tự động forward-fill ô trống theo nhóm dòng và khử trùng lặp (Rule 8), ánh xạ toàn bộ bảng Excel/CSV vào CSDL SQLite in-memory siêu tốc.
2. **Module 2 (Semantic Grounding):** Giải mã thời gian tương đối ("hôm nay", "tuần này", "Tết") đối chiếu với `as_of_date` và `calendar.csv`. Khớp tên sản phẩm/khách hàng bằng thuật toán BM25 và Fuzzy Matching tiếng Việt.
3. **Module 3 (Deterministic Feasibility Gate):** Lá chắn phát hiện câu hỏi ngoài khoảng thời gian dữ liệu shop để trả về `unanswerable` ngay lập tức, tránh bị phạt âm điểm.
4. **Module 4 (Neuro-Symbolic Synthesizer):** Sử dụng mô hình `Qwen2.5-Coder-14B-Instruct` qua vLLM với Greedy Decoding ($T=0$) để sinh mã Python/SQL chuẩn xác.
5. **Module 5 (Execution Sandbox):** Thực thi mã trong môi trường cô lập, hỗ trợ cơ chế phản tư tự sửa lỗi (Self-Correction Loop tối đa 2 vòng).
6. **Module 6 (Format Normalizer & Calibrated Gate):** Chuẩn hóa định dạng chuẩn 8 kiểu dữ liệu, giải quyết đồng hạng theo mã code tăng dần, và kích hoạt cơ chế `abstain` an toàn khi độ tin cậy thấp.

---

## 📁 7. Cấu trúc Dự án (Repository Structure)

```text
.
├── docs/                                      # Tài liệu đặc tả và thiết kế
│   ├── DataMate_Zalo_AI_Challenge_2026.md     # Đặc tả chi tiết từ BTC
│   ├── DataMate_Solution_Architecture.md      # Thiết kế kiến trúc giải pháp 6 module
│   └── Timeline_and_Contribution.md           # Kế hoạch triển khai & phân bổ 2 thành viên
├── competition_data/                          # Dữ liệu cuộc thi
│   ├── train/                                 # Dữ liệu huấn luyện mẫu (3.000 câu)
│   └── public_test/                           # Dữ liệu thử nghiệm công khai
├── src/                                       # Mã nguồn chính của Agent
├── predict.sh                                 # Script entrypoint cho Docker container
├── README.md                                  # Hướng dẫn và thông tin tổng quan
└── Dockerfile                                 # Thiết lập môi trường container
```

---

*Tài liệu được tổng hợp và thiết kế cho đội thi phát triển giải pháp DataMate tại Zalo AI Challenge 2026.*
