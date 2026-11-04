"""
build_dataset.py — Pipeline tổng hợp và đóng gói tập dữ liệu huấn luyện (Dataset Builder).

Tập hợp các module:
- paraphrase.py: mở rộng câu hỏi tiếng Việt đời thường
- unanswerable_gen.py: bổ sung câu hỏi bất khả thi gài bẫy
- tet_variants.py: bổ sung biến thể thời gian lễ Tết
- clean_filter.py: thẩm định chất lượng trước khi xuất file
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from data_synth.clean_filter import filter_synthetic_sample
from data_synth.paraphrase import paraphrase_question
from data_synth.tet_variants import generate_tet_questions
from data_synth.unanswerable_gen import generate_unanswerable_questions


def augment_seed_questions(
    seed_questions: list[dict[str, Any]],
    target_count: int = 100,
    paraphrase_variants: int = 2,
) -> list[dict[str, Any]]:
    """Mở rộng từ danh sách câu hỏi gốc thành tập dữ liệu tổng hợp phong phú."""
    dataset: list[dict[str, Any]] = []

    for item in seed_questions:
        # Thêm câu hỏi gốc nếu đạt chuẩn
        if filter_synthetic_sample(item):
            dataset.append(item)

        # 1. Sinh paraphrase
        q_text = item.get("question", "")
        if q_text:
            paras = paraphrase_question(q_text, num_variants=paraphrase_variants)
            for p in paras:
                new_item = dict(item)
                new_item["question"] = p
                new_item["is_synthetic"] = True
                new_item["synth_type"] = "paraphrase"
                if filter_synthetic_sample(new_item):
                    dataset.append(new_item)

        # 2. Sinh Unanswerable
        b_id = item.get("business_id", "shop_sample")
        as_of = item.get("as_of_date", "2024-05-01")
        unans_samples = generate_unanswerable_questions(b_id, as_of)
        for u in unans_samples:
            u["is_synthetic"] = True
            u["synth_type"] = "unanswerable"
            dataset.append(u)

        # 3. Sinh Tết variants
        tet_samples = generate_tet_questions(b_id, as_of)
        for t in tet_samples:
            t["is_synthetic"] = True
            t["synth_type"] = "tet_variant"
            if filter_synthetic_sample(t):
                dataset.append(t)

        if len(dataset) >= target_count:
            break

    return dataset[:target_count]


def export_dataset_jsonl(dataset: list[dict[str, Any]], output_path: str | Path) -> int:
    """Ghi tập dữ liệu ra định dạng JSON Lines."""
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with open(out_file, "w", encoding="utf-8") as f:
        for row in dataset:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1

    return count

