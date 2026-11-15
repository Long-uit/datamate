#!/usr/bin/env bash
set -e

# ==============================================================================
# make_checksum.sh — Tính mã băm MD5 & SHA256 cho tệp nộp bài / Docker Image Tarball
# Phân hệ: Phase 4 — Zalo AI Challenge 2026 (DataMate Track)
# ==============================================================================

TARGET_FILE="${1:-submission.jsonl}"

if [ ! -f "$TARGET_FILE" ]; then
    echo "⚠️ Không tìm thấy tệp: $TARGET_FILE"
    echo "Sử dụng: ./scripts/make_checksum.sh <đường_dẫn_tệp>"
    exit 1
fi

echo "=============================================================================="
echo "DATAMATE — TÍNH MÃ BĂM MD5 & SHA256 XÁC THỰC TOÀN VẸN (PHASE 4)"
echo "=============================================================================="
echo "• Tệp mục tiêu: $TARGET_FILE"
echo "• Kích thước  : $(ls -lh "$TARGET_FILE" | awk '{print $5}')"

# 1. Tính MD5 (Ban tổ chức yêu cầu khi nộp Docker Image)
if command -v md5sum &> /dev/null; then
    MD5_CHECKSUM=$(md5sum "$TARGET_FILE" | awk '{print $1}')
elif command -v md5 &> /dev/null; then
    MD5_CHECKSUM=$(md5 -q "$TARGET_FILE")
else
    MD5_CHECKSUM=$(python -c "import hashlib; h=hashlib.md5(); f=open('$TARGET_FILE','rb'); [h.update(c) for c in iter(lambda: f.read(65536), b'')]; print(h.hexdigest())")
fi

# 2. Tính SHA256
if command -v sha256sum &> /dev/null; then
    SHA256_CHECKSUM=$(sha256sum "$TARGET_FILE" | awk '{print $1}')
elif command -v shasum &> /dev/null; then
    SHA256_CHECKSUM=$(shasum -a 256 "$TARGET_FILE" | awk '{print $1}')
else
    SHA256_CHECKSUM=$(python -c "import hashlib; h=hashlib.sha256(); f=open('$TARGET_FILE','rb'); [h.update(c) for c in iter(lambda: f.read(65536), b'')]; print(h.hexdigest())")
fi

echo "------------------------------------------------------------------------------"
echo "🔑 MÃ CHECKSUM MD5 (Dùng nộp form BTC): $MD5_CHECKSUM"
echo "🔑 MÃ CHECKSUM SHA256                  : $SHA256_CHECKSUM"
echo "=============================================================================="
echo "$MD5_CHECKSUM  $TARGET_FILE" > "${TARGET_FILE}.md5"
echo "$SHA256_CHECKSUM  $TARGET_FILE" > "${TARGET_FILE}.sha256"
echo "✓ Đã lưu mã MD5 vào    : ${TARGET_FILE}.md5"
echo "✓ Đã lưu mã SHA256 vào : ${TARGET_FILE}.sha256"
