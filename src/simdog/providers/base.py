from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from simdog.contracts import AgentRequest, AgentResponse


@dataclass(frozen=True)
class ProviderCapabilities:
    structured_output: bool = True
    tool_use: bool = False
    image_input: bool = False
    persistent_sessions: bool = False
    workspace_access: bool = False
    max_context_tokens: int | None = None


@dataclass(frozen=True)
class ProviderManifest:
    provider_id: str
    implementation_version: str
    protocol_versions: tuple[str, ...]
    capabilities: ProviderCapabilities


class AgentProvider(Protocol):
    def manifest(self) -> ProviderManifest: ...

    def execute(self, request: AgentRequest) -> AgentResponse: ...


def require_capabilities(manifest: ProviderManifest, required: set[str]) -> None:
    missing = [name for name in sorted(required) if not bool(getattr(manifest.capabilities, name, False))]
    if missing:
        raise ValueError(f"provider {manifest.provider_id} lacks capabilities: {', '.join(missing)}")
