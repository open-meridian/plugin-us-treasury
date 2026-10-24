# Pages

Both pages are the data role's, the same on every data plugin, under
**Manage**, for the plugin's admins. Neither shows a rate. Each is also a
read tool on the deployment's MCP, answering what the page shows, under the
same names on every data plugin.

## Connection (`read_connection`)

How the plugin reaches Treasury, and how the last check went:

- the head's status: answering, checking, not answering, or curves'
  records not resolved;
- **Key:** the mode (Live or Sample data), "No key needed", and what
  Treasury serves;
- **Limits and use:** the limits it keeps (Treasury states none; one
  request at a time, at most one every two seconds, a check every hour),
  the requests made, the last check and error; and **Sources**, how many of
  Treasury's three files answer and the latest day published. Its `…` opens
  each file -- the par yield curve, the real par yield curve, the bill rates
  -- with its state, last day published, next day expected, calls, how far
  its history is read back, the tenors its latest day states and its last
  error; then the calendar and how many answers are kept;
- **Stream:** it does not stream.

## Datasets (`read_datasets`)

What the plugin serves:

- **Served:** its three datasets as the deployment's catalogue lists them,
  with the terms each declares and whether a deployment admin has licensed
  it, what it recorded and declined; then, one dataset being one curve,
  its **Record**, the deployment's record for the curve or why there is none
  (the heading cites Treasury as the source), and its **Lag**: Treasury
  states no publication time, so the median time from a day's start in New
  York to the plugin first reading it, over the days first read while it was
  watching;
- **Wants:** the standing wants it keeps current, and the last wants it
  answered; **Subjects**.
