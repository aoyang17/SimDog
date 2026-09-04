from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from simdog.acceptance import evaluate_acceptance
from simdog.adapters.command import CommandAdapter
from simdog.adapters.registry import adapter_factories
from simdog.executors.local import ExecutionPolicy, LocalExecutor
from simdog.executors.slurm import SlurmExecutor, SlurmJob
from simdog.executors.gateway import GatewaySSHConfig, InteractiveGatewayTransport
from simdog.executors.ssh import SSHConfig, SSHTransport
from simdog.providers.conformance import inspect_provider
from simdog.providers.recording import RecordingProvider
from simdog.simulation import SimulationRunController, prepare_simulation
from simdog.util import atomic_json, contained_path, load_data
from simdog.workflow import Controller
from simdog.workspace import initialize_workspace


def _emit(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="simdog")
    sub = root.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--root", required=True)
    init.add_argument("--template", required=True)
    init.add_argument("--title", required=True)
    for name in ("status", "prepare", "check-stage", "submit"):
        item = sub.add_parser(name)
        item.add_argument("--root", required=True)
    run = sub.add_parser("run-command")
    run.add_argument("--root", required=True)
    run.add_argument("--spec", required=True)
    run.add_argument("--result")
    validate = sub.add_parser("validate")
    validate.add_argument("--case", required=True)
    validate.add_argument("--metrics", required=True)
    validate.add_argument("--report")
    sub.add_parser("adapters")
    sub.add_parser("providers")
    plan = sub.add_parser("plan-adapter")
    plan.add_argument("--adapter", required=True)
    plan.add_argument("--spec", required=True)
    execute_adapter = sub.add_parser("run-adapter")
    execute_adapter.add_argument("--root", required=True)
    execute_adapter.add_argument("--adapter", required=True)
    execute_adapter.add_argument("--spec", required=True)
    execute_adapter.add_argument("--result")
    slurm = sub.add_parser("slurm")
    slurm_sub = slurm.add_subparsers(dest="slurm_command", required=True)
    slurm_submit = slurm_sub.add_parser("submit")
    slurm_submit.add_argument("--config", required=True)
    slurm_submit.add_argument("--remote-workdir", required=True)
    slurm_submit.add_argument("--script", required=True)
    for name in ("status", "cancel"):
        item = slurm_sub.add_parser(name)
        item.add_argument("--config", required=True)
        item.add_argument("--remote-workdir", required=True)
        item.add_argument("--script", default="unknown.slurm")
        item.add_argument("--job-id", required=True)
    slurm_verify = slurm_sub.add_parser("verify")
    slurm_verify.add_argument("--config", required=True)
    slurm_verify.add_argument("--remote-workdir", required=True)
    slurm_verify.add_argument("--script", default="unknown.slurm")
    slurm_verify.add_argument("--job-id", required=True)
    slurm_verify.add_argument("--artifact", action="append", default=[])
    slurm_verify.add_argument("--file", action="append", default=[])
    slurm_verify.add_argument("--log", action="append", default=[])
    simulation = sub.add_parser("simulation")
    simulation_sub = simulation.add_subparsers(dest="simulation_command", required=True)
    simulation_prepare = simulation_sub.add_parser("prepare")
    simulation_prepare.add_argument("--profile", required=True)
    simulation_prepare.add_argument("--run-id")
    simulation_record = simulation_sub.add_parser("record-submission")
    simulation_record.add_argument("--workspace", required=True)
    simulation_record.add_argument("--job-id", required=True)
    simulation_record.add_argument("--remote-workdir", required=True)
    simulation_record.add_argument("--script", required=True)
    simulation_downloads = simulation_sub.add_parser("record-downloads")
    simulation_downloads.add_argument("--workspace", required=True)
    simulation_downloads.add_argument("--path", action="append", required=True)
    gateway = sub.add_parser("gateway")
    gateway_sub = gateway.add_subparsers(dest="gateway_command", required=True)
    gateway_probe = gateway_sub.add_parser("probe")
    gateway_probe.add_argument("--config", required=True)
    gateway_ensure = gateway_sub.add_parser("ensure-workdir")
    gateway_ensure.add_argument("--config", required=True)
    gateway_ensure.add_argument("--remote-workdir", required=True)
    gateway_upload = gateway_sub.add_parser("upload")
    gateway_upload.add_argument("--config", required=True)
    gateway_upload.add_argument("--local", required=True)
    gateway_upload.add_argument("--remote", required=True)
    gateway_download = gateway_sub.add_parser("download")
    gateway_download.add_argument("--config", required=True)
    gateway_download.add_argument("--remote", required=True)
    gateway_download.add_argument("--local", required=True)
    gateway_submit = gateway_sub.add_parser("submit")
    gateway_submit.add_argument("--config", required=True)
    gateway_submit.add_argument("--remote-workdir", required=True)
    gateway_submit.add_argument("--script", required=True)
    for name in ("status", "cancel"):
        item = gateway_sub.add_parser(name)
        item.add_argument("--config", required=True)
        item.add_argument("--remote-workdir", required=True)
        item.add_argument("--job-id", required=True)
    gateway_verify = gateway_sub.add_parser("verify")
    gateway_verify.add_argument("--config", required=True)
    gateway_verify.add_argument("--remote-workdir", required=True)
    gateway_verify.add_argument("--job-id", required=True)
    gateway_verify.add_argument("--artifact", action="append", default=[])
    gateway_verify.add_argument("--file", action="append", default=[])
    gateway_verify.add_argument("--log", action="append", default=[])
    gateway_verify.add_argument("--record-workspace")
    return root


def run(args: argparse.Namespace) -> int:
    if args.command == "init":
        _emit(initialize_workspace(args.root, args.template, args.title))
        return 0
    if args.command in {"status", "prepare", "check-stage", "submit"}:
        controller = Controller(args.root)
        operation = {
            "status": controller.status,
            "prepare": controller.prepare,
            "check-stage": controller.validate_active,
            "submit": controller.submit,
        }[args.command]
        result = operation()
        _emit(result)
        return 0 if result.get("ok") else 1
    if args.command == "run-command":
        workspace = Path(args.root).expanduser().resolve()
        spec = load_data(args.spec)
        policy_data = load_data(workspace / "policy.yml")
        policy = ExecutionPolicy(
            allowed_executables=tuple(policy_data.get("allowed_executables") or []),
            max_timeout_seconds=float(policy_data.get("max_timeout_seconds") or 3600),
            allowed_environment=tuple(policy_data.get("allowed_environment") or []),
        )
        request = CommandAdapter().execution_request(spec)
        result = LocalExecutor(workspace, policy).execute(request).as_dict()
        if args.result:
            atomic_json(args.result, result)
        _emit(result)
        return 0 if result["execution_ok"] else 1
    if args.command == "validate":
        case = load_data(args.case)
        metrics = load_data(args.metrics)
        result = evaluate_acceptance(list(case.get("acceptance") or []), metrics)
        if args.report:
            atomic_json(args.report, result)
        _emit(result)
        return 0 if result["passed"] else 1
    if args.command == "adapters":
        manifests = []
        for name, factory in sorted(adapter_factories().items()):
            adapter = factory()
            manifests.append({"registration": name, **asdict(adapter.manifest())})
        _emit({"ok": True, "adapters": manifests})
        return 0
    if args.command == "providers":
        _emit({
            "ok": True,
            "provider_kinds": [
                {
                    "kind": "recording",
                    "configuration": "none",
                    "purpose": "deterministic offline tests",
                    "conformance": inspect_provider(RecordingProvider()),
                },
                {
                    "kind": "process-json-stdio",
                    "configuration": "argv + timeout",
                    "purpose": "local vendor or agent-framework bridge",
                },
                {
                    "kind": "native-https-gateway",
                    "configuration": "HTTPS endpoint + secret environment reference + truthful capabilities",
                    "purpose": "remote Codex/OpenAI/Anthropic/local-model gateway",
                },
            ],
        })
        return 0
    if args.command == "plan-adapter":
        factories = adapter_factories()
        if args.adapter not in factories:
            raise ValueError(f"unknown solver adapter: {args.adapter}")
        adapter = factories[args.adapter]()
        spec = load_data(args.spec)
        if hasattr(adapter, "build_plan"):
            plan = adapter.build_plan(spec)
            result = {
                "ok": True,
                "adapter": asdict(adapter.manifest()),
                "plan": asdict(plan),
            }
        else:
            result = {
                "ok": True,
                "adapter": asdict(adapter.manifest()),
                "plan": {"steps": [asdict(adapter.execution_request(spec))]},
            }
        _emit(result)
        return 0
    if args.command == "run-adapter":
        workspace = Path(args.root).expanduser().resolve()
        policy_data = load_data(workspace / "policy.yml")
        policy = ExecutionPolicy(
            allowed_executables=tuple(policy_data.get("allowed_executables") or []),
            max_timeout_seconds=float(policy_data.get("max_timeout_seconds") or 3600),
            allowed_environment=tuple(policy_data.get("allowed_environment") or []),
        )
        factories = adapter_factories()
        if args.adapter not in factories:
            raise ValueError(f"unknown solver adapter: {args.adapter}")
        adapter = factories[args.adapter]()
        spec = load_data(args.spec)
        requests = (
            adapter.build_plan(spec).steps
            if hasattr(adapter, "build_plan")
            else (adapter.execution_request(spec),)
        )
        executor = LocalExecutor(workspace, policy)
        step_results = []
        for index, request in enumerate(requests, 1):
            executed = executor.execute(request)
            step_results.append({"step": index, **executed.as_dict()})
            if not executed.execution_ok:
                break
        result = {
            "ok": len(step_results) == len(requests) and all(item["execution_ok"] for item in step_results),
            "adapter": asdict(adapter.manifest()),
            "steps": step_results,
        }
        if args.result:
            atomic_json(contained_path(workspace, args.result), result)
        _emit(result)
        return 0 if result["ok"] else 1
    if args.command == "slurm":
        slurm = SlurmExecutor(SSHTransport(SSHConfig.load(args.config)))
        if args.slurm_command == "submit":
            _emit({"ok": True, **asdict(slurm.submit(remote_workdir=args.remote_workdir, script=args.script))})
            return 0
        job = SlurmJob(args.job_id, args.remote_workdir, args.script)
        if args.slurm_command == "status":
            result = slurm.status(job).as_dict()
        elif args.slurm_command == "cancel":
            result = slurm.cancel(job).as_dict()
        else:
            result = slurm.verify(
                job, required_artifacts=args.artifact, required_files=args.file, clean_logs=args.log,
            ).as_dict()
        _emit(result)
        return 0 if result["ok"] else 1
    if args.command == "simulation":
        if args.simulation_command == "prepare":
            result = prepare_simulation(Path.cwd(), args.profile, args.run_id)
        elif args.simulation_command == "record-submission":
            result = SimulationRunController(args.workspace).record_submission(
                args.job_id, args.remote_workdir, args.script,
            )
        else:
            result = SimulationRunController(args.workspace).record_downloads(args.path)
        _emit(result)
        return 0
    if args.command == "gateway":
        transport = InteractiveGatewayTransport(GatewaySSHConfig.load(args.config))
        if args.gateway_command == "probe":
            result = transport.probe()
        elif args.gateway_command == "ensure-workdir":
            result = transport.ensure_workdir(args.remote_workdir).as_dict()
        elif args.gateway_command == "upload":
            result = transport.upload(args.local, args.remote).as_dict()
        elif args.gateway_command == "download":
            result = transport.download(args.remote, args.local).as_dict()
        else:
            executor = SlurmExecutor(transport)
            if args.gateway_command == "submit":
                result = {"ok": True, **asdict(executor.submit(
                    remote_workdir=args.remote_workdir, script=args.script,
                ))}
            else:
                job = SlurmJob(args.job_id, args.remote_workdir, "")
                if args.gateway_command == "status":
                    result = executor.status(job).as_dict()
                elif args.gateway_command == "cancel":
                    result = executor.cancel(job).as_dict()
                else:
                    result = executor.verify(
                        job, required_artifacts=args.artifact, required_files=args.file, clean_logs=args.log,
                    ).as_dict()
                    if args.record_workspace:
                        SimulationRunController(args.record_workspace).record_verification(result)
        _emit(result)
        return 0 if result["ok"] else 1
    raise RuntimeError(f"unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parser().parse_args(argv))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
