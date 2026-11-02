#!/usr/bin/env bash
set -e

# ==============================================================================
# predict.sh — Inference Entrypoint for Zalo AI Challenge 2026 (DataMate Track)
# ==============================================================================
# Quy cách Docker:
# - Đọc dữ liệu kiểm thử từ: /data (hoặc tham số thứ nhất)
# - Ghi file kết quả nộp bài ra: /result/submission.jsonl (hoặc tham số thứ hai)
# - Ghi nhật ký chi tiết ra: /result/logs/ (hoặc tham số thứ ba)
# ==============================================================================

DATA_DIR="${1:-/data}"
OUTPUT_FILE="${2:-/result/submission.jsonl}"
LOG_DIR="${3:-/result/logs}"

echo "[predict.sh] Bắt đầu suy luận DataMate..."
echo "  • Data Directory   : $DATA_DIR"
echo "  • Output Submission: $OUTPUT_FILE"
echo "  • Logs Directory   : $LOG_DIR"

python predict.py \
    --data_dir "$DATA_DIR" \
    --output_file "$OUTPUT_FILE" \
    --log_dir "$LOG_DIR"

echo "[predict.sh] Hoàn tất quá trình suy luận thành công!"
