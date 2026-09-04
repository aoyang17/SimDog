from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from simdog.contracts import AGENT_PROTOCOL_VERSION, AgentRequest
from simdog.providers.base import AgentProvider, require_capabilities
from simdog.util import atomic_json, contained_path, sha256_file


@dataclass(frozen=True)
class BrokerResult:
    ok: bool
    request_id: str
    status: str
    staging_dir: str
    artifacts: tuple[dict[str, Any], ...]
    provider: dict[str, Any]
    error: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentBroker:
    """Validate provider work and materialize proposals only in staging."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

    def execute(
        self,
        provider: AgentProvider,
        request: AgentRequest,
        *,
        required_capabilities: set[str] | None = None,
        forbidden_identities: set[str] | None = None,
    ) -> BrokerResult:
        manifest = provider.manifest()
        if AGENT_PROTOCOL_VERSION not in manifest.protocol_versions:
            raise ValueError(f"provider does not support {AGENT_PROTOCOL_VERSION}")
        require_capabilities(manifest, required_capabilities or {"structured_output"})
        response = provider.execute(request)
        if response.request_id != request.request_id:
            raise ValueError("agent response request_id mismatch")
        response_provider_id = str(response.provider.get("id") or "")
        if response_provider_id != manifest.provider_id:
            raise ValueError(
                f"provider identity mismatch: manifest={manifest.provider_id!r}, response={response_provider_id!r}"
            )
        provider_identity = self._identity(response.provider)
        if provider_identity and provider_identity in (forbidden_identities or set()):
            raise ValueError("independent role cannot reuse a forbidden provider session identity")
        staging = contained_path(
            self.workspace,
            Path(".simdog") / "staging" / request.request_id,
        )
        staging.mkdir(parents=True, exist_ok=True)
        required = {item.name for item in request.outputs if item.required}
        declared = {item.name for item in request.outputs}
        proposed = {item.name for item in response.artifacts}
        errors: list[str] = []
        if response.status == "completed":
            missing = sorted(required - proposed)
            unexpected = sorted(proposed - declared)
            if missing:
                errors.append("missing required proposals: " + ", ".join(missing))
            if unexpected:
                errors.append("undeclared proposals: " + ", ".join(unexpected))
        artifacts: list[dict[str, Any]] = []
        if not errors and response.status == "completed":
            contracts = {item.name: item for item in request.outputs}
            for proposal in response.artifacts:
                if Path(proposal.name).name != proposal.name or proposal.name in {"", ".", ".."}:
                    raise ValueError(f"unsafe artifact proposal name: {proposal.name}")
                contract = contracts[proposal.name]
                if proposal.media_type != contract.media_type:
                    raise ValueError(f"artifact media type mismatch: {proposal.name}")
                destination = contained_path(staging, proposal.name)
                if proposal.media_type == "application/json":
                    atomic_json(destination, proposal.content)
                elif isinstance(proposal.content, str):
                    destination.write_text(proposal.content, encoding="utf-8")
                else:
                    raise ValueError(f"non-JSON proposal content must be text: {proposal.name}")
                artifacts.append({
                    "name": proposal.name,
                    "path": str(destination),
                    "sha256": sha256_file(destination),
                    "media_type": proposal.media_type,
                })
        receipt = {
            "protocol_version": AGENT_PROTOCOL_VERSION,
            "request": request.as_dict(),
            "response": response.as_dict(),
            "provider_manifest": asdict(manifest),
            "contract_errors": errors,
            "artifacts": artifacts,
        }
        atomic_json(staging / "broker_receipt.json", receipt)
        ok = response.status == "completed" and not errors
        return BrokerResult(
            ok=ok,
            request_id=request.request_id,
            status=response.status if not errors else "failed",
            staging_dir=str(staging),
            artifacts=tuple(artifacts),
            provider=response.provider,
            error=response.error if not errors else {"kind": "contract_error", "messages": errors},
        )

    @staticmethod
    def _identity(provider: dict[str, Any]) -> str:
        return ":".join(str(provider.get(key) or "") for key in ("id", "session_id"))
