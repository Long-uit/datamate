"""
Script: train.py
Mục đích: Pipeline huấn luyện tinh chỉnh (Supervised Fine-Tuning - SFT) cho mô hình Qwen2.5-Coder-7B-Instruct
          sử dụng kỹ thuật QLoRA 4-bit (NF4) tối ưu hóa bộ nhớ GPU (Zalo AI Challenge 2026 - DataMate Track).
Tác giả: Long (AI Architect & Model Lead)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def parse_args():
    parser = argparse.ArgumentParser(description="DataMate SFT / QLoRA Training Pipeline for Qwen2.5-Coder")
    parser.add_argument("--model_id", type=str, default="Qwen/Qwen2.5-Coder-7B-Instruct", help="HuggingFace model ID hoặc đường dẫn checkpoint")
    parser.add_argument("--data_file", type=str, default="benchmark/splits/business_holdout_v1/fold_0/train_questions.jsonl", help="Đường dẫn file câu hỏi huấn luyện (jsonl)")
    parser.add_argument("--answers_file", type=str, default="benchmark/splits/business_holdout_v1/fold_0/train_answers.jsonl", help="Đường dẫn file đáp án huấn luyện (jsonl)")
    parser.add_argument("--output_dir", type=str, default="weights/qwen2.5-coder-7b-datamate", help="Thư mục lưu adapter weights sau huấn luyện")
    parser.add_argument("--epochs", type=int, default=3, help="Số epoch huấn luyện")
    parser.add_argument("--batch_size", type=int, default=2, help="Kích thước batch trên mỗi GPU")
    parser.add_argument("--grad_accum", type=int, default=8, help="Số bước tích lũy gradient (Gradient accumulation steps)")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate cho AdamW")
    parser.add_argument("--max_seq_length", type=int, default=2048, help="Chiều dài chuỗi token tối đa")
    parser.add_argument("--lora_rank", type=int, default=16, help="Hạng LoRA (rank r)")
    parser.add_argument("--lora_alpha", type=int, default=32, help="Hệ số phóng đại LoRA (alpha)")
    parser.add_argument("--lora_dropout", type=float, default=0.05, help="Tỷ lệ LoRA dropout")
    parser.add_argument("--seed", type=int, default=42, help="Random seed tất định")
    parser.add_argument("--dry_run", action="store_true", help="Chạy kiểm thử cấu trúc pipeline không nạp trọng số nặng")
    return parser.parse_args()


def load_training_dataset(questions_path: Path, answers_path: Path) -> List[Dict[str, Any]]:
    """Đọc và ghép nối câu hỏi kèm đáp án chuẩn (Gold standard solution) thành định dạng huấn luyện."""
    if not questions_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file câu hỏi: {questions_path}")

    answers_map = {}
    if answers_path.exists():
        with open(answers_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    item = json.loads(line)
                    answers_map[item["id"]] = item

    samples = []
    with open(questions_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                q_item = json.loads(line)
                qid = q_item["id"]
                gold = answers_map.get(qid, {})
                samples.append({
                    "id": qid,
                    "business_id": q_item.get("business_id"),
                    "question": q_item.get("question"),
                    "as_of_date": q_item.get("as_of_date"),
                    "gold_type": gold.get("type"),
                    "gold_answer": gold.get("answer"),
                })
    return samples


def main():
    args = parse_args()
    print("=" * 80)
    print("DATAMATE - HUẤN LUYỆN TINH CHỈNH MÔ HÌNH QWEN2.5-CODER (QLoRA 4-bit)")
    print("=" * 80)
    print(f"• Backbone Model : {args.model_id}")
    print(f"• Dataset        : {args.data_file}")
    print(f"• Output Weights : {args.output_dir}")
    print(f"• LoRA Config    : rank={args.lora_rank}, alpha={args.lora_alpha}, dropout={args.lora_dropout}")
    print(f"• Training Setup : epochs={args.epochs}, batch={args.batch_size}, grad_accum={args.grad_accum}, lr={args.lr}")
    print("=" * 80)

    # 1. Nạp và kiểm định tập dữ liệu
    q_path = Path(args.data_file)
    a_path = Path(args.answers_file)
    dataset = load_training_dataset(q_path, a_path)
    print(f"[Dataset] Đã nạp thành công {len(dataset)} mẫu câu hỏi huấn luyện.")

    if args.dry_run:
        print("[Dry-Run] Kiểm tra cấu hình và dữ liệu huấn luyện thành công! Bỏ qua nạp GPU.")
        out_p = Path(args.output_dir)
        out_p.mkdir(parents=True, exist_ok=True)
        manifest = {
            "model_id": args.model_id,
            "train_samples": len(dataset),
            "lora_rank": args.lora_rank,
            "lora_alpha": args.lora_alpha,
            "status": "dry_run_verified",
        }
        with open(out_p / "training_manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        print(f"[Dry-Run] Đã tạo manifest kiểm định tại {out_p / 'training_manifest.json'}")
        return

    # 2. Kiểm tra thư viện PyTorch và GPU
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, TrainingArguments
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    except ImportError as exc:
        print(f"⚠️ Thiếu thư viện huấn luyện: {exc}. Hãy cài đặt: pip install torch transformers peft bitsandbytes accelerate")
        sys.exit(1)

    if not torch.cuda.is_available():
        print("⚠️ Cảnh báo: Không tìm thấy GPU CUDA! Huấn luyện 7B trên CPU không khả thi.")
        sys.exit(1)

    device_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    print(f"[Phần cứng] Phát hiện GPU: {device_name} ({vram_gb:.2f} GB VRAM)")

    # 3. Cấu hình QLoRA 4-bit (NF4)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
    )

    print(f"[Mô hình] Đang nạp {args.model_id} dạng lượng tử hóa 4-bit...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    model = prepare_model_for_kbit_training(model)

    # 4. Cấu hình LoRA Adapter
    lora_config = LoraConfig(
        r=args.lora_rank,
        lora_alpha=args.lora_alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    print("[Huấn luyện] Thiết lập hoàn tất! Sẵn sàng thực hiện SFT.")
    # Các bước huấn luyện SFT thực tế sẽ được kích hoạt khi nạp đủ bộ sinh dữ liệu tổng hợp ở Phase 3.


if __name__ == "__main__":
    main()
