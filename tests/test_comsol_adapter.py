from __future__ import annotations

from pathlib import Path
import unittest

from simdog.adapters.comsol import ComsolAdapter
from simdog.util import load_data


ROOT = Path(__file__).resolve().parents[1]


class ComsolAdapterTests(unittest.TestCase):
    def test_distributed_ecm_plan_is_two_bounded_steps(self) -> None:
        spec = load_data(ROOT / "examples/distributed_ecm/comsol_plan.yml")
        plan = ComsolAdapter().build_plan(spec)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].argv, ("comsol", "compile", "DistributedECMFixed.java"))
        self.assertIn("C_rate=0.5", plan.steps[1].argv)
        self.assertIn("fixed_0p5c_10s_solved.mph", plan.steps[1].expected_outputs)

    def test_paths_cannot_escape_workspace(self) -> None:
        with self.assertRaises(ValueError):
            ComsolAdapter().build_plan({
                "action": "batch-mph",
                "input_model": "../outside.mph",
            })

    def test_parameter_key_injection_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ComsolAdapter().build_plan({
                "action": "batch-mph",
                "input_model": "model.mph",
                "parameters": {"bad key": "1"},
            })
