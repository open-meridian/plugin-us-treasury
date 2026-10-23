"""The two pages under Manage, and their read tools: what each shows, to
whom, and that a tool answers what its page shows."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from meridian.testing import PageClient

from us_treasury import page as page_module
from us_treasury.page import CONNECTION, DATASETS, figures, hold, pages
from us_treasury.treasury import Fetched, SyntheticTreasury, TreasuryUnreachable

from conftest import BILLS, PAR, REAL, feed, want


@pytest.fixture
def client(tmp_path: Path) -> PageClient:
    work = feed(tmp_path)

    async def run() -> None:
        await work.check()
        await work.history()
        await work.on_want(want("w-0925", [PAR], day="2026-09-25"))
        await work.on_want(want("w-standing", [PAR], standing=True))

    asyncio.run(run())
    hold(work)
    return PageClient(pages)


def test_each_page_is_managed_alone(client: PageClient) -> None:
    served = {(r.page.path, r.level): r.response.status for r in client.every_page()}
    assert served == {
        (CONNECTION, "admin"): 200,
        (CONNECTION, "write"): 403,
        (CONNECTION, "read"): 403,
        (DATASETS, "admin"): 200,
        (DATASETS, "write"): 403,
        (DATASETS, "read"): 403,
    }
    # No rate on any page: Treasury's figures are the reading roles' to show.
    client.assert_no_account_data("4.96", "5.32", "2.64", "4.14")


def test_connection_says_how_treasury_is_reached(client: PageClient) -> None:
    text = client.get(CONNECTION, "admin").text
    # The data role's sections, in its order, Treasury's Sources a row of
    # "Limits and use" (one screen beside the role's four sections).
    assert text.index("<h2>Key</h2>") < text.index("<h2>Limits and use</h2>")
    assert text.index("<h2>Limits and use</h2>") < text.index('<th scope="row">Sources</th>')
    assert text.index('<th scope="row">Sources</th>') < text.index("<h2>Stream</h2>")
    assert "3 of 3 answering, latest Thu 22 Oct" in text
    assert 'state="ok"' in text and "Sample data" in text
    assert "No key needed" in text and "Does not stream" in text
    assert text.count("<dt data-source=") == 3
    assert "Thu 22 Oct" in text  # the latest day published
    assert "Fri 23 Oct" in text  # the next one expected, Monday to Friday
    assert "read back to 1990" in text and "read back to 2003" in text
    assert "1M, 6W, 2M, 3M" in text and "4W, 6W, 8W, 13W" in text
    assert "/.meridian/ui/" in text


def test_datasets_lists_each_dataset_and_curve(client: PageClient) -> None:
    text = client.get(DATASETS, "admin").text
    assert text.index("<h2>Served</h2>") < text.index("<h2>Wants</h2>")
    # Records and Lag are columns of Served: one dataset is one curve.
    assert text.index("<h2>Served</h2>") < text.index(">Record</th>")
    assert text.index(">Record</th>") < text.index('<th class="wide-only">Lag</th>')
    for key in ("ust_par", "ust_real", "ust_bills"):
        assert f"us-treasury:{key}" in text
    assert "Not licensed yet" in text and "US government work" in text
    assert text.count("<td data-dataset=") == 3
    assert all(record in text for record in (PAR, REAL, BILLS))
    assert "Source: U.S. Department of the Treasury" in text
    assert "Kept current" in text


def test_the_tools_answer_what_the_pages_show(client: PageClient) -> None:
    names = {t.name for t in pages.tools}
    assert names == {"read_connection", "read_datasets"}
    connection = client.call_tool("read_connection")
    assert connection.outcome == "unchanged", connection.json
    data = connection.data
    assert data["mode"] == "Sample data" and data["credentials"] == []
    assert data["sessions"] is None
    sources = {s["dataset"]: s for s in data["sources"]}
    assert set(sources) == {"us-treasury:ust_par", "us-treasury:ust_real", "us-treasury:ust_bills"}
    par = sources["us-treasury:ust_par"]
    assert par["last_release"] == "2026-10-22" and par["next_expected"] == "2026-10-23"
    assert par["history_from"] == 1990 and par["history_done"] is True
    assert par["tenors"][:3] == ["1M", "6W", "2M"]
    datasets = client.call_tool("read_datasets")
    assert datasets.outcome == "unchanged"
    read = datasets.data
    assert [s["dataset"] for s in read["served"]] == list(sources)
    assert all(s["arrives"] == "push, pull" for s in read["served"])
    assert read["served"][0]["recorded"] >= 36 * 14 and read["served"][0]["licensed"] is False
    records = {r["dataset"]: r for r in read["records"]}
    assert records["us-treasury:ust_bills"]["instrument_id"] == BILLS
    assert records["us-treasury:ust_par"]["code"] == "Daily Treasury Par Yield Curve Rates"
    page = client.get(DATASETS, "admin").text
    assert all(r["instrument_id"] in page for r in read["records"])
    assert read["wants"][0]["want_id"] == "w-standing"
    assert read["wants"][0]["state"] == "Kept current"
    assert [lag["dataset"] for lag in read["lag"]] == list(sources)


def test_before_the_first_check() -> None:
    page_module._held.clear()
    text = PageClient(pages).get(CONNECTION, "admin").text
    assert "Checking Treasury" in text and "Not read yet" in text
    empty = PageClient(pages).get(DATASETS, "admin").text
    assert "No wants yet" in empty and "not yet resolved" in empty


def test_treasury_not_reached(tmp_path: Path) -> None:
    class Down(SyntheticTreasury):
        async def get(self, path: str) -> Fetched:
            raise TreasuryUnreachable("https://home.treasury.gov: ConnectionRefusedError")

    work = feed(tmp_path, source=Down())
    asyncio.run(work.check())
    hold(work)
    text = PageClient(pages).get(CONNECTION, "admin").text
    assert 'state="error"' in text and "Not answering" in text
    assert "ConnectionRefusedError" in text


def test_a_licensed_dataset_is_said_so(client: PageClient) -> None:
    page_module._held["feed"].wants.licensed = frozenset({"us-treasury:ust_par"})
    served = client.call_tool("read_datasets").data["served"]
    assert [s["licensed"] for s in served] == [True, False, False]


def test_the_figures_are_the_data_roles_in_its_order(client: PageClient) -> None:
    work = page_module._held["feed"]
    said = figures(work.status, work)
    assert [f.label for f in said] == [
        "Connection",
        "Entitled at the vendor",
        "Stream",
        "Last recorded",
    ]
    assert said[0].value == "Sample data" and said[1].value == "3 of 3 datasets"
    assert said[2].value == "Does not stream"
