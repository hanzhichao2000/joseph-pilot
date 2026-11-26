# joseph-pilot

Lightweight experiment layer: vectorbt on pinned revisions, notebooks, and run manifests attached
to GitHub Issues. Unrelated to the trading core by design; results are hypotheses, not claims.

Routes (Project `joseph-build` #6):

- **C (IH daily research / GNN):** daily strategies on joseph-dal revisions; model research
  (torch) in notebooks; minimal Joseph infrastructure (no joseph_core testing, PM or OMS).
- **A (QT5m replica):** fast vectorized replication experiments. Production adoption of mature
  modules from the dismantle line happens in joseph-mini, not here.

Every experiment records a manifest: revision id, economic conventions, vectorbt version, seed,
window, experiment id. Promotion to the trading core is re-implementation through a migration
skill, never an equivalence claim.

Public contracts: https://github.com/hanzhichao2000/joseph-docs-public
