from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any

from simdog.util import atomic_json, load_data, sha256_file


class WorkflowError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Controller:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.state_path = self.root / "workflow.json"
        if not self.state_path.is_file():
            raise WorkflowError(f"missing workflow state: {self.state_path}")
        self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.template = load_data(self.root / str(self.state["template"]))

    def status(self) -> dict[str, Any]:
        return {"ok": True, **self.state}

    def active_stage_spec(self) -> dict[str, Any] | None:
        stage_id = self.state.get("active_stage")
        return dict(self._spec(str(stage_id))) if stage_id else None

    def stage_specs(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._stage_specs()]

    def _stage_specs(self) -> list[dict[str, Any]]:
        return list(self.template.get("stages") or [])

    def _spec(self, stage_id: str) -> dict[str, Any]:
        for item in self._stage_specs():
            if item.get("id") == stage_id:
                return item
        raise WorkflowError(f"unknown stage: {stage_id}")

    def prepare(self) -> dict[str, Any]:
        stage_id = self.state.get("active_stage")
        if not stage_id:
            raise WorkflowError("workflow is complete")
        record = self.state["stages"][stage_id]
        if record["status"] not in {"ready", "in_progress"}:
            raise WorkflowError(f"stage is not ready: {stage_id}")
        spec = self._spec(stage_id)
        task = {
            "protocol_version": "simdog.stage.v1",
            "workflow_id": self.state["workflow_id"],
            "cycle": self.state["cycle"],
            "stage": stage_id,
            "role": spec.get("role"),
            "objective": spec.get("objective"),
            "required_outputs": spec.get("required_outputs") or [],
            "constraints": spec.get("constraints") or {},
        }
        task_path = self.root / "stages" / stage_id / "task.json"
        atomic_json(task_path, task)
        if record["status"] == "ready":
            record["attempts"] += 1
        record["status"] = "in_progress"
        self._event("stage_prepared", stage_id)
        self._save()
        return {"ok": True, "stage": stage_id, "task": str(task_path), "required_outputs": task["required_outputs"]}

    def validate_active(self) -> dict[str, Any]:
        stage_id = self.state.get("active_stage")
        if not stage_id:
            raise WorkflowError("workflow is complete")
        spec = self._spec(stage_id)
        directory = self.root / "stages" / stage_id
        errors: list[str] = []
        outputs: list[dict[str, Any]] = []
        for name in spec.get("required_outputs") or []:
            path = (directory / str(name)).resolve()
            try:
                path.relative_to(directory.resolve())
            except ValueError:
                errors.append(f"output escapes stage directory: {name}")
                continue
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"missing required output: {name}")
            else:
                outputs.append({"path": name, "size": path.stat().st_size, "sha256": sha256_file(path)})
        return {"ok": not errors, "stage": stage_id, "errors": errors, "outputs": outputs}

    def submit(self) -> dict[str, Any]:
        validation = self.validate_active()
        stage_id = str(validation["stage"])
        record = self.state["stages"][stage_id]
        record["validation"] = validation
        if not validation["ok"]:
            record["status"] = "in_progress"
            self._event("stage_validation_failed", stage_id, {"errors": validation["errors"]})
            self._save()
            return validation
        record["status"] = "complete"
        record["completed_at"] = _now()
        record["outputs"] = validation["outputs"]
        specs = self._stage_specs()
        index = next(i for i, item in enumerate(specs) if item["id"] == stage_id)
        if index + 1 == len(specs):
            if self._spec(stage_id).get("role") == "reviewer":
                review_path = self.root / "stages" / stage_id / "review.json"
                review = json.loads(review_path.read_text(encoding="utf-8"))
                if review.get("decision") != "accepted":
                    return self._rework(stage_id, str(review.get("return_stage") or ""), review)
            self.state["active_stage"] = None
            self.state["status"] = "complete"
            publication = {
                "schema_version": "simdog.publication.v1",
                "workflow_id": self.state["workflow_id"],
                "cycle": self.state["cycle"],
                "completed_at": _now(),
                "stages": self.state["stages"],
            }
            atomic_json(self.root / "publication.json", publication)
            self._event("workflow_completed", stage_id)
            self._save()
            return {"ok": True, "status": "complete", "publication": str(self.root / "publication.json")}
        next_stage = str(specs[index + 1]["id"])
        self.state["active_stage"] = next_stage
        self.state["stages"][next_stage]["status"] = "ready"
        self._event("stage_completed", stage_id, {"next_stage": next_stage})
        self._save()
        return {"ok": True, "stage": stage_id, "next_stage": next_stage}

    def promote_agent_result(self, result: Any) -> dict[str, Any]:
        """Promote a broker-validated proposal without completing the stage."""
        value = result.as_dict() if hasattr(result, "as_dict") else dict(result)
        if not value.get("ok") or value.get("status") != "completed":
            raise WorkflowError("cannot promote an unsuccessful agent result")
        stage_id = self.state.get("active_stage")
        if not stage_id:
            raise WorkflowError("workflow is complete")
        record = self.state["stages"][stage_id]
        if record["status"] not in {"ready", "in_progress"}:
            raise WorkflowError(f"active stage does not accept artifacts: {stage_id}")
        provider = dict(value.get("provider") or {})
        identity = self._provider_identity(provider)
        if self._spec(stage_id).get("role") == "reviewer" and identity in self.producer_identities():
            raise WorkflowError("reviewer must use an identity independent of producing stages")
        staging = Path(str(value.get("staging_dir") or "")).expanduser().resolve()
        allowed_staging = (self.root / ".simdog" / "staging").resolve()
        try:
            staging.relative_to(allowed_staging)
        except ValueError as exc:
            raise WorkflowError("broker staging directory is outside this workspace") from exc
        required = set(self._spec(stage_id).get("required_outputs") or [])
        artifacts = list(value.get("artifacts") or [])
        offered = {str(item.get("name") or "") for item in artifacts}
        missing = sorted(required - offered)
        unexpected = sorted(offered - required)
        if missing or unexpected:
            messages = []
            if missing:
                messages.append("missing stage artifacts: " + ", ".join(missing))
            if unexpected:
                messages.append("undeclared stage artifacts: " + ", ".join(unexpected))
            raise WorkflowError("; ".join(messages))
        stage_dir = (self.root / "stages" / stage_id).resolve()
        receipt = staging / "broker_receipt.json"
        if not receipt.is_file():
            raise WorkflowError("broker receipt is missing")
        verified: list[tuple[dict[str, Any], Path, Path]] = []
        for artifact in artifacts:
            name = str(artifact["name"])
            source = Path(str(artifact["path"])).expanduser().resolve()
            try:
                source.relative_to(staging)
            except ValueError as exc:
                raise WorkflowError(f"artifact is outside broker staging: {name}") from exc
            if not source.is_file() or sha256_file(source) != artifact.get("sha256"):
                raise WorkflowError(f"artifact hash verification failed: {name}")
            destination = (stage_dir / name).resolve()
            try:
                destination.relative_to(stage_dir)
            except ValueError as exc:
                raise WorkflowError(f"artifact escapes stage directory: {name}") from exc
            if destination.exists():
                raise WorkflowError(f"canonical stage artifact already exists: {name}")
            verified.append((artifact, source, destination))
        promoted: list[dict[str, Any]] = []
        for artifact, source, destination in verified:
            name = str(artifact["name"])
            temporary = destination.with_suffix(destination.suffix + ".promoting")
            shutil.copy2(source, temporary)
            temporary.replace(destination)
            promoted.append({"name": name, "sha256": artifact["sha256"]})
        provenance_dir = self.root / ".simdog" / "provenance" / stage_id
        provenance_dir.mkdir(parents=True, exist_ok=True)
        provenance = provenance_dir / f"{value['request_id']}.json"
        shutil.copy2(receipt, provenance)
        record["agent_identity"] = identity
        record["agent_provider"] = provider
        record["agent_request_id"] = value["request_id"]
        record["status"] = "in_progress"
        self._event("agent_artifacts_promoted", stage_id, {"request_id": value["request_id"], "artifacts": promoted})
        self._save()
        return {"ok": True, "stage": stage_id, "promoted": promoted, "provenance": str(provenance)}

    def producer_identities(self) -> set[str]:
        identities: set[str] = set()
        for spec in self._stage_specs():
            if spec.get("role") == "reviewer":
                continue
            identity = str(self.state["stages"][str(spec["id"])].get("agent_identity") or "")
            if identity:
                identities.add(identity)
        return identities

    @staticmethod
    def _provider_identity(provider: dict[str, Any]) -> str:
        provider_id = str(provider.get("id") or "")
        session_id = str(provider.get("session_id") or "")
        if not provider_id or not session_id:
            raise WorkflowError("provider id and session_id are required for canonical promotion")
        return f"{provider_id}:{session_id}"

    def _rework(self, review_stage: str, return_stage: str, review: dict[str, Any]) -> dict[str, Any]:
        ids = [str(item["id"]) for item in self._stage_specs()]
        if return_stage not in ids or ids.index(return_stage) >= ids.index(review_stage):
            raise WorkflowError("review must return to an earlier valid stage")
        archive = self.root / "archive" / f"cycle-{self.state['cycle']:03d}"
        archive.mkdir(parents=True, exist_ok=True)
        for stage_id in ids[ids.index(return_stage):]:
            source = self.root / "stages" / stage_id
            destination = archive / stage_id
            if source.exists() and any(source.iterdir()):
                shutil.copytree(source, destination)
                for item in source.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
            record = self.state["stages"][stage_id]
            record["status"] = "ready" if stage_id == return_stage else "pending"
            record["completed_at"] = None
            record.pop("validation", None)
            record.pop("outputs", None)
        self.state["cycle"] += 1
        self.state["active_stage"] = return_stage
        self._event("review_rejected", review_stage, {"return_stage": return_stage, "findings": review.get("findings") or []})
        self._save()
        return {"ok": True, "status": "rework", "return_stage": return_stage, "archive": str(archive)}

    def _event(self, event: str, stage: str, extra: dict[str, Any] | None = None) -> None:
        self.state["history"].append({"at": _now(), "event": event, "stage": stage, **(extra or {})})

    def _save(self) -> None:
        self.state["updated_at"] = _now()
        atomic_json(self.state_path, self.state)
