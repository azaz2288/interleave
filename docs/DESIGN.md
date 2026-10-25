# Interleave v0.1.0

This is a bounded exact checker, not a load generator with a pass-rate dashboard. Input is an interval history of a single register (read/write/CAS) or bounded FIFO queue (enqueue/dequeue). It asks whether all completed responses can be explained by a legal sequential execution respecting real-time precedence. CAS is atomic in the sequential specification; a read/check/write implementation is not silently accepted as CAS.

## Algorithm
Precompute predecessor bitsets from completed return < invocation and sequential process order. DFS chooses ready operations, executes a pure sequential model and compares the observed result. Memoize `(selected-bitmask, immutable-state)`. Pending calls can be omitted or included with a model-generated response; completed operations cannot be omitted. Monotone bitmasks make the search DAG acyclic. Return a replayable witness on success, exhaustive rejection on failure, or explicit inconclusive on time/state exhaustion. Maximum64 operations; exponential worst case.

Global timestamps must use one monotonic clock. Equal cross-process timestamps are interpreted as overlapping, not a proven before relation; same-process order is preserved. Input timestamps and values are signed64 integers, bool is not int. Sequential clients only, pending last. No cross-machine clock correction or crash durability inference. A legal witness proves only that one supplied history matches one model, not that the implementation is correct for all histories.

Counterexample reduction deletes one operation only when the remaining history is exactly rejected. Global deadline bounds the whole reduction. `one_minimal` means no single deletion preserves rejection, not minimum cardinality or causal blame. An unfinished reduction says so. Initial state is held fixed; reduced observations need not be executable alone on the original system.

## Evidence
CLI outputs canonical-history SHA256, model/assumptions, budget, state count, elapsed time, witness and deepest legal prefix (diagnostic only, not a proof certificate of rejection). Witness replay separately enforces precedence/results/completeness. Tests independently enumerate permutations and pending subsets using separately implemented sequential models, plus a true multiprocessing SQLite lost-update experiment. SQLite is the target, not the checker implementation.

No third-party runtime dependencies, HTTP server, authentication or production data ingestion. CLI input capped2MiB; library assumes caller memory budget. No distributed tracing adapters, multi-object compositional partitioning, full transaction serializability, arbitrary specifications or formal verification of the checker.
