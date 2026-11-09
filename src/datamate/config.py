"""
config.py — Quản lý cấu hình tập trung cho toàn bộ hệ thống DataMate.

Hỗ trợ đọc từ YAML và ghi đè linh hoạt qua biến môi trường (Environment Variables).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None


@dataclass
class ModelConfig:
    model_id: str = "Qwen/Qwen2.5-Coder-3B-Instruct"
    backend: str = "transformers"  # "transformers" hoặc "vllm"
    max_new_tokens: int = 1536
    temperature: float = 0.0
    device: str = "auto"


@dataclass
class ExecutionConfig:
    timeout_seconds: int = 15
    memory_limit_mb: int = 4096
    use_sqlite_cache: bool = True


@dataclass
class GroundingConfig:
    entity_linking_threshold: float = 0.6
    max_entity_candidates: int = 10


@dataclass
class PathsConfig:
    calendar_csv: str = "competition_data/public_test/calendar.csv"
    rulebook_md: str = "competition_data/public_test/rulebook.md"
    data_dir: str = "competition_data/public_test/data"
    output_file: str = "submission.jsonl"
    logs_dir: str = "submission_logs"


@dataclass
class OutputConfig:
    tau_star: float = 0.50
    default_timeout: int = 30


@dataclass
class AppConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    grounding: GroundingConfig = field(default_factory=GroundingConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


_GLOBAL_CONFIG: Optional[AppConfig] = None


def find_default_config_path() -> Path:
    """Tìm đường dẫn tệp config/default.yaml từ thư mục gốc dự án."""
    cwd = Path.cwd()
    candidate = cwd / "config" / "default.yaml"
    if candidate.exists():
        return candidate
    # Tìm theo đường dẫn tương đối từ file mã nguồn
    src_parent = Path(__file__).resolve().parents[2] / "config" / "default.yaml"
    if src_parent.exists():
        return src_parent
    return candidate


def load_config(config_path: Optional[str | Path] = None) -> AppConfig:
    """Nạp file cấu hình YAML và áp dụng ghi đè từ biến môi trường."""
    path = Path(config_path) if config_path else find_default_config_path()
    raw_dict = {}

    if path.exists() and path.is_file():
        if yaml is not None:
            with open(path, "r", encoding="utf-8") as f:
                raw_dict = yaml.safe_load(f) or {}

    # Khởi tạo các sub-config từ dictionary
    m_data = raw_dict.get("model", {})
    e_data = raw_dict.get("execution", {})
    g_data = raw_dict.get("grounding", {})
    p_data = raw_dict.get("paths", {})
    o_data = raw_dict.get("output", {})

    cfg = AppConfig(
        model=ModelConfig(
            model_id=m_data.get("model_id", "Qwen/Qwen2.5-Coder-3B-Instruct"),
            backend=m_data.get("backend", "transformers"),
            max_new_tokens=m_data.get("max_new_tokens", 512),
            temperature=float(m_data.get("temperature", 0.0)),
            device=m_data.get("device", "auto"),
        ),
        execution=ExecutionConfig(
            timeout_seconds=int(e_data.get("timeout_seconds", 15)),
            memory_limit_mb=int(e_data.get("memory_limit_mb", 4096)),
            use_sqlite_cache=bool(e_data.get("use_sqlite_cache", True)),
        ),
        grounding=GroundingConfig(
            entity_linking_threshold=float(g_data.get("entity_linking_threshold", 0.6)),
            max_entity_candidates=int(g_data.get("max_entity_candidates", 10)),
        ),
        paths=PathsConfig(
            calendar_csv=p_data.get("calendar_csv", "competition_data/public_test/calendar.csv"),
            rulebook_md=p_data.get("rulebook_md", "competition_data/public_test/rulebook.md"),
            data_dir=p_data.get("data_dir", "competition_data/public_test/data"),
            output_file=p_data.get("output_file", "submission.jsonl"),
            logs_dir=p_data.get("logs_dir", "submission_logs"),
        ),
        output=OutputConfig(
            tau_star=float(o_data.get("tau_star", 0.50)),
            default_timeout=int(o_data.get("default_timeout", 30)),
        ),
    )

    # Ghi đè từ biến môi trường nếu có
    if "DATAMATE_MODEL_ID" in os.environ:
        cfg.model.model_id = os.environ["DATAMATE_MODEL_ID"]
    if "DATAMATE_BACKEND" in os.environ:
        cfg.model.backend = os.environ["DATAMATE_BACKEND"]
    if "DATAMATE_TIMEOUT" in os.environ:
        cfg.execution.timeout_seconds = int(os.environ["DATAMATE_TIMEOUT"])
    if "DATAMATE_DATA_DIR" in os.environ:
        cfg.paths.data_dir = os.environ["DATAMATE_DATA_DIR"]
    if "DATAMATE_OUTPUT_FILE" in os.environ:
        cfg.paths.output_file = os.environ["DATAMATE_OUTPUT_FILE"]
    if "DATAMATE_TAU_STAR" in os.environ:
        cfg.output.tau_star = float(os.environ["DATAMATE_TAU_STAR"])

    return cfg


def get_config(reload: bool = False) -> AppConfig:
    """Truy xuất cấu hình Singleton toàn cục."""
    global _GLOBAL_CONFIG
    if _GLOBAL_CONFIG is None or reload:
        _GLOBAL_CONFIG = load_config()
    return _GLOBAL_CONFIG


def reset_config() -> None:
    """Dọn dẹp singleton (hữu ích cho unit test)."""
    global _GLOBAL_CONFIG
    _GLOBAL_CONFIG = None

