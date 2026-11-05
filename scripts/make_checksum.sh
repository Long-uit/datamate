#!/usr/bin/env bash
set -e

# ==============================================================================
# make_checksum.sh — Tính mã băm SHA256 cho tệp nộp bài / Docker Image Tarball
# Phân hệ: Phase 4 — Zalo AI Challenge 2026 (DataMate Track)
# ==============================================================================

TARGET_FILE="${1:-submission.jsonl}"

if [ ! -f "$TARGET_FILE" ]; then
    echo "⚠️ Không tìm thấy tệp: $TARGET_FILE"
    echo "Sử dụng: ./scripts/make_checksum.sh <đường_dẫn_tệp>"
    exit 1
fi

echo "=============================================================================="
echo "DATAMATE — TÍNH MÃ BĂM SHA256 XÁC THỰC TOÀN VẸN (PHASE 4)"
echo "=============================================================================="
echo "• Tệp mục tiêu: $TARGET_FILE"
echo "• Kích thước  : $(ls -lh "$TARGET_FILE" | awk '{print $5}')"

if command -v sha256sum &> /dev/null; then
    CHECKSUM=$(sha256sum "$TARGET_FILE" | awk '{print $1}')
elif command -v shasum &> /dev/null; then
    CHECKSUM=$(shasum -a 256 "$TARGET_FILE" | awk '{print $1}')
else
    CHECKSUM=$(python -c "import hashlib; print(hashlib.sha256(open('$TARGET_FILE', 'rb').read()).hexdigest())")
fi

echo "• SHA256 Hash : $CHECKSUM"
echo "=============================================================================="
echo "$CHECKSUM  $TARGET_FILE" > "${TARGET_FILE}.sha256"
echo "✓ Đã ghi mã băm vào tệp: ${TARGET_FILE}.sha256"
