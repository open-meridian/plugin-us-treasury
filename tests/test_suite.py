"""The data suite (meridian.suites) at contract v27, each case Treasury's
files present mapped to the plugin's own conversion of Treasury's recorded
answers: the rates slice's cases as spec/a-public-rates-and-filings-data-
plugin §6 lists them, for this plugin's own datasets.

Treasury publishes curves: a par yield a tenor, nominal and real, and a
bill's discount rate and coupon equivalent a tenor. Presented:

- `a-curve-for-a-date`: February 2025's par curve, its tenor set changed
  on 18 February, when Treasury first published the 1.5-month point;
- `a-tenor-not-published`: 14 February 2025's par curve, before that point,
  recorded without it -- no row, never a zero;
- `two-conventions-one-tenor`: the bill rates, each tenor's discount rate
  and coupon equivalent;
- `a-same-day-revision`: a value Treasury corrects, read again within the
  current months, the same row's next version;
- `an-asset-that-does-not-resolve`, the wants, the licences, and the cases
  the SDK answers.

A case about what Treasury never states (`about`) is not presented, with
why: every case a rates-only plugin never presents, as the SDK names them
(`meridian.roles.data.testing.RATES_NOT_PRESENTED`, ruling 538) -- prices
(`an-exact-price` and `a-want-recorded-against` among them, about closes
from ruling 537), trades, quotes, outcomes, a stream's liveness, and the
feed delay, about `latency` until contract v28 (ruling 518); then
Treasury's own: a reference rate's fixing and an index level (the NY Fed's
and the ECB's), a single-point series of another source's curve (FRED's),
settlement dates, and `reads-a-calendar`, since its datasets declare no
calendar until one of the US government securities market is curated (the
spec's Q15).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles.data.testing import RATES_NOT_PRESENTED
from meridian.suites import ANSWERED_BY_SDK, Recorder, run, suite

from us_treasury.curves import BILLS, PAR
from us_treasury.feed import Feed
from us_treasury.raw import RawStore
from us_treasury.treasury import month_path

from conftest import AT, INSTANCE, RECORDS, Corrected, Recorded, answering, want

#: The rates cases Treasury never presents, and the work it never does,
#: each with why.
TREASURY_NEVER = {
    "a-rate-fixing": "Treasury publishes curves, no reference rate's daily fixing",
    "an-index-level": "Treasury publishes no index level",
    "a-curve-point-from-another-source": (
        "Treasury publishes whole curves, never a single-point series; FRED's DGS10 and the "
        "Board's H.15 record their points against this plugin's curve records"
    ),
    "reads-a-calendar": (
        "its datasets declare no calendar until one of the US government securities market "
        "is curated (the spec's Q15); it expects Monday to Friday"
    ),
    "asks-for-a-settlement-date": (
        "records each day's rates as published; never computes a settlement date"
    ),
}
NOT_PRESENTED = {**RATES_NOT_PRESENTED, **TREASURY_NEVER}


def producers(tmp: Path) -> dict[str, Callable[[Recorder], Awaitable[None]]]:
    def work(recorder: Recorder, source: Any = None) -> Feed:
        return Feed(recorder, source or Recorded(), RawStore(tmp), now=lambda: AT)

    async def a_month(recorder: Recorder, key: str, month: datetime) -> None:
        answering(recorder)
        feed = work(recorder)
        curve = PAR if key == "ust_par" else BILLS
        read, _, raw = await feed.read(curve, month_path(curve.feed_type, month.date()))
        await feed.record(curve, read, raw)

    async def a_curve_for_a_date(recorder: Recorder) -> None:
        await a_month(recorder, "ust_par", datetime(2025, 2, 1, tzinfo=UTC))
        tenors = {
            r.meta.business_date: len([x for x in recorder.on("RecordRates")[0].rates
                                       if x.meta.business_date == r.meta.business_date])
            for r in recorder.on("RecordRates")[0].rates
        }  # fmt: skip
        assert tenors["2025-02-14"] == 13 and tenors["2025-02-18"] == 14

    async def a_tenor_not_published(recorder: Recorder) -> None:
        answering(recorder)
        feed = work(recorder)
        read, _, raw = await feed.read(PAR, month_path(PAR.feed_type, datetime(2025, 2, 14).date()))
        await feed.record(PAR, read, raw, days=[datetime(2025, 2, 14).date()])

    async def two_conventions(recorder: Recorder) -> None:
        await a_month(recorder, "ust_bills", datetime(2026, 10, 1, tzinfo=UTC))

    async def revised(recorder: Recorder) -> None:
        answering(recorder)
        feed = work(recorder, Corrected())
        read, _, raw = await feed.read(PAR, month_path(PAR.feed_type, AT.date()))
        day = [datetime(2026, 10, 22).date()]
        await feed.record(PAR, read, raw, days=day)
        read, _, raw = await feed.read(PAR, month_path(PAR.feed_type, AT.date()))
        # The corrected tenor alone, as a reader's want for it asks.
        rows = feed.rows(PAR, RECORDS["ust_par"], read, raw, day)
        tens = [r for r in rows if r.meta is not None and "10Y" in r.meta.row_key]
        await feed.rates.record(PAR.key, tens)
        first, second = recorder.on("RecordRates")
        [again] = second.rates
        [before] = [r for r in first.rates if r.meta.row_key == again.meta.row_key]
        assert before.value != again.value

    async def two_records(recorder: Recorder) -> None:
        recorder.answer(
            "ResolveIdentifier",
            lambda _: ops.ResolveIdentifierResult(
                found=False, miss_reason=ops.MISS_REASON_AMBIGUOUS
            ),
        )
        await work(recorder).check()

    def wanted(message: Any) -> Callable[[Recorder], Awaitable[None]]:
        async def produce(recorder: Recorder) -> None:
            answering(recorder)
            feed = work(recorder)
            recorder.answer("ObservationsWanted", lambda _: message)
            await recorder.receive(observations_wanted=feed.on_want)

        return produce

    async def withdrawn(recorder: Recorder) -> None:
        answering(recorder)
        feed = work(recorder)
        recorder.answer(
            "WantWithdrawn",
            lambda _: ops.WantWithdrawnEvent(want_id="w-standing", dataset=f"{INSTANCE}:ust_par"),
        )
        await recorder.receive(want_withdrawn=feed.on_withdrawn)

    async def licences(recorder: Recorder) -> None:
        dataset = f"{INSTANCE}:ust_par"
        recorder.answer(
            "ListDatasets",
            lambda _: ops.ListDatasetsResult(licences=[ops.DatasetLicence(dataset=dataset)]),
        )
        feed = work(recorder)
        await feed.wants.read_licences()
        assert feed.wants.licensed == {dataset}

    declined: Heard = want("w-2", ["INS-SOFR"], day="2026-10-22")  # type: ignore[type-arg]
    return {
        "a-curve-for-a-date": a_curve_for_a_date,
        "a-tenor-not-published": a_tenor_not_published,
        "two-conventions-one-tenor": two_conventions,
        "a-same-day-revision": revised,
        "an-asset-that-does-not-resolve": two_records,
        "a-subject-declined": wanted(declined.message),
        "a-standing-want-withdrawn": withdrawn,
        "reads-its-datasets-licences": licences,
    }


def test_the_data_suite_passes(tmp_path: Path) -> None:
    report = run("data", producers(tmp_path), not_presented=NOT_PRESENTED, instance_id=INSTANCE)
    assert report.passed, report.failures
    assert sorted(report.not_presented) == sorted(NOT_PRESENTED)
    assert report.answered_by_sdk == list(ANSWERED_BY_SDK)
    presented = {
        "a-curve-for-a-date", "a-tenor-not-published", "two-conventions-one-tenor",
        "a-same-day-revision", "an-asset-that-does-not-resolve", "a-subject-declined",
        "a-standing-want-withdrawn", "reads-its-datasets-licences",
    }  # fmt: skip
    assert set(report.passed_cases) == presented | set(ANSWERED_BY_SDK)


def test_the_two_price_cases_are_about_closes() -> None:
    # Ruling 537: no longer required of a plugin recording no prices.
    assert NOT_PRESENTED["an-exact-price"] == "it records rates, never prices"
    assert NOT_PRESENTED["a-want-recorded-against"] == "it records rates, never prices"


def test_every_latency_case_waits_for_contract_v28() -> None:
    latency = [c.name for c in suite("data").cases if c.about == "latency"]
    assert latency and all(
        NOT_PRESENTED[n] == "core receives ReportLatency from contract v28, ruling 515"
        for n in latency
    )


def test_the_lake_query_is_not_presented_for_it_records_no_trades() -> None:
    assert NOT_PRESENTED["queries-the-lake-within-bounds"] == "it records rates, never trades"
