"""
Script: scripts/train_qlora.py
Mục đích: Huấn luyện QLoRA 4-bit tinh chỉnh mô hình Qwen/Qwen2.5-Coder-7B-Instruct
          trên tập Gold Trajectories, tối ưu trọn vẹn cho GPU 6GB VRAM (RTX 3050).

Thiết lập tối ưu bộ nhớ:
- 4-bit NF4 Quantization (BitsAndBytes)
- LoRA rank r=16, alpha=32, target: all linear layers
- Batch size = 1, Gradient Accumulation = 8 (effective batch = 8)
- Gradient Checkpointing = True (tiết kiệm 60% activation VRAM)
- Optimizer: paged_adamw_8bit
- VRAM dự kiến: ~5.4 - 5.6 GB VRAM
"""

from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Huấn luyện QLoRA 4-bit cho Qwen2.5-Coder-7B.")
    parser.add_argument("--train_file", type=str, default="data/rft_gold_trajectories.jsonl", help="Đường dẫn file dữ liệu train")
    parser.add_argument("--output_dir", type=str, default="models/qwen2.5_coder_qlora_adapter", help="Thư mục lưu adapter")
    parser.add_argument("--model_id", type=str, default="Qwen/Qwen2.5-Coder-7B-Instruct", help="Tên model gốc")
    parser.add_argument("--epochs", type=int, default=3, help="Số epochs")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    args = parser.parse_args()

    train_path = Path(args.train_file)
    if not train_path.exists():
        print(f"Lỗi: Không tìm thấy file dữ liệu {train_path}. Hãy chạy scripts/collect_rft_trajectories.py trước!")
        sys.exit(1)

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from datasets import load_dataset
        from trl import SFTTrainer
    except ImportError as e:
        print(f"Lỗi thiếu thư viện: {e}")
        print("Vui lòng cài đặt: pip install transformers peft trl datasets bitsandbytes accelerate")
        sys.exit(1)

    print(f"=== BẮT ĐẦU HUẤN LUYỆN QLORA 4-BIT (GPU 6GB OPTIMIZED) ===")
    print(f"• Model gốc   : {args.model_id}")
    print(f"• Dữ liệu     : {args.train_file}")
    print(f"• Thư mục lưu : {args.output_dir}")

    # 1. Cấu hình lượng tử hóa 4-bit
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print("Nạp mô hình 4-bit lên GPU...")
    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        quantization_config=bnb_config,
        device_map={"": 0},
        trust_remote_code=True,
        torch_dtype=torch.float16,
    )

    model = prepare_model_for_kbit_training(model)
    model.gradient_checkpointing_enable()

    # 2. Cấu hình LoRA Adapter
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 3. Chuẩn bị dữ liệu định dạng ChatML
    dataset = load_dataset("json", data_files=args.train_file, split="train")

    def format_chatml(example):
        text = tokenizer.apply_chat_template(example["messages"], tokenize=False, add_generation_prompt=False)
        return {"text": text}

    dataset = dataset.map(format_chatml)

    # 4. Tham số huấn luyện tiết kiệm VRAM tối đa
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        gradient_checkpointing=True,
        optim="paged_adamw_8bit",
        learning_rate=args.lr,
        fp16=True,
        logging_steps=5,
        save_strategy="epoch",
        warmup_ratio=0.05,
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=1536,
        tokenizer=tokenizer,
        args=training_args,
    )

    print("Bắt đầu quá trình huấn luyện...")
    trainer.train()

    print(f"Huấn luyện thành công! Lưu adapter tại: {args.output_dir}")
    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)


if __name__ == "__main__":
    main()
