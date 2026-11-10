"""
test_e2e_offline.py — Kiểm thử End-to-End quy trình ngoại tuyến Phase 4 (Task 4 Phase 4).
Bao gồm:
- Thẩm định file nộp bài submission qua verify_submission.py
- Kiểm định tính tái lập qua repro_check.py
- Kiểm định hiệu chuẩn ngưỡng tau* qua calibrate_tau.py
- Kiểm định phân tích độ trễ qua latency.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

try:
    from benchmark.calibrate_tau import find_optimal_tau, simulate_abstention_at_threshold
    from benchmark.latency import analyze_latencies
    from benchmark.repro_check import compare_runs
    from scripts.verify_submission import validate_submission_file
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    try:
        from benchmark.calibrate_tau import find_optimal_tau, simulate_abstention_at_threshold
        from benchmark.latency import analyze_latencies
        from benchmark.repro_check import compare_runs
        from scripts.verify_submission import validate_submission_file
    except ImportError:
        pytest.skip("Bỏ qua test_e2e_offline do thiếu dependencies phụ trợ benchmark", allow_module_level=True)


def test_verify_submission_valid_format(tmp_path: Path):
    """Xác nhận bộ thẩm định chấp nhận file nộp bài hợp lệ chuẩn 8 types."""
    sub_file = tmp_path / "valid_submission.jsonl"
    records = [
        {"id": "q1", "type": "number", "answer": 150000},
        {"id": "q2", "type": "percent", "answer": 25.5},
        {"id": "q3", "type": "string", "answer": "Cà phê sữa đá"},
        {"id": "q4", "type": "date", "answer": "2024-05-15"},
        {"id": "q5", "type": "boolean", "answer": True},
        {"id": "q6", "type": "list", "answer": ["SP01", "SP02"]},
        {"id": "q7", "type": "table", "answer": {"columns": ["sku", "qty"], "rows": [["SP01", 10]]}},
        {"id": "q8", "type": "unanswerable", "answer": None},
        {"id": "q9", "type": "abstain", "answer": None},
    ]
    with open(sub_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    is_valid, errors, summary = validate_submission_file(sub_file)
    assert is_valid is True
    assert len(errors) == 0
    assert summary["total_records"] == 9
    assert summary["unique_ids"] == 9


def test_verify_submission_catches_invalid_formats(tmp_path: Path):
    """Xác nhận bộ thẩm định bắt đúng các lỗi format sai kiểu hoặc lệch phạm vi."""
    sub_file = tmp_path / "invalid_submission.jsonl"
    records = [
        {"id": "q1", "type": "percent", "answer": 120.0},        # Lỗi: > 100%
        {"id": "q2", "type": "number", "answer": True},          # Lỗi: boolean thay vì number
        {"id": "q3", "type": "date", "answer": "15-05-2024"},     # Lỗi: không đúng ISO
        {"id": "q4", "type": "unanswerable", "answer": "Lỗi"},    # Lỗi: answer phải là None
        {"id": "q4", "type": "string", "answer": "Món trùng"},    # Lỗi: ID trùng
    ]
    with open(sub_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    is_valid, errors, summary = validate_submission_file(sub_file)
    assert is_valid is False
    assert len(errors) >= 4


def test_reproducibility_check_passes_identical_runs():
    """Xác nhận kiểm thử tái lập đạt 100% khi 2 lần chạy cho cùng đáp án."""
    run1 = {
        "q1": {"id": "q1", "type": "number", "answer": 100},
        "q2": {"id": "q2", "type": "string", "answer": "Sản phẩm A"},
    }
    run2 = {
        "q1": {"id": "q1", "type": "number", "answer": 100},
        "q2": {"id": "q2", "type": "string", "answer": "Sản phẩm A"},
    }
    is_repro, mismatches, stats = compare_runs(run1, run2)
    assert is_repro is True
    assert len(mismatches) == 0
    assert stats["reproducibility_rate"] == 100.0


def test_reproducibility_check_catches_mismatches():
    """Xác nhận kiểm thử tái lập bắt được độ lệch giữa 2 lần chạy."""
    run1 = {
        "q1": {"id": "q1", "type": "number", "answer": 100},
        "q2": {"id": "q2", "type": "string", "answer": "Sản phẩm A"},
    }
    run2 = {
        "q1": {"id": "q1", "type": "number", "answer": 101},     # Lệch giá trị
        "q2": {"id": "q2", "type": "string", "answer": "Sản phẩm A"},
    }
    is_repro, mismatches, stats = compare_runs(run1, run2)
    assert is_repro is False
    assert len(mismatches) == 1
    assert stats["reproducibility_rate"] == 50.0


def test_calibrate_tau_optimization():
    """Kiểm tra thuật toán tìm ngưỡng tau* tối ưu hóa Penalized Accuracy."""
    golds = {
        "q1": {"id": "q1", "type": "number", "answer": 100, "alias": []},
        "q2": {"id": "q2", "type": "number", "answer": 200, "alias": []},
        "q3": {"id": "q3", "type": "number", "answer": 300, "alias": []},
    }
    # q1: đúng, độ tin cậy cao 0.90
    # q2: đúng, độ tin cậy vừa 0.70
    # q3: sai, độ tin cậy thấp 0.30 (nên abstain để cứu -1 điểm)
    preds = [
        {"id": "q1", "type": "number", "answer": 100, "confidence": 0.90},
        {"id": "q2", "type": "number", "answer": 200, "confidence": 0.70},
        {"id": "q3", "type": "number", "answer": 999, "confidence": 0.30},
    ]

    best_tau, results = find_optimal_tau(preds, golds, min_tau=0.20, max_tau=0.80, step=0.10)
    # Tại tau=0.30+: q1 (+1), q2 (+1), q3 bị abstain (0). PA = (2 - 0) / 3 = 0.6667
    # Tại tau=0.20: q1 (+1), q2 (+1), q3 sai (-1). PA = (2 - 1) / 3 = 0.3333
    assert best_tau >= 0.30
    best_stats = [r for r in results if abs(r["tau"] - best_tau) < 1e-4][0]
    assert best_stats["pa"] > 0.50


def test_latency_profiler(tmp_path: Path):
    """Kiểm tra công cụ phân tích độ trễ đọc và tính toán đúng thông lượng."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    for i in range(5):
        log_file = log_dir / f"q_{i:03d}.json"
        data = {
            "question_id": f"q_{i:03d}",
            "generation_seconds": 1.5 + (i * 0.1),
            "execution_ms": 200.0 + (i * 50.0),
        }
        log_file.write_text(json.dumps(data), encoding="utf-8")

    stats = analyze_latencies(log_dir)
    assert stats["num_samples"] == 5
    assert stats["mean_generation"] > 1.0
    assert stats["mean_execution"] > 0.1
    assert stats["safe_within_limit"] is True
