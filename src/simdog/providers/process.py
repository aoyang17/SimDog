from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from simdog.contracts import AGENT_PROTOCOL_VERSION, AgentRequest, AgentResponse
from .base import ProviderCapabilities, ProviderManifest


@dataclass
class ProcessProvider:
    """Vendor-neutral JSON-over-stdio provider. No shell is involved."""

    argv: list[str]
    provider_id: str = "process"
    timeout_seconds: float = 300.0

    def __post_init__(self) -> None:
        if not self.argv or any("\x00" in part for part in self.argv):
            raise ValueError("provider argv must be a non-empty safe argument list")

    def manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            implementation_version="1",
            protocol_versions=(AGENT_PROTOCOL_VERSION,),
            capabilities=ProviderCapabilities(structured_output=True),
        )

    def execute(self, request: AgentRequest) -> AgentResponse:
        completed = subprocess.run(
            self.argv,
            input=json.dumps(request.as_dict(), ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"agent provider exited {completed.returncode}: {completed.stderr[-2000:]}")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("agent provider did not return one JSON response") from exc
        response = AgentResponse.from_dict(payload)
        if response.request_id != request.request_id:
            raise ValueError("agent provider response request_id mismatch")
        return response
