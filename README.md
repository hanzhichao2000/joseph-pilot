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

Public = code that reproduces a published strategy with its published parameters, and its
replication results on public data labeled as replication diagnostics. Private = anything tuned,
or evaluated as a candidate for capital.

## Notebooks

Book examples belong under `notebooks/book-examples/<author-book>/chapter-<number>-<topic>/`.
Each notebook must have a `SOURCE.md` in its chapter directory identifying publication, edition,
chapter, and published parameters, with any example assumptions distinguished from the source.
Label results as replication diagnostics, not evidence of strategy validity. Runtime rules live in
[the public runtime conventions](https://github.com/hanzhichao2000/joseph-docs-public/blob/main/contracts/runtime-conventions.md).

## Contract expiry

`attach_contracts` takes contract attributes from `option_contracts` and rejects missing or
repeated symbols. `resolve_expiry` uses the source expiry date when present; otherwise it starts
at the third Friday of `expiry_month` and advances to the first trading day. Supply an authoritative
exchange calendar mapping every calendar date from that Friday through the resulting trading day
to its trading status; missing dates fail closed. The helper does not fetch a calendar.

The source or calendar-derived expiry is authoritative, not the last bar in a potentially truncated
revision window. The helper compares the expiry to the symbol's last bar date and raises with both
dates if they differ. To validate the cross-check, provide a revision whose window covers the full
contract lifetime through expiry and whose calendar covers the holiday adjustment; an earlier last
bar may indicate truncation or missing data, not an earlier expiry.

Public contracts: https://github.com/hanzhichao2000/joseph-docs-public
