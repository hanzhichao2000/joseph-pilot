import ast
import json
import sys
from datetime import date
from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient
from test_revision import make_revision

from joseph_pilot.manifest import Manifest, Pin

NOTEBOOK = Path(
    "notebooks/book-examples/natenberg-option-volatility-and-pricing/chapter-04-expiration-pnl/basic-positions-io.ipynb"
)


def test_notebook_import_subset():
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    allowed = {"pandas", "pyarrow", "matplotlib", "numpy"} | sys.stdlib_module_names
    for cell in notebook.cells:
        if cell.cell_type != "code":
            continue
        for node in ast.walk(ast.parse(cell.source)):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                assert module in {
                    "joseph_pilot.manifest",
                    "joseph_pilot.revision",
                    "joseph_pilot.runtime",
                } or (module.split(".")[0] in allowed), module


def test_notebook_executes_reproducibly(tmp_path, monkeypatch):
    symbols = ["IO2611C4000.CFE", "IO2611P4000.CFE"]
    expiry = date(2026, 11, 20)
    observed = date(2026, 11, 19)
    frames = {
        "option_contracts": [
            {
                "symbol": s,
                "list_date": date(2026, 1, 1),
                "expiry_date": expiry,
                "expiry_month": date(2026, 11, 1),
                "option_type": typ,
                "strike": 4000.0,
                "multiplier": 100.0,
            }
            for s, typ in zip(symbols, ["C", "P"], strict=True)
        ],
        "option_bars": [
            {"symbol": s, "trade_date": observed, "settle": price}
            for s, price in zip(symbols, [9.2, 57.6], strict=True)
        ],
        "index_bars": [{"symbol": "000300.SH", "trade_date": observed, "close": 3984.84}],
    }
    pins = {}
    for capability, rows in frames.items():
        root = tmp_path / capability
        root.mkdir()
        record = make_revision(root, capability, {"data.parquet": rows}, window=None)
        pins[capability] = Pin(
            revision_id=record.revision_id, window=None, content_digest=record.content_digest
        )
    pins["option_bars"] = Pin.model_validate(
        {
            **pins["option_bars"].model_dump(),
            "calendar_unverified": {"start": "2023-11-01", "end": "2023-11-25"},
        }
    )
    manifest = Manifest(
        inputs=pins,
        economic_conventions={"premium": "settle"},
        vectorbt_version="0.28.1",
        seed=42,
        window="IO2611C4000.CFE, IO2611P4000.CFE; 2026-11",
        experiment_id="replication_diagnostic",
    )
    path = tmp_path / "manifest.json"
    path.write_text(manifest.model_dump_json())
    monkeypatch.delenv("JOSEPH_PILOT_REVISION_ROOT", raising=False)
    config = tmp_path / "config" / "joseph" / ".env"
    config.parent.mkdir(parents=True)
    config.write_text(f"JOSEPH_PILOT_REVISION_ROOT={tmp_path}\n")
    config.chmod(0o600)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("PILOT_MANIFEST_PATH", str(path))
    outputs = []
    for _ in range(2):
        nb = nbformat.read(NOTEBOOK, as_version=4)
        NotebookClient(nb, timeout=180, kernel_name="python3").execute()
        text = "".join(
            o.get("text", "")
            for c in nb.cells
            for o in c.get("outputs", [])
            if o.output_type == "stream"
        )
        assert "2023-11-01" in text and "2023-11-25" in text
        outputs.append(json.loads(text.strip().splitlines()[-1]))
    assert outputs[0] == outputs[1]
    assert outputs[0]["call_break_even"] == 4009.2
    assert outputs[0]["put_break_even"] == 3942.4
    assert outputs[0]["long_call_max_loss"] == pytest.approx(-920.0)
    assert outputs[0]["long_put_max_gain"] == 394240.0
    assert outputs[0]["short_put_max_loss"] == -394240.0
    assert outputs[0]["index_close"] == 3984.84
