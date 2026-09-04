from __future__ import annotations

import os
import unittest

from simdog.contracts import AgentRequest
from simdog.providers.http import NativeGatewayProvider


class FakeClient:
    def __init__(self) -> None:
        self.call = None

    def post(self, url, payload, headers, timeout):
        self.call = {"url": url, "payload": payload, "headers": headers, "timeout": timeout}
        return {
            "protocol_version": "simdog.agent.v1",
            "request_id": payload["request_id"],
            "status": "completed",
            "provider": {"id": "any-vendor", "model": "opaque", "session_id": "new"},
            "artifacts": [],
            "events": [],
            "usage": {},
            "error": None,
        }


class HttpProviderTests(unittest.TestCase):
    def test_secret_is_header_only_and_not_contract_payload(self) -> None:
        client = FakeClient()
        os.environ["SIMDOG_TEST_GATEWAY_TOKEN"] = "not-persisted-secret"
        try:
            provider = NativeGatewayProvider(
                endpoint="https://gateway.example/simdog",
                provider_id="any-vendor",
                secret_env="SIMDOG_TEST_GATEWAY_TOKEN",
                client=client,
            )
            response = provider.execute(AgentRequest(
                workflow_id="wf", role="theory", objective="freeze model",
            ))
        finally:
            os.environ.pop("SIMDOG_TEST_GATEWAY_TOKEN", None)
        self.assertEqual(response.status, "completed")
        self.assertEqual(client.call["headers"]["Authorization"], "Bearer not-persisted-secret")
        self.assertNotIn("not-persisted-secret", json_text(client.call["payload"]))

    def test_plain_http_remote_endpoint_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            NativeGatewayProvider(endpoint="http://gateway.example/run", provider_id="bad")


def json_text(value) -> str:
    import json
    return json.dumps(value)
