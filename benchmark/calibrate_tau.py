"""
calibrate_tau.py — Công cụ quét tìm ngưỡng từ chối tối ưu tau* (Calibrated Abstention Gate).
Phân hệ: Phase 4 — Zalo AI Challenge 2026 (DataMate Track).
Tác giả: DataMate Team (Long & Phat)

Mục đích:
- Nhận danh sách dự đoán kèm điểm tin cậy C (confidence score) và file đáp án chuẩn (ground truth).
- Quét ngưỡng tau* trong dải [0.10, 0.90] với bước nhảy (step) 0.02.
- Với mỗi ngưỡng tau, các câu có C < tau được chuyển thành 'abstain' (0 điểm).
- Tính toán Penalized Accuracy (PA): PA = (Correct - Wrong) / Total.
- Xác định giá trị tau* tối đa hóa điểm số PA và xuất bảng phân tích Markdown.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from benchmark.evaluate import compare_value, load_jsonl_to_dict


def parse_args():
    parser = argparse.ArgumentParser(description="Quét tìm ngưỡng tau* tối ưu cho Calibrated Abstention Gate")
    parser.add_argument(
        "--preds",
        type=str,
        default="benchmark/splits/business_holdout_v1/fold_0/val_answers.jsonl",
        help="Đường dẫn file dự đoán (kèm trường confidence)",
    )
    parser.add_argument(
        "--golds",
        type=str,
        default="benchmark/splits/business_holdout_v1/fold_0/val_answers.jsonl",
        help="Đường dẫn file ground truth",
    )
    parser.add_argument("--min_tau", type=float, default=0.20, help="Ngưỡng tau tối thiểu (mặc định: 0.20)")
    parser.add_argument("--max_tau", type=float, default=0.85, help="Ngưỡng tau tối đa (mặc định: 0.85)")
    parser.add_argument("--step", type=float, default=0.05, help="Bước nhảy quét tau (mặc định: 0.05)")
    parser.add_argument("--output_report", type=str, default="logs/calibrated_tau_report.md", help="Đường dẫn lưu báo cáo")
    return parser.parse_args()


def simulate_abstention_at_threshold(
    records: List[Dict[str, Any]],
    golds: Dict[str, Dict[str, Any]],
    tau: float,
) -> Dict[str, Any]:
    """Mô phỏng chấm điểm PA khi áp dụng ngưỡng tau."""
    total = len(golds)
    correct = 0
    wrong = 0
    abstained = 0

    for rec in records:
        qid = rec.get("id")
        if qid not in golds:
            continue

        gold = golds[qid]
        gold_type = gold["type"]
        gold_ans = gold.get("answer")
        conf = float(rec.get("confidence", 1.0))

        # Nếu độ tin cậy thấp hơn ngưỡng tau -> Chủ động Abstain (0 điểm)
        if conf < tau or rec.get("type") == "abstain":
            abstained += 1
            continue

        pred_val = rec.get("answer")
        pred_type = rec.get("type")

        # So khớp đáp án
        if pred_type == gold_type:
            matched = compare_value(pred_val, gold_ans, gold_type, aliases=gold.get("alias", []))
            if matched:
                correct += 1
            else:
                wrong += 1
        else:
            wrong += 1

    pa = (correct - wrong) / total if total > 0 else 0.0
    accuracy = correct / total if total > 0 else 0.0
    coverage = (correct + wrong) / total if total > 0 else 0.0

    return {
        "tau": round(tau, 3),
        "total": total,
        "correct": correct,
        "wrong": wrong,
        "abstained": abstained,
        "pa": round(pa, 4),
        "accuracy": round(accuracy, 4),
        "coverage": round(coverage, 4),
    }


def find_optimal_tau(
    preds_data: List[Dict[str, Any]],
    golds_dict: Dict[str, Dict[str, Any]],
    min_tau: float = 0.20,
    max_tau: float = 0.85,
    step: float = 0.05,
) -> Tuple[float, List[Dict[str, Any]]]:
    """Quét toàn bộ dải tau và trả về ngưỡng tối ưu nhất."""
    results = []
    best_tau = min_tau
    best_pa = -999.0

    curr_tau = min_tau
    while curr_tau <= max_tau + 1e-6:
        stats = simulate_abstention_at_threshold(preds_data, golds_dict, curr_tau)
        results.append(stats)
        if stats["pa"] > best_pa:
            best_pa = stats["pa"]
            best_tau = stats["tau"]
        curr_tau += step

    return best_tau, results


def generate_markdown_report(
    best_tau: float,
    results: List[Dict[str, Any]],
    output_path: Path,
) -> str:
    """Tạo báo cáo chi tiết quá trình quét ngưỡng dạng Markdown."""
    lines = [
        "# Báo Cáo Hiệu Chuẩn Ngưỡng Từ Chối (Calibrated Abstention Report)",
        "**Dự án:** DataMate — Zalo AI Challenge 2026 (Phase 4)  ",
        f"**Ngưỡng tối ưu tìm được ($\tau^*$):** `{best_tau:.2f}`  ",
        "",
        "---",
        "",
        "## 1. Bảng Kết Quả Quét Ngưỡng $\\tau$",
        "",
        "| Ngưỡng $\\tau$ | Tổng câu | Số đúng (+1) | Số sai (-1) | Số từ chối (0) | Độ bao phủ (Coverage) | Penalized Accuracy (PA) | Đánh giá |",
        "|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for r in results:
        is_best = " **Tối ưu (Best $\\tau^*$)**" if abs(r["tau"] - best_tau) < 1e-4 else ""
        lines.append(
            f"| `{r['tau']:.2f}` | {r['total']} | {r['correct']} | {r['wrong']} | {r['abstained']} | {r['coverage']*100:.1f}% | **{r['pa']:.4f}** |{is_best} |"
        )

    lines.extend([
        "",
        "## 2. Khuyến nghị ứng dụng cho Production",
        f"- Cập nhật cấu hình `tau_star: {best_tau:.2f}` trong `config/default.yaml`.",
        f"- Sử dụng cờ `--tau_star {best_tau:.2f}` khi khởi chạy `predict.py` hoặc `predict.sh`.",
        "- Cơ chế này bảo vệ an toàn bảng xếp hạng trước các câu hỏi rủi ro cao hoặc sinh lỗi runtime.",
    ])

    content = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return content


def main():
    args = parse_args()
    print("=" * 75)
    print("DATAMATE — HIỆU CHUẨN NGƯỠNG CALIBRATED ABSTENTION GATE (PHASE 4)")
    print("=" * 75)

    preds_file = Path(args.preds)
    golds_file = Path(args.golds)
    if not preds_file.exists() or not golds_file.exists():
        print(f"⚠️ Không tìm thấy file: {preds_file} hoặc {golds_file}")
        sys.exit(1)

    preds_data = []
    with open(preds_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                preds_data.append(json.loads(line))

    golds_dict = load_jsonl_to_dict(golds_file)
    print(f"• Số lượng câu dự đoán : {len(preds_data)}")
    print(f"• Số lượng ground truth: {len(golds_dict)}")
    print(f"• Quét dải tau          : [{args.min_tau:.2f} ➔ {args.max_tau:.2f}] (step {args.step:.2f})")

    best_tau, results = find_optimal_tau(
        preds_data=preds_data,
        golds_dict=golds_dict,
        min_tau=args.min_tau,
        max_tau=args.max_tau,
        step=args.step,
    )

    out_p = Path(args.output_report)
    generate_markdown_report(best_tau, results, out_p)

    print("=" * 75)
    print(f"✅ ĐÃ TÌM ĐƯỢC NGƯỠNG TỐI ƯU: tau* = {best_tau:.2f}")
    print(f"📄 Báo cáo chi tiết đã lưu tại: {out_p}")
    print("=" * 75)


if __name__ == "__main__":
    main()
