"""A day's published time (from 0.2.0; ruling 518): Treasury states none, so
a day first stated by an hourly read on its own day, the read before having
stated it not, is stated `published` at that read -- the true publication up
to an hour earlier -- and a day found later states none. The feed delay is
measured from it (`reports-its-feed-delay`)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.suites import Recorder

from us_treasury.feed import Feed
from us_treasury.raw import RawStore

from conftest import INSTANCE, ON_THE_DAY, Appearing, Clock, answering


def published(recorder: Recorder) -> dict[str, int]:
    """Each 22 October par rate sent, by row key: its published time, 0 for
    none."""
    out: dict[str, int] = {}
    for batch in recorder.on("RecordRates"):
        for rate in batch.rates:
            if rate.meta.business_date == "2026-10-22" and "ust_par" in rate.meta.source.dataset:
                times = [
                    t.at_ns
                    for t in rate.meta.source_times
                    if t.kind == ops.SOURCE_TIME_KIND_PUBLISHED
                ]
                out[rate.meta.row_key] = times[0] if times else 0
    return out


def test_a_day_first_stated_by_the_next_hourly_read_is_published_then(tmp_path: Path) -> None:
    recorder = answering(Recorder(INSTANCE))
    clock = Clock()
    source = Appearing(clock)
    work = Feed(recorder, source, RawStore(tmp_path), now=clock)
    asyncio.run(work.check())
    assert published(recorder) == {}
    clock.at += timedelta(hours=1)
    source.appeared = True
    asyncio.run(work.check())
    stated = published(recorder)
    assert len(stated) == 14
    assert set(stated.values()) == {int(clock.at.timestamp()) * 10**9}
    # Read again by a new process (the same storage): the same time, so the
    # lake answers the same row.
    again = answering(Recorder(INSTANCE))
    clock.at += timedelta(minutes=5)
    later = Appearing(clock)
    later.appeared = True
    asyncio.run(Feed(again, later, RawStore(tmp_path), now=clock).check())
    assert published(again) == stated


def test_a_day_found_later_states_no_published_time(tmp_path: Path) -> None:
    # The first read of a process: the day was already there.
    recorder = answering(Recorder(INSTANCE))
    clock = Clock()
    work = Feed(recorder, Appearing(clock), RawStore(tmp_path / "first"), now=clock)
    work.source.appeared = True  # type: ignore[attr-defined]
    asyncio.run(work.check())
    assert published(recorder) and set(published(recorder).values()) == {0}
    # After a pause: the read before is more than 70 minutes old.
    recorder = answering(Recorder(INSTANCE))
    source = Appearing(clock)
    work = Feed(recorder, source, RawStore(tmp_path / "paused"), now=clock)
    asyncio.run(work.check())
    clock.at += timedelta(hours=3)
    source.appeared = True
    asyncio.run(work.check())
    assert published(recorder) and set(published(recorder).values()) == {0}
    # A past day: the next day's first read states the 22nd for the first time.
    recorder = answering(Recorder(INSTANCE))
    clock = Clock(ON_THE_DAY + timedelta(days=1))
    source = Appearing(clock)
    work = Feed(recorder, source, RawStore(tmp_path / "past"), now=clock)
    asyncio.run(work.check())
    clock.at += timedelta(hours=1)
    source.appeared = True
    asyncio.run(work.check())
    assert published(recorder) and set(published(recorder).values()) == {0}
