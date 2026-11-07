"""
datamate.output_abstention — Module chuẩn hóa đáp án (Normalizer), cổng từ chối (Calibrated Abstention Gate) và xuất file submission.
"""

from __future__ import annotations

from datamate.output_abstention.abstention import (
    apply_abstention_gate,
    compute_confidence_score,
    find_optimal_threshold,
)
from datamate.output_abstention.normalizer import (
    apply_tie_breaker,
    check_result_sanity,
    normalize_output,
)
from datamate.output_abstention.submission import (
    SubmissionWriter,
    make_abstain,
    to_answer,
    validate_submission,
)

__all__ = [
    "compute_confidence_score",
    "apply_abstention_gate",
    "find_optimal_threshold",
    "normalize_output",
    "apply_tie_breaker",
    "check_result_sanity",
    "to_answer",
    "make_abstain",
    "SubmissionWriter",
    "validate_submission",
]

