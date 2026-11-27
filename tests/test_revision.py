from __future__ import annotations

import hashlib
import socket
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from joseph_api import RevisionFile, RevisionRecord, RevisionWindow
from joseph_dal import RevisionVerificationError

from joseph_pilot.manifest import Pin
from joseph_pilot.revision import RevisionData, attach_contracts, load_revision, resolve_expiry
from joseph_pilot.runtime import Settings, bootstrap

WINDOW = (date(2024, 1, 2), date(2024, 1, 5))


def make_revision(
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


BARS = {
    "year=2024/month=1/data_0.parquet": [
        {"symbol": "IO2403C3500.CFE", "trade_date": date(2024, 1, 2), "settle": 91.4},
        {"symbol": "IO2403C3500.CFE", "trade_date": date(2024, 1, 3), "settle": 93.0},
    ]
}
CONTRACTS = {
    "part-0.parquet": [
        {
            "symbol": "IO2403C3500.CFE",
            "expiry_date": None,
            "expiry_month": date(2024, 3, 1),
            "multiplier": 100.0,
        }
    ]
}


def settings_for(root: Path) -> Settings:
    return Settings(mode="research", revision_root=root)


def test_load_revision_returns_rows_and_pin(tmp_path: Path) -> None:
    record = make_revision(tmp_path, "option_bars", BARS)
    data = load_revision("option_bars", settings=settings_for(tmp_path))
    assert isinstance(data, RevisionData)
    assert data.rows["settle"].tolist() == [91.4, 93.0]
    assert data.record == record
    assert data.pin == Pin(
        revision_id="option_bars@lake:fake0001",
        window="2024-01-02..2024-01-05",
        content_digest=record.content_digest,
    )


def test_missing_file_fails_by_name_before_any_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_revision(tmp_path, "option_bars", BARS)
    (tmp_path / "option_bars/year=2024/month=1/data_0.parquet").unlink()

    def _no_read(*args: object, **kwargs: object) -> None:
        raise AssertionError("no parquet may be read before verification passes")

    monkeypatch.setattr(pq, "read_table", _no_read)
    with pytest.raises(RevisionVerificationError, match="data_0.parquet"):
        load_revision("option_bars", settings=settings_for(tmp_path))


def test_load_revision_makes_no_live_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_revision(tmp_path, "option_bars", BARS)

    def _no_subprocess(*args: object, **kwargs: object) -> None:
        raise AssertionError("the reader never runs a subprocess")

    def _no_socket(*args: object, **kwargs: object) -> None:
        raise AssertionError("the reader never opens a socket")

    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    monkeypatch.setattr(socket, "socket", _no_socket)
    data = load_revision("option_bars", settings=settings_for(tmp_path))
    assert len(data.rows) == 2


def test_load_revision_requires_the_root_variable(tmp_path: Path) -> None:
    make_revision(tmp_path, "option_bars", BARS)
    with pytest.raises(RuntimeError, match="JOSEPH_PILOT_REVISION_ROOT"):
        load_revision("option_bars", settings=Settings(mode="research"))


def test_bootstrap_reads_the_root_variable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOSEPH_PILOT_REVISION_ROOT", str(tmp_path))
    settings, _, _ = bootstrap()
    assert settings.revision_root == tmp_path


def test_attach_contracts_joins_on_symbol() -> None:
    bars = pd.DataFrame({"symbol": ["IO2403C3500.CFE", "IO2403C3500.CFE"], "settle": [91.4, 93.0]})
    contracts = pd.DataFrame(CONTRACTS["part-0.parquet"])
    joined = attach_contracts(bars, contracts)
    assert joined["expiry_month"].iloc[0] == date(2024, 3, 1)
    assert joined["multiplier"].iloc[0] == 100.0
    assert len(joined) == 2


def test_attach_contracts_reports_bars_without_a_contract() -> None:
    bars = pd.DataFrame({"symbol": ["IO2403C3500.CFE"], "settle": [91.4]})
    contracts = pd.DataFrame(
        [
            {
                "symbol": "HO2311C2125.CFE",
                "expiry_date": None,
                "expiry_month": date(2023, 11, 1),
                "multiplier": 100.0,
            }
        ]
    )
    with pytest.raises(ValueError, match="IO2403C3500.CFE"):
        attach_contracts(bars, contracts)


def test_resolve_expiry_uses_the_source_date_or_the_third_friday() -> None:
    assert resolve_expiry(date(2026, 11, 20), date(2026, 11, 1), date(2026, 11, 20)) == date(
        2026, 11, 20
    )
    assert resolve_expiry(None, date(2024, 3, 1), date(2024, 3, 15)) == date(2024, 3, 15)
    assert resolve_expiry(None, date(2024, 11, 1), date(2024, 11, 15)) == date(2024, 11, 15)


def test_resolve_expiry_raises_on_disagreement() -> None:
    with pytest.raises(ValueError, match=r"2024-03-15.*2024-03-14"):
        resolve_expiry(None, date(2024, 3, 1), date(2024, 3, 14))
