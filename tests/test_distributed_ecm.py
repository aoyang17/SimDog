from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path("/home/aobo/PaperEngine/Needs/distributed_ecm_debug")


class DistributedECMProbeTests(unittest.TestCase):
    def test_legacy_validator_distinguishes_pass_and_reject(self) -> None:
        if not SOURCE_ROOT.is_dir():
            self.skipTest("PaperEngine DistributedECM assets are not available")
        module_path = PROJECT_ROOT / "examples/distributed_ecm/run_probe.py"
        spec = importlib.util.spec_from_file_location("distributed_probe", module_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.run_probe(SOURCE_ROOT)
        self.assertTrue(result["ok"])
        by_case = {item["case"]: item for item in result["outcomes"]}
        self.assertTrue(by_case["reported_0p5c_pass"]["accepted"])
        self.assertFalse(by_case["reported_1c_coarse_reject"]["accepted"])
        self.assertFalse(result["claims"]["imports_paper_engine"])
