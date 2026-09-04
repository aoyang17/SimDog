# DistributedECM compatibility probe

This is an offline, non-mutating integration probe against the real validator in
PaperEngine's `Needs/distributed_ecm_debug` case. It demonstrates that SimDog can:

1. inventory and hash an external legacy model package;
2. invoke an existing validator through the black-box command adapter;
3. preserve stdout, stderr, return code, duration, and verdict;
4. distinguish solver completion from scientific/numerical acceptance;
5. integrate the case without importing PaperEngine Python modules.

`pass_0p5c.csv` represents the reported strict-pass 0.5C metrics. `reject_1c.csv`
represents the reported coarse 1C run, which completed but exceeds the 1 mV
algebraic residual gates.

The probe never invokes COMSOL and never modifies the source project.

`task_spec.yml` records the debug objectives, known physics blockers, and strict
acceptance gates. `comsol_plan.yml` demonstrates how the existing Java wrapper is
translated into separate compile and batch argv requests. Render it with:

```bash
bin/simdog plan-adapter --adapter comsol \
  --spec examples/distributed_ecm/comsol_plan.yml
```

Rendering the plan is offline. Running it requires a workspace snapshot containing
the declared Java sources, a policy allowing the exact COMSOL executable, a valid
license, and either a local or explicitly configured remote executor.
