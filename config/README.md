# SimDog configuration layout

Configuration is separated from reusable simulation definitions.

```text
config/
├── templates/                 tracked examples without real credentials
└── local/                     ignored, user- and machine-specific
    ├── connections/           SSH/gateway endpoints and secret-file references
    ├── executors/             scheduler and resource defaults
    └── users/                 optional per-user selections

simulations/                   tracked reusable simulation profiles
└── <simulation-id>/
    ├── profile.yml            source inventory and workflow
    ├── run_specs/             solver and qualification plans
    └── acceptance/            deterministic gates

workspaces/                    ignored runtime snapshots and outputs
└── <simulation-id>/<run-id>/
```

Files below `config/local/` may contain hostnames and user names, but must contain
only references to secret files. Passwords, private keys, tokens, and license
secrets must remain outside this repository. Secret files must not be accessible
by group or other users.

Simulation profiles refer to a connection by logical name. Different users can
replace `config/local/connections/<name>.yml` without changing the simulation
definition or workflow history.
