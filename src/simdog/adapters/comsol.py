from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
from typing import Any

from simdog.executors.local import ExecutionRequest
from .base import AdapterCapabilities, AdapterManifest, ExecutionPlan


_PARAMETER_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _relative_artifact(value: Any, field: str) -> str:
    text = str(value or "")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or "\x00" in text or "\n" in text:
        raise ValueError(f"{field} must be a safe workspace-relative path")
    return text


class ComsolAdapter:
    """Translate a declarative COMSOL run spec into bounded argv requests."""

    adapter_id = "comsol"

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(build=True, run=True, remote=True)

    def manifest(self) -> AdapterManifest:
        return AdapterManifest(
            adapter_id=self.adapter_id,
            implementation_version="1",
            solver_family="COMSOL Multiphysics",
            capabilities=self.capabilities(),
            actions=("compile-java", "batch-mph", "compile-and-batch-java"),
        )

    def execution_request(self, spec: dict[str, Any]) -> ExecutionRequest:
        plan = self.build_plan(spec)
        if len(plan.steps) != 1:
            raise ValueError(f"COMSOL action {plan.action} contains multiple execution steps; use build_plan")
        return plan.steps[0]

    def build_plan(self, spec: dict[str, Any]) -> ExecutionPlan:
        action = str(spec.get("action") or "")
        if action not in self.manifest().actions:
            raise ValueError(f"unsupported COMSOL action: {action}")
        executable = str(spec.get("comsol_bin") or "comsol")
        if "\x00" in executable or "\n" in executable:
            raise ValueError("invalid COMSOL executable")
        cwd = str(spec.get("cwd") or ".")
        timeout = float(spec.get("timeout_seconds") or 3600)
        environment = dict(spec.get("environment") or {})
        steps: list[ExecutionRequest] = []
        if action in {"compile-java", "compile-and-batch-java"}:
            source = _relative_artifact(spec.get("java_source"), "java_source")
            class_file = _relative_artifact(
                spec.get("class_file") or str(Path(source).with_suffix(".class")), "class_file"
            )
            steps.append(ExecutionRequest(
                argv=(executable, "compile", source),
                cwd=cwd,
                timeout_seconds=timeout,
                environment=environment,
                expected_outputs=(class_file,),
                clean_log_patterns=tuple(spec.get("clean_log_patterns") or []),
            ))
        if action in {"batch-mph", "compile-and-batch-java"}:
            if action == "batch-mph":
                input_file = _relative_artifact(spec.get("input_model"), "input_model")
            else:
                input_file = _relative_artifact(
                    spec.get("class_file") or str(Path(str(spec.get("java_source"))).with_suffix(".class")),
                    "class_file",
                )
            batch_log = _relative_artifact(spec.get("batch_log") or "comsol_batch.log", "batch_log")
            argv = [executable, "batch", "-inputfile", input_file, "-batchlog", batch_log]
            output_model = spec.get("output_model")
            if output_model:
                argv.extend(["-outputfile", _relative_artifact(output_model, "output_model")])
            if bool(spec.get("nosave", False)):
                argv.append("-nosave")
            parameters = spec.get("parameters") or {}
            if not isinstance(parameters, dict):
                raise ValueError("COMSOL parameters must be an object")
            if parameters:
                argv.append("-prodargs")
                for key, value in parameters.items():
                    if not _PARAMETER_KEY.fullmatch(str(key)):
                        raise ValueError(f"invalid COMSOL parameter key: {key}")
                    rendered = str(value)
                    if "\x00" in rendered or "\n" in rendered or "\r" in rendered:
                        raise ValueError(f"invalid COMSOL parameter value: {key}")
                    argv.append(f"{key}={rendered}")
            expected = [batch_log]
            expected.extend(_relative_artifact(item, "expected_outputs") for item in spec.get("expected_outputs") or [])
            steps.append(ExecutionRequest(
                argv=tuple(argv),
                cwd=cwd,
                timeout_seconds=timeout,
                environment=environment,
                expected_outputs=tuple(dict.fromkeys(expected)),
                clean_log_patterns=tuple(spec.get("clean_log_patterns") or [
                    "Error", "Exception", "Singular matrix", "Repeated error test",
                ]),
            ))
        return ExecutionPlan(adapter_id=self.adapter_id, action=action, steps=tuple(steps))
