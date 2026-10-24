"""What this version declares beside its role, `data` (W8.1, W4.1; the
catalogue from contract v18, the Rate kind from v27), built from code and
used twice: `__main__` registers with it, and `meridian plugin upload` reads
it from the built image (pyproject.toml's `[tool.meridian] declaration`).

**The catalogue: three datasets, `ust_par`, `ust_real` and `ust_bills`**
(spec/a-public-rates-and-filings-data-plugin §3, their keys approved with
the batch, 2026-10-14, and placed in this plugin by ruling 343). Treasury's
daily par yield curve, real par yield curve and bill rates, each day's
pushed when Treasury publishes it, and any past day pulled when the lake
wants it:

- `vendor` the U.S. Department of the Treasury; no aggregator, since the
  plugin reads Treasury's own files;
- `data_types` rates alone (`meridian.v1.Rate`, contract v27): a par yield,
  a discount rate and a coupon equivalent are rates, never prices;
- `modes` `push` (each day's curve recorded when it appears) and `pull` (a
  past day, on a want);
- `cadence` a day, in seconds: Treasury publishes each business day of the
  US government securities market;
- `history` as the spec's table has it: the par curve from 1990 (about
  13,400 days), the real curve from 2003 (8,400) and the bill rates from
  2002 (8,700); the plugin reads it back on its first run (feed.py);
- its day New York's, ending at midnight (`America/New_York`, 0);
- **no calendar**: Treasury's days follow SIFMA's bond-market closes, which
  no calendar the platform curates holds yet; the spec's Q15 says to declare
  none until one is curated, so the plugin assumes Monday to Friday;
- no venue: Treasury's curves are its own, no venue's;
- the licence its terms suggest: kept, derived use not restricted, and
  display, with no limit on retention, and not one person's terms. The data
  are US government work: no attribution is required, and the plugin cites
  Treasury as the source on its Datasets page and in docs/terms.md. A
  deployment's licence confirms or replaces the default on the Data sources
  page; the plugin says nothing of whether a deployment meets anyone's
  terms.

**Storage:** Treasury's answers (raw.py), archivable, ten years by default.
"""

from __future__ import annotations

from meridian import DatasetDeclaration, DatasetLicence
from meridian.declaration import RecordKind

from .curves import BILLS, PAR, REAL, Curve
from .raw import DEFAULT_WINDOW_DAYS, RESPONSES

VENDOR = "U.S. Department of the Treasury"
RATE = "meridian.v1.Rate"
#: A day, in seconds.
CADENCE = 86_400
#: New York's day, ending at midnight.
DAY_TIME_ZONE = "America/New_York"
DAY_END_MINUTE = 0
#: Each dataset's history, in days, as the spec's catalogue states it.
HISTORY = {PAR.key: 13_400, REAL.key: 8_400, BILLS.key: 8_700}


def declared(curve: Curve) -> DatasetDeclaration:
    return DatasetDeclaration(
        key=curve.key,
        vendor=VENDOR,
        data_types=[RATE],
        modes=["push", "pull"],
        cadence=CADENCE,
        history=HISTORY[curve.key],
        licence_default=DatasetLicence(
            kept=True, derived_use=True, derived_use_terms="not_restricted", display=True
        ),
        day_time_zone=DAY_TIME_ZONE,
        day_end_minute=DAY_END_MINUTE,
    )


CATALOGUE = [declared(curve) for curve in (PAR, REAL, BILLS)]

RESPONSES_KIND = RecordKind(RESPONSES, "Raw responses", window_days=DEFAULT_WINDOW_DAYS)
