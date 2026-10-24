"""Treasury's files read as curves: tenors as Treasury labels them, kinds
and conventions as it states them, values as written, and what is not
published or not read left out."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

import pytest

from us_treasury.curves import BILLS, PAR, REAL, NotRates, column, parse
from us_treasury.treasury import month_path, year_path

from conftest import Recorded


def answer(path: str) -> str:
    return asyncio.run(Recorded().get(path)).text


def test_the_par_curve_as_treasury_labels_it() -> None:
    read = parse(answer(month_path(PAR.feed_type, date(2026, 10, 1))), PAR)
    assert [c.tenor for c in read.columns] == [
        "1M", "6W", "2M", "3M", "4M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y",
    ]  # fmt: skip
    assert {c.kind for c in read.columns} == {"par_yield"}
    assert {(c.convention.day_count, c.convention.compounding) for c in read.columns} == {
        ("act_act", "compounded")
    }
    latest = read.days[-1]
    assert latest.day == date(2026, 10, 22)
    ten = next(p for p in latest.points if p.column.tenor == "10Y")
    assert ten.text == "4.96" and ten.value == Decimal("4.96")
    assert read.days[0].day < latest.day and not read.unread


def test_the_real_curve_reads_five_tenors() -> None:
    read = parse(answer(month_path(REAL.feed_type, date(2026, 9, 1))), REAL)
    assert [c.tenor for c in read.columns] == ["5Y", "7Y", "10Y", "20Y", "30Y"]


def test_a_bills_two_conventions_for_one_tenor() -> None:
    read = parse(answer(month_path(BILLS.feed_type, date(2026, 10, 1))), BILLS)
    by = {(c.tenor, c.kind): c.convention for c in read.columns}
    assert sorted({t for t, _ in by}) == sorted(["4W", "6W", "8W", "13W", "17W", "26W", "52W"])
    discount = by[("13W", "discount")]
    assert (discount.day_count, discount.compounding) == ("act_360", "discount")
    simple = by[("26W", "coupon_equivalent")]
    assert (simple.day_count, simple.compounding) == ("act_act", "simple")
    year = by[("52W", "coupon_equivalent")]
    assert (year.day_count, year.compounding, year.periods_per_year) == ("act_act", "compounded", 2)


def test_the_tenor_set_changes_with_the_six_week_bill() -> None:
    # Treasury first published the 1.5-month point on 18 February 2025.
    read = parse(answer(month_path(PAR.feed_type, date(2025, 2, 1))), PAR)
    tenors = {d.day: [p.column.tenor for p in d.points] for d in read.days}
    assert "6W" not in tenors[date(2025, 2, 14)]
    assert "6W" in tenors[date(2025, 2, 18)]
    assert len(tenors[date(2025, 2, 14)]) == 13 and len(tenors[date(2025, 2, 18)]) == 14


def test_a_tenor_not_published_is_no_point() -> None:
    # In 2002 Treasury states the 52-week bill on a few days of February
    # alone: its columns are empty on every other day, never zero.
    read = parse(answer(year_path(BILLS.feed_type, 2002)), BILLS)
    tenors = {d.day: {p.column.tenor for p in d.points} for d in read.days}
    assert "52W" not in tenors[date(2002, 1, 2)] and len(tenors[date(2002, 1, 2)]) == 3
    assert "52W" in tenors[date(2002, 2, 5)]
    assert sum("52W" in held for held in tenors.values()) < 10
    assert all(p.text != "0" for d in read.days for p in d.points)


def test_what_does_not_read_is_said_not_recorded() -> None:
    text = 'Date,"1 Mo","9 Fortnights","2 Mo"\n10/22/2026,4.11,1.00,N/A\n'
    read = parse(text, PAR)
    assert [p.column.tenor for p in read.days[0].points] == ["1M"]
    assert read.unread == ["the column '9 Fortnights'", "2026-10-22 2 Mo: 'N/A'"]


def test_an_empty_answer_is_a_period_with_no_rate() -> None:
    assert parse("", PAR).days == []
    assert parse(answer(year_path(PAR.feed_type, 1985)), PAR).days == []


def test_an_answer_that_is_no_rates_file_is_refused() -> None:
    with pytest.raises(NotRates):
        parse("<html>Service unavailable</html>\n", PAR)


def test_a_column_treasury_might_add_reads_by_its_label() -> None:
    held = column(BILLS, "39 WEEKS COUPON EQUIVALENT")
    assert held is not None and held.tenor == "39W"
    assert held.convention.compounding == "compounded"
    assert column(PAR, "1.5 Month") is not None and column(PAR, "Date") is None
