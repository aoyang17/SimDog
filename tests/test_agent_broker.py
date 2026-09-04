from __future__ import annotations

import tempfile
import unittest

from simdog.agents.broker import AgentBroker
from simdog.contracts import AgentRequest, AgentResponse, ArtifactContract, ArtifactProposal
from simdog.providers.recording import RecordingProvider


class AgentBrokerTests(unittest.TestCase):
    def test_validated_proposal_is_staged_not_published(self) -> None:
        def respond(request: AgentRequest) -> AgentResponse:
            return AgentResponse(
                request_id=request.request_id,
                status="completed",
                provider={"id": "recording", "model": "model-x", "session_id": "session-1"},
                artifacts=(ArtifactProposal("model.json", "application/json", {"ok": True}),),
            )

        with tempfile.TemporaryDirectory() as temporary:
            request = AgentRequest(
                workflow_id="wf", role="builder", objective="build",
                outputs=(ArtifactContract("model.json"),),
            )
            result = AgentBroker(temporary).execute(RecordingProvider(respond), request)
            self.assertTrue(result.ok)
            self.assertIn("/.simdog/staging/", result.artifacts[0]["path"])

    def test_missing_required_artifact_fails_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            request = AgentRequest(
                workflow_id="wf", role="theory", objective="freeze",
                outputs=(ArtifactContract("model.json"),),
            )
            result = AgentBroker(temporary).execute(RecordingProvider(), request)
            self.assertFalse(result.ok)
            self.assertEqual(result.error["kind"], "contract_error")

    def test_independent_reviewer_session_is_enforced(self) -> None:
        def respond(request: AgentRequest) -> AgentResponse:
            return AgentResponse(
                request_id=request.request_id, status="completed",
                provider={"id": "recording", "session_id": "producer"},
            )

        with tempfile.TemporaryDirectory() as temporary:
            request = AgentRequest(workflow_id="wf", role="reviewer", objective="review")
            with self.assertRaises(ValueError):
                AgentBroker(temporary).execute(
                    RecordingProvider(respond), request,
                    forbidden_identities={"recording:producer"},
                )
