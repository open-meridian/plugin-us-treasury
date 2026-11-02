"""The US Treasury's daily interest rates as an Open Meridian data plugin
(spec/a-public-rates-and-filings-data-plugin, `plugin-us-treasury`; one
plugin per publisher's feed, rulings 343 to 349): the par yield curve, the
real par yield curve and the bill rates of each business day into the
deployment's lake, as rates, each curve one referential record and its
points rows.

It runs its data role class, `Lake` (feed.py's `Feed`, with its lifecycle
here), with `meridian.run` on the sidecar it is launched beside, declaring
its catalogue, its storage and its one setting (declaration.py);
`meridian.run` delivers the settings, serves its two pages (page.py), hands
it what the lake wants of it, and sets the data role's figures on each
heartbeat. It reads Treasury's current months at start and every hour,
recording what changed, and reads back each curve's history on its first
run (feed.py). What Treasury answered is kept in the storage the deployment
grants (raw.py), and moved past its window as the settings say. It reads
which of its datasets a deployment admin has licensed, on start and every
minute. It holds nothing else: a restart reads Treasury again, and the lake
answers what it recorded before unchanged.

Everything it says to the deployment goes through the sidecar; everything it
reads comes from Treasury's public site, or with sample data from the
answers committed with it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import meridian

from .declaration import DECLARATION, PORT
from .feed import Feed
from .page import figures, hold, pages
from .raw import RawStore
from .settings import Config, config_from
from .treasury import source

log = logging.getLogger("us_treasury")

#: How often the current months are checked, in seconds: hourly.
CHECK_SECONDS = 3600
#: How often storage is tended past its window, in seconds: daily.
TEND_SECONDS = 86_400
#: How often the datasets' licences are read again.
LICENCES_SECONDS = 60


class Lake(Feed):
    """The data role's class with its lifecycle (open-meridian 0.35, rulings
    1004, 1005, 1009 to 1023): `meridian.run` delivers each settings to
    `on_settings` -- the first before anything is heard -- and starts `run`,
    again after a backoff should it fail."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.config = Config()
        self.wake = asyncio.Event()

    async def on_settings(self, delivered: Any) -> None:
        """Apply each delivery of the settings: sample data on or off, and the
        answers' window, tended at once."""
        config = config_from(delivered.values)
        self.config = config
        self.use(source(config.sample_data))
        self.wake.set()
        await self.raw.tend(self.plugin, config.window_days, config.past_window, self.now())

    async def run(self) -> None:
        """The current months checked and the history read on, storage
        tended, the licences read, and the feed delay reported (contract
        v28, ReportLatency)."""
        await asyncio.gather(self._check(), self._tend(), self._licences(), self.latency.run())

    async def _check(self) -> None:
        """Read the current months at once, then hourly, or at once when the
        settings change; after each check, read on with the history where it
        is not all read."""
        while True:
            self.wake.clear()
            try:
                await self.check()
                await self.history()
            except meridian.MeridianError as failed:
                # The sidecar refused something a recording needed; say so and
                # keep the schedule rather than spin.
                for held in self.status.sources.values():
                    held.error = held.error or f"the deployment refused a recording: {failed}"
                log.warning("this check stopped: %s", failed)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.wake.wait(), timeout=CHECK_SECONDS)

    async def _tend(self) -> None:
        while True:
            await asyncio.sleep(TEND_SECONDS)
            config = self.config
            await self.raw.tend(self.plugin, config.window_days, config.past_window, self.now())

    async def _licences(self) -> None:
        """Its own declared datasets' licences (contract v20, W10.9), read on
        start and every minute, for the Datasets page."""
        while True:
            try:
                await self.wants.read_licences()
            except meridian.MeridianError as failed:
                log.warning("the datasets' licences were not read this time: %s", failed)
            await asyncio.sleep(LICENCES_SECONDS)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    lake = Lake(source(False), RawStore())
    hold(lake)
    # The version's whole declaration (declaration.py): its settings, its
    # pages with the levels each serves and their tools, and its
    # documentation. A version registers exactly what it was uploaded with
    # (contract v25).
    meridian.run(
        declaration=DECLARATION,
        roles=[lake],
        pages=pages,
        port=PORT,
        on_settings=lake.on_settings,
        figures=lambda: figures(lake.status, lake),
    )


if __name__ == "__main__":
    main()
