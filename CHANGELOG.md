# Changelog

## 0.1.0

The US Treasury's daily interest rates as a data plugin, on the lake's rates
slice (contract v27, SDK 0.32.1; spec/a-public-rates-and-filings-data-plugin,
`plugin-us-treasury`, rulings 343 to 349).

- Three datasets of rates: `ust_par` (the par yield curve), `ust_real` (the
  real par yield curve) and `ust_bills` (the bill rates), read from
  Treasury's daily Treasury rates files with no key, through the SDK's
  `roles.data.rates` helpers. Each curve is the platform's seeded
  referential record named by Treasury's title under `ustreasury`; its
  points are rows, each with its tenor as Treasury labels it, its kind and
  its convention; a bill's discount rate and coupon equivalent two rows a
  tenor.
- Pushed hourly from the current months, a correction the same row's next
  version; each curve's history read back on the first run, to 1990, 2003
  and 2002; a past day pulled when the lake wants it.
- Raw responses kept from day one, as the SDK's storage settings say.
- The data role's Connection (with Sources) and Datasets (with Lag and
  Records), each a read tool; terms as US government work.
- The data suite at v27: the rates cases Treasury presents mapped, the rest
  not presented with why (the SDK's `RATES_NOT_PRESENTED`, ruling 538), the
  latency cases waiting for v28 (ruling 518).
