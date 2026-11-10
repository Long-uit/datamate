# 📘 HƯỚNG DẪN ĐỔI MÔ HÌNH GIỮA 7B VÀ 14B (CHẠY TEST & NỘP BÀI)
> **Dự án**: DataMate — Zalo AI Challenge 2026 (Chặng 4)  
> **Hai mô hình trọng tâm**:
> * `Qwen/Qwen2.5-Coder-7B-Instruct`
> * `Qwen/Qwen2.5-Coder-14B-Instruct`

---

## 1. Cơ Chế Tự Động Thích Ứng Của Hệ Thống (Giải Đáp Thắc Mắc)

> **Hỏi**: *Model của mình khi đổi từ 7B sang 14B (hoặc ngược lại) thì có tự động chạy theo những cấu hình phù hợp với model đó không?*

### 👉 **CÂU TRẢ LỜI: CÓ, HOÀN TOÀN TỰ ĐỘNG 100%!**

Vì cả hai mô hình **7B** và **14B** đều thuộc cùng dòng kiến trúc mã nguồn đỉnh cao **`Qwen2.5-Coder`**, toàn bộ kiến trúc của hệ thống DataMate đã được thiết kế sẵn sàng để tự thích ứng động:

1. **Chuẩn hóa Prompt & Chat Template**: Hệ thống nạp trực tiếp Chat Template của mô hình (`tokenizer.apply_chat_template`), tự động ánh xạ đúng các token đặc biệt (`<|im_start|>`, `<|im_end|>`) và vai trò `system / user / assistant` mà không cần sửa code.
2. **Điểm dừng sinh thông minh (`CodeBlockEndStoppingCriteria`)**: Tự động ngắt sinh ngay khi mô hình đóng khối mã `def solution(data)` và ký tự ` ``` `, áp dụng đồng nhất cho cả 7B và 14B giúp tiết kiệm VRAM và tăng tốc độ suy luận gấp 15–30 lần.
3. **Phân bổ GPU Động (`device_map="auto"`)**:
   * Khi nạp **7B**: Tốn ít VRAM hơn (~7.5GB ở 8-bit), hệ thống tự nạp gọn trong 1 GPU hoặc chia đều 2 GPU.
   * Khi nạp **14B**: Trọng số lớn hơn (~14.7GB ở 8-bit), hệ thống tự động phân mảnh đều sang cả 2 GPU (ví dụ trên Kaggle GPU T4 x 2: mỗi GPU chỉ chịu ~7.4GB VRAM, hoàn toàn tránh lỗi CUDA OOM).
4. **Bộ kiểm duyệt AST & Hộp cát Sandbox an toàn**: Chạy độc lập ở tầng ngoài để kiểm tra tính hợp lệ cú pháp Python, thực thi tính toán trên dữ liệu cửa hàng, bắt lỗi runtime và kích hoạt tự sửa lỗi (Self-Correction).
5. **Cổng từ chối Calibrated Abstention ($\tau^* = 0.50$)**: Ngưỡng độ tin cậy được thiết kế bất biến theo luật thi đấu, tối đa hóa điểm Penalized Accuracy (PA) cho bất kỳ mô hình nào.

> ⚠️ **Lưu ý duy nhất về phần cứng (VRAM)**:
> * Trên **Kaggle (GPU T4 x 2 = 30GB VRAM)**: Cả **7B** và **14B** đều chạy mạnh nhất ở chế độ **8-bit** (`QUANTIZATION = "8bit"`).
> * Trên **Google Colab Free (chỉ có 1 GPU T4 = 16GB VRAM)**:
>   * Nếu chọn **7B**: Chạy thoải mái ở cả **8-bit** (~7.5GB) lẫn **4-bit** (~4.5GB).
>   * Nếu chọn **14B**: Khuyên dùng **4-bit** (`QUANTIZATION = "4bit"`, tốn ~9GB VRAM) để không bị chạm trần bộ nhớ khi sinh context dài.

---

## 2. Bảng Tra Cứu Nhanh Tất Cả Các Vị Trí Cần Chỉnh

Dưới đây là danh sách đầy đủ tất cả các vị trí trong dự án cho từng nhu cầu:

| Tình huống / Môi trường | File cần chỉnh | Vị trí / Dòng | Giá trị cần đổi (7B hoặc 14B) |
| :--- | :--- | :--- | :--- |
| **Kaggle Notebook** (Cả Train & Public Test) | [`colab/Datamate_kaggle.ipynb`](file:///d:/Company/Agentic%20AI/datamate/colab/Datamate_kaggle.ipynb) | **Cell 1** (Ô cấu hình) | `MODEL_ID = "Qwen/Qwen2.5-Coder-14B-Instruct"`<br>hoặc `"Qwen/Qwen2.5-Coder-7B-Instruct"` |
| **Google Colab Notebook** (Cả Train & Public Test) | [`colab/DataMate_Colab.ipynb`](file:///d:/Company/Agentic%20AI/datamate/colab/DataMate_Colab.ipynb) | **Cell 1** (Ô cấu hình) | `MODEL_ID = "Qwen/Qwen2.5-Coder-14B-Instruct"`<br>hoặc `"Qwen/Qwen2.5-Coder-7B-Instruct"` |
| **Chạy kiểm thử / Train bằng CLI** | [`tests/inspect_pipeline.py`](file:///d:/Company/Agentic%20AI/datamate/tests/inspect_pipeline.py) | Tham số CLI `--model_id`<br>hoặc Dòng `2597` | Thêm cờ `--model_id "Qwen/Qwen2.5-Coder-14B-Instruct"` |
| **Chạy sinh kết quả nộp bài bằng CLI** | [`predict.py`](file:///d:/Company/Agentic%20AI/datamate/predict.py) | Tham số CLI `--model_id`<br>hoặc Dòng `243` | Thêm cờ `--model_id "Qwen/Qwen2.5-Coder-14B-Instruct"` |
| **Cấu hình mặc định toàn dự án (YAML)** | [`config/default.yaml`](file:///d:/Company/Agentic%20AI/datamate/config/default.yaml) | Dòng `4` | `model_id: "Qwen/Qwen2.5-Coder-14B-Instruct"` |
| **Cấu hình Python DataClass** | [`src/datamate/config.py`](file:///d:/Company/Agentic%20AI/datamate/src/datamate/config.py) | Dòng `23` | `model_id: str = "Qwen/Qwen2.5-Coder-14B-Instruct"` |
| **Đóng gói Docker nộp bài offline** | [`Dockerfile`](file:///d:/Company/Agentic%20AI/datamate/Dockerfile) | Dòng `43` | `ARG BASE_MODEL_ID="Qwen/Qwen2.5-Coder-14B-Instruct"` |
| **Biến môi trường toàn hệ thống** | Terminal OS / Docker | Môi trường runtime | `export DATAMATE_MODEL_ID="Qwen/Qwen2.5-Coder-14B-Instruct"` |

---

## 3. Hướng Dẫn Chi Tiết Theo Từng Mục Đích Sử Dụng

### Trường Hợp A: Chạy Trên Kaggle (`colab/Datamate_kaggle.ipynb`)
Chỉ cần chỉnh duy nhất tại **Cell 1 (Ô Cấu Hình Tập Trung)**:

```python
# 4. CẤU HÌNH MÔ HÌNH LLM:
# 👉 Chọn 1 trong 2 dòng dưới đây:
MODEL_ID = "Qwen/Qwen2.5-Coder-14B-Instruct"  # Bản 14B mạnh nhất (Mặc định)
# MODEL_ID = "Qwen/Qwen2.5-Coder-7B-Instruct"  # Bản 7B nhẹ, nhanh hơn

# Mức lượng tử hóa:
QUANTIZATION = "8bit"     # Khuyên dùng "8bit" trên GPU T4 x 2; hoặc "4bit"
```
* Khi bạn đổi `MODEL_ID` tại đây, cả **Bước 5 (Đánh giá trên tập Train)** và **Bước 6 (Suy luận Public Test xuất submission.jsonl)** sẽ tự động dùng mô hình được chọn.

---

### Trường Hợp B: Chạy Trên Google Colab (`colab/DataMate_Colab.ipynb`)
Tương tự Kaggle, mở **Cell 1** của Notebook:

```python
# CẤU HÌNH MÔ HÌNH:
MODEL_ID = "Qwen/Qwen2.5-Coder-14B-Instruct"  # hoặc "Qwen/Qwen2.5-Coder-7B-Instruct"
```
* **Lưu ý khi dùng Colab Free (1 GPU T4)**: Nếu chọn `14B`, hãy đặt thêm biến môi trường `os.environ["DATAMATE_QUANTIZATION"] = "4bit"` để tránh hết bộ nhớ VRAM.

---

### Trường Hợp C: Chạy Trực Tiếp Bằng Lệnh Terminal (CLI)

#### 1. Khi chạy kiểm thử trên tập Train (White-Box Evaluation):
Bạn chỉ cần truyền cờ `--model_id`:

```bash
# Chạy với mô hình 14B:
python tests/inspect_pipeline.py \
    --batch --with_llm \
    --data_dir competition_data/train \
    --model_id "Qwen/Qwen2.5-Coder-14B-Instruct" \
    --quantization 8bit \
    --range 1-50 \
    --preserve_order

# Chạy với mô hình 7B:
python tests/inspect_pipeline.py \
    --batch --with_llm \
    --data_dir competition_data/train \
    --model_id "Qwen/Qwen2.5-Coder-7B-Instruct" \
    --quantization 8bit \
    --range 1-50 \
    --preserve_order
```

#### 2. Khi chạy sinh file kết quả nộp bài `submission.jsonl` (Public Test):
```bash
# Chạy ra kết quả nộp bài với mô hình 14B:
python predict.py \
    --data_dir competition_data/public_test \
    --model_id "Qwen/Qwen2.5-Coder-14B-Instruct" \
    --quantization 8bit \
    --output_file submission.jsonl \
    --preserve_order

# Chạy ra kết quả nộp bài với mô hình 7B:
python predict.py \
    --data_dir competition_data/public_test \
    --model_id "Qwen/Qwen2.5-Coder-7B-Instruct" \
    --quantization 8bit \
    --output_file submission.jsonl \
    --preserve_order
```

---

### Trường Hợp D: Đóng Gói Docker Image Để Nộp Bài Thi Offline Cho BTC

Trong file [`Dockerfile`](file:///d:/Company/Agentic%20AI/datamate/Dockerfile), biến `BASE_MODEL_ID` ở dòng 43 quy định mô hình nào sẽ được tải sẵn (bake) vào container nộp bài:

```dockerfile
# Dòng 43:
ARG BASE_MODEL_ID="Qwen/Qwen2.5-Coder-14B-Instruct"
```

Khi build Docker image trên máy chủ / VM của bạn, bạn có thể chuyển đổi linh hoạt bằng lệnh build mà **không cần sửa file**:

```bash
# Build nộp bài với bản 14B:
docker build -t datamate:14b --build-arg BASE_MODEL_ID="Qwen/Qwen2.5-Coder-14B-Instruct" .

# Build nộp bài với bản 7B:
docker build -t datamate:7b --build-arg BASE_MODEL_ID="Qwen/Qwen2.5-Coder-7B-Instruct" .
```

---

## 4. Bảng So Sánh Nhanh Thông Số Kỹ Thuật (7B vs 14B)

| Tiêu chí so sánh | Qwen2.5-Coder-7B-Instruct | Qwen2.5-Coder-14B-Instruct |
| :--- | :--- | :--- |
| **Số lượng tham số** | ~7.6 tỷ tham số | ~14.7 tỷ tham số (Gần gấp đôi) |
| **Khả năng suy luận mã & số học** | Rất tốt (Top phân khúc <= 7B) | Xuất sắc, vượt trội hơn ở các câu SQL / Pandas phức tạp nhiều bảng |
| **Dung lượng VRAM (8-bit INT8)** | ~7.5 GB VRAM | ~14.7 GB VRAM |
| **Dung lượng VRAM (4-bit NF4)** | ~4.5 GB VRAM | ~9.0 GB VRAM |
| **Môi trường Kaggle (T4 x 2 = 30GB)** | Dư dả bộ nhớ, tốc độ rất nhanh | **Lý tưởng nhất** (Mỗi GPU gánh ~7.4GB, sức mạnh tối đa) |
| **Môi trường Colab Free (1 x T4 = 15GB)** | Khuyên dùng 8-bit hoặc 4-bit | Khuyên dùng 4-bit (`QUANTIZATION = "4bit"`) |
| **Tốc độ xử lý trung bình** | ~2.5 – 3.5 giây / câu hỏi | ~4.5 – 6.5 giây / câu hỏi |

---

## 5. Tóm Tắt Quy Trình Nhanh Khi Muốn Đổi Model

1. **Trên Kaggle / Colab**: Mở **Cell 1**, sửa tên tại `MODEL_ID` thành 7B hoặc 14B rồi nhấn *Run All*.
2. **Khi test bằng lệnh**: Thêm cờ `--model_id "Qwen/Qwen2.5-Coder-7B-Instruct"` vào lệnh `inspect_pipeline.py` hoặc `predict.py`.
3. **Mọi cơ chế khác**: Giữ nguyên mặc định, hệ thống tự động lo toàn bộ phần còn lại!

