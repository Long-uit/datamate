"""
split.py — Phân chia tập dữ liệu train thành 2.400 Train / 600 Validation.

Quy tắc chia:
- Cố định seed ngẫu nhiên (seed=42) để bảo đảm tính tái lập 100%.
- Phân tầng (stratified) theo business_id để tập val có đại diện của các shop
  (khoảng 80% câu mỗi shop vào train, 20% vào val).
- Lưu danh sách ID và tạo các file val phục vụ chấm điểm tự động.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import random
import sys
from collections import defaultdict

# Bảo đảm in tiếng Việt không bị lỗi cp1252 trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

log = logging.getLogger(__name__)


def create_split(
    questions_file: Path | str = "competition_data/train/questions.jsonl",
    answers_file: Path | str = "competition_data/train/answers.jsonl",
    output_dir: Path | str = "benchmark",
    val_ratio: float = 0.20,
    seed: int = 42,
) -> tuple[list[str], list[str]]:
    """
    Chia 3.000 câu hỏi thành train và val theo tỷ lệ val_ratio (mặc định 20% = 600 câu).
    """
    questions_path = Path(questions_file)
    answers_path = Path(answers_file)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if not questions_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file câu hỏi: {questions_path}")

    # Đọc danh sách câu hỏi
    questions = []
    with open(questions_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))

    # Đọc đáp án nếu có
    answers_by_id = {}
    if answers_path.exists():
        with open(answers_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    answers_by_id[item["id"]] = item

    # Nhóm câu hỏi theo business_id
    by_biz = defaultdict(list)
    for q in questions:
        by_biz[q.get("business_id", "unknown")].append(q)

    rng = random.Random(seed)
    train_ids: list[str] = []
    val_ids: list[str] = []

    train_questions: list[dict] = []
    val_questions: list[dict] = []

    for biz_id, biz_q_list in sorted(by_biz.items()):
        # Xáo trộn các câu của từng shop với seed cố định
        shuffled = list(biz_q_list)
        rng.shuffle(shuffled)

        n_val = max(1, int(round(len(shuffled) * val_ratio)))
        biz_val = shuffled[:n_val]
        biz_train = shuffled[n_val:]

        for q in biz_train:
            train_ids.append(q["id"])
            train_questions.append(q)

        for q in biz_val:
            val_ids.append(q["id"])
            val_questions.append(q)

    # Lưu train_ids.json và val_ids.json
    (out_path / "train_ids.json").write_text(
        json.dumps(train_ids, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_path / "val_ids.json").write_text(
        json.dumps(val_ids, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Lưu val_questions.jsonl và val_answers.jsonl
    with open(out_path / "val_questions.jsonl", "w", encoding="utf-8") as f:
        for q in val_questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")

    if answers_by_id:
        with open(out_path / "val_answers.jsonl", "w", encoding="utf-8") as f:
            for vid in val_ids:
                if vid in answers_by_id:
                    f.write(json.dumps(answers_by_id[vid], ensure_ascii=False) + "\n")

    print(f"Phân chia hoàn tất (seed={seed}):")
    print(f"- Tổng số câu: {len(questions)}")
    print(f"- Tập Train:   {len(train_ids)} câu ({out_path / 'train_ids.json'})")
    print(f"- Tập Val:     {len(val_ids)} câu ({out_path / 'val_ids.json'})")
    return train_ids, val_ids


def main():
    parser = argparse.ArgumentParser(description="Tách tập train thành Train / Val cho Benchmark")
    parser.add_argument("--questions", default="competition_data/train/questions.jsonl")
    parser.add_argument("--answers", default="competition_data/train/answers.jsonl")
    parser.add_argument("--output-dir", default="benchmark")
    parser.add_argument("--val-ratio", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    create_split(
        questions_file=args.questions,
        answers_file=args.answers,
        output_dir=args.output_dir,
        val_ratio=args.val_ratio,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
