from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any


def provider_factories() -> dict[str, Any]:
    factories: dict[str, Any] = {}
    for item in entry_points(group="simdog.agent_providers"):
        factories[item.name] = item.load()
    return factories
