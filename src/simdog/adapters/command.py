from __future__ import annotations

from typing import Any

from simdog.executors.local import ExecutionRequest
from .base import AdapterCapabilities, AdapterManifest


class CommandAdapter:
    """Black-box adapter for legacy solvers and validators."""

    adapter_id = "command"

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(run=True)

    def manifest(self) -> AdapterManifest:
        return AdapterManifest(
            adapter_id=self.adapter_id,
            implementation_version="1",
            solver_family="external-command",
            capabilities=self.capabilities(),
            actions=("run",),
        )

    def execution_request(self, spec: dict[str, Any]) -> ExecutionRequest:
        argv = spec.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
            raise ValueError("command adapter requires argv as a list of strings")
        return ExecutionRequest(
            argv=tuple(argv),
            cwd=str(spec.get("cwd") or "."),
            timeout_seconds=float(spec.get("timeout_seconds") or 300),
            environment=dict(spec.get("environment") or {}),
            expected_outputs=tuple(spec.get("expected_outputs") or []),
            clean_log_patterns=tuple(spec.get("clean_log_patterns") or []),
            success_codes=tuple(int(item) for item in (spec.get("success_codes") or [0])),
        )
