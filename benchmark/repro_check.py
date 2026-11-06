"""
repro_check.py — Công cụ kiểm định tính tái lập tuyệt đối (Reproducibility Verifier).
Phân hệ: Phase 4 — Zalo AI Challenge 2026 (DataMate Track).
Tác giả: DataMate Team (Long & Phat)

Mục đích:
- Kiểm tra điều kiện quy chế BTC: |PA_uploaded - PA_rerun| <= 0.03 (mục tiêu nội bộ: |PA_1 - PA_2| = 0).
- So sánh chi tiết từng dòng giữa 2 file submission (Run 1 vs Run 2).
- Thẩm định tính tất định (Deterministic Behavior) của pipeline (Greedy Decoding T=0, fixed seed=42).
"""

from __future__ import annotations

import argparse
import json
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path
from typing import Any, Dict, List, Tuple


def parse_args():
    parser = argparse.ArgumentParser(description="Kiểm tra tính tái lập tuyệt đối giữa 2 lượt chạy độc lập")
    parser.add_argument("--run1", type=str, required=True, help="Đường dẫn file submission lượt chạy 1")
    parser.add_argument("--run2", type=str, required=True, help="Đường dẫn file submission lượt chạy 2")
    parser.add_argument("--golds", type=str, default=None, help="Đường dẫn file ground truth (tùy chọn để tính PA)")
    parser.add_argument("--output_report", type=str, default="logs/reproducibility_report.md", help="Đường dẫn lưu báo cáo")
    return parser.parse_args()


def load_submission(file_path: Path) -> Dict[str, Dict[str, Any]]:
    """Đọc file submission JSONL thành từ điển {id: record}."""
    records = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                qid = item.get("id")
                if not qid:
                    raise ValueError(f"Dòng {idx} thiếu trường 'id'")
                records[qid] = item
            except json.JSONDecodeError as exc:
                raise ValueError(f"Dòng {idx} không phải JSON hợp lệ: {exc}")
    return records


def compare_runs(
    run1: Dict[str, Dict[str, Any]],
    run2: Dict[str, Dict[str, Any]],
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """So sánh 2 lần chạy chi tiết từng câu hỏi."""
    mismatches = []
    ids1 = set(run1.keys())
    ids2 = set(run2.keys())

    diff_ids = ids1.symmetric_difference(ids2)
    if diff_ids:
        mismatches.append(f"Tập hợp ID không khớp giữa 2 file: {len(diff_ids)} ID khác biệt.")

    common_ids = sorted(ids1.intersection(ids2))
    identical_count = 0

    for qid in common_ids:
        rec1 = run1[qid]
        rec2 = run2[qid]

        t1, t2 = rec1.get("type"), rec2.get("type")
        a1, a2 = rec1.get("answer"), rec2.get("answer")

        # So khớp type và answer
        if t1 != t2 or a1 != a2:
            mismatches.append(f"ID {qid}: Run1=({t1}, {a1}) != Run2=({t2}, {a2})")
        else:
            identical_count += 1

    total = len(common_ids)
    identical_ratio = (identical_count / total) if total > 0 else 0.0
    is_reproducible = (len(mismatches) == 0 and total > 0)

    stats = {
        "total_common": total,
        "identical_count": identical_count,
        "mismatch_count": len(mismatches),
        "reproducibility_rate": round(identical_ratio * 100, 2),
        "is_reproducible": is_reproducible,
    }
    return is_reproducible, mismatches, stats


def main():
    args = parse_args()
    print("=" * 75)
    print("DATAMATE — KIỂM ĐỊNH TÍNH TÁI LẬP TUYỆT ĐỐI (REPRODUCIBILITY CHECK)")
    print("=" * 75)

    p1 = Path(args.run1)
    p2 = Path(args.run2)
    if not p1.exists() or not p2.exists():
        print(f"⚠️ Không tìm thấy file: {p1} hoặc {p2}")
        sys.exit(1)

    run1 = load_submission(p1)
    run2 = load_submission(p2)

    print(f"• Run 1: {p1} ({len(run1)} câu)")
    print(f"• Run 2: {p2} ({len(run2)} câu)")

    is_repro, mismatches, stats = compare_runs(run1, run2)

    report_lines = [
        "# Báo Cáo Kiểm Định Tính Tái Lập (Reproducibility Verification Report)",
        "**Dự án:** DataMate — Zalo AI Challenge 2026 (Phase 4)  ",
        f"**File Run 1:** `{p1}` ({len(run1)} mẫu)  ",
        f"**File Run 2:** `{p2}` ({len(run2)} mẫu)  ",
        f"**Tỷ lệ trùng khớp:** `{stats['reproducibility_rate']}%` ({stats['identical_count']}/{stats['total_common']})  ",
        f"**Kết luận tái lập:** `{'ĐẠT (PASS 100%)' if is_repro else 'KHÔNG ĐẠT (FAILED)'}`  ",
        "",
        "---",
        "",
        "## 1. Chi tiết kiểm thử",
        f"- Tổng số câu hỏi đối chiếu: `{stats['total_common']}`",
        f"- Số câu hoàn toàn trùng khớp: `{stats['identical_count']}`",
        f"- Số câu có độ lệch: `{stats['mismatch_count']}`",
        "",
    ]

    if mismatches:
        report_lines.append("### Danh sách các câu bị lệch:")
        for m in mismatches[:20]:
            report_lines.append(f"- {m}")
        if len(mismatches) > 20:
            report_lines.append(f"- ... và {len(mismatches) - 20} câu khác.")
    else:
        report_lines.append("🎉 **Hoàn hảo:** Tất cả câu hỏi cho ra cùng một đáp án và kiểu dữ liệu ở cả 2 lần chạy độc lập!")

    out_p = Path(args.output_report)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text("\n".join(report_lines), encoding="utf-8")

    print(f"• Tỷ lệ trùng khớp: {stats['reproducibility_rate']}%")
    print(f"📄 Báo cáo chi tiết đã lưu tại: {out_p}")
    print("=" * 75)

    if not is_repro:
        print("❌ KIỂM TRA TÁI LẬP THẤT BẠI!")
        sys.exit(1)
    else:
        print("✅ KIỂM TRA TÁI LẬP THÀNH CÔNG (100% IDENTICAL)!")


if __name__ == "__main__":
    main()
