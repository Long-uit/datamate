"""
test_config.py — Kiểm thử nạp và quản lý cấu hình hệ thống (Task 3 Phase 3).
"""

import os
import unittest
from pathlib import Path

from datamate.config import get_config, load_config, reset_config


class TestConfig(unittest.TestCase):
    def setUp(self):
        reset_config()
        for key in list(os.environ.keys()):
            if key.startswith("DATAMATE_"):
                del os.environ[key]

    def tearDown(self):
        reset_config()
        for key in list(os.environ.keys()):
            if key.startswith("DATAMATE_"):
                del os.environ[key]

    def test_default_config_loading(self):
        cfg = load_config()
        self.assertIn(cfg.model.model_id, ["Qwen/Qwen2.5-Coder-3B-Instruct", "Qwen/Qwen2.5-Coder-7B-Instruct"])
        self.assertIn(cfg.model.backend, ("transformers", "vllm"))
        self.assertGreater(cfg.execution.timeout_seconds, 0)
        self.assertEqual(cfg.grounding.entity_linking_threshold, 0.6)

    def test_environment_override(self):
        os.environ["DATAMATE_MODEL_ID"] = "Qwen/Qwen2.5-Coder-14B-Instruct"
        os.environ["DATAMATE_BACKEND"] = "vllm"
        os.environ["DATAMATE_TIMEOUT"] = "30"

        cfg = load_config()
        self.assertEqual(cfg.model.model_id, "Qwen/Qwen2.5-Coder-14B-Instruct")
        self.assertEqual(cfg.model.backend, "vllm")
        self.assertEqual(cfg.execution.timeout_seconds, 30)

    def test_singleton_accessor(self):
        cfg1 = get_config()
        cfg2 = get_config()
        self.assertIs(cfg1, cfg2)


if __name__ == "__main__":
    unittest.main()
