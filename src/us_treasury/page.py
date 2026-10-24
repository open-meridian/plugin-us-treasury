"""The plugin's pages, under Manage alone: the data role's common pages
(spec/plugin-pages-follow-their-role), Connection and Datasets, in its
order, each also a read tool for agents on the deployment's MCP under the
role's names (`read_connection`, `read_datasets`). Each record is the
role's (`meridian.roles.data`), extended with Treasury's fields; each
template is the role's, with Treasury's nuance at its blocks only.

A data plugin shows its connectivity, its data subscriptions and how its
entitlements resolve, and no market data (the product owner, 2026-10-03).
So, as spec/a-public-rates-and-filings-data-plugin §5 has them:

- **Connection** (`/`): "Key" -- the mode (Live or Sample data), "No key
  needed", what Treasury serves; "Limits and use" -- Treasury states no
  limit, the requests made, the last check and error, and **Sources** as
  one row of it, each file in its detail: its state, the last day
  published, the next expected, its calls, its last error, its tenors and
  how far its history is read back; "Stream": it does not stream. A
  section of its own, even paged, does not fit one screen beside the role's
  sections, so Sources is a row of the one whose calls it divides.
- **Datasets** (`/datasets`): "Served", with **Records** (the curve's record
  or why there is none) and **Lag** as columns of it, one dataset being one
  curve; "Wants" and "Subjects".

Neither shows an account's data, since the plugin reaches none, nor a rate:
rates are the reading roles' to show.
"""

from __future__ import annotations

import statistics
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import meridian
from meridian.roles import data

from . import records
from .curves import CURVES
from .declared import CATALOGUE
from .feed import Feed, SourceStatus, Status
from .treasury import BASE, FILES

TITLE = "U.S. Treasury"

pages = meridian.Pages(TITLE, templates=Path(__file__).parent / "templates")

CONNECTION = "/"
DATASETS = "/datasets"

#: How many wants the Datasets tab lists; read_datasets answers every one held.
SHOWN_WANTS = 3
#: How Treasury is cited: its data are US government work, and no
#: attribution is required (the spec's §7).
ATTRIBUTION = (
    "Source: U.S. Department of the Treasury, daily Treasury rates. US government work: "
    "no attribution is required, and Treasury is cited as the source."
)
DEFAULT_TERMS = "kept, derived use not restricted, display; US government work"
#: What each file's rows are.
ROWS = {
    "ust_par": "par yields, bond-equivalent, one row a tenor",
    "ust_real": "real par yields, bond-equivalent, one row a tenor",
    "ust_bills": "bank discount and coupon equivalent, two rows a tenor",
}

_held: dict[str, Feed] = {}


def hold(feed: Feed) -> None:
    """The feed the pages read, once the plugin has registered."""
    _held["feed"] = feed


def _status() -> tuple[Status, Feed | None]:
    feed = _held.get("feed")
    return (feed.status if feed is not None else Status(), feed)


def _iso(moment: datetime | None) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds") if moment else ""


def _day(day: date | None) -> str:
    return day.isoformat() if day else ""


def _state(status: Status) -> tuple[str, str, str]:
    """The head's status: its state, what it means, and its detail."""
    misses = [s for s in status.sources.values() if s.miss]
    if status.error and not status.read:
        return "error", "Not answering", status.error
    if status.error:
        return "warn", "Answering", status.error
    if not status.read:
        return "busy", "Checking Treasury", ""
    if misses:
        titles = ", ".join(s.curve.code for s in misses)
        plural = "record" if len(misses) == 1 else "records"
        return "warn", f"{len(misses)} {plural} not resolved", titles
    if status.mode == "synthetic":
        return "ok", "Sample data", ""
    return "ok", "Answering", ""


def _source_state(held: SourceStatus) -> str:
    if held.error and held.read_at is None:
        return "Not answering"
    if held.error:
        return "Answering, last read failed"
    if held.read_at is None:
        return "Not read yet"
    if held.miss:
        return "Record not resolved"
    return "Answering"


def _history(held: SourceStatus, first_year: int) -> str:
    years = held.history_years
    if held.history_done:
        return f"Read back to {first_year}"
    said = f"Read back to {min(years)}, of {first_year} on" if years else "Not read back yet"
    return f"{said}: {held.history_error}" if held.history_error else said


def connection_read(status: Status, feed: Feed | None) -> records.ConnectionRead:
    state, said, _ = _state(status)
    kept = feed.raw.keys() if feed is not None else []
    window = ""
    if feed is not None and feed.raw.granted:
        window = "in the storage the deployment grants, as its responses settings say"
    elif feed is not None:
        window = "in a directory of the plugin's own: this deployment grants no storage"
    instance = feed.plugin.identity.instance_id if feed is not None else "us-treasury"
    next_release = feed.next_release() if feed is not None else None
    last_call = max((s.read_at for s in status.sources.values() if s.read_at), default=None)
    sources = []
    for curve in CURVES:
        held = status.sources[curve.key]
        sources.append(
            records.SourceRead(
                source=curve.code,
                dataset=f"{instance}:{curve.key}",
                state=_source_state(held),
                last_release=_day(held.latest_day),
                next_expected=_day(next_release) if held.latest_day else "",
                calls=held.calls,
                last_error=held.error,
                reads=(
                    "The answers recorded on 2026-10-23, committed with the plugin"
                    if status.mode == "synthetic"
                    else f"{BASE}{FILES}, type {curve.feed_type}"
                ),
                tenors=list(held.tenors),
                history_from=held.history_from,
                history_first_year=curve.first_year,
                history_done=held.history_done,
                history=_history(held, curve.first_year),
            )
        )
    return records.ConnectionRead(
        mode="Sample data" if status.mode == "synthetic" else "Live",
        credentials=[],
        entitled_at_vendor=(
            "Every daily Treasury rate it publishes: no key"
            if status.read or status.mode == "synthetic"
            else ""
        ),
        limit=(
            "Treasury states none; the plugin asks one request at a time, at most one every "
            "two seconds, and checks for new rates every hour"
        ),
        calls=status.calls,
        last_call_at=_iso(last_call),
        last_error=status.error,
        sessions=None,
        state=state,
        said=said,
        checked_at=_iso(status.checked_at),
        calendar=(
            "Monday to Friday: no calendar of the US government securities market is "
            "curated yet, so a market holiday is expected and found empty"
        ),
        sources=sources,
        responses_kept=len(kept),
        kept_for=window,
    )


def _duration(seconds: int) -> str:
    hours, rest = divmod(max(seconds, 0), 3600)
    return f"{hours} h {rest // 60:02d} m"


def lag_read(held: SourceStatus, dataset: str) -> records.LagRead:
    lags = held.lags
    if not lags:
        return records.LagRead(dataset=dataset, said="No day first read while watching yet")
    median, longest = int(statistics.median(lags)), max(lags)
    return records.LagRead(
        dataset=dataset,
        days=len(lags),
        median_seconds=median,
        longest_seconds=longest,
        median=f"{_duration(median)} median",
        said=f"{_duration(median)} median, {_duration(longest)} longest, of {len(lags)} days",
    )


def datasets_read(status: Status, feed: Feed | None) -> records.DatasetsRead:
    instance = feed.plugin.identity.instance_id if feed is not None else "us-treasury"
    served = data.served(
        CATALOGUE,
        instance,
        feed.wants if feed is not None else None,
        "Yes: no key needed" if status.read or status.mode == "synthetic" else "Not asked yet",
    )
    served = [replace(s, default_terms=DEFAULT_TERMS) for s in served]
    unread: dict[str, int] = {}
    for held in status.sources.values():
        for line, seen in held.unread.items():
            unread[f"{held.curve.key}: {line}"] = seen
    return records.DatasetsRead(
        served=served,
        wants=list(data.want_rows(feed.wants)) if feed is not None else [],
        reads_instruments=True,
        attribution=ATTRIBUTION,
        records=[
            records.RecordRead(
                dataset=f"{instance}:{curve.key}",
                code=curve.code,
                curve=curve.title,
                rows=ROWS[curve.key],
                instrument_id=status.sources[curve.key].instrument_id,
                miss=status.sources[curve.key].miss,
            )
            for curve in CURVES
        ],
        lag=[lag_read(status.sources[c.key], f"{instance}:{c.key}") for c in CURVES],
        unread=[f"{line} ({n} reads)" for line, n in sorted(unread.items())],
    )


def figures(status: Status, feed: Feed | None) -> list[meridian.Figure]:
    """The data role's figures, in its order (`meridian.roles.data`);
    Treasury's plugin reports none of its own."""
    state, said, why = _state(status)
    if status.mode == "synthetic" and state == "ok":
        connection: Any = "Sample data"
    elif said == "Not answering":
        connection = meridian.Figure("", said, state="error", why=why[:200])
    else:
        connection = meridian.Figure(
            "", "Answering", state="warn" if status.error else None, why=status.error[:200]
        )
    last = feed.wants.counts.last_ns if feed is not None else 0
    return data.figures(
        connection=connection,
        entitled_at_vendor=f"{len(CATALOGUE)} of {len(CATALOGUE)} datasets",
        stream="Does not stream",
        last_recorded=(datetime.fromtimestamp(last / 10**9, UTC) if last else None),
    )


def _moment(value: str) -> str:
    """An ISO moment as a person reads it, to the minute in UTC."""
    if not value:
        return ""
    if len(value) == 10:
        return value
    return datetime.fromisoformat(value).astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _weekday(value: str) -> str:
    return date.fromisoformat(value).strftime("%a %d %b") if value else ""


pages.environment.filters["moment"] = _moment
pages.environment.filters["day"] = _weekday


@pages.page(
    CONNECTION,
    "Connection",
    levels="admin",
    answers=records.ConnectionRead,
    name="read_connection",
    description=(
        "How this plugin reaches the US Treasury's daily interest rate files, as every data "
        "plugin's Connection answers it: the mode (Live or Sample data), no key needed, what "
        "Treasury serves, its limits (none stated) and the requests made, the last check and "
        "why it failed if it did; it does not stream. Then Treasury's own: each file (the par "
        "yield curve, the real par yield curve, the bill rates) with its state, the latest day "
        "it published, the next day expected, its calls and last error, the tenors it states "
        "and how far its history is read back; and how many answers are kept. No rate."
    ),
)
async def connection(request: meridian.Request) -> meridian.Response:
    status, feed = _status()
    read = connection_read(status, feed)
    return pages.answer("connection.html", read, detail=_state(status)[2])


@pages.page(
    DATASETS,
    "Datasets",
    levels="admin",
    answers=records.DatasetsRead,
    name="read_datasets",
    description=(
        "What this plugin serves the lake, as every data plugin's Datasets answers it: its "
        "three datasets as the catalogue declares them (Treasury's daily par yield curve, "
        "real par yield curve and bill rates, as rates, New York's day, kept as US government "
        "work), whether a deployment admin has licensed each, what it recorded and declined; "
        "the standing wants it keeps current and the wants it answered. Then Treasury's own: "
        "how Treasury is cited, the lag between a day's start and the plugin first reading "
        "it, and each curve with the deployment's record for it or why there is none. No rate."
    ),
)
async def datasets(request: meridian.Request) -> meridian.Response:
    status, feed = _status()
    read = datasets_read(status, feed)
    # A browser is drawn the latest wants; a tool answers them all.
    drawn = read if request.tool_name else replace(read, wants=read.wants[:SHOWN_WANTS])
    return pages.answer(
        "datasets.html",
        drawn,
        state=_state(status),
        checked_at=_iso(status.checked_at),
        wants=len(read.wants),
    )
