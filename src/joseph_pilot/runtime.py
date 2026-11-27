import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from joseph_api.env import Declaration, Registry, config_path, read_shared_file
from pydantic import SecretStr
from pydantic.fields import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JOSEPH_PILOT_", extra="forbid")

    mode: Literal["research", "diagnostic"] = Field(default="research")
    access_key: SecretStr | None = None
    revision_root: Path | None = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def bootstrap(
    controlled: bool = False,
    *,
    declarations: tuple[Declaration, ...] | list[Declaration] = (),
    reservations: tuple[tuple[str, str], ...] | list[tuple[str, str]] = (),
) -> tuple[Settings, dict[str, str], str]:
    registry = Registry()
    registry.register(Declaration(owner="pilot", name="JOSEPH_PILOT_MODE"))
    registry.register(Declaration(owner="pilot", name="JOSEPH_PILOT_ACCESS_KEY", sensitive=True))
    registry.register(Declaration(owner="pilot", name="JOSEPH_PILOT_REVISION_ROOT"))
    registry.register(Declaration.shared(owner="host", name="JOSEPH_PROGRESS"))
    for owner, prefix in reservations:
        registry.reserve(owner, prefix)
    for declaration in declarations:
        registry.register(declaration)
    registry.finalize()
    path = config_path(os.environ.get("XDG_CONFIG_HOME"), Path.home())
    file = read_shared_file(path, controlled=controlled)
    values, diagnostics = registry.resolve_sources(file, os.environ, controlled=controlled)
    for diagnostic in diagnostics:
        logging.getLogger("joseph_pilot").warning("configuration: %s", " ".join(diagnostic))
    settings = Settings.model_validate(
        {
            key.removeprefix("JOSEPH_PILOT_").lower(): value
            for key, value in values.items()
            if key.startswith("JOSEPH_PILOT_")
        }
    )
    return settings, registry.redacted(values), values.get("JOSEPH_PROGRESS", "")


@contextmanager
def progress(enabled: bool) -> Iterator[None]:
    if not enabled:
        yield
        return
    try:
        from rich.console import Console
        from rich.progress import Progress
    except ImportError:
        yield
        return
    console = Console(stderr=True, no_color=bool(os.environ.get("NO_COLOR")))
    with Progress(console=console, redirect_stdout=False, redirect_stderr=False) as display:
        display.add_task("runtime check", total=1, completed=1)
        yield


def progress_enabled(value: str) -> bool:
    return sys.stderr.isatty() and not os.environ.get("CI") and value.lower() != "off"
