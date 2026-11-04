"""
test_data_synth.py — Kiểm thử bộ công cụ sinh dữ liệu mở rộng (Task 1 Phase 3).
"""

from pathlib import Path
import pytest

from data_synth.build_dataset import augment_seed_questions, export_dataset_jsonl
from data_synth.clean_filter import (
    filter_synthetic_sample,
    validate_python_code,
    validate_rulebook_compliance,
)
from data_synth.paraphrase import paraphrase_question, remove_vietnamese_accents
from data_synth.tet_variants import generate_tet_questions
from data_synth.unanswerable_gen import generate_unanswerable_questions


class TestDataSynth:
    def test_paraphrase_question(self):
        q = "Doanh thu hôm nay của cửa hàng là bao nhiêu?"
        variants = paraphrase_question(q, num_variants=3)
        assert len(variants) > 0
        # Kiểm tra biến thể không được rỗng
        for v in variants:
            assert len(v.strip()) > 5

    def test_unanswerable_generation(self):
        samples = generate_unanswerable_questions(
            business_id="shop_01",
            as_of_date="2024-05-15",
            date_range=("2024-01-01", "2024-12-31"),
        )
        assert len(samples) >= 3
        for s in samples:
            assert s["type"] == "unanswerable"
            assert s["answer"] is None
            assert "reason" in s

    def test_tet_variants_generation(self):
        samples = generate_tet_questions(business_id="shop_01", as_of_date="2024-05-01", year=2024)
        assert len(samples) >= 2
        assert any("Tết" in s["question"] for s in samples)

    def test_code_validation_and_safety(self):
        valid_code = "def solution(data):\n    return 100\nFINAL_RESULT = solution(None)"
        ok, msg = validate_python_code(valid_code)
        assert ok is True

        syntax_error_code = "def solution(data:\n    return 100"
        ok_syn, _ = validate_python_code(syntax_error_code)
        assert ok_syn is False

        unsafe_code = "import os\nos.system('rm -rf /')"
        ok_safe, msg_safe = validate_python_code(unsafe_code)
        assert ok_safe is False
        assert "Chứa lệnh không an toàn" in msg_safe

    def test_dataset_building_and_export(self, tmp_path: Path):
        seed = [
            {
                "id": "q1",
                "business_id": "shop_01",
                "as_of_date": "2024-05-15",
                "question": "Doanh thu hôm nay là bao nhiêu?",
                "type": "number",
                "answer": 500000,
            }
        ]
        augmented = augment_seed_questions(seed, target_count=5)
        assert len(augmented) >= 2

        out_file = tmp_path / "train_synth.jsonl"
        exported = export_dataset_jsonl(augmented, out_file)
        assert exported == len(augmented)
        assert out_file.exists()
