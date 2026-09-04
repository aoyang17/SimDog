from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
import uuid


AGENT_PROTOCOL_VERSION = "simdog.agent.v1"


@dataclass(frozen=True)
class ArtifactContract:
    name: str
    media_type: str = "application/json"
    schema_ref: str | None = None
    required: bool = True


@dataclass(frozen=True)
class InputReference:
    name: str
    uri: str
    sha256: str | None = None
    media_type: str = "application/octet-stream"


@dataclass(frozen=True)
class AgentRequest:
    workflow_id: str
    role: str
    objective: str
    inputs: tuple[InputReference, ...] = ()
    outputs: tuple[ArtifactContract, ...] = ()
    constraints: dict[str, Any] = field(default_factory=dict)
    budget: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    protocol_version: str = AGENT_PROTOCOL_VERSION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactProposal:
    name: str
    media_type: str
    content: Any


@dataclass(frozen=True)
class AgentResponse:
    request_id: str
    status: str
    provider: dict[str, Any]
    artifacts: tuple[ArtifactProposal, ...] = ()
    events: tuple[dict[str, Any], ...] = ()
    usage: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    protocol_version: str = AGENT_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.status not in {"completed", "blocked", "failed"}:
            raise ValueError(f"invalid agent response status: {self.status}")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AgentResponse":
        if value.get("protocol_version") != AGENT_PROTOCOL_VERSION:
            raise ValueError("unsupported agent protocol version")
        artifacts = tuple(ArtifactProposal(**item) for item in value.get("artifacts") or [])
        return cls(
            request_id=str(value.get("request_id") or ""),
            status=str(value.get("status") or ""),
            provider=dict(value.get("provider") or {}),
            artifacts=artifacts,
            events=tuple(value.get("events") or []),
            usage=dict(value.get("usage") or {}),
            error=value.get("error"),
            protocol_version=str(value["protocol_version"]),
        )
