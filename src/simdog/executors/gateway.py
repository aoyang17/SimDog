from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
import shlex
import uuid
from typing import Any, Callable

from simdog.util import load_data
from .transport import RemoteCommand, TransportResult


class GatewayError(RuntimeError):
    pass


@dataclass(frozen=True)
class GatewaySSHConfig:
    connection_id: str
    host: str
    port: int
    user: str
    instance_selection: str
    instance_id: str
    password_file: Path
    environment_script: str
    work_root: str
    strict_host_key_checking: bool = True

    @classmethod
    def load(cls, path: str | Path) -> "GatewaySSHConfig":
        value = load_data(path)
        if not isinstance(value, dict) or value.get("schema_version") != "simdog.gateway-ssh.v1":
            raise GatewayError("invalid gateway SSH configuration")
        ssh = value.get("ssh") or {}
        gateway = value.get("gateway") or {}
        authentication = value.get("authentication") or {}
        remote = value.get("remote") or {}
        if authentication.get("kind") != "password_file":
            raise GatewayError("gateway authentication must use an external password_file reference")
        config = cls(
            connection_id=str(value.get("connection_id") or "").strip(),
            host=str(ssh.get("host") or "").strip(),
            port=int(ssh.get("port") or 22),
            user=str(ssh.get("user") or "").strip(),
            instance_selection=str(gateway.get("instance_selection") or "").strip(),
            instance_id=str(gateway.get("instance_id") or "").strip(),
            password_file=Path(str(authentication.get("password_file") or "")).expanduser(),
            environment_script=str(remote.get("environment_script") or "").strip(),
            work_root=str(remote.get("work_root") or "").strip(),
            strict_host_key_checking=bool(ssh.get("strict_host_key_checking", True)),
        )
        missing = [
            name for name in (
                "connection_id", "host", "user", "instance_selection",
                "environment_script", "work_root",
            ) if not getattr(config, name)
        ]
        if missing or not str(config.password_file):
            raise GatewayError("missing gateway configuration fields: " + ", ".join(missing or ["password_file"]))
        if not 1 <= config.port <= 65535:
            raise GatewayError("gateway SSH port must be between 1 and 65535")
        if not config.strict_host_key_checking:
            raise GatewayError("StrictHostKeyChecking cannot be disabled")
        return config


class InteractiveGatewayTransport:
    """PaperEngine-compatible password gateway with argv-first commands.

    The remote gateway exposes an interactive shell, so argv must be serialized
    at that final boundary. Every field is individually shell-quoted and no raw
    agent/provider string is accepted as a command.
    """

    def __init__(self, config: GatewaySSHConfig, spawn: Callable[..., Any] | None = None) -> None:
        self.config = config
        self._spawn = spawn

    def run(self, command: RemoteCommand) -> TransportResult:
        self._require_work_path(command.cwd)
        script = self.render_remote_script(command)
        return self._run_script(script, timeout=int(command.timeout_seconds))

    def probe(self) -> dict[str, Any]:
        checks = []
        for argv in (("comsol", "--version"), ("sbatch", "--version")):
            result = self._run_script(
                self._environment_prefix() + shlex.join(argv), timeout=60
            )
            checks.append({"argv": list(argv), **result.as_dict()})
        return {"ok": all(item["ok"] for item in checks), "checks": checks}

    def ensure_workdir(self, remote_workdir: str) -> TransportResult:
        self._require_work_path(remote_workdir)
        return self._run_script(f"mkdir -p {self._remote_path(remote_workdir)}", timeout=60)

    def render_remote_script(self, command: RemoteCommand) -> str:
        self._require_work_path(command.cwd)
        env_parts = []
        for key, value in command.environment.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise GatewayError(f"invalid remote environment key: {key}")
            if "\x00" in value or "\n" in value or "\r" in value:
                raise GatewayError(f"invalid remote environment value: {key}")
            env_parts.append(f"{key}={shlex.quote(value)}")
        environment = "env " + " ".join(env_parts) + " " if env_parts else ""
        return (
            f"cd {self._remote_path(command.cwd)} && "
            + self._environment_prefix()
            + environment
            + shlex.join(command.argv)
        )

    def upload(self, local_path: str | Path, remote_path: str, timeout: int = 600) -> TransportResult:
        source = Path(local_path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"upload source does not exist: {source}")
        self._require_work_path(remote_path)
        args = self._scp_args()
        if source.is_dir():
            args.append("-r")
        args.extend([str(source), f"{self.config.host}:{remote_path}"])
        return self._transfer(args, timeout)

    def download(self, remote_path: str, local_path: str | Path, timeout: int = 1800) -> TransportResult:
        self._require_work_path(remote_path)
        destination = Path(local_path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        args = self._scp_args()
        args.extend(["-r", f"{self.config.host}:{remote_path}", str(destination)])
        return self._transfer(args, timeout)

    def _environment_prefix(self) -> str:
        return (
            'export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" && '
            f"source {self._remote_path(self.config.environment_script)} && "
        )

    def _run_script(self, script: str, timeout: int) -> TransportResult:
        pexpect = self._pexpect()
        child = self._spawn_ssh(pexpect, timeout)
        chunks: list[str] = []
        try:
            self._authenticate(child, pexpect, chunks, timeout)
            child.send("stty -echo\r")
            if child.expect([r"(?m)[^\r\n]*[#$] ?$", pexpect.EOF, pexpect.TIMEOUT]) != 0:
                raise GatewayError("could not disable remote command echo")
            chunks.clear()
            marker = f"__SIMDOG_DONE_{uuid.uuid4().hex}__"
            wrapped = f"{script}; simdog_rc=$?; printf '\\n{marker}:%s\\n' \"$simdog_rc\""
            child.send(wrapped + "\r")
            finished = child.expect([rf"{re.escape(marker)}:(\d+)\r?\n", pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
            chunks.append(child.before or "")
            if finished != 0:
                raise GatewayError("remote command did not finish before disconnect or timeout")
            returncode = int(child.match.group(1))
            child.send("exit\r")
            output = self._clean_output("".join(chunks))
            return TransportResult(returncode, output, "" if returncode == 0 else output)
        finally:
            child.close(force=True)

    def _transfer(self, args: list[str], timeout: int) -> TransportResult:
        pexpect = self._pexpect()
        child = (self._spawn or pexpect.spawn)("scp", args, encoding="utf-8", timeout=timeout)
        chunks: list[str] = []
        last_percent: int | None = None
        try:
            self._password_prompt(child, pexpect, chunks)
            if not self.config.instance_id:
                self._instance_prompt(child, pexpect, chunks)
            while True:
                quiet_timeout = min(timeout, 30) if last_percent is not None else timeout
                completed = child.expect(
                    [r"([0-9]{1,3})%", r"(?m)[^\r\n]*[#$] ?$", pexpect.EOF, pexpect.TIMEOUT],
                    timeout=quiet_timeout,
                )
                chunks.append(child.before or "")
                if completed == 0:
                    chunks.append(child.after or "")
                    last_percent = int(child.match.group(1))
                    continue
                if completed == 1:
                    child.send("exit\r")
                    return TransportResult(0, self._clean_output("".join(chunks)))
                if completed == 2:
                    if last_percent == 100:
                        return TransportResult(0, "transfer completed; gateway closed after 100%")
                    returncode = child.exitstatus if child.exitstatus is not None else 1
                    return TransportResult(returncode, self._clean_output("".join(chunks)))
                if last_percent == 100:
                    return TransportResult(0, "transfer completed; gateway remained open after 100%")
                raise GatewayError("SCP transfer timed out before completion")
        finally:
            child.close(force=True)

    def _spawn_ssh(self, pexpect: Any, timeout: int) -> Any:
        args = [
            "-tt", "-p", str(self.config.port),
            "-o", "StrictHostKeyChecking=yes",
            "-o", "PreferredAuthentications=password,keyboard-interactive",
            "-o", "PubkeyAuthentication=no",
            f"{self._login_user()}@{self.config.host}",
        ]
        return (self._spawn or pexpect.spawn)("ssh", args, encoding="utf-8", timeout=timeout)

    def _authenticate(self, child: Any, pexpect: Any, chunks: list[str], timeout: int) -> None:
        self._password_prompt(child, pexpect, chunks)
        if not self.config.instance_id:
            self._instance_prompt(child, pexpect, chunks)
        entered = child.expect([r"(?m)[^\r\n]*[#$] ?$", pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
        chunks.append(child.before or "")
        if entered != 0:
            raise GatewayError("selected instance did not produce a remote shell")

    def _password_prompt(self, child: Any, pexpect: Any, chunks: list[str]) -> None:
        matched = child.expect([r"(?i)password[^:]*:", r"密码[^:：]*[:：]", pexpect.EOF, pexpect.TIMEOUT])
        chunks.append(child.before or "")
        if matched >= 2:
            raise GatewayError("SSH password prompt was not reached")
        child.send(self._read_password() + "\r")

    def _instance_prompt(self, child: Any, pexpect: Any, chunks: list[str]) -> None:
        selected = child.expect([r"认证成功[^\r\n]*实例", r"(?i)select[^\r\n]*instance", pexpect.EOF, pexpect.TIMEOUT])
        chunks.append(child.before or "")
        if selected >= 2:
            raise GatewayError("SSH gateway instance menu was not reached")
        child.send(self.config.instance_selection + "\r")

    def _read_password(self) -> str:
        try:
            mode = self.config.password_file.stat().st_mode & 0o777
            if mode & 0o077:
                raise GatewayError("password file must not be accessible by group or others")
            password = self.config.password_file.read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as exc:
            raise GatewayError(f"cannot read password file: {exc}") from exc
        if not password:
            raise GatewayError("password file is empty")
        return password

    def _login_user(self) -> str:
        return f"{self.config.user}::{self.config.instance_id}" if self.config.instance_id else self.config.user

    def _scp_args(self) -> list[str]:
        return [
            "-P", str(self.config.port),
            "-o", "StrictHostKeyChecking=yes",
            "-o", "PreferredAuthentications=password,keyboard-interactive",
            "-o", "PubkeyAuthentication=no",
            "-o", f"User={self._login_user()}",
        ]

    def _require_work_path(self, value: str) -> None:
        if not value or any(char in value for char in ("\x00", "\n", "\r")):
            raise GatewayError("invalid remote path")
        if not re.fullmatch(r"~?/[A-Za-z0-9_./-]+", value):
            raise GatewayError("remote path contains unsupported characters")
        root = self.config.work_root.rstrip("/")
        if value != root and not value.startswith(root + "/"):
            raise GatewayError(f"remote path is outside configured work root: {value}")

    @staticmethod
    def _remote_path(value: str) -> str:
        if not value or any(char in value for char in ("\x00", "\n", "\r")):
            raise GatewayError("invalid remote path")
        if value.startswith("~/"):
            return '"$HOME"/' + shlex.quote(value[2:])
        return shlex.quote(value)

    @staticmethod
    def _pexpect() -> Any:
        try:
            import pexpect
        except ImportError as exc:
            raise GatewayError("interactive gateway transport requires pexpect>=4.8") from exc
        return pexpect

    @staticmethod
    def _clean_output(value: str) -> str:
        without_ansi = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
        return without_ansi.replace("\r", "").strip()
