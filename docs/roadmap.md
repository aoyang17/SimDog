# Roadmap

## Completed foundation

- file-backed workflow controller and archive-first review rework;
- versioned agent requests, responses, stage tasks, run specs, and remote commands;
- controller-only promotion from agent staging;
- provider capability negotiation and reviewer-session independence;
- command adapter, local executor, acceptance engine, and DistributedECM probe;
- encoded SSH transport, server-side remote policy helper, and Slurm lifecycle;
- first COMSOL compile/batch adapter and DistributedECM execution plan;
- provider-neutral stdio and HTTPS gateway boundaries.
- role-provider routing and an end-to-end multi-agent orchestration loop.

## Completed real COMSOL qualification

The PaperEngine-compatible interactive gateway path was used for a real
DistributedECM 0.5C/10s COMSOL 6.4 qualification. Slurm job `44029` completed in
12:50, fail-closed validation passed, and downloaded results matched remote hashes.
See `simulations/distributed_ecm/qualification_runs/20260904_job44029.json`.

Remaining remote hardening work includes interrupted-transfer resume, a remote
helper deployment for non-interactive clusters, and explicit cancel, timeout,
missing-log, corrupt-artifact, and scheduler-failure integration exercises.

## Next: provider plugins

Implement separate installable bridges, each running the same conformance suite:

- Codex app-server or CLI bridge;
- OpenAI Responses bridge;
- Anthropic Messages bridge;
- local OpenAI-compatible server bridge;
- generic multi-agent orchestrator bridge.

The core package will not import their SDKs. A provider plugin must normalize
events and output artifacts into `simdog.agent.v1`, report truthful capabilities,
preserve request IDs, expose provider/session provenance, and pass recording-based
failure tests.

## Next: model and automation depth

- versioned `TaskSpec`, `ModelSpec`, and `ExperimentPlan` semantic validators;
- COMSOL model inspection and equation-to-feature mapping;
- safe model patch/diff artifacts;
- parameter sweeps, mesh/time-step convergence, controls, and resumable run DAGs;
- container executor and artifact-store abstraction;
- OpenFOAM or Abaqus adapter only after the COMSOL contract stabilizes.

## Later: workbench

Build the browser UI over controller/API operations. It should display workflow
state, agent provenance, model revisions, diagnostic hypotheses, job state,
convergence, acceptance, and review. It must not become another state backend.
