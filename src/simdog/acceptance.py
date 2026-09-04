from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping


@dataclass(frozen=True)
class AcceptanceResult:
    criterion_id: str
    metric: str
    operator: str
    expected: Any
    actual: Any
    passed: bool
    required: bool
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _lookup(metrics: Mapping[str, Any], dotted: str) -> Any:
    value: Any = metrics
    for part in dotted.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise KeyError(dotted)
        value = value[part]
    return value


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    if isinstance(actual, float) and not math.isfinite(actual):
        return False
    if operator == "between":
        low, high = expected
        return float(low) <= float(actual) <= float(high)
    if operator == "relative_error_le":
        target, tolerance = expected
        return abs(float(actual) - float(target)) / max(abs(float(target)), 1e-30) <= float(tolerance)
    operations = {
        "<": lambda: actual < expected,
        "<=": lambda: actual <= expected,
        ">": lambda: actual > expected,
        ">=": lambda: actual >= expected,
        "==": lambda: actual == expected,
    }
    if operator not in operations:
        raise ValueError(f"unsupported acceptance operator: {operator}")
    return bool(operations[operator]())


def evaluate_acceptance(criteria: list[dict[str, Any]], metrics: Mapping[str, Any]) -> dict[str, Any]:
    results: list[AcceptanceResult] = []
    seen: set[str] = set()
    for index, criterion in enumerate(criteria):
        criterion_id = str(criterion.get("id") or f"criterion-{index + 1}")
        if criterion_id in seen:
            raise ValueError(f"duplicate acceptance criterion: {criterion_id}")
        seen.add(criterion_id)
        metric = str(criterion.get("metric") or "")
        operator = str(criterion.get("operator") or "")
        required = bool(criterion.get("required", True))
        try:
            actual = _lookup(metrics, metric)
            passed = _compare(actual, operator, criterion.get("expected"))
            message = "pass" if passed else "value does not satisfy criterion"
        except KeyError:
            actual = None
            passed = False
            message = "metric missing"
        except (TypeError, ValueError, ZeroDivisionError) as exc:
            actual = None
            passed = False
            message = f"invalid metric or criterion: {exc}"
        results.append(AcceptanceResult(
            criterion_id=criterion_id, metric=metric, operator=operator,
            expected=criterion.get("expected"), actual=actual, passed=passed,
            required=required, message=message,
        ))
    required_results = [item for item in results if item.required]
    return {
        "passed": all(item.passed for item in required_results),
        "required_passed": sum(item.passed for item in required_results),
        "required_total": len(required_results),
        "results": [item.as_dict() for item in results],
    }
