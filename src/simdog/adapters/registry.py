from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

from .command import CommandAdapter
from .comsol import ComsolAdapter


def adapter_factories() -> dict[str, Any]:
    factories: dict[str, Any] = {"command": CommandAdapter, "comsol": ComsolAdapter}
    for item in entry_points(group="simdog.solver_adapters"):
        factories[item.name] = item.load()
    return factories
