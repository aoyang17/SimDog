# Architecture

```text
CLI / API / Web
       |
       v
Workflow Controller ---- Policy ---- Provenance
       |                     |
       +---- Agent Broker    +---- Acceptance Engine
       |          |
       |          +---- provider plugins (Codex, OpenAI, local, other)
       |
       +---- Solver Adapter Registry
                    |
                    +---- Execution Request
                               |
                       Local / container / SSH / scheduler
```

## Control plane

The controller is a deterministic state machine. A workflow template defines
stages, owners, required outputs, and review behavior. `workflow.json` is canonical
state. Stage outputs are written to stage-local directories and promoted only
after contract checks.

## Agent plane

Agents receive `AgentRequest` and return `AgentResponse`. The request contains a
role, objective, typed input references, output contracts, constraints, and a
budget. It does not contain provider-native chat messages. Providers translate
the request into their own API and normalize the result back into the contract.

Provider output is a proposal, never an authoritative state transition. SimDog
supports mediated providers that return artifact content and workspace providers
that can write only to a controller-created staging directory.

`AgentOrchestrator` connects the layers in one bounded sequence:

```text
Controller.prepare
  -> build provider-neutral AgentRequest from the active stage
  -> RoleProviderRouter.provider_for(role)
  -> AgentBroker.execute and validate proposal
  -> Controller.promote_agent_result
  -> Controller.submit
```

Inputs from completed stages are passed as relative URIs with SHA-256 hashes. A
blocked or failed provider leaves the stage in progress and cannot advance it.
Different roles may use different providers or models; the workflow observes only
their normalized contracts and provenance.

## Solver plane

Adapters describe capabilities and turn solver-neutral task/run specifications
into execution requests. Executors enforce policy and perform process, container,
remote, or scheduler operations. This prevents solver-specific command construction
from leaking into the workflow controller.

Remote execution uses two boundaries:

```text
SlurmExecutor -> RemoteCommand(argv, cwd, env, timeout)
              -> SSHTransport
              -> base64 JSON envelope
              -> simdog-remote
              -> server-side policy
              -> subprocess argv (never shell=True)
```

The remote helper must be installed by the cluster operator. Its policy fixes
allowed roots, exact executable names or absolute paths, environment keys, and
maximum runtime. SSH uses key authentication and strict host-key checking.

## Verification plane

Execution health, numerical acceptance, scientific review, and publication are
separate decisions:

1. execution completed;
2. required artifacts exist and logs are clean;
3. deterministic metrics satisfy declared gates;
4. an independent reviewer accepts fidelity and interpretation;
5. the controller emits a publication manifest.

## Initial workflow roles

- specification: turn intent into explicit requirements and acceptance criteria;
- theory: freeze equations, units, assumptions, initial/boundary conditions;
- builder: map the frozen model to a solver adapter;
- automation: define sweeps, controls, convergence and resources;
- debug: propose falsifiable hypotheses and minimal diagnostic experiments;
- experiment: interpret execution records and extract metrics;
- reviewer: independently decide acceptance or the earliest return stage.

The roles are logical contracts, not permanent processes. A workflow starts only
the roles it needs.

## Canonical artifact promotion

Agent responses are materialized below `.simdog/staging/<request-id>/`. The broker
writes a receipt containing the request, normalized response, provider manifest,
and artifact hashes. `Controller.promote_agent_result` verifies the receipt,
workspace containment, exact stage output set, hashes, and reviewer independence
before atomically promoting files. Promotion does not complete a stage; normal
stage validation and submission are still required.
