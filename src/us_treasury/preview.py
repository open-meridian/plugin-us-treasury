"""The pages on sample data, each printed as one HTML file:
for looking at them without a deployment.

    python -m us_treasury.preview connection > preview/connection.html
    python -m us_treasury.preview datasets > preview/datasets.html

The plugin's work runs on the SDK's lake as a test stands it in, in place of
a sidecar -- each curve resolved to a record the stand-in names, every batch
recorded -- against the answers committed under responses/, at noon in New
York on 23 October 2026: the current months read, the history read back
(the years not recorded answered empty), a want for 25 September answered,
one for Saturday 17 October declined (Treasury publishes nothing on a
weekend), and a standing want kept current. Each page links the kit where
the dashboard serves it, /.meridian/ui/<version>/: served beside the kit it
is styled (meridian-ui's `make serve`, or `make preview SHOTS=...`, which
checks each in a browser); opened on its own it is the page without the kit,
unstyled, which works too. `connection-first` and `datasets-first` are the
pages before the first check, with no want yet: the role's "not set up yet"
states.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

from meridian.plugin.v1 import operations_pb2 as ops
from meridian.receive import Heard
from meridian.roles.data.testing import Lake
from meridian.testing import PageClient

from .curves import ADMINISTRATOR, CURVES
from .feed import Feed
from .page import CONNECTION, DATASETS, hold, pages
from .raw import RawStore
from .treasury import SyntheticTreasury

AT = datetime(2026, 10, 23, 16, 0, tzinfo=UTC)
PAGES = {
    "connection": CONNECTION,
    "datasets": DATASETS,
    "connection-first": CONNECTION,
    "datasets-first": DATASETS,
}


def _want(want_id: str, subject: str, day: str = "", standing: bool = False) -> Heard:  # type: ignore[type-arg]
    return Heard(
        row="ObservationsWanted",
        message=ops.ObservationsWantedEvent(
            want_id=want_id,
            dataset="us-treasury:ust_par",
            data_type="meridian.v1.Rate",
            subjects=[ops.SubjectRef(entity_id=subject)],
            business_date=day,
            standing=standing,
        ),
    )


def _feed() -> Feed:
    lake = Lake("us-treasury")
    for curve in CURVES:
        lake.instruments.hold(
            f"INS-PREVIEW-{curve.key.upper().replace('_', '-')}",
            ops.Identifier(scheme="symbol", value=curve.code, source=ADMINISTRATOR),
            asset_class=ops.ASSET_CLASS_REFERENTIAL,
        )
    return Feed(lake, SyntheticTreasury(lambda: AT), RawStore(), now=lambda: AT)


async def synthetic_feed() -> Feed:
    """A feed as sample data leaves it, on the stand-in lake."""
    feed = _feed()
    await feed.check()
    await feed.history()
    par = feed.status.sources["ust_par"].instrument_id
    await feed.on_want(_want("want-0925", par, "2026-09-25"))
    await feed.on_want(_want("want-1017", par, "2026-10-17"))
    await feed.on_want(_want("want-standing", par, standing=True))
    return feed


def render(page: str) -> str:
    feed = _feed() if page.endswith("-first") else asyncio.run(synthetic_feed())
    hold(feed)
    answer = PageClient(pages).get(PAGES[page], "admin")
    if answer.status != 200:
        raise SystemExit(f"{page} answered {answer.status}: {answer.text[:200]}")
    return answer.text


def main() -> None:
    page = sys.argv[1] if len(sys.argv) > 1 else "connection"
    if page not in PAGES:
        raise SystemExit(f"no page {page!r}: {', '.join(PAGES)}")
    sys.stdout.write(render(page))


if __name__ == "__main__":
    main()
