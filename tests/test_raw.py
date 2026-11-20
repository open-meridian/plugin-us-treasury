"""Treasury's answers kept as received, and the history read noted."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from meridian import edge

from us_treasury.__main__ import Lake
from us_treasury.raw import RawStore, answer_name
from us_treasury.treasury import Fetched, month_path, source, year_path

AT = datetime(2026, 10, 23, 16, 0, tzinfo=UTC)


def test_an_answer_is_kept_before_it_is_read(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    path = month_path("daily_treasury_yield_curve", AT.date())
    key = store.keep(Fetched(path, 200, b'Date,"1 Mo"\n10/22/2026,4.11', AT, "Fri, 23 Oct 2026"))
    assert key == "responses/2026-10/20261023T160000000000Z-par-202610.json.gz"
    kept = json.loads(gzip.decompress((tmp_path / key).read_bytes()))
    assert kept["status"] == 200 and kept["body"].endswith("4.11")
    assert kept["url"].startswith("https://home.treasury.gov/")
    assert store.read(key) == kept and store.keys() == [key]
    assert store.read("../outside") is None
    [unit] = store.units()
    assert unit.unit == "responses/2026-10" and unit.records == 1


def test_names_say_which_file_and_period() -> None:
    assert answer_name(year_path("daily_treasury_bill_rates", 2002)) == "bills-2002"
    assert answer_name("/elsewhere") == "answer-none"


def test_the_history_read_is_noted(tmp_path: Path) -> None:
    store = RawStore(tmp_path)
    assert store.history() == {}
    store.note_year("ust_par", 1990)
    store.note_year("ust_par", 1991)
    store.note_year("ust_bills", 2002)
    assert RawStore(tmp_path).history() == {"ust_par": [1990, 1991], "ust_bills": [2002]}
    (tmp_path / "history.json").write_text("not json")
    assert RawStore(tmp_path).history() == {}


async def test_storage_read_once_registered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On an instance run as shards, storage is read once the plugin has
    registered, from the class's on_start: its shard's own folder, read
    afresh when it registers again (open-meridian 0.37.0). Built before
    Register, as `main()` builds it, nothing is read: read then, it raises."""
    monkeypatch.setenv("MERIDIAN_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("MERIDIAN_PLUGIN_SHARDS", "2")
    monkeypatch.setattr(edge, "_serving", None)
    lake = Lake(source(False), RawStore())
    monkeypatch.setattr(edge, "_serving", (1, 2))
    await lake.on_start()
    assert lake.raw.granted
    assert lake.raw.root == tmp_path / "shard-1"
    await lake.on_stop()
    monkeypatch.setattr(edge, "_serving", (0, 2))
    await lake.on_start()
    assert lake.raw.root == tmp_path / "shard-0"
