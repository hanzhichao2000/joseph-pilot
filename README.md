# joseph-pilot

Public, lightweight experiment layer built **only on open-source packages**: vectorbt on pinned
revisions, notebooks, and run manifests attached to GitHub Issues. Unrelated to the trading core by
design; results are hypotheses, not claims.

## What may live here

- **Example strategies** and **replications of textbook or published strategies** (a book, a paper,
  a public course), each with a `SOURCE.md` that cites the publication and states which parameters
  are the published ones.
- Tooling: the revision reader, the manifest schema, notebooks, CI.

## What may never live here

- **Our own money-making strategies**: any strategy whose edge depends on non-public rules,
  parameters, signals, features or models. Those live in the private sandbox
  (`joseph-sandbox-dx`), which may depend on this package; this package never depends on it.
- Research results, tuned parameter sweeps, manifests or data that are not public.

## Boundary rule, one line

Public = code that reproduces a published strategy with its published parameters. Private =
anything tuned, or evaluated as a candidate for capital.

Public contracts: https://github.com/hanzhichao2000/joseph-docs-public
