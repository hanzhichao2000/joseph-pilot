import json
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

NonEmpty = Annotated[str, Field(min_length=1)]


class Pin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: NonEmpty
    window: NonEmpty
    content_digest: NonEmpty


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inputs: dict[str, Pin] = Field(min_length=1)
    economic_conventions: dict[str, str] = Field(min_length=1)
    vectorbt_version: NonEmpty
    seed: int
    window: NonEmpty
    experiment_id: NonEmpty


def write_manifest(manifest: Manifest, path: Path) -> None:
    path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")
