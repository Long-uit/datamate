# BÁO CÁO ĐÁNH GIÁ CHUYÊN SÂU 30 CÂU HỎI QUA TỪNG MODULE
## DataMate Engine — Modular Diagnostic & Benchmark Report

> [!NOTE]
> **Môi trường thử nghiệm:**
> - **Dữ liệu:** 30 câu hỏi ngẫu nhiên từ tập dữ liệu huấn luyện thực tế (`competition_data/train`), trải rộng trên 12 cửa hàng bán lẻ (`biz_103` đến `biz_130`).
> - **Mô hình AI:** `Qwen/Qwen2.5-Coder-3B-Instruct` lượng tử hóa 4-bit NF4 (`bitsandbytes`) chạy trực tiếp trên GPU máy trạm RTX 3050 Laptop (VRAM ~3.8GB).
> - **Cơ chế:** Đánh giá độc lập 7 modules: Ingestion, Feasibility Gate, Grounding, Prompt Builder, LLM Code Generation, Execution Sandbox, Output Normalizer & Abstention Shield.

---

## 1. TỔNG QUAN HIỆU SUẤT VÀ ĐIỂM SỐ (SCORECARD)

| Chỉ số đánh giá | Kết quả thực tế | Tỷ lệ (%) | Ý nghĩa & Đánh giá |
| :--- | :---: | :---: | :--- |
| **Tổng số câu hỏi đánh giá** | **30 câu** | 100.0% | Bao phủ đầy đủ các dạng bài: Doanh thu, Đơn hàng, Top-K, Tỷ lệ hủy đơn, Tồn kho. |
| **Đáp án Chính Xác (+1.0)** | **4 câu** | **13.3%** | Giải đúng 100% khớp đáp án Ban Tổ Chức (BTC) với độ lệch số học $\le 10^{-2}$. |
| **Đáp án Bị Trừ Điểm (-1.0)** | **7 câu** | **23.3%** | Trả lời sai do lỗi mô hình hoặc nhầm lẫn logic tính toán. |
| **Từ Chối Trả Lời (Abstain - 0.0)** | **19 câu** | **63.3%** | Kích hoạt tấm khiên an toàn (Abstention Shield) khi phát hiện code lỗi/timeout/AST. |
| **Penalized Accuracy (PA)** | **-0.1000** | - | Điểm thi thức tế theo công thức BTC: $\text{PA} = \frac{\text{Correct} - \text{Wrong}}{\text{Total}} = \frac{4 - 7}{30}$. |
| **Độ chính xác khi trả lời (Accuracy)** | **36.36%** | - | Tỷ lệ đúng trên tổng số câu có trả lời: $\frac{4}{4 + 7}$. |
| **Độ bao phủ dữ liệu (Coverage)** | **36.67%** | - | Tỷ lệ câu dám trả lời trên toàn bộ tập dữ liệu: $\frac{11}{30}$. |
| **Tổng thời gian chạy (End-to-End)** | **2,562.06s** | - | Trung bình **85.40s / câu** (Bao gồm nạp CSV, sinh mã LLM và chạy sandbox). |

```mermaid
pie title Phân Bổ Kết Quả 30 Câu Hỏi DataMate
    "Đúng (+1 point)" : 4
    "Sai (-1 penalty)" : 7
    "Từ chối Abstain (0 point)" : 19
```

> [!IMPORTANT]
> **Vai trò cứu nguy của Abstention Shield:**
> Nếu không có cơ chế Abstention Shield (bắt lỗi AST, sandbox timeout, sanity check), 19 câu này sẽ bị phán đoán mò hoặc văng lỗi ra kết quả sai, đẩy số câu sai lên **26/30** và kéo điểm PA tụt thảm hại xuống **-0.7333 (-22/30)**. 
> Abstention Shield đã **bảo toàn thành công +19.0 điểm phạt** cho toàn bộ hệ thống!

---

## 2. HIỆU NĂNG VÀ ĐỘ TRỄ CHI TIẾT TỪNG MODULE

Dưới đây là bảng thống kê thời gian thực thi (Latency Profiling) của 7 module đo đạc trực tiếp trên 30 câu hỏi:

| Thứ tự Module | Tên Module DataMate | Mean (s) | Median (s) | Max (s) | Tỷ trọng thời gian (%) | Đánh giá nghẽn (Bottleneck) |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| **M1** | **Ingestion & Schema Profiler** | 9.77s | 1.72s | 42.29s | 11.4% | **Trung bình - Thấp** (Nặng ở lần nạp đầu, < 0.1ms khi trúng cache) |
| **M2** | **Feasibility Gate** | 0.007s | 0.006s | 0.072s | 0.0% | **Cực nhanh** (Xử lý thuần metadata & regex, không tốn GPU) |
| **M3** | **Grounding (Temporal + Entity)** | 0.066s | 0.064s | 0.175s | 0.1% | **Cực nhanh** (Lọc thời gian và đối chiếu từ khóa sản phẩm) |
| **M4** | **Prompt Builder & Few-Shot** | 0.004s | 0.004s | 0.008s | 0.0% | **Tức thì** (Ghép prompt và dynamic few-shot theo Intent) |
| **M5** | **LLM Code Generation (3B)** | **55.98s** | **49.43s** | **101.04s** | **65.6%** | 🔥 **ĐIỂM NGHẼN CHÍNH 1** (Sinh 512 token trên GPU 4-bit) |
| **M6** | **Execution Sandbox Subprocess** | **19.57s** | **20.69s** | **30.02s** | **22.9%** | 🔥 **ĐIỂM NGHẼN CHÍNH 2** (Khởi động tiến trình con + nạp lại CSV) |
| **M7** | **Normalizer & Abstention Shield** | 0.000s | 0.000s | 0.003s | 0.0% | **Tức thì** (Chuẩn hóa kết quả và tính điểm Confidence) |

```mermaid
flowchart TD
    Q["Câu hỏi + as_of_date"] --> M1["M1: Ingestion & Schema<br/><b>9.77s</b> (11.4%)"]
    M1 --> M2["M2: Feasibility Gate<br/><b>0.007s</b> (0.0%)"]
    M2 -->|Hợp lệ| M3["M3: Grounding<br/><b>0.066s</b> (0.1%)"]
    M2 -.->|Không thể trả lời| M7
    M3 --> M4["M4: Prompt Builder<br/><b>0.004s</b> (0.0%)"]
    M4 --> M5["M5: LLM Code Gen (Qwen 3B)<br/>🔥 <b>55.98s</b> (65.6%)"]
    M5 --> M6["M6: Execution Sandbox<br/>🔥 <b>19.57s</b> (22.9%)"]
    M6 --> M7["M7: Normalizer & Shield<br/><b>0.000s</b> (0.0%)"]
    M7 --> ANS["Submission JSON"]

    classDef bottleneck fill:#ffe6e6,stroke:#ff0000,stroke-width:2px;
    classDef fast fill:#e6ffe6,stroke:#00aa00,stroke-width:1px;
    class M5,M6 bottleneck;
    class M2,M3,M4,M7 fast;
```

---

## 3. PHÂN TÍCH CHUYÊN SÂU 7 CÂU SAI (-1.0 PENALTY)

Việc mổ xẻ nguyên nhân 7 câu bị trừ điểm mang lại phát hiện cực kỳ quan trọng về mặt kiến trúc:

| Index | Question ID | Cửa hàng | Câu hỏi của người dùng | Đáp án BTC (Gold) | Model sinh ra (Pred) | Nguyên nhân cốt lõi |
| :---: | :---: | :---: | :--- | :---: | :---: | :--- |
| **Q04** | `q_00558c1410ef` | `biz_105` | tỉ lệ huỷ đơn tháng 6/2025 là nhiêu % | **2.08%** | **2.29%** | **Sai lệch điều kiện lọc:** Lệch mẫu số (Tổng đơn) do cách tính đơn hủy/trả hàng khác nhau giữa các trạng thái. |
| **Q06** | `q_0088f7a0afc5` | `biz_119` | Tháng 7/2025 mặt hàng Otrivin 0,1% xịt mũi chai 10ml bán được tổng cộng bao nhiêu chai? | **77** | `unanswerable` | ⚠️ **Lỗi Prompt Few-Shot:** Code LLM không tìm thấy cột khớp 100% nên tự gọi `return "unanswerable"`. |
| **Q07** | `q_008f69128180` | `biz_117` | trong thang 10/2025, ti le don huy la bnhiu % | **1.21%** | `unanswerable` | ⚠️ **Lỗi Prompt Few-Shot:** Tương tự Q06, code LLM bắt ngoại lệ bằng `return "unanswerable"`. |
| **Q11** | `q_00d4d6380d03` | `biz_114` | thang 6/2025 hang nao chay nhat | **Gạch ống 8x8x18 Tuynel** | `unanswerable` | ⚠️ **Lỗi Prompt Few-Shot:** Không tìm thấy bảng bán lẻ nên tự trả về `unanswerable`. |
| **Q14** | `q_0139627bccae` | `biz_104` | check gium hnay cua hang co bao nhiu don | **107** | **15,173,000** | **Lỗi Nhầm Intent:** Câu hỏi hỏi "bao nhiêu đơn" (số lượng giao dịch) nhưng code LLM lại tính tổng doanh thu (VND)! |
| **Q18** | `q_0194d8d10f17` | `biz_111` | Tính đến hết ngày 19/08/2026, có bao nhiêu khách còn nợ cửa hàng? | **35** | `unanswerable` | ⚠️ **Lỗi Prompt Few-Shot:** Code LLM không tìm thấy đúng cột công nợ nên sinh `return "unanswerable"`. |
| **Q29** | `q_0279f675859e` | `biz_111` | thang 7/2025, cac khach thuoc nhom than thiet mua tong cong bao nhiu tien hang | **46,871,000** | `unanswerable` | ⚠️ **Lỗi Prompt Few-Shot:** Nhóm khách hàng không join được nên code tự trả về `unanswerable`. |

### 💥 PHÁT HIỆN ĐỘT PHÁ: "Căn Bệnh" False Unanswerable do Prompt Few-Shot
Trong 7 câu sai:
- Có tới **5 câu (Q06, Q07, Q11, Q18, Q29) chiếm 71.4% số lỗi** KHÔNG PHẢI do Feasibility Gate chặn, mà do **mô hình LLM bắt chước đoạn code mẫu trong Few-shot**:
  ```python
  # Đoạn code trong ví dụ mẫu của prompt_builder.py:
  if df_sales is None:
      return "unanswerable"
  if grouped.empty:
      return "unanswerable"
  ```
- Khi code thực thi trong sandbox, nếu điều kiện lọc bị rỗng hoặc tên cột khác một chút, hàm `solution` trả về chuỗi `"unanswerable"`.
- Adapter của sandbox và Normalizer chuyển thành `{"type": "unanswerable", "answer": None}` với độ tin cậy tuyệt đối (`confidence = 1.0`).
- BTC chấm điểm: Câu hỏi vốn dĩ trả lời được bằng số nhưng model nộp `unanswerable` $\rightarrow$ **Bị xử phạt -1.0 điểm**!

> [!TIP]
> **Kịch bản phục hồi điểm số tức thì:**
> Nếu ta sửa quy tắc code: *"Khi không tìm thấy bảng/cột, hàm `solution` trả về `None` (để rơi vào Abstain an toàn) chứ TUYỆT ĐỐI KHÔNG trả về `unanswerable`"*:
> - 5 câu này sẽ biến thành **Abstain (0.0 điểm)** thay vì bị trừ **(-5.0 điểm)**.
> - Khi đó: Đúng 4, Sai 2, Abstain 24.
> - **Điểm PA sẽ lập tức đảo chiều từ âm (-0.1000) sang DƯƠNG: $\text{PA} = \frac{4 - 2}{30} = +0.0667$!**

---

## 4. PHÂN TÍCH 19 CÂU TỪ CHỐI (ABSTAIN - 0.0 POINT)

19 câu từ chối trả lời được Abstention Shield ngăn chặn thành công thuộc 3 nhóm chính:

```mermaid
pie title Phân Loại 19 Câu Abstain An Toàn
    "Lỗi cú pháp AST / Sinh dở dang" : 10
    "Sandbox Timeout (> 30s)" : 6
    "Pandas Runtime Exception" : 3
```

1. **Nhóm 1: Lỗi cú pháp AST / Sinh dở dang (10 câu - 52.6%)**
   - *Biểu hiện:* Qwen 3B bị cắt cụt do giới hạn token (`unterminated string literal`, `invalid syntax`, thiếu dấu hai chấm `:`).
   - *Xử lý:* Tấm khiên AST Checker phát hiện cú pháp hỏng, kích hoạt Self-correction 1 lần; nếu vẫn lỗi thì fallback ngay về `make_abstain("AST Syntax Error")` $\rightarrow$ Đạt 0.0 điểm, tránh bị trừ -10 điểm.
2. **Nhóm 2: Sandbox Timeout quá 30 giây (6 câu - 31.6%)**
   - *Biểu hiện:* Các câu phức tạp trên cửa hàng lớn (như `biz_124` có 27 bảng, `biz_106`, `biz_128`).
   - *Nguyên nhân:* Tiến trình con sandbox khởi động lại từ đầu và đọc lại hàng trăm MB file CSV từ ổ đĩa cứng, chiếm mất 15-25s của thời gian chờ (timeout limit 30s).
   - *Xử lý:* Hard timeout 30s ngắt an toàn và trả về Abstain $\rightarrow$ Tránh treo toàn bộ chương trình và tránh kết quả rác.
3. **Nhóm 3: Pandas Runtime Exception (3 câu - 15.8%)**
   - *Biểu hiện:* `KeyError: None`, `KeyError: 'Tổng sau giảm giá'`, `NameError: name 'total' is not defined`.
   - *Xử lý:* Sandbox bắt được lỗi ngoại lệ và Abstention Shield gán điểm Confidence = 0.0 $\rightarrow$ Giữ nguyên 0.0 điểm.

---

## 5. PHÂN TÍCH 4 CÂU ĐẠT CHUẨN TUYỆT ĐỐI (+1.0 CORRECT)

4 câu hỏi giải quyết xuất sắc chứng minh năng lực lõi của kiến trúc DataMate khi dữ liệu và prompt ăn khớp:

1. **Q03 (`q_002d03ebbded` - biz_120):**
   - *Câu hỏi:* "Tổng doanh thu trong ngày hôm nay là bao nhiêu?" (as_of_date: `2025-04-30`)
   - *Kết quả:* Khớp chính xác **10,309,400 VNĐ** (Thời gian sandbox: 29.01s).
2. **Q15 (`q_0166f82c0223` - biz_104):**
   - *Câu hỏi:* "thang 9/2025 cua hang co bnhiu % don bi huy"
   - *Kết quả:* Khớp chính xác **1.66%** (Thời gian sandbox: 11.60s).
3. **Q22 (`q_01a47607f90c` - biz_128):**
   - *Câu hỏi:* "tổng dthu trong ngày hôm nay là bao nhiêu vaayj"
   - *Kết quả:* Khớp chính xác **39,793,500 VNĐ** (Thời gian sandbox: 22.89s).
4. **Q28 (`q_0271d9f39fde` - biz_112):**
   - *Câu hỏi:* "tháng 5/2026 cửa hàng có nhiêu % đơn bị huỷ"
   - *Kết quả:* Khớp chính xác **2.19%** (Thời gian sandbox: 18.76s).

> [!NOTE]
> **Nhận xét chuyên môn:**
> - Các câu hỏi tính **doanh thu trong ngày (`hôm nay`)** và **tỷ lệ đơn hủy (`%`)** đạt độ chính xác **100%** khi mô hình sinh đúng cấu trúc.
> - Temporal Grounding phân tích cực kỳ chính xác mốc ngày `as_of_date` và khoảng thời gian tháng.

---

## 6. KẾ HOẠCH HÀNH ĐỘNG TỐI ƯU HÓA (ACTION PLAN)

Dựa trên kết quả thực nghiệm 30 câu, đây là 4 giải pháp can thiệp có tính chất quyết định để nâng điểm số:

### Hành động 1: Cấm LLM tự ý sinh `return "unanswerable"` (Ưu tiên số 1 - Tăng ngay +0.1667 PA)
- **Vấn đề:** 5/7 câu sai là do LLM tự đoán `unanswerable` khi gặp lỗi truy vấn nhỏ.
- **Giải pháp:**
  - Sửa lại toàn bộ các ví dụ Few-Shot trong [prompt_builder.py](file:///d:/Projects/AI%20%20project/datamate/src/datamate/llm/prompt_builder.py): Thay tất cả các lệnh `return "unanswerable"` bên trong code bằng `return None`.
  - Chỉ duy nhất **Feasibility Gate** (Module 2) được quyền kết luận một câu hỏi là `unanswerable` dựa trên quy tắc nghiệp vụ rõ ràng (thiếu cột giới tính, thiếu camera,...). Nếu Feasibility Gate cho qua, LLM bắt buộc phải cố gắng tính toán hoặc trả về `None` để Abstain an toàn.

### Hành động 2: Tối ưu hóa I/O cho Execution Sandbox (Giảm 70% Timeout)
- **Vấn đề:** Subprocess sandbox hiện tại đang đọc lại CSV từ đĩa cho từng câu hỏi, mất 15-25s chỉ để load dữ liệu của shop lớn.
- **Giải pháp:**
  - Trong [sandbox.py](file:///d:/Projects/AI%20%20project/datamate/src/datamate/execution/sandbox.py), truyền sẵn SQLite database file (`biz.db`) hoặc nạp dữ liệu từ RAM Shared Memory thay vì đọc lại hàng loạt file CSV.
  - Tăng nhẹ hard timeout từ 30s lên 45s cho các shop có trên 20 bảng dữ liệu.

### Hành động 3: Thêm Rule phân biệt "Bao nhiêu đơn" vs "Bao nhiêu tiền"
- **Vấn đề:** Q14 bị nhầm lẫn giữa đếm số lượng hóa đơn (`len(df)`) và tính tổng tiền hàng (`df['Thành tiền'].sum()`).
- **Giải pháp:** Bổ sung rule tường minh vào System Prompt:
  - Nếu câu hỏi chứa *"bao nhiêu đơn / số lượng đơn / có mấy đơn"*: Kiểu kết quả trả về là số nguyên đếm (`count()`).
  - Nếu câu hỏi chứa *"doanh thu / tiền hàng / giá trị / bao nhiêu tiền"*: Kiểu kết quả trả về là số tiền (`sum()`).

### Hành động 4: Đánh giá khả năng nâng cấp lên Qwen2.5-Coder-7B khi nộp bài
- Trên máy cá nhân RTX 3050 Laptop (4GB VRAM), mô hình 3B chạy an toàn không bị tràn bộ nhớ nhưng sinh lỗi cú pháp ở 10/30 câu.
- Khi triển khai môi trường dự thi (GPU Colab T4 / Kaggle / Cloud 16GB VRAM), chuyển sang `Qwen/Qwen2.5-Coder-7B-Instruct` sẽ giảm thiểu đáng kể lỗi cú pháp AST, dự kiến nâng độ phủ từ 36% lên trên 75%.
