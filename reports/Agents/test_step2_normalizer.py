"""
Kiểm thử Bước 2 — Format Normalizer:
1. percent phải là float làm tròn 2 chữ số thập phân (không ép về int(round(...)), không kèm ký tự %).
2. Ngay cả khi code của LLM viết `return int(round(ratio))` hoặc `return round(ratio)`, sandbox/AST phải giữ nguyên phần thập phân để normalize_percent làm tròn 2 chữ số thập phân chính xác.
3. Rà soát đầy đủ 8 kiểu đáp án theo mục 3.2 trong docs: number, percent, string (NFC, giữ dấu, kèm hàm canonicalize_string_for_eval chuẩn mục 3.2), date, boolean, list, table, unanswerable.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3
import sys

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import pandas as pd
import numpy as np
import pytest

from src.datamate.output_abstention.normalizer import (
    normalize_output,
    normalize_number,
    normalize_percent,
    normalize_string,
    normalize_date,
    normalize_boolean,
    normalize_list,
    normalize_table,
    canonicalize_string_for_eval,
    apply_tie_breaker,
)
from src.datamate.grounding_feasibility.temporal import filter_future_data
from src.datamate.llm_execution.worker import execute_code_in_env
from src.datamate.llm_execution.sandbox import clean_num, clean_date
from src.datamate.exceptions import DataNotFoundError
from src.datamate.llm_execution.prompt import get_return_format_instruction


def test_step2_percent_is_always_float_rounded_2_decimals():
    """percent phải luôn là float làm tròn 2 chữ số thập phân, không bao giờ là int hoặc kèm ký tự %."""
    p1 = normalize_percent(13.534)
    assert isinstance(p1, float)
    assert p1 == 13.53

    p2 = normalize_percent("38,884%", code_text="return val")
    assert isinstance(p2, float)
    assert p2 == 38.88

    # Kể cả khi giá trị tròn nguyên (ví dụ 20% hoặc 5%), kiểu trả về của normalize_percent vẫn phải là float (20.0, 5.0)
    p3 = normalize_percent(0.05)
    assert isinstance(p3, float)
    assert p3 == 5.0

    p4 = normalize_percent(20, code_text="return ratio * 100")
    assert isinstance(p4, float)
    assert p4 == 20.0

    out = normalize_output(13.534, question="Tỉ trọng của nhóm cát đá trong doanh thu tháng 8/2026 là bao nhiêu %?")
    assert out == {"type": "percent", "answer": 13.53}
    assert isinstance(out["answer"], float)


def test_step2_worker_unwraps_int_round_for_percent_questions():
    """
    Khi LLM sinh `return int(round(percentage_increase))` trên câu hỏi percent,
    sandbox worker không được làm mất phần thập phân trước khi qua Format Normalizer.
    """
    code = """def solution(data):
    total_current = 138.884
    total_previous = 100.0
    percentage_increase = ((total_current - total_previous) / total_previous) * 100
    return int(round(percentage_increase))
FINAL_RESULT = solution(data)
"""
    con = sqlite3.connect(":memory:")
    res = execute_code_in_env(
        code_str=code,
        data_dict={},
        business=None,
        con=con,
        pd=pd,
        np=np,
        apply_tie_breaker=apply_tie_breaker,
        filter_future_data=filter_future_data,
        clean_num=clean_num,
        clean_date=clean_date,
        DataNotFoundError=DataNotFoundError,
    )
    assert res["ok"] is True
    norm = normalize_output(
        res["final_result"],
        question="tu dau thang nay den het hnay, dthu hon hay kem cung ky thang trc may %",
        code_text=code,
    )
    assert norm == {"type": "percent", "answer": 38.88}
    assert isinstance(norm["answer"], float)


def test_step2_prompt_return_instruction_for_percent():
    """get_return_format_instruction phải hướng dẫn round(val, 2) cho câu hỏi percent thay vì int(round(...))."""
    instr = get_return_format_instruction("Tỉ trọng của nhóm cát đá trong doanh thu tháng 8/2026 là bao nhiêu %?")
    assert "round(" in instr and "2" in instr
    assert "int(round" not in instr


def test_step2_eight_answer_types_and_string_canonicalization():
    """Rà soát toàn bộ 8 kiểu đáp án theo mục 3.2 trong docs."""
    # 1. number
    assert normalize_output("4.820.000 đ", question="Doanh thu hôm qua là bao nhiêu?") == {
        "type": "number",
        "answer": 4820000,
    }
    assert normalize_output(18.646, question="Trung bình mỗi đơn có bao nhiêu món?") == {
        "type": "number",
        "answer": 18.65,
    }

    # 2. percent
    assert normalize_output("-36,412%", question="Tăng hay giảm bao nhiêu %?") == {
        "type": "percent",
        "answer": -36.41,
    }

    # 3. string (NFC, giữ dấu) + canonicalize_string_for_eval (NFC, lowercase, bỏ dấu câu, giữ dấu tiếng Việt)
    s_nfd = "Sting da\u0302u   330ml"  # NFD 'dâu'
    out_str = normalize_output(s_nfd, expected_type="string")
    assert out_str == {"type": "string", "answer": "Sting dâu 330ml"}
    assert canonicalize_string_for_eval("  Sting Dâu - 330ml (Lon)! ") == "sting dâu 330ml lon"

    # 4. date
    assert normalize_output(date(2026, 8, 15), expected_type="date") == {
        "type": "date",
        "answer": "2026-08-15",
    }
    assert normalize_output("tháng 9/2025", expected_type="date") == {
        "type": "date",
        "answer": "2025-09",
    }

    # 5. boolean
    assert normalize_output("đúng", expected_type="boolean") == {
        "type": "boolean",
        "answer": True,
    }

    # 6. list
    assert normalize_output(["Cà phê sữa", "Bạc xỉu"], expected_type="list") == {
        "type": "list",
        "answer": ["Cà phê sữa", "Bạc xỉu"],
    }

    # 7. table
    tbl = normalize_output(
        {"columns": ["khach_hang", "so_tien_no"], "rows": [["Chị Lan", "3.200.000đ"]]},
        expected_type="table",
    )
    assert tbl == {
        "type": "table",
        "answer": {"columns": ["khach_hang", "so_tien_no"], "rows": [["Chị Lan", 3200000]]},
    }

    # 8. unanswerable
    assert normalize_output("unanswerable") == {"type": "unanswerable", "answer": None}
