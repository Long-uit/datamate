# Đề xuất giải pháp DataMate: mô hình, từ vựng và hệ thống

> **Trạng thái tài liệu:** Đây là đề xuất thiết kế cho DataMate, chưa phải kết quả benchmark thực nghiệm. Nhận định về cấu hình mô hình dưới đây cần được xác nhận bằng PA trên benchmark đã sửa đúng rulebook. Kết luận của nhà phát triển mô hình được dẫn nguồn riêng; không xem điểm trên benchmark khác là điểm dự đoán của DataMate.

## 1. Tóm tắt quyết định

DataMate nên dùng **một mô hình chính để hiểu câu hỏi và tạo kế hoạch truy vấn có cấu trúc**, còn việc làm sạch, nối bảng, tính số, áp quy tắc nghiệp vụ và định dạng đáp án nên nằm trong các thành phần tất định có thể kiểm tra.

Đề xuất thực hiện theo thứ tự:

1. Giữ Qwen2.5-Coder-3B hiện tại làm baseline phát triển.
2. Đưa Qwen2.5-Coder-7B-Instruct và Qwen2.5-Coder-14B-Instruct vào vòng đánh giá. 14B là ứng viên chính vì phù hợp công việc sinh logic; 7B là phương án dự phòng có nhiều dư địa hơn về tốc độ và giới hạn tổng tham số.
3. Chỉ chọn mô hình theo **PA trên các split không rò rỉ**, độ bao phủ, số câu sai, thời gian chạy và tính tái lập. Chưa có số liệu này thì chưa thể kết luận mô hình nào thắng.
4. Không để LLM sinh và chạy Python tùy ý trong đường chạy chính. LLM sinh QueryPlan JSON đã định kiểu; bộ kiểm tra xác thực kế hoạch và compiler chuyển kế hoạch thành truy vấn SQL/phép tính được cho phép.
5. Xây từ điển tiếng Việt hai tầng: thuật ngữ nghiệp vụ dùng chung và bí danh/thực thể riêng từng doanh nghiệp. Luôn giữ nguyên dấu tiếng Việt và tên chuẩn để xuất kết quả.
6. Sửa hợp đồng đầu ra và evaluator trước khi dùng PA để fine-tune hay hiệu chỉnh abstain.

Qwen2.5-Coder có các bản 7B và 14B; tài liệu chính thức nêu bản 14B có 14,7B tham số, và bản 7B/14B thuộc Apache 2.0. Đây là thông số do nhà phát triển công bố, không chứng minh hiệu năng trên DataMate. Qwen3-14B dense là ứng viên so sánh khác, không phải mặc định tốt hơn. [Qwen2.5-Coder: các kích thước và tham số](https://qwenlm.github.io/blog/qwen2.5-coder-family/), [Qwen2.5-Coder: huấn luyện và năng lực code do tác giả báo cáo](https://qwenlm.github.io/blog/qwen2.5-coder/), [Qwen3: các bản dense và giấy phép](https://qwenlm.github.io/blog/qwen3/)

## 2. Hiện trạng cần xử lý trong mã

Một số chỗ trong source hiện có thể làm mất điểm trước cả khi xét chất lượng mô hình:

| Thành phần | Hiện trạng quan sát được | Hướng xử lý |
|---|---|---|
| Model client | Mặc định nạp Qwen2.5-Coder-3B, trong khi README/architecture đặt 14B làm đích. Model ID đang ghi cứng trong client. | Đọc model path, revision, dtype, quantization và giới hạn context từ config được khóa phiên bản. |
| Bộ phân loại ý định | Phân loại bằng một số từ khóa cố định; chưa sinh kế hoạch có trường và kiểu dữ liệu rõ ràng. | Dùng classifier nhẹ/tất định để gợi ý intent, sau đó yêu cầu LLM trả QueryPlan JSON; xác thực trước khi chạy. |
| Prompt | Chèn quy tắc chung, rulebook đầy đủ và ví dụ Python tổng quát vào cùng prompt. Ví dụ có thể xung đột với rulebook của shop/split. | Tách chỉ dẫn ổn định khỏi quy tắc áp dụng; truy xuất đúng các mục rulebook liên quan và luôn giữ đúng rulebook của split. |
| Hợp đồng đáp án | Prompt có chỗ yêu cầu trả chuỗi “unanswerable”; hàm chuẩn hóa suy type từ kiểu Python. Do đó float thành number, ngày ISO thành string, chuỗi “unanswerable” thành string; bảng dạng dict thường không thành table. | Không suy type từ kiểu Python. Truyền answer type rõ ràng từ QueryPlan đến Answer và validator. |
| Benchmark | Evaluator hiện bỏ qua nội dung bảng và một số quy tắc định dạng trong rulebook. | Sửa evaluator trước khi lấy PA làm tiêu chí chọn model. |
| Tách dữ liệu | Split hiện tại giữ mọi doanh nghiệp ở cả train lẫn val. | Duy trì split đó để đo câu mới trên doanh nghiệp đã thấy; bổ sung split giữ nguyên doanh nghiệp để đo generalization. |
| Feasibility và entity linking | Metadata và temporal grounding đã có module, nhưng đường predict chưa có gate tất định và QueryPlan được xác thực; chưa có linker bí danh theo doanh nghiệp được nối vào pipeline. | Nối gate/linker vào pipeline; dùng bằng chứng dữ liệu để phân biệt unanswerable với abstain. |
| Temporal context | Có bộ giải mã thời gian trong prompt builder và module grounding riêng, nhưng pipeline dùng resolver trong prompt builder và không truyền rõ calendar của split. Hai cách triển khai có thể lệch nhau. | Dùng một temporal resolver duy nhất, truyền calendar của đúng package và kiểm tra theo rulebook split. |

Các điểm liên quan nằm trong [LLM client](../src/datamate/llm/client.py), [prompt builder](../src/datamate/llm/prompt_builder.py), [submission normalizer](../src/datamate/output/submission.py), [evaluator](../benchmark/evaluate.py), [splitter](../benchmark/split.py) và [entrypoint](../predict.py). Đây là nhận xét tĩnh theo source hiện có, chưa phải kết quả chạy inference.

## 3. Mô hình và cách huấn luyện

### 3.1. Cấu hình cần đưa vào bake-off

| Ứng viên | Vai trò | Nhận xét có thể xác nhận từ nguồn | Quyết định DataMate |
|---|---|---|---|
| Qwen2.5-Coder-3B-Instruct | Baseline hiện tại | Đang được dùng trong client; tiện cho phát triển cục bộ. | Giữ làm mốc so sánh, không mặc định là bản nộp. |
| Qwen2.5-Coder-7B-Instruct | Baseline production | Bản coder 7B; thông số/giấy phép được công bố trong tài liệu chính thức. | Chạy benchmark PA, thời gian và lỗi từng loại. |
| Qwen2.5-Coder-14B-Instruct | Ứng viên chính | Bản 14B có 14,7B tham số theo bảng chính thức, sát giới hạn 15B. | Chỉ dùng nếu audit tổng tham số, PA cross-business và thời gian đều đạt. Không ghép thêm embedding/reranker neural. |
| Qwen3-14B dense | Challenger | Qwen công bố bản dense 14B, Apache 2.0. | So sánh thực nghiệm nếu còn thời gian; không suy ra thắng từ benchmark của tác giả. |

**Không nạp nhiều backbone cùng lúc trong bản nộp.** Giới hạn được tính theo tổng tham số, không theo số tham số hoạt động và không giảm khi lượng tử hóa. Với 14,7B, phải tính cả adapter/thành phần học được nếu quy định của BTC xem chúng là tham số mô hình; lưu manifest và phép đếm để chứng minh. Nếu cần dư địa cho classifier/adapter hoặc 14B không tăng PA đủ rõ, chọn 7B.

Tài liệu mô hình chính thức cho biết Qwen2.5-Coder được thiết kế chuyên cho code và có các bản 7B/14B; đó là **tuyên bố và benchmark do tác giả mô hình báo cáo**, không phải đánh giá DataMate. Qwen3-14B chỉ nên là challenger. [Qwen2.5-Coder family](https://qwenlm.github.io/blog/qwen2.5-coder-family/), [Qwen3 release](https://qwenlm.github.io/blog/qwen3/)

### 3.2. Vai trò duy nhất của LLM

LLM nhận câu hỏi, schema đã rút gọn, README, các thực thể ứng viên, mốc thời gian và đúng phần rulebook cần áp dụng. LLM trả về một **kế hoạch truy vấn JSON có schema**, gồm:

- metric nghiệp vụ và type đầu ra;
- bảng/cột dự kiến cùng lý do chọn;
- mốc thời gian và loại ngày áp dụng;
- bộ lọc, nhóm, phép tổng hợp, thứ tự xếp hạng và cách phá hòa;
- phép nối cùng khóa nối;
- trạng thái: answer / unanswerable / uncertain;
- yêu cầu kiểm chứng sau khi chạy.

LLM **không** tự tính tổng số lớn, tự đoán dữ liệu còn thiếu, hoặc quyết định type đầu ra từ cách viết kết quả. Hệ thống chạy tính toán bằng SQLite/Python tất định và trả lại Answer có type rõ ràng.

### 3.3. Fine-tune có điều kiện

Không fine-tune trực tiếp để ghi nhớ 3.000 cặp câu hỏi–đáp án. Đáp án một mình không dạy mô hình cách nối bảng hay áp dụng đúng luật. Trước khi SFT, cần tạo các trace đã được kiểm chứng:

1. Câu hỏi và schema.
2. QueryPlan đã gán nhãn.
3. Mã/truy vấn được compiler sinh.
4. Kết quả chạy trên dữ liệu tương ứng.
5. So sánh với đáp án chuẩn và ghi nhận lý do nếu lệch.

Chỉ dùng các ID train. Dữ liệu tổng hợp được phép dùng khi giữ source/seed và kiểm chứng bằng thực thi; loại mẫu sinh có truy vấn lỗi hoặc không khớp gold. Bắt đầu từ SFT/LoRA cho QueryPlan; chỉ cân nhắc DPO/RLVR sau khi có đủ trace đúng/sai đáng tin cậy. Không fine-tune trên public/private test.

## 4. Kiến trúc đích

~~~mermaid
flowchart LR
    A["Question + as_of_date"] --> B["Chuẩn hóa câu hỏi"]
    B --> C["Business profile + schema graph"]
    C --> D["Lexicon / entity linking"]
    D --> E["Rulebook đúng split + temporal grounding"]
    E --> F["LLM: typed QueryPlan JSON"]
    F --> G{"Plan validator"}
    G -- "Không hợp lệ / mơ hồ" --> H["Abstain hoặc kiểm tra khả năng trả lời"]
    G -- "Hợp lệ" --> I["SQL compiler / phép tính allowlist"]
    I --> J["Read-only execution"]
    J --> K["Cross-check + provenance"]
    K --> L["Typed Answer validator"]
    L --> M{"PA confidence gate"}
    M -- "Đủ tin cậy" --> N["submission.jsonl"]
    M -- "Chưa đủ tin cậy" --> H
~~~

### 4.1. QueryPlan và runtime

Tạo kiểu dữ liệu phiên bản hóa cho QueryPlan/Answer. Compiler chỉ cho phép những phép toán cần thiết như lọc, join, sum/count/average, group-by, rank/top-k, so sánh kỳ, phần trăm, đơn vị quy đổi và tính tồn/nợ theo rulebook. Dùng truy vấn read-only, placeholder cho giá trị, kiểm tra tên bảng/cột với schema; số học tiền và làm tròn qua Decimal hoặc hàm tất định đã kiểm chứng.

Dữ liệu bất thường cần có provenance tới file, sheet, bảng, dòng và cột nguồn. Nếu truy vấn trả rỗng, phân biệt:
- kỳ ngoài toàn bộ khoảng dữ liệu hoặc thiếu loại thông tin cần thiết theo rulebook → có thể là unanswerable;
- kỳ nằm trong vùng dữ liệu nhưng không phát sinh giao dịch → thường là 0 hoặc danh sách rỗng theo type;
- kế hoạch không chắc bảng/cột/ý nghĩa → uncertain, không tự biến thành 0.

Có thể giữ sandbox hiện tại làm lớp phụ trong giai đoạn chuyển đổi, nhưng không nên xem kiểm tra AST là ranh giới bảo mật cho mã Python tùy ý do LLM sinh.

## 5. Từ vựng, entity linking và chuẩn hóa tiếng Việt

### 5.1. Tách ba mục tiêu chuẩn hóa

1. **Chuẩn hóa để so khớp đáp án:** NFC, casefold, chuẩn hóa dấu câu và khoảng trắng theo rulebook; giữ dấu tiếng Việt. Dùng alias đã có trong đáp án chuẩn. Không dùng phép bỏ dấu để chấm đúng một tên sai dấu.
2. **Chuẩn hóa để tìm ứng viên:** giữ khóa có dấu; tạo thêm khóa không dấu/chữ viết tắt/teencode chỉ để tìm candidate. Khóa không dấu có trọng số thấp hơn, không tự quyết định entity.
3. **Chuẩn hóa để xuất đáp án:** lấy tên/mã chuẩn từ dữ liệu nguồn; không xuất chuỗi đã làm mất dấu hoặc đã bị fuzzy rewrite.

Không dùng chung một hàm normalize cho cả ba mục đích.

### 5.2. Từ điển nghiệp vụ dùng chung

Mỗi thuật ngữ trỏ tới một khái niệm chuẩn và giữ các khác biệt nghiệp vụ quan trọng:

| Cụm từ thường gặp | Khái niệm chuẩn / điều phải phân biệt |
|---|---|
| “bán được bao nhiêu tiền”, “thu về bao nhiêu tiền”, “tiền hàng” | Doanh thu theo rulebook; không đồng nghĩa với tiền mặt thực nhận hoặc tiền trả nợ. |
| “tiền mặt”, “đã thu”, “thu nợ” | Dòng tiền/thanh toán; phải xác định theo ngày và hình thức thanh toán được rulebook chỉ định. |
| “đơn hủy” | Đơn hủy, khác với đơn trả hàng. |
| “trả hàng” | Rulebook train loại cả đơn khỏi doanh thu dù trả một phần; công nợ vẫn có quy tắc riêng. Không gộp với hủy. |
| “bán chạy”, “bán nhiều nhất”, “hot nhất” | Ranking theo số lượng quy về đơn vị cơ bản, không mặc định theo doanh thu. |
| “khách mua nhiều tiền nhất” | Ranking theo doanh thu của khách, không phải số đơn hay số ngày mua. |
| “ngày bán”, “ngày giao”, “ngày thu tiền” | Ba trường thời gian khác nhau; chọn loại ngày theo câu hỏi và rulebook. |
| “còn nợ”, “nợ thêm”, “trả nợ” | Các phép đo khác nhau; chú ý ngày đặt, khoản trả cùng ngày mua và loại đơn. |
| “thùng/hộp/lốc/vỉ/cái” | Chuyển đổi theo bảng quy đổi của shop và mặt hàng; không dùng tỷ lệ quy đổi toàn cục. |

Các biến thể khẩu ngữ như “dthu”, “hnay”, “bnhiu”, câu không dấu hay lỗi gõ là alias truy vấn, không phải dữ kiện để sửa đáp án. Không gộp “tiền thu” với “doanh thu” chỉ vì chúng xuất hiện gần nhau.

### 5.3. Từ điển riêng theo doanh nghiệp

Sinh từ master data/README và lưu kèm nguồn gốc:

- sản phẩm: mã, tên chuẩn, tên gọi khác, quy cách/size, nhóm hàng, đơn vị cơ bản và các bậc quy đổi;
- khách hàng: mã khách, tên, tên thường gọi, số điện thoại nếu dữ liệu cho phép dùng để phân biệt;
- nhà cung cấp, nhân viên, thuốc/hoạt chất, dòng xe/biển số và thực thể riêng ngành;
- bí danh cột: tên cột gốc → khái niệm chuẩn, độ tin cậy, bảng và file nguồn;
- các giá trị trạng thái/thanh toán thực sự xuất hiện trong shop.

Thứ tự liên kết nên là: mã chính xác → tên chuẩn → bí danh đã xác nhận → so khớp có dấu → candidate không dấu/fuzzy. Chỉ tự chọn khi điểm phù hợp cao và cách biệt đủ với ứng viên thứ hai; nếu hai ứng viên gần nhau thì đánh dấu uncertain. Không dựa vào question_id/business_id để mã hóa đáp án.

## 6. Answer, unanswerable và abstain

Answer cần luôn có type tường minh:

~~~json
{"type":"percent","answer":12.4}
~~~

Tương tự, ngày phải là date, số phần trăm là percent chứ không phải number, bảng phải là table; không suy type từ float, string hay dict. Validator phải từ chối sai kiểu JSON trước khi ghi submission.

- **unanswerable:** bằng chứng từ phạm vi dữ liệu/rulebook cho thấy thiếu dữ liệu cần thiết; nếu có reason thì reason phải là chuỗi.
- **abstain:** hệ thống chưa đủ chắc về schema linking, truy vấn hoặc kết quả, dù chưa chứng minh câu hỏi không thể trả lời.
- Không có human-in-the-loop nên không hỏi lại; mơ hồ không giải được thì abstain.

Với PA, nếu xác suất đã hiệu chuẩn rằng đáp án đúng hoàn toàn (cả type và giá trị) là p, kỳ vọng trả lời là 2p − 1; abstain có điểm 0. Vì vậy ngưỡng lý thuyết là p > 0,5. Không dùng confidence tự khai của LLM làm p. Ước lượng từ tín hiệu có thể kiểm tra: plan pass validator, trường được map rõ, khoảng thời gian hợp lệ, query chạy, nguồn dữ liệu bao phủ, kiểm tra chéo khớp và output schema hợp lệ. Chọn ngưỡng trên dự đoán out-of-fold theo doanh nghiệp, không fit rồi báo điểm trên cùng dữ liệu.

## 7. Benchmark và tiêu chí nghiệm thu

### 7.1. Bộ đánh giá

- Sửa evaluator để khớp hai rulebook split: kiểm tra JSON type nghiêm ngặt; số chính xác, chỉ dung sai biểu diễn float; chuỗi chuẩn hóa đúng; alias cho list/table; bảng so cột và tập hàng, không phụ thuộc thứ tự hàng; validate reason; không âm thầm bỏ dòng lỗi hoặc ID trùng.
- Giữ split câu hỏi hiện tại như phép đo in-domain. Tạo thêm split theo doanh nghiệp; nếu metadata ngành đủ tin cậy thì thêm leave-one-industry-out.
- Chỉ train/fine-tune trên train IDs. Không dùng nhãn validation vào train. Public test chỉ dùng theo quy chế cuộc thi, không biến thành dữ liệu huấn luyện.
- So sánh model trên cùng prompt, schema, compiler, decoding và giới hạn thời gian. Mỗi ứng viên cần cùng phiên bản input/output.

### 7.2. Chỉ số cần lưu

PA tổng; PA theo type/doanh nghiệp/ngành/intent; đúng/sai/abstain; coverage; sai trên gold unanswerable; lỗi định dạng; lỗi liên kết entity; lỗi truy vấn/runtime; độ trễ P50/P95 và tổng thời gian; chênh PA khi chạy lại. Báo số lượng câu của từng nhóm vì hiện validation có rất ít boolean/table nên điểm nhóm đó còn bất ổn.

### 7.3. Điều kiện trước khi đóng Docker

- Model, tokenizer, config, adapter và dependency được khóa phiên bản; lưu checksum và manifest.
- Nạp model từ thư mục cục bộ; chế độ offline không tải model hoặc gọi dịch vụ ngoài.
- Đếm tổng tham số theo đúng cách hiểu của BTC; không cộng thêm embedding/reranker neural nếu làm vượt giới hạn.
- Test contract cho cả 9 type, dữ liệu lỗi, chạy tiếp sau lỗi một câu, resume/ghi log, giới hạn RAM/VRAM và thời gian toàn tập.
- Chạy hai lượt độc lập để đo reproducibility; kiểm tra đủ ID, không trùng ID, mọi dòng parse được và không phụ thuộc thứ tự input.

## 8. Thứ tự triển khai

| Ưu tiên | Việc cần làm | Tiêu chí xong |
|---|---|---|
| P0 | Sửa Answer contract, validator và evaluator theo mục 9 của rulebook train/public. | Các trường hợp sai JSON type, alias, bảng, unanswerable được chấm đúng; mọi lỗi file được báo rõ. |
| P1 | Hoàn thiện ingestion/profile, truyền đúng rulebook/calendar của split, tạo schema graph và từ điển alias có provenance. | Entity/cột/thời gian có candidate, confidence và nguồn; không fuzzy chọn khi mơ hồ. |
| P2 | Chốt schema QueryPlan JSON, validator và compiler/allowlist SQL. | Query chỉ chạy khi plan hợp lệ và mọi cột/bảng tồn tại; phép tính tiền/type tất định. |
| P3 | Benchmark 3B, 7B, 14B; sau đó mới quyết định SFT/LoRA trên trace đã kiểm chứng. | Chọn theo cross-business PA + coverage + lỗi + latency; có manifest tham số. |
| P4 | Hiệu chuẩn abstain, offline packaging và kiểm tra tái lập. | Đạt PA/latency/reproducibility theo challenge và xuất được log cho từng câu. |

**Điều chưa nên làm:** tuyên bố 14B là mô hình thắng trước khi chạy PA; fine-tune trên cả 3.000 câu rồi chấm trên 608 câu trong đó; dùng fuzzy không ngưỡng; hoặc để prompt tự viết logic nghiệp vụ thay cho kiểm tra có cấu trúc.


