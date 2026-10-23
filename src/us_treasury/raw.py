"""What Treasury answered, kept as received, in the plugin's own storage;
and how far back each curve's history has been read.

A data plugin keeps its source's raw records in the storage the deployment
grants an edge plugin (decisions/028, `meridian.edge.storage_dir()`), and
every row it records names the one it was converted from
(`ObservationMeta.raw`). Here that is each answer of Treasury's: its
address, status, Date header, when it was received, and the CSV itself, one
gzipped JSON file each, kept before anything is read from it. Raw answers
are kept from the first day (the spec's Q17), so a later version converting
more of what Treasury states needs no refetch.

One kind of raw record, `responses` (declared.py), in units of a month of
receipt: `responses/<YYYY-MM>/`, each file `<received>-<file>-<period>.json.gz`,
its key that path. A month's unit is written to only in that month, so once
its last record is past the kind's window it is moved whole, as the SDK's
`responses_past_window` setting says: archived (`plugin.archive_unit`),
deleted (`plugin.delete_unit`, which a deployment's hold refuses, keeping
it) or kept. The current months are read hourly, about 4 kB gzipped each,
so a year of answers is some 100 MB, and the window defaults to ten years.

**The history read** (`history.json` at the storage's root): each curve's
past years read whole, so a restart reads on from where the last one
stopped, and a new container with the same storage reads none of them
again. Where storage is lost the history is read again, and the lake
answers each rate it holds unchanged.

Where no storage is granted -- a test, a preview -- the store keeps its
records in a directory of its own and moves nothing.
"""

from __future__ import annotations

import gzip
import json
import logging
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import meridian
from meridian import edge

from .treasury import Fetched, period_of

log = logging.getLogger("us_treasury")

#: The kind of raw record, and its default window: ten years.
RESPONSES = "responses"
DEFAULT_WINDOW_DAYS = 3650
#: The longest a window may be set to, which the storage declaration states.
MOST_WINDOW_DAYS = 36500
#: Where each curve's history read is noted, at the storage's root.
HISTORY = "history.json"

_SHORT = {
    "daily_treasury_yield_curve": "par",
    "daily_treasury_real_yield_curve": "real",
    "daily_treasury_bill_rates": "bills",
}


def _ns(moment: datetime) -> int:
    return int(moment.timestamp() * 1_000_000) * 1000


def answer_name(path: str) -> str:
    """A short name for what an address asks: `par-202610`, `bills-2002`."""
    feed_type, period = period_of(path)
    return f"{_SHORT.get(feed_type, 'answer')}-{period or 'none'}"


@dataclass(frozen=True)
class Unit:
    """A month of answers: its path in storage, and what it holds."""

    unit: str
    records: int
    first_ns: int
    last_ns: int


class RawStore:
    """Answers kept under `root`: the granted storage, or a directory of the
    store's own where none is granted (`granted` False)."""

    def __init__(self, root: Path | None = None) -> None:
        granted = root if root is not None else edge.storage_dir()
        self.granted = granted is not None
        self.root = Path(granted) if granted is not None else Path(tempfile.mkdtemp(prefix="ust-"))

    def keep(self, fetched: Fetched) -> str:
        """Keep an answer before anything is read from it; its key."""
        at = fetched.fetched_at.astimezone(UTC)
        unit = f"{RESPONSES}/{at:%Y-%m}"
        key = f"{unit}/{at:%Y%m%dT%H%M%S%fZ}-{answer_name(fetched.path)}.json.gz"
        document = {
            "url": fetched.url,
            "status": fetched.status,
            "date": fetched.date,
            "received_at": at.isoformat(),
            "body": fetched.text,
        }
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".partial")
        partial.write_bytes(gzip.compress(json.dumps(document).encode(), mtime=0))
        partial.replace(target)
        return key

    # ── The history read ────────────────────────────────────────────────

    def history(self) -> dict[str, list[int]]:
        """Each curve's past years read whole, by its dataset's key."""
        try:
            held = json.loads((self.root / HISTORY).read_text())
        except (OSError, ValueError):
            return {}
        if not isinstance(held, dict):
            return {}
        return {
            str(k): sorted(int(y) for y in v if isinstance(y, int))
            for k, v in held.items()
            if isinstance(v, list)
        }

    def note_year(self, key: str, year: int) -> None:
        """Note a past year of `key`'s curve read whole."""
        held = self.history()
        years = set(held.get(key, []))
        years.add(year)
        held[key] = sorted(years)
        target = self.root / HISTORY
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(".partial")
        partial.write_text(json.dumps(held, sort_keys=True))
        partial.replace(target)

    # ── Reading back and moving ─────────────────────────────────────────

    def read(self, key: str) -> dict[str, Any] | None:
        """A kept answer by its key, or None where storage no longer holds it."""
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file():
            return None
        document: dict[str, Any] = json.loads(gzip.decompress(path.read_bytes()))
        return document

    def keys(self) -> list[str]:
        """Every kept answer's key, oldest first."""
        held = self.root / RESPONSES
        if not held.is_dir():
            return []
        return sorted(str(p.relative_to(self.root)) for p in held.glob("*/*.json.gz"))

    def units(self) -> Iterator[Unit]:
        """Each month of answers in storage, oldest first."""
        held = self.root / RESPONSES
        if not held.is_dir():
            return
        for month in sorted(p for p in held.iterdir() if p.is_dir()):
            read = (_received(p.name) for p in month.glob("*.json.gz"))
            stamps = sorted(s for s in read if s is not None)
            if stamps:
                yield Unit(
                    str(month.relative_to(self.root)), len(stamps), _ns(stamps[0]), _ns(stamps[-1])
                )

    async def tend(
        self, plugin: meridian.Plugin, window_days: int, past_window: str, now: datetime
    ) -> dict[str, int]:
        """Move each month past the window as `past_window` says, and say on
        the heartbeat what storage holds; what it came to."""
        done = {"archived": 0, "deleted": 0, "kept": 0, "refused": 0}
        if not self.granted:
            return done
        cut = _ns(now - timedelta(days=window_days))
        this_month = f"{RESPONSES}/{now.astimezone(UTC):%Y-%m}"
        for unit in list(self.units()):
            if unit.last_ns >= cut or unit.unit == this_month:
                continue
            if past_window not in ("archived", "deleted"):
                done["kept"] += 1
                continue
            move = plugin.archive_unit if past_window == "archived" else plugin.delete_unit
            try:
                await move(
                    RESPONSES,
                    unit.unit,
                    record_count=unit.records,
                    first_received_ns=unit.first_ns,
                    last_received_ns=unit.last_ns,
                )
                done[past_window] += 1
            except meridian.MeridianError as refused:
                log.warning("%s: %s refused, kept: %s", unit.unit, past_window, refused)
                done["refused"] += 1
        plugin.stored = [self.span()]
        return done

    def span(self) -> Any:
        """What storage holds of the kind, for the heartbeat."""
        from meridian.v1 import sidecar_pb2

        units = list(self.units())
        return sidecar_pb2.StoredSpan(
            record_kind=RESPONSES,
            record_count=sum(u.records for u in units),
            first_received_ns=units[0].first_ns if units else 0,
            last_received_ns=units[-1].last_ns if units else 0,
        )


def _received(name: str) -> datetime | None:
    try:
        return datetime.strptime(name.split("-", 1)[0], "%Y%m%dT%H%M%S%fZ").replace(tzinfo=UTC)
    except ValueError:
        return None
