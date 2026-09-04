from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simdog.agents.broker import AgentBroker
from simdog.contracts import AgentRequest, ArtifactContract, InputReference
from simdog.providers.base import AgentProvider
from simdog.util import sha256_file
from simdog.workflow import Controller


def _media_type(name: str) -> str:
    suffix = Path(name).suffix.lower()
    return {
        ".json": "application/json",
        ".yml": "application/yaml",
        ".yaml": "application/yaml",
        ".md": "text/markdown",
        ".txt": "text/plain",
    }.get(suffix, "application/octet-stream")


@dataclass
class RoleProviderRouter:
    providers: dict[str, AgentProvider]
    default: AgentProvider | None = None

    def provider_for(self, role: str) -> AgentProvider:
        provider = self.providers.get(role) or self.default
        if provider is None:
            raise KeyError(f"no agent provider configured for role: {role}")
        return provider


class AgentOrchestrator:
    """Connect role providers to the controller without transferring authority."""

    def __init__(self, root: str | Path, router: RoleProviderRouter) -> None:
        self.root = Path(root).expanduser().resolve()
        self.controller = Controller(self.root)
        self.router = router
        self.broker = AgentBroker(self.root)

    def request_for_active_stage(self) -> AgentRequest:
        spec = self.controller.active_stage_spec()
        if spec is None:
            raise RuntimeError("workflow is complete")
        stage_id = str(spec["id"])
        inputs: list[InputReference] = []
        for prior_spec in self.controller.stage_specs():
            prior_id = str(prior_spec["id"])
            if prior_id == stage_id:
                break
            record = self.controller.state["stages"][prior_id]
            if record.get("status") != "complete":
                continue
            for output in record.get("outputs") or []:
                relative = Path("stages") / prior_id / str(output["path"])
                source = self.root / relative
                inputs.append(InputReference(
                    name=f"{prior_id}:{output['path']}",
                    uri=relative.as_posix(),
                    sha256=sha256_file(source),
                    media_type=_media_type(str(output["path"])),
                ))
        outputs = tuple(
            ArtifactContract(name=str(name), media_type=_media_type(str(name)))
            for name in spec.get("required_outputs") or []
        )
        return AgentRequest(
            workflow_id=str(self.controller.state["workflow_id"]),
            role=str(spec.get("role") or ""),
            objective=str(spec.get("objective") or ""),
            inputs=tuple(inputs),
            outputs=outputs,
            constraints={
                "stage": stage_id,
                "cycle": self.controller.state["cycle"],
                "canonical_writes": "forbidden",
                "proposal_mode": "mediated",
            },
        )

    def run_stage(self) -> dict[str, Any]:
        prepared = self.controller.prepare()
        request = self.request_for_active_stage()
        provider = self.router.provider_for(request.role)
        forbidden = self.controller.producer_identities() if request.role == "reviewer" else set()
        broker_result = self.broker.execute(
            provider,
            request,
            required_capabilities={"structured_output"},
            forbidden_identities=forbidden,
        )
        if not broker_result.ok:
            return {
                "ok": False,
                "status": broker_result.status,
                "stage": prepared["stage"],
                "broker": broker_result.as_dict(),
            }
        promotion = self.controller.promote_agent_result(broker_result)
        submission = self.controller.submit()
        return {
            "ok": bool(submission.get("ok")),
            "stage": prepared["stage"],
            "request_id": request.request_id,
            "promotion": promotion,
            "submission": submission,
        }

    def run_until_terminal(self, max_stages: int = 20) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for _ in range(max_stages):
            if self.controller.state.get("status") == "complete":
                return {"ok": True, "status": "complete", "stages": results}
            result = self.run_stage()
            results.append(result)
            if not result.get("ok") or result.get("submission", {}).get("status") == "rework":
                return {
                    "ok": False,
                    "status": result.get("submission", {}).get("status") or result.get("status") or "failed",
                    "stages": results,
                }
        return {"ok": False, "status": "stage_limit_exceeded", "stages": results}
