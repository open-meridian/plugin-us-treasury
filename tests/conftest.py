"""Shared stand-ins: Treasury's recorded answers, a fixed clock, the
deployment's three seeded curve records, and the lake's wants as the
sidecar delivers them."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles.data.testing import Instruments, Lake
from meridian.suites import Recorder

from us_treasury.curves import ADMINISTRATOR, CURVES
from us_treasury.feed import Feed
from us_treasury.raw import RawStore
from us_treasury.treasury import FILES, Fetched, SyntheticTreasury, period_of

#: After the recording: 16:00 UTC on Friday 23 October 2026, noon in New York.
AT = datetime(2026, 10, 23, 16, 0, tzinfo=UTC)
INSTANCE = "us-treasury"
#: Each curve's record, as the platform seeds it, by its dataset's key.
RECORDS = {curve.key: f"INS-{curve.key.upper()}" for curve in CURVES}
PAR, REAL, BILLS = RECORDS["ust_par"], RECORDS["ust_real"], RECORDS["ust_bills"]
#: The recording's business days, 1 September to 22 October 2026.
DAYS = 36
#: Points a day: the par curve's 14 tenors, the real curve's 5, the bills' 7
#: tenors at two conventions each.
POINTS = {"ust_par": 14, "ust_real": 5, "ust_bills": 14}
TESTS = Path(__file__).parent / "responses"


def held(store: Instruments, *, missing: str = "") -> Instruments:
    """The three curve records, as the platform's seed names them; `missing`
    left out."""
    for curve in CURVES:
        if curve.key == missing:
            continue
        store.hold(
            RECORDS[curve.key],
            ops.Identifier(scheme="symbol", value=curve.code, source=ADMINISTRATOR),
            asset_class=ops.ASSET_CLASS_REFERENTIAL,
            instrument_type=ops.INSTRUMENT_TYPE_RATE_CURVE,
        )
    return store


def lake(missing: str = "") -> Lake:
    """The lake as a test stands it in, holding the curve records."""
    made = Lake(INSTANCE)
    held(made.instruments, missing=missing)
    return made


def answering(recorder: Recorder, missing: str = "") -> Recorder:
    """A suite recorder answering resolves from the curve records."""
    held(Instruments().answering(recorder), missing=missing)
    return recorder


class Recorded(SyntheticTreasury):
    """The sample answers, and beside them those recorded for the tests
    (tests/responses/): the par curve of February 2025 and the bill rates
    of 2002."""

    def __init__(self, at: datetime = AT) -> None:
        super().__init__(lambda: at)
        index = json.loads((TESTS / "index.json").read_text(encoding="utf-8"))
        self.extra: dict[tuple[str, str], str] = {}
        for entry in index["responses"]:
            period = entry.get("month") or entry.get("year")
            text = gzip.decompress((TESTS / entry["file"]).read_bytes()).decode()
            self.extra[(entry["type"], period)] = text

    async def get(self, path: str) -> Fetched:
        found = self.extra.get(period_of(path))
        if path.startswith(FILES) and found is not None:
            self.asked.append(path)
            return Fetched(path, 200, found.encode(), self._now())
        return await super().get(path)


class Corrected(SyntheticTreasury):
    """Treasury's site, October's par curve read twice: as recorded, then
    with the 10-year of 22 October corrected from 4.96 to 4.97."""

    def __init__(self, at: datetime = AT) -> None:
        super().__init__(lambda: at)
        self.reads = 0

    async def get(self, path: str) -> Fetched:
        got = await super().get(path)
        if "daily_treasury_yield_curve" not in path or "202610" not in path:
            return got
        self.reads += 1
        if self.reads == 1:
            return got
        line = "10/22/2026,4.11,4.10,4.16,4.22,4.29,4.29,4.41,4.65,4.72,4.78,4.86,4.96,"
        body = got.text.replace(line, line[:-5] + "4.97,")
        assert body != got.text
        return Fetched(path, 200, body.encode(), got.fetched_at, got.date)


def feed(tmp: Path, plugin: Any = None, at: datetime = AT, source: Any = None) -> Feed:
    """The plugin's work on the lake as a test stands it in and the recorded
    answers, at `at`."""
    return Feed(
        plugin if plugin is not None else lake(),
        source or Recorded(at),
        RawStore(tmp),
        now=lambda: at,
    )


def want(
    want_id: str,
    subjects: list[str],
    *,
    key: str = "ust_par",
    day: str = "",
    standing: bool = False,
    data_type: str = "meridian.v1.Rate",
    valid_from_ns: int = 0,
    valid_until_ns: int = 0,
) -> Heard:  # type: ignore[type-arg]
    return Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id=want_id,
            dataset=f"{INSTANCE}:{key}",
            data_type=data_type,
            subjects=[ops.SubjectRef(entity_id=s) for s in subjects],
            business_date=day,
            standing=standing,
            valid_from_ns=valid_from_ns,
            valid_until_ns=valid_until_ns,
        ),
    )
