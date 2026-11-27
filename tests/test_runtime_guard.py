import ast
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
CANARY = "synthetic-access-value-7319-long-canary"


def env_for(tmp_path, **values):
    env = {k: v for k, v in os.environ.items() if not k.startswith("JOSEPH_")}
    env.update(HOME=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path / "config"), PYTHONPATH=str(SRC))
    env.pop("CI", None)
    env.pop("NO_COLOR", None)
    env.update(values)
    return env


def run_cli(tmp_path, *args, module=False, **env):
    command = (
        [sys.executable, "-m", "joseph_pilot"]
        if module
        else [str(Path(sys.executable).with_name("joseph-pilot"))]
    )
    return subprocess.run(
        [*command, *args],
        env=env_for(tmp_path, **env),
        capture_output=True,
        text=True,
        check=False,
    )


def write_config(tmp_path, text):
    directory = tmp_path / "config" / "joseph"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".env"
    path.write_text(text)
    path.chmod(0o600)
    return path


def aliases_are_prefixed(source):
    tree = ast.parse(source)
    os_names = {"os"}
    getenv_names = set()
    environ_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            os_names.update(
                alias.asname or alias.name for alias in node.names if alias.name == "os"
            )
        elif isinstance(node, ast.ImportFrom) and node.module == "os" and node.level == 0:
            for alias in node.names:
                if alias.name == "getenv":
                    getenv_names.add(alias.asname or alias.name)
                elif alias.name == "environ":
                    environ_names.add(alias.asname or alias.name)

    def approved(value):
        if isinstance(value, ast.Constant):
            return isinstance(value.value, str) and value.value.startswith("JOSEPH_PILOT_")
        return False

    def is_os_attribute(node, name):
        return (
            isinstance(node, ast.Attribute)
            and node.attr == name
            and isinstance(node.value, ast.Name)
            and node.value.id in os_names
        )

    def is_environ(node):
        return is_os_attribute(node, "environ") or (
            isinstance(node, ast.Name) and node.id in environ_names
        )

    def safe_env_key(node):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            return False
        key = node.value
        return (
            not key.startswith("JOSEPH_")
            or key.startswith("JOSEPH_PILOT_")
            or key == "JOSEPH_PROGRESS"
        )

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and is_environ(node.value)
            and not safe_env_key(node.slice)
        ):
            return False
        if isinstance(node, ast.Call):
            direct_get = (
                is_os_attribute(node.func, "getenv")
                or (isinstance(node.func, ast.Name) and node.func.id in getenv_names)
                or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get"
                    and is_environ(node.func.value)
                )
            )
            if direct_get:
                key = node.args[0] if node.args else None
                if node.args:
                    if len(node.args) > 2 or any(isinstance(arg, ast.Starred) for arg in node.args):
                        return False
                    if node.keywords and (
                        len(node.args) == 2
                        or len(node.keywords) != 1
                        or node.keywords[0].arg != "default"
                    ):
                        return False
                else:
                    names = [keyword.arg for keyword in node.keywords]
                    if len(names) == len(set(names)) and set(names) in (
                        {"key"},
                        {"key", "default"},
                    ):
                        key = next(
                            keyword.value for keyword in node.keywords if keyword.arg == "key"
                        )
                if key is None or not safe_env_key(key):
                    return False
            is_field = (isinstance(node.func, ast.Name) and node.func.id == "Field") or (
                isinstance(node.func, ast.Attribute) and node.func.attr == "Field"
            )
            if is_field and any(keyword.arg is None for keyword in node.keywords):
                return False
        if (
            isinstance(node, ast.keyword)
            and node.arg in {"alias", "validation_alias"}
            and not approved(node.value)
        ):
            return False
    return True


@pytest.mark.parametrize(
    "source",
    [
        'x = Field(**{"validation_alias": "BARE"})',
        'x = pydantic.Field(**{"alias": "JOSEPH_PILOT_SAFE"})',
        "x = Field(**unknown)",
    ],
)
def test_field_expanded_kwargs_fail_closed(source):
    assert not aliases_are_prefixed(source)


@pytest.mark.parametrize(
    "source",
    [
        "os.getenv('JOSEPH_OTHER_X')",
        "os.environ.get('JOSEPH_OTHER_X')",
        "os.environ['JOSEPH_OTHER_X']",
        "os.getenv(name)",
        "os.environ.get(name)",
        "os.environ[name]",
    ],
)
def test_direct_env_guard_rejects_unsafe_keys(source):
    assert not aliases_are_prefixed(source)


@pytest.mark.parametrize(
    "source",
    [
        "os.getenv('JOSEPH_PILOT_X')",
        "os.environ.get('JOSEPH_PROGRESS')",
        "os.environ['JOSEPH_PILOT_X']",
        "os.getenv('XDG_CONFIG_HOME')",
        "os.environ.get('CI')",
        "os.environ['NO_COLOR']",
    ],
)
def test_direct_env_guard_allows_safe_keys(source):
    assert aliases_are_prefixed(source)


@pytest.mark.parametrize("method", ["os.getenv", "os.environ.get"])
@pytest.mark.parametrize("key", ["CI", "JOSEPH_PILOT_X", "JOSEPH_PROGRESS"])
def test_direct_env_guard_allows_safe_keyword_keys(method, key):
    assert aliases_are_prefixed(f"{method}(key={key!r})")


@pytest.mark.parametrize("method", ["os.getenv", "os.environ.get"])
@pytest.mark.parametrize("key", ["'JOSEPH_OTHER_X'", "name"])
def test_direct_env_guard_rejects_unsafe_keyword_keys(method, key):
    assert not aliases_are_prefixed(f"{method}(key={key})")


@pytest.mark.parametrize("method", ["os.getenv", "os.environ.get"])
def test_direct_env_guard_rejects_expanded_keyword_keys(method):
    assert not aliases_are_prefixed(f"{method}(**kwargs)")


@pytest.mark.parametrize("method", ["os.getenv", "os.environ.get"])
@pytest.mark.parametrize("key", ["CI", "JOSEPH_PILOT_X", "JOSEPH_PROGRESS"])
def test_direct_env_guard_allows_safe_keyword_keys_with_default(method, key):
    assert aliases_are_prefixed(f"{method}(key={key!r}, default='false')")


@pytest.mark.parametrize("method", ["os.getenv", "os.environ.get"])
@pytest.mark.parametrize(
    "args",
    [
        "key='JOSEPH_OTHER_X', default='false'",
        "key=name, default='false'",
        "key='CI', default='false', other=1",
        "key='CI', default='false', **kwargs",
    ],
)
def test_direct_env_guard_rejects_unsafe_keyword_combinations(method, args):
    assert not aliases_are_prefixed(f"{method}({args})")


@pytest.mark.parametrize("method", ["os.getenv", "os.environ.get"])
@pytest.mark.parametrize(
    "args",
    [
        "'CI', **kwargs",
        "'CI', other=1",
        "'CI', 'false', default='false'",
        "'CI', 'false', 'extra'",
        "'CI', key='JOSEPH_OTHER_X'",
    ],
)
def test_direct_env_guard_rejects_invalid_positional_combinations(method, args):
    assert not aliases_are_prefixed(f"{method}({args})")


@pytest.mark.parametrize("method", ["os.getenv", "os.environ.get"])
@pytest.mark.parametrize("args", ["'CI', 'false'", "'CI', default='false'"])
def test_direct_env_guard_allows_positional_key_with_default(method, args):
    assert aliases_are_prefixed(f"{method}({args})")


@pytest.mark.parametrize(
    ("import_line", "method"),
    [
        ("import os as o", "o.getenv"),
        ("import os as o", "o.environ.get"),
        ("from os import getenv", "getenv"),
        ("from os import getenv as fetch", "fetch"),
        ("from os import environ", "environ.get"),
        ("from os import environ as env", "env.get"),
    ],
)
@pytest.mark.parametrize(
    "args", ["'JOSEPH_OTHER_X'", "name", "'CI', **kwargs", "key='CI', other=1"]
)
def test_imported_env_guard_rejects_unsafe_calls(import_line, method, args):
    assert not aliases_are_prefixed(f"{import_line}\n{method}({args})")


@pytest.mark.parametrize(
    ("import_line", "environ"),
    [
        ("import os as o", "o.environ"),
        ("from os import environ", "environ"),
        ("from os import environ as env", "env"),
    ],
)
@pytest.mark.parametrize("key", ["'JOSEPH_OTHER_X'", "name"])
def test_imported_env_guard_rejects_unsafe_subscripts(import_line, environ, key):
    assert not aliases_are_prefixed(f"{import_line}\n{environ}[{key}]")


@pytest.mark.parametrize(
    ("import_line", "method"),
    [
        ("import os as o", "o.getenv"),
        ("import os as o", "o.environ.get"),
        ("from os import getenv", "getenv"),
        ("from os import getenv as fetch", "fetch"),
        ("from os import environ", "environ.get"),
        ("from os import environ as env", "env.get"),
    ],
)
@pytest.mark.parametrize(
    "args", ["'CI', 'false'", "key='JOSEPH_PILOT_X', default='false'", "'JOSEPH_PROGRESS'"]
)
def test_imported_env_guard_allows_safe_calls(import_line, method, args):
    assert aliases_are_prefixed(f"{import_line}\n{method}({args})")


def test_env_prefix_guard(tmp_path):
    for path in SRC.rglob("*.py"):
        assert aliases_are_prefixed(path.read_text()), str(path)
    assert not aliases_are_prefixed('x = Field(validation_alias=AliasChoices("BARE"))')
    assert not aliases_are_prefixed("BARE = 'UNAPPROVED'; x = Field(validation_alias=BARE)")
    assert not aliases_are_prefixed("x = Field(alias=make_alias('JOSEPH_PILOT_OK'))")
    assert aliases_are_prefixed('x = Field(alias="JOSEPH_PILOT_SAFE")')
    assert not aliases_are_prefixed('x = Field(validation_alias=AliasChoices("JOSEPH_PILOT_SAFE"))')
    write_config(tmp_path, "JOSEPH_MINI_OTHER=ignored\nJOSEPH_PILOT_UNKNOWN=value\n")
    result = run_cli(tmp_path, "runtime-check", "--json")
    assert result.returncode == 0
    assert "JOSEPH_PILOT_UNKNOWN" in result.stderr
    assert "JOSEPH_MINI_OTHER" not in result.stderr


def test_no_secret_in_logs(tmp_path):
    write_config(tmp_path, f"JOSEPH_PILOT_ACCESS_KEY={CANARY}\nJOSEPH_PILOT_MODE=research\n")
    result = run_cli(tmp_path, "runtime-check", "--json", JOSEPH_PILOT_MODE="research")
    assert result.returncode == 0
    assert "JOSEPH_PILOT_MODE" in result.stderr
    if CANARY in result.stdout + result.stderr:
        pytest.fail("Sensitive value leaked", pytrace=False)
    assert json.loads(result.stdout)["config"]["JOSEPH_PILOT_ACCESS_KEY"] == "***"
    result = run_cli(tmp_path, "runtime-check", "--json", JOSEPH_PILOT_MODE=CANARY)
    assert result.returncode != 0
    assert not result.stdout
    if CANARY in result.stderr:
        pytest.fail("Sensitive value leaked", pytrace=False)
    assert "configuration validation failed" in result.stderr
    result = run_cli(
        tmp_path, "runtime-check", "--json", "--controlled", JOSEPH_PILOT_ACCESS_KEY=CANARY
    )
    assert result.returncode != 0
    assert not result.stdout
    if CANARY in result.stderr:
        pytest.fail("Sensitive value leaked", pytrace=False)


@pytest.mark.parametrize("module", [False, True])
def test_stdout_is_machine_readable(tmp_path, module):
    result = run_cli(tmp_path, "runtime-check", "--json", module=module)
    assert result.returncode == 0
    document = json.loads(result.stdout)
    assert document == {"status": "ok", "config": {}}
    failure = run_cli(
        tmp_path, "runtime-check", "--json", module=module, JOSEPH_PILOT_MODE="invalid"
    )
    assert failure.returncode != 0 and failure.stdout == "" and failure.stderr


def test_import_has_no_side_effects(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", "import joseph_pilot"],
        env=env_for(tmp_path, JOSEPH_PILOT_UNKNOWN=CANARY),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert not result.stdout and not result.stderr


def test_missing_rich_fallback(tmp_path):
    code = """import builtins, json
original = builtins.__import__
blocked_calls = []
def blocked(name, *args, **kwargs):
    if name == 'rich' or name.startswith('rich.'):
        blocked_calls.append(name)
        raise ImportError('blocked')
    return original(name, *args, **kwargs)
builtins.__import__ = blocked
from joseph_pilot.runtime import progress
with progress(True):
    print(json.dumps({'status': 'ok'}))
assert blocked_calls, 'Rich import fallback not exercised'
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env_for(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "ok"


@pytest.mark.skipif(os.name != "posix", reason="PTY requires POSIX")
@pytest.mark.parametrize(
    "overrides,progress",
    [
        ({}, True),
        ({"CI": "true"}, False),
        ({"JOSEPH_PROGRESS": "off"}, False),
        ({"NO_COLOR": "1"}, True),
        ({"NO_COLOR": ""}, True),
    ],
)
def test_stderr_tty(tmp_path, overrides, progress):
    import pty

    master, slave = pty.openpty()
    try:
        result = subprocess.run(
            [str(Path(sys.executable).with_name("joseph-pilot")), "runtime-check", "--json"],
            env=env_for(tmp_path, TERM="xterm-256color", **overrides),
            stdout=subprocess.PIPE,
            stderr=slave,
            check=False,
        )
    finally:
        os.close(slave)
    try:
        chunks = []
        while True:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
        stderr = b"".join(chunks)
    finally:
        os.close(master)
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "ok"
    assert (b"runtime check" in stderr) is progress
    import re

    if overrides.get("NO_COLOR"):
        assert not re.search(rb"\x1b\[[0-9;]*m", stderr)
    elif progress:
        assert re.search(rb"\x1b\[[0-9;]*m", stderr)


@pytest.mark.parametrize("exception", ["RuntimeError", "KeyboardInterrupt"])
def test_progress_cleanup_and_exception_safety(tmp_path, exception):
    code = """import sys
from rich.progress import Progress as RealProgress
import rich.progress
class TrackingProgress(RealProgress):
    instances = []
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stopped = False
        self.instances.append(self)
    def stop(self):
        super().stop()
        self.stopped = True
rich.progress.Progress = TrackingProgress
from joseph_pilot.runtime import progress
old = (sys.stdout, sys.stderr)
try:
    with progress(True):
        assert TrackingProgress.instances and TrackingProgress.instances[0].live.is_started
        raise EXCEPTION()
except EXCEPTION:
    pass
assert (sys.stdout, sys.stderr) == old
assert TrackingProgress.instances[0].stopped
assert not TrackingProgress.instances[0].live.is_started
""".replace("EXCEPTION", exception)
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env_for(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not result.stdout


def test_help(tmp_path):
    result = run_cli(tmp_path, "--help")
    assert result.returncode == 0
    assert "runtime-check" in result.stdout


def test_controlled_file_and_source_precedence(tmp_path):
    write_config(tmp_path, "JOSEPH_PILOT_MODE=research\n")
    ordinary = run_cli(tmp_path, "runtime-check", "--json", JOSEPH_PILOT_MODE="diagnostic")
    assert ordinary.returncode == 0
    assert json.loads(ordinary.stdout)["config"]["JOSEPH_PILOT_MODE"] == "diagnostic"
    assert "JOSEPH_PILOT_MODE" in ordinary.stderr
    controlled = run_cli(
        tmp_path, "runtime-check", "--json", "--controlled", JOSEPH_PILOT_MODE="diagnostic"
    )
    assert controlled.returncode != 0 and not controlled.stdout
    allowed = run_cli(tmp_path, "runtime-check", "--json", "--controlled")
    assert allowed.returncode == 0


@pytest.mark.parametrize("exception", ["RuntimeError", "ValueError"])
def test_exception_does_not_leak(tmp_path, exception):
    code = """import sys
from joseph_pilot import cli
def fail(*args, **kwargs):
    raise EXCEPTION('synthetic-access-value-7319-long-canary')
cli.bootstrap = fail
raise SystemExit(cli.main(['runtime-check', '--json']))
""".replace("EXCEPTION", exception)
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env_for(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0 and not result.stdout
    if CANARY in result.stderr:
        pytest.fail("Sensitive value leaked", pytrace=False)
    assert result.stderr


def test_settings_cannot_read_environment_directly(tmp_path):
    code = """from joseph_pilot.runtime import Settings
assert Settings().mode == 'research'
assert Settings().access_key is None
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env_for(tmp_path, JOSEPH_PILOT_MODE="diagnostic", JOSEPH_PILOT_ACCESS_KEY=CANARY),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0


def test_missing_controlled_file_and_unsafe_file(tmp_path):
    result = run_cli(tmp_path, "runtime-check", "--json", "--controlled")
    assert result.returncode != 0 and not result.stdout and result.stderr
    path = write_config(tmp_path, f"JOSEPH_MINI_VALUE={CANARY}\n")
    path.chmod(0o644)
    result = run_cli(tmp_path, "runtime-check", "--json")
    assert result.returncode != 0 and not result.stdout and result.stderr
    if CANARY in result.stderr:
        pytest.fail("Sensitive value leaked", pytrace=False)
    assert "Unsafe shared file" in result.stderr
    assert path.stat().st_mode & 0o777 == 0o644


def test_conflicting_registry_declarations(tmp_path):
    code = """from joseph_api.env import Declaration, Registry
r = Registry()
r.register(Declaration(owner='pilot', name='JOSEPH_PILOT_MODE'))
r.register(Declaration(owner='pilot', name='JOSEPH_PILOT_MODE', sensitive=True))
try:
    r.finalize()
except ValueError:
    pass
else:
    raise AssertionError('conflict was accepted')
"""
    result = subprocess.run(
        [sys.executable, "-c", code], env=env_for(tmp_path), capture_output=True, check=False
    )
    assert result.returncode == 0


def test_host_composition_conflict_is_safe(tmp_path):
    code = """from joseph_api.env import Declaration
from joseph_pilot import cli
import sys
original = cli.bootstrap
def injected(**kw):
    try:
        original(declarations=[Declaration(owner='pilot', name='JOSEPH_PILOT_MODE', sensitive=True)], **kw)
    except ValueError:
        print('confirmed declaration conflict', file=sys.stderr)
        raise RuntimeError('confirmed declaration conflict')
    raise AssertionError('conflict accepted')
cli.bootstrap = injected
raise SystemExit(cli.main(['runtime-check', '--json']))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env_for(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0 and result.stdout == ""
    assert result.stderr.splitlines() == ["confirmed declaration conflict", "runtime check failed"]


def test_host_composition_shared_progress_is_idempotent(tmp_path):
    code = """from joseph_api.env import Declaration
from joseph_pilot.runtime import bootstrap
_, manifest, progress = bootstrap(declarations=[Declaration.shared(owner='host', name='JOSEPH_PROGRESS')])
assert manifest['JOSEPH_PROGRESS'] == 'off'
assert progress == 'off'
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env_for(tmp_path, JOSEPH_PROGRESS="off"),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_host_composition_private_extension(tmp_path):
    code = """from joseph_api.env import Declaration
from joseph_pilot.runtime import bootstrap
_, manifest, _ = bootstrap(declarations=[Declaration(owner='sample', name='JOSEPH_SAMPLE_VALUE')], reservations=[('sample', 'JOSEPH_SAMPLE_')])
assert manifest['JOSEPH_SAMPLE_VALUE'] == 'extended'
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env_for(tmp_path, JOSEPH_SAMPLE_VALUE="extended"),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_dependency_constraints_match_validated_versions():
    with (ROOT / "pyproject.toml").open("rb") as file:
        project = tomllib.load(file)["project"]
    assert "pydantic-settings==2.13.1" in project["dependencies"]
    assert "rich==14.3.3" in project["optional-dependencies"]["ux"]


def test_relative_xdg_uses_home_fallback_from_both_working_directories(tmp_path):
    home = tmp_path / "home"
    config = home / ".config" / "joseph"
    config.mkdir(parents=True)
    path = config / ".env"
    path.write_text("JOSEPH_PILOT_MODE=diagnostic\n")
    path.chmod(0o600)
    for name in ("first", "second"):
        cwd = tmp_path / name
        cwd.mkdir()
        decoy = cwd / "relative" / "joseph"
        decoy.mkdir(parents=True)
        decoy_file = decoy / ".env"
        decoy_file.write_text("JOSEPH_PILOT_MODE=research\n")
        decoy_file.chmod(0o600)
        result = subprocess.run(
            [str(Path(sys.executable).with_name("joseph-pilot")), "runtime-check", "--json"],
            cwd=cwd,
            env=env_for(home, XDG_CONFIG_HOME="relative"),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert json.loads(result.stdout)["config"]["JOSEPH_PILOT_MODE"] == "diagnostic"


def test_empty_xdg_uses_home_fallback_via_console(tmp_path):
    home = tmp_path / "home"
    path = home / ".config" / "joseph" / ".env"
    path.parent.mkdir(parents=True)
    path.write_text(f"JOSEPH_PILOT_MODE=diagnostic\nJOSEPH_PILOT_ACCESS_KEY={CANARY}\n")
    path.chmod(0o600)
    result = subprocess.run(
        [str(Path(sys.executable).with_name("joseph-pilot")), "runtime-check", "--json"],
        cwd=tmp_path,
        env=env_for(home, XDG_CONFIG_HOME=""),
        capture_output=True,
        text=True,
        check=False,
    )
    if CANARY in result.stdout + result.stderr:
        pytest.fail("Sensitive value leaked", pytrace=False)
    assert result.returncode == 0
    assert json.loads(result.stdout)["config"] == {
        "JOSEPH_PILOT_MODE": "diagnostic",
        "JOSEPH_PILOT_ACCESS_KEY": "***",
    }


def test_cli_fails_safely_when_platform_secure_access_is_unavailable(tmp_path):
    write_config(tmp_path, f"JOSEPH_PILOT_ACCESS_KEY={CANARY}\n")
    code = """import joseph_api.env
from joseph_pilot import cli
joseph_api.env._supports_secure_file_reading = lambda: False
raise SystemExit(cli.main(['runtime-check', '--json']))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env_for(tmp_path, JOSEPH_PILOT_ACCESS_KEY=CANARY),
        capture_output=True,
        text=True,
        check=False,
    )
    if CANARY in result.stdout + result.stderr:
        pytest.fail("Sensitive value leaked", pytrace=False)
    assert result.returncode != 0
    assert not result.stdout
    assert "Secure shared file access unavailable" in result.stderr


def test_active_access_key_in_unsafe_file_is_rejected_without_chmod_or_leak(tmp_path):
    path = write_config(tmp_path, f"JOSEPH_PILOT_ACCESS_KEY={CANARY}\n")
    path.chmod(0o644)
    result = run_cli(tmp_path, "runtime-check", "--json")
    if CANARY in result.stdout + result.stderr:
        pytest.fail("Sensitive value leaked", pytrace=False)
    assert result.returncode != 0
    assert not result.stdout
    assert "Unsafe shared file" in result.stderr
    assert path.stat().st_mode & 0o777 == 0o644


def test_cli_exception_cleans_progress_before_safe_diagnostic(tmp_path):
    code = """import contextlib, sys
from joseph_pilot import cli
real_progress = cli.progress
@contextlib.contextmanager
def tracked(enabled):
    try:
        with real_progress(enabled):
            print('entered', file=sys.stderr)
            yield
            raise RuntimeError('synthetic-access-value-7319-long-canary')
    finally:
        print('cleanup', file=sys.stderr)
cli.progress = tracked
raise SystemExit(cli.main(['runtime-check', '--json']))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env_for(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    if CANARY in result.stdout + result.stderr:
        pytest.fail("Sensitive value leaked", pytrace=False)
    assert result.returncode != 0
    assert not result.stdout
    assert result.stderr.splitlines() == ["entered", "cleanup", "runtime check failed"]


def test_non_tty_has_no_progress(tmp_path):
    result = run_cli(tmp_path, "runtime-check", "--json", TERM="xterm-256color")
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"status": "ok", "config": {}}
    assert "runtime check" not in result.stderr
