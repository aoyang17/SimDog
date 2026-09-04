from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from simdog.simulation import SimulationRunController, prepare_simulation


class SimulationProfileTests(unittest.TestCase):
    def test_sources_are_snapshotted_with_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            source = project / "source.java"
            source.write_text("class Source {}", encoding="utf-8")
            profile = project / "profile.yml"
            profile.write_text(
                "schema_version: simdog.simulation-profile.v1\n"
                "simulation_id: sample\n"
                "connection: local\n"
                "workspace_root: workspaces/sample\n"
                "remote_workdir: ~/simdog-runs/sample\n"
                f"source_files:\n  - name: Source.java\n    source: {source}\n",
                encoding="utf-8",
            )
            result = prepare_simulation(project, profile, "run1")
            self.assertTrue(result["ok"])
            self.assertEqual(
                result["source_files"][0]["source_sha256"],
                result["source_files"][0]["snapshot_sha256"],
            )
            self.assertTrue((project / "workspaces/sample/run1/input/Source.java").is_file())
            recorded = SimulationRunController(result["workspace"]).record_submission(
                "123", "~/simdog-runs/sample/run1", "run.slurm"
            )
            self.assertEqual(recorded["status"], "submitted")
            self.assertEqual(recorded["scheduler"]["job_id"], "123")

    def test_project_source_reference_is_portable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            source = project / "simulations/sample/run.slurm"
            source.parent.mkdir(parents=True)
            source.write_text("#!/bin/sh", encoding="utf-8")
            profile = project / "profile.yml"
            profile.write_text(
                "schema_version: simdog.simulation-profile.v1\n"
                "simulation_id: sample\n"
                "source_files:\n"
                "  - name: run.slurm\n"
                "    source: project://simulations/sample/run.slurm\n",
                encoding="utf-8",
            )
            result = prepare_simulation(project, profile, "run1")
            self.assertTrue(Path(result["workspace"], "input/run.slurm").is_file())

    def test_workspace_cannot_escape_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            source = project / "source.java"
            source.write_text("x", encoding="utf-8")
            profile = project / "profile.yml"
            profile.write_text(
                "schema_version: simdog.simulation-profile.v1\n"
                "simulation_id: sample\nworkspace_root: ../outside\n"
                f"source_files:\n  - source: {source}\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                prepare_simulation(project, profile, "run1")
