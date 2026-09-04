from __future__ import annotations

from dataclasses import asdict
from typing import Any

from simdog.contracts import AGENT_PROTOCOL_VERSION
from .base import AgentProvider


def inspect_provider(provider: AgentProvider) -> dict[str, Any]:
    manifest = provider.manifest()
    errors: list[str] = []
    if not manifest.provider_id.strip():
        errors.append("provider_id is required")
    if not manifest.implementation_version.strip():
        errors.append("implementation_version is required")
    if AGENT_PROTOCOL_VERSION not in manifest.protocol_versions:
        errors.append(f"provider must support {AGENT_PROTOCOL_VERSION}")
    if not manifest.capabilities.structured_output:
        errors.append("structured_output capability is required")
    return {"ok": not errors, "manifest": asdict(manifest), "errors": errors}
