from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Any

from simdog.util import atomic_json, contained_path, load_data, sha256_file


def prepare_simulation(
    project_root: str | Path,
    profile_path: str | Path,
    run_id: str | None = None,
) -> dict[str, Any]:
    project = Path(project_root).expanduser().resolve()
    profile_source = Path(profile_path).expanduser().resolve()
    profile = load_data(profile_source)
    if not isinstance(profile, dict) or profile.get("schema_version") != "simdog.simulation-profile.v1":
        raise ValueError("invalid simulation profile")
    simulation_id = str(profile.get("simulation_id") or "")
    if not simulation_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in simulation_id):
        raise ValueError("invalid simulation_id")
    stamp = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not stamp or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in stamp):
        raise ValueError("invalid run_id")
    workspace_root = contained_path(project, str(profile.get("workspace_root") or f"workspaces/{simulation_id}"))
    workspace = contained_path(workspace_root, stamp)
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError(f"simulation workspace is not empty: {workspace}")
    input_dir = workspace / "input"
    output_dir = workspace / "output"
    reports_dir = workspace / "reports"
    for directory in (input_dir, output_dir, reports_dir):
        directory.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    for item in profile.get("source_files") or []:
        if not isinstance(item, dict):
            raise ValueError("source_files entries must be objects")
        source_value = str(item.get("source") or "")
        if source_value.startswith("project://"):
            source = contained_path(project, source_value.removeprefix("project://"))
        else:
            source = Path(source_value).expanduser().resolve()
        name = str(item.get("name") or source.name)
        if Path(name).name != name or not source.is_file():
            raise ValueError(f"invalid simulation source: {source}")
        destination = input_dir / name
        shutil.copy2(source, destination)
        copied.append({
            "name": name,
            "source": str(source),
            "source_sha256": sha256_file(source),
            "snapshot": str(destination.relative_to(project)),
            "snapshot_sha256": sha256_file(destination),
        })
    manifest = {
        "schema_version": "simdog.simulation-run.v1",
        "simulation_id": simulation_id,
        "run_id": stamp,
        "profile": str(profile_source),
        "connection": str(profile.get("connection") or ""),
        "remote_workdir": str(profile.get("remote_workdir") or ""),
        "source_files": copied,
        "status": "prepared",
    }
    atomic_json(workspace / "run.json", manifest)
    return {"ok": True, "workspace": str(workspace), **manifest}


class SimulationRunController:
    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.path = self.workspace / "run.json"
        value = load_data(self.path)
        if not isinstance(value, dict) or value.get("schema_version") != "simdog.simulation-run.v1":
            raise ValueError("invalid simulation run workspace")
        self.state = value

    def record_submission(self, job_id: str, remote_workdir: str, script: str) -> dict[str, Any]:
        if not job_id or not job_id.replace("_", "").replace(".", "").isalnum():
            raise ValueError("invalid scheduler job id")
        self.state["status"] = "submitted"
        self.state["scheduler"] = {
            "kind": "slurm",
            "job_id": job_id,
            "remote_workdir": remote_workdir,
            "script": script,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
        self._event("submitted", {"job_id": job_id})
        self._save()
        return {"ok": True, **self.state}

    def record_verification(self, verification: dict[str, Any]) -> dict[str, Any]:
        if self.state.get("verification") == verification:
            return {"ok": True, **self.state}
        self.state["verification"] = verification
        self.state["status"] = "accepted" if verification.get("ok") else "rejected"
        self._event("verified", {"accepted": bool(verification.get("ok"))})
        self._save()
        return {"ok": True, **self.state}

    def record_downloads(self, paths: list[str | Path]) -> dict[str, Any]:
        artifacts = []
        for value in paths:
            path = Path(value).expanduser().resolve()
            try:
                relative = path.relative_to(self.workspace)
            except ValueError as exc:
                raise ValueError(f"download is outside run workspace: {path}") from exc
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"download is missing or empty: {path}")
            artifacts.append({
                "path": relative.as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            })
        self.state["downloaded_artifacts"] = artifacts
        self._event("downloads_hashed", {"count": len(artifacts)})
        self._save()
        return {"ok": True, "artifacts": artifacts}

    def _event(self, name: str, details: dict[str, Any]) -> None:
        self.state.setdefault("history", []).append({
            "at": datetime.now(timezone.utc).isoformat(),
            "event": name,
            **details,
        })

    def _save(self) -> None:
        atomic_json(self.path, self.state)
