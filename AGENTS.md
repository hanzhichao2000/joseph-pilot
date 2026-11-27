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

Use the public boundary keyword lists with the existing scanner. CI checks out the lists
under `.boundary-docs` and runs `python tools/check_keywords.py .boundary-docs/keywords .`.

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

## Public changes and evidence

- Use `codex/<topic>-<issue number>` for work branches.
- Keep planning issues in the internal tracker. Public PRs require approval from the private
  project lead.
- Check all public changes for vendor names, private paths and URLs, credentials, and
  proprietary strategy identifiers.
- Attach the tested commit SHA and CI run to the governing internal GitHub issue. Follow
  [Evidence and claims](https://github.com/hanzhichao2000/joseph-docs-public/blob/main/contracts/evidence-and-claims.md).
  Keep raw logs and evidence bundles out of this repository.
