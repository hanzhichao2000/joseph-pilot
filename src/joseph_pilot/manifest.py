import json
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

NonEmpty = Annotated[str, Field(min_length=1)]


class CalendarRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: date
    end: date


class Pin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: NonEmpty
    window: NonEmpty | None = None
    calendar_unverified: CalendarRange | None = None
    content_digest: Annotated[str, Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")]


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["1"] = Field(default="1", alias="$schema")
    inputs: dict[str, Pin] = Field(min_length=1)
    economic_conventions: dict[str, str] = Field(min_length=1)
    vectorbt_version: NonEmpty
    seed: int
    window: NonEmpty | None
    experiment_id: NonEmpty


def write_manifest(manifest: Manifest, path: Path) -> None:
    path.write_text(
        json.dumps(manifest.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True) + "\n"
    )
