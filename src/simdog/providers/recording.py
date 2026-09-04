from __future__ import annotations

from typing import Callable

from simdog.contracts import AgentRequest, AgentResponse
from .base import ProviderCapabilities, ProviderManifest


class RecordingProvider:
    """Deterministic provider used for orchestration and conformance tests."""

    def __init__(self, responder: Callable[[AgentRequest], AgentResponse] | None = None) -> None:
        self.requests: list[AgentRequest] = []
        self.responder = responder

    def manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="recording",
            implementation_version="1",
            protocol_versions=("simdog.agent.v1",),
            capabilities=ProviderCapabilities(structured_output=True),
        )

    def execute(self, request: AgentRequest) -> AgentResponse:
        self.requests.append(request)
        if self.responder:
            return self.responder(request)
        return AgentResponse(
            request_id=request.request_id,
            status="completed",
            provider={"id": "recording", "version": "1", "model": "deterministic"},
        )
