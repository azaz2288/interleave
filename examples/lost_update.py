"""True spawned processes: intentionally broken read/check/write CAS vs transactional CAS.

Only a new TemporaryDirectory SQLite database is touched. Each worker records call/return
using the same host monotonic perf_counter_ns clock. A barrier makes the race reproducible.
"""

import argparse
import json
import multiprocessing as mp
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from threading import BrokenBarrierError

from interleave import check, minimize, replay


def worker(database, ident, fixed, barrier, outputs):
    connection = None
    try:
        connection = sqlite3.connect(database, timeout=10, isolation_level=None)
        started = time.perf_counter_ns()
        if fixed:
            barrier.wait(timeout=10)
            connection.execute("BEGIN IMMEDIATE")
            observed = connection.execute("SELECT value FROM register").fetchone()[0]
        else:
            observed = connection.execute("SELECT value FROM register").fetchone()[0]
            barrier.wait(timeout=10)
        success = observed == 0
        if success:
            connection.execute("UPDATE register SET value=?", (ident,))
        if fixed:
            connection.commit()
        finished = time.perf_counter_ns()
        connection.close()
        outputs.put(
            {
                "id": str(ident),
                "process": str(ident),
                "call": started,
                "return": finished,
                "kind": "cas",
                "input": [0, ident],
                "output": success,
            }
        )
    except (sqlite3.Error, OSError, BrokenBarrierError) as error:
        outputs.put({"error": str(error)})
    finally:
        if connection is not None:
            connection.close()


def experiment(fixed):
    context = mp.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix="interleave-synthetic-") as folder:
        path = Path(folder) / "register.sqlite3"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE register(value INTEGER NOT NULL)")
            connection.execute("INSERT INTO register VALUES(0)")
            connection.commit()
        barrier = context.Barrier(2)
        outputs = context.Queue()
        processes = [
            context.Process(target=worker, args=(str(path), i, fixed, barrier, outputs))
            for i in (1, 2)
        ]
        try:
            for process in processes:
                process.start()
            operations = [outputs.get(timeout=20) for _ in processes]
            for process in processes:
                process.join(timeout=20)
                if process.exitcode != 0:
                    raise RuntimeError("worker failed")
            if any("error" in operation for operation in operations):
                raise RuntimeError(operations)
            history = {
                "schema": 1,
                "model": "register",
                "initial": 0,
                "operations": sorted(operations, key=lambda op: op["id"]),
            }
            report = check(history)
            if report["status"] == "linearizable":
                replay(history, report["witness"])
            else:
                report["counterexample"] = minimize(history)
            return {
                "implementation": "transactional CAS" if fixed else "broken read/check/write CAS",
                "synthetic": True,
                "history": history,
                "audit": report,
            }
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=10)
            outputs.close()
            outputs.join_thread()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    reports = [experiment(False), experiment(True)]
    if [item["audit"]["status"] for item in reports] != [
        "nonlinearizable",
        "linearizable",
    ]:
        raise SystemExit("experiment did not satisfy acceptance")
    data = json.dumps(reports, indent=2)
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(data + "\n")
    print(data)


if __name__ == "__main__":
    main()
