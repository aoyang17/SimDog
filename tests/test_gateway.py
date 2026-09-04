from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from simdog.executors.gateway import GatewayError, GatewaySSHConfig, InteractiveGatewayTransport
from simdog.executors.transport import RemoteCommand


class GatewayTests(unittest.TestCase):
    def test_config_contains_only_password_file_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            password = root / "password"
            password.write_text("unused", encoding="utf-8")
            password.chmod(0o600)
            config_path = root / "gateway.yml"
            config_path.write_text(
                "schema_version: simdog.gateway-ssh.v1\n"
                "connection_id: test\n"
                "ssh:\n  host: gateway.example\n  port: 2222\n  user: user\n"
                "gateway:\n  instance_selection: '1'\n  instance_id: '123'\n"
                f"authentication:\n  kind: password_file\n  password_file: {password}\n"
                "remote:\n  environment_script: ~/env/comsol.sh\n  work_root: ~/simdog-runs\n",
                encoding="utf-8",
            )
            config = GatewaySSHConfig.load(config_path)
            self.assertEqual(config.password_file, password)
            self.assertFalse(hasattr(config, "password"))

    def test_argv_is_quoted_at_interactive_gateway_boundary(self) -> None:
        config = GatewaySSHConfig(
            connection_id="test", host="gateway.example", port=22, user="user",
            instance_selection="1", instance_id="123", password_file=Path("/secret/ref"),
            environment_script="~/env/comsol.sh", work_root="~/simdog-runs",
        )
        transport = InteractiveGatewayTransport(config)
        script = transport.render_remote_script(RemoteCommand(
            argv=("sbatch", "--parsable", "job name.slurm"),
            cwd="~/simdog-runs/case",
        ))
        self.assertIn("'job name.slurm'", script)
        self.assertIn('cd "$HOME"/simdog-runs/case', script)

    def test_remote_path_escape_is_rejected(self) -> None:
        config = GatewaySSHConfig(
            connection_id="test", host="gateway.example", port=22, user="user",
            instance_selection="1", instance_id="123", password_file=Path("/secret/ref"),
            environment_script="~/env/comsol.sh", work_root="~/simdog-runs",
        )
        with self.assertRaises(GatewayError):
            InteractiveGatewayTransport(config).render_remote_script(RemoteCommand(
                argv=("test", "-s", "x"), cwd="~/other/case",
            ))

    def test_terminal_control_sequences_are_not_persisted(self) -> None:
        self.assertEqual(
            InteractiveGatewayTransport._clean_output("\x1b[?2004l\r\nCOMPLETED|0:0\r\n"),
            "COMPLETED|0:0",
        )
