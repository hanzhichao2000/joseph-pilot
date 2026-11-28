# joseph-pilot agent instructions

Use public packages and data for examples and published-strategy replications. Include a
`SOURCE.md` with the publication, edition, chapter, and published parameters for each example
notebook or strategy module.

## Local checks

Use Python 3.11 or newer. From the repository root, create a temporary virtual environment
for development. CI uses `python -m pip install '.[dev,ux]'` for a non-editable install.

```sh
dev_env="$(mktemp -d)"
python3 -m venv "$dev_env"
. "$dev_env/bin/activate"
python -m pip install -e '.[dev,ux]'
ruff check src tests tools
ruff format --check src tests tools
mypy
pytest
python tools/check_sources.py
```

Run `python3 tools/check_keywords.py keywords/public-boundary.txt .` to reproduce the CI check
for publishable boundary rules. The repository-local checker and list mirror the public docs
checker and run without a separate documentation checkout. CI reports counts for findings.
Keep internal roadmap and tracker details out of public documentation and examples.

For packaging verification, build the repository wheel and install it with its dependencies
into a separate, clean venv. Run the installed CLI from outside the checkout.

```sh
wheel_dir="$(mktemp -d)"
python -m pip wheel --no-deps --wheel-dir "$wheel_dir" .
python3 -m venv "$wheel_dir/venv"
(
    cd "$wheel_dir" || exit 1
    venv/bin/python -m pip install joseph_pilot-*.whl &&
    env -u PYTHONPATH venv/bin/joseph-pilot runtime-check --help
)
```

Keep the `joseph-api` dependency pinned to an immutable full commit SHA in `pyproject.toml`.
The current pin is `bce432db6836bed3ff2834946541617de285fa11`.
When this repository needs new API behavior, such as the option-row DTOs from
[joseph-api PR #10](https://github.com/hanzhichao2000/joseph-api/pull/10),
update the pin after the API PR merges, using the full SHA of the merged commit.

## Public changes and evidence

- Use `codex/<topic>-<issue number>` for work branches.
- Keep planning issues in the internal tracker. Public PRs require approval from the private
  project lead.
- In `joseph-docs-public` only, add new public-layer Markdown files to `public-layer.allow`
  in the same PR and keep each file at or below 200 lines.
- Check all public changes for vendor names, private paths and URLs, credentials, and
  proprietary strategy identifiers.
- Attach the tested commit SHA and CI run to the governing internal GitHub issue. Follow
  [Evidence and claims](https://github.com/hanzhichao2000/joseph-docs-public/blob/main/contracts/evidence-and-claims.md).
  Keep raw logs and evidence bundles out of this repository.
