from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from joseph_api import RevisionFile, RevisionRecord, RevisionWindow

WINDOW = (date(2024, 1, 2), date(2024, 1, 5))


def _make_revision(
    root: Path,
    capability: str,
    frames: dict[str, list[dict[str, object]]],
    *,
    window: tuple[date, date] | None = WINDOW,
    lake_id: str = "fake0001",
) -> RevisionRecord:
    """Write a revision the way the provider does: parquet under `<capability>/...`, digests, receipt."""
    files = []
    for rel, rows in frames.items():
        path = root / capability / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pylist(rows), path)
        files.append(
            RevisionFile(
                path=path.relative_to(root).as_posix(),
                digest=hashlib.sha256(path.read_bytes()).hexdigest(),
                size=path.stat().st_size,
            )
        )
    record = RevisionRecord(
        capability_id=capability,
        schema_version="cne-contract-0.25.0",
        source="cnequity@0.25.0",
        revision_id=f"{capability}@lake:{lake_id}",
        content_digest=RevisionRecord.compute_content_digest(
            capability, "cne-contract-0.25.0", "cnequity@0.25.0", tuple(files)
        ),
        files=tuple(files),
        window=RevisionWindow(start=window[0], end=window[1]) if window else None,
    )
    (root / f"{capability}.revision.json").write_text(record.to_json(), encoding="utf-8")
    return record


@pytest.fixture
def make_revision():
    return _make_revision
