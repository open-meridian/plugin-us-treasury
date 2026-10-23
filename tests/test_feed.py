"""The plugin's work on its typed operations: the current months pushed,
the history read back, the curves' records resolved or reported, wants
recorded against or declined."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from meridian.operations import as_decimal
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles.data import rates
from meridian.suites import Recorder

from us_treasury.feed import Feed, day_start_ns, next_weekday
from us_treasury.raw import RawStore
from us_treasury.treasury import Fetched, SyntheticTreasury, TreasuryUnreachable

from conftest import (
    AT,
    BILLS,
    DAYS,
    PAR,
    POINTS,
    REAL,
    Corrected,
    Recorded,
    feed,
    lake,
    want,
)


def rows(plugin: Recorder) -> list[ops.Rate]:
    return [r for batch in plugin.on("RecordRates") for r in batch.rates]


async def test_the_current_months_pushed_whole(tmp_path: Path) -> None:
    work = feed(tmp_path)
    done = await work.check()
    assert {k: o.recorded for k, o in done.items()} == {k: DAYS * n for k, n in POINTS.items()}
    sent = rows(work.plugin)
    assert all(not b.want_id for b in work.plugin.on("RecordRates"))
    assert {r.meta.subjects[0].entity_id for r in sent} == {PAR, REAL, BILLS}
    ten = next(
        r for r in sent
        if r.meta.subjects[0].entity_id == PAR and r.meta.business_date == "2026-10-22"
        and rates.tenor_label(r.tenor) == "10Y"
    )  # fmt: skip
    assert str(as_decimal(ten.value.value)) == "4.96" and ten.value.unit == ops.VALUE_UNIT_PERCENT
    assert ten.kind == ops.RATE_KIND_PAR_YIELD
    assert ten.convention.day_count == ops.DAY_COUNT_ACT_ACT
    assert ten.convention.periods_per_year == 2
    assert ten.meta.valid_from_ns == day_start_ns(date(2026, 10, 22))
    assert ten.meta.source.dataset == "us-treasury:ust_par"
    # Treasury states no publication time: none is said.
    assert not ten.meta.source_times
    # Every row names the answer it was read from, kept first.
    kept = work.raw.keys()
    assert {r.meta.raw.key for r in sent} <= set(kept)
    assert all(work.raw.read(k) for k in kept)


async def test_every_value_is_exact(tmp_path: Path) -> None:
    work = feed(tmp_path)
    await work.check()
    values = [str(as_decimal(r.value.value)) for r in rows(work.plugin)]
    assert all("e" not in v.lower() and len(v.split(".")[-1]) == 2 for v in values)


async def test_a_bills_tenor_is_two_rows(tmp_path: Path) -> None:
    work = feed(tmp_path)
    await work.check()
    day = [
        r for r in rows(work.plugin)
        if r.meta.subjects[0].entity_id == BILLS and r.meta.business_date == "2026-10-22"
        and rates.tenor_label(r.tenor) == "13W"
    ]  # fmt: skip
    assert sorted(ops.RateKind.Name(r.kind) for r in day) == [
        "RATE_KIND_COUPON_EQUIVALENT",
        "RATE_KIND_DISCOUNT",
    ]
    assert len({r.meta.row_key for r in day}) == 2


async def test_a_read_unchanged_is_not_recorded_again(tmp_path: Path) -> None:
    work = feed(tmp_path)
    await work.check()
    again = await work.check()
    assert all(o.sent == 0 for o in again.values())
    # Each curve's two current months, recorded once.
    assert len(work.plugin.on("RecordRates")) == 6


async def test_a_correction_is_the_same_rows_next_version(tmp_path: Path) -> None:
    work = feed(tmp_path, source=Corrected())
    await work.check()
    done = await work.check()
    assert done["ust_par"].restated == 1 and done["ust_par"].recorded == 0
    assert done["ust_par"].unchanged == 15 * POINTS["ust_par"] - 1


async def test_a_record_not_held_is_reported_and_its_rows_wait(tmp_path: Path) -> None:
    plugin = lake(missing="ust_real")
    held = plugin.instruments

    def resolve(params: ops.ResolveIdentifierParams) -> ops.ResolveIdentifierResult:
        if params.identifiers[0].value == "Daily Treasury Par Real Yield Curve Rates":
            return ops.ResolveIdentifierResult(found=False, miss_reason=ops.MISS_REASON_NOT_FOUND)
        return held.resolve(params)  # type: ignore[no-any-return]

    plugin.answer("ResolveIdentifier", resolve)
    work = feed(tmp_path, plugin=plugin)
    done = await work.check()
    assert done["ust_real"].sent == 0 and done["ust_par"].recorded
    [missed] = work.plugin.on("ReportMissingInstrument")
    assert missed.identifiers[0].value == "Daily Treasury Par Real Yield Curve Rates"
    assert missed.identifiers[0].source == "ustreasury"
    assert work.status.sources["ust_real"].miss
    # Once a day: the next check asks again, and reports nothing new.
    await work.check()
    assert len(work.plugin.on("ReportMissingInstrument")) == 1


async def test_the_history_read_back_to_each_first_year(tmp_path: Path) -> None:
    work = feed(tmp_path)
    await work.check()
    years = await work.history()
    # 1990 to 2026, 2003 to 2026 and 2002 to 2026.
    assert years == 37 + 24 + 25
    assert all(s.history_done for s in work.status.sources.values())
    assert work.status.sources["ust_par"].history_from == 1990
    # 2002's bill rates are recorded from the tests' answer.
    bills = {r.meta.business_date for r in rows(work.plugin) if r.meta.business_date < "2003"}
    assert "2002-12-31" in bills
    # A new process on the same storage reads only the current year again.
    later = Feed(work.plugin, Recorded(), RawStore(tmp_path), now=lambda: AT)
    assert await later.history() == 3


async def test_a_history_that_fails_stops_and_reads_on_later(tmp_path: Path) -> None:
    class Fails(Recorded):
        async def get(self, path: str) -> Fetched:
            if "/2010/" in path:
                raise TreasuryUnreachable("https://home.treasury.gov: TimeoutError")
            return await super().get(path)

    work = feed(tmp_path, source=Fails())
    await work.history()
    par = work.status.sources["ust_par"]
    assert not par.history_done and par.history_from == 2011
    assert "2010" in par.history_error
    work.source = Recorded()
    await work.history()
    assert work.status.sources["ust_par"].history_done


async def test_treasury_not_reached_is_said(tmp_path: Path) -> None:
    class Down(SyntheticTreasury):
        async def get(self, path: str) -> Fetched:
            raise TreasuryUnreachable("https://home.treasury.gov: ConnectionRefusedError")

    work = feed(tmp_path, source=Down())
    done = await work.check()
    assert all(o.sent == 0 for o in done.values())
    assert "ConnectionRefusedError" in work.status.error
    assert not work.plugin.on("RecordRates")


async def test_a_day_wanted_is_recorded_against_the_want(tmp_path: Path) -> None:
    work = feed(tmp_path)
    await work.on_want(want("w-1", [PAR], day="2025-02-18"))
    [batch] = work.plugin.on("RecordRates")
    assert batch.want_id == "w-1" and len(batch.rates) == 14
    assert {r.meta.business_date for r in batch.rates} == {"2025-02-18"}
    assert not work.plugin.on("DeclineWant")


async def test_a_range_wanted_reads_each_year(tmp_path: Path) -> None:
    work = feed(tmp_path)
    start = int(datetime(2025, 2, 13, 5, tzinfo=UTC).timestamp()) * 10**9
    until = int(datetime(2025, 2, 19, 5, tzinfo=UTC).timestamp()) * 10**9
    await work.on_want(want("w-r", [PAR], valid_from_ns=start, valid_until_ns=until))
    days = {r.meta.business_date for r in rows(work.plugin)}
    assert days == {"2025-02-13", "2025-02-14", "2025-02-18"}


async def test_wants_declined_with_why(tmp_path: Path) -> None:
    work = feed(tmp_path)
    await work.on_want(want("w-weekend", [PAR], day="2026-10-17"))
    await work.on_want(want("w-old", [PAR], day="1985-06-03"))
    await work.on_want(want("w-other", ["INS-SOFR"], day="2026-10-22"))
    await work.on_want(want("w-type", [PAR], day="2026-10-22", data_type="meridian.v1.Price"))
    await work.on_want(want("w-future", [PAR], day="2026-12-01"))
    declined = {
        d.want_id: ops.UnansweredReason.Name(d.reason) for d in work.plugin.on("DeclineWant")
    }
    assert declined == {
        "w-weekend": "UNANSWERED_REASON_SOURCE_SILENT",
        "w-old": "UNANSWERED_REASON_BEYOND_HISTORY",
        "w-other": "UNANSWERED_REASON_NOT_COVERED",
        "w-type": "UNANSWERED_REASON_NOT_COVERED",
        "w-future": "UNANSWERED_REASON_SOURCE_SILENT",
    }
    assert not work.plugin.on("RecordRates")


async def test_a_standing_want_kept_until_withdrawn(tmp_path: Path) -> None:
    from meridian.receive import Heard

    work = feed(tmp_path)
    await work.on_want(want("w-s", [PAR], standing=True))
    assert "w-s" in work.wants.standing
    # The latest day, read first: no want had come before the push.
    assert {r.meta.business_date for r in work.plugin.on("RecordRates")[-1].rates} == {"2026-10-22"}
    await work.on_withdrawn(
        Heard(row="WantWithdrawn", message=ops.WantWithdrawnEvent(want_id="w-s"))
    )
    assert "w-s" not in work.wants.standing


async def test_a_day_first_read_while_watching_has_its_lag(tmp_path: Path) -> None:
    class Later(SyntheticTreasury):
        """October's par curve without 22 October, then with it."""

        def __init__(self) -> None:
            super().__init__(lambda: AT)
            self.reads = 0

        async def get(self, path: str) -> Fetched:
            got = await super().get(path)
            if "daily_treasury_yield_curve" in path and "202610" in path:
                self.reads += 1
                if self.reads == 1:
                    lines = [x for x in got.text.splitlines() if not x.startswith("10/22/2026")]
                    return Fetched(path, 200, "\n".join(lines).encode(), got.fetched_at)
            return got

    work = feed(tmp_path, source=Later())
    await work.check()
    assert work.status.sources["ust_par"].lags == []
    await work.check()
    # Noon in New York on 23 October: 36 hours after 22 October began.
    assert work.status.sources["ust_par"].lags == [36 * 3600]
    assert work.status.sources["ust_real"].lags == []


def test_the_next_day_expected_is_a_weekday() -> None:
    assert next_weekday(date(2026, 10, 22)) == date(2026, 10, 23)
    assert next_weekday(date(2026, 10, 23)) == date(2026, 10, 26)
