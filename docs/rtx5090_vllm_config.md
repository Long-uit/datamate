# CẤU HÌNH ĐỀ XUẤT CHO HỆ THỐNG 2x NVIDIA GEFORCE RTX 5090 (BLACKWELL)
# Dành cho môi trường máy thi đấu offline BTC Zalo AI Challenge 2026

## 1. Phân tích tài nguyên phần cứng & Mô hình
- Phần cứng: 2x NVIDIA RTX 5090 (32GB VRAM / card = 64GB VRAM tổng cộng).
- Mô hình: Qwen/Qwen2.5-Coder-14B-Instruct (14.77B tham số).
- Dung lượng bộ nhớ trọng số mô hình:
  + bfloat16: 14.77 × 2 bytes ≈ 29.54 GB.
  + FP8: 14.77 × 1 byte ≈ 14.77 GB.
  + 4-bit (AWQ / GPTQ): 14.77 × 0.5 byte ≈ 7.39 GB.
- Đánh giá trên 1 card (32GB VRAM):
  Trọng số bfloat16 (29.54GB) + PyTorch overhead (~1.5GB) = 31.0GB -> KHÔNG ĐỦ VRAM để cấp phát KV Cache cho context dài 8.192 tokens.
  Do đó, KHÔNG THỂ chạy bfloat16 trên 1 card duy nhất.

---

## 2. Các phương án cấu hình triển khai đề xuất

### Phương án 1 (Khuyên dùng - Chất lượng tối đa): bfloat16 với Tensor Parallelism = 2
- Giải pháp: Chia đều mô hình qua cả 2 card RTX 5090 bằng vLLM Tensor Parallel (`tensor_parallel_size=2`).
- Phân bổ VRAM:
  + Mỗi card gánh: ~14.8 GB weights + ~1.5 GB CUDA runtime = ~16.3 GB.
  + VRAM trống mỗi card: ~15.7 GB -> Đủ chỗ cho KV Cache của 8.192 tokens và batch size lớn, không bao giờ OOM.
  + Giữ nguyên độ chính xác 100% gốc của mô hình (không bị suy hao do lượng tử hóa).

* Lệnh khởi chạy / Cấu hình:
```bash
python predict.py \
  --backend vllm \
  --model_id /weights/Qwen2.5-Coder-14B-Instruct \
  --data_dir /data \
  --output_file /result/submission.jsonl
```
* vLLM Engine kwargs tương ứng:
```python
llm = LLM(
    model="/weights/Qwen2.5-Coder-14B-Instruct",
    tensor_parallel_size=2,
    dtype="bfloat16",
    enable_prefix_caching=True,
    max_model_len=8192,
    gpu_memory_utilization=0.90,
    trust_remote_code=True,
)
```

### Phương án 2 (Thay thế nếu không muốn chia Tensor Parallel): FP8 trên 1 card (hoặc Pipeline Parallel)
- Giải pháp: Sử dụng checkpoint FP8 (ví dụ: `Qwen/Qwen2.5-Coder-14B-Instruct-FP8`).
- Phân bổ VRAM:
  + 1 card RTX 5090 chứa ~14.8 GB weights + 1.5 GB runtime = ~16.3 GB.
  + Còn trống ~15.7 GB cho KV cache.
  + Card thứ 2 có thể tận dụng để chạy song song hoặc làm dự phòng.

---

## 3. Yêu cầu môi trường & Thư viện tương thích kiến trúc Blackwell (sm_120)

Do kiến trúc NVIDIA Blackwell (GeForce RTX 50-series) sử dụng compute capability `sm_120`, các phiên bản CUDA và PyTorch cũ sẽ không nhận diện được phần cứng.

Bắt buộc cấu hình môi trường Docker:
1. CUDA Driver & Toolkit:
   - NVIDIA Driver >= 570.xx
   - CUDA Toolkit >= 12.8 (bắt buộc để biên dịch kernel `sm_120`).
2. PyTorch:
   - PyTorch >= 2.6.0 (hoặc nightly build có cờ hỗ trợ `sm_120`).
3. vLLM:
   - vLLM >= 0.7.3 (hoặc bản build from source với `TORCH_CUDA_ARCH_LIST="12.0;12.0+PTX"`).
4. FlashAttention / Triton:
   - Triton >= 3.2.0.

---

## 4. Những gì CHƯA THỂ kiểm chứng (Khi chưa có phần cứng RTX 5090)

1. Tốc độ giao tiếp PCIe / NVLink giữa 2 card RTX 5090:
   - RTX 5090 dòng tiêu dùng (GeForce) không có cầu nối cứng NVLink, giao tiếp Tensor Parallel (TP=2) sẽ chạy qua bus PCIe 5.0 x16.
   - Chưa thể đo đạc thực tế độ trễ `AllReduce` qua PCIe 5.0 so với NVLink thực thụ.
2. Kernel FP8 Tensor Core thế hệ mới trên sm_120:
   - Hiệu năng suy luận FP8 và độ chính xác thực tế trên Blackwell cần benchmark trực tiếp trên card vật lý.
3. Độ ổn định nhiệt độ và phân bổ điện năng khi cả 2 GPU chạy liên tục 6 tiếng private test.
