# AutoLink: Autonomous Schema Exploration and Expansion for Scalable Schema Linking in Text-to-SQL at Scale

| Thông tin | Chi tiết |
|---|---|
| **Tác giả** | Ziyang Wang, Yuanlei Zheng, Zhenbiao Cao, Xiaojin Zhang, Zhongyu Wei, Pei Fu, Zhenbo Luo, Wei Chen, Xiang Bai |
| **Đơn vị** | Huazhong University of Science and Technology (HUST), Fudan University, MiLM Plus (Xiaomi Inc.) |
| **Năm / Venue** | 2025 / arXiv:2511.17190 |
| **Loại bài** | Phương pháp (Method) |
| **Chủ đề** | Text-to-SQL, Schema Linking, Autonomous Agent, Large-Scale Database, Vector Store, Iterative Schema Exploration |
| **File gốc** | [AutoLink.pdf](../papers/AutoLink.pdf) |

## 1. Tóm tắt nhanh (TL;DR)
AutoLink tái định nghĩa bài toán schema linking trên các cơ sở dữ liệu doanh nghiệp quy mô lớn (hàng ngàn cột) như một tiến trình khám phá và mở rộng lặp tuần tự (iterative agent-driven exploration). Thay vì nạp toàn bộ schema vào ngữ cảnh LLM gây quá tải token và nhiễu loạn, một LLM agent chủ động tương tác với hai môi trường (Database Environment để thăm dò metadata/dữ liệu mẫu và Schema Vector Store Environment để tìm kiếm ngữ nghĩa mục tiêu), giúp đạt kỷ lục Strict Recall Rate 91.2% trên Spider 2.0-Lite và 97.4% trên BIRD-Dev với chi phí token cực thấp.

## 2. Bối cảnh & Vấn đề nghiên cứu
- **Bối cảnh**: Trong các hệ thống Text-to-SQL công nghiệp (industrial-scale), cơ sở dữ liệu quan hệ và data warehouse (như Google BigQuery, Snowflake) chứa hàng trăm bảng và hàng ngàn cột. Cung cấp toàn bộ schema ($S_{full}$) vào prompt LLM sẽ vượt giới hạn context window, tăng mạnh chi phí token và tạo ra nhiễu thông tin khổng lồ làm giảm chất lượng sinh SQL.
- **Vai trò của Schema Linking**: Xác định tập con schema tối thiểu cần thiết ($S_{linked} \subset S_{full}$). Chỉ số đo lường sống còn là **Strict Recall Rate (SRR)** — tỷ lệ các trường hợp mà schema con bao phủ toàn bộ 100% các bảng/cột cần thiết của ground-truth SQL. Nếu thiếu dù chỉ 1 cột, giới hạn trên (upper bound) của SQL sinh ra sẽ bị hỏng hoàn toàn.
- **Bế tắc của các phương pháp hiện hữu**:
  - *Element-level scoring* (RESDSQL, CodeS, CHESS): Chấm điểm từng cặp câu hỏi - cột, tốn chi phí $O(|S|)$ lượt suy luận khi $|S| > 1.000$.
  - *Full-schema / Backward reasoning* (MCS-SQL, SQL-to-Schema, RSL-SQL): Bắt buộc nạp toàn bộ schema vào prompt, vừa tràn context vừa nhanh chóng bão hòa SRR dù có tăng số lần lấy mẫu giải mã (decoding passes).
  - *Dual-encoder retrieval* (BGE, BM25): Để đạt SRR cao buộc phải lấy $K$ thật lớn (top-200), kéo theo quá nhiều cột rác (noise) làm phản tác dụng lọc schema.
  - *Noise-minimization rủi ro* (LinkAlign): Cố gắng ép schema thật nhỏ (chỉ 21 cột) dẫn đến SRR tụt dốc thảm hại (chỉ còn 36.4% trên Spider 2.0-Lite).

## 3. Phương pháp / Nội dung chính

AutoLink mô phỏng quy trình làm việc thực tế của kỹ sư dữ liệu: bắt đầu với hiểu biết sơ bộ, sau đó chạy các câu lệnh SQL thăm dò cấu trúc và tìm kiếm ngữ nghĩa theo nhu cầu để từng bước mở rộng schema.

```mermaid
flowchart LR
    subgraph Environments ["External Environments"]
        EDB["Database Env (EDB)<br/>Thực thi SQL thăm dò / Metadata / Timeout 120s / Top-5 rows"]
        EVS["Schema Vector Store (EVS)<br/>Faiss ANN + bge-large-en-v1.5 / M-Schema format"]
    end

    subgraph AgentLoop ["AutoLink Agent Loop (DeepSeek-V3)"]
        H0["Context: Instruction + Question<br/>+ Table Names List + S_initial (top-n)"] --> ThinkAction["Think: Phân tích thiếu sót<br/>Action: Chọn hành động"]
        ThinkAction --> ActFeedback{"Feedback Actions?"}
        ActFeedback -->|@explore_schema| EDB
        ActFeedback -->|@retrieve_schema| EVS
        ActFeedback -->|@verify_schema| EDB
        EDB --> Observe["Observation (RSQL / Metadata / Error)"]
        EVS --> Observe
        Observe --> ThinkAction
        ThinkAction -->|@add_schema| Expand["Schema Expansion: S_linked = S_linked ∪ S_added"]
        Expand --> ThinkAction
        ThinkAction -->|@stop_action / Max Turn| FinalSchema["Final Linked Schema (S_linked)"]
    end

    subgraph Downstream ["SQL Generation Pipeline"]
        FinalSchema --> GenSQL["Candidate Generation (Self-Consistency x5)<br/>(DeepSeek-R1)"]
        GenSQL --> SyntacticFix["Iterative Syntactic Correction<br/>(Execution feedback loop max 5 turns)"]
        SyntacticFix --> MajorityVote["Majority Voting by Execution Result<br/>+ Pairwise LLM Tie-Breaker"]
        MajorityVote --> OutSQL["Executable Final SQL"]
    end
```

### 3.1 Hai môi trường tương tác bên ngoài
1. **Database Environment ($E_{DB}$)**: Là kết nối cơ sở dữ liệu sống. Cho phép chạy các truy vấn SQL thăm dò metadata (`INFORMATION_SCHEMA`, SQLite `PRAGMA table_info`), kiểm tra mẫu dữ liệu (`LIKE '%keyword%'`, khoảng giá trị min/max). Giới hạn trả về tối đa 5 dòng, timeout 120s để tránh nghẽn.
2. **Schema Vector Store Environment ($E_{VS}$)**:
   - **Gộp bảng phân vùng (Partitioned Table Merging)**: Trên BigQuery thường có hàng trăm bảng dạng `table_YYYYMMDD` giống hệt cấu trúc cột. AutoLink gom nhóm các bảng cùng cấu trúc và chỉ nhúng 1 lần, giúp giảm từ hơn 100.000 cột ảo xuống chỉ còn 559 cột thực tế mỗi DB trên Spider 2.0-Lite.
   - Tài liệu cột gồm: Tên cột, danh sách bảng sở hữu, kiểu dữ liệu, mô tả cột, khóa chính/ngoại.
   - Mã hóa bằng `bge-large-en-v1.5`, lập chỉ mục Faiss ANN. Thời gian dựng vector store cực nhanh (trung bình 1.4s/DB trên Spider 2.0-Lite). Truy xuất trả về cấu trúc định dạng M-Schema.

### 3.2 Không gian hành động của Agent (Action Space)
Agent tương tác theo vòng lặp `<think>` và `<actions>` qua tối đa 10 lượt:
- **Hành động có phản hồi (Actions with Feedback)**:
  - `@explore_schema(sql_query)`: Thực thi SQL thăm dò metadata hoặc phân bố giá trị mẫu trong $E_{DB}$.
  - `@retrieve_schema(nl_query)`: Tìm kiếm ngữ nghĩa tập trung trong $E_{VS}$ với câu truy vấn khái niệm (ví dụ: suy luận tìm cột "điểm số học sinh" thay vì chỉ tìm từ "score"). Loại trừ các cột đã lấy ($C_{excl}$). Lấy $m=3$ cột.
  - `@verify_schema(sql_query)`: Chạy thử một câu SQL giải quyết bài toán giả định trên $S_{linked}$ hiện có. Lỗi thực thi (như `no such column: X`) trở thành tín hiệu chẩn đoán chính xác tuyệt đối để kích hoạt tìm kiếm cột thiếu.
- **Hành động không có phản hồi (Actions without Feedback)**:
  - `@add_schema(table.column; ...)`: Cam kết bổ sung các cột mới phát hiện vào $S_{linked}$. Bắt buộc phải đi kèm ít nhất một hành động có phản hồi hoặc `@stop_action`.
  - `@stop_action()`: Kết thúc thăm dò khi nhận thấy schema đã đầy đủ để sinh SQL hoàn chỉnh.

### 3.3 Pipeline sinh SQL hạ nguồn (SQL Generation)
- **Candidate Generation**: Lấy mẫu self-consistency 5 câu lệnh SQL bằng LLM reasoning (DeepSeek-R1).
- **Iterative Syntactic Correction**: Tự động sửa lỗi cú pháp dựa trên thông báo lỗi của database engine (tối đa 5 lượt).
- **Majority Voting by Execution Result**: Nhóm các câu SQL có kết quả thực thi trả về giống nhau. Chọn nhóm chiếm đa số; nếu hòa điểm, LLM so sánh từng cặp (pairwise tournament) để chọn câu tối ưu.

## 4. Thực nghiệm & Kết quả chính
- **Benchmark**: Spider 2.0-Lite (547 ca kiểm thử enterprise trên BigQuery, Snowflake, SQLite với trung bình hơn 800 cột/DB) và BIRD-Dev (1.543 ca kiểm thử trên 11 DB).
- **Mô hình cốt lõi**: DeepSeek-V3 làm Policy cho AutoLink schema linking; DeepSeek-R1 / Gemini-1.5-Pro cho SQL generation.

### 4.1 Kết quả Schema Linking (Strict Recall Rate & Token)

| Dataset | Phương pháp | Cần Full Schema? | Strict Recall Rate (SRR) | Số cột trung bình ($\bar{C}$) | Avg. Token Consumed |
|---|---|:---:|---|:---:|:---:|
| **BIRD-Dev** | MCS-SQL | ✓ | 85.7% | 7.5 | 29.8K |
| | SQL-to-Schema | ✓ | 92.5% | 13.5 | 19.4K |
| | CHESS | ✓ | 89.7% | 4.5 | – |
| | RSL-SQL | ✓ | 93.3% | 13.0 | 14.8K |
| | **AutoLink (Ours)** | ✗ | **97.4%** | 35.8 | **8.0K** |
| **Spider 2.0-Lite** | DE-SL (BGE-Large) | ✓ | 43.6% | 153.8 | – |
| | CE-SL (BGE-reranker) | ✓ | 57.6% | 153.8 | – |
| | MCS-SQL ($N=5$) | ✓ | 58.9% | 45.1 | 168.9K |
| | SQL-to-Schema ($N=5$) | ✓ | 64.0% | 49.0 | 171.9K |
| | RSL-SQL | ✓ | 52.0% | 25.8 | 29.2K |
| | LinkAlign | ✗ | 36.4% | 21.1 | 66.7K |
| | **AutoLink (Ours)** | ✗ | **91.2%** | 159.4 | **21.2K** |

*Chi tiết Spider 2.0-Lite theo phương ngữ: BigQuery đạt 93.7%, Snowflake đạt 85.7%, SQLite đạt 95.8%.*

### 4.2 Kết quả Execution Accuracy (EX) trên Spider 2.0-Lite

| Phương pháp | Backbone Model | Execution Accuracy (EX) | Avg. Tokens |
|---|---|:---:|:---:|
| Spider-Agent | Claude-3.7-Sonnet | 28.52% | – |
| Spider-Agent | DeepSeek-R1 | 13.71% | – |
| CHESS | GPT-4o | 3.84% | – |
| LinkAlign | DeepSeek-R1 | 33.09% | – |
| RSL-SQL | DeepSeek-R1 | 30.53% | 50.0K |
| ReFoRCE | DeepSeek-R1 | 29.62% | 81.1K |
| ReFoRCE | GPT-o3 | 37.84% | 81.1K |
| **AutoLink (Ours)** | **DeepSeek-R1** | **34.92%** | **38.0K** |

*(Xếp thứ 2 trên bảng xếp hạng chính thức Spider 2.0-Lite tại thời điểm nộp bài; đạt SOTA trong số tất cả các mô hình dùng DeepSeek-R1, tiêu tốn chưa tới một nửa số token so với ReFoRCE).* Trên BIRD-Dev, AutoLink đạt **68.71% EX** (Gemini-1.5-Pro) và 66.36% (DeepSeek-V3) chỉ với 8.0K tokens.

### 4.3 Khả năng mở rộng quy mô (Scalability) & Ablation
- **Quy mô DB > 3.000 cột**: Khi cơ sở dữ liệu vượt quá 3.000 cột, SRR của tất cả các baseline (BGE-Large, BGE-reranker, MCS-SQL, SQL-to-Schema, LinkAlign) rơi xuống dưới **40%**, trong khi AutoLink vẫn duy trì xấp xỉ **90%**.
- **Ablation hành động**:
  - Bỏ `@retrieve_schema`: SRR giảm mạnh nhất (-6.7% đến -7.6%), khẳng định vai trò sống còn của tìm kiếm ngữ nghĩa theo khái niệm suy luận.
  - Bỏ `@explore_schema`: SRR giảm 2.4% - 3.2%, chứng minh giá trị của việc thăm dò metadata giải quyết mơ hồ.
  - Bỏ `@verify_schema`: SRR giảm 1.2% - 2.0%, cho thấy phản hồi lỗi thực thi là tín hiệu tinh chỉnh quan trọng.
- **Ablation pipeline SQL**: Cú pháp cơ bản (23.47% EX) $\rightarrow$ thêm Iterative Correction (+7.87% lên 31.34%) $\rightarrow$ thêm Majority Voting (+3.63% lên 34.97%).

## 5. Tính mới (Novelty & Đóng góp)
- **Mô hình hóa Schema Linking dạng tương tác Agentic tuần tự**: Lần đầu tiên chuyển dịch schema linking từ bài toán lọc tĩnh (static retrieval/ranking) sang tiến trình khám phá chủ động đa vòng giữa LLM Agent và môi trường, hoàn toàn không cần nhìn thấy full database schema.
- **Kiến trúc môi trường kép ($E_{DB} + E_{VS}$)**: Kết hợp hài hòa giữa khả năng thăm dò chính xác cấu trúc/dữ liệu thực qua SQL engine và năng lực tìm kiếm ngữ nghĩa mờ qua vector store.
- **Cơ chế suy luận khái niệm thiếu (`@retrieve_schema`) và kiểm chứng giả thuyết (`@verify_schema`)**: Khác với query rewrite thông thường, agent tự sinh từ khóa trừu tượng để tìm cột bị thiếu và dùng lỗi thực thi SQL làm động lực sửa đổi.
- **Chiến lược gộp bảng phân vùng (Partitioned Table Merging)**: Đóng góp kỹ thuật thực tế vô cùng giá trị cho Text-to-SQL trên data warehouse lớn, giảm tải hàng chục ngàn cột trùng lặp.

## 6. Hạn chế
### 6.1 Hạn chế do tác giả thừa nhận
- **Số lượng cột recalled ($\bar{C}$) còn tương đối lớn**: Trên Spider 2.0-Lite, AutoLink giữ lại trung bình 159.4 cột (để đảm bảo SRR cao), cao hơn so với LinkAlign (21.1 cột) hay MCS-SQL (45.1 cột). Mặc dù lọc bỏ được 80% nhiễu so với full schema (>800 cột), con số 159 cột vẫn có thể đưa vào một số cột nhiễu nhỏ.
- **Phụ thuộc vào khả năng instruction following của LLM Agent**: Việc dùng DeepSeek-R1 làm agent policy gặp hiện tượng suy giảm tuân thủ định dạng thẻ `<think>` và `<actions>`, buộc phải dùng DeepSeek-V3 làm policy khám phá và R1 cho phần sinh SQL sau cùng.

### 6.2 Nhận xét thêm của người review
- **Độ trễ thời gian do nhiều vòng tương tác**: Trung bình agent chạy từ 3.7 đến 5.8 lượt tương tác; mỗi lượt gồm gọi LLM, chạy SQL hoặc Faiss. Dù token tiêu thụ ít, latency end-to-end cho một câu hỏi có thể cao hơn single-pass prompt.
- **Rủi ro phụ thuộc vào tính mở của cơ sở dữ liệu**: Môi trường $E_{DB}$ đòi hỏi quyền truy cập chạy thử câu lệnh trên database sống. Với môi trường production có quyền hạn bị thắt chặt (read-only, bảo mật PII, chặn `INFORMATION_SCHEMA`), việc tự do explore và verify có thể bị giới hạn.
- **Chi phí xây dựng và đồng bộ Vector Store**: Dù thời gian dựng vector store ban đầu ngắn (1.4s/DB), nếu schema database thường xuyên biến động (thêm cột, sửa bảng), hệ thống cần cơ chế trigger cập nhật index liên tục.

## 7. Ý nghĩa ứng dụng (cho hệ thống agent phân tích dữ liệu / Text-to-SQL)
- **Áp dụng mô hình Schema Linking chủ động cho Enterprise Data Agent**: Không cố nhồi toàn bộ database catalog vào context của LLM; thay vào đó chỉ cấp cho Agent danh sách tên bảng và công cụ tìm kiếm metadata theo nhu cầu.
- **Tận dụng lỗi thực thi làm động lực Schema Linking**: Triển khai action `@verify_schema` cho agent chạy thử câu lệnh giả định; bắt lỗi cú pháp/cột không tồn tại (`column not found`) để tự động kích hoạt truy vấn vector store tìm đúng tên cột tương đương.
- **Kỹ thuật Partitioned Table Merging**: Khi làm việc với BigQuery/Snowflake/ClickHouse chứa các bảng chia theo ngày (`orders_20240101`, `orders_20240102`), bắt buộc gom nhóm schema trước khi đưa vào RAG/Agent để tránh bùng nổ token.

## 8. Từ khóa
`AutoLink`, `Text-to-SQL`, `Schema Linking`, `Strict Recall Rate`, `Autonomous Agent`, `Spider 2.0-Lite`, `BIRD`, `Faiss Vector Store`, `DeepSeek-R1`, `Database Exploration`
