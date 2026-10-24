"""Treasury's curves into the lake: each day's pushed when Treasury
publishes it, the history read back on the first run, and any past day
recorded when the lake wants it (W10.4, W10.7). Every row goes through the
SDK's rates helpers (`meridian.roles.data.rates`, ruling 345).

**Push.** The current months -- this one and the one before, in New York --
of each file are read at start and every hour. What a read states is
recorded whole, in batches of at most 500, the first time this process reads
it and again whenever it changes; the lake answers each rate it holds
unchanged, so nothing is kept between starts but the answers in storage
(decisions/028: a plugin's process holds nothing it cannot lose). A rate
Treasury corrects within the range is the same row's next version: its row
key names the curve's record, the kind, the tenor, the convention and the
business date (`rates.Feed`), never when it was read.

**History.** On the first run each curve's past is read back, a year at a
time, newest first, to the first year Treasury states (the spec's §3: the
par curve from 1990, the real curve from 2003, the bill rates from 2002),
one request every two seconds. Each past year read whole is noted in
storage (raw.py), so a restart reads on from where it stopped; the current
year is read once in every process, which fills any gap left while the
plugin was not running.

**Subjects.** Before anything is recorded, each curve's record is resolved
by Treasury's title as a `symbol` scoped to `ustreasury` -- the platform's
seeded referential records -- as of now (`rates.Feed.subject`). One the
deployment does not hold, or holds twice, is reported missing (W3.2) once a
day, and its rows wait until it resolves: a plugin never mints.

**Wants.** The lake asks for what a reader read and it does not hold
(ObservationsWanted): a business date, a range, or the latest, of one
dataset. Each dataset has one subject, its curve; any other is declined
`not_covered`, as is a want for another data type. (A want's kinds are a
price's; a rates want is answered with every kind the curve states.) A day
before the dataset's history is declined `beyond_history`; one not come
yet, or one Treasury states nothing for (a weekend, a market holiday),
`source_silent`. The rest are read from Treasury -- a month where the days
asked are in one, else each year, at most a year of days -- and recorded
against the want. A standing want asks the curve kept
current, which the push does; it is kept until it is withdrawn
(WantWithdrawn). The SDK's `meridian.roles.data.Wants` keeps the wants,
declines by reason, sends the batches and counts them; only Treasury's part
is here.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import meridian
from meridian.operations import Rate
from meridian.plugin.v1 import operations_pb2 as ops
from meridian.roles import data
from meridian.roles.data import rates

from .curves import ADMINISTRATOR, BY_KEY, CURVES, Curve, NotRates, Read, parse
from .declared import DAY_TIME_ZONE, RATE
from .raw import RawStore
from .treasury import Fetched, Source, TreasuryUnreachable, month_path, utc_now, year_path

log = logging.getLogger("us_treasury")

NEW_YORK = ZoneInfo(DAY_TIME_ZONE)
#: The most days one want is answered for: a year.
MOST_DAYS = 366
#: How many first-read lags are kept per curve, for the Lag section.
LAGS = 2000


def _ns(moment: datetime) -> int:
    return int(moment.timestamp() * 1_000_000) * 1000


def day_start_ns(day: date) -> int:
    """The start of business date `day`: midnight in New York."""
    return _ns(datetime.combine(day, time(0, 0), NEW_YORK))


def new_york_day(at: datetime) -> date:
    return at.astimezone(NEW_YORK).date()


def next_weekday(after: date) -> date:
    """The first Monday-to-Friday day after `after`: no calendar of the US
    government securities market is curated yet (the spec's Q15)."""
    day = after + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


@dataclass(frozen=True)
class Outcome:
    recorded: int = 0
    restated: int = 0
    unchanged: int = 0

    @property
    def sent(self) -> int:
        return self.recorded + self.restated + self.unchanged


@dataclass
class SourceStatus:
    """One file as the plugin last saw it, for its pages; held in memory,
    lost on a restart and read again by the first check."""

    curve: Curve
    #: The deployment's record for the curve, or why there is none.
    instrument_id: str = ""
    miss: str = ""
    read_at: datetime | None = None
    error: str = ""
    calls: int = 0
    #: The current months' first and latest day with a rate.
    first_day: date | None = None
    latest_day: date | None = None
    #: The tenors the latest day states, in the file's order.
    tenors: list[str] = field(default_factory=list)
    #: What could not be read, each with how often seen.
    unread: dict[str, int] = field(default_factory=dict)
    #: The history: each past year read, whether every year is, and why it stopped.
    history_years: list[int] = field(default_factory=list)
    history_done: bool = False
    history_error: str = ""
    #: When each day first read since the plugin started watching was first
    #: seen, minus its start in New York, in seconds.
    lags: list[int] = field(default_factory=list)
    seen: set[date] = field(default_factory=set)
    watching: bool = False

    @property
    def history_from(self) -> int | None:
        return min(self.history_years) if self.history_years else None


@dataclass
class Status:
    """What the plugin last did, for its pages."""

    mode: str = "live"
    started_at: datetime | None = None
    checked_at: datetime | None = None
    sources: dict[str, SourceStatus] = field(
        default_factory=lambda: {c.key: SourceStatus(c) for c in CURVES}
    )

    @property
    def error(self) -> str:
        return next((s.error for s in self.sources.values() if s.error), "")

    @property
    def read(self) -> bool:
        return any(s.read_at is not None for s in self.sources.values())

    @property
    def calls(self) -> int:
        return sum(s.calls for s in self.sources.values())


class Feed:
    """The plugin's work, on its typed operations -- `plugin` is the
    connected `meridian.Plugin`, or the suite's `Recorder` in its tests --
    reading Treasury, resolving, recording, answering wants."""

    def __init__(
        self,
        plugin: Any,
        source: Source,
        raw: RawStore,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.plugin = plugin
        self.source = source
        self.raw = raw
        self.now = now
        self.wants = data.Wants(plugin, tuple(BY_KEY), clock_ns=lambda: _ns(self.now()))
        self.rates = rates.Feed(
            plugin,
            ADMINISTRATOR,
            wants=self.wants,
            day_zone=DAY_TIME_ZONE,
            clock_ns=lambda: _ns(self.now()),
        )
        self.status = Status(mode=source.mode, started_at=now())
        self._digests: dict[str, str] = {}
        self._current_year_read: set[str] = set()

    def today(self) -> date:
        return new_york_day(self.now())

    def use(self, source: Source) -> None:
        """Read from `source` from now on: sample data turned on or off."""
        if source.mode != self.source.mode:
            self.source = source
            self.status = Status(mode=source.mode, started_at=self.now())
            self._digests.clear()
            self._current_year_read.clear()
            # A record missed reading the other source is asked again now,
            # not tomorrow: what was missing then may be held.
            self.rates.missed.clear()

    # ── Reading Treasury ────────────────────────────────────────────────

    async def read(self, curve: Curve, path: str) -> tuple[Read, Fetched, str]:
        """One answer for `curve`, kept, read; TreasuryUnreachable or
        NotRates otherwise."""
        held = self.status.sources[curve.key]
        held.calls += 1
        fetched = await self.source.get(path)
        key = self.raw.keep(fetched)
        if fetched.status != 200:
            raise TreasuryUnreachable(f"{fetched.url} answered {fetched.status}")
        read = parse(fetched.text, curve)
        for line in read.unread:
            held.unread[line] = held.unread.get(line, 0) + 1
        return read, fetched, key

    # ── Resolving ───────────────────────────────────────────────────────

    async def subject(self, curve: Curve) -> str:
        """The curve's record, resolved now where not yet; a miss reported
        once a day, and said."""
        held = self.status.sources[curve.key]
        found = await self.rates.subject(
            curve.identifier, description=curve.code, instrument_type="rate_curve"
        )
        held.instrument_id = found
        held.miss = "" if found else "not held by the deployment; reported missing"
        return found

    # ── Recording ───────────────────────────────────────────────────────

    def rows(
        self,
        curve: Curve,
        subject: str,
        read: Read,
        key: str,
        days: Iterable[date] | None = None,
    ) -> list[Rate]:
        """The rates `read` states for `subject`, on `days` where given: one
        row per point, never one for a tenor left empty. Each names the
        answer it was first read from (raw.py), so a rate read again -- the
        next check, the history, a want, a restart -- is the same row."""
        wanted = set(days) if days is not None else None
        made: list[Rate] = []
        for day in read.days:
            if wanted is not None and day.day not in wanted:
                continue
            for point in day.points:
                column = point.column
                said = (
                    f"{curve.key}:{column.kind}:{column.tenor}:{column.header}:"
                    f"{day.day.isoformat()}={point.text}"
                )
                made.append(
                    self.rates.rate(
                        subject,
                        curve.key,
                        column.kind,
                        point.text,
                        business_date=day.day,
                        convention=column.convention,
                        tenor=column.tenor,
                        series=curve.key,
                        raw_key=self.raw.first(said, day.day, key),
                    )
                )
        self.raw.save_firsts()
        return made

    async def record(
        self,
        curve: Curve,
        read: Read,
        key: str,
        *,
        want_id: str = "",
        days: Iterable[date] | None = None,
    ) -> Outcome:
        """Record what `read` states for the curve, against `want_id` where
        given; nothing while its record does not resolve."""
        subject = await self.subject(curve)
        if not subject:
            return Outcome()
        made = self.rows(curve, subject, read, key, days)
        counts = self.wants.sent_to(curve.key)
        before = (counts.recorded, counts.restated, counts.unchanged)
        if made:
            await self.rates.record(curve.key, made, want_id)
        return Outcome(
            counts.recorded - before[0], counts.restated - before[1], counts.unchanged - before[2]
        )

    def _note(self, curve: Curve, read: Read) -> None:
        """What a read of the current months says of the curve, for its pages;
        and each day newly seen while watching, its lag."""
        held = self.status.sources[curve.key]
        held.read_at = self.now()
        if not read.days:
            return
        first, latest = read.days[0].day, read.days[-1].day
        held.first_day = min(held.first_day or first, first)
        if held.latest_day is None or latest >= held.latest_day:
            held.latest_day = latest
            held.tenors = list(dict.fromkeys(p.column.tenor for p in read.days[-1].points))
        for day in read.days:
            if day.day in held.seen:
                continue
            held.seen.add(day.day)
            if held.watching:
                lag = (_ns(self.now()) - day_start_ns(day.day)) // 10**9
                held.lags = [*held.lags[-(LAGS - 1) :], lag]

    async def check(self) -> dict[str, Outcome]:
        """Read each curve's current months; record what this process has not
        recorded as it reads now. What each recorded."""
        self.status.checked_at = self.now()
        done: dict[str, Outcome] = {}
        for curve in CURVES:
            held = self.status.sources[curve.key]
            total = Outcome()
            try:
                for month in self.source.current(self.today()):
                    path = month_path(curve.feed_type, month)
                    read, _, key = await self.read(curve, path)
                    self._note(curve, read)
                    digest = digest_of(read)
                    if self._digests.get(path) == digest:
                        continue
                    outcome = await self.record(curve, read, key)
                    if held.instrument_id:
                        self._digests[path] = digest
                    total = Outcome(
                        total.recorded + outcome.recorded,
                        total.restated + outcome.restated,
                        total.unchanged + outcome.unchanged,
                    )
                held.error = ""
            except (TreasuryUnreachable, NotRates) as failed:
                held.error = str(failed)
                log.warning("%s: the current rates were not read: %s", curve.key, failed)
            held.watching = held.read_at is not None
            done[curve.key] = total
            if total.sent:
                log.info(
                    "%s to %s: %d recorded, %d restated, %d unchanged",
                    curve.key,
                    held.latest_day,
                    total.recorded,
                    total.restated,
                    total.unchanged,
                )
        return done

    def next_release(self) -> date | None:
        """The next day expected, Monday to Friday after the latest stated."""
        latest = [s.latest_day for s in self.status.sources.values() if s.latest_day]
        return next_weekday(max(latest)) if latest else None

    # ── History ─────────────────────────────────────────────────────────

    async def history(self) -> int:
        """Read back each curve's past a year at a time, newest first, to its
        first year: past years noted in storage are not read again, the
        current year once a process. How many years were read. A year that
        fails stops that curve's reading until the next call."""
        years_read = 0
        noted = self.raw.history()
        this_year = self.today().year
        for curve in CURVES:
            held = self.status.sources[curve.key]
            done = set(noted.get(curve.key, []))
            held.history_years = sorted(done)
            if held.read_at is None:
                # Treasury not read yet: the history waits for the current
                # months, and resolves nothing before them.
                held.history_error = "waiting for Treasury to answer"
                continue
            if not await self.subject(curve):
                held.history_error = "waiting for the curve's record to resolve"
                continue
            held.history_error = ""
            for year in range(this_year, curve.first_year - 1, -1):
                past = year < this_year
                if (past and year in done) or (not past and curve.key in self._current_year_read):
                    continue
                try:
                    read, _, key = await self.read(curve, year_path(curve.feed_type, year))
                    outcome = await self.record(curve, read, key)
                except (TreasuryUnreachable, NotRates, meridian.MeridianError) as failed:
                    held.history_error = f"{year}: {failed}"
                    log.warning("%s: the history stopped at %d: %s", curve.key, year, failed)
                    break
                years_read += 1
                if past:
                    self.raw.note_year(curve.key, year)
                    done.add(year)
                    held.history_years = sorted(done)
                else:
                    self._current_year_read.add(curve.key)
                log.info(
                    "%s %d read back: %d recorded, %d restated, %d unchanged",
                    curve.key,
                    year,
                    outcome.recorded,
                    outcome.restated,
                    outcome.unchanged,
                )
            held.history_done = all(y in done for y in range(curve.first_year, this_year)) and (
                curve.key in self._current_year_read
            )
        return years_read

    # ── Wants ───────────────────────────────────────────────────────────

    async def on_want(self, heard: meridian.Heard[ops.ObservationsWantedEvent]) -> None:
        """Record what the lake wants of one of the plugin's datasets, or
        decline it (the SDK's `Wants.hear`, answered by `answer`)."""
        await self.wants.hear(heard, self.answer)

    async def on_withdrawn(self, heard: meridian.Heard[ops.WantWithdrawnEvent]) -> None:
        """A standing want withdrawn: no longer kept current."""
        self.wants.withdraw(heard.message.want_id)
        log.info("standing want %s withdrawn", heard.message.want_id)

    def _days(self, want: ops.ObservationsWantedEvent, curve: Curve) -> list[date]:
        if want.business_date:
            return [date.fromisoformat(want.business_date)]
        if want.valid_from_ns or want.valid_until_ns:
            start = new_york_day(datetime.fromtimestamp(want.valid_from_ns // 10**9, NEW_YORK))
            # Valid times end before `valid_until_ns`: a range to midnight
            # holds no day after it.
            until = want.valid_until_ns - 1 if want.valid_until_ns else _ns(self.now())
            end = new_york_day(datetime.fromtimestamp(until // 10**9, NEW_YORK))
            days = [start + timedelta(days=n) for n in range((end - start).days + 1)]
            return days[-MOST_DAYS:]
        latest = self.status.sources[curve.key].latest_day
        return [latest] if latest else []

    async def answer(
        self,
        want: ops.ObservationsWantedEvent,
        key: str,
        subjects: list[str],
        kinds: tuple[int, ...],
    ) -> dict[str, str]:
        """One want answered from Treasury: its rates recorded against it,
        and each subject declined, with why."""
        curve = BY_KEY.get(key)
        if curve is None or want.data_type not in ("", RATE):
            return {s: "not_covered" for s in subjects}
        subject = await self.subject(curve)
        declined = {s: "not_covered" for s in subjects if s != subject}
        if not subject or subject not in subjects:
            return declined
        if want.standing:
            self.wants.stand(want, [subject], kinds)
        latest = not want.business_date and not want.valid_from_ns and not want.valid_until_ns
        if latest and self.status.sources[curve.key].latest_day is None:
            await self.check()
        reason = await self._record_days(curve, want, self._days(want, curve))
        if reason:
            declined[subject] = reason
        return declined

    async def _record_days(
        self,
        curve: Curve,
        want: ops.ObservationsWantedEvent,
        days: Sequence[date],
    ) -> str:
        """Record the days asked against the want; the reason the curve is
        declined, or empty where a rate was recorded."""
        today = self.today()
        oldest = date(curve.first_year, 1, 1)
        if days and all(d < oldest for d in days):
            return "beyond_history"
        asked = [d for d in days if oldest <= d <= today and d.weekday() < 5]
        if not asked:
            return "source_silent"
        first, last = min(asked), max(asked)
        if (first.year, first.month) == (last.year, last.month):
            paths = [month_path(curve.feed_type, first)]
        else:
            paths = [year_path(curve.feed_type, y) for y in range(first.year, last.year + 1)]
        sent = 0
        for path in paths:
            try:
                read, _, key = await self.read(curve, path)
            except (TreasuryUnreachable, NotRates) as failed:
                log.warning("want %s: Treasury was not read: %s", want.want_id, failed)
                return "source_silent"
            done = await self.record(curve, read, key, want_id=want.want_id, days=asked)
            sent += done.sent
        return "" if sent else "source_silent"


def digest_of(read: Read) -> str:
    """What an answer states, as a short digest: its points, never the
    answer's other bytes."""
    stated = repr(
        [(d.day, [(p.column.header, p.text) for p in d.points]) for d in read.days]
    ).encode()
    return hashlib.sha256(stated).hexdigest()[:16]
