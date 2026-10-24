# Overview

The US Treasury publishes its daily interest rates every business day of the
US government securities market: the par yield curve, the real par yield
curve and the bill rates. This plugin reads them from Treasury's daily
Treasury rates files and puts them into your deployment's lake as rates,
where a reporting, portfolio or analytics plugin reads a curve for a date.

It is a data plugin: its first-use path, its two pages and its Summary figures are every data plugin's, described once on [Using a data plugin](https://open-meridian.dev/how-to/using-a-data-plugin/). These sections cover what is Treasury's own.

## Its three datasets

| Dataset | What it holds | Each day |
|---|---|---|
| `ust_par` | The par yield curve: nominal par yields from 1 month to 30 years | One row a tenor, up to 14 |
| `ust_real` | The real par yield curve: TIPS par yields from 5 to 30 years | One row a tenor, 5 |
| `ust_bills` | The bill rates: each bill's bank discount rate and coupon equivalent | Two rows a tenor, 4 to 52 weeks |

Each curve is one record in your deployment, the platform's seeded rate
curve named by Treasury's own title (`Daily Treasury Par Yield Curve Rates`,
`Daily Treasury Par Real Yield Curve Rates`, `Daily Treasury Bill Rates`).
Its points are rows, each with its tenor.

## What a rate means here

A rate is a value in per cent, exactly as Treasury writes it, never a price.

- **10Y 4.96** on the par curve on 22 October 2026 is the 10-year par yield,
  4.96 per cent, bond-equivalent (compounded semi-annually).
- **13W discount 4.04** and **13W coupon equivalent 4.14** on the bill rates
  are two rows for one tenor: the 13-week bill's bank discount rate
  (actual/360, off the face amount) and its yield on the year's actual days.
- Treasury's **1.5-month** point, published since 18 February 2025, is the
  six-week bill's, recorded as the tenor **6W**. The bills keep Treasury's
  weeks: 13W is never turned into 3M.

A tenor Treasury left empty on a day is no row, never a zero: the tenors
published have changed over the years.

## When rates arrive

Treasury publishes each day's rates in the afternoon, New York time, after
the market's closing quotes. The plugin checks the current month and the one
before every hour, and records a day's curve when it appears; a value
Treasury corrects in those weeks becomes the same row's next version.
Treasury states no publication time, so none is recorded. A rate belongs to
its day, New York time.

On its first run the plugin reads each curve's history back, a year at a
time: the par curve from 1990, the real curve from 2003, the bill rates from
2002. That takes a few minutes; Connection shows how far it has read.

Asked for an older day, the plugin reads it from Treasury and records it.
Asked for a weekend, a holiday or a day not published yet, it says the
source has not stated it.

## What it does not do

- It shows no rate on its own pages: rates are read by the plugins that use
  them.
- It never fits, interpolates or bootstraps a curve, and never fills an
  empty tenor: that is the analytics component's.
- It reads no auction results or bond terms.
