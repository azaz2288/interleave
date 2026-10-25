# v0.1.0 · 2026-10-25 (America/New_York)

## Implemented and locally accepted
- Interval partial-order bitsets and exact memoized state-space search for integer register/read/write/CAS and bounded FIFO/enqueue/dequeue. Optional pending completion, strict process histories and bool/integer separation. Distinct linearizable/nonlinearizable/inconclusive outcomes; no timeout-to-pass shortcut.
- Canonical history SHA256 and budgets in JSON, independent witness replay, globally time-bounded single-operation counterexample reduction. Only exact rejection permits deletion; unfinished minimization never claims one-minimal.
-18 Python methods1.089s passed, including400 deterministic random histories against separately implemented factorial permutation/pending-subset oracle,36 exhaustive register pairs, FIFO ordering/capacity, pending writes/CAS, equal timestamp semantics, strict inputs, tampered witness rejection, timeout/state budgets and minimizer-budget behavior.
- Adversarial impossible read after10 no-op writes exhausts exactly1024 memo states; smaller state budget returns inconclusive. This is a bounded search evidence point, not a broad performance claim.
- Real `spawn` multiprocessing SQLite experiment:barrier-forced read/check/write CAS produces two successful conflicting updates and is rejected; transactional CAS produces exactly one winner and a separately replayable sequential witness. Original synthetic interval histories and outputs are recorded. Clocks use same-host monotonic perf_counter_ns, not cross-machine wall clocks.
- Isolated wheel install and installed console script tested outside source tree for both legal and contradictory input. Runtime has zero third-party packages. Compileall, pip check and Ruff checks/format passed. Dual-platform workflow included; actual current-SHA CI results are recorded separately at publication.

## Failures retained and fixed
First real-process test failed cleaning its synthetic SQLite DB on Windows:SQLite's connection context manager commits but does not close. Parent now uses contextlib.closing; worker has finally-close. No real database was touched. New venv initially lacked setuptools for no-build-isolation; build tools installed only in this project's venv via official PyPI, no global or old-project dependency changes. Lint found explicit-check/type-comparison issues; fixed, not ignored.

## Limits
Exactness is for supplied histories up to64 operations and the chosen model. Exponential worst case remains; no proof for all executions, cross-machine clock correction, multi-object composition, transaction serializability, rejection certificate or production service integration. Single-deletion minimality is not global smallest counterexample. The deepest legal prefix is diagnostic, not a proof of which operation caused a bug.
