# BÁO CÁO CHẨN ĐOÁN VÀ ĐỊNH VỊ NGUYÊN NHÂN LỖI BATCH 50 (DATA MATE DEBUGGING)

---

## 1. TÓM TẮT 5 DÒNG (EXECUTIVE SUMMARY)
* Thực nghiệm 50 câu trên tập train ngẫu nhiên ghi nhận 3 đúng (+1.0), 25 sai (-1.0), 22 từ chối (0.0), đạt điểm Penalized Accuracy (PA) = -0.4400.
* Nhóm 25 câu SAI (-1) bắt nguồn từ 3 điểm nghẽn chính: (1) Lệch mốc thời gian do regex bug và vài-shot làm sai lệch filter; (2) Thiếu từ khóa "hoàn hàng" trong bộ lọc đơn huỷ/trả; (3) Nhầm lẫn Count vs Sum do template few-shot aggregation ép hàm `.sum()`.
* Nhóm 22 câu ABSTAIN (0) chủ yếu do LLM sao chép nguyên mẫu vòng lặp `for name, df in data.items()` từ few-shot thay vì dùng `SmartDataDict` trực tiếp, dẫn đến không tìm thấy bảng và `return None` ngầm (10 câu), hoặc dính lỗi runtime type/index/key (9 câu), và 3 câu dính AST fallback.
* Lá chắn Abstention đã bảo vệ thành công 22 điểm phạt (cứu PA không rơi xuống -0.8800) vì 100% số câu abstain đều thực sự bị hỏng logic/dữ liệu; không có câu đúng nào bị chặn nhầm.
* Phát hiện then chốt: Dữ liệu Excel dạng ô gộp (merged cells) làm mất ngày tháng của các dòng chi tiết nếu không forward-fill (ffill), và `SmartDataDict` đã có sẵn nhưng bị "vô hiệu hóa" bởi chính các ví dụ few-shot trong prompt.

---

## 2. NGUYÊN NHÂN GỐC RỄ THEO CÁC NHÓM A — I (TRUY VẾT SOURCE CODE)

### A. Lệch mốc thời gian (8 câu sai — 32% câu sai)
* **Các câu đại diện:** `q_083211e2c80c`, `q_20ad1fe3cbcd`, `q_026fabde15fc`, `q_766c79feaf8e`, `q_f1fad9500cbd`, `q_5a4149617845`.
* **Vị trí trong mã nguồn:**
  * `src/datamate/grounding_feasibility/temporal.py`:
    * Dòng 321: `re.search(r"t[uừ]\s*đ[aầ]u\s*n[aă]m(\s*(t[oớ]i|đ[eế]n)\s*nay)?", q)`
    * Dòng 236: `re.search(r"\bh[oô]m nay\b|\bng[aà]y m[oố]c\b|\bhnay\b|\bb[uữ]a nay\b", q)`
  * `src/datamate/llm_execution/prompt.py`:
    * Dòng 520 (Few-shot aggregation): `mask = (df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month == 5) & ...`
    * Dòng 773: `temporal_lines.append(f"- Gợi ý lọc Pandas: {temporal_info['code_hint']}")`
* **Tầng gây lỗi (Root Cause Layer):**
  * Tầng (b) — Module tất định: Regex dòng 321 trong `temporal.py` không khớp được các biến thể có chữ "hết", ví dụ `"từ đầu năm đến hết hnay"` (`q_20ad1fe3cbcd`) hay `"từ đầu năm đến hết hôm nay"` (`q_5a4149617845`). Do trượt regex này, biểu thức bị rơi xuống dòng 236 và bắt nhầm chữ `"hnay"`, dẫn đến cửa sổ thời gian bị gán sai thành **DUY NHẤT NGÀY HÔM NAY** (`2026-06-02 đến 2026-06-02`) thay vì từ đầu năm (`2026-01-01 đến 2026-06-02`).
  * Tầng (a) & (e) — Prompt & Few-shot: Trong `prompt.py`, few-shot dạy cú pháp `dt.month == 5`. Khi gặp câu hỏi "quý 1" (`q_083211e2c80c`) hay "quý 2" (`q_026fabde15fc`), LLM sao chép máy móc thành `dt.month == 1` và `dt.month == 2`, bỏ qua `code_hint` chuẩn đã được `temporal.py` tính toán sẵn vì prompt chỉ dán nhãn đây là "Gợi ý" thay vì "Ràng buộc bắt buộc".
* **Đối chiếu câu thực tế:**
  * `q_026fabde15fc`: Câu hỏi "quý 2/2026", LLM sinh: `mask = (df_sales['clean_date'].dt.year == 2026) & (df_sales['clean_date'].dt.month == 2)` $\rightarrow$ Dự đoán: `281,466,500` vs Gold: `518,445,500`.

---

### B. Quên loại trừ đơn Hủy / Trả / Hoàn khi tính doanh thu (4 câu sai — 16% câu sai)
* **Các câu đại diện:** `q_491041bd1d39`, `q_ee2a9e668ccc`, `q_222e5130802b`, `q_5950425c2059`.
* **Vị trí trong mã nguồn:**
  * `src/datamate/llm_execution/prompt.py`:
    * Dòng 515–517 (Few-shot aggregation):
      ```python
      status_col = next((c for c in cols_s if any(k in str(c).lower() for k in ['trạng thái', 'status', 'ghi chú tt', 'tình trạng'])), None)
      if status_col:
          df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains('hủy|huỷ|trả|cancel')]
      ```
    * Dòng 565–567 (Few-shot ranking): Tương tự.
* **Tầng gây lỗi (Root Cause Layer):**
  * Tầng (a) & (c) — Prompt pattern thiếu sót & Helper không can thiệp:
    * Khảo sát thực tế dữ liệu bảng `DonHang_ChiTiet` tại `biz_102`, `biz_126`: cột `Trạng thái đơn hàng` chứa các giá trị thực tế: `['Đã hoàn thành', 'Đã hoàn hàng', 'Đã hủy', 'Đang giao dịch']`.
    * Chuỗi regex `'hủy|huỷ|trả|cancel'` trong few-shot **HOÀN TOÀN BỎ SÓT TỪ KHÓA "HOÀN HÀNG" / "HOÀN"**.
    * Các đơn bị khách trả lại có trạng thái `"Đã hoàn hàng"` không bị loại bỏ, dẫn đến doanh thu tính toán bị cộng dôi đúng bằng giá trị các đơn hoàn trả (chênh lệch từ vài nghìn đến 20 triệu đồng).
* **Đối chiếu câu thực tế:**
  * `q_222e5130802b`: Doanh thu tháng 2/2025 tại `biz_126`. Dự đoán: `455,194,500` vs Gold: `435,686,000` (dôi đúng 19,508,500đ từ các đơn có trạng thái "Đã hoàn hàng").

---

### C. Logic nghiệp vụ đặc thù: Sổ nợ, Hàng ế, Giá nhập bình quân, Lũy kế (4 câu sai — 16% câu sai)
* **Các câu đại diện:** `q_c06729907fcc`, `q_8aa3aaf65ac7`, `q_18a4f2eb5280`, `q_1b118bb533ea`.
* **Vị trí trong mã nguồn:**
  * `src/datamate/llm_execution/prompt.py`:
    * Dòng 116–122 (`classify_intent`): Danh sách từ khóa `cong_no` thiếu `"trả nợ"`, `"thu nợ"`, `"mua chịu"`, `"trả bớt"`.
    * Dòng 416–454 (Few-shot `cong_no`): Chỉ minh họa đếm số khách nợ (`nunique`), không minh họa cách tính số tiền khách đã trả nợ.
* **Tầng gây lỗi (Root Cause Layer):**
  * Tầng (a) & (b) — Prompt classification & Thiếu logic chuyên biệt:
    * `q_c06729907fcc` ("tiền khách trả bowts nợ các đơn mua chịu"): Do có chữ `"mua chịu"` và `"trả bowts nợ"`, `classify_intent` không khớp được từ khóa nào nên rơi về `aggregation`. LLM nhận few-shot tính tổng doanh thu bán hàng (`df_sales.sum()`), cho ra kết quả `121,716,500` thay vì tra cứu cột "Tiền đã trả" trong sổ công nợ (Gold = `4,598,548`).
    * `q_8aa3aaf65ac7` ("mấy mặt hàng ế, bán ko được cái nào"): Không có intent "unsold_products". LLM sinh `len(df_sales[mask])` (đếm số giao dịch thành công) thay vì lấy hiệu số giữa `Danh sách sản phẩm` và `Sản phẩm có phát sinh bán`.
    * `q_18a4f2eb5280` ("giá nhập bình quân 1 cây"): LLM sinh `df['clean_amt'].mean()` thay vì `sum(clean_amt) / sum(clean_qty)`. Giá trị trung bình của cột thành tiền trên mỗi dòng đơn nhập không phải là đơn giá bình quân trên mỗi đơn vị hàng hóa.

---

### D. Nhầm lẫn giữa Đếm (Count/Số lượng) và Tính tổng tiền (Sum) (3 câu sai — 12% câu sai)
* **Các câu đại diện:** `q_cc3e3994a1d7`, `q_99a0f6d709bd`, `q_edc6c6cd6326`.
* **Vị trí trong mã nguồn:**
  * `src/datamate/llm_execution/prompt.py`:
    * Dòng 145: Mọi câu hỏi không chứa từ khóa top/tỷ lệ đều rơi vào intent `"aggregation"`.
    * Dòng 521: Ví dụ mẫu của `aggregation` cố định kết quả: `return int(round(df_sales[mask]['clean_amt'].sum()))`.
* **Tầng gây lỗi (Root Cause Layer):**
  * Tầng (e) — Prompt Exemplar Bank quá cứng nhắc:
    * Khi câu hỏi hỏi rõ ràng: *"bị huỷ mấy đơn?"* (`q_cc3e3994a1d7`), *"bán được bao nhiêu đơn hàng?"* (`q_99a0f6d709bd`), *"Số lon bán được hôm qua là bao nhiêu"* (`q_edc6c6cd6326`), intent vẫn bị gán là `aggregation`.
    * LLM học vẹt từ dòng 521 và luôn gọi `.sum()` trên cột tiền thay vì gọi `len()`, `nunique('Mã đơn hàng')`, hoặc `sum(clean_qty)`.
* **Đối chiếu câu thực tế:**
  * `q_cc3e3994a1d7`: Hỏi "mấy đơn huỷ". LLM tính tổng tiền các đơn huỷ: `325,196,800` vs Gold: `49` (đơn).

---

### E. Entity Linking trượt chuỗi & Quy cách (3 câu sai — 12% câu sai)
* **Các câu đại diện:** `q_2087fd52f66d`, `q_689b129e020c`, `q_d2b32a2c57d8`.
* **Vị trí trong mã nguồn:**
  * `src/datamate/grounding_feasibility/entity_linker.py`:
    * Dòng 80–120: `extract_candidates_from_business` chỉ trích xuất danh từ riêng mặt hàng, không trích xuất quy cách / thuộc tính như `"size L"`, `"5L"`, `"12kg"`.
  * `src/datamate/llm_execution/prompt.py`:
    * Dòng 809–816: Format tiêm entity vào prompt chỉ hiển thị danh sách dạng văn bản, không ép buộc cấu trúc code lọc.
* **Tầng gây lỗi (Root Cause Layer):**
  * Tầng (b) — Module Entity Linker bỏ sót thuộc tính:
    * `q_2087fd52f66d` hỏi *"số ly size L"*: "size L" là hậu tố quy cách trong tên đồ uống (ví dụ `Trà đào (L)`). Entity Linker không bắt được "size L", prompt không có gợi ý, LLM sinh code tính tổng doanh thu toàn cửa hàng và bỏ qua lọc size L.
    * `q_689b129e020c` ("Sơn lót Jotun Jotashield chống kiềm 5L"): LLM tự viết `filtered_df['Sản phẩm'].str.contains(...)`. Tên cột thực tế là `'Tên sản phẩm'`, code văng KeyError hoặc khớp 0 dòng, trả về 0.

---

### F. Sai công thức % và Sai kiểu output List vs Scalar (3 câu sai — 12% câu sai)
* **Các câu đại diện:** `q_b218cee27fe9`, `q_e9a29330a629`, `q_313dfc683558`.
* **Vị trí trong mã nguồn:**
  * `src/datamate/llm_execution/prompt.py`:
    * Dòng 708: `elif any(k in q_low for k in ["tăng liên tục", "so với", "thay đổi bao nhiêu", "tăng trưởng"]): example = EXEMPLAR_BANK.get("time_series")`
    * Dòng 677–687: Few-shot `time_series` tính so sánh giữa tháng này và tháng trước `((rev_curr - rev_prev) / rev_prev) * 100`.
* **Tầng gây lỗi (Root Cause Layer):**
  * Tầng (a) & (e) — Heuristic chọn few-shot sai lệch:
    * `q_b218cee27fe9` hỏi *"So với ca sáng, số đơn ca chiều tháng 4/2025 chênh bao nhiêu %?"*. Do câu có từ `"so với"`, hàm `retrieve_dynamic_few_shot` nạp ví dụ so sánh tháng trước - tháng này. LLM sao chép mã tính doanh thu tháng 4 so với tháng 3, thay vì so sánh ca sáng với ca chiều trong cùng tháng 4.
    * `q_313dfc683558` hỏi *"Liệt kê doanh thu 3 tháng liên tiếp từ tháng 2/2025 đến tháng 4/2025 theo thứ tự thời gian"*. Prompt không có bất kỳ ví dụ nào trả về kiểu `list`. LLM mặc định cộng gộp doanh thu 3 tháng thành 1 số nguyên `424,898,800` (Gold: `[337066700, 266675100, 263443400]`).

---

### G. Code dò tên bảng cứng nhắc bằng vòng lặp `data.items()` rồi `return None` (10 câu abstain — 45.5% abstain)
* **Các câu đại diện:** `q_f969bd7ed482`, `q_db64c1b7436d`, `q_52dca90024ce`, `q_f490b558605d`, `q_94bfa97928af`, `q_6902a9f52492`, `q_252244893f6d`, `q_44e61088806a`, `q_d69e9bae8064`, `q_42f415d692be`.
* **Vị trí trong mã nguồn:**
  * `src/datamate/llm_execution/prompt.py`:
    * Dòng 498–509 (Few-shot `aggregation`):
      ```python
      for name, df in data.items():
          n_clean = re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())
          if any(k in n_clean for k in ['nhap', 'kho', 'chiphi', 'ncc', 'tonkho']):
              continue
          cols = df.columns.tolist()
          d_c = next((c for c in cols if any(k in str(c).lower() for k in ['ngày', 'date', 'ngaylap', 'thời gian'])), None)
          a_c = next((c for c in cols if any(k in str(c).lower() for k in ['thành tiền', 'tổng tiền', 'tiền bán', 'doanh thu', 'tiền']) and 'thuế' not in str(c).lower()), None)
          if d_c and a_c:
              df_sales = df.copy(); date_col = d_c; amt_col = a_c; break
      if df_sales is None:
          raise DataNotFoundError(...)
      ```
    * Dòng 845: `3. Tìm bảng cụ thể, tìm cột ngày gốc bằng d_c = next(...)`
  * `src/datamate/llm_execution/worker.py`:
    * Dòng 29–71 (`SmartDataDict`): Hỗ trợ truy cập mềm dẻo `data['ban_hang']` nhưng **KHÔNG ghi đè phương thức `.items()`**.
* **Tầng gây lỗi (Root Cause Layer):**
  * Tầng (e) & (d) — Vòng lặp mẫu phản tác dụng & Triệt tiêu `SmartDataDict`:
    * LLM được dạy trong mọi few-shot phải viết vòng lặp quét qua `data.items()`. Khi gặp các shop có file tên là `ban_hang.csv`, `SoBanHang`, `chi_tiet_ban_hang`, hoặc bảng bị gán mã `t_01`, điều kiện lọc tên bảng hoặc lọc cột trong `next(...)` không khớp.
    * Khi không thấy bảng, code văng `DataNotFoundError` hoặc khối `try...except` ngầm bắt được và thực thi `return None`.
    * Khi hàm `solution()` trả về `None`, Normalizer và Abstention Gate lập tức ép về `ABSTAIN` (0 điểm).

---

### H. Sandbox Runtime Crashes: KeyError, TypeError, ValueError, IndexError (9 câu abstain — 40.9% abstain)
* **Các câu đại diện:** `q_e4fe38fbebb9`, `q_b42ecb762c43`, `q_e69dcf0740d1`, `q_14eca92559aa`, `q_9984c1acf035`, `q_7940a4484419`, `q_a98ebd61ce5e`, `q_4dd228e342c3`, `q_2d2d91435d5d`.
* **Vị trí trong mã nguồn:**
  * `src/datamate/llm_execution/sandbox.py`:
    * Dòng 452 (`clean_num`): Hoạt động tốt nhưng LLM không gọi mà gọi thẳng `.sum()` trên Series string.
    * Dòng 542 (`clean_date`): Hoạt động tốt nhưng LLM dùng `.dt` trực tiếp trên cột gốc chưa qua `clean_date`.
  * `src/datamate/grounding_feasibility/temporal.py`:
    * Dòng 581: `code_hint` sinh cú pháp `df[date_col].dt.date >= pd.to_datetime(...).date()`. Trong Pandas $\ge$ 2.0, nếu cột là `datetime64[us]` mà so sánh với `date` object sẽ ném `TypeError: Invalid comparison between dtype=datetime64[us] and date`.
* **Tầng gây lỗi (Root Cause Layer):**
  * Tầng (c) & (a) — Thiếu phòng vệ runtime & Gợi ý code không tương thích Pandas 2.0+:
    * `q_e69dcf0740d1`: Cột tiền chứa chuỗi format, LLM không gọi `clean_num` mà gọi `.sum()`, biến cột thành 1 chuỗi ký tự khổng lồ; dòng sau chia cho `len(df)` gây lỗi `TypeError: unsupported operand type(s) for /: 'str' and 'int'`.
    * `q_14eca92559aa`: LLM gọi `int(round(df['clean_amt'].mean()))`. Khi DataFrame lọc rỗng, `.mean()` trả về `np.nan`; ép kiểu `int(nan)` văng `ValueError: cannot convert float NaN to integer`.
    * `q_e4fe38fbebb9`: Hard-code `df['Khách']` thay vì dùng biến tìm kiếm cột khách hàng $\rightarrow$ `KeyError: 'Khách'`.
    * `q_9984c1acf035`: Gọi `grp.iloc[0]` trên bảng rỗng $\rightarrow$ `IndexError: list index out of range`.

---

### I. AST Fallback an toàn sau khi Retry vẫn lỗi cú pháp (3 câu abstain — 13.6% abstain)
* **Các câu đại diện:** `q_1b211d642140`, `q_afedc107ddb1`, `q_93d4030bafe4`.
* **Vị trí trong mã nguồn:**
  * `src/datamate/llm_execution/client.py`:
    * Dòng 465–471: Prompt retry chỉ gửi lại mã lỗi và yêu cầu viết lại, **hoàn toàn không đính kèm schema rút gọn hoặc ngữ cảnh thời gian**.
    * Dòng 485–492:
      ```python
      if not is_valid:
          code = (
              "def solution(data):\n"
              "    # Fallback an toàn khi mã sinh ra không đạt chuẩn cú pháp\n"
              "    return None\n"
          )
      ```
* **Tầng gây lỗi (Root Cause Layer):**
  * Tầng (d) — Cơ chế retry trong `client.py` thiếu ngữ cảnh: Lượt 1 sinh mã bị lỗi cú pháp AST; lượt 2 thử sửa lại nhưng prompt retry bị trơ trọi thông tin khiến mô hình tiếp tục sinh hỏng cú pháp. Cơ chế an toàn kích hoạt trả về `return None` để bảo vệ điểm.

---

## 3. RỦI RO CHÉO PHÁT HIỆN THÊM (CROSS-SYSTEM RISKS)

1. **Hiệu ứng ô gộp Excel (Merged Cells) làm rơi rụng dữ liệu chi tiết đơn:**
   * Trong các file Excel chi tiết hóa đơn (như `DonHang_ChiTiet.xlsx` ở `biz_102`, `biz_103`), ngày bán và mã đơn chỉ xuất hiện ở dòng đầu tiên của đơn; các mặt hàng thứ 2, 3 trong cùng đơn bị để trống (`NaN`).
   * Nếu mã nguồn của LLM tự lọc ngày trước khi forward-fill (`ffill`), **toàn bộ các dòng sản phẩm thứ 2 trở đi bị xóa sạch**. Đây là lý do khiến doanh thu tính ra thường xuyên bị thiếu hụt một nửa so với Gold nếu code không gọi `ffill`.
2. **Khả năng tương thích kiểu ngày của Pandas 2.0+:**
   * Chuỗi gợi ý `code_hint` hiện tại sinh ra: `pd.to_datetime(...).date()`. So sánh giữa `Series[datetime64]` và `datetime.date` trong Pandas mới sẽ gây crash ngay lập tức (`Invalid comparison between dtype=datetime64[us] and date`). Cần chuẩn hóa so sánh trực tiếp dạng Timestamp: `pd.to_datetime('YYYY-MM-DD')`.
3. **Tuân thủ quy chế cuộc thi (Competition Integrity Check):**
   * Đã quét toàn bộ `src/`: **100% không có hardcode `question_id`, `business_id`** hay logic gian lận.
   * `as_of_date` không bị hardcode trong source mà được nạp động từ `shops.json`.
4. **Độ an toàn của Helper `clean_num`:**
   * Kiểm thử thực tế xác nhận `clean_num` xử lý hoàn hảo mọi định dạng: `"1.234.000đ"`, `"(500.000đ)"`, `"1.5 triệu"`, `"500k"`. Vấn đề duy nhất là LLM... quên gọi `clean_num` mà gọi thẳng phép toán số học trên Series thô.

---

## 4. KẾ HOẠCH SỬA THEO THỨ TỰ ƯU TIÊN (ACTION PLAN)
Ưu tiên giải pháp **tất định (deterministic python code) trong worker/helper và tiền xử lý** hơn là chỉ trông chờ vào việc sửa prompt.

---

### ƯU TIÊN 1 (P0): Khắc phục lỗi Regex Thời gian & Buộc dùng Temporal Window
* **File/Hàm:** `src/datamate/grounding_feasibility/temporal.py` (`resolve_temporal`).
* **Mô tả thay đổi:**
  * Mở rộng regex tại dòng 321 để bắt trọn mọi biến thể: `r"t[uừ]\s*đ[aầ]u\s*n[aă]m.*?(?:nay|hnay|h[oô]m\s*nay)"`.
  * Sửa chuỗi `code_hint` tại dòng 581, 598: Bỏ `.date()`, dùng so sánh Timestamp chuẩn Pandas:
    `# Gợi ý: (df[date_col] >= pd.to_datetime('{start}')) & (df[date_col] <= pd.to_datetime('{end} 23:59:59'))`.
* **Pseudo-diff:**
  ```python
  # src/datamate/grounding_feasibility/temporal.py
  - if re.search(r"t[uừ]\s*đ[aầ]u\s*n[aă]m(\s*(t[oớ]i|đ[eế]n)\s*nay)?", q):
  + if re.search(r"t[uừ]\s*đ[aầ]u\s*n[aă]m.*?(?:nay|hnay|h[oô]m\s*nay)", q):
  ```
* **Rủi ro regression:** Cực thấp (chỉ sửa regex nhận diện khoảng ngày).
* **Độ khó:** S (Dễ).

---

### ƯU TIÊN 2 (P0): Bổ sung từ khóa "hoàn hàng" vào Rulebook & Bộ lọc Huỷ/Trả
* **File/Hàm:** `src/datamate/llm_execution/prompt.py` (tất cả các few-shot exemplars) & `src/datamate/grounding_feasibility/temporal.py` (`filter_future_data`).
* **Mô tả thay đổi:**
  * Cập nhật regex trạng thái: thay thế `r'hủy|huỷ|trả|cancel'` bằng `r'hủy|huỷ|trả|hoàn|cancel|return'`.
  * Trong prompt hướng dẫn (dòng 845), thêm điều luật cứng: "Khi tính doanh thu hoặc số đơn bán thành công, BẮT BUỘC lọc bỏ các đơn chứa chữ 'hủy', 'huỷ', 'trả', 'hoàn', 'cancel'."
* **Pseudo-diff:**
  ```python
  # src/datamate/llm_execution/prompt.py
  - df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains('hủy|huỷ|trả|cancel')]
  + df_sales = df_sales[~df_sales[status_col].astype(str).str.lower().str.contains('hủy|huỷ|trả|hoàn|cancel|return')]
  ```
* **Rủi ro regression:** Không có. Quy chuẩn kế toán luôn loại trừ hàng hoàn/trả.
* **Độ khó:** S (Dễ).

---

### ƯU TIÊN 3 (P1): Sửa Few-shot Prompt để dập tắt vòng lặp `data.items()` và kích hoạt `SmartDataDict`
* **File/Hàm:** `src/datamate/llm_execution/prompt.py` (`EXEMPLAR_BANK`).
* **Mô tả thay đổi:**
  * Sửa các ví dụ minh họa trong `prompt.py`: Thay thế vòng lặp tìm bảng phức tạp bằng cách gọi trực tiếp:
    `df_sales = data.get('ban_hang') or data.get('t_02') or ...` kết hợp hàm trợ giúp tìm bảng tự động `get_main_table(data)`.
  * `SmartDataDict` tại `src/datamate/llm_execution/worker.py` bổ sung phương thức `get_table(keywords)` để code của LLM chỉ cần 1 dòng: `df_sales = data.get_sales_table()`.
* **Rủi ro regression:** Thấp. Giải phóng cho 10 câu đang bị kẹt `return None`.
* **Độ khó:** M (Trung bình).

---

### ƯU TIÊN 4 (P1): Tách biệt Intent Count vs Sum & Ngăn chặn lỗi chia cho 0 / NaN
* **File/Hàm:** `src/datamate/llm_execution/prompt.py` (`classify_intent`, `build_dynamic_system_instruction`).
* **Mô tả thay đổi:**
  * Bổ sung intent `count_query` khi câu hỏi chứa: `"mấy đơn"`, `"bao nhiêu đơn"`, `"số lượng đơn"`, `"số đơn"`, `"mấy lon"`, `"bao nhiêu lon"`, `"mấy ly"`.
  * Khi intent là `count_query`, cấm sinh `.sum()` trên cột tiền, bắt buộc dùng `len()` hoặc `nunique()` hoặc `.sum()` trên cột số lượng.
  * Cung cấp tiện ích an toàn `safe_int(val)` trong worker để xử lý `NaN` thành 0 thay vì văng `ValueError`.
* **Rủi ro regression:** Thấp.
* **Độ khó:** M (Trung bình).

---

### ƯU TIÊN 5 (P2): Chuẩn hóa Entity Linking cho Thuộc tính & Quy cách (size, dung tích)
* **File/Hàm:** `src/datamate/grounding_feasibility/entity_linker.py`.
* **Mô tả thay đổi:**
  * Trích xuất thêm các pattern quy cách vào candidate list: `\b(size\s*[smlxl]+|\d+kg|\d+ml|\d+l)\b`.
  * Tiêm code snippet lọc cụ thể vào prompt thay vì chỉ in chuỗi text.
* **Rủi ro regression:** Thấp.
* **Độ khó:** M (Trung bình).

---

## 5. PREDICTED OUTPUT (DỰ ĐOÁN ĐIỂM PA SAU KHI SỬA)

### Bảng dự kiến chuyển đổi trạng thái theo nhóm lỗi:

| Nhóm can thiệp | Số câu can thiệp | Dự kiến chuyển trạng thái | Mức tự tin | Lý do kỹ thuật căn cứ từ log |
| :--- | :---: | :--- | :---: | :--- |
| **Nhóm A (Sửa Regex & Filter thời gian)** | 8 câu sai | 5 câu SAI $\rightarrow$ ĐÚNG, 3 câu giữ nguyên | **Cao** | Regex khớp đúng `từ đầu năm đến nay` và sửa `dt.month == 2` thành khoảng quý 2 sẽ sửa trực tiếp `q_20ad1fe3cbcd`, `q_026fabde15fc`, `q_083211e2c80c`. |
| **Nhóm B (Thêm từ khóa "hoàn hàng")** | 4 câu sai | 3 câu SAI $\rightarrow$ ĐÚNG, 1 câu giữ nguyên | **Rất cao** | Sai lệch ở `q_491041bd1d39`, `q_222e5130802b`, `q_5950425c2059` lệch đúng bằng số tiền các đơn "Đã hoàn hàng". |
| **Nhóm D (Tách Count vs Sum)** | 3 câu sai | 2 câu SAI $\rightarrow$ ĐÚNG, 1 câu giữ nguyên | **Cao** | Khắc phục triệt để câu hỏi "mấy đơn" (`q_cc3e3994a1d7`, `q_99a0f6d709bd`). |
| **Nhóm G (Mở khóa SmartDataDict cho 10 câu None)**| 10 câu abstain | 4 câu ABSTAIN $\rightarrow$ ĐÚNG, 5 câu giữ ABSTAIN, 1 câu $\rightarrow$ SAI | **Vừa** | Giúp lấy được bảng dữ liệu. Giữ chốt chặn kiểm tra rỗng để tránh chuyển thành SAI (-1). |
| **Nhóm H (Phòng ngừa Sandbox crash - NaN, kiểu str)**| 9 câu abstain | 3 câu ABSTAIN $\rightarrow$ ĐÚNG, 6 câu giữ ABSTAIN | **Vừa** | Xử lý `safe_int(mean)` và gọi `clean_num` trước khi chia. |
| **Nhóm C, E, F (Logic nghiệp vụ, entity, list)** | 10 câu sai | 2 câu SAI $\rightarrow$ ĐÚNG, 8 câu giữ nguyên | **Thấp** | Cần prompt tuning sâu hơn. |

---

### Dự báo điểm Penalized Accuracy (PA) trên tập 50 câu:

* **Kịch bản Thận trọng (Conservative):**
  * Chuyển đổi: 7 câu Sai $\rightarrow$ Đúng; 3 câu Abstain $\rightarrow$ Đúng; 1 câu Abstain $\rightarrow$ Sai.
  * Phân bổ mới: Đúng = 13 (26%), Sai = 19 (38%), Abstain = 18 (36%).
  * **PA dự kiến:** `(13 - 19) / 50 =` **-0.1200** (Tăng **+0.3200** so với hiện tại).
* **Kịch bản Kỳ vọng (Expected - Khả thi nhất):**
  * Chuyển đổi: 10 câu Sai $\rightarrow$ Đúng; 6 câu Abstain $\rightarrow$ Đúng; 0 câu Abstain $\rightarrow$ Sai.
  * Phân bổ mới: Đúng = 19 (38%), Sai = 15 (30%), Abstain = 16 (32%).
  * **PA dự kiến:** `(19 - 15) / 50 =` **+0.0800** (Vượt qua mốc âm, chuyển sang điểm DƯƠNG).
* **Kịch bản Lạc quan (Optimistic):**
  * Chuyển đổi: 13 câu Sai $\rightarrow$ Đúng; 8 câu Abstain $\rightarrow$ Đúng; 0 câu Abstain $\rightarrow$ Sai.
  * Phân bổ mới: Đúng = 24 (48%), Sai = 12 (24%), Abstain = 14 (28%).
  * **PA dự kiến:** `(24 - 12) / 50 =` **+0.2400** (Tăng **+0.6800** so với hiện tại).

---

### Thứ tự ưu tiên theo Điểm PA tăng thêm trên mỗi giờ công (PA Gain / Man-Hour):
1. **Ưu tiên 1: Sửa regex thời gian trong `temporal.py` + Bổ sung từ khóa `"hoàn"` vào bộ lọc đơn hủy/trả**
   * Ước tính công: **1.0 giờ**.
   * Điểm PA tăng dự kiến: **+0.2400** (sửa được ~6 câu sai thành đúng, mỗi câu mang lại +2 điểm chênh lệch).
   * **Hiệu suất: 0.2400 PA / giờ**.
2. **Ưu tiên 2: Bổ sung intent `count_query` trong `prompt.py` (ngăn cấm gọi sum trên câu hỏi đếm)**
   * Ước tính công: **0.5 giờ**.
   * Điểm PA tăng dự kiến: **+0.0800** (sửa được 2 câu sai nặng thành đúng).
   * **Hiệu suất: 0.1600 PA / giờ**.
3. **Ưu tiên 3: Xóa bỏ vòng lặp `data.items()` trong few-shot, thay bằng truy cập trực tiếp qua `SmartDataDict`**
   * Ước tính công: **1.5 giờ**.
   * Điểm PA tăng dự kiến: **+0.1600** (mở khóa 4 câu abstain thành đúng).
   * **Hiệu suất: 0.1067 PA / giờ**.
4. **Ưu tiên 4: Bổ sung wrapper an toàn `safe_int()` và tự động bọc `clean_num` trong Worker**
   * Ước tính công: **1.0 giờ**.
   * Điểm PA tăng dự kiến: **+0.0800**.
   * **Hiệu suất: 0.0800 PA / giờ**.

---

### Biện pháp phòng ngừa: Ngăn chặn câu Abstain biến thành câu SAI (-1):
* Khi mở khóa 10 câu đang trả về `None` do lỗi tìm bảng, có nguy cơ mô hình sẽ tính toán ẩu và sinh ra một đáp án sai, khiến hệ thống bị **mất thêm 1 điểm phạt (-1)** thay vì an toàn ở mức 0 điểm.
* **Cơ chế khóa an toàn đề xuất:**
  * Trong `normalizer.py`, nếu kết quả tính ra bằng `0` hoặc số âm trên các câu hỏi doanh thu / số lượng, BẮT BUỘC coi là Sanity Check Thất bại $\rightarrow$ Ép về `ABSTAIN`.
  * Nếu độ che phủ thực thể (Grounding Coverage) nhỏ hơn 0.30 trên câu hỏi có chứa tên sản phẩm cụ thể $\rightarrow$ Ép về `ABSTAIN`.

---

## 6. CÂU HỎI CẦN BẠN QUYẾT ĐỊNH

1. **Về chiến lược sửa mã:** Bạn có đồng ý ưu tiên triển khai ngay **Gói can thiệp nhanh P0** (sửa regex thời gian trong `temporal.py` và thêm từ khóa `"hoàn"` vào bộ lọc trạng thái đơn trong `prompt.py` & `temporal.py`) trước để kiểm chứng mức tăng điểm PA ngay lập tức không?
2. **Về cơ chế SmartDataDict:** Bạn muốn chúng tôi sửa trực tiếp các ví dụ mẫu (Few-shot Exemplar) trong `prompt.py` để LLM dùng `data['tên_bảng']`, hay viết thêm một helper hàm tất định `get_sales_df(data)` chèn sẵn vào global namespace của worker?
