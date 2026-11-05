"""
build_dataset.py — Pipeline tổng hợp và đóng gói tập dữ liệu huấn luyện (Dataset Builder).

Tập hợp các module:
- paraphrase.py: mở rộng câu hỏi tiếng Việt đời thường (teencode, viết tắt, không dấu)
- unanswerable_gen.py: bổ sung câu hỏi bất khả thi gài bẫy
- tet_variants.py: bổ sung biến thể thời gian lễ Tết
- clean_filter.py: thẩm định chất lượng trước khi xuất file

Cải tiến chống trùng lặp (Deduplication Gate) & cân bằng tỷ lệ các nhóm dữ liệu.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from data_synth.clean_filter import filter_synthetic_sample
from data_synth.paraphrase import paraphrase_question
from data_synth.tet_variants import generate_tet_questions
from data_synth.unanswerable_gen import generate_unanswerable_questions


def _normalize_key(text: str) -> str:
    """Tạo khóa chuẩn hóa để phát hiện câu hỏi trùng lặp."""
    return " ".join(str(text).strip().lower().split())


def augment_seed_questions(
    seed_questions: list[dict[str, Any]],
    target_count: int = 100,
    paraphrase_variants: int = 2,
    unanswerable_ratio: float = 0.15,
    tet_ratio: float = 0.10,
) -> list[dict[str, Any]]:
    """
    Mở rộng từ danh sách câu hỏi gốc thành tập dữ liệu tổng hợp phong phú và không trùng lặp.
    
    Args:
        seed_questions: Danh sách câu hỏi hạt giống (seed).
        target_count: Số lượng mẫu mục tiêu cần sinh.
        paraphrase_variants: Số biến thể diễn đạt lại cho mỗi câu hỏi gốc.
        unanswerable_ratio: Tỷ lệ mục tiêu cho nhóm câu hỏi bất khả thi (~15%).
        tet_ratio: Tỷ lệ mục tiêu cho nhóm câu hỏi thời gian Tết (~10%).
    """
    dataset: list[dict[str, Any]] = []
    seen_questions: set[str] = set()

    def add_if_unique(sample: dict[str, Any]) -> bool:
        q = sample.get("question", "")
        if not q:
            return False
        key = _normalize_key(q)
        if key in seen_questions:
            return False
        if not filter_synthetic_sample(sample):
            return False
        seen_questions.add(key)
        dataset.append(sample)
        return True

    # 1. Thêm câu hỏi gốc vào dataset
    for item in seed_questions:
        add_if_unique(dict(item))
        if len(dataset) >= target_count:
            return dataset[:target_count]

    # 2. Sinh biến thể Paraphrase từ các câu gốc
    for item in seed_questions:
        q_text = item.get("question", "")
        if not q_text:
            continue
        paras = paraphrase_question(q_text, num_variants=paraphrase_variants)
        for p in paras:
            new_item = dict(item)
            new_item["question"] = p
            new_item["is_synthetic"] = True
            new_item["synth_type"] = "paraphrase"
            add_if_unique(new_item)
            if len(dataset) >= target_count:
                return dataset[:target_count]

    # 3. Thu thập các shop và ngày mốc (as_of_date) để sinh unanswerable và tết đa dạng
    biz_map: dict[str, str] = {}
    for item in seed_questions:
        b_id = item.get("business_id", "shop_sample")
        as_of = item.get("as_of_date", "2024-05-01")
        if b_id not in biz_map:
            biz_map[b_id] = as_of

    # 4. Sinh Unanswerable theo từng shop (có kiểm soát deduplication)
    max_unans = int(target_count * unanswerable_ratio)
    unans_count = 0
    for b_id, as_of in biz_map.items():
        if unans_count >= max_unans:
            break
        samples = generate_unanswerable_questions(b_id, as_of)
        for u in samples:
            u["is_synthetic"] = True
            u["synth_type"] = "unanswerable"
            if add_if_unique(u):
                unans_count += 1
                if unans_count >= max_unans or len(dataset) >= target_count:
                    break

    # 5. Sinh biến thể thời gian Tết theo từng shop
    max_tet = int(target_count * tet_ratio)
    tet_count = 0
    for b_id, as_of in biz_map.items():
        if tet_count >= max_tet:
            break
        samples = generate_tet_questions(b_id, as_of)
        for t in samples:
            t["is_synthetic"] = True
            t["synth_type"] = "tet_variant"
            if add_if_unique(t):
                tet_count += 1
                if tet_count >= max_tet or len(dataset) >= target_count:
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


def main() -> None:
    """CLI runner để sinh và xuất tập dữ liệu tổng hợp trực tiếp từ terminal."""
    parser = argparse.ArgumentParser(description="Sinh dữ liệu tổng hợp SFT Data Augmentation cho DataMate.")
    parser.add_argument("--input", type=str, default="competition_data/train/questions.jsonl", help="Đường dẫn questions.jsonl gốc")
    parser.add_argument("--output", type=str, default="data_synth/synthetic_dataset.jsonl", help="Đường dẫn file JSONL xuất ra")
    parser.add_argument("--target", type=int, default=1000, help="Số lượng mẫu cần sinh")
    parser.add_argument("--paraphrase_variants", type=int, default=2, help="Số biến thể paraphrase mỗi câu")
    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"[Lỗi] Không tìm thấy tệp đầu vào tại: {in_path}")
        sys.exit(1)

    with open(in_path, "r", encoding="utf-8") as f:
        seeds = [json.loads(line) for line in f if line.strip()]

    print(f"• Đã nạp {len(seeds)} câu hỏi hạt giống từ {in_path.name}")
    print(f"• Đang sinh tập dữ liệu mở rộng (Mục tiêu: {args.target} mẫu)...")

    dataset = augment_seed_questions(
        seed_questions=seeds,
        target_count=args.target,
        paraphrase_variants=args.paraphrase_variants,
    )

    n_exported = export_dataset_jsonl(dataset, args.output)
    print(f"✓ Đã xuất thành công {n_exported} mẫu vào {args.output}")


if __name__ == "__main__":
    main()
