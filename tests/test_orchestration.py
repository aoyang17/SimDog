from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from simdog.contracts import AgentRequest, AgentResponse, ArtifactProposal
from simdog.orchestration import AgentOrchestrator, RoleProviderRouter
from simdog.providers.recording import RecordingProvider
from simdog.workspace import initialize_workspace


class OrchestrationTests(unittest.TestCase):
    def test_roles_can_use_different_providers_without_state_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "template.yml"
            template.write_text(
                "schema_version: simdog.workflow.v1\n"
                "name: orchestration-test\n"
                "stages:\n"
                "  - id: theory\n"
                "    role: theory\n"
                "    objective: freeze\n"
                "    required_outputs: [model.json]\n"
                "  - id: review\n"
                "    role: reviewer\n"
                "    objective: review\n"
                "    required_outputs: [review.json]\n",
                encoding="utf-8",
            )
            workspace = root / "case"
            initialize_workspace(workspace, template, "case")

            def theory(request: AgentRequest) -> AgentResponse:
                return AgentResponse(
                    request_id=request.request_id,
                    status="completed",
                    provider={"id": "recording", "session_id": "theory-session", "model": "model-a"},
                    artifacts=(ArtifactProposal("model.json", "application/json", {"equation": "x=1"}),),
                )

            def review(request: AgentRequest) -> AgentResponse:
                self.assertEqual(request.inputs[0].name, "theory:model.json")
                return AgentResponse(
                    request_id=request.request_id,
                    status="completed",
                    provider={"id": "recording", "session_id": "review-session", "model": "model-b"},
                    artifacts=(ArtifactProposal("review.json", "application/json", {"decision": "accepted"}),),
                )

            orchestrator = AgentOrchestrator(
                workspace,
                RoleProviderRouter({
                    "theory": RecordingProvider(theory),
                    "reviewer": RecordingProvider(review),
                }),
            )
            result = orchestrator.run_until_terminal()
            self.assertTrue(result["ok"])
            publication = json.loads((workspace / "publication.json").read_text())
            self.assertEqual(publication["workflow_id"], "case")

    def test_provider_block_does_not_advance_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "template.yml"
            template.write_text(
                "schema_version: simdog.workflow.v1\nname: blocked\nstages:\n"
                "  - id: build\n    role: builder\n    objective: build\n    required_outputs: [model.json]\n",
                encoding="utf-8",
            )
            workspace = root / "case"
            initialize_workspace(workspace, template, "case")

            def blocked(request: AgentRequest) -> AgentResponse:
                return AgentResponse(
                    request_id=request.request_id,
                    status="blocked",
                    provider={"id": "recording", "session_id": "blocked", "model": "none"},
                    error={"kind": "missing_input"},
                )

            orchestrator = AgentOrchestrator(
                workspace, RoleProviderRouter({"builder": RecordingProvider(blocked)})
            )
            result = orchestrator.run_stage()
            self.assertFalse(result["ok"])
            self.assertEqual(orchestrator.controller.state["active_stage"], "build")
            self.assertEqual(orchestrator.controller.state["stages"]["build"]["status"], "in_progress")
