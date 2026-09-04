from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml


def load_data(path: str | Path) -> Any:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def atomic_json(path: str | Path, value: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return target


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def contained_path(root: str | Path, value: str | Path) -> Path:
    base = Path(root).expanduser().resolve()
    candidate = Path(value)
    resolved = (base / candidate).resolve() if not candidate.is_absolute() else candidate.expanduser().resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"path escapes workspace: {value}") from exc
    return resolved
