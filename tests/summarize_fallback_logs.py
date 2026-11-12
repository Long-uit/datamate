"""
Script: tests/summarize_fallback_logs.py
Mục đích: Tổng hợp log JSON sinh mã (`llm_generation.attempts`) sau khi chạy
          pipeline đã gắn telemetry cho các câu rơi vào fallback `return None`.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_FALLBACK_IDS = [
    "q_0285dfd1bb28",  # biz_127 (5 bảng CSV)
    "q_0266c6b24cbf",  # biz_106 (10 bảng XLSX)
    "q_047c8277cc35",  # biz_108 (7 bảng XLSX)
    "q_047586efd4bf",  # biz_117 (7 file XLSX)
    "q_03cf8b6c4b16",  # biz_105 (6 bảng XLSX)
    "q_02f8f6235ddb",  # biz_115 (4 bảng XLSX)
    "q_026fabde15fc",  # biz_103 (2 file XLSX)
    "q_02eb42db6665",  # biz_125 (1 bảng CSV)
]


def has_complete_solution_body(raw_text: str, extracted_code: str) -> bool:
    """Kiểm tra sơ bộ xem `def solution` trong raw_text / extracted_code có thân hàm hợp lệ về mặt AST không."""
    for candidate in (extracted_code, raw_text):
        if not candidate or "def solution" not in candidate:
            continue
        idx = candidate.find("def solution")
        snippet = candidate[idx:].strip()
        if "```" in snippet:
            snippet = snippet.split("```", 1)[0].strip()
        try:
            tree = ast.parse(snippet)
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "solution":
                    has_ret = any(isinstance(n, ast.Return) for n in ast.walk(node))
                    if has_ret:
                        return True
        except SyntaxError:
            pass
    return False


def classify_attempt(att: Dict[str, Any]) -> str:
    """Phân loại sơ bộ nguyên nhân fallback cho một lần gọi `_generate_raw`."""
    raw_text = att.get("raw_text") or ""
    extracted = att.get("extracted_code") or ""
    finish = att.get("finish_reason")
    ast_valid = bool(att.get("ast_valid", False))
    complete_fn = has_complete_solution_body(raw_text, extracted)

    if ast_valid:
        return "valid (khong roi AST fallback)"
    if finish == "length":
        if complete_fn:
            return "(a) Ham hoan chinh nhung model viet thua / khong dung -> dung max_new_tokens"
        return "(b) Bi cat giua ham do dung max_new_tokens (finish_reason=length)"
    if complete_fn:
        return "(a) Ham hoan chinh nhung extractor / stopping / phan du lam hong AST"
    if finish == "stop":
        return "(c) Loi cu phap that du model da tu dung (finish_reason=stop)"
    return "(d) Khac (error / OOM / rong)"


def summarize_log_dir(log_dir: Path) -> List[Dict[str, Any]]:
    """Đọc toàn bộ file JSON trong `log_dir` và trích xuất bảng chẩn đoán fallback."""
    rows: List[Dict[str, Any]] = []
    for json_path in sorted(log_dir.glob("*.json")):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        qid = payload.get("question_id") or json_path.stem
        biz = payload.get("business_id", "?")
        llm_gen = payload.get("llm_generation") or {}
        attempts = llm_gen.get("attempts") or []
        ans = payload.get("answer") or {}

        att_summaries: List[Dict[str, Any]] = []
        for att in attempts:
            raw = att.get("raw_text") or ""
            extracted = att.get("extracted_code") or ""
            att_summaries.append({
                "attempt": att.get("attempt"),
                "role": att.get("role"),
                "prompt_tokens": att.get("prompt_tokens"),
                "prompt_tokens_used": att.get("prompt_tokens_used"),
                "truncated": att.get("truncated"),
                "generated_tokens": att.get("generated_tokens"),
                "finish_reason": att.get("finish_reason"),
                "stop_detail": att.get("stop_detail"),
                "backtick_fence_count": raw.count("```"),
                "starts_with_python_fence": raw.lstrip().startswith("```python"),
                "has_complete_solution_body": has_complete_solution_body(raw, extracted),
                "ast_valid": att.get("ast_valid"),
                "ast_error": att.get("ast_error"),
                "raw_head_200": raw[:200],
                "raw_tail_300": raw[-300:] if len(raw) > 300 else raw,
                "category": classify_attempt(att),
            })

        rows.append({
            "question_id": qid,
            "business_id": biz,
            "pred_type": ans.get("type"),
            "pred_answer": ans.get("answer"),
            "used_fallback_return_none": llm_gen.get("used_fallback_return_none"),
            "attempts": att_summaries,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Tổng hợp log telemetry LLM cho các câu fallback.")
    parser.add_argument("--log_dir", type=str, default="results/diag_8q_logs", help="Thư mục chứa log <qid>.json")
    parser.add_argument("--out_json", type=str, default=None, help="Tùy chọn lưu bản tóm tắt ra JSON")
    args = parser.parse_args()

    log_dir = Path(args.log_dir)
    if not log_dir.exists():
        raise SystemExit(f"Khong tim thay thu muc log: {log_dir}")

    rows = summarize_log_dir(log_dir)
    for row in rows:
        print("=" * 80)
        print(
            f"{row['question_id']} ({row['business_id']}) | pred={row['pred_type']}:{row['pred_answer']} "
            f"| fallback_return_none={row['used_fallback_return_none']}"
        )
        for att in row["attempts"]:
            print(
                f"  - Attempt {att['attempt']} [{att['role']}]: prompt={att['prompt_tokens']}->"
                f"{att['prompt_tokens_used']} (trunc={att['truncated']}), gen={att['generated_tokens']}, "
                f"finish={att['finish_reason']} ({att['stop_detail']}), ```={att['backtick_fence_count']}, "
                f"starts_```python={att['starts_with_python_fence']}, complete_body={att['has_complete_solution_body']}, "
                f"ast_valid={att['ast_valid']}, ast_err={att['ast_error']}"
            )
            print(f"    Category: {att['category']}")
            print(f"    Head(200): {att['raw_head_200']!r}")
            print(f"    Tail(300): {att['raw_tail_300']!r}")

    if args.out_json:
        out_p = Path(args.out_json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nDa luu tom tat tai: {out_p}")


if __name__ == "__main__":
    main()
