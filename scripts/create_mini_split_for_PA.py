# scripts/create_mini_split.py
import json
from pathlib import Path

train_dir = Path("competition_data/train")
out_dir = Path("benchmark/splits/mini_30")
out_dir.mkdir(parents=True, exist_ok=True)

# 1. Đọc 30 câu đầu tiên (hoặc lấy theo doanh nghiệp bạn muốn)
with open(train_dir / "questions.jsonl", "r", encoding="utf-8") as f:
    questions = [json.loads(line) for line in f if line.strip()][:30]

q_ids = {q["id"] for q in questions}

with open(train_dir / "answers.jsonl", "r", encoding="utf-8") as f:
    answers = [json.loads(line) for line in f if line.strip() and json.loads(line)["id"] in q_ids]

# 2. Chia 24 train / 6 validation (tỷ lệ 80% / 20%)
train_q, val_q = questions[:24], questions[24:30]
train_a, val_a = answers[:24], answers[24:30]

train_ids = [q["id"] for q in train_q]
val_ids = [q["id"] for q in val_q]

# 3. Ghi ra 7 tệp chuẩn hóa của DataMate Benchmark
for name, data in [("train_ids.json", train_ids), ("val_ids.json", val_ids)]:
    with open(out_dir / name, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

for name, rows in [
    ("train_questions.jsonl", train_q),
    ("train_answers.jsonl", train_a),
    ("val_questions.jsonl", val_q),
    ("val_answers.jsonl", val_a),
]:
    with open(out_dir / name, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"✓ Đã tạo thành công bộ split mini_30: {len(train_ids)} train, {len(val_ids)} val!")