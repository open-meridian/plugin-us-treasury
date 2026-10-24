"""Treasury's three files as curves: what each is, and its CSV read into
points, each a tenor, a kind, a convention and the value as written.

**A curve is one record and its points are rows** (the spec's §2,
research-kinds Q4): the nominal par yield curve, the real par yield curve
and the bill rates are each one platform record, the seeded referential
records named by Treasury's own titles under the source `ustreasury`
(`Daily Treasury Par Yield Curve Rates`, `Daily Treasury Par Real Yield
Curve Rates`, `Daily Treasury Bill Rates`). Each row carries its tenor.

**Tenors, as Treasury labels them** (`rates.tenor`): `1 Mo`, `10 Yr`,
`5 YR`, `13 WEEKS`. One is not a whole number of its unit: the par curve's
`1.5 Month`, which Treasury added on 18 February 2025 for the six-week bill
it began issuing, is recorded as six weeks (`6W`), the bill its point is
read from. The bill rates keep Treasury's weeks -- 4, 6, 8, 13, 17, 26 and
52 -- never turned into months.

**Kinds and conventions, as Treasury states them:**

- a par yield, nominal or real: `par_yield`, bond-equivalent, compounded
  semi-annually on an actual/actual basis (`rates.BOND_EQUIVALENT`), as
  Treasury's yield curve methodology states its par yields;
- a bill's bank discount rate: `discount`, actual/360 off the face amount
  (`rates.DISCOUNT`);
- a bill's coupon equivalent: `coupon_equivalent`, on the actual days of
  the year (365, or 366 in a leap year) -- simple for a bill of a half-year
  or less (26 weeks), compounded semi-annually for the 52-week bill, as
  Treasury's formula for a bill of more than a half-year does.

A bill's discount rate and coupon equivalent for one tenor are two rows,
told apart by kind and convention (the spec's §2).

**What a file states is read as written.** Each value is made a `Decimal`
from its text, never a float. A tenor left empty on a day is no row, never
a zero: the tenor sets change over the years (the 20-year was not published
from 1987 to 1993, nor the 30-year from 2002 to 2006, nor the 52-week bill
from 2001 to 2008). A column the plugin does not know, or a value that is
not a number, is not recorded, and is said on the Datasets page.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from meridian.operations import RateConvention
from meridian.roles.data import rates

#: The source every identifier of these records is scoped to: the
#: administrator, as the platform's seed names it.
ADMINISTRATOR = "ustreasury"

#: A bill's coupon equivalent: actual days over the year's, simple up to a
#: half-year, compounded semi-annually beyond it.
COUPON_EQUIVALENT = RateConvention(day_count="act_act", compounding="simple")
COUPON_EQUIVALENT_LONG = rates.BOND_EQUIVALENT
#: The longest bill whose coupon equivalent is simple: a half-year.
HALF_YEAR_WEEKS = 26


@dataclass(frozen=True)
class Curve:
    """One of Treasury's files as a dataset: its key, the file's type in the
    address, the record its rows are about, and the first year it states."""

    key: str
    feed_type: str
    code: str
    title: str
    first_year: int
    bills: bool = False

    @property
    def identifier(self) -> tuple[str, str, str]:
        return ("symbol", self.code, ADMINISTRATOR)

    @property
    def kinds(self) -> tuple[str, ...]:
        """The kinds of rate the file states."""
        return ("discount", "coupon_equivalent") if self.bills else ("par_yield",)


PAR = Curve(
    "ust_par",
    "daily_treasury_yield_curve",
    "Daily Treasury Par Yield Curve Rates",
    "Par yield curve",
    1990,
)
REAL = Curve(
    "ust_real",
    "daily_treasury_real_yield_curve",
    "Daily Treasury Par Real Yield Curve Rates",
    "Real par yield curve",
    2003,
)
BILLS = Curve(
    "ust_bills",
    "daily_treasury_bill_rates",
    "Daily Treasury Bill Rates",
    "Bill rates",
    2002,
    bills=True,
)
CURVES: tuple[Curve, ...] = (PAR, REAL, BILLS)
BY_KEY = {curve.key: curve for curve in CURVES}

_BILL = re.compile(r"(\d+)\s+WEEKS?\s+(BANK DISCOUNT|COUPON EQUIVALENT)", re.IGNORECASE)
_NUMBER = re.compile(r"-?\d+(\.\d+)?")
#: Treasury's one fractional tenor, and the bill it is read from.
_SIX_WEEKS = {"1.5 month", "1.5 mo"}


@dataclass(frozen=True)
class Column:
    """What one of a file's columns states: its tenor, as the wire's label,
    its kind and its convention."""

    header: str
    tenor: str
    kind: str
    convention: RateConvention


@dataclass(frozen=True)
class Point:
    column: Column
    text: str

    @property
    def value(self) -> Decimal:
        return Decimal(self.text)


@dataclass(frozen=True)
class Day:
    day: date
    points: tuple[Point, ...]


@dataclass
class Read:
    """A file's answer as read: each day's points, oldest first, and what
    could not be read -- an unknown column, or a value that is not a number."""

    curve: Curve
    days: list[Day] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)
    unread: list[str] = field(default_factory=list)


class NotRates(Exception):  # noqa: N818 - what the answer was
    """An answer that is not one of Treasury's rates files."""


def column(curve: Curve, header: str) -> Column | None:
    """What a header states for `curve`, or None for one not known."""
    text = header.strip()
    if curve.bills:
        found = _BILL.fullmatch(text)
        if found is None:
            return None
        weeks = int(found.group(1))
        tenor = rates.tenor_label(rates.tenor(f"{weeks} WEEKS"))
        if found.group(2).upper() == "BANK DISCOUNT":
            return Column(text, tenor, "discount", rates.DISCOUNT)
        convention = COUPON_EQUIVALENT if weeks <= HALF_YEAR_WEEKS else COUPON_EQUIVALENT_LONG
        return Column(text, tenor, "coupon_equivalent", convention)
    if text.lower() in _SIX_WEEKS:
        return Column(text, "6W", "par_yield", rates.BOND_EQUIVALENT)
    try:
        held = rates.tenor(text)
    except ValueError:
        return None
    return Column(text, rates.tenor_label(held), "par_yield", rates.BOND_EQUIVALENT)


def parse(text: str, curve: Curve) -> Read:
    """A file's CSV as `Read`: an empty answer is a period with no rate."""
    read = Read(curve)
    if not text.strip():
        return read
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    header, body = rows[0], rows[1:]
    if not header or header[0].strip().lower() != "date":
        raise NotRates(f"the answer for {curve.key} is not a rates file: {','.join(header)[:120]}")
    columns: list[Column | None] = []
    for named in header[1:]:
        held = column(curve, named)
        columns.append(held)
        if held is None:
            read.unread.append(f"the column {named!r}")
        else:
            read.columns.append(held)
    for row in body:
        if not row or not row[0].strip():
            continue
        try:
            day = datetime.strptime(row[0].strip(), "%m/%d/%Y").date()
        except ValueError:
            read.unread.append(f"the date {row[0]!r}")
            continue
        points = []
        for held, value in zip(columns, row[1:], strict=False):
            said = value.strip()
            if held is None or not said:
                continue
            if not _NUMBER.fullmatch(said):
                read.unread.append(f"{day.isoformat()} {held.header}: {said!r}")
                continue
            points.append(Point(held, said))
        read.days.append(Day(day, tuple(points)))
    read.days.sort(key=lambda d: d.day)
    return read
