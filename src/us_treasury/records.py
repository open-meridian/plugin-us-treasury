"""The typed records the pages answer, for a person's page and an agent's
tool alike (contract v12; spec/a-deployment-serves-its-mcp): the data role's
common records (`meridian.roles.data`, spec/plugin-pages-follow-their-role),
each extended with Treasury's own fields under the names
spec/a-public-rates-and-filings-data-plugin §5 gives its vendor sections:
Connection's **Sources**, and Datasets' **Records** and **Lag**. The
Connection tab is `read_connection`, the Datasets tab `read_datasets`, each
answering what its page shows, as data, under the role's names.

A data plugin's pages show its connection and its datasets, never a value
(plans/the-lake-prices-the-book, ruled 2026-10-03): rates are the reading
roles' to show. So neither record holds a rate; each says how Treasury was
reached and what the plugin serves of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from meridian.roles import data


@dataclass(frozen=True)
class SourceRead:
    """One source the plugin reads, as "Sources" lists it: one of Treasury's
    files, its state, the last day it published, the next expected, the
    calls made of it and its last error, and how far its history is read."""

    source: str
    dataset: str
    state: str
    last_release: str = ""
    next_expected: str = ""
    calls: int = 0
    last_error: str = ""
    #: The address the plugin reads it at.
    reads: str = ""
    #: The tenors its latest day states, as the lake labels them.
    tenors: list[str] = field(default_factory=list)
    #: Its history: the earliest year read back, whether every year from
    #: its first is read, and why the reading stopped where it did.
    history_from: int | None = None
    history_first_year: int = 0
    history_done: bool = False
    history: str = ""


@dataclass(frozen=True)
class ConnectionRead(data.ConnectionRead):
    """Connection's common fields, then Treasury's: the head's status and
    what it means, the last check, each source as "Sources" lists it, how the
    next day is expected, and the answers kept."""

    #: The head's status: `ok`, `busy`, `warn` or `error`, and what it means.
    state: str = ""
    said: str = ""
    checked_at: str = ""
    #: How the next day is expected: Monday to Friday, no calendar curated.
    calendar: str = ""
    sources: list[SourceRead] = field(default_factory=list)
    responses_kept: int = 0
    kept_for: str = ""


@dataclass(frozen=True)
class RecordRead:
    """One curve, as "Records" lists it: its dataset, Treasury's title for it
    (its `symbol` under `ustreasury`), what its rows are, and the
    deployment's record resolved for it, or why there is none."""

    dataset: str
    code: str
    curve: str
    rows: str
    instrument_id: str
    miss: str


@dataclass(frozen=True)
class LagRead:
    """The "Lag" section, for one dataset: Treasury states no publication
    time, so the lag is the time each day was first read by the plugin's
    hourly check, minus the day's start in New York -- the median and the
    longest, in seconds and in words -- over the days first read while the
    plugin was watching, and how many."""

    dataset: str
    days: int = 0
    median_seconds: int = 0
    longest_seconds: int = 0
    #: The median, and the whole, in words.
    median: str = ""
    said: str = ""


@dataclass(frozen=True)
class DatasetsRead(data.DatasetsRead):
    """Datasets' common fields, then Treasury's: the attribution it is
    cited with, each curve ("Records"), the lag of its days ("Lag"), and
    what it could not read. Its rows are the role's."""

    served: list[data.Served] = field(default_factory=list)
    wants: list[data.WantHeard] = field(default_factory=list)  # type: ignore[assignment]
    attribution: str = ""
    records: list[RecordRead] = field(default_factory=list)
    lag: list[LagRead] = field(default_factory=list)
    #: What a file stated that could not be read, each with how often seen.
    unread: list[str] = field(default_factory=list)
