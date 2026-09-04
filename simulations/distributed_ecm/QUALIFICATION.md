# DistributedECM real COMSOL qualification

## Separation of concerns

- `profile.yml` is reusable and contains no credentials.
- `config/local/connections/yeesuan-comsol.yml` is user-local and ignored.
- The connection references an external mode-0600 password file; it does not
  contain the password.
- `workspaces/distributed_ecm/<run-id>/input` is an immutable-by-convention source
  snapshot with SHA-256 values in `run.json`.
- Remote runs stay below the connection's declared `work_root`.

## Controlled flow

```bash
bin/simdog gateway probe --config <connection.yml>

bin/simdog simulation prepare \
  --profile simulations/distributed_ecm/profile.yml \
  --run-id <run-id>

bin/simdog gateway ensure-workdir \
  --config <connection.yml> \
  --remote-workdir '~/simdog-runs/distributed_ecm/<run-id>'

bin/simdog gateway upload \
  --config <connection.yml> \
  --local workspaces/distributed_ecm/<run-id>/input \
  --remote '~/simdog-runs/distributed_ecm/<run-id>'

bin/simdog gateway submit \
  --config <connection.yml> \
  --remote-workdir '~/simdog-runs/distributed_ecm/<run-id>/input' \
  --script qualification_0p5c.slurm
```

After Slurm completes, verification must include scheduler exit state, Slurm files,
the COMSOL batch log, nonempty model/data/validation artifacts, and remote hashes:

```bash
bin/simdog gateway verify \
  --config <connection.yml> \
  --remote-workdir '~/simdog-runs/distributed_ecm/<run-id>/input' \
  --job-id <job-id> \
  --file slurm.<job-id>.out \
  --file slurm.<job-id>.err \
  --log fixed_0p5c_10s_comsol.log \
  --artifact fixed_0p5c_10s_built.mph \
  --artifact fixed_0p5c_10s_solved.mph \
  --artifact fixed_0p5c_10s_global.csv \
  --artifact fixed_0p5c_10s_validation.txt \
  --artifact fixed_0p5c_10s_manifest.sha256 \
  --record-workspace workspaces/distributed_ecm/<run-id>
```

An accepted infrastructure verification is still followed by download, local
SHA-256 recording, and inspection of `validation_status=PASS`. Long-duration runs
remain blocked by the known spherical-inventory inconsistency until the model
owner chooses the intended physics.

## Completed qualification

The first real SimDog-controlled qualification completed on 2026-09-04 as Slurm
job `44029`. COMSOL 6.4.0.293 reached 10 s at 0.5C, the deterministic validator
passed every short-run gate, remote verification passed, and six downloaded
artifacts matched their recorded hashes. The publication-safe result is
`qualification_runs/20260904_job44029.json`.
