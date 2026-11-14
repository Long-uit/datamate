# DATAMATE: QUY TẮC PHÁT TRIỂN KỸ THUẬT VÀ TIÊU CHUẨN THỰC THI (ENGINEERING RULES)

> **Dự án**: DataMate — Zalo AI Challenge 2026
> **Mục tiêu**: Hệ thống Agentic AI hỏi đáp ngôn ngữ tự nhiên tiếng Việt trên dữ liệu bảng phức tạp của doanh nghiệp nhỏ.
> **Tôn chỉ sống còn**: *"Silence is Free, Guessing is Fatal"* (Đúng: +1, Bỏ qua: 0, Sai: -1).

---

## 1. THỐNG NHẤT MÔ HÌNH VÀ PHÂN BỔ CÂN BẰNG 2 GPU (MODEL & 2-GPU BALANCE)

1. **Backbone duy nhất trên toàn hệ thống: `Qwen2.5-Coder-14B-Instruct` (8-bit INT8)**:
   - Để đảm bảo tính tái lập tuyệt đối giữa kết quả tự nộp và lần chạy lại độc lập của Ban Tổ Chức:
     $$\lvert PA_{\text{uploaded}} - PA_{\text{rerun}} \rvert \le 0.03$$
     Toàn bộ hệ thống thống nhất sử dụng **mô hình 14B ở chế độ lượng tử hóa 8-bit (INT8)** trên cả môi trường phát triển (Kaggle) và máy chủ chấm thi của BTC.
   - Tuyệt đối không thay đổi backbone hoặc hạ xuống 7B.

2. **Cân bằng tải tuyệt đối trên 2 GPU (Symmetrical 2-GPU Balanced Allocation)**:
   - Mô hình 14B ở 8-bit có tổng dung lượng trọng số ~14.5 GB.
   - Khi chạy trên 2 GPU (2 × Tesla T4 16GB trên Kaggle hoặc 2 × RTX 5090 32GB trên máy BTC), bắt buộc phân bổ đối xứng hoàn hảo 50/50:
     * **GPU 0**: Gánh `model.embed_tokens` (0.78 GB) + 24 tầng đầu (`model.layers.0` đến `model.layers.23`, ~6.48 GB) $\implies$ **Tổng ~7.26 GB**.
     * **GPU 1**: Gánh 24 tầng sau (`model.layers.24` đến `model.layers.47`, ~6.48 GB) + `model.norm` + `lm_head` (0.78 GB) $\implies$ **Tổng ~7.27 GB**.
   - **Dung lượng VRAM khả dụng còn lại**:
     * Trên Kaggle (T4 15.0 GB): Còn trống **~7.7 GB** trên mỗi GPU $\implies$ Đủ cho Attention SDPA forward và KV-cache 3,584 tokens mà không bị OOM.
     * Trên BTC (RTX 5090 32.0 GB): Còn trống **~24.7 GB** trên mỗi GPU $\implies$ Dư thừa cho 8,192 tokens và batch lớn.
   - **Cấm CPU Offload**: Khi có từ 2 GPU trở lên, tắt hoàn toàn `llm_int8_enable_fp32_cpu_offload=False` để giữ 100% layer trên VRAM, triệt tiêu độ trễ chuyển giao PCIe.

---

## 2. RÀNG BUỘC THỜI GIAN CHẠY: DƯỚI 6 GIỜ CHO 1.000 CÂU (6-HOUR TIME BUDGET)

1. **Ngân sách thời gian**:
   - 6 giờ = $21.600$ giây.
   - Ngân sách trần tuyệt đối cho 1.000 câu: **$\le 21.6$ giây / câu**.
2. **Mục tiêu tốc độ**:
   - Tốc độ trung bình cần đạt: **$3 - 6$ giây / câu** $\implies$ Hoàn thành 1.000 câu trong **1.0 đến 1.8 giờ** (đạt biên an toàn dự phòng $> 4.2$ giờ chống rủi ro).
3. **Các chốt chặn chống nghẽn thời gian (Anti-Bottleneck Guards)**:
   - **Deterministic Feasibility Gate**: Bắt sớm các câu hỏi bất khả thi ngoài kỳ dữ liệu $\rightarrow$ trả về `unanswerable` trong $< 1\text{ ms}$ (0 giây GPU), tiết kiệm tài nguyên cho ~15-25% số câu.
   - **Sandbox Hard Timeout**: Cố định `timeout=15s`. Bất kỳ script nào chạy quá 15s sẽ bị terminate ngay lập tức để tránh treo pipeline.
   - **Giới hạn số vòng Self-Correction**: Tối đa 2 vòng thử lại cho mỗi câu hỏi.
   - **CodeBlockEndStoppingCriteria**: Dừng sinh sớm ngay khi mô hình viết xong khối lệnh `def solution(data):` và lệnh `return`. Decode gia số mỗi 8 tokens thay vì 4 tokens để giảm 50% xung nhịp đồng bộ CPU-GPU.
   - **Cấm xả cache liên tục**: Tuyệt đối **không gọi `torch.cuda.empty_cache()` và `gc.collect()`** trong vòng lặp sinh mã bình thường. Chỉ gọi khi bắt được ngoại lệ `OutOfMemoryError` thực sự.

---

## 3. KỶ LUẬT THỰC NGHIỆM: CẤM VÁ LỖI CỤC BỘ (NO-NAIVE-PATCH DIRECTIVE)

1. **Nghiêm cấm Overfitting thô thiển**:
   - Khi nhận kết quả chạy thực nghiệm (Batch 50 câu, Train/Val split), AI Chuyên gia **TUYỆT ĐỐI KHÔNG** được sửa code bằng cách thêm regex hoặc điều kiện `if/else` chỉ để câu hỏi đó không bị sai khi chạy lại.
2. **Quy chiếu về Taxonomy lỗi khoa học**:
   - Mọi lỗi phải được phân tích và phân loại vào đúng 1 trong 4 tầng:
     * *(a) Lexical & Entity Grounding*: Lỗi từ viết tắt, gõ sai chính tả, từ đồng nghĩa.
     * *(b) Schema & Table Structural*: Lỗi ô gộp, thiếu forward-fill, nhầm sheet POS.
     * *(c) Semantic Parsing / Query Alignment*: Lỗi toán tử nghiệp vụ (Sum vs Count, Mean vs Weighted Avg).
     * *(d) Boundary & Feasibility*: Lỗi phạm vi thời gian hoặc câu hỏi chủ quan thiếu dữ liệu.
3. **Giải pháp phải mang tính tổng quát hóa (Generalizable Invariant)**:
   - Mọi sửa đổi phải dựa trên công thức, tiên đề hoặc cấu trúc Intermediate Representation (QueryPlan) có thể áp dụng cho mọi doanh nghiệp chưa từng thấy (Unseen Data).

---

## 4. KIẾN TRÚC 2 TẦNG (GLOBAL SOTA CORE & CALIBRATED VIETNAMESE LAYER)

1. **Tầng lõi Tổng quát (Core Engine)**:
   - Dựa trên các nguyên lý SOTA quốc tế (DIN-SQL, BIRD, SpreadsheetLLM, REDSQL).
   - Truy vấn qua Intermediate Representation (Typed QueryPlan) hoặc In-Memory Relational Engine (DuckDB/SQLite).
2. **Tầng Bản địa hóa Việt Nam (Vietnamese POS Domain Layer)**:
   - Từ điển thuật ngữ kế toán và khẩu ngữ POS Việt Nam (KiotViet, Sapo, Haravan): `lô`, `két`, `lốc`, `thùng`, `k`, `tr`, `mua chịu`, `ghi sổ`, `trả bớt`, `hàng ế`, `đơn hoàn`.
   - Đối chiếu Lịch Âm Dương (`calendar.csv` và `lunardate`) cho mùa vụ Tết Nguyên Đán.
   - Xử lý lỗi telex/chính tả nhanh qua thuật toán Symmetric Delete (`symspellpy`) trên CPU.
   - **Kỷ luật Overfitting**: Việc tinh chỉnh/hiệu chỉnh sâu dữ liệu đặc thù Việt Nam **chỉ được tiến hành ở pha cuối cùng của lộ trình với liều lượng vừa đủ**, không phá vỡ tính tổng quát của hệ thống.

---

## 5. BẢO VỆ ĐIỂM SỐ THEO THƯỚC ĐO PENALIZED ACCURACY (PA)

1. Thước đo: $PA = \frac{1}{N} \sum_{i=1}^N s_i$ (Đúng: $+1$, Abstain: $0$, Sai: $-1$).
2. Ngưỡng tin cậy hiệu chuẩn tối ưu:
   $$\tau^* = \frac{C_{\text{wrong}}}{C_{\text{correct}} + C_{\text{wrong}}} = \frac{1}{1 + 1} = 0.50$$
3. Mọi câu hỏi có độ tin cậy $P(\text{correct}) < 0.50$ hoặc vi phạm Sanity Check sau 2 lượt sửa lỗi bắt buộc phải chuyển sang `abstain` (0 điểm) để tránh bị trừ 1 điểm.
