from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any

from simdog.util import contained_path, sha256_file


@dataclass(frozen=True)
class ExecutionPolicy:
    allowed_executables: tuple[str, ...]
    max_timeout_seconds: float = 3600.0
    allowed_environment: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionRequest:
    argv: tuple[str, ...]
    cwd: str = "."
    timeout_seconds: float = 300.0
    environment: dict[str, str] = field(default_factory=dict)
    expected_outputs: tuple[str, ...] = ()
    clean_log_patterns: tuple[str, ...] = ()
    success_codes: tuple[int, ...] = (0,)


@dataclass(frozen=True)
class ExecutionResult:
    started_at: str
    duration_seconds: float
    returncode: int
    stdout: str
    stderr: str
    outputs: tuple[dict[str, Any], ...]
    execution_ok: bool
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class LocalExecutor:
    def __init__(self, workspace: str | Path, policy: ExecutionPolicy) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.policy = policy

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not request.argv or any("\x00" in value for value in request.argv):
            raise ValueError("argv must be a non-empty safe argument list")
        if not executable_allowed(request.argv[0], self.policy.allowed_executables):
            raise PermissionError(f"executable is not allowed: {request.argv[0]}")
        if request.timeout_seconds <= 0 or request.timeout_seconds > self.policy.max_timeout_seconds:
            raise ValueError("requested timeout exceeds execution policy")
        unexpected_env = sorted(set(request.environment) - set(self.policy.allowed_environment))
        if unexpected_env:
            raise PermissionError(f"environment keys are not allowed: {', '.join(unexpected_env)}")
        cwd = contained_path(self.workspace, request.cwd)
        if not cwd.is_dir():
            raise FileNotFoundError(f"execution cwd does not exist: {cwd}")
        output_paths = [contained_path(self.workspace, item) for item in request.expected_outputs]
        env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
        env.update(request.environment)
        started_at = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()
        completed = subprocess.run(
            list(request.argv), cwd=cwd, env=env, capture_output=True, text=True,
            timeout=request.timeout_seconds, check=False,
        )
        duration = time.monotonic() - start
        errors: list[str] = []
        if completed.returncode not in request.success_codes:
            errors.append(f"unexpected return code: {completed.returncode}")
        combined = completed.stdout + "\n" + completed.stderr
        for pattern in request.clean_log_patterns:
            if re.search(pattern, combined, flags=re.IGNORECASE):
                errors.append(f"forbidden log pattern matched: {pattern}")
        outputs: list[dict[str, Any]] = []
        for path in output_paths:
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"required output missing or empty: {path.relative_to(self.workspace)}")
            else:
                outputs.append({
                    "path": path.relative_to(self.workspace).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                })
        return ExecutionResult(
            started_at=started_at,
            duration_seconds=duration,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            outputs=tuple(outputs),
            execution_ok=not errors,
            errors=tuple(errors),
        )


def executable_allowed(requested: str, allowed: tuple[str, ...]) -> bool:
    path = Path(requested)
    if path.is_absolute():
        requested_resolved = str(path.expanduser().resolve())
        return any(
            Path(item).is_absolute() and str(Path(item).expanduser().resolve()) == requested_resolved
            for item in allowed
        )
    if len(path.parts) != 1:
        return False
    return requested in allowed
