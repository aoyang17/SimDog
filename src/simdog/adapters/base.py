from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from simdog.executors.local import ExecutionRequest


@dataclass(frozen=True)
class AdapterCapabilities:
    inspect: bool = False
    build: bool = False
    patch: bool = False
    run: bool = True
    extract: bool = False
    remote: bool = False


@dataclass(frozen=True)
class AdapterManifest:
    adapter_id: str
    implementation_version: str
    solver_family: str
    capabilities: AdapterCapabilities
    actions: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionPlan:
    adapter_id: str
    action: str
    steps: tuple[ExecutionRequest, ...]


class SolverAdapter(Protocol):
    adapter_id: str

    def capabilities(self) -> AdapterCapabilities: ...

    def execution_request(self, spec: dict[str, Any]) -> ExecutionRequest: ...

    def manifest(self) -> AdapterManifest: ...
