"""`make e2e`: the plugin on the plugin harness of the runtime it pins
(contract v27), beside `reader`, a reporting plugin (e2e/reader.py) entitled
to its datasets, and the harness's admin. Run from the repository's root by
the Makefile, which builds the image and writes the harness's plugins first;
standard library only. The harness's stand-in for the platform holds the
platform's seeded referential records, matched by `symbol` and the
administrator's source (core a5da59a), so each curve resolves to its `INS-`.

1. Treasury unreachable: the plugin's hosts file sends Treasury's site
   nowhere, so its first check fails, and Connection says so -- "Not
   answering", the data role's word -- and records nothing.
2. Sample data on (a developer's setting, accepted on the harness): the
   plugin reads the committed answers, 1 September to 22 October 2026,
   resolves each curve's record by Treasury's title under `ustreasury` to
   the platform's `INS-`, records 1,188 rates (504 par yields, 180 real par
   yields, 504 bill rates), and reads each curve's history back to its
   first year (the years not recorded answer empty).
3. Parity: through the deployment's MCP, `read_connection` and
   `read_datasets` answer what the pages show, under the data role's names
   -- the latest day, the history read, each curve's `INS-` -- and core's
   `dashboard__list_datasets` lists the three datasets as the catalogue
   declares them: push and pull, daily, New York's day ending at midnight,
   no calendar.
4. Licensed and entitled at the Data sources page: the reader is entitled.
5. Read back, as curves for a date (`rates.read_curve`): the par curve on 22
   October 2026 is 14 points in tenor order, the 10-year 4.96 per cent,
   bond-equivalent; the bills' 13-week tenor two rows, a discount rate and a
   coupon equivalent; the real curve 5 points; each version 1, no published
   time.
6. Wanted: a day Treasury states nothing for -- a Saturday, a day of 2024
   the sample does not hold -- is asked of the plugin and declined
   `source_silent`; a day before 1990 `beyond_history`; the bills' record
   asked of the par curve's dataset `not_covered`.
7. `store lake` is e2e/expected.lake, each curve's record named by its
   dataset's key.
8. A new container: it reads Treasury again and records nothing twice;
   the lake is unchanged.
"""

import json
import os
import subprocess
import sys
import time

PROJECT = "us-treasury-e2e"
LOG = ".e2e/runner.log"
COMPONENTS = ".e2e/components.log"
COMPOSE = ["docker", "compose", "-p", PROJECT, "-f", ".e2e/harness/compose.yaml",
           "-f", ".e2e/harness/plugins.yaml", "-f", "e2e/plugin.yaml"]
INSTANCE = "us-treasury"
DATASETS = [f"{INSTANCE}:ust_par", f"{INSTANCE}:ust_real", f"{INSTANCE}:ust_bills"]
PAR, REAL, BILLS = DATASETS
#: Each curve's record, by Treasury's title.
TITLES = [
    "Daily Treasury Par Yield Curve Rates",
    "Daily Treasury Par Real Yield Curve Rates",
    "Daily Treasury Bill Rates",
]
#: The current months' rates: 36 days of 14, 5 and 14 points.
CURRENT = 36 * (14 + 5 + 14)


class Failed(Exception):
    pass


def log(text):
    with open(LOG, "a", encoding="utf-8") as kept:
        kept.write(text + "\n")


def compose(*args, check=True, timeout=600):
    done = subprocess.run(COMPOSE + list(args), capture_output=True, text=True,
                          timeout=timeout)
    log(f"$ compose {' '.join(args)[:300]}\n{done.stdout[-4000:]}{done.stderr[-2000:]}")
    if check and done.returncode != 0:
        raise Failed(f"compose {' '.join(args)[:200]}: {(done.stdout + done.stderr).strip()[-600:]}")
    return done


def runner(*args, check=True):
    done = compose("run", "--rm", "-T", "runner", *args, check=check)
    return done.stdout if check else done


def must(condition, why):
    if not condition:
        raise Failed(why)


def until(seconds, attempt, what):
    deadline = time.monotonic() + seconds
    last = None
    while True:
        try:
            answer = attempt()
        except Failed as failed:
            answer, last = None, failed
        if answer:
            return answer
        if time.monotonic() > deadline:
            raise Failed(f"{what}, in {seconds} seconds" + (f": {last}" if last else ""))
        time.sleep(2)


def page(instance, level, path):
    said = runner("page", "--instance", instance, "--level", level, path)
    status, _, body = said.partition("\n")
    must(status.strip() == "200", f"{instance} {path} answered {said[-600:]}")
    return body


def call(tool, arguments=None):
    done = runner("mcp", "call", tool, json.dumps(arguments or {}), check=False)
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        raise Failed(f"{tool}: no answer: {(done.stdout + done.stderr)[-400:]}")
    must(answer.get("outcome") in ("read", "unchanged"), f"{tool} answered {done.stdout[-700:]}")
    return answer["data"]


def store_lake():
    return compose("run", "--rm", "-T", "store", "lake").stdout


def curve(subject, day, dataset):
    """The reader's read of a curve for a business date, from one dataset."""
    body = page("reader", "read", f"/curve?subject={subject}&date={day}&dataset={dataset}")
    return json.loads(body)


def named(lines, records):
    """`store lake` with each curve's record, drawn per run, named by its
    dataset's key, each distinct line once."""
    out = []
    for line in lines.strip().splitlines():
        for instrument, key in records.items():
            line = line.replace(instrument, key)
        out.append(line)
    # A want is a line each time the lake asked: how many depends on how
    # often the reader read, so each kind of want is compared once.
    return "\n".join(sorted(set(out))) + "\n"


def run():
    started = time.time()
    compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
    compose("up", "-d")
    runner("ready")
    runner("ready", "--instance", "reader")

    # 1. Treasury unreachable.
    said = runner("page", "--level", "admin", "/", "--until", "Not answering", "--seconds", "90")
    must("ConnectionRefusedError" in said,
         f"step 1, Connection names why Treasury was not reached: {said[-500:]}")
    lake = store_lake()
    must("row|" not in lake, f"step 1, nothing recorded with Treasury unreachable: {lake[-500:]}")

    # 2. Sample data: each record resolved, the current months recorded, the
    # history read back.
    runner("settings", "sample_data=true")
    runner("page", "--level", "admin", "/", "--until", "Thu 22 Oct", "--seconds", "120")
    until(180, lambda: sum(store_lake().count(f"|{d}|") for d in DATASETS) >= CURRENT,
          f"step 2, the {CURRENT} current rates were not recorded")
    runner("page", "--level", "admin", "/", "--until", "read back to 1990", "--seconds", "300")

    # 3. Parity through the deployment's MCP, and core's view of the catalogue.
    runner("grant", "--level", "admin")
    runner("mcp", "connect", "--covers", "deployment_admin", "--covers", f"{INSTANCE}:admin")
    tools = runner("mcp", "list").split()
    read_connection = next((t for t in tools if t.endswith("read_connection")), "")
    read_datasets = next((t for t in tools if t.endswith("read_datasets")), "")
    must(read_connection and read_datasets, f"step 3, the plugin's two tools are listed: {tools}")
    connection = until(300, lambda: (lambda c: c if all(s["history_done"] for s in c["sources"]) else None)(
        call(read_connection)), "step 3, read_connection says every history read")
    sources = {s["dataset"]: s for s in connection["sources"]}
    must(connection["mode"] == "Sample data" and connection["credentials"] == []
         and connection["sessions"] is None and list(sources) == DATASETS
         and connection["said"] == "Sample data"
         and sources[PAR]["last_release"] == "2026-10-22"
         and sources[PAR]["next_expected"] == "2026-10-23"
         and sources[PAR]["history_from"] == 1990 and sources[REAL]["history_from"] == 2003
         and sources[BILLS]["history_from"] == 2002
         and sources[PAR]["tenors"][:2] == ["1M", "6W"],
         f"step 3, read_connection: {connection}")
    datasets = call(read_datasets)
    records = {r["dataset"]: r["instrument_id"] for r in datasets["records"]}
    must(list(records) == DATASETS and all(i.startswith("INS-") for i in records.values())
         and [r["code"] for r in datasets["records"]] == TITLES
         and [s["dataset"] for s in datasets["served"]] == DATASETS,
         f"step 3, read_datasets names each curve's INS- record: {datasets}")
    shown = page(INSTANCE, "admin", "/datasets")
    must(all(i in shown for i in records.values()), "step 3, Datasets shows what read_datasets answers")
    listed = {d["dataset"]: d for d in call("dashboard__list_datasets")["datasets"]}
    for dataset in DATASETS:
        entry = listed.get(dataset, {}).get("catalogue_entry", {})
        must(entry.get("modes") == ["push", "pull"] and entry.get("day_time_zone") == "America/New_York"
             and not entry.get("day_end_minute") and entry.get("cadence") == 86400
             and not entry.get("calendar_id"),
             f"step 3, core lists {dataset} as declared: {listed.get(dataset)}")

    # 4. Licensed and entitled.
    for dataset in DATASETS:
        runner("licence", dataset, "kept=true", "retention_days=0", "derived_use=true", "display=true",
               "personal_use=false", "note=Treasury's daily rates: US government work.")
        runner("entitle", "--instance", "reader", dataset, "note=The e2e's reader reads the curves.")
    runner("grant", "--instance", "reader", "--level", "read")

    # 5. Read back, as curves for a date.
    par = until(60, lambda: (lambda r: r if len(r["rates"]) == 14 else None)(
        curve(records[PAR], "2026-10-22", PAR)), "step 5, the par curve of 22 October was not read")
    tenors = [r["tenor"] for r in par["rates"]]
    ten = [r for r in par["rates"] if r["tenor"] == "10Y"]
    must(tenors == ["1M", "6W", "2M", "3M", "4M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
         and ten and ten[0]["value"] == "4.96" and ten[0]["kind"] == "RATE_KIND_PAR_YIELD"
         and ten[0]["unit"] == "VALUE_UNIT_PERCENT" and ten[0]["subject"] == records[PAR]
         and ten[0]["convention"] == ["DAY_COUNT_ACT_ACT", "COMPOUNDING_COMPOUNDED", 2]
         and ten[0]["version"] == 1 and ten[0]["published"] == []
         and ten[0]["business_date"] == "2026-10-22",
         f"step 5, the par curve in tenor order, the 10-year as Treasury states it: {par}")
    bills = curve(records[BILLS], "2026-10-22", BILLS)["rates"]
    thirteen = sorted((r["kind"], r["value"]) for r in bills if r["tenor"] == "13W")
    must(len(bills) == 14 and thirteen == [("RATE_KIND_COUPON_EQUIVALENT", "4.14"),
                                           ("RATE_KIND_DISCOUNT", "4.04")],
         f"step 5, the bills' 13-week tenor two rows: {bills}")
    real = curve(records[REAL], "2026-10-22", REAL)["rates"]
    must(len(real) == 5 and real[0]["tenor"] == "5Y", f"step 5, the real curve's five points: {real}")

    # 6. Wants: days Treasury states nothing for, one before the history, a
    # subject not covered, each asked of the plugin and declined with why.
    def declined(subject, day, dataset, reason):
        said = curve(subject, day, dataset)
        return not said["rates"] and [u["reason"] for u in said["unanswered"]] == [reason]

    for subject, day, dataset, reason in (
        (records[PAR], "2026-10-17", PAR, "UNANSWERED_REASON_SOURCE_SILENT"),
        (records[PAR], "2024-03-15", PAR, "UNANSWERED_REASON_SOURCE_SILENT"),
        (records[PAR], "1985-06-03", PAR, "UNANSWERED_REASON_BEYOND_HISTORY"),
        (records[BILLS], "2026-10-22", PAR, "UNANSWERED_REASON_NOT_COVERED"),
    ):
        until(90, lambda: declined(subject, day, dataset, reason),
              f"step 6, {subject} on {day} from {dataset} was not declined {reason}")
    lake = store_lake()
    must(f"want|{PAR}|declined|{records[PAR]}|" in lake and f"want|{PAR}|declined|{records[BILLS]}|" in lake,
         f"step 6, the lake holds the plugin's declines: {[l for l in lake.splitlines() if l.startswith('want|')]}")

    # 7. The lake.
    names = {instrument: dataset.split(":")[1] for dataset, instrument in records.items()}
    got = named(store_lake(), names)
    with open(".e2e/lake", "w", encoding="utf-8") as kept:
        kept.write(got)
    with open("e2e/expected.lake", encoding="utf-8") as held:
        expected = held.read()
    if got != expected:
        diff = subprocess.run(["diff", "-u", "e2e/expected.lake", ".e2e/lake"], capture_output=True, text=True)
        raise Failed(f"step 7, the lake is not e2e/expected.lake:\n{diff.stdout[-3000:]}")

    # 8. A new container records nothing twice.
    compose("up", "-d", "--no-deps", "--force-recreate", INSTANCE)
    runner("ready")
    until(180, lambda: "3 of 3 answering, latest Thu 22 Oct" in page(INSTANCE, "admin", "/"),
          "step 8, the new container did not read Treasury again")
    until(300, lambda: all(s["history_done"] for s in call(read_connection)["sources"]),
          "step 8, the new container did not read the history on")
    again = named(store_lake(), names)
    must(again == got, "step 8, the new container recorded something twice:\n"
         + subprocess.run(["diff", "-u", "-", ".e2e/lake"], input=again, capture_output=True, text=True).stdout[-2000:])
    logs = compose("logs", "--no-color", INSTANCE).stdout
    must("ust_par to 2026-10-22: 0 recorded, 0 restated, 504 unchanged" in logs,
         "step 8, the new container's check was answered unchanged: " + logs[-800:])
    until(90, lambda: all(s["licensed"] for s in call(read_datasets)["served"]),
          "step 8, the new container never read its datasets' licences")

    rows = got.count(f"|{PAR}|") + got.count(f"|{REAL}|") + got.count(f"|{BILLS}|")
    print(f"e2e OK in {int(time.time() - started)}s on the plugin harness: Treasury unreachable said on "
          f"Connection, nothing recorded; sample data's 1 September to 22 October 2026 recorded "
          f"({CURRENT} rates), each curve's record resolved by Treasury's title to its INS- and each "
          f"history read back; read_connection and read_datasets answering what the pages show, and "
          f"core listing the three datasets as declared; licensed and entitled; the par curve of 22 "
          f"October read in tenor order (10-year 4.96, bond-equivalent), the bills' two conventions a "
          f"tenor, the real curve's five points; a Saturday and an empty day declined source silent, "
          f"1985 beyond history and a record not covered; `store lake` as e2e/expected.lake ({rows} "
          f"lines of the datasets); and a new container recording nothing twice, its licences read "
          f"on start")


def main():
    os.makedirs(".e2e", exist_ok=True)
    open(LOG, "w").close()
    try:
        run()
    except (Failed, subprocess.TimeoutExpired, KeyError, ValueError, IndexError, TypeError) as failed:
        with open(COMPONENTS, "a", encoding="utf-8") as kept:
            kept.write(compose("logs", "--no-color", check=False).stdout)
        compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
        print(f"e2e FAILED: {failed}; the runner's log is in {LOG}, the components' in {COMPONENTS}",
              file=sys.stderr)
        return 1
    compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
