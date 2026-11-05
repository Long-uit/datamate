"""
error_analysis.py — Công cụ phân tích lỗi chuyên sâu (Daily Error Analysis) cho DataMate.

Dựa trên nghiên cứu BIRD (Evaluating Language Models on Enterprise Text-to-SQL Workflows)
và thước đo độ tin cậy TrustSQL:
- Tự động nhóm các câu bị phạt điểm (-1) theo nguyên nhân gốc rễ (Root Cause Analysis).
- Phân tích chuyên sâu nhóm unanswerable bị đoán mò hoặc dự đoán sai.
- Chuẩn hóa dung sai so khớp số học và phần trăm bám sát Điều 9 Rulebook (percent làm tròn 2 chữ số).
- Xuất báo cáo định dạng Markdown chi tiết hỗ trợ đội ngũ cải tiến hàng ngày.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ErrorRecord:
    question_id: str
    question: str
    pred_answer: Any
    pred_type: str
    truth_answer: Any
    truth_type: str
    score: int                  # +1, -1, 0
    error_category: str         # "CORRECT", "UNANSWERABLE_MISSED", "NUMERIC_MISMATCH", etc.
    details: str = ""


@dataclass
class AnalysisSummary:
    total: int = 0
    correct: int = 0
    wrong: int = 0
    abstain: int = 0
    penalized_accuracy: float = 0.0
    error_counts: dict[str, int] = field(default_factory=dict)
    records: list[ErrorRecord] = field(default_factory=list)


def classify_error(pred_item: dict[str, Any], truth_item: dict[str, Any]) -> tuple[int, str, str]:
    """
    Xác định điểm số (+1, -1, 0) và phân loại lỗi giữa kết quả dự đoán và đáp án chuẩn.
    Tuân thủ tuyệt đối quy định so khớp tại Điều 9 Rulebook.
    """
    p_type = str(pred_item.get("type", "")).strip().lower()
    t_type = str(truth_item.get("type", "")).strip().lower()
    p_ans = pred_item.get("answer")
    t_ans = truth_item.get("answer")

    # Trường hợp kiêng trả lời (Abstain) -> 0 điểm an toàn
    if p_type == "abstain":
        return 0, "ABSTAIN", "Mô hình chủ động từ chối trả lời (0 điểm)"

    # Trường hợp câu hỏi không thể trả lời (Unanswerable)
    if t_type == "unanswerable":
        if p_type == "unanswerable":
            return 1, "CORRECT_UNANSWERABLE", "Từ chối chính xác câu hỏi bất khả thi (+1 điểm)"
        else:
            return -1, "UNANSWERABLE_MISSED", f"Bị phạt: Đáng lẽ unanswerable nhưng cố đoán {p_ans} (-1 điểm)"

    # Nếu câu hỏi có đáp án mà dự đoán lại là unanswerable
    if p_type == "unanswerable":
        return -1, "UNANSWERABLE_FALSE_POSITIVE", f"Bị phạt: Câu hỏi có đáp án nhưng từ chối unanswerable (-1 điểm)"

    # So sánh kiểu dữ liệu
    if p_type != t_type:
        return -1, "TYPE_MISMATCH", f"Lệch kiểu: Dự đoán {p_type} nhưng đáp án là {t_type} (-1 điểm)"

    # So sánh giá trị theo từng kiểu
    # 1. Số (number: tiền nguyên, số đếm, sai số float < 1e-4)
    if p_type == "number":
        try:
            val_p = float(p_ans)
            val_t = float(t_ans)
            if abs(val_p - val_t) < 1e-4:
                return 1, "CORRECT_NUMERIC", "Khớp số học hoàn hảo (+1 điểm)"
            else:
                return -1, "NUMERIC_MISMATCH", f"Sai số: Dự đoán {val_p} != Đáp án {val_t} (-1 điểm)"
        except (ValueError, TypeError):
            return -1, "PARSE_ERROR", f"Không parse được số từ {p_ans} hoặc {t_ans} (-1 điểm)"

    # 2. Phần trăm (percent: làm tròn 2 chữ số thập phân theo Rulebook / evaluate.py)
    if p_type == "percent":
        try:
            val_p = float(p_ans)
            val_t = float(t_ans)
            if round(val_p, 2) == round(val_t, 2) or abs(val_p - val_t) <= 0.01:
                return 1, "CORRECT_NUMERIC", f"Khớp phần trăm ({round(val_p, 2)}% ~ {round(val_t, 2)}%) (+1 điểm)"
            else:
                return -1, "NUMERIC_MISMATCH", f"Sai phần trăm: Dự đoán {val_p}% != Đáp án {val_t}% (-1 điểm)"
        except (ValueError, TypeError):
            return -1, "PARSE_ERROR", f"Không parse được số từ {p_ans} hoặc {t_ans} (-1 điểm)"

    # 3. Chuỗi hoặc ngày
    if p_type in ("string", "date"):
        str_p = str(p_ans).strip().lower()
        str_t = str(t_ans).strip().lower()
        if str_p == str_t:
            return 1, "CORRECT_TEXT", "Khớp chuỗi chính xác (+1 điểm)"
        return -1, "TEXT_MISMATCH", f"Lệch chuỗi: '{p_ans}' != '{t_ans}' (-1 điểm)"

    # 4. Boolean
    if p_type == "boolean":
        bool_p = bool(p_ans)
        bool_t = bool(t_ans)
        if bool_p == bool_t:
            return 1, "CORRECT_BOOLEAN", "Khớp boolean đúng (+1 điểm)"
        return -1, "BOOLEAN_MISMATCH", f"Sai boolean: {bool_p} != {bool_t} (-1 điểm)"

    # 5. List hoặc Table
    if json.dumps(p_ans, sort_keys=True) == json.dumps(t_ans, sort_keys=True):
        return 1, "CORRECT_COMPLEX", "Khớp danh sách/bảng chính xác (+1 điểm)"

    return -1, "VALUE_MISMATCH", f"Sai giá trị chi tiết (-1 điểm)"


def run_error_analysis(
    predictions: list[dict[str, Any]] | dict[str, dict[str, Any]],
    ground_truth: list[dict[str, Any]] | dict[str, dict[str, Any]],
) -> AnalysisSummary:
    """Thực hiện phân tích toàn bộ tập dữ liệu dự đoán so với ground truth."""
    # Chuẩn hóa về dict {id: item}
    preds_dict: dict[str, dict[str, Any]] = {}
    if isinstance(predictions, list):
        for item in predictions:
            if "id" in item:
                preds_dict[str(item["id"])] = item
    else:
        preds_dict = predictions

    truth_dict: dict[str, dict[str, Any]] = {}
    if isinstance(ground_truth, list):
        for item in ground_truth:
            if "id" in item:
                truth_dict[str(item["id"])] = item
    else:
        truth_dict = ground_truth

    summary = AnalysisSummary()
    summary.total = len(truth_dict)

    for q_id, t_item in truth_dict.items():
        p_item = preds_dict.get(q_id, {"type": "abstain", "answer": None})
        score, category, details = classify_error(p_item, t_item)

        rec = ErrorRecord(
            question_id=q_id,
            question=t_item.get("question", ""),
            pred_answer=p_item.get("answer"),
            pred_type=p_item.get("type", ""),
            truth_answer=t_item.get("answer"),
            truth_type=t_item.get("type", ""),
            score=score,
            error_category=category,
            details=details,
        )
        summary.records.append(rec)

        if score > 0:
            summary.correct += 1
        elif score < 0:
            summary.wrong += 1
        else:
            summary.abstain += 1

        summary.error_counts[category] = summary.error_counts.get(category, 0) + 1

    if summary.total > 0:
        summary.penalized_accuracy = round((summary.correct - summary.wrong) / summary.total, 4)

    return summary


def generate_markdown_report(summary: AnalysisSummary) -> str:
    """Sinh báo cáo lỗi trực quan dưới dạng GitHub Flavored Markdown."""
    lines = [
        "# 📊 BÁO CÁO PHÂN TÍCH LỖI VÀ ĐỘ TIN CẬY (ERROR ANALYSIS)",
        "",
        "## 1. Tổng quan Điểm số & Chỉ số PA",
        f"- **Tổng số câu hỏi đánh giá:** {summary.total}",
        f"- **Số câu đúng (+1 điểm):** {summary.correct} ({round(summary.correct / summary.total * 100, 2) if summary.total else 0}%)",
        f"- **Số câu bị phạt (-1 điểm):** {summary.wrong} ({round(summary.wrong / summary.total * 100, 2) if summary.total else 0}%)",
        f"- **Số câu từ chối an toàn (0 điểm):** {summary.abstain} ({round(summary.abstain / summary.total * 100, 2) if summary.total else 0}%)",
        f"- **Penalized Accuracy (PA):** **{summary.penalized_accuracy}**",
        "",
        "## 2. Phân bố Nguyên nhân Lỗi (Error Taxonomy)",
        "| Danh mục nguyên nhân | Số lượng | Tỷ lệ (%) | Đánh giá |",
        "|---|:---:|:---:|---|",
    ]

    for cat, count in sorted(summary.error_counts.items(), key=lambda x: x[1], reverse=True):
        pct = round(count / summary.total * 100, 2) if summary.total else 0
        status = "✅ Tốt" if "CORRECT" in cat else ("⚠️ Mất điểm" if count > 0 else "Trung tính")
        lines.append(f"| `{cat}` | {count} | {pct}% | {status} |")

    # Liệt kê các câu hỏi bị phạt điểm nặng nhất
    penalized = [r for r in summary.records if r.score < 0]
    if penalized:
        lines.extend([
            "",
            "## 3. Danh sách các câu bị phạt điểm (-1) cần khắc phục",
            "| ID | Câu hỏi | Dự đoán | Đáp án chuẩn | Nguyên nhân |",
            "|---|---|---|---|---|",
        ])
        for p in penalized[:15]:
            q_snippet = (p.question[:50] + "...") if len(p.question) > 50 else p.question
            lines.append(f"| `{p.question_id}` | {q_snippet} | `{p.pred_answer}` ({p.pred_type}) | `{p.truth_answer}` ({p.truth_type}) | {p.error_category} |")

    return "\n".join(lines)


def main() -> None:
    """CLI runner để chạy Error Analysis từ dòng lệnh."""
    parser = argparse.ArgumentParser(description="Chạy Error Analysis so sánh kết quả dự đoán với ground truth.")
    parser.add_argument("--pred", type=str, required=True, help="Đường dẫn file submission.jsonl")
    parser.add_argument("--truth", type=str, required=True, help="Đường dẫn file answers.jsonl chuẩn")
    parser.add_argument("--output", type=str, default="benchmark/error_report.md", help="Đường dẫn file markdown report xuất ra")
    args = parser.parse_args()

    pred_path = Path(args.pred)
    truth_path = Path(args.truth)
    if not pred_path.exists():
        print(f"[Lỗi] Không tìm thấy file predictions tại: {pred_path}")
        sys.exit(1)
    if not truth_path.exists():
        print(f"[Lỗi] Không tìm thấy file ground truth tại: {truth_path}")
        sys.exit(1)

    with open(pred_path, "r", encoding="utf-8") as f:
        preds = [json.loads(line) for line in f if line.strip()]
    with open(truth_path, "r", encoding="utf-8") as f:
        truths = [json.loads(line) for line in f if line.strip()]

    summary = run_error_analysis(preds, truths)
    report = generate_markdown_report(summary)

    out_p = Path(args.output)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(report, encoding="utf-8")
    print(f"✓ Đã xuất báo cáo phân tích lỗi vào {out_p.resolve()}")
    print(f"• PA: {summary.penalized_accuracy} | Đúng: {summary.correct} | Sai: {summary.wrong} | Abstain: {summary.abstain}")


if __name__ == "__main__":
    main()
