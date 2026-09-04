from __future__ import annotations

from pathlib import Path
import sys
import unittest

from simdog.contracts import AgentRequest, ArtifactContract
from simdog.providers.base import require_capabilities
from simdog.providers.process import ProcessProvider
from simdog.providers.recording import RecordingProvider


class ProviderContractTests(unittest.TestCase):
    def test_recording_provider_is_vendor_neutral(self) -> None:
        request = AgentRequest(
            workflow_id="wf-1", role="reviewer", objective="Review metrics",
            outputs=(ArtifactContract("review.json"),),
        )
        provider = RecordingProvider()
        response = provider.execute(request)
        self.assertEqual(response.request_id, request.request_id)
        self.assertEqual(response.status, "completed")
        require_capabilities(provider.manifest(), {"structured_output"})

    def test_json_stdio_provider_conformance(self) -> None:
        script = Path(__file__).parent / "fixtures" / "stdio_provider.py"
        request = AgentRequest(workflow_id="wf-2", role="debug", objective="Find root cause")
        response = ProcessProvider([sys.executable, str(script)], provider_id="fixture").execute(request)
        self.assertEqual(response.status, "completed")
        self.assertEqual(response.artifacts[0].content["role"], "debug")

    def test_request_id_mismatch_is_rejected(self) -> None:
        request = AgentRequest(workflow_id="wf-3", role="builder", objective="Build")
        script = Path(__file__).parent / "fixtures" / "stdio_provider.py"
        response = ProcessProvider([sys.executable, str(script)]).execute(request)
        self.assertEqual(response.request_id, request.request_id)
