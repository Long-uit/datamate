"""
Tệp kiểm thử: tests/llm_execution/test_summarize_fallback_logs.py
Mục đích: Kiểm tra bộ phân tích log fallback LLM (`summarize_fallback_logs.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.summarize_fallback_logs import classify_attempt, has_complete_solution_body, summarize_log_dir


def test_has_complete_solution_body_detects_extra_prose_after_fence():
    raw = "def solution(data):\n    return 100\n```\nĐây là code giải thích thêm..."
    assert has_complete_solution_body(raw, "") is True
    cat = classify_attempt({
        "raw_text": raw,
        "extracted_code": "def solution(data):\n    return 100",
        "finish_reason": "length",
        "ast_valid": False,
    })
    assert cat.startswith("(a)")


def test_classify_truncated_and_syntax_error():
    cat_b = classify_attempt({
        "raw_text": "def solution(data):\n    df = data['a'\n",
        "extracted_code": "def solution(data):\n    df = data['a'",
        "finish_reason": "length",
        "ast_valid": False,
    })
    assert cat_b.startswith("(b)")

    cat_c = classify_attempt({
        "raw_text": "```python\ndef solution(:\n    pass\n```",
        "extracted_code": "def solution(:\n    pass",
        "finish_reason": "stop",
        "ast_valid": False,
    })
    assert cat_c.startswith("(c)")


def test_summarize_log_dir_reads_llm_generation_attempts(tmp_path: Path):
    sample = {
        "question_id": "q_test1",
        "business_id": "biz_999",
        "answer": {"id": "q_test1", "type": "abstain", "answer": None},
        "llm_generation": {
            "used_fallback_return_none": True,
            "attempts": [
                {
                    "attempt": 0,
                    "role": "initial",
                    "prompt_tokens": 4400,
                    "prompt_tokens_used": 3584,
                    "truncated": True,
                    "generated_tokens": 1536,
                    "finish_reason": "length",
                    "stop_detail": "max_new_tokens",
                    "ast_valid": False,
                    "ast_error": "SyntaxError: invalid syntax",
                    "raw_text": "def solution(data):\n    x = (\n",
                    "extracted_code": "def solution(data):\n    x = (",
                }
            ],
        },
    }
    (tmp_path / "q_test1.json").write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    rows = summarize_log_dir(tmp_path)
    assert len(rows) == 1
    att = rows[0]["attempts"][0]
    assert att["prompt_tokens"] == 4400
    assert att["truncated"] is True
    assert att["generated_tokens"] == 1536
    assert att["finish_reason"] == "length"
    assert att["starts_with_python_fence"] is False
    assert att["backtick_fence_count"] == 0
    assert att["category"].startswith("(b)")
