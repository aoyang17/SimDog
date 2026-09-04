from __future__ import annotations

import json
from pathlib import Path
import unittest

from simdog.util import sha256_file


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "simulations/distributed_ecm/qualification_runs/20260904_job44029.json"


class RealQualificationRecordTests(unittest.TestCase):
    def test_recorded_short_run_satisfies_declared_gates(self) -> None:
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        values = record["validation"]
        self.assertEqual(record["verdict"], "accepted")
        self.assertEqual(values["status"], "PASS")
        self.assertLessEqual(values["current_balance_tab_b9"], 1e-4)
        self.assertLessEqual(values["current_mapping_b9_b6"], 1e-4)
        self.assertLessEqual(values["v2_residual_V"], 1e-3)
        self.assertLessEqual(values["interface_voltage_residual_V"], 1e-3)

    def test_downloaded_artifacts_match_public_record_when_present(self) -> None:
        output = ROOT / "workspaces/distributed_ecm/qual_0p5c_20260904/output/input"
        if not output.is_dir():
            self.skipTest("real qualification workspace is not present")
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        for name, expected in record["artifacts"].items():
            self.assertEqual(sha256_file(output / name), expected)
