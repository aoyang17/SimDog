# Trust and safety boundaries

## Untrusted inputs

Treat model files, agent output, solver logs, downloaded scripts, and provider
events as untrusted. Parsing an artifact does not authorize its execution.

## Agent boundary

An agent provider can return artifact proposals only. The broker validates request
correlation, protocol version, declared artifact names, media types, and required
outputs, then writes proposals to `.simdog/staging/<request-id>/`. Only the
controller may promote validated artifacts into canonical stage directories.

Reviewer independence is expressed as a forbidden provider-session identity set.
Production orchestration must populate it from all producer receipts.

## Execution boundary

Local commands are argument arrays and never pass through a shell. Policy limits:

- exact bare executable names or normalized absolute executable paths;
- working directories beneath the active workspace;
- environment keys;
- maximum timeout;
- required outputs;
- forbidden log patterns;
- acceptable return codes.

Executable matching is exact: a bare command must match a bare allowlist entry,
while an absolute executable must match the same normalized absolute path. A file
cannot gain authority merely by using an allowed basename.

Container, SSH, scheduler, and cloud executors must implement the same request and
result contract. Remote completion must be verified by scheduler state, logs,
declared artifacts, and hashes.

Some institutional gateways expose only an interactive shell after password and
instance selection. `InteractiveGatewayTransport` keeps commands as argv until
that final boundary, quotes every argument, requires strict host-key checking,
restricts all remote paths to the configured work root, and reads the password
only from an external mode-0600 file. The local connection file is ignored and
contains only the password-file reference.

## Secrets

Specs contain secret references, not secret values. Providers do not receive a
secret unless a policy explicitly grants it for one operation. Secrets must not
enter prompts, workflow state, command arguments, logs, or manifests.

## Scientific safety

Agents cannot change declared acceptance criteria during a run. A proposed change
creates a new task-spec revision and invalidates downstream artifacts. Numerical
completion, deterministic acceptance, independent review, and publication remain
separate controller states.
