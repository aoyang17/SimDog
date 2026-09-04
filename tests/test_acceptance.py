from __future__ import annotations

import unittest

from simdog.acceptance import evaluate_acceptance


class AcceptanceTests(unittest.TestCase):
    def test_required_criteria_control_verdict(self) -> None:
        criteria = [
            {"id": "residual", "metric": "solver.residual", "operator": "<=", "expected": 1e-3},
            {"id": "soc", "metric": "soc", "operator": "between", "expected": [0, 1]},
        ]
        self.assertTrue(evaluate_acceptance(criteria, {"solver": {"residual": 9e-4}, "soc": 0.4})["passed"])
        self.assertFalse(evaluate_acceptance(criteria, {"solver": {"residual": 2e-3}, "soc": 0.4})["passed"])

    def test_missing_metric_fails_closed(self) -> None:
        result = evaluate_acceptance(
            [{"id": "missing", "metric": "x.y", "operator": "==", "expected": 1}], {}
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["results"][0]["message"], "metric missing")
