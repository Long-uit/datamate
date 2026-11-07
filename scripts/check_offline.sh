#!/usr/bin/env bash
set -e

# ==============================================================================
# check_offline.sh — Thử nghiệm chạy Container hoàn toàn Offline (--network none)
# Phân hệ: Phase 4 — Zalo AI Challenge 2026 (DataMate Track)
# ==============================================================================

IMAGE_TAG="${1:-datamate:latest}"
HOST_DATA_DIR="${2:-$(pwd)/competition_data/public_test}"
HOST_RESULT_DIR="${3:-$(pwd)/result_offline_test}"

echo "=============================================================================="
echo "DATAMATE — THỬ NGHIỆM CHẠY DOCKER NGOẠI TUYẾN 100% (--network none)"
echo "=============================================================================="
echo "  • Docker Image     : $IMAGE_TAG"
echo "  • Host Data Dir    : $HOST_DATA_DIR (Read-Only :ro)"
echo "  • Host Result Dir  : $HOST_RESULT_DIR"
echo "=============================================================================="

# Tạo thư mục nhận kết quả
mkdir -p "$HOST_RESULT_DIR/logs"

# Khởi chạy Docker Container với cờ cô lập mạng tuyệt đối (--network none)
docker run --rm \
    --gpus all \
    --network none \
    --shm-size 8g \
    -v "$HOST_DATA_DIR:/data:ro" \
    -v "$HOST_RESULT_DIR:/result:rw" \
    "$IMAGE_TAG" \
    /data \
    /result/submission.jsonl \
    /result/logs

echo "=============================================================================="
echo "Kiểm tra file kết quả sau khi chạy..."
if [ -f "$HOST_RESULT_DIR/submission.jsonl" ]; then
    echo "✓ Đã tìm thấy: $HOST_RESULT_DIR/submission.jsonl"
    python scripts/verify_submission.py \
        --submission "$HOST_RESULT_DIR/submission.jsonl" \
        --questions "$HOST_DATA_DIR/questions.jsonl"
    echo "🎉 THỬ NGHIỆM OFFLINE THÀNH CÔNG RỰC RỠ!"
else
    echo "❌ LỖI: Không tìm thấy file submission.jsonl trong $HOST_RESULT_DIR!"
    exit 1
fi
echo "=============================================================================="
