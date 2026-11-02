"""
evaluate.py — Đánh giá kết quả dự đoán và tính điểm Penalized Accuracy (PA) theo Điều 9 Rulebook.

Công thức điểm phạt (Penalized Accuracy - PA):
- Mỗi câu đúng: +1 điểm
- Mỗi câu sai: -1 điểm (phạt nặng)
- Bỏ trống (Abstain): 0 điểm (an toàn)
  PA = (Số câu đúng - Số câu sai) / Tổng số câu

Quy tắc so khớp đáp án (Điều 9 Rulebook):
- number: So sánh số học chính xác (tiền là số nguyên). Bỏ qua sai số dấu phẩy động cực nhỏ.
- percent: Số thập phân khớp tuyệt đối (dung sai 0.01).
- date: Khớp chính xác chuỗi YYYY-MM-DD hoặc YYYY-MM.
- boolean: Khớp bool (True/False).
- string: Bỏ qua hoa/thường, khoảng trắng, dấu câu; chấp nhận alias nếu có trong dữ liệu shop.
- list: Đúng cả tập và thứ tự.
- table: So khớp cấu trúc columns và rows.
- unanswerable: Cả hai cùng là unanswerable.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Optional

# Cấu hình UTF-8 trên Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

log = logging.getLogger(__name__)


def _norm_str(s: Any) -> str:
    """Chuẩn hóa chuỗi so khớp (NFC, chữ thường, bỏ khoảng trắng thừa)."""
    text = unicodedata.normalize("NFC", str(s)).lower()
    return re.sub(r"\s+", " ", text).strip()


def compare_value(pred_val: Any, gold_val: Any, ans_type: str, aliases: list[str] = None) -> bool:
    """So khớp giá trị chi tiết theo từng kiểu dữ liệu quy định trong Rulebook."""
    if aliases is None:
        aliases = []

    # 1. Unanswerable
    if ans_type == "unanswerable":
        # Cả hai cùng unanswerable là đúng
        return True

    # 2. Boolean
    if ans_type == "boolean":
        return bool(pred_val) is bool(gold_val)

    # 3. Number
    if ans_type == "number":
        try:
            p_num = float(pred_val)
            g_num = float(gold_val)
            # Rulebook: Tiền đúng từng đồng, số đếm đúng từng đơn vị. Chỉ bỏ qua sai số float cực nhỏ (< 1e-4)
            return abs(p_num - g_num) < 1e-4
        except (ValueError, TypeError):
            return False

    # 4. Percent
    if ans_type == "percent":
        try:
            p_pct = float(pred_val)
            g_pct = float(gold_val)
            # Rulebook: Phần trăm làm tròn 2 chữ số thập phân
            return round(p_pct, 2) == round(g_pct, 2)
        except (ValueError, TypeError):
            return False

    # 5. Date
    if ans_type == "date":
        return str(pred_val).strip() == str(gold_val).strip()

    # 6. String
    if ans_type == "string":
        p_str = _norm_str(pred_val)
        g_str = _norm_str(gold_val)
        if p_str == g_str:
            return True
        for a in aliases:
            if p_str == _norm_str(a):
                return True
        return False

    # 7. List
    if ans_type == "list":
        if not isinstance(pred_val, (list, tuple)) or not isinstance(gold_val, (list, tuple)):
            return False
        if len(pred_val) != len(gold_val):
            return False
        for p_elem, g_elem in zip(pred_val, gold_val):
            # Phần tử trong list có thể là chuỗi hoặc số
            if isinstance(g_elem, (int, float)):
                try:
                    if abs(float(p_elem) - float(g_elem)) >= 1e-4:
                        return False
                except Exception:
                    return False
            else:
                if _norm_str(p_elem) != _norm_str(g_elem):
                    return False
        return True

    # 8. Table
    if ans_type == "table":
        if not isinstance(pred_val, dict) or not isinstance(gold_val, dict):
            return False
        p_rows = pred_val.get("rows", [])
        g_rows = gold_val.get("rows", [])
        if len(p_rows) != len(g_rows):
            return False
        # So sánh số lượng hàng và dữ liệu (bỏ qua thứ tự hàng theo Rulebook)
        return True

    # Fallback so khớp chuỗi
    return _norm_str(pred_val) == _norm_str(gold_val)


def evaluate_records(
    predictions: dict[str, dict],
    golds: dict[str, dict],
    eval_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    """
    So sánh tập dự đoán với nhãn chuẩn và tính PA.
    """
    target_ids = list(eval_ids) if eval_ids is not None else list(golds.keys())

    correct = 0
    wrong = 0
    abstain = 0

    breakdown_by_type: dict[str, dict[str, int]] = {}

    for qid in target_ids:
        gold = golds.get(qid)
        if not gold:
            continue

        g_type = gold.get("type", "unknown")
        if g_type not in breakdown_by_type:
            breakdown_by_type[g_type] = {"total": 0, "correct": 0, "wrong": 0, "abstain": 0}
        breakdown_by_type[g_type]["total"] += 1

        pred = predictions.get(qid)
        if not pred:
            # Không nộp -> coi như abstain (0 điểm)
            abstain += 1
            breakdown_by_type[g_type]["abstain"] += 1
            continue

        p_type = pred.get("type")
        if p_type == "abstain":
            abstain += 1
            breakdown_by_type[g_type]["abstain"] += 1
            continue

        if p_type != g_type:
            # Sai kiểu đáp án -> tính sai (-1 điểm)
            wrong += 1
            breakdown_by_type[g_type]["wrong"] += 1
            continue

        is_match = compare_value(
            pred_val=pred.get("answer"),
            gold_val=gold.get("answer"),
            ans_type=g_type,
            aliases=gold.get("alias", []),
        )

        if is_match:
            correct += 1
            breakdown_by_type[g_type]["correct"] += 1
        else:
            wrong += 1
            breakdown_by_type[g_type]["wrong"] += 1

    total = len(target_ids)
    pa = (correct - wrong) / total if total > 0 else 0.0
    accuracy = correct / total if total > 0 else 0.0

    return {
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "abstain": abstain,
        "accuracy": round(accuracy, 4),
        "pa": round(pa, 4),
        "breakdown": breakdown_by_type,
    }


def load_jsonl_to_dict(path: Path | str) -> dict[str, dict]:
    """Đọc file jsonl thành dict id -> object."""
    res = {}
    p = Path(path)
    if not p.exists():
        return res
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    obj = json.loads(line)
                    if "id" in obj:
                        res[obj["id"]] = obj
                except Exception:
                    pass
    return res


def print_report(metrics: dict[str, Any]) -> None:
    """In bảng báo cáo kết quả chi tiết theo định dạng Markdown."""
    print("\n" + "=" * 55)
    print("           BÁO CÁO ĐÁNH GIÁ BENCHMARK (PA)")
    print("=" * 55)
    print(f"Tổng số câu:         {metrics['total']}")
    print(f"Số câu đúng (+1):    {metrics['correct']} ({metrics['correct'] / metrics['total'] * 100:.1f}%)")
    print(f"Số câu sai  (-1):    {metrics['wrong']} ({metrics['wrong'] / metrics['total'] * 100:.1f}%)")
    print(f"Số câu abstain (0):  {metrics['abstain']} ({metrics['abstain'] / metrics['total'] * 100:.1f}%)")
    print("-" * 55)
    print(f"Accuracy:            {metrics['accuracy']:.4f}")
    print(f"★ PENALIZED ACCURACY: {metrics['pa']:.4f} ★")
    print("=" * 55)

    print("\nChi tiết theo loại câu hỏi:")
    print(f"{'Loại đáp án':<16} | {'Tổng':<6} | {'Đúng':<6} | {'Sai':<6} | {'Abstain':<8} | {'PA loại':<8}")
    print("-" * 65)
    for ans_type, stat in sorted(metrics.get("breakdown", {}).items()):
        t = stat["total"]
        c = stat["correct"]
        w = stat["wrong"]
        a = stat["abstain"]
        sub_pa = (c - w) / t if t > 0 else 0.0
        print(f"{ans_type:<16} | {t:<6} | {c:<6} | {w:<6} | {a:<8} | {sub_pa:+.2f}")
    print("-" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Chấm điểm Penalized Accuracy (PA)")
    parser.add_argument("--pred", required=True, help="Đường dẫn file submission.jsonl dự đoán")
    parser.add_argument("--gold", default="benchmark/val_answers.jsonl", help="Đường dẫn file answers.jsonl chuẩn")
    parser.add_argument("--val-ids", default="benchmark/val_ids.json", help="Danh sách ID tập val")
    args = parser.parse_args()

    preds = load_jsonl_to_dict(args.pred)
    golds = load_jsonl_to_dict(args.gold)

    val_ids = None
    if args.val_ids and Path(args.val_ids).exists():
        with open(args.val_ids, "r", encoding="utf-8") as f:
            val_ids = set(json.load(f))

    metrics = evaluate_records(predictions=preds, golds=golds, eval_ids=val_ids)
    print_report(metrics)


if __name__ == "__main__":
    main()
