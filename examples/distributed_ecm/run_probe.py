#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from simdog.adapters.command import CommandAdapter
from simdog.executors.local import ExecutionPolicy, LocalExecutor
from simdog.util import atomic_json, sha256_file


REQUIRED_SOURCE_FILES = (
    "DistributedECMFixed.java",
    "comsol_fixed_surface_smoke.slurm",
    "validate_smoke.py",
    "validate_capacity.py",
)


def run_probe(source_root: Path) -> dict[str, Any]:
    source_root = source_root.expanduser().resolve()
    missing = [name for name in REQUIRED_SOURCE_FILES if not (source_root / name).is_file()]
    if missing:
        return {"ok": False, "error": "missing DistributedECM assets", "missing": missing}
    source_manifest = [
        {
            "path": str((source_root / name).resolve()),
            "size": (source_root / name).stat().st_size,
            "sha256": sha256_file(source_root / name),
        }
        for name in REQUIRED_SOURCE_FILES
    ]
    validator = source_root / "validate_smoke.py"
    fixture_root = Path(__file__).resolve().parent
    cases = (
        ("reported_0p5c_pass", fixture_root / "pass_0p5c.csv", True),
        ("reported_1c_coarse_reject", fixture_root / "reject_1c.csv", False),
    )
    outcomes: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="simdog-distributed-ecm-") as temporary:
        workspace = Path(temporary)
        for name, fixture, expected_acceptance in cases:
            local_fixture = workspace / fixture.name
            shutil.copy2(fixture, local_fixture)
            spec = {
                "argv": [sys.executable, str(validator), str(local_fixture), "--expected-final", "10"],
                "cwd": ".",
                "timeout_seconds": 30,
                "success_codes": [0],
            }
            request = CommandAdapter().execution_request(spec)
            policy = ExecutionPolicy(
                allowed_executables=(str(Path(sys.executable).resolve()),),
                max_timeout_seconds=60,
            )
            result = LocalExecutor(workspace, policy).execute(request)
            accepted = result.returncode == 0 and "validation_status=PASS" in result.stdout
            outcomes.append({
                "case": name,
                "expected_acceptance": expected_acceptance,
                "accepted": accepted,
                "expectation_met": accepted is expected_acceptance,
                "execution": result.as_dict(),
            })
    return {
        "ok": all(item["expectation_met"] for item in outcomes),
        "probe": "distributed_ecm_legacy_validator",
        "source_root": str(source_root),
        "source_manifest": source_manifest,
        "outcomes": outcomes,
        "claims": {
            "imports_paper_engine": False,
            "modifies_source": False,
            "runs_comsol": False,
            "distinguishes_completion_from_acceptance": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = run_probe(args.source_root)
    if args.report:
        atomic_json(args.report, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
