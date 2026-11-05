#!/usr/bin/env bash
set -e

# ==============================================================================
# predict.sh — Inference Entrypoint for Zalo AI Challenge 2026 (DataMate Track)
# Phase 4: Calibrated Abstention, Offline Isolation & Reproducibility
# ==============================================================================
# Quy cách Docker:
# - Đọc dữ liệu kiểm thử từ: /data (hoặc tham số thứ nhất)
# - Ghi file kết quả nộp bài ra: /result/submission.jsonl (hoặc tham số thứ hai)
# - Ghi nhật ký chi tiết ra: /result/logs/ (hoặc tham số thứ ba)
# ==============================================================================

DATA_DIR="${1:-/data}"
OUTPUT_FILE="${2:-/result/submission.jsonl}"
LOG_DIR="${3:-/result/logs}"
TAU_STAR="${TAU_STAR:-0.50}"
SEED="${SEED:-42}"

echo "=============================================================================="
echo "[predict.sh] KHỞI ĐỘNG SUY LUẬN DATAMATE — ZALO AI CHALLENGE 2026 (PHASE 4)"
echo "=============================================================================="
echo "  • Data Directory   : $DATA_DIR"
echo "  • Output Submission: $OUTPUT_FILE"
echo "  • Logs Directory   : $LOG_DIR"
echo "  • Calibrated Tau*  : $TAU_STAR"
echo "  • Random Seed      : $SEED"
echo "=============================================================================="

# Đảm bảo các thư mục đầu ra tồn tại
mkdir -p "$(dirname "$OUTPUT_FILE")" "$LOG_DIR"

# Kích hoạt suy luận chính thức
python predict.py \
    --data_dir "$DATA_DIR" \
    --output_file "$OUTPUT_FILE" \
    --log_dir "$LOG_DIR" \
    --tau_star "$TAU_STAR" \
    --seed "$SEED"

echo "[predict.sh] Hoàn tất quá trình suy luận thành công!"
