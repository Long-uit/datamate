# Research DataMate: Text-to-SQL, spreadsheet QA và độ tin cậy

## Mục đích và phạm vi

Thư mục này ghép mỗi PDF gốc với một review tiếng Việt. Bộ tài liệu được chia theo **mức ưu tiên cho challenge**, không phải theo chất lượng học thuật: “Cốt lõi” là nên đọc trước để định hướng kiểm thử/thiết kế; “Tham khảo” hữu ích cho một câu hỏi hẹp hoặc để tra cứu, nhưng không cần đọc hết trước khi triển khai.

Phân loại dựa trên [đặc tả challenge](../docs/DataMate_Zalo_AI_Challenge_2026.md): dữ liệu CSV/XLSX/SQLite và rulebook theo split; đầu ra có kiểu dữ liệu; chấm Penalized Accuracy (đúng +1, abstain 0, sai -1); suy luận offline, không có người trong vòng lặp, tổng tham số không quá 15B. Điểm Text-to-SQL, execution accuracy và PA không thể hoán đổi.

## Cấu trúc

```text
research/
  core/
    papers/       # PDF cần đọc ưu tiên
    reviews/      # Review tương ứng, cùng basename với PDF
  reference/
    papers/       # PDF tham khảo
    reviews/      # Review tương ứng
  README.md
```

Hiện có **38 cặp PDF–review: 9 cốt lõi và 29 tham khảo**. Không xóa nhóm tham khảo; có thể đọc theo nhu cầu.

## Cốt lõi — ưu tiên đọc trước

| Bài báo / review                                                                                                                                                                    | PDF gốc                                                                                                           | Vì sao nằm trong nhóm này                                                                                                                         |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| [A Pilot Study of Text-to-SQL Semantic Parsing for Vietnamese](<core/reviews/A%20Pilot%20Study%20of%20Text-to-SQL%20Semantic%20Parsing%20for%20Vietnamese.md>)                         | [PDF](<core/papers/A%20Pilot%20Study%20of%20Text-to-SQL%20Semantic%20Parsing%20for%20Vietnamese.pdf>)               | Nguồn nền về tiếng Việt, word segmentation và schema linking; benchmark dịch từ Spider nên không đại diện đủ cho câu hỏi cửa hàng. |
| [AbstentionBench](core/reviews/AbstentionBench.md)                                                                                                                                     | [PDF](core/papers/AbstentionBench.pdf)                                                                              | Taxonomy và đánh giá câu không thể trả lời; metric phải được hiệu chỉnh lại theo PA.                                                  |
| [Benchmarking Text-to-SQL Reliability with Penalty-Based Scoring](<core/reviews/Benchmarking%20Text-to-SQL%20Reliability%20with%20Penalty-Based%20Scoring.md>)                         | [PDF](<core/papers/Benchmarking%20Text-to-SQL%20Reliability%20with%20Penalty-Based%20Scoring.pdf>)                  | Cách phân tích chi phí trả lời sai; TrustSQL không dùng chính metric PA của challenge.                                                      |
| [Can LLM Already Serve as A Database Interface](<core/reviews/Can%20LLM%20Already%20Serve%20as%20A%20Database%20Interface.md>)                                                         | [PDF](<core/papers/Can%20LLM%20Already%20Serve%20as%20A%20Database%20Interface.pdf>)                                | BIRD: giá trị bẩn, domain evidence và execution-based evaluation trên dữ liệu quan hệ.                                                        |
| [Encoding Spreadsheets for Large Language Models](<core/reviews/Encoding%20Spreadsheets%20for%20Large%20Language%20Models.md>)                                                         | [PDF](<core/papers/Encoding%20Spreadsheets%20for%20Large%20Language%20Models.pdf>)                                  | Biểu diễn/nén workbook; không tự giải quyết logic nghiệp vụ hoặc tính toán.                                                               |
| [Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows](<core/reviews/Evaluating%20Language%20Models%20on%20Real-World%20Enterprise%20Text-to-SQL%20Workflows.md>) | [PDF](<core/papers/Evaluating%20Language%20Models%20on%20Real-World%20Enterprise%20Text-to-SQL%20Workflows%20.pdf>) | Spider 2.0: generalization và workflow doanh nghiệp; môi trường lớn hơn challenge.                                                             |
| [MiMoTable](core/reviews/MiMoTable.md)                                                                                                                                                 | [PDF](core/papers/MiMoTable.pdf)                                                                                    | Benchmark workbook nhiều sheet/header, hữu ích khi thiết kế ca kiểm thử Excel.                                                                 |
| [Same SQL, Different Decision](<core/reviews/Same%20SQL%2C%20Different%20Decision.md>)                                                                                                 | [PDF](<core/papers/Same%20SQL%2C%20Different%20Decision.pdf>)                                                       | Kiểm tra verifier đa ngôn ngữ; có kết quả tiếng Việt và cảnh báo độ fidelity của literal.                                              |
| [SheetBrain](core/reviews/SheetBrain.md)                                                                                                                                               | [PDF](core/papers/SheetBrain.pdf)                                                                                   | Kiến trúc hiểu–thực thi–kiểm tra trên spreadsheet; cần xét sandbox và giới hạn inference.                                                |

## Tham khảo — đọc theo nhu cầu

### Tổng quan và taxonomy

| Bài báo / review                                                                                                                                                                       | PDF gốc                                                                                                             | Vì sao nằm trong nhóm này                                                      |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| [A Survey of Text-to-SQL in the Era of LLMs](<reference/reviews/A%20Survey%20of%20Text-to-SQL%20in%20the%20Era%20of%20LLMs.md>)                                                           | [PDF](<reference/papers/A%20Survey%20of%20Text-to-SQL%20in%20the%20Era%20of%20LLMs.pdf>)                              | Survey vòng đời Text-to-SQL; chọn một survey làm tài liệu tra cứu chính. |
| [A Survey on Employing Large Language Models for](<reference/reviews/A%20Survey%20on%20Employing%20Large%20Language%20Models%20for.md>)                                                   | [PDF](<reference/papers/A%20Survey%20on%20Employing%20Large%20Language%20Models%20for.pdf>)                           | Survey prompt/fine-tuning; nội dung trùng một phần với các survey khác.     |
| [Large Language Model for Table Processing](<reference/reviews/Large%20Language%20Model%20for%20Table%20Processing.md>)                                                                   | [PDF](<reference/papers/Large%20Language%20Model%20for%20Table%20Processing.pdf>)                                     | Survey xử lý bảng tổng quát; nguồn tra cứu hơn là bằng chứng benchmark. |
| [Natural Language Interfaces for Tabular Data Querying and Visualization](<reference/reviews/Natural%20Language%20Interfaces%20for%20Tabular%20Data%20Querying%20and%20Visualization.md>) | [PDF](<reference/papers/Natural%20Language%20Interfaces%20for%20Tabular%20Data%20Querying%20and%20Visualization.pdf>) | Survey có nhánh visualization không nằm trong output challenge.                |
| [Next-Generation Database Interfaces A Survey of LLM-based Text-to-SQL](<reference/reviews/Next-Generation%20Database%20Interfaces%20A%20Survey%20of%20LLM-based%20Text-to-SQL.md>)       | [PDF](<reference/papers/Next-Generation%20Database%20Interfaces%20A%20Survey%20of%20LLM-based%20Text-to-SQL.pdf>)     | Survey dự phòng, chồng lấn với survey Text-to-SQL khác.                      |
| [Table Question Answering in the Era of LLMs](<reference/reviews/Table%20Question%20Answering%20in%20the%20Era%20of%20LLMs.md>)                                                           | [PDF](<reference/papers/Table%20Question%20Answering%20in%20the%20Era%20of%20LLMs.pdf>)                               | Survey table QA; tra cứu taxonomy thay vì dùng điểm tổng hợp làm dự báo. |

### Benchmark và câu hỏi mơ hồ

| Bài báo / review                                                                                                                                                       | PDF gốc                                                                                                   | Vì sao nằm trong nhóm này                                                                           |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| [A Practical Text-to-SQL Benchmark for Electronic Health Records](<reference/reviews/A%20Practical%20Text-to-SQL%20Benchmark%20for%20Electronic%20Health%20Records.md>)   | [PDF](<reference/papers/A%20Practical%20Text-to-SQL%20Benchmark%20for%20Electronic%20Health%20Records.pdf>) | Unanswerable và truy vấn thời gian trong dữ liệu y tế; domain khác DataMate.                     |
| [AmbiSQL](reference/reviews/AmbiSQL.md)                                                                                                                                   | [PDF](reference/papers/AmbiSQL.pdf)                                                                         | Phân loại mơ hồ; luồng hỏi lại người dùng không dùng được trong lượt chấm tự động. |
| [Benchmarking and Improving Text-to-SQL Generation under Ambiguity](<reference/reviews/Benchmarking%20and%20Improving%20Text-to-SQL%20Generation%20under%20Ambiguity.md>) | [PDF](<reference/papers/Benchmarking%20and%20Improving%20Text-to-SQL%20Generation%20under%20Ambiguity.pdf>) | Benchmark các diễn giải SQL thay thế; khác định nghĩa đáp án/abstain của challenge.         |
| [Probing Ambiguity](<reference/reviews/Probing%20Ambiguity.md>)                                                                                                           | [PDF](<reference/papers/Probing%20Ambiguity.pdf>)                                                           | Adversarial ambiguity probing; cần đo latency và không chờ xác nhận người dùng.               |
| [Query Carefully](<reference/reviews/Query%20Carefully.md>)                                                                                                               | [PDF](<reference/papers/Query%20Carefully.pdf>)                                                             | Unanswerable trong Text-to-SQL y tế; metric và domain riêng.                                         |

### Kiến trúc, schema linking và table reasoning

| Bài báo / review                                                                                                                             | PDF gốc                                                                                     | Vì sao nằm trong nhóm này                                                                |
| ---------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| [A Multi-Agent Collaborative Framework for Text-to-SQL](<reference/reviews/A%20Multi-Agent%20Collaborative%20Framework%20for%20Text-to-SQL.md>) | [PDF](<reference/papers/A%20Multi-Agent%20Collaborative%20Framework%20for%20Text-to-SQL.pdf>) | Mẫu kiến trúc multi-agent; đối chiếu chi phí, API và PA trước khi chuyển giao.    |
| [AutoLink](reference/reviews/AutoLink.md)                                                                                                       | [PDF](reference/papers/AutoLink.pdf)                                                          | Schema exploration nhiều vòng cho database lớn; có thể tốn compute/latency.            |
| [Chain-of-Table](reference/reviews/Chain-of-Table.md)                                                                                           | [PDF](reference/papers/Chain-of-Table.pdf)                                                    | Reasoning qua chuỗi phép biến đổi bảng; benchmark WikiTQ/Table QA.                     |
| [Contextual Harnessing for Efficient SQL Synthesis](<reference/reviews/Contextual%20Harnessing%20for%20Efficient%20SQL%20Synthesis.md>)         | [PDF](<reference/papers/Contextual%20Harnessing%20for%20Efficient%20SQL%20Synthesis.pdf>)     | Retrieval schema và execution tests; framework đa thành phần.                            |
| [Disambiguate First, Parse Later](<reference/reviews/Disambiguate%20First%2C%20Parse%20Later.md>)                                               | [PDF](<reference/papers/Disambiguate%20First%2C%20Parse%20Later.pdf>)                         | Sinh diễn giải để phân tích mơ hồ; không yêu cầu user xác nhận.                 |
| [LinkAlign](reference/reviews/LinkAlign.md)                                                                                                     | [PDF](reference/papers/LinkAlign.pdf)                                                         | Schema linking đa database; dùng nếu lỗi schema đã được xác định là bottleneck. |
| [MAGIC](reference/reviews/MAGIC.md)                                                                                                             | [PDF](reference/papers/MAGIC.pdf)                                                             | Tự tổng hợp guideline tự sửa SQL; đánh giá chi phí và môi trường cục bộ.      |
| [ReAcTable](reference/reviews/ReAcTable.md)                                                                                                     | [PDF](reference/papers/ReAcTable.pdf)                                                         | ReAct cho Table QA; benchmark/executor khác package dữ liệu challenge.                    |
| [SchemaGraphSQL](reference/reviews/SchemaGraphSQL.md)                                                                                           | [PDF](reference/papers/SchemaGraphSQL.pdf)                                                    | Foreign-key graph linking; chỉ hữu ích khi nguồn có quan hệ khóa ngoại.              |

### Model và huấn luyện

| Bài báo / review                                                                                                                                             | PDF gốc                                                                                              | Vì sao nằm trong nhóm này                                                              |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| [DIN-SQL](reference/reviews/DIN-SQL.md)                                                                                                                         | [PDF](reference/papers/DIN-SQL.pdf)                                                                    | Baseline decomposition và self-correction; kết quả chính phụ thuộc GPT-4 API.        |
| [ExCoT](reference/reviews/ExCoT.md)                                                                                                                             | [PDF](reference/papers/ExCoT.pdf)                                                                      | DPO/execution feedback; phương pháp huấn luyện cần compute và kiểm tra model size. |
| [LatentRefusal](reference/reviews/LatentRefusal.md)                                                                                                             | [PDF](reference/papers/LatentRefusal.pdf)                                                              | Probe trạng thái ẩn phụ thuộc model/checkpoint và calibration.                       |
| [Simple Rewards, Strong Reasoning in Text-to-SQL](<reference/reviews/Simple%20Rewards%2C%20Strong%20Reasoning%20in%20Text-to-SQL.md>)                           | [PDF](<reference/papers/Simple%20Rewards%2C%20Strong%20Reasoning%20in%20Text-to-SQL.pdf>)              | RL fine-tuning SQL; ưu tiên nếu chọn huấn luyện model.                               |
| [Synthesizing High-quality Text-to-SQL Data at Scale](<reference/reviews/Synthesizing%20High-quality%20Text-to-SQL%20Data%20at%20Scale.md>)                     | [PDF](<reference/papers/Synthesizing%20High-quality%20Text-to-SQL%20Data%20at%20Scale.pdf>)            | Tạo dữ liệu Text-to-SQL tổng hợp; kiểm tra domain shift và cỡ model.               |
| [Towards Building Open-source Language Models for Text-to-SQL](<reference/reviews/Towards%20Building%20Open-source%20Language%20Models%20for%20Text-to-SQL.md>) | [PDF](<reference/papers/Towards%20Building%20Open-source%20Language%20Models%20for%20Text-to-SQL.pdf>) | CodeS có model mở 1B–15B; SQL-specialized, không đại diện Excel/rulebook.           |

### Spreadsheet và tài chính

| Bài báo / review                                                                                             | PDF gốc                                                                    | Vì sao nằm trong nhóm này                                                                  |
| -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| [FinSheet-Bench](reference/reviews/FinSheet-Bench.md)                                                           | [PDF](reference/papers/FinSheet-Bench.pdf)                                   | Audit spreadsheet đầu tư tài chính; tác vụ không tương đồng hỏi đáp cửa hàng. |
| [Large Language Models for Spreadsheets](<reference/reviews/Large%20Language%20Models%20for%20Spreadsheets.md>) | [PDF](<reference/papers/Large%20Language%20Models%20for%20Spreadsheets.pdf>) | FLARE: công thức và thao tác spreadsheet, không trùng output task.                       |
| [WorkstreamBench](reference/reviews/WorkstreamBench.md)                                                         | [PDF](reference/papers/WorkstreamBench.pdf)                                  | Agent dựng workbook tài chính end-to-end; khác trả lời từ workbook có sẵn.            |

## Quy ước chất lượng review

Mỗi review dùng chung 10 phần: tóm tắt; vấn đề; phương pháp; kết quả; đóng góp; hạn chế; ứng dụng; từ khóa; mức phù hợp challenge; và nguồn/truy nguyên kết quả.

- Mục 1–6 mô tả bài báo. Mục 7 và 9 là suy luận ứng dụng cho DataMate, trừ khi review nói rõ bài báo đã đánh giá cùng thiết lập.
- Số liệu phải đi cùng benchmark, split, metric và phiên bản model; tuyên bố SOTA chỉ gắn với thiết lập/thời điểm của bài báo.
- Với số liệu quan trọng, đối chiếu trang/bảng/hình ở mục 10 và PDF gốc. Các survey không phải thí nghiệm mới; lần theo bài sơ cấp trước khi dùng số liệu.
- Các bài mới cần kiểm tra riêng vấn đề dữ liệu dịch, domain shift, giấy phép, khả năng tái lập và tính tương thích với giới hạn offline/15B.

## Các bài học kiến trúc có thể mang sang DataMate

> **Nguồn và loại nhận định:** Đây là khuyến nghị tổng hợp của người review từ [đặc tả challenge](../docs/DataMate_Zalo_AI_Challenge_2026.md) và các bài trong nhóm cốt lõi, gồm [AbstentionBench](core/reviews/AbstentionBench.md), [SheetBrain](core/reviews/SheetBrain.md) và [nghiên cứu verifier đa ngôn ngữ](<core/reviews/Same%20SQL,%20Different%20Decision.md>). Đây không phải kết luận chung của các tác giả, cũng chưa phải kết quả đánh giá thực nghiệm của DataMate.

1. **Tuân thủ rulebook của từng split:** đọc README doanh nghiệp và rulebook áp dụng cho split trước khi tính; không suy rộng quy tắc từ train sang public/private.
2. **Tách hiểu câu hỏi khỏi phép tính:** dùng parser/LLM để xác định intent và nguồn dữ liệu; thực hiện phép tính xác định bằng Python hoặc SQLite tùy định dạng nguồn để giảm lỗi số học và định dạng.
3. **Hiệu chỉnh answerability theo PA:** câu trả lời đúng được +1, sai -1, abstain 0. Abstain không bị trừ điểm, nhưng bỏ lỡ +1 nếu câu hỏi có thể trả lời đúng. Đánh giá coverage cùng lỗi trên validation thay vì chọn ngưỡng chỉ từ Text-to-SQL benchmark.
4. **Rà cấu trúc workbook trước khi truy vấn:** kiểm tra nhiều sheet, tiêu đề nhiều hàng, ô gộp, vùng dữ liệu rời rạc và đơn vị; chỉ nén hoặc cắt ngữ cảnh sau khi đã bảo toàn cấu trúc cần cho câu hỏi.
5. **Kiểm thử trên doanh nghiệp chưa thấy và toàn bộ output contract:** dùng câu hỏi tiếng Việt; kiểm tra từng kiểu đầu ra, kiểu dữ liệu và quy tắc chuẩn hóa; chạy Docker offline với tổng tham số không quá 15B và thời gian private test tối đa 6 giờ, gồm nạp mô hình. Theo dõi log và kiểm tra chênh lệch PA khi chạy lại không quá 0,03.

Không dùng human-in-the-loop trong inference vì quy định challenge không cho phép người can thiệp.
