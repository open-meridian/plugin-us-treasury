# Troubleshooting

## Connection

| What you see | What it means | What to do |
|---|---|---|
| **Not answering** | No check has reached Treasury's site: no network, a proxy, or the site down | Check the deployment's outbound access to home.treasury.gov; the plugin tries again every hour |
| **Answering**, with a warning | An earlier check worked; the last did not | Nothing, usually: the next check runs within the hour. The detail says what failed |
| Sources: history **read back to** a year, with an error | Reading the history stopped at that year | Nothing: it reads on from there at the next check |

## Curves and records

| What you see | What it means | What to do |
|---|---|---|
| **N records not resolved** | A curve's title found no record in your deployment, or two | Pull or merge the platform's rate curve at the Instruments page; the next check records its rows |
| Something the plugin could not read | Treasury stated a column or a value it does not know | It is not recorded; the Datasets page lists it |
| A tenor missing on a day | Treasury left it empty that day | Nothing: no row is recorded, and a reader sees the source silent for it |

## Wants and licences

| What you see | What it means | What to do |
|---|---|---|
| A day declined, *source silent* | A weekend, a market holiday, or a day not published yet | Wait for the next business day's rates, in the New York afternoon |
| A day declined, *beyond history* | Before the curve's first year: 1990, 2003 or 2002 | Nothing: Treasury publishes nothing earlier |
| A subject declined, *not covered* | Each dataset covers its one curve; another record, a price or a kind it does not state is not Treasury's | Read the curve's own record, from its own dataset |
| Datasets: **Not licensed yet** | No deployment admin has licensed the dataset | Ask a deployment admin to license it on Data sources; the page says so within a minute |
