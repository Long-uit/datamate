#!/usr/bin/env bash
set -e

# ==============================================================================
# train.sh — Supervised Fine-Tuning Entrypoint for DataMate (Phase 3)
# Tinh chỉnh Qwen2.5-Coder-7B-Instruct bằng kỹ thuật QLoRA 4-bit (NF4)
# ==============================================================================

DATA_FILE="${1:-benchmark/splits/business_holdout_v1/fold_0/train_questions.jsonl}"
ANSWERS_FILE="${2:-benchmark/splits/business_holdout_v1/fold_0/train_answers.jsonl}"
OUTPUT_DIR="${3:-weights/qwen2.5-coder-7b-datamate}"
MODEL_ID="${4:-Qwen/Qwen2.5-Coder-7B-Instruct}"

echo "================================================================================"
echo "DATAMATE - KHỞI CHẠY HUẤN LUYỆN SFT / QLORA"
echo "================================================================================"
echo "• Model Backbone : $MODEL_ID"
echo "• Questions File : $DATA_FILE"
echo "• Answers File   : $ANSWERS_FILE"
echo "• Output Adapter : $OUTPUT_DIR"
echo "================================================================================"

python train.py \
    --model_id "$MODEL_ID" \
    --data_file "$DATA_FILE" \
    --answers_file "$ANSWERS_FILE" \
    --output_dir "$OUTPUT_DIR" \
    --epochs 3 \
    --batch_size 2 \
    --grad_accum 8 \
    --lr 2e-4 \
    --lora_rank 16 \
    --lora_alpha 32

echo "[train.sh] Hoàn tất quá trình huấn luyện thành công!"

