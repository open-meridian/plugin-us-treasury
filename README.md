# meridian-us-treasury

The US Treasury's daily interest rates for [Open Meridian](https://open-meridian.dev),
as a data plugin: each business day's **par yield curve**, **real par yield
curve** and **bill rates**, read from Treasury's daily Treasury rates files,
put into a deployment's lake as rates. No key, no account: Treasury's data
are US government work.

| Dataset | What it holds | History |
|---|---|---|
| `ust_par` | Nominal par yields, 1 month to 30 years, bond-equivalent | from 1990 |
| `ust_real` | Real par yields, 5 to 30 years, bond-equivalent | from 2003 |
| `ust_bills` | Each bill's bank discount rate and coupon equivalent, 4 to 52 weeks | from 2002 |

Each curve is one record in the deployment, the platform's seeded rate curve
named by Treasury's title (`ustreasury:Daily Treasury Par Yield Curve
Rates` and the others), and its points are rows, each with its tenor as
Treasury labels it. A tenor Treasury leaves empty is no row, never a zero.

Treasury states no publication time. From 0.2.0 a day that appears in an
hourly read on its own day, the read before (within 70 minutes) not having
stated it, is stated `published` at that read -- the first read that saw
it, so the true publication can be up to an hour earlier -- and each rate's
age at the edge is reported from it (the feed delay, ruling 518); a day
found later (the first read, after a pause, the history, a want) states
none. Version 0.2.1 is built on `open-meridian==0.33.4`, contract v28.

## Using it

Put it in a deployment that `meridian connect` signed you in to, and launch
it:

    meridian plugin upload
    meridian plugin launch us-treasury 0.1.0 --instance us-treasury

Then, on the dashboard's **Data sources** page, a deployment admin licenses
`us-treasury:ust_par`, `:ust_real` and `:ust_bills` and entitles the plugins
that read them. On its first run it reads each curve's history back, which
takes a few minutes; after that it checks Treasury every hour.

Its pages are under **Manage**: Connection (each file's state, latest day,
history read) and Datasets (what it serves, its wants, each curve's record).
Each is also a read tool for agents, `read_connection` and `read_datasets`.
The [docs/](docs/README.md) are what a deployment admin reads on its
Documentation tab.

## Developing it

    make ci-local                     # lint, tests, plugin check, image, e2e
    make preview SHOTS=/tmp/shots     # the pages in a browser, at 375, 582 and 1280 px

Every gate runs in a container. The tests run against Treasury's real
answers, recorded and committed under `src/us_treasury/responses/` and
`tests/responses/`; nothing in CI calls Treasury. `AGENTS.md` is for coding
agents working on it.

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). This project is not
affiliated with or endorsed by the US Department of the Treasury.
