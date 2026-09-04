from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class RemoteCommand:
    """Solver-neutral remote command. Implementations must not use local shells."""

    argv: tuple[str, ...]
    cwd: str
    timeout_seconds: float = 300.0
    environment: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.argv or any(not isinstance(item, str) or "\x00" in item for item in self.argv):
            raise ValueError("remote argv must be a non-empty safe argument array")
        if not self.cwd or "\x00" in self.cwd:
            raise ValueError("remote cwd is required")


@dataclass(frozen=True)
class TransportResult:
    returncode: int
    stdout: str
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def as_dict(self) -> dict[str, object]:
        return {**asdict(self), "ok": self.ok}


class RemoteTransport(Protocol):
    def run(self, command: RemoteCommand) -> TransportResult: ...


class RecordingTransport:
    """Deterministic transport for executor tests without SSH or a scheduler."""

    def __init__(self, results: list[TransportResult] | None = None) -> None:
        self.results = list(results or [])
        self.commands: list[RemoteCommand] = []

    def run(self, command: RemoteCommand) -> TransportResult:
        self.commands.append(command)
        if not self.results:
            return TransportResult(0, "")
        return self.results.pop(0)
