from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from .transport import RemoteCommand, RemoteTransport, TransportResult


_JOB_ID = re.compile(r"^[0-9]+(?:[_.][A-Za-z0-9]+)?$")


@dataclass(frozen=True)
class SlurmJob:
    job_id: str
    remote_workdir: str
    script: str


@dataclass(frozen=True)
class SlurmVerification:
    ok: bool
    job_state: str
    checks: tuple[dict[str, Any], ...]
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class SlurmExecutor:
    def __init__(self, transport: RemoteTransport) -> None:
        self.transport = transport

    def submit(self, *, remote_workdir: str, script: str) -> SlurmJob:
        result = self.transport.run(RemoteCommand(
            argv=("sbatch", "--parsable", script), cwd=remote_workdir,
        ))
        if not result.ok:
            raise RuntimeError(f"sbatch failed: {result.stderr or result.stdout}")
        matches = re.findall(r"(?m)^([0-9]+(?:[_.][A-Za-z0-9]+)?)(?:;[^\r\n]+)?\r?$", result.stdout)
        job_id = matches[-1] if matches else ""
        if not _JOB_ID.fullmatch(job_id):
            raise ValueError(f"invalid Slurm job id returned by sbatch: {job_id!r}")
        return SlurmJob(job_id=job_id, remote_workdir=remote_workdir, script=script)

    def status(self, job: SlurmJob) -> TransportResult:
        self._validate_job(job)
        return self.transport.run(RemoteCommand(
            argv=("sacct", "-j", job.job_id, "--format=State,ExitCode,Elapsed", "-n", "-P"),
            cwd=job.remote_workdir,
        ))

    def cancel(self, job: SlurmJob) -> TransportResult:
        self._validate_job(job)
        return self.transport.run(RemoteCommand(
            argv=("scancel", job.job_id), cwd=job.remote_workdir,
        ))

    def verify(
        self,
        job: SlurmJob,
        *,
        required_artifacts: list[str],
        required_files: list[str] | None = None,
        clean_logs: list[str],
        forbidden_log_pattern: str = "Error|Exception|Singular matrix|Repeated error test",
    ) -> SlurmVerification:
        self._validate_job(job)
        checks: list[dict[str, Any]] = []
        errors: list[str] = []
        state_result = self.status(job)
        checks.append({"name": "scheduler", **state_result.as_dict()})
        state_line = next((line.strip() for line in state_result.stdout.splitlines() if line.strip()), "")
        if not state_result.ok or not state_line.startswith("COMPLETED|0:0"):
            errors.append(f"Slurm job is not COMPLETED|0:0: {state_line or 'missing state'}")
        for required_file in required_files or []:
            result = self.transport.run(RemoteCommand(
                argv=("test", "-f", required_file), cwd=job.remote_workdir,
            ))
            checks.append({"name": "file_exists", "path": required_file, **result.as_dict()})
            if not result.ok:
                errors.append(f"required file missing: {required_file}")
        for artifact in required_artifacts:
            result = self.transport.run(RemoteCommand(
                argv=("test", "-s", artifact), cwd=job.remote_workdir,
            ))
            checks.append({"name": "artifact_nonempty", "path": artifact, **result.as_dict()})
            if not result.ok:
                errors.append(f"required artifact missing or empty: {artifact}")
        for log in clean_logs:
            exists = self.transport.run(RemoteCommand(
                argv=("test", "-s", log), cwd=job.remote_workdir,
            ))
            checks.append({"name": "log_nonempty", "path": log, **exists.as_dict()})
            if not exists.ok:
                errors.append(f"required log missing or empty: {log}")
                continue
            scan = self.transport.run(RemoteCommand(
                argv=("grep", "-Eiq", forbidden_log_pattern, log), cwd=job.remote_workdir,
            ))
            checks.append({
                "name": "log_scan",
                "path": log,
                "returncode": scan.returncode,
                "stdout": scan.stdout,
                "stderr": scan.stderr,
                "matched_forbidden": scan.returncode == 0,
                "clean": scan.returncode == 1,
            })
            if scan.returncode == 0:
                errors.append(f"forbidden solver error found in log: {log}")
            elif scan.returncode != 1:
                errors.append(f"could not scan solver log: {log}")
        if not errors and required_artifacts:
            digest = self.transport.run(RemoteCommand(
                argv=("sha256sum", *required_artifacts), cwd=job.remote_workdir,
            ))
            checks.append({"name": "sha256", **digest.as_dict()})
            if not digest.ok:
                errors.append("failed to hash remote artifacts")
        return SlurmVerification(
            ok=not errors,
            job_state=state_line,
            checks=tuple(checks),
            errors=tuple(errors),
        )

    @staticmethod
    def _validate_job(job: SlurmJob) -> None:
        if not _JOB_ID.fullmatch(job.job_id):
            raise ValueError("invalid Slurm job id")
