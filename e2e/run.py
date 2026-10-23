"""`make e2e`: the plugin on the plugin harness of the runtime it pins
(contract v27), beside `reader`, a reporting plugin (e2e/reader.py) entitled
to its datasets, and the harness's admin. Run from the repository's root by
the Makefile, which builds the image and writes the harness's plugins first;
standard library only.

**The harness holds none of the platform's seeded referential records.**
Its stand-in for the platform's master (platform.py, `REFERENTIAL`) holds two
records of its own, matched by FIGI alone, while the platform seeds each
curve by Treasury's title as a `symbol` under `ustreasury`. So here every
curve's record is a miss: reported, its rows waiting, nothing recorded --
which is the plugin's behaviour on any deployment not yet holding the
records, and what this run proves. Recording, curves read back and wants
answered are proved by the tests and the data suite against Treasury's
recorded answers; the read back returns here once the harness holds the
seeded records, with the reader (e2e/reader.py) reading each curve for a date.

1. Treasury unreachable: the plugin's hosts file sends Treasury's site
   nowhere, so its first check fails, and Connection says so -- "Not
   answering", the data role's word -- and records nothing.
2. Sample data on (a developer's setting, accepted on the harness): the
   plugin reads the committed answers, 1 September to 22 October 2026, and
   resolves each curve's record by Treasury's title: none is held, so each
   is reported missing once (`miss|us-treasury|3` in the lake's store),
   Connection says "3 records not resolved", the history waits, and nothing
   is recorded.
3. Parity: through the deployment's MCP, `read_connection` and
   `read_datasets` answer what the pages show, under the data role's names
   -- the latest day, the tenors, each curve's miss -- and core's
   `dashboard__list_datasets` lists the three datasets as the catalogue
   declares them: push and pull, daily, New York's day ending at midnight,
   no calendar.
4. Licensed and entitled at the Data sources page: the reader is entitled,
   and the plugin reads its licences.
5. `store lake` is e2e/expected.lake.
6. A new container: it reads Treasury again, reports each curve's record
   missing once in its own day, and records nothing.
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
PAR = DATASETS[0]
#: Each curve's record, by Treasury's title.
TITLES = [
    "Daily Treasury Par Yield Curve Rates",
    "Daily Treasury Par Real Yield Curve Rates",
    "Daily Treasury Bill Rates",
]


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

    # 2. Sample data: read, each curve's record missing, nothing recorded.
    runner("settings", "sample_data=true")
    runner("page", "--level", "admin", "/", "--until", "Thu 22 Oct", "--seconds", "120")
    runner("page", "--level", "admin", "/", "--until", "3 records not resolved", "--seconds", "60")
    shown = runner("page", "--level", "admin", "/datasets", "--until",
                   "reported missing", "--seconds", "60")
    must(shown.count("not held by the deployment; reported missing") >= 3,
         f"step 2, Datasets shows each curve's record missing: {shown[-800:]}")
    logs = compose("logs", "--no-color", INSTANCE).stdout
    must(all(f"'{title}', 'ustreasury'" in logs for title in TITLES),
         "step 2, each curve's record resolved by Treasury's title under ustreasury: " + logs[-800:])
    must("row|" not in store_lake(), "step 2, nothing recorded while no record resolves")

    # 3. Parity through the deployment's MCP, and core's view of the catalogue.
    runner("grant", "--level", "admin")
    runner("mcp", "connect", "--covers", "deployment_admin", "--covers", f"{INSTANCE}:admin")
    tools = runner("mcp", "list").split()
    read_connection = next((t for t in tools if t.endswith("read_connection")), "")
    read_datasets = next((t for t in tools if t.endswith("read_datasets")), "")
    must(read_connection and read_datasets, f"step 3, the plugin's two tools are listed: {tools}")
    connection = call(read_connection)
    sources = {s["dataset"]: s for s in connection["sources"]}
    must(connection["mode"] == "Sample data" and connection["credentials"] == []
         and connection["sessions"] is None and list(sources) == DATASETS
         and connection["said"] == "3 records not resolved"
         and sources[PAR]["last_release"] == "2026-10-22"
         and sources[PAR]["next_expected"] == "2026-10-23"
         and sources[PAR]["tenors"][:2] == ["1M", "6W"]
         and all(not s["history_done"] and "waiting" in s["history"] for s in sources.values()),
         f"step 3, read_connection: {connection}")
    datasets = call(read_datasets)
    records = {r["dataset"]: r for r in datasets["records"]}
    must(list(records) == DATASETS and all(not r["instrument_id"] and r["miss"] for r in records.values())
         and [r["code"] for r in records.values()] == TITLES
         and [s["dataset"] for s in datasets["served"]] == DATASETS
         and all(s["recorded"] == 0 for s in datasets["served"]),
         f"step 3, read_datasets names each curve's miss: {datasets}")
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
    until(90, lambda: all(s["licensed"] for s in call(read_datasets)["served"]),
          "step 4, the plugin never read its datasets' licences")

    # 5. The lake.
    got = "\n".join(sorted(store_lake().strip().splitlines())) + "\n"
    with open(".e2e/lake", "w", encoding="utf-8") as kept:
        kept.write(got)
    with open("e2e/expected.lake", encoding="utf-8") as held:
        expected = held.read()
    if got != expected:
        diff = subprocess.run(["diff", "-u", "e2e/expected.lake", ".e2e/lake"], capture_output=True, text=True)
        raise Failed(f"step 5, the lake is not e2e/expected.lake:\n{diff.stdout[-3000:]}")

    # 6. A new container records nothing; it reports each miss once in its
    # own day, as a new process does.
    compose("up", "-d", "--no-deps", "--force-recreate", INSTANCE)
    runner("ready")
    until(180, lambda: "3 records not resolved" in page(INSTANCE, "admin", "/"),
          "step 6, the new container did not read Treasury again")
    again = until(60, lambda: (lambda lake: lake if f"miss|{INSTANCE}|6" in lake else None)(store_lake()),
                  "step 6, the new container did not report each miss once")
    must("row|" not in again and again.replace(f"|{INSTANCE}|6", f"|{INSTANCE}|3").strip() == got.strip(),
         f"step 6, the new container recorded something: {again[-800:]}")
    until(90, lambda: all(s["licensed"] for s in call(read_datasets)["served"]),
          "step 6, the new container never read its datasets' licences")

    print(f"e2e OK in {int(time.time() - started)}s on the plugin harness: Treasury unreachable said on "
          f"Connection, nothing recorded; sample data's 1 September to 22 October 2026 read, each "
          f"curve's record resolved by Treasury's title and, the harness holding none, reported "
          f"missing and nothing recorded; read_connection and read_datasets answering what the pages "
          f"show, and core listing the three datasets as declared; licensed and entitled, the "
          f"licences read; `store lake` as e2e/expected.lake; and a new container recording nothing")


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
