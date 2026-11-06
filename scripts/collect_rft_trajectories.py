"""
Script: scripts/collect_rft_trajectories.py
Mục đích: Rejection Sampling Fine-Tuning (RFT) Data Generator.
          Chạy suy luận trên tập train, đối chiếu kết quả với answers.jsonl,
          chỉ thu thập các câu hỏi có code sinh ra CHÍNH XÁC 100% để tạo tập dữ liệu huấn luyện QLoRA.
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Any, Dict, List

_ROOT_DIR = str(Path(__file__).resolve().parents[1])
_SRC_DIR = str(Path(__file__).resolve().parents[1] / "src")
for p in [_ROOT_DIR, _SRC_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Tái sử dụng logic so khớp và nạp dữ liệu từ run_eval
from run_eval import (
    load_ground_truth_answers,
    match_answers,
    get_cached_business_data,
    execute_solution,
    normalize_output,
)
from datamate.llm.client import LLMClient
from datamate.llm.prompt_builder import build_prompt, load_rulebook
from datamate.grounding.entity_linker import link_entities


def main():
    parser = argparse.ArgumentParser(description="Thu thập Gold Trajectories từ tập train cho QLoRA Fine-tuning.")
    parser.add_argument("--data_dir", type=str, default="competition_data/train", help="Thư mục tập train")
    parser.add_argument("--output_file", type=str, default="data/rft_gold_trajectories.jsonl", help="File dữ liệu ra")
    parser.add_argument("--limit", type=int, default=100, help="Số câu tối đa để quét")
    parser.add_argument("--model_id", type=str, default="Qwen/Qwen2.5-Coder-7B-Instruct")
    args = parser.parse_args()

    train_dir = Path(args.data_dir)
    q_file = train_dir / "questions.jsonl"
    ans_file = train_dir / "answers.jsonl"
    out_path = Path(args.output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not q_file.exists() or not ans_file.exists():
        print(f"Lỗi: Không tìm thấy {q_file} hoặc {ans_file}")
        sys.exit(1)

    gt_answers = load_ground_truth_answers(ans_file)
    rulebook_content = load_rulebook(train_dir)
    data_root = train_dir / "data"

    with open(q_file, "r", encoding="utf-8") as f:
        questions = [json.loads(line) for line in f if line.strip()]
    if args.limit:
        questions = questions[:args.limit]

    print(f"=== BẮT ĐẦU THU THẬP RFT GOLD TRAJECTORIES (Số câu: {len(questions)}) ===")
    print(f"Nạp LLM: {args.model_id}...")
    llm = LLMClient(model_id=args.model_id)
    if not llm.is_loaded:
        print("Lỗi: Không thể nạp mô hình vào GPU!")
        sys.exit(1)

    collected_count = 0
    with open(out_path, "w", encoding="utf-8") as out_f:
        for idx, q in enumerate(questions, 1):
            qid = q["id"]
            biz_id = q["business_id"]
            q_text = q["question"]
            as_of_date = q["as_of_date"]

            if qid not in gt_answers:
                continue
            gt_ans = gt_answers[qid]

            data_dict, con, schema_str, bd, shop_meta, candidates, _ = get_cached_business_data(biz_id, data_root)
            if not data_dict:
                continue

            entity_matches = link_entities(q_text, candidates=candidates, threshold=0.55) if candidates else []
            biz_readme = getattr(bd, "readme_text", None) if bd is not None else None

            sys_p, usr_p = build_prompt(
                schema_str=schema_str,
                as_of_date=as_of_date,
                question=q_text,
                rulebook_content=rulebook_content,
                business_note=biz_readme,
                candidates=candidates,
                entity_matches=entity_matches,
                return_messages=True,
            )

            code = llm.generate_code(prompt=usr_p, system_prompt=sys_p, max_new_tokens=400)
            raw_res, err, _ = execute_solution(code, biz_dir=data_root / biz_id, data_dict=data_dict, con=con, business_obj=bd)
            if err:
                continue

            pred_ans = normalize_output(raw_res, question=q_text, code_text=code)
            is_matched, _ = match_answers(pred_ans, gt_ans)

            if is_matched:
                collected_count += 1
                record = {
                    "question_id": qid,
                    "business_id": biz_id,
                    "messages": [
                        {"role": "system", "content": sys_p},
                        {"role": "user", "content": usr_p},
                        {"role": "assistant", "content": f"```python\n{code}\n```"},
                    ]
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                out_f.flush()
                print(f"[{idx}/{len(questions)}] ✓ ĐẠT CHUẨN (Gold Trajectory #{collected_count}): {qid}")
            else:
                print(f"[{idx}/{len(questions)}] ✗ Không khớp đáp án: {qid}")

    print(f"\n Hoàn tất! Đã thu thập {collected_count}/{len(questions)} Gold Trajectories lưu tại: {out_path}")


if __name__ == "__main__":
    main()
