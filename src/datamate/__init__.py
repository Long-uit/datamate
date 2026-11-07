"""
DataMate — Hệ thống AI Hỏi-Đáp & Phân Tích Dữ Liệu Bán Lẻ Doanh Nghiệp.
Zalo AI Challenge 2026.
"""

import sys
from datamate.exceptions import DataMateError, DataNotFoundError

# Thiết lập bí danh (Backward-compatibility aliases) cho các module cũ
import datamate.ingestion_schema as _ingestion_schema
import datamate.grounding_feasibility as _grounding_feasibility
import datamate.llm_execution as _llm_execution
import datamate.output_abstention as _output_abstention

sys.modules.setdefault("datamate.ingestion", _ingestion_schema)
sys.modules.setdefault("datamate.grounding", _grounding_feasibility)
sys.modules.setdefault("datamate.llm", _llm_execution)
sys.modules.setdefault("datamate.execution", _llm_execution)
sys.modules.setdefault("datamate.output", _output_abstention)

__all__ = ["DataMateError", "DataNotFoundError"]
__version__ = "0.2.0"

