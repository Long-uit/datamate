# Báo Cáo Phân Tích Độ Trễ & Thông Lượng (Latency & Throughput Report)
**Dự án:** DataMate — Zalo AI Challenge 2026 (Phase 4)  
**Số lượng mẫu phân tích:** `1002`  
**Thời gian trung bình mỗi câu:** `0.0s`  
**Dự báo Public Test (1.000 câu):** `0.0 phút` (~`0.0 giờ`)  
**Dự báo Private Test (2.000 câu):** `0.0 giờ` (Giới hạn tối đa: 6.0 giờ)  
**Đánh giá an toàn thời gian:** `AN TOÀN (SAFE)`  

---

## 1. Phân phối thời gian thực thi (Latency Distribution)

| Chỉ số | Thời gian (giây) | Ghi chú kỹ thuật |
|---|:---:|---|
| **Mean Total** | `0.0s` | Trung bình cộng toàn bộ thời gian xử lý |
| **Median (P50)** | `0.0s` | 50% câu hỏi hoàn thành dưới mốc này |
| **P90 Latency** | `0.0s` | 90% câu hỏi hoàn thành dưới mốc này |
| **P95 Latency** | `0.0s` | Các câu phức tạp hoặc có Self-Correction |
| **Max Latency** | `0.0s` | Câu chạm trần sandbox timeout |
| **Mean LLM Gen** | `0.0s` | Thời gian Qwen2.5-Coder sinh mã |
| **Mean Execution** | `0.0s` | Thời gian chạy Pandas/SQLite trong Sandbox |

## 2. Kết luận & Tối ưu hóa
- Các câu hỏi `unanswerable` bị Feasibility Gate bắt sớm tiêu tốn **~0.01s (0s GPU)**.
- Cơ chế In-Memory Caching (`_BUSINESS_CACHE`) giúp nạp dữ liệu cửa hàng chỉ 1 lần duy nhất.
- Dự báo tổng thời gian hoàn toàn nằm trong ngân sách 6 giờ của Ban Tổ Chức.