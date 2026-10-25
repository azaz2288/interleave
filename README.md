# Interleave

**Find concurrency bugs that successful API responses conceal.** A dependency-free Python3.12+ bounded exact linearizability auditor for atomic read/write/CAS registers and bounded FIFO queues.

Two overlapping `CAS(0,1) → true` and `CAS(0,2) → true` cannot both be correct. Interleave exhausts interval-respecting sequential explanations, reports the contradiction, and reduces it to a replayable input. Legal histories get a separately checked witness. Exhausted search gets **inconclusive**, never a fabricated pass/fail.

## Run
```powershell
python -m unittest discover -s tests -v
python -m examples.lost_update
python -m interleave examples/double-cas.json --minimize
```
The last command intentionally exits1: the supplied synthetic example is invalid under atomic CAS. The multiprocessing experiment creates a **new temporary SQLite DB**, reproduces broken read/check/write with a barrier, then tests transactionally serialized CAS. It never connects to an external service or opens existing data.

Optional install: `python -m pip install .`, then `interleave HISTORY.json` from any directory. No runtime packages are required.

## Input
```json
{"schema":1,"model":"register","initial":0,"operations":[
 {"id":"a","process":"p1","call":10,"return":20,"kind":"cas","input":[0,1],"output":true},
 {"id":"b","process":"p2","call":11,"return":21,"kind":"cas","input":[0,2],"output":true}
]}
```
Each process is sequential; timestamps use **one shared monotonic clock**. `return:null, output:null` denotes an unfinished call: it may be omitted or completed with a legal model result. Cross-process equal timestamps overlap. Signed64 integer values, max64 operations, CLI input2MiB. Queue initial state is `{"capacity":2,"values":[]}`; enqueue returns bool, dequeue returns integer or null for empty. Register write returns null, read integer, CAS bool.

Exit0=linearizable,1=nonlinearizable,2=invalid input,3=inconclusive. `--max-states 200000 --timeout 5` bounds each check; minimization has its own global timeout. Output includes canonical input SHA256, budgets, actual explored states/time, assumptions, witness and a diagnostic legal prefix. `--minimize` adds a reduced history; `one_minimal` is **single-deletion minimal**, not globally smallest. Failed/budget-limited reduction does not claim minimality.

## Why this is more than response checking
Bitset precedence and memoized state-space search jointly enforce real-time order and sequential semantics. The test oracle independently enumerates permutations/pending subsets and implements separate models; it does not call the production transition function. The experiment uses actual spawned OS processes, not mocked interleavings.

## Limits
Exponential worst case; bounded history correctness is not implementation-wide proof. No multi-machine clock repair, multi-key partitioning, arbitrary transaction serializability, distributed fault injection or formal rejection certificates. A minimal observation set may not execute in isolation on the original target. No throughput/production-scale claim; see [design](docs/DESIGN.md), [roadmap](docs/ROADMAP.md), [evidence](docs/PROGRESS.md).
