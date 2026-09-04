# SimDog Agent Guide

SimDog is provider-neutral. Never make workflow correctness depend on a model
vendor, prompt format, model name, or provider-specific event stream.

## Authority boundaries

- `simdog.workflow.Controller` exclusively owns workflow state transitions.
- Agents may propose artifacts. They may not mark stages complete, publish runs,
  weaken acceptance criteria, or overwrite canonical state.
- Solver adapters produce execution requests; executors alone launch processes.
- The controller validates and promotes staged artifacts.
- Review must use a session/provider identity distinct from the producing agent.

## Safety

- Do not use shell execution. Commands are argument arrays.
- Resolve every working directory and expected artifact beneath its workspace.
- Credentials must be external secret references, never fields in task specs,
  prompts, logs, manifests, or provider responses.
- Destructive actions require an explicit controller operation and archive-first
  behavior.

## Compatibility

- Public contracts are versioned JSON-compatible objects.
- New providers and adapters should be registered through Python entry points.
- Provider-native messages must be normalized into SimDog events.
- Core workflow tests must pass with the deterministic recording provider and
  without network access or an installed commercial solver.
