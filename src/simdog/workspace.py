from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import shutil

from simdog.util import atomic_json, load_data


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_workspace(root: str | Path, template_path: str | Path, title: str) -> dict[str, Any]:
    target = Path(root).expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError(f"workspace is not empty: {target}")
    template = load_data(template_path)
    if not isinstance(template, dict) or template.get("schema_version") != "simdog.workflow.v1":
        raise ValueError("unsupported workflow template")
    stages = template.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError("workflow template requires stages")
    stage_ids = [str(stage.get("id") or "") for stage in stages]
    if any(not item for item in stage_ids) or len(stage_ids) != len(set(stage_ids)):
        raise ValueError("workflow stage ids must be non-empty and unique")
    target.mkdir(parents=True, exist_ok=True)
    for child in ("source", "model", "runs", "reports", "archive", "stages", ".simdog"):
        (target / child).mkdir()
    copied_template = target / "workflow_template.yml"
    shutil.copy2(template_path, copied_template)
    for stage_id in stage_ids:
        (target / "stages" / stage_id).mkdir()
    now = utc_now()
    state = {
        "schema_version": "simdog.state.v1",
        "workflow_id": target.name,
        "title": title,
        "template": "workflow_template.yml",
        "status": "active",
        "cycle": 1,
        "active_stage": stage_ids[0],
        "created_at": now,
        "updated_at": now,
        "stages": {
            stage_id: {
                "status": "ready" if index == 0 else "pending",
                "attempts": 0,
                "completed_at": None,
            }
            for index, stage_id in enumerate(stage_ids)
        },
        "history": [{"at": now, "event": "workspace_initialized", "stage": stage_ids[0]}],
    }
    atomic_json(target / "workflow.json", state)
    (target / "policy.yml").write_text(
        "schema_version: simdog.policy.v1\n"
        "allowed_executables: []\n"
        "max_timeout_seconds: 3600\n"
        "canonical_state_writes: controller_only\n"
        "archive_before_rework: true\n",
        encoding="utf-8",
    )
    return {"ok": True, "root": str(target), "workflow_id": target.name, "active_stage": stage_ids[0]}
