# Agent provider contract

SimDog's core contract is independent of LLM vendors and agent frameworks.

## Request

Every provider receives one JSON-compatible `AgentRequest` with:

- `protocol_version`;
- unique request and workflow identifiers;
- logical role and objective;
- typed, hashable input references;
- explicit output artifact contracts;
- constraints and permissions;
- optional time/token budgets;
- correlation metadata.

## Response

Every provider returns one `AgentResponse` with:

- the same protocol and request identifiers;
- `completed`, `blocked`, or `failed` status;
- artifact proposals or staging paths;
- normalized events and usage;
- structured blocker/error information;
- provider and model provenance.

Provider-specific tool calls, token accounting, reasoning traces, stream events,
and session identifiers stay inside the provider implementation. Core code must
not branch on model names.

SimDog currently provides three integration shapes:

- `RecordingProvider` for deterministic offline orchestration tests;
- `ProcessProvider` for any local agent bridge that speaks one JSON request and
  one JSON response over standard I/O;
- `NativeGatewayProvider` for an HTTPS service that speaks the SimDog contract.

Codex, OpenAI, Anthropic, local-model, or multi-agent-framework integrations should
translate their native APIs behind one of these boundaries or a separately
installed provider plugin. Example gateway configurations live in
`templates/providers/`. Vendor SDKs are deliberately absent from the core package.

## Capability negotiation

Before assignment, the broker checks a provider manifest for required features:
structured output, tool use, image input, persistent sessions, workspace access,
and maximum context. Unsupported requests fail before work begins.

## Migration guarantees

- Protocol versions are explicit and validated.
- Artifact schemas, not prose responses, are the interoperability boundary.
- Providers cannot mutate canonical workflow state.
- Retries are idempotent by request ID.
- Provider/model/version/parameters are recorded in provenance.
- A deterministic recording provider runs all core tests offline.
- Provider conformance tests are mandatory for plugin registration.
- The response provider ID must match the negotiated manifest provider ID.
- Canonical promotion requires both provider ID and session ID.
- Reviewer promotion rejects identities used by producing stages.
