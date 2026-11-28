import json
from datetime import date, timedelta
from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

from joseph_pilot.manifest import Manifest, Pin

NOTEBOOK = Path(
    "notebooks/book-examples/natenberg-option-volatility-and-pricing/"
    "chapter-04-expiration-pnl/parity-io-2024-2025.ipynb"
)


def test_parity_notebook_executes_on_revisions(tmp_path, monkeypatch, make_revision):
    start, end = date(2023, 12, 1), date(2024, 5, 31)
    holidays = {date(2024, 2, 16)}
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    days = [day for day in days if day.weekday() < 5 and day not in holidays]
    expiries = {
        "2401": date(2024, 1, 19),
        "2402": date(2024, 2, 19),
        "2403": date(2024, 3, 15),
        "2404": date(2024, 4, 19),
    }
    contracts, options, futures = [], [], []
    for code, expiry in expiries.items():
        for kind in ("C", "P"):
            symbol = f"IO{code}{kind}4000.CFE"
            contracts.append(
                {
                    "symbol": symbol,
                    "expiry_month": expiry.replace(day=1),
                    "expiry_date": None,
                    "option_type": kind,
                    "strike": 4000.0,
                    "multiplier": 100.0,
                    "tick_size": 0.2,
                }
            )
            last = expiry - timedelta(days=1) if code == "2404" else expiry
            for day in days:
                if day <= last:
                    options.append(
                        {
                            "symbol": symbol,
                            "trade_date": day,
                            "settle": 25.0 if day == last else 20.0,
                        }
                    )
        for day in days:
            if day <= expiry:
                futures.append({"symbol": f"IF{code}.CFE", "trade_date": day, "settle": 4010.0})
    frames = {
        "option_contracts": contracts,
        "option_bars": options,
        "futures_bars": futures,
        "index_bars": [{"symbol": "000300.SH", "trade_date": day, "close": 4000.0} for day in days],
    }
    pins = {}
    for name, rows in frames.items():
        root = tmp_path / ("index_bars-20231101" if name == "index_bars" else name)
        root.mkdir()
        record = make_revision(root, name, {"data.parquet": rows}, window=None)
        pins[name] = Pin(
            revision_id=record.revision_id, window=None, content_digest=record.content_digest
        )
    manifest = Manifest(
        inputs=pins,
        economic_conventions={
            "entry": "settle twenty trading days before expiry",
            "expiry": "expiry-day option settle",
            "underlying": "matching IF futures settle on expiry day",
            "costs": "no fees or margin",
        },
        vectorbt_version="none",
        seed=42,
        window="2024..2025",
        experiment_id="replication_diagnostic",
    )
    path = tmp_path / "manifest.json"
    path.write_text(manifest.model_dump_json())
    monkeypatch.setenv("JOSEPH_PILOT_REVISION_ROOT", str(tmp_path))
    monkeypatch.setenv("PILOT_MANIFEST_PATH", str(path))
    manifest.economic_conventions["costs"] = "fees included"
    path.write_text(manifest.model_dump_json())
    with pytest.raises(CellExecutionError, match="economic conventions"):
        NotebookClient(
            nbformat.read(NOTEBOOK, as_version=4), timeout=180, kernel_name="python3"
        ).execute()
    manifest.economic_conventions["costs"] = "no fees or margin"
    path.write_text(manifest.model_dump_json())
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    NotebookClient(notebook, timeout=180, kernel_name="python3").execute()
    text = "".join(
        output.get("text", "")
        for cell in notebook.cells
        for output in cell.get("outputs", [])
        if output.output_type == "stream"
    )
    result = json.loads(text.strip().splitlines()[-1])
    rows = result["rows"]
    february = next(row for row in rows if row["expiry"] == "2024-02-19")
    assert february["third_friday"] == "2024-02-16"
    assert february["option_last"] == february["future_last"] == february["expiry"]
    assert len(rows) == 12
    assert {row["expiry"] for row in rows} == {"2024-01-19", "2024-02-19", "2024-03-15"}
    assert all(
        sum(row["expiry"] == expiry for row in rows) == 4
        for expiry in {row["expiry"] for row in rows}
    )
    for row in rows:
        sign = 1 if row["position"].startswith("Long") else -1
        intrinsic = (
            max(row["if_settle"] - row["K"], 0)
            if "call" in row["position"]
            else max(row["K"] - row["if_settle"], 0)
        )
        assert row["parity_pnl"] == pytest.approx(
            sign * (intrinsic - row["entry_settle"]) * row["multiplier"]
        )
        assert row["realized_pnl"] == pytest.approx(
            sign * (row["expiry_settle"] - row["entry_settle"]) * row["multiplier"]
        )
    manifest.inputs["option_bars"] = pins["option_bars"].model_copy(
        update={"calendar_unverified": {"start": "2023-12-01", "end": "2024-02-19"}}
    )
    path.write_text(manifest.model_dump_json())
    with pytest.raises(CellExecutionError, match="unverified calendar prefix"):
        NotebookClient(
            nbformat.read(NOTEBOOK, as_version=4), timeout=180, kernel_name="python3"
        ).execute()
    dropped = result["dropped"]
    assert any(
        item["month"] == "2024-04"
        and item["option_last"] == "2024-04-18"
        and item["future_last"] == "2024-04-19"
        for item in dropped
    )
