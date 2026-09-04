# Simulation profiles

Each directory is a reusable, user-independent simulation definition. It records
source snapshots, solver plans, acceptance gates, and the logical connection name.
It must not contain passwords, private keys, access tokens, or user-specific login
details.

Runtime snapshots and results are written below ignored `workspaces/`. Connection
details are resolved separately from ignored `config/local/connections/`.
