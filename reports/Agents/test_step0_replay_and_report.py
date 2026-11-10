"""
Kiểm thử Bước 0:
1. Chế độ --replay_logs trong tests/inspect_pipeline.py: lấy code từ logs, bỏ qua LLM, chạy lại sandbox + abstention + format, in PA và số câu đổi trạng thái.
2. Báo cáo Markdown: hiển thị đầy đủ câu hỏi gốc, as_of_date, intent, khoảng ngày (kể cả kỳ so sánh), entity linking, gold answer, và thời gian từng pha.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import pytest

from tests.inspect_pipeline import render_markdown_evaluation_report, main as inspect_main


def test_markdown_report_contains_full_grounding_and_timing(tmp_path: Path):
    """Kiểm tra render_markdown_evaluation_report đọc đúng các trường top-level của log JSON."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    qid = "q_23401b31d098"
    log_payload = {
        "question_id": qid,
        "business_id": "biz_104",
        "as_of_date": "2026-06-02",
        "original_question": "so don bi huy trong thang 5 nam 2025 la bao nhieu z",
        "normalized_question": "so don bi huy trong thang 5 nam 2025 la bao nhieu z",
        "intent": "cancelled_orders",
        "temporal_info": {
            "description": "Tháng 5/2025",
            "start_date": "2025-05-01",
            "end_date": "2025-05-31",
        },
        "entity_matches": ["Trịnh Thắng Huy"],
        "selected_tables": ["DonHang_ChiTiet"],
        "selected_columns": ["clean_date"],
        "confidence": 1.0,
        "self_correction_count": 1,
        "code": "def solution(data):\n    return 66",
        "answer": {"id": qid, "type": "number", "answer": 66},
        "gold_answer": {"answer": 66, "type": "number", "alias": []},
        "latency_breakdown_ms": {
            "ingest_schema": 1200.5,
            "feasibility": 1.2,
            "grounding": 45.3,
            "prompt_build": 5.0,
            "llm_gen": 35000.0,
            "sandbox_exec": 250.4,
            "normalizer": 0.5,
        },
    }
    (log_dir / f"{qid}.json").write_text(json.dumps(log_payload, ensure_ascii=False), encoding="utf-8")

    md_path = tmp_path / "report.md"
    metrics = {
        "total": 1,
        "correct": 1,
        "wrong": 0,
        "abstain": 0,
        "pa": 1.0,
        "accuracy": 1.0,
        "coverage": 1.0,
        "total_time_sec": 36.5,
        "breakdown": {"number": {"total": 1, "correct": 1, "wrong": 0, "abstain": 0, "pa": 1.0, "avg_latency_ms": 36500.0}},
    }
    gold_map = {qid: {"id": qid, "type": "number", "answer": 66, "alias": []}}
    written_records = {qid: {"id": qid, "type": "number", "answer": 66}}

    render_markdown_evaluation_report(
        metrics=metrics,
        eval_qids=[qid],
        log_dir=log_dir,
        gold_map=gold_map,
        written_records=written_records,
        md_path=md_path,
        model_id="Qwen/Qwen2.5-Coder-7B-Instruct",
    )

    content = md_path.read_text(encoding="utf-8")
    assert "so don bi huy trong thang 5 nam 2025 la bao nhieu z" in content
    assert "as_of_date = 2026-06-02" in content
    assert "intent = cancelled_orders" in content
    assert "2025-05-01 -> 2025-05-31" in content
    assert "Trịnh Thắng Huy" in content
    # Phải hiển thị thời gian từng pha (nạp dữ liệu / LLM / thực thi)
    assert "1200.5" in content or "Nạp dữ liệu" in content


def test_replay_logs_cli_flag_exists_and_runs(tmp_path: Path, monkeypatch, capsys):
    """Kiểm tra cờ --replay_logs chạy lại code từ thư mục logs mà không gọi LLM và in PA + số câu đổi trạng thái."""
    out_sub = tmp_path / "replay_sub.jsonl"
    out_rep = tmp_path / "replay_rep.json"
    out_md = tmp_path / "replay_rep.md"
    out_chart = tmp_path / "replay_chart.png"
    out_logs = tmp_path / "replay_logs"

    monkeypatch.setattr(
        "sys.argv",
        [
            "inspect_pipeline.py",
            "--data_dir",
            "competition_data/train",
            "--replay_logs",
            "datamate_runs/train_eval/logs",
            "--id",
            "q_23401b31d098",
            "--in_process",
            "--output_file",
            str(out_sub),
            "--report_file",
            str(out_rep),
            "--md_file",
            str(out_md),
            "--chart_file",
            str(out_chart),
            "--log_dir",
            str(out_logs),
        ],
    )
    inspect_main()
    captured = capsys.readouterr().out
    assert "Penalized Accuracy (PA)" in captured
    assert "Đổi trạng thái" in captured or "đổi trạng thái" in captured.lower()
    assert out_rep.exists()
    rep_data = json.loads(out_rep.read_text(encoding="utf-8"))
    assert "status_changes" in rep_data


def test_clean_date_mixed_iso_and_vn_dates():
    """Kiểm tra clean_date không bị đảo tháng/ngày cho các dòng ISO (YYYY-MM-DD) khi cùng cột có dòng DD/MM/YYYY."""
    import pandas as pd
    from src.datamate.llm_execution.sandbox import clean_date

    s = pd.Series(["02/01/2026", "2026-01-02 00:00:00", "15/01/2026"])
    parsed = clean_date(s)
    assert list(parsed.dt.year) == [2026, 2026, 2026]
    assert list(parsed.dt.month) == [1, 1, 1]
    assert list(parsed.dt.day) == [2, 2, 15]

