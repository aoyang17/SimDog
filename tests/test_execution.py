from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

from simdog.executors.local import ExecutionPolicy, ExecutionRequest, LocalExecutor


class ExecutionTests(unittest.TestCase):
    def test_executable_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executor = LocalExecutor(temporary, ExecutionPolicy(allowed_executables=("false-name",)))
            with self.assertRaises(PermissionError):
                executor.execute(ExecutionRequest(argv=(sys.executable, "--version")))

    def test_cwd_cannot_escape_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executor = LocalExecutor(
                temporary, ExecutionPolicy(allowed_executables=(str(Path(sys.executable).resolve()),))
            )
            with self.assertRaises(ValueError):
                executor.execute(ExecutionRequest(argv=(sys.executable, "--version"), cwd=".."))

    def test_return_code_is_not_silently_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executor = LocalExecutor(
                temporary, ExecutionPolicy(allowed_executables=(str(Path(sys.executable).resolve()),))
            )
            result = executor.execute(ExecutionRequest(argv=(sys.executable, "-c", "raise SystemExit(3)")))
            self.assertFalse(result.execution_ok)
            self.assertEqual(result.returncode, 3)

    def test_absolute_executable_cannot_spoof_allowed_basename(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            executor = LocalExecutor(temporary, ExecutionPolicy(allowed_executables=("python3",)))
            with self.assertRaises(PermissionError):
                executor.execute(ExecutionRequest(argv=(str(Path(sys.executable).resolve()), "--version")))
