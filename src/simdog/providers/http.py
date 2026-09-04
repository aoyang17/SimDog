from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from typing import Any, Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from simdog.contracts import AGENT_PROTOCOL_VERSION, AgentRequest, AgentResponse
from .base import ProviderCapabilities, ProviderManifest


class JsonHttpClient(Protocol):
    def post(self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]: ...


class UrllibJsonHttpClient:
    def post(self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        with urlopen(request, timeout=timeout) as response:  # nosec: endpoint is operator-configured and validated
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("agent gateway response must be a JSON object")
        return value


@dataclass
class NativeGatewayProvider:
    """SimDog-native HTTP gateway for any LLM or agent framework.

    Vendor-specific chat/tool/event formats stay behind the gateway. The secret
    is resolved from an environment reference at call time and is never stored in
    requests, responses, manifests, or workflow state.
    """

    endpoint: str
    provider_id: str
    secret_env: str | None = None
    timeout_seconds: float = 300.0
    client: JsonHttpClient | None = None
    allow_insecure_localhost: bool = False
    gateway_capabilities: ProviderCapabilities = field(
        default_factory=lambda: ProviderCapabilities(structured_output=True)
    )

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not (self.allow_insecure_localhost and local and parsed.scheme == "http"):
            raise ValueError("agent gateway endpoint must use HTTPS, except explicitly allowed localhost")
        if not parsed.netloc:
            raise ValueError("agent gateway endpoint is invalid")
        self.client = self.client or UrllibJsonHttpClient()

    def manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id=self.provider_id,
            implementation_version="1",
            protocol_versions=(AGENT_PROTOCOL_VERSION,),
            capabilities=self.gateway_capabilities,
        )

    def execute(self, request: AgentRequest) -> AgentResponse:
        headers: dict[str, str] = {}
        if self.secret_env:
            secret = os.environ.get(self.secret_env)
            if not secret:
                raise RuntimeError(f"agent gateway secret environment reference is unavailable: {self.secret_env}")
            headers["Authorization"] = f"Bearer {secret}"
        assert self.client is not None
        payload = self.client.post(self.endpoint, request.as_dict(), headers, self.timeout_seconds)
        response = AgentResponse.from_dict(payload)
        if response.request_id != request.request_id:
            raise ValueError("agent gateway response request_id mismatch")
        return response
