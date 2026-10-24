"""The US Treasury's daily interest rate files, where the par yield curves
and bill rates are published, and their stand-in.

One kind of request is made, and nothing else: one of Treasury's daily
Treasury rates files as CSV, for a month or for a year --

    /resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/all/<YYYYMM>
        ?type=<type>&field_tdr_date_value_month=<YYYYMM>&page&_format=csv
    /resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/<YYYY>/all
        ?type=<type>&field_tdr_date_value=<YYYY>&page&_format=csv

-- `type` one of `daily_treasury_yield_curve` (the nominal par yield
curve), `daily_treasury_real_yield_curve` (the real par yield curve) and
`daily_treasury_bill_rates` (the bill rates). Each answer is a header naming
the date and the tenors published that period, then a line a business day,
newest first, a tenor not published that day left empty. A period with no
rate -- before a curve's history, or not come yet -- is answered 200 with an
empty body.

The current rates are this month and the one before it, in New York, read
hourly: a correction to a rate of the last few weeks is read as the same
row's next version. Treasury states no Last-Modified and no publication
time, so every check reads them in full (a few kilobytes each); the plugin
records only what changed since its last read. A past year is read once,
for the history (feed.py), and a past day when a reader wants it.

Read from Treasury itself: no key, no account. Treasury's data are US
government work (docs/terms.md). It states no rate limit for these files;
the plugin asks one request at a time, at most one every two seconds, and
says who it is in its User-Agent. The standard library's client: the SDK
carries none, and one kind of request needs nothing more.

`SyntheticTreasury` answers from the real answers committed under
responses/, recorded on 2026-10-23 (responses/index.json): each file's
September and October 2026. A month is answered with its recorded answer, a
year with the recorded rows in it, newest first, and anything else with an
empty body, as Treasury answers a period it holds nothing for; its current
months are September and October 2026 whatever the clock says, so the
plugin's tests and its e2e run on it, offline, the same on any day.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from importlib import resources
from typing import Protocol

BASE = "https://home.treasury.gov"
FILES = "/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv"
USER_AGENT = "meridian-us-treasury (+https://github.com/open-meridian/plugin-us-treasury)"
#: The least time between two requests, in seconds.
SPACING = 2.0
#: How long one request may take.
TIMEOUT = 60.0
#: The most of an answer read: a year of any file is under 100 kB.
MOST_BYTES = 16 * 1024 * 1024


def month_path(feed_type: str, month: date) -> str:
    """The address of one file's rates for the month `month` falls in."""
    stamp = f"{month:%Y%m}"
    return (
        f"{FILES}/all/{stamp}?type={feed_type}&field_tdr_date_value_month={stamp}&page&_format=csv"
    )


def year_path(feed_type: str, year: int) -> str:
    """The address of one file's rates for a year."""
    return f"{FILES}/{year}/all?type={feed_type}&field_tdr_date_value={year}&page&_format=csv"


def period_of(path: str) -> tuple[str, str]:
    """The file type and the period (`YYYYMM` or `YYYY`) an address asks;
    empty where it asks neither."""
    query = dict(part.partition("=")[::2] for part in path.partition("?")[2].split("&"))
    period = query.get("field_tdr_date_value_month") or query.get("field_tdr_date_value") or ""
    return query.get("type", ""), period


def previous_month(day: date) -> date:
    return (day.replace(day=1) - timedelta(days=1)).replace(day=1)


class TreasuryUnreachable(Exception):  # noqa: N818 - what Treasury's site was
    """Treasury's site could not be asked: no answer, or not in time."""


@dataclass(frozen=True)
class Fetched:
    """One answer of Treasury's, as received."""

    path: str
    status: int
    body: bytes
    fetched_at: datetime
    date: str = ""

    @property
    def url(self) -> str:
        return BASE + self.path

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class Source(Protocol):
    mode: str

    def current(self, today: date) -> list[date]: ...

    async def get(self, path: str) -> Fetched: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


class LiveTreasury:
    """Treasury's site itself."""

    mode = "live"

    def __init__(self, now: Callable[[], datetime] = utc_now) -> None:
        self._now = now
        self._lock = asyncio.Lock()
        self._last = 0.0

    def current(self, today: date) -> list[date]:
        """The current months: the one before today's, and today's."""
        return [previous_month(today), today.replace(day=1)]

    async def get(self, path: str) -> Fetched:
        async with self._lock:
            wait = self._last + SPACING - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                return await asyncio.to_thread(self._get, path)
            finally:
                self._last = time.monotonic()

    def _get(self, path: str) -> Fetched:
        headers = {"User-Agent": USER_AGENT, "Accept": "text/csv"}
        request = urllib.request.Request(BASE + path, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:  # noqa: S310 - Treasury's https address
                body = answer.read(MOST_BYTES + 1)
                status = answer.status
                said = answer.headers
        except urllib.error.HTTPError as refused:
            body = refused.read(MOST_BYTES + 1) if refused.fp else b""
            status, said = refused.code, refused.headers
        except (urllib.error.URLError, TimeoutError, OSError) as failed:
            reason = getattr(failed, "reason", failed)
            raise TreasuryUnreachable(f"{BASE}{FILES}: {type(reason).__name__}") from failed
        if len(body) > MOST_BYTES:
            raise TreasuryUnreachable(f"{BASE}{path}: answered more than {MOST_BYTES} bytes")
        return Fetched(path, status, body, self._now(), date=said.get("Date", "") if said else "")


class SyntheticTreasury:
    """The answers committed under responses/: a recorded month answered as
    recorded, a year with the recorded rows in it, anything else empty."""

    mode = "synthetic"

    def __init__(self, now: Callable[[], datetime] = utc_now) -> None:
        self._now = now
        held = resources.files(__package__).joinpath("responses")
        index = json.loads(held.joinpath("index.json").read_text(encoding="utf-8"))
        self.recorded: dict[tuple[str, str], tuple[str, str]] = {}
        for entry in index["responses"]:
            text = gzip.decompress(held.joinpath(entry["file"]).read_bytes()).decode("utf-8")
            self.recorded[(entry["type"], entry["month"])] = (text, str(entry["date"]))
        self.last_day = date.fromisoformat(index["last_day"])
        self.asked: list[str] = []

    def current(self, today: date) -> list[date]:
        """The recording's current months, whatever the clock says."""
        return [previous_month(self.last_day), self.last_day.replace(day=1)]

    async def get(self, path: str) -> Fetched:
        self.asked.append(path)
        if not path.startswith(FILES + "/"):
            return Fetched(path, 404, b"Not found", self._now())
        feed_type, period = period_of(path)
        if len(period) == 6:
            text, said = self.recorded.get((feed_type, period), ("", ""))
            return Fetched(path, 200, text.encode(), self._now(), said)
        months = sorted(
            (m for (t, m) in self.recorded if t == feed_type and m.startswith(period)),
            reverse=True,
        )
        if len(period) != 4 or not months:
            return Fetched(path, 200, b"", self._now())
        header = ""
        lines: list[str] = []
        for month in months:
            text, _ = self.recorded[(feed_type, month)]
            first, *rows = text.splitlines()
            header = header or first
            lines.extend(r for r in rows if r)
        body = "\n".join([header, *lines]) + "\n"
        return Fetched(
            path, 200, body.encode(), self._now(), self.recorded[(feed_type, months[0])][1]
        )


def source(synthetic: bool, now: Callable[[], datetime] = utc_now) -> Source:
    return SyntheticTreasury(now) if synthetic else LiveTreasury(now)
