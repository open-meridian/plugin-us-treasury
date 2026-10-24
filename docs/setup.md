# Setup

## Launching it

Treasury's rates need no key and no account: the files are public. Launch
the plugin and approve its one role, `data` (a data plugin). It reads
Treasury at once, and every hour after; on its first run it also reads the
three curves' history back.

Its settings, in the dashboard's Settings form:

- **Raw responses window** and **past the window** (the SDK's): how long
  Treasury's answers are kept in the plugin's storage, ten years by default,
  and whether they are then archived, kept or deleted.
- **Sample data**, on a deployment installed for development only:
  Treasury's rates of 1 September to 22 October 2026, recorded on 23
  October 2026 and committed with the plugin, in place of Treasury's site.
  For trying it offline.

## Its datasets

On the deployment's **Data sources** page (deployment admins):

1. **License** `<instance>:ust_par`, `<instance>:ust_real` and
   `<instance>:ust_bills`. Each catalogue default is kept, with derived use
   not restricted and display, no limit on retention, and not one person's
   terms: Treasury's data are US government work. Confirm the default, or
   set your own, with a note saying why.
2. **Entitle** each plugin that reads rates, such as your reporting or
   analytics plugin.
3. **Priority**, where another dataset also records these curves' points
   (the Federal Reserve Board's H.15, FRED's Treasury series): put the one
   your readers should read first.

## The curves' records

Each dataset's rows are about one record, the platform's seeded rate curve,
found by Treasury's title as a `symbol` scoped to `ustreasury`. The Datasets
tab shows each curve's record, or why there is none. A curve without one
waits: its rows are recorded once it resolves, at the next check. If your
deployment does not hold them, pull them from the platform at the
Instruments page.

## No calendar yet

Treasury's days follow the bond market's closes (SIFMA's), which no
calendar the platform curates holds yet. The datasets declare none, and the
plugin expects a new day Monday to Friday: on a market holiday it finds
nothing, and says so.
