# Changelog

## 0.2.0

On open-meridian 0.33.1, contract v28 (plugin-common-v28), on core v28's
harness.

- **A day's published time** (decided under the working agreement
  2026-10-26, after plugin-ny-fed's): Treasury states none. A day first
  stated by an hourly read on its own day, the read before (within 70
  minutes) not having stated it, is stated `published` at that read -- the
  first read that saw it, so the true publication can be up to an hour
  earlier. A day found later (a process's first read, after a pause, the
  history, a want, a past day) states none. The time is noted beside the
  rate's first answer (raw.py), so a rate read again, in this process or
  the next, states the same. Tested both ways (tests/test_published.py).
- **The feed delay, reported** (ruling 518, required again from contract
  v28): each rate recorded unasked or for a standing want has its age at
  the edge recorded from that time (`roles.Latency` on the SDK's `Wants`),
  reported every 10 seconds (`ReportLatency`); `reports-its-feed-delay` is
  presented on 22 October's par curve appearing between two reads.
- **The suite's v28 cases:** option chains, filings and the quality of
  quotes not presented, the SDK's `RATES_NOT_PRESENTED`.
- **`meridian plugin migrate`** (to_0_33_0, to_0_33_1): e2e/reader.py's
  SubjectRefs are `meridian.SubjectRef` (ruling 599).
- **The pins:** open-meridian 0.33.1 and plugin-python:0.33.1 by tag and
  digest; core v28's runtime and harness at `8def82a` (chart 0.1.313) by
  digest; `meridian` 0.1.52 in check.yaml (was 0.1.51).

## 0.1.0

The US Treasury's daily interest rates as a data plugin, on the lake's rates
slice (contract v27, SDK 0.32.2; spec/a-public-rates-and-filings-data-plugin,
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
- Raw responses kept from day one, as the SDK's storage settings say; each
  rate names the answer it was first read from, so a rate read again is the
  same row.
- The data role's Connection (with Sources) and Datasets (with Lag and
  Records), each a read tool; terms as US government work.
- The data suite at v27: the rates cases Treasury presents mapped, the rest
  not presented with why (the SDK's `RATES_NOT_PRESENTED`, ruling 538), the
  latency cases waiting for v28 (ruling 518).
