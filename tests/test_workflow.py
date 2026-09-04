from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from simdog.agents.broker import AgentBroker
from simdog.contracts import AgentRequest, AgentResponse, ArtifactContract, ArtifactProposal
from simdog.providers.recording import RecordingProvider
from simdog.workflow import Controller
from simdog.workspace import initialize_workspace


class WorkflowTests(unittest.TestCase):
    def _template(self, root: Path) -> Path:
        template = root / "template.yml"
        template.write_text(
            "schema_version: simdog.workflow.v1\n"
            "name: test\n"
            "stages:\n"
            "  - id: build\n"
            "    role: builder\n"
            "    objective: build\n"
            "    required_outputs: [model.json]\n"
            "  - id: review\n"
            "    role: reviewer\n"
            "    objective: review\n"
            "    required_outputs: [review.json]\n",
            encoding="utf-8",
        )
        return template

    def test_controller_owns_transition_and_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            workspace = parent / "case"
            initialize_workspace(workspace, self._template(parent), "case")
            controller = Controller(workspace)
            controller.prepare()
            (workspace / "stages/build/model.json").write_text("{}", encoding="utf-8")
            self.assertEqual(controller.submit()["next_stage"], "review")
            controller.prepare()
            (workspace / "stages/review/review.json").write_text(
                json.dumps({"decision": "accepted"}), encoding="utf-8"
            )
            self.assertEqual(controller.submit()["status"], "complete")
            self.assertTrue((workspace / "publication.json").is_file())

    def test_rejected_review_archives_and_returns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            workspace = parent / "case"
            initialize_workspace(workspace, self._template(parent), "case")
            controller = Controller(workspace)
            controller.prepare()
            (workspace / "stages/build/model.json").write_text("{}", encoding="utf-8")
            controller.submit()
            controller.prepare()
            (workspace / "stages/review/review.json").write_text(
                json.dumps({"decision": "rejected", "return_stage": "build", "findings": ["bad mapping"]}),
                encoding="utf-8",
            )
            result = controller.submit()
            self.assertEqual(result["status"], "rework")
            self.assertTrue((workspace / "archive/cycle-001/build/model.json").is_file())
            self.assertEqual(Controller(workspace).status()["active_stage"], "build")

    def test_only_controller_promotes_broker_staging_and_enforces_reviewer_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            workspace = parent / "case"
            initialize_workspace(workspace, self._template(parent), "case")
            controller = Controller(workspace)
            controller.prepare()

            def build_response(request):
                return AgentResponse(
                    request_id=request.request_id,
                    status="completed",
                    provider={"id": "recording", "session_id": "shared", "model": "deterministic"},
                    artifacts=(ArtifactProposal("model.json", "application/json", {"model": "ok"}),),
                )

            build_request = AgentRequest(
                workflow_id="case", role="builder", objective="build",
                outputs=(ArtifactContract("model.json"),),
            )
            staged = AgentBroker(workspace).execute(RecordingProvider(build_response), build_request)
            self.assertFalse((workspace / "stages/build/model.json").exists())
            promoted = controller.promote_agent_result(staged)
            self.assertTrue(promoted["ok"])
            self.assertTrue((workspace / "stages/build/model.json").exists())
            controller.submit()
            controller.prepare()

            def review_response(request):
                return AgentResponse(
                    request_id=request.request_id,
                    status="completed",
                    provider={"id": "recording", "session_id": "shared", "model": "deterministic"},
                    artifacts=(ArtifactProposal("review.json", "application/json", {"decision": "accepted"}),),
                )

            review_request = AgentRequest(
                workflow_id="case", role="reviewer", objective="review",
                outputs=(ArtifactContract("review.json"),),
            )
            review_staged = AgentBroker(workspace).execute(RecordingProvider(review_response), review_request)
            with self.assertRaises(Exception):
                controller.promote_agent_result(review_staged)
