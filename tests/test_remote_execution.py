from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import unittest
import sys

from simdog.executors.slurm import SlurmExecutor
from simdog.executors.ssh import SSHConfig, SSHTransport
from simdog.executors.transport import RecordingTransport, RemoteCommand, TransportResult
from simdog.remote_helper import execute_envelope


class RemoteExecutionTests(unittest.TestCase):
    def test_ssh_uses_encoded_argv_envelope(self) -> None:
        transport = SSHTransport(SSHConfig(host="cluster.example", user="runner"))
        command = transport.command(RemoteCommand(
            argv=("sbatch", "--parsable", "job with spaces.slurm"),
            cwd="/srv/simdog-runs/case",
        ))
        self.assertNotIn("job with spaces.slurm", command)
        token = command[-1]
        payload = json.loads(base64.urlsafe_b64decode(token).decode("utf-8"))
        self.assertEqual(payload["argv"][2], "job with spaces.slurm")
        self.assertEqual(payload["protocol_version"], "simdog.remote-command.v1")

    def test_remote_helper_enforces_server_side_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            policy = root / "policy.yml"
            policy.write_text(
                "schema_version: simdog.remote-policy.v1\n"
                f"allowed_roots:\n  - {root}\n"
                f"allowed_executables:\n  - {Path(sys.executable).resolve()}\n"
                "allowed_environment: []\n"
                "max_timeout_seconds: 30\n",
                encoding="utf-8",
            )
            envelope = {
                "protocol_version": "simdog.remote-command.v1",
                "argv": [sys.executable, "--version"],
                "cwd": str(root),
                "timeout_seconds": 10,
                "environment": {},
            }
            token = base64.urlsafe_b64encode(json.dumps(envelope).encode()).decode()
            self.assertEqual(execute_envelope(token, policy), 0)

            envelope["cwd"] = "/"
            token = base64.urlsafe_b64encode(json.dumps(envelope).encode()).decode()
            with self.assertRaises(Exception):
                execute_envelope(token, policy)

    def test_slurm_submit_and_fail_closed_verification(self) -> None:
        transport = RecordingTransport([
            TransportResult(0, "42831\n"),
            TransportResult(0, "COMPLETED|0:0\n"),
            TransportResult(0, ""),
            TransportResult(0, ""),
            TransportResult(0, ""),
            TransportResult(1, ""),
            TransportResult(0, "abc  solved.mph\n"),
        ])
        slurm = SlurmExecutor(transport)
        job = slurm.submit(remote_workdir="/srv/simdog-runs/case", script="run.slurm")
        verdict = slurm.verify(
            job,
            required_artifacts=["solved.mph"],
            required_files=["slurm.42831.out"],
            clean_logs=["solver.log"],
        )
        self.assertTrue(verdict.ok)
        self.assertEqual(job.job_id, "42831")
        self.assertEqual(transport.commands[0].argv, ("sbatch", "--parsable", "run.slurm"))

    def test_slurm_completed_with_solver_error_is_rejected(self) -> None:
        transport = RecordingTransport([
            TransportResult(0, "COMPLETED|0:0\n"),
            TransportResult(0, ""),
            TransportResult(0, "matched"),
        ])
        slurm = SlurmExecutor(transport)
        from simdog.executors.slurm import SlurmJob
        verdict = slurm.verify(
            SlurmJob("99", "/srv/run", "run.slurm"),
            required_artifacts=[],
            clean_logs=["solver.log"],
        )
        self.assertFalse(verdict.ok)
        self.assertIn("forbidden solver error", verdict.errors[0])
