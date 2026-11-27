"""Pinned-revision reader: a receipt under the revision root, verified whole before any file is
read, read as plain Parquet into rows plus the pin. Never a live source, never the lake CLI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import pyarrow.parquet as pq
from joseph_api import RevisionRecord
from joseph_dal import verify_revision

from joseph_pilot.manifest import Pin
from joseph_pilot.runtime import Settings, bootstrap

CONTRACT_COLUMNS = ("expiry_date", "expiry_month", "option_type", "strike", "multiplier")


@dataclass(frozen=True)
class RevisionData:
    """Rows of one capability plus the record and the pin a manifest carries."""

    rows: pd.DataFrame
    record: RevisionRecord
    pin: Pin


def load_revision(capability: str, *, settings: Settings | None = None) -> RevisionData:
    """Load a capability's revision under `JOSEPH_PILOT_REVISION_ROOT`.

    Verifies the whole revision against its receipt before reading any file; a missing file fails
    by name and nothing is read partially.
    """
    settings = settings or bootstrap()[0]
    root = settings.revision_root
    if root is None:
        raise RuntimeError(
            "JOSEPH_PILOT_REVISION_ROOT is not set; point it at the directory holding "
            f"{capability}.revision.json"
        )
    receipt = root / f"{capability}.revision.json"
    record = RevisionRecord.from_json(receipt.read_text(encoding="utf-8"))
    verify_revision(root, record)
    frames = [pq.read_table(root / entry.path).to_pandas() for entry in record.files]
    rows = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    window = f"{record.window.start}..{record.window.end}" if record.window else None
    pin = Pin(
        revision_id=record.revision_id,
        window=window,
        content_digest=record.content_digest,
    )
    return RevisionData(rows=rows, record=record, pin=pin)


def attach_contracts(bars: pd.DataFrame, contracts: pd.DataFrame) -> pd.DataFrame:
    """Join option bars to their contract rows on `symbol` for the typed contract columns.

    Contract columns are sourced from the contract row. Missing or duplicate contract symbols
    are rejected rather than dropping or multiplying bars.
    """
    orphans = sorted(set(bars["symbol"]) - set(contracts["symbol"]))
    if orphans:
        raise ValueError(f"{len(orphans)} bar symbols have no contract row, e.g. {orphans[:3]}")
    return bars.drop(columns=list(CONTRACT_COLUMNS), errors="ignore").merge(
        contracts[["symbol", *CONTRACT_COLUMNS]], on="symbol", how="left", validate="many_to_one"
    )


def resolve_expiry(
    expiry_date: date | None,
    expiry_month: date,
    last_bar_date: date,
    *,
    trading_calendar: Mapping[date, bool] | None = None,
) -> date:
    """Use the source expiry, or roll the third Friday to the next calendar trading day.

    A derived expiry requires a calendar covering every day through the next trading day.
    The expiry, never the potentially truncated last bar, is authoritative; a mismatch fails.
    """
    resolved = expiry_date
    if resolved is None:
        resolved = third_friday(expiry_month.year, expiry_month.month)
        while True:
            if trading_calendar is None or resolved not in trading_calendar:
                raise ValueError(f"trading calendar missing date {resolved}")
            if trading_calendar[resolved]:
                break
            resolved += timedelta(days=1)
    if resolved != last_bar_date:
        raise ValueError(
            f"derived expiry {resolved} disagrees with the symbol's last bar date {last_bar_date}"
        )
    return resolved


def third_friday(year: int, month: int) -> date:
    day = date(year, month, 1)
    fridays = 0
    while day.month == month:
        if day.weekday() == 4:
            fridays += 1
            if fridays == 3:
                return day
        day += timedelta(days=1)
    raise ValueError(f"no third Friday in {year}-{month:02d}")
