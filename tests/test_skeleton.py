import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_roundtrip_and_pins(tmp_path):
    from joseph_pilot.manifest import Manifest, Pin, write_manifest

    pin = Pin(revision_id="revision", window="2024", content_digest="a" * 64)
    other = Pin(revision_id="revision", window="2025", content_digest="a" * 64)
    assert pin != other
    manifest = Manifest(
        inputs={"data": pin},
        economic_conventions={"price": "settle"},
        vectorbt_version="none",
        seed=1,
        window="2024",
        experiment_id="example",
    )
    path = tmp_path / "manifest.json"
    write_manifest(manifest, path)
    assert Manifest.model_validate_json(path.read_text()) == manifest
    assert (
        path.read_text()
        == json.dumps(json.loads(path.read_text()), indent=2, sort_keys=True) + "\n"
    )
    with pytest.raises(ValueError):
        Manifest.model_validate({**manifest.model_dump(), "unknown": 1})
    with pytest.raises(ValueError):
        Pin(revision_id="", window="2024", content_digest="a" * 64)


def test_snapshot_windows_and_required_manifest_window():
    from joseph_pilot.manifest import Manifest, Pin

    pin = Pin(revision_id="snapshot", content_digest="a" * 64)
    assert pin.window is None
    values = {
        "inputs": {"data": pin},
        "economic_conventions": {"price": "settle"},
        "vectorbt_version": "none",
        "seed": 1,
        "experiment_id": "snapshot",
    }
    assert Manifest(**values, window=None).window is None
    with pytest.raises(ValueError):
        Manifest(**values)


@pytest.mark.parametrize(
    "digest", ["garbage", "A" * 64, "a" * 63, "a" * 65, "g" * 64, "a" * 64 + "\n"]
)
def test_pin_rejects_invalid_digest(digest):
    from joseph_pilot.manifest import Pin

    with pytest.raises(ValueError):
        Pin(revision_id="revision", window="2024", content_digest=digest)


def run_tool(name, *args):
    return subprocess.run(
        [sys.executable, str(ROOT / "tools" / name), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_source_guard(tmp_path):
    root = tmp_path / "notebooks" / "book-examples"
    root.mkdir(parents=True)
    assert run_tool("check_sources.py", root).returncode == 0
    chapter = root / "author-book" / "chapter-04-example"
    chapter.mkdir(parents=True)
    notebook = chapter / "example.ipynb"
    notebook.write_text("{}")
    assert run_tool("check_sources.py", root).returncode != 0
    (chapter / "SOURCE.md").write_text(
        "publication: Book\nedition: 2\nchapter: 4\npublished parameters: example\n"
    )
    assert run_tool("check_sources.py", root).returncode == 0
    notebook.rename(chapter / "Bad_Name.ipynb")
    assert run_tool("check_sources.py", root).returncode != 0


@pytest.fixture
def keyword_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "-C", root, "init", "-q"], check=True)
    return root


@pytest.fixture
def keywords(tmp_path):
    path = tmp_path / "keywords.txt"
    path.write_text("synthetic-forbidden-term\n")
    return path


def track_keyword_fixture(root, filename, content):
    path = root / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    subprocess.run(["git", "-C", root, "add", "--", filename], check=True)
    return path


def test_keyword_guard(keyword_repo, keywords):
    path = track_keyword_fixture(keyword_repo, "src/file.py", "SYNTHETIC-FORBIDDEN-TERM")
    assert run_tool("check_keywords.py", keywords, keyword_repo).returncode == 1
    path.write_text("safe")
    assert run_tool("check_keywords.py", keywords, keyword_repo).returncode == 0


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_keyword_guard_rejects_invalid_scan_root(tmp_path, keywords, kind):
    root = tmp_path / "scan-root"
    if kind == "file":
        root.write_text("safe")
    result = run_tool("check_keywords.py", keywords, root)
    assert result.returncode == 2
    assert "target Git working tree" in result.stderr
    assert "synthetic-forbidden-term" not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


def test_template_valid():
    from joseph_pilot.manifest import Manifest

    Manifest.model_validate_json((ROOT / "templates" / "manifest.json").read_text())


@pytest.mark.parametrize("field", ["publication", "edition", "chapter", "published parameters"])
@pytest.mark.parametrize("kind", ["missing", "empty", "spaces", "crossline"])
def test_source_fields_require_same_line_values(tmp_path, field, kind):
    root = tmp_path / "books"
    chapter = root / "author-book" / "chapter-04-example"
    chapter.mkdir(parents=True)
    (chapter / "example.ipynb").write_text("{}")
    fields = {
        "publication": "Book",
        "edition": "2",
        "chapter": "4",
        "published parameters": "example",
    }
    lines = [f"{key}: {value}" for key, value in fields.items() if key != field]
    if kind != "missing":
        lines.insert(0, f"{field}:" + ("   " if kind == "spaces" else ""))
        if kind == "crossline":
            lines.insert(1, "")
    (chapter / "SOURCE.md").write_text("\n".join(lines) + "\n")
    result = run_tool("check_sources.py", root)
    assert result.returncode != 0, (field, kind)


@pytest.mark.parametrize("field", ["publication", "edition", "chapter", "published parameters"])
@pytest.mark.parametrize(
    "placeholder", ["TODO", "TBD", "placeholder", "unknown", "n/a", "<required>"]
)
def test_source_rejects_placeholder_values(tmp_path, field, placeholder):
    chapter = tmp_path / "author-book" / "chapter-04-example"
    chapter.mkdir(parents=True)
    (chapter / "example.ipynb").write_text("{}")
    fields = {
        "publication": "A Book",
        "edition": "2",
        "chapter": "4",
        "published parameters": "payoff",
    }
    fields[field] = placeholder
    (chapter / "SOURCE.md").write_text(
        "".join(f"{key}: {value}\n" for key, value in fields.items())
    )
    assert run_tool("check_sources.py", tmp_path).returncode != 0


def test_source_fields_complete_values_pass(tmp_path):
    chapter = tmp_path / "author-book" / "chapter-04-example"
    chapter.mkdir(parents=True)
    (chapter / "example.ipynb").write_text("{}")
    (chapter / "SOURCE.md").write_text(
        "publication: Book\nedition: 2\nchapter: 4\npublished parameters: payoff\n"
    )
    assert run_tool("check_sources.py", tmp_path).returncode == 0


def test_source_checker_rejects_missing_root(tmp_path):
    result = run_tool("check_sources.py", tmp_path / "wrong")
    assert result.returncode != 0


def test_strategy_requires_sibling_source(tmp_path):
    books = tmp_path / "books"
    strategies = tmp_path / "strategies"
    books.mkdir()
    strategies.mkdir()
    (strategies / "__init__.py").write_text("")
    assert run_tool("check_sources.py", books, strategies).returncode == 0
    strategy = strategies / "nested"
    strategy.mkdir()
    (strategy / "example.py").write_text("pass\n")
    assert run_tool("check_sources.py", books, strategies).returncode != 0
    (strategy / "SOURCE.md").write_text(
        "publication: Book\nedition: 2\nchapter: 4\npublished parameters: value\n"
    )
    assert run_tool("check_sources.py", books, strategies).returncode == 0
    (strategy / "SOURCE.md").write_text(
        "publication:\nedition: 2\nchapter: 4\npublished parameters: value\n"
    )
    assert run_tool("check_sources.py", books, strategies).returncode != 0
    assert run_tool("check_sources.py", books, tmp_path / "missing").returncode != 0


def test_real_source_roots_pass():
    assert (
        run_tool(
            "check_sources.py",
            ROOT / "notebooks/book-examples",
            ROOT / "src/joseph_pilot/strategies",
        ).returncode
        == 0
    )


@pytest.mark.parametrize("invalid", [None, "", "# comment\n  \n"])
def test_keyword_list_required_and_nonempty(keyword_repo, keywords, invalid):
    if invalid is None:
        keywords.unlink()
    else:
        keywords.write_text(invalid)
    assert run_tool("check_keywords.py", keywords, keyword_repo).returncode == 2


@pytest.mark.parametrize(
    "filename",
    ["tools/example.py", ".github/workflows/ci.yml", "pyproject.toml", "README.md", "LICENSE"],
)
def test_keyword_scans_public_text(keyword_repo, keywords, filename):
    track_keyword_fixture(keyword_repo, filename, "SYNTHETIC-FORBIDDEN-TERM")
    result = run_tool("check_keywords.py", keywords, keyword_repo)
    assert result.returncode == 1
    assert "(0 path, 1 text matches)" in result.stderr
    assert "synthetic-forbidden-term" not in result.stderr.casefold()


def test_keyword_scans_tracked_paths(keyword_repo, keywords):
    track_keyword_fixture(keyword_repo, "src/synthetic-forbidden-term/module.py", "pass")
    result = run_tool("check_keywords.py", keywords, keyword_repo)
    assert result.returncode == 1
    assert "(1 path, 0 text matches)" in result.stderr
    assert "synthetic-forbidden-term" not in result.stderr


def test_self_hosted_job_rejects_fork_pull_requests():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert (
        "    if: github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository"
        in workflow
    )


def test_ci_ruff_scans_only_pilot_directories():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    commands = [
        line.strip().removeprefix("- run: ")
        for line in workflow.splitlines()
        if line.strip().startswith("- run: ") and ".venv/bin/ruff " in line
    ]
    assert commands == [
        ".venv/bin/ruff check src tests tools",
        ".venv/bin/ruff format --check src tests tools",
    ]


def test_ci_uses_isolated_python_environment():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    commands = [
        line.strip().removeprefix("- run: ")
        for line in workflow.splitlines()
        if line.strip().startswith("- run: ")
    ]
    assert commands == [
        "python3 tools/check_keywords.py keywords/public-boundary.txt .",
        'python3 -c "import sys; assert sys.version_info >= (3, 11), sys.version"',
        "python3 -m venv .venv",
        ".venv/bin/pip install '.[dev,ux]'",
        ".venv/bin/ruff check src tests tools",
        ".venv/bin/ruff format --check src tests tools",
        ".venv/bin/mypy",
        ".venv/bin/pytest",
        ".venv/bin/python tools/check_sources.py",
    ]
