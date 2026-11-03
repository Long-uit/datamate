# MAGIC: Generating Self-Correction Guideline for In-Context Text-to-SQL

| Thông tin | Chi tiết |
|---|---|
| **Tác giả** | Arian Askari, Christian Poelitz, Xinye Tang |
| **Đơn vị** | Leiden University, Microsoft Research Cambridge (UK), Microsoft Redmond |
| **Năm / Venue** | AAAI 2025 / arXiv:2406.12692 |
| **Loại bài** | Phương pháp (Method) |
| **Chủ đề** | Text-to-SQL, Self-Correction, In-Context Learning, Automated Guideline Generation, Multi-Agent Collaboration, Error Analysis |
| **File gốc** | [MAGIC.pdf](../papers/MAGIC.pdf) |

## 1. Tóm tắt nhanh (TL;DR)
MAGIC là phương pháp đa tác tử (multi-agent) đầu tiên tự động hóa hoàn toàn quy trình sinh bộ hướng dẫn tự sửa sai (self-correction guideline) cho các hệ thống Text-to-SQL in-context learning. Bằng cách để ba tác tử chuyên biệt (Manager, Feedback, Correction) phối hợp phân tích các ca dự đoán sai trên tập huấn luyện, MAGIC tự động đúc kết bộ cẩm nang phản tư dạng "hỏi-tự-đáp" (ask-to-myself) chỉ trong chưa đầy 2 giờ, đạt kết quả cao hơn trong các cấu hình được so sánh các hướng dẫn do chuyên gia con người biên soạn thủ công và nâng cao độ chính xác thực thi trên cả BIRD và SPIDER.

## 2. Bối cảnh & Vấn đề nghiên cứu
- **Bối cảnh**: Mặc dù các mô hình ngôn ngữ lớn (LLM) đã cải thiện vượt bậc năng lực Text-to-SQL, khoảng cách độ chính xác so với con người vẫn lên tới ~30% trên các benchmark phức tạp như BIRD. Kỹ thuật tự sửa sai (self-correction) dựa trên giả định rằng "nhận biết lỗi sai dễ hơn là tránh phạm lỗi ngay từ đầu".
- **Hạn chế của các tiếp cận hiện nay**:
  - Các hệ thống SOTA (như DIN-SQL, MAC-SQL, CHESS) đều dựa vào **bộ hướng dẫn tự sửa sai do chuyên gia con người tự tay viết (human-crafted guidelines)**.
  - Quy trình thủ công này cực kỳ tốn công sức, đòi hỏi kỹ sư phải rà soát hàng ngàn lỗi trên tập train và khó bao quát hết mọi quy luật lỗi tiềm ẩn của LLM.
  - Hiện tượng phản tác dụng khi áp dụng tự sửa sai trên toàn bộ câu hỏi (All SQLs): Khi ép LLM sửa cả những câu ban đầu đã đúng, các hướng dẫn của con người thường khiến mô hình hoang tưởng và biến câu đúng thành câu sai (làm tụt mạnh độ chính xác, ví dụ guideline của MAC-SQL làm tụt EX từ 56.52% xuống 46.14%).

## 3. Phương pháp / Nội dung chính

MAGIC xây dựng một quy trình khép kín gồm 3 tác tử làm việc trên tập huấn luyện (nơi có ground-truth SQL $s_{gt}$) để chẩn đoán các câu SQL dự đoán sai ($s'$), từ đó chưng cất thành guideline dùng trong giai đoạn suy luận (inference).

```mermaid
flowchart LR
    subgraph OfflineGuideGen ["Giai đoạn 1: Sinh Guideline tự động bằng Multi-Agent (Offline Train Set)"]
        FailInput["Input ca lỗi:<br/>Question + Pred SQL (s') + Ground-truth (s_gt)"] --> Manager["Manager Agent<br/>(Lập kế hoạch, điều phối vòng lặp,<br/>sửa prompt động, tổng hợp cẩm nang)"]
        Manager -->|Gửi s' và s_gt| Feedback["Feedback Agent<br/>(Chỉ ra nguyên nhân lỗi sai logic/cú pháp)"]
        Feedback -->|Feedback giải thích lỗi| Manager
        Manager -->|Gửi Question, Schema, s', Feedback<br/>(KHÔNG cấp s_gt)| Correction["Correction Agent<br/>(Sinh SQL sửa đổi)"]
        Correction -->|Revised SQL| Manager
        Manager -->|Chạy SQL thử nghiệm| Executor["Tool: SQL Executor"]
        Executor -->|Khớp s_gt: Thành công<br/>Chưa khớp: Manager tinh chỉnh prompt| Manager
        Manager -->|Gom 10 feedback thành công| Memory["Guideline Batch Aggregation<br/>(Tạo Ask-to-Myself Questions)"]
        Memory --> FinalGuide["MAGIC Self-Correction Guideline"]
    end

    subgraph Inference ["Giai đoạn 2: Suy luận & Tự sửa sai (Inference Test Set)"]
        FinalGuide --> PromptInference["Prompting LLM (DIN-SQL / GPT-4)<br/>Tự vấn theo checklist 'Ask-to-myself'<br/>trước khi xuất Revised SQL"]
        PromptInference --> FinalCorrectSQL["Corrected Executable SQL"]
    end
```

### 3.1 Cấu trúc 3 tác tử trong MAGIC
1. **Manager Agent (Tác tử quản trị)**:
   - Điều phối vòng lặp phản hồi - sửa lỗi (Feedback-correction cycle) tối đa 5 lượt lặp.
   - Sử dụng công cụ `SQL Executor` chạy câu SQL sửa đổi để đối chiếu kết quả thực thi với $s_{gt}$.
   - **Tự động điều chỉnh prompt cho tác tử (Revising agents' instruction)**: Nếu Correction Agent sửa chưa đúng, Manager phân tích phản hồi cũ và viết lại prompt chỉ dẫn mới phù hợp hơn cho Feedback và Correction Agent.
   - Lưu trữ các ca sửa thành công vào bộ nhớ và gom nhóm theo lô (batch size $k=10$) để biên soạn guideline.
2. **Feedback Agent (Tác tử phản hồi)**: Nhận câu hỏi, SQL sai $s'$ và SQL chuẩn $s_{gt}$; so sánh ngữ nghĩa và giải thích bản chất lỗi (nhầm lẫn ngày tháng, thiếu hàm tổng hợp lồng, sai điều kiện lọc).
3. **Correction Agent (Tác tử sửa lỗi)**: Nhận schema, câu hỏi, câu SQL sai $s'$ và bản phản hồi phân tích lỗi từ Feedback Agent. **Tác tử này tuyệt đối không được nhìn thấy $s_{gt}$**, đảm bảo tính khách quan rằng SQL sửa được là nhờ chất lượng của phản hồi hướng dẫn.

### 3.2 Cấu trúc bộ hướng dẫn (Ask-to-Myself Guideline)
Cứ sau 10 ca sửa lỗi thành công, Manager Agent tích hợp và khái quát hóa thành các mục hướng dẫn mang tính quy nạp:
1. **Tên dạng lỗi (Reminder of Mistake)**: Ví dụ: *Limit Clause Omission*, *Aggregation within Aggregation*, *Misuse of DISTINCT*.
2. **Ví dụ cụ thể**: Câu hỏi thực tế, câu SQL sai ban đầu và câu SQL đã sửa đúng.
3. **Bộ câu hỏi tự vấn nghiêm ngặt (Step-by-step ask-to-myself questions)**: Buộc LLM khi đọc lại SQL của chính mình phải tự trả lời các câu hỏi phản tư (ví dụ: *"Mình có kiểm tra xem câu hỏi có yêu cầu giới hạn số lượng kết quả không?"*, *"Mình có lồng hàm SUM bên trong MAX mà quên dùng subquery không?"*).

## 4. Thực nghiệm & Kết quả chính

> **Cách đọc số liệu:** Các kết quả thuộc benchmark, split, metric và phiên bản mô hình của bài báo. “SOTA” chỉ áp dụng trong bối cảnh/thời điểm bài báo nêu; không so trực tiếp với PA của challenge.
- **Môi trường & Benchmark**: BIRD Dev (1.534 ca kiểm thử phức tạp) và SPIDER Dev.
- **Hệ thống gốc**: DIN-SQL tái lập hoàn toàn trên GPT-4 (gpt-4-32k/0613). Tác giả tái lập toàn bộ baseline trên cùng một phiên bản model để đảm bảo công bằng.

### 4.1 Kết quả Execution Accuracy (EX %) trên BIRD Dev

| Nhóm phương pháp | Chi tiết phương pháp | Kịch bản 1: Sửa SQL sai (Oracle) | Kịch bản 2: Sửa SQL lỗi thực thi (Exec Error) | Kịch bản 3: Sửa toàn bộ SQL (All SQLs) |
|---|---|:---:|:---:|:---:|
| Không tự sửa | DIN-SQL (W/o self-correction) | 56.52% | 56.52% | 56.52% |
| Không dùng Guideline | Self-Debugging | 57.24% | 56.78% | 56.58% |
| | Self-Consistency ($N=20$) | 58.08% | 56.58% | 57.17% |
| | Multiple-Prompt | 57.86% | 56.65% | 57.30% |
| Dùng Guideline con người | Human Expert G (MAC-SQL) | 56.60% | 56.58% | 46.14% *(Tụt dốc)* |
| | Human Expert G (DIN-SQL) | 57.76% | 56.98% | 55.80% |
| **Dùng Guideline tự động** | **MAGIC G (Ours)** | **59.13%** | **57.32%** | **58.55%** |

*(Kết quả đạt độ tin cậy thống kê $p < 0.05$ qua paired t-test với hiệu chỉnh Bonferroni).*

### 4.2 Kết quả trên SPIDER Dev và Khả năng áp dụng chéo (Cross-method)
- **Trên SPIDER Dev**: Sửa SQL sai giúp nâng từ 78.62% lên **85.66% EX**, vượt xa Self-Consistency (81.64%), Multiple-Prompt (80.22%) và Human Guideline của DIN-SQL (80.35%).
- **Áp dụng guideline MAGIC lên các kiến trúc Text-to-SQL khác**:
  - *Zero-shot GPT-4*: Tăng từ 40.18% lên **48.19%** (+8.01%).
  - *Few-shot CoT GPT-4*: Tăng từ 45.66% lên **50.38%** (+4.72%).
  - *DIN-SQL*: Tăng từ 56.52% lên **59.13%** (+2.61%).
  - *MAC-SQL*: Tăng từ 59.39% lên **61.92%** (+2.53%).

### 4.3 Phân tích Ablation và Vai trò của Manager Agent
- **Vai trò quan trọng của Manager Agent**: Khi loại bỏ Manager (trở về chu trình Critic-Refine đơn thuần):
  - Số vòng lặp trung bình để sửa được một câu tăng lên (từ 2.41 lên 2.87 lượt).
  - Tỷ lệ sửa thành công giảm (từ 81.81% xuống 78.60% EX trên train set BIRD).
  - Điểm hiệu quả thực thi hợp lệ (Valid Efficiency Score - VES) giảm từ 84.19 xuống 79.58 do Manager biết tự bổ sung chỉ dẫn tối ưu cú pháp gọn gàng hơn.
- **Tốc độ hội tụ của Guideline**: Sau khi tích lũy 10 lô feedback (tương đương 100 ca sửa lỗi trên tập train), chất lượng guideline đã đạt ngưỡng bão hòa và vượt qua hướng dẫn của chuyên gia con người.

## 5. Tính mới (Novelty & Đóng góp)
- **Thiết lập bài toán mới**: Định nghĩa bài toán tự động sinh hướng dẫn tự sửa sai (Self-correction Guideline Generation) độc lập, giải phóng sức lao động thủ công của kỹ sư AI.
- **Kiến trúc Multi-Agent phối hợp có kiểm soát thông tin**: Tách biệt rõ ràng quyền truy cập thông tin giữa các agent (Correction Agent bị che $s_{gt}$, Manager có quyền sửa prompt động cho các tác tử con), đảm bảo feedback sinh ra có giá trị tổng quát cao.
- **Định dạng hướng dẫn tự vấn (Ask-to-Myself)**: Phát hiện cấu trúc prompt tự vấn step-by-step giúp kích hoạt khả năng nội suy (introspection) của LLM trong khâu self-correction, mang lại tính diễn giải (interpretability) cao.
- **Khắc phục hiện tượng sửa lợn lành thành lợn què**: MAGIC guideline là phương pháp hiếm hoi vẫn gia tăng hiệu năng (+2.03%) khi áp dụng mù quáng trên toàn bộ câu lệnh (All SQLs), trong khi các guideline người viết làm giảm sút nghiêm trọng.

## 6. Hạn chế
### 6.1 Hạn chế do tác giả thừa nhận
- **Phụ thuộc vào tập huấn luyện có nhãn**: Cần tập train có câu hỏi và SQL chuẩn tương ứng để chạy offline thu thập các ca thất bại ban đầu.
- **Độ dài ngữ cảnh tăng thêm trong inference**: Bộ guideline hoàn chỉnh gồm 17 mục chi tiết kèm câu hỏi phản tư chiếm thêm một phần context window đáng kể khi đưa vào prompt của giai đoạn suy luận.
- **Biến thiên hiệu quả giữa các database**: Một số database có mức độ hưởng lợi rất cao, trong khi các database quá đặc thù ít hưởng lợi hơn, gợi ý cần các guideline chuyên biệt theo từng miền dữ liệu.

### 6.2 Nhận xét thêm của người review
- **Chi phí gọi API trong pha sinh Guideline**: Dù chỉ chạy một lần offline trong ~2 giờ, việc chạy 3 agent lặp lại tối đa 5 lượt trên hàng trăm ca lỗi của tập train tiêu tốn lượng token GPT-4 không nhỏ.
- **Chưa kiểm thử trên các Open-Source Reasoning LLMs mới**: Nghiên cứu tập trung chủ yếu vào GPT-4 (phiên bản 2023-2024). Với sự xuất hiện của các mô hình suy luận mạnh mẽ như DeepSeek-R1, OpenAI o1/o3-mini có sẵn khả năng tự phản tư nội tại (internal CoT), cần đánh giá xem guideline dạng văn bản ngoài còn mang lại biên lợi ích lớn hay không.
- **Phụ thuộc vào độ bao phủ của lỗi ban đầu**: Nếu hệ thống Text-to-SQL cơ sở gặp những dạng lỗi hoàn toàn mới ở môi trường production mà chưa từng xuất hiện trên tập train, guideline có thể không có mục tương ứng để nhắc nhở.

## 7. Ý nghĩa ứng dụng (cho hệ thống agent phân tích dữ liệu / Text-to-SQL)

> **Phân biệt nguồn:** Khuyến nghị trong mục này là suy luận ứng dụng cho DataMate; bài báo không đánh giá trực tiếp trên challenge, trừ khi nêu rõ.
- **Cơ chế Offline Rule/Guideline Extraction tự động**: Thay vì tốn nhân lực ngồi viết luật hậu kiểm (post-processing rules) hay prompt sửa lỗi thủ công, hệ thống Text-to-SQL doanh nghiệp có thể định kỳ cho multi-agent chạy trên log truy vấn sai để tự cập nhật cẩm nang tự sửa sai.
- **Đưa checklist "Ask-to-Myself" vào System Prompt của Agent**: Thay vì chỉ yêu cầu LLM "hãy kiểm tra lại câu lệnh", việc bắt buộc mô hình trả lời lần lượt một danh sách câu hỏi cụ thể ("Đã GROUP BY đúng khóa chính chưa?", "Có bị lồng hàm tổng hợp không?", "Có lọc ngày tháng đúng định dạng không?") giúp tăng mạnh tỷ lệ sửa lỗi thành công.
- **Cảnh giác khi triển khai Self-Correction đại trà**: Không nên áp dụng module tự sửa sai cho 100% truy vấn nếu không có guideline được kiểm chứng cẩn thận hoặc không có tín hiệu lỗi thực thi (compiler error/execution exception), nhằm tránh làm hỏng các truy vấn ban đầu vốn đã đúng.

## 8. Từ khóa
`MAGIC`, `Text-to-SQL`, `Self-Correction`, `In-Context Learning`, `Multi-Agent Framework`, `Guideline Generation`, `Ask-to-Myself`, `BIRD`, `DIN-SQL`, `GPT-4`

## 9. Mức độ phù hợp với challenge DataMate

**Phân nhóm: Tham khảo.** Tự xây guideline sửa lỗi có thể hỗ trợ SQL; cần đối chiếu chi phí và khả năng chạy cục bộ.

## 10. Nguồn và truy nguyên kết quả

- **PDF gốc:** liên kết ở bảng thông tin đầu review và bản lưu trong thư mục `../papers/`.
- **Vị trí kiểm chứng:** Method and guideline generation: PDF pp. 2–5; results/tables: pp. 5–7; discussion p. 7.
- Số liệu ở mục 4 là kết quả tác giả trên benchmark gốc; phần áp dụng DataMate tại mục 7 và mục 9 là nhận định của review.
