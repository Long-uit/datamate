"""
data_synth — Bộ công cụ mở rộng và kiểm thử dữ liệu huấn luyện (Data Augmentation & Synthesis).
"""

from data_synth.build_dataset import augment_seed_questions, export_dataset_jsonl
from data_synth.clean_filter import filter_synthetic_sample, validate_python_code
from data_synth.paraphrase import paraphrase_question
from data_synth.tet_variants import generate_tet_questions
from data_synth.unanswerable_gen import generate_unanswerable_questions

__all__ = [
    "paraphrase_question",
    "generate_unanswerable_questions",
    "generate_tet_questions",
    "validate_python_code",
    "filter_synthetic_sample",
    "augment_seed_questions",
    "export_dataset_jsonl",
]

