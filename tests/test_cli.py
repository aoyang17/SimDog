from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest

from simdog.cli import main


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_adapters_are_discoverable(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["adapters"])
        self.assertEqual(code, 0)
        names = {item["registration"] for item in json.loads(output.getvalue())["adapters"]}
        self.assertIn("command", names)
        self.assertIn("comsol", names)

    def test_distributed_ecm_comsol_plan_is_renderable(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([
                "plan-adapter", "--adapter", "comsol",
                "--spec", str(ROOT / "examples/distributed_ecm/comsol_plan.yml"),
            ])
        self.assertEqual(code, 0)
        plan = json.loads(output.getvalue())["plan"]
        self.assertEqual(len(plan["steps"]), 2)
