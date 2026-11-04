"""
test_config.py — Kiểm thử nạp và quản lý cấu hình hệ thống (Task 3 Phase 3).
"""

import os
from pathlib import Path
import pytest

from datamate.config import get_config, load_config, reset_config


@pytest.fixture(autouse=True)
def clean_config_env():
    reset_config()
    for key in list(os.environ.keys()):
        if key.startswith("DATAMATE_"):
            del os.environ[key]
    yield
    reset_config()


class TestConfig:
    def test_default_config_loading(self):
        cfg = load_config()
        assert cfg.model.model_id is not None
        assert cfg.model.backend in ("transformers", "vllm")
        assert cfg.execution.timeout_seconds > 0
        assert cfg.grounding.entity_linking_threshold == 0.6

    def test_environment_override(self):
        os.environ["DATAMATE_MODEL_ID"] = "Qwen/Qwen2.5-Coder-14B-Instruct"
        os.environ["DATAMATE_BACKEND"] = "vllm"
        os.environ["DATAMATE_TIMEOUT"] = "30"

        cfg = load_config()
        assert cfg.model.model_id == "Qwen/Qwen2.5-Coder-14B-Instruct"
        assert cfg.model.backend == "vllm"
        assert cfg.execution.timeout_seconds == 30

    def test_singleton_accessor(self):
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

