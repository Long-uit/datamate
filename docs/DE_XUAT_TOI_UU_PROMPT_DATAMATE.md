# BÁO CÁO ĐỀ XUẤT CẢI TIẾN THIẾT KẾ PROMPT & PIPELINE DATAMATE

> **Người gửi:** Phát  
> **Người nhận:** Long & Team DataMate  
> **Chủ đề:** Tối ưu hóa Prompting, Khắc phục lỗi False Zero, Đồng bộ Rulebook §1 và Nâng cao điểm số Penalized Accuracy (PA)  
> **Ngày:** 13/11/2026  

---

## I. BỐI CẢNH & MỤC TIÊU CỐT LÕI (CORE OBJECTIVE)

Trong bài toán thi đấu DataMate, chỉ số quyết định thứ hạng là **Penalized Accuracy (PA)**:
* **Trả lời đúng:** $+1.0$ điểm.
* **Chủ động từ chối (Abstain / Không thể trả lời):** $0.0$ điểm.
* **Trả lời sai:** $-1.0$ điểm (bị phạt nặng).

> ⚠️ **Quy tắc sống còn:** Khi dữ liệu bị thiếu, cột/bảng không tồn tại hoặc thực thể không kinh doanh tại cửa hàng, việc cố tình ép mã nguồn trả về con số `0` sẽ khiến hệ thống bị **trừ thẳng 1.0 điểm**. Ngược lại, nếu mã nguồn chủ động phát hiện và báo không trả lời được (`CannotAnswer`), pipeline sẽ đưa ra quyết định **Abstain an toàn** và nhận **0.0 điểm** (bảo toàn điểm số).

Dưới đây là phân tích chi tiết 6 lỗi thiết kế prompt hiện tại, phương án kỹ thuật xử lý và kế hoạch nghiệm thu cụ thể để team thống nhất trước khi triển khai.

---

## II. CHI TIẾT 6 HẠNG MỤC CẢI TIẾN

### 1. Gỡ Quy tắc 7 & 9 ("Không return None / không raise, cứ trả 0") $\rightarrow$ Phân biệt "Dữ liệu không tồn tại" vs "Số lượng bằng 0"

#### A. Vấn đề hiện tại (Root Cause)
Trong file `src/datamate/llm_execution/prompt.py` (dòng 681 & 683), prompt đang ép buộc mô hình:
```text
7. Nếu dữ liệu sau lọc rỗng hoặc không tìm thấy: trả về 0 (doanh thu/số đơn/số lượng), 0.0 (tỉ lệ), hoặc [] (top-k). Không return None.
...
9. TUYỆT ĐỐI KHÔNG raise DataNotFoundError hay các Exception khác. Nếu bảng/cột không khớp, hãy trả về 0, 0.0 hoặc []!
```
* **Hậu quả ("Silent Zero" độc hại):**
  * Khi câu hỏi nhắc đến một sản phẩm hoàn toàn **không có trong danh mục của shop** (ví dụ: Shop bán vật liệu xây dựng nhưng câu hỏi hỏi *"Doanh thu trà sữa tháng 5"*), mô hình lọc `df[item_col].str.contains("trà sữa")` ra DataFrame rỗng (0 dòng trong toàn bộ lịch sử cửa hàng).
  * Do bị cấm raise exception và bị ép trả 0, mô hình return `0`.
  * Đáp án đúng của BTC trong trường hợp này là `unanswerable` (hoặc câu hỏi không khả thi). Việc hệ thống trả lời `0` bị coi là câu trả lời sai $\rightarrow$ **bị phạt $-1.0$ điểm**.

#### B. Phương pháp giải quyết
1. Bổ sung exception chuẩn nghiệp vụ `CannotAnswer(Exception)` vào môi trường sandbox.
2. Viết lại Quy tắc 7 & 9 trong System Prompt:
   * **Trường hợp A (Raise `CannotAnswer` $\rightarrow$ Nhận 0.0 điểm):** Nếu thiếu bảng/cột bắt buộc, hoặc bộ lọc thực thể (sản phẩm / khách hàng / danh mục) **khớp 0 dòng trong TOÀN BỘ lịch sử bảng dữ liệu** (nghĩa là shop chưa bao giờ có thực thể này), code BẮT BUỘC phải:
     ```python
     raise CannotAnswer("Sản phẩm/Khách hàng không tồn tại trong danh mục của cửa hàng")
     ```
     Khi đó, sandbox sẽ bắt ngoại lệ này và đưa vào cổng Abstention an toàn (0.0 điểm thay vì -1.0).
   * **Trường hợp B (Trả về `0` thật sự $\rightarrow$ Nhận +1.0 điểm):** Thực thể **CÓ TỒN TẠI** trong danh mục của shop (tìm thấy ít nhất 1 dòng trong lịch sử), nhưng trong **kỳ thời gian / trạng thái được hỏi** không phát sinh giao dịch nào. Lúc này trả về `0` là hoàn toàn chính xác.

---

### 2. Gỡ Regex lọc theo dòng (`tra|hoan|huy`) ở Quy tắc 5 $\rightarrow$ Đồng bộ triệt để với Rulebook §1

#### A. Vấn đề hiện tại (Root Cause)
Quy tắc 5 trong system prompt hiện tại đang hướng dẫn:
```python
st_c = next((c for c in cols if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt'])), None)
if st_c: 
    df = df[~df[st_c].astype(str).str.contains(r'hủy|huỷ|huy|trả|tra|hoàn|hoan|cancel|return', case=False, na=False)]
```
* **Mâu thuẫn với Rulebook §1:**
  1. **Lọc dòng vs Loại bỏ cấp đơn hàng:** Theo Rulebook §1, nếu một đơn hàng có **bất kỳ dòng nào bị trả hàng**, thì **toàn bộ đơn hàng đó** phải bị loại bỏ hoàn toàn (hoặc trừ theo đơn hàng), không được chỉ xóa mỗi dòng trả hàng rồi vẫn cộng doanh thu của các dòng còn lại trong cùng đơn.
  2. **Nhầm lẫn trạng thái:** "Hủy đơn" khác hoàn toàn với "Trả hàng". Lọc gộp chung làm sai lệch kết quả của các câu hỏi chuyên biệt về đơn hủy.
  3. **False-Positive do từ khóa ngắn:** Regex `tra` rất dễ lọc nhầm các mặt hàng như *"trà xanh"*, *"trà sữa"*, hoặc ghi chú *"trả góp"*, *"đã trả đủ"*.

#### B. Phương pháp giải quyết
* Gỡ bỏ hoàn toàn đoạn regex lọc theo dòng này khỏi Quy tắc 5 của system prompt.
* Hướng dẫn mô hình sử dụng hàm trợ giúp chuẩn Rulebook §1:
  * Doanh thu: Gọi helper tất định `revenue(data, start_date=..., end_date=..., product=...)`.
  * Đếm đơn: Gọi helper `count_orders(data, start_date=..., end_date=..., status='valid'|'cancelled')`.
  * Nếu bắt buộc viết tay: Hướng dẫn tìm danh sách mã đơn vi phạm trước, sau đó loại bỏ toàn bộ đơn hàng bằng `df[~df[order_col].isin(invalid_orders)]`.

---

### 3. Viết lại Exemplar Doanh thu để gọi `revenue(...)` thay vì dạy mô hình viết tay

#### A. Vấn đề hiện tại (Root Cause)
Trong `EXEMPLAR_BANK["aggregation"]` (`prompt.py`, dòng 1157-1187), bài mẫu tính doanh thu hiện đang dài 30 dòng với logic viết tay:
* Bóc cột tiền $\rightarrow$ bóc ngày $\rightarrow$ lọc regex trạng thái $\rightarrow$ tạo mask tháng $\rightarrow$ lọc tên sản phẩm $\rightarrow$ `sum()`.
* **Hậu quả:** Mô hình ngôn ngữ lớn (LLM) phụ thuộc cực kỳ nặng vào **Few-shot Exemplar**. Dù system prompt có dặn dùng helper, nhưng khi nhìn thấy Exemplar viết tay dài dòng, LLM sẽ copy nguyên mẫu cách viết tay:
  * Dẫn đến việc chọn sai cột tiền (lấy nhầm cột cấp đơn "Tiền khách trả" / "Tổng bill" thay vì "Thành tiền sau chiết khấu").
  * Bỏ quên các bảng chiết khấu, quy đổi đơn vị tính.
  * Bỏ qua helper `revenue(...)` đã được tối ưu sẵn.

#### B. Phương pháp giải quyết
Viết lại toàn bộ exemplar `aggregation` thành dạng chuẩn mực, súc tích:
```python
--- VÍ DỤ MINH HỌA: TÍNH DOANH THU / TIỀN BÁN HÀNG ---
Câu hỏi: "Tháng 3/2026 hàng nước ép dưa hấu (L) thu về bao nhiêu tiền?" (as_of_date = "2026-06-24")
```python
def solution(data):
    # Ưu tiên gọi hàm nghiệp vụ chuẩn tắc Rulebook §1
    val = revenue(data, start_date="2026-03-01", end_date="2026-03-31", product="nước ép dưa hấu")
    if val is None or val < 0:
        raise CannotAnswer("Không tìm thấy dữ liệu doanh thu hợp lệ cho mặt hàng này")
    return int(round(val))
```
```

---

### 4. Sửa `code_hint` Ngày tháng (Tránh so sánh trực tiếp chuỗi với `pd.Timestamp`)

#### A. Vấn đề hiện tại (Root Cause)
Trong `src/datamate/grounding_feasibility/temporal.py` (dòng 727, 744, 766), biến `code_hint` đang sinh ra gợi ý:
```python
(df[date_col] >= pd.Timestamp('2026-03-01')) & (df[date_col] <= pd.Timestamp('2026-03-31 23:59:59'))
```
* **Hậu quả:** Cột `date_col` gốc khi nạp từ file CSV/Excel thường có kiểu chuỗi (`object/string`). Việc so sánh trực tiếp giữa một Series chuỗi và `pd.Timestamp` sẽ ném ra lỗi:
  ```text
  TypeError: Invalid comparison between dtype=object and Timestamp
  ```
* Lỗi này làm hỏng lượt chạy đầu tiên của code, buộc pipeline phải tốn thời gian vào vòng Self-Correction.

#### B. Phương pháp giải quyết
Điều chỉnh nội dung tiêm vào `code_hint` trong `temporal.py` để hướng dẫn ép kiểu ngày trước:
```python
# Cú pháp an toàn tuyệt đối:
df['clean_date'] = clean_date(df[date_col])
mask = (df['clean_date'] >= '2026-03-01') & (df['clean_date'] <= '2026-03-31 23:59:59')
```
Hoặc gợi ý sử dụng helper `in_period(df, start_date, end_date)`.

---

### 5. Lọc sạch không gian thực thể của Entity Linker & Không in mục "THỰC THỂ" rác

#### A. Vấn đề hiện tại (Root Cause)
1. **Lẫn cột số lượng/đơn vị tính vào thực thể:** Trong `entity_linker.py`, hàm `extract_candidates_from_business` duyệt qua các cột. Nếu một bảng có cột đơn vị tính hoặc quy cách chứa các giá trị như *"2 bao"*, *"1 thùng"*, *"hộp 10 vỉ"*, chúng bị gán nhầm là ứng viên thực thể. Khi câu hỏi xuất hiện *"bán được 2 bao xi măng"*, Entity Linker nhận nhầm *"2 bao"* là tên sản phẩm!
2. **In block thực thể rỗng/nhiễu:** Với các câu hỏi tổng quát không có thực thể (ví dụ: *"Tổng doanh thu toàn cửa hàng tháng trước là bao nhiêu?"*), mục `THỰC THỂ KHỚP TRONG CSDL` trong prompt đôi khi vẫn xuất hiện các từ dừng không liên quan, khiến LLM cố công đi lọc theo một thực thể ảo.

#### B. Phương pháp giải quyết
1. **Thiết lập Blacklist cột rõ ràng khi trích xuất Candidate:**
   * Bỏ qua các cột số lượng: `qty`, `số lượng`, `sl`, `quy cách`, `đơn vị tính`, `dvt`.
   * Bỏ qua các cột tiền tệ: `giá`, `tiền`, `đơn giá`, `thành tiền`, `chiết khấu`.
   * Bỏ qua các cột ngày tháng: `ngày`, `date`, `thời gian`.
   * Bỏ qua các cột mã đơn/mã chứng từ.
   * **Chỉ trích xuất từ:** Tên sản phẩm/hàng hóa, Tên khách hàng, Tên danh mục/nhóm hàng, Hoạt chất.
2. **Kiểm tra chặt chẽ trước khi render Prompt:** Chỉ hiển thị khối `THỰC THỂ KHỚP TRONG CSDL (ENTITY LINKING)` khi có ít nhất 1 thực thể khớp thực sự với danh từ riêng trong câu hỏi (với độ tương đồng cao $\ge 0.65$).

---

### 6. Rút gọn System Prompt từ ~2.800 token xuống $\le$ 1.500 token, xóa bỏ nội dung trùng lặp

#### A. Vấn đề hiện tại (Root Cause)
Hiện tại quy tắc tính **Doanh thu** đang bị lặp lại ở 5 vị trí khác nhau:
1. Trong phần lõi `core` của System Prompt.
2. Trong phần `conditional_rules` (`[Doanh thu hợp lệ]`).
3. Trong `req_3` của User Prompt (`build_prompt`).
4. Trong `rulebook_block` (trích đoạn Rulebook §1).
5. Trong Few-shot Exemplar `aggregation`.

* **Tác hại lớn:**
  * Tổng dung lượng prompt lên tới **2.800 - 3.500 token**, làm mô hình bị phân tán chú ý (*Lost in the Middle*).
  * Làm tăng thời gian phản hồi đầu tiên (Time to First Token - TTFT), làm chậm tốc độ xử lý batch trên Kaggle.
  * Tăng nguy cơ bị kích hoạt bộ cắt tỉa prompt (`MAX_SAFE_INPUT_TOKENS`) làm mất các thông tin schema quan trọng.

#### B. Phương pháp giải quyết
* Tối giản System Prompt: Gom toàn bộ quy tắc về doanh thu về 1 câu duy nhất: Khẳng định gọi `revenue(...)` là tiêu chuẩn cao nhất.
* Loại bỏ văn phong rườm rà, tập trung vào cú pháp Python rõ ràng.
* Khống chế toàn bộ System Instruction dưới **1.500 token** (đo đạc chính xác qua Qwen2.5 Tokenizer).

---

## III. BẢNG SO SÁNH TỔNG HỢP TRƯỚC VÀ SAU CẢI TIẾN

| Hạng mục | Hiện tại (Trước cải tiến) | Đề xuất mới (Sau cải tiến) | Kỳ vọng tác động điểm số (PA) |
| :--- | :--- | :--- | :--- |
| **Thực thể không tồn tại** | Bị ép trả về `0` (Silent Zero) | `raise CannotAnswer` $\rightarrow$ Chuyển thành Abstain | **Tăng mạnh:** Tránh bị trừ -1.0 điểm cho các ca không khả thi. |
| **Lọc đơn hủy / trả hàng** | Dùng regex thô theo dòng `tra\|hoan\|huy` | Gọi helper chuẩn Rulebook §1 (loại bỏ cấp đơn hàng) | **Tăng:** Doanh thu tính chuẩn xác từng đồng, không lọc nhầm "trà sữa". |
| **Exemplar Doanh thu** | Code viết tay 30 dòng, bỏ qua helper | Code mẫu 4-5 dòng gọi trực tiếp `revenue(...)` | **Tăng tốc & Giảm lỗi:** LLM không chọn nhầm cột tiền cấp đơn. |
| **Code Hint Ngày tháng** | `df[c] >= pd.Timestamp(...)` gây TypeError | Ép kiểu `clean_date` trước khi so sánh | **Giảm lỗi:** Loại bỏ 100% lỗi so sánh chuỗi với Timestamp. |
| **Không gian Thực thể** | Nhận diện nhầm số lượng/ĐVT ('2 bao', '1 thùng') | Loại bỏ cột số lượng/tiền khỏi candidate | **Tăng độ chuẩn:** Không bị sinh mã lọc nhầm số lượng vào cột tên hàng. |
| **Kích thước Prompt** | Dài ~2.800 token, trùng lặp 5 nơi | Ngắn gọn $\le 1.500$ token, nhất quán | **Tối ưu VRAM & Tốc độ:** Giảm 30-40% độ trễ sinh mã của LLM. |

---

## IV. QUY TRÌNH NGHIỆM THU ĐỊNH LƯỢNG (VERIFICATION PLAN)

Sau khi team chốt phương án, việc nghiệm thu sẽ được đo lường qua các bước cụ thể:

1. **Đo Token Prompt (Trước vs Sau):**
   * Sử dụng tokenizer của mô hình đo đạc trên 5 câu hỏi thuộc các intent khác nhau (trong đó có 1 shop lớn chứa 10 bảng dữ liệu).
   * **Tiêu chí đạt:** Token của System Instruction giảm từ ~2.800 xuống dưới $\le 1.500$ token.
2. **Chạy Benchmark kiểm thử trên 50 câu (Batch 50):**
   * Đo lường số lượng câu trả về kết quả `0` trước và sau chỉnh sửa.
   * Đếm số lượng câu kích hoạt thành công ngoại lệ `CannotAnswer` để chuyển thành `Abstain` hợp lệ.
3. **Kiểm thử hồi quy (Regression Test):**
   * Chạy toàn bộ test suite: bảo đảm **201/201 unit test hiện tại tiếp tục PASS 100%**.

---
*Tài liệu này được lập để team thảo luận và thống nhất trước khi chỉnh sửa trực tiếp vào mã nguồn.*
