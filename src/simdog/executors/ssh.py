from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import subprocess

from simdog.util import load_data

from .transport import RemoteCommand, TransportResult


_SAFE_HOST = re.compile(r"^[A-Za-z0-9.-]+$")
_SAFE_USER = re.compile(r"^[A-Za-z0-9_.-]+$")
_SAFE_HELPER = re.compile(r"^[A-Za-z0-9_./-]+$")


@dataclass(frozen=True)
class SSHConfig:
    host: str
    user: str
    port: int = 22
    identity_file: str | None = None
    known_hosts_file: str | None = None
    remote_helper: str = "simdog-remote"

    @classmethod
    def load(cls, path: str | Path) -> "SSHConfig":
        value = load_data(path)
        if not isinstance(value, dict) or value.get("schema_version") != "simdog.ssh.v1":
            raise ValueError("invalid SimDog SSH configuration")
        return cls(
            host=str(value.get("host") or ""),
            user=str(value.get("user") or ""),
            port=int(value.get("port") or 22),
            identity_file=value.get("identity_file"),
            known_hosts_file=value.get("known_hosts_file"),
            remote_helper=str(value.get("remote_helper") or "simdog-remote"),
        )

    def __post_init__(self) -> None:
        if not _SAFE_HOST.fullmatch(self.host):
            raise ValueError("invalid SSH host")
        if not _SAFE_USER.fullmatch(self.user):
            raise ValueError("invalid SSH user")
        if not 1 <= int(self.port) <= 65535:
            raise ValueError("SSH port must be between 1 and 65535")
        if not _SAFE_HELPER.fullmatch(self.remote_helper):
            raise ValueError("invalid remote helper command")


class SSHTransport:
    """Send a versioned command envelope to a policy-enforcing remote helper.

    The SSH client is launched as an argv array. User command fields are encoded
    as URL-safe base64 JSON and are never interpolated into a shell expression.
    """

    def __init__(self, config: SSHConfig, *, ssh_bin: str = "ssh") -> None:
        self.config = config
        self.ssh_bin = ssh_bin

    def command(self, remote: RemoteCommand) -> list[str]:
        envelope = {
            "protocol_version": "simdog.remote-command.v1",
            **asdict(remote),
        }
        token = base64.urlsafe_b64encode(
            json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).decode("ascii")
        argv = [
            self.ssh_bin,
            "-p", str(self.config.port),
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes",
        ]
        if self.config.identity_file:
            identity = Path(self.config.identity_file).expanduser().resolve()
            if not identity.is_file():
                raise FileNotFoundError(f"SSH identity file not found: {identity}")
            argv.extend(["-i", str(identity)])
        if self.config.known_hosts_file:
            known_hosts = Path(self.config.known_hosts_file).expanduser().resolve()
            if not known_hosts.is_file():
                raise FileNotFoundError(f"known-hosts file not found: {known_hosts}")
            argv.extend(["-o", f"UserKnownHostsFile={known_hosts}"])
        argv.extend([
            f"{self.config.user}@{self.config.host}",
            self.config.remote_helper,
            "execute",
            "--envelope",
            token,
        ])
        return argv

    def run(self, command: RemoteCommand) -> TransportResult:
        completed = subprocess.run(
            self.command(command),
            text=True,
            capture_output=True,
            timeout=command.timeout_seconds,
            check=False,
        )
        return TransportResult(completed.returncode, completed.stdout, completed.stderr)
