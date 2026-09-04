from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from simdog.executors.transport import RemoteCommand
from simdog.executors.local import executable_allowed
from simdog.util import load_data


class RemotePolicyError(RuntimeError):
    pass


def _decode_envelope(token: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid remote command envelope") from exc
    if not isinstance(value, dict) or value.get("protocol_version") != "simdog.remote-command.v1":
        raise ValueError("unsupported remote command protocol")
    return value


def _under_one_root(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            pass
    return False


def execute_envelope(token: str, policy_path: str | Path) -> int:
    value = _decode_envelope(token)
    policy = load_data(policy_path)
    if not isinstance(policy, dict) or policy.get("schema_version") != "simdog.remote-policy.v1":
        raise RemotePolicyError("invalid remote execution policy")
    argv = value.get("argv")
    environment = value.get("environment") or {}
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
        raise ValueError("remote envelope argv must be a list of strings")
    if not isinstance(environment, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in environment.items()):
        raise ValueError("remote envelope environment must contain strings")
    allowed_executables = tuple(str(item) for item in policy.get("allowed_executables") or [])
    if not executable_allowed(argv[0], allowed_executables):
        raise RemotePolicyError(f"remote executable is not allowed: {argv[0]}")
    allowed_environment = set(policy.get("allowed_environment") or [])
    unexpected_environment = sorted(set(environment) - allowed_environment)
    if unexpected_environment:
        raise RemotePolicyError("remote environment keys are not allowed: " + ", ".join(unexpected_environment))
    roots = [Path(item).expanduser().resolve() for item in policy.get("allowed_roots") or []]
    if not roots:
        raise RemotePolicyError("remote policy has no allowed roots")
    cwd = Path(str(value.get("cwd") or "")).expanduser().resolve()
    if not cwd.is_dir() or not _under_one_root(cwd, roots):
        raise RemotePolicyError(f"remote cwd is outside allowed roots: {cwd}")
    timeout = float(value.get("timeout_seconds") or 0)
    max_timeout = float(policy.get("max_timeout_seconds") or 3600)
    if timeout <= 0 or timeout > max_timeout:
        raise RemotePolicyError("remote timeout exceeds policy")
    clean_environment = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
    clean_environment.update(environment)
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=clean_environment,
        timeout=timeout,
        check=False,
    )
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simdog-remote")
    sub = parser.add_subparsers(dest="command", required=True)
    execute = sub.add_parser("execute")
    execute.add_argument("--envelope", required=True)
    execute.add_argument(
        "--policy",
        default=os.environ.get("SIMDOG_REMOTE_POLICY", "/etc/simdog/remote-policy.yml"),
    )
    args = parser.parse_args(argv)
    try:
        return execute_envelope(args.envelope, args.policy)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 126


if __name__ == "__main__":
    raise SystemExit(main())
