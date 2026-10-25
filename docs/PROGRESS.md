# v0.1.0 · 2026-10-26 (Asia/Shanghai)

## Implemented and locally accepted
- Interval partial-order bitsets and exact memoized state-space search for integer register/read/write/CAS and bounded FIFO/enqueue/dequeue. Optional pending completion, strict process histories and bool/integer separation. Distinct linearizable/nonlinearizable/inconclusive outcomes; no timeout-to-pass shortcut.
- Canonical history SHA256 and budgets in JSON, independent witness replay, globally time-bounded single-operation counterexample reduction. Only exact rejection permits deletion; unfinished minimization never claims one-minimal.
-18 Python methods1.089s passed, including400 deterministic random histories against separately implemented factorial permutation/pending-subset oracle,36 exhaustive register pairs, FIFO ordering/capacity, pending writes/CAS, equal timestamp semantics, strict inputs, tampered witness rejection, timeout/state budgets and minimizer-budget behavior.
- Adversarial impossible read after10 no-op writes exhausts exactly1024 memo states; smaller state budget returns inconclusive. This is a bounded search evidence point, not a broad performance claim.
- Real `spawn` multiprocessing SQLite experiment:barrier-forced read/check/write CAS produces two successful conflicting updates and is rejected; transactional CAS produces exactly one winner and a separately replayable sequential witness. Original synthetic interval histories and outputs are recorded. Clocks use same-host monotonic perf_counter_ns, not cross-machine wall clocks.
- Isolated wheel install and installed console script tested outside source tree for both legal and contradictory input. Runtime has zero third-party packages. Compileall, pip check and Ruff checks/format passed. Dual-platform workflow included; actual current-SHA CI results are recorded separately at publication.

## Publication evidence
Implementation revision `6e4b5612ab33d4758da8cbd787d2c924b0881637` passed both Windows and Ubuntu jobs in [run40216618972](https://github.com/azaz2288/interleave/actions/runs/40216618972):all14 actual steps per platform completed successfully, with no skipped tests. That run verifies exactly that revision; subsequent revisions require their own completed run. This documentation update corrects the earlier mistaken New York date label to the user's October26 Asia/Shanghai date. Raw UTC timestamps remain unchanged.

## Failures retained and fixed
First real-process test failed cleaning its synthetic SQLite DB on Windows:SQLite's connection context manager commits but does not close. Parent now uses contextlib.closing; worker has finally-close. No real database was touched. New venv initially lacked setuptools for no-build-isolation; build tools installed only in this project's venv via official PyPI, no global or old-project dependency changes. Lint found explicit-check/type-comparison issues; fixed, not ignored.

## Limits
Exactness is for supplied histories up to64 operations and the chosen model. Exponential worst case remains; no proof for all executions, cross-machine clock correction, multi-object composition, transaction serializability, rejection certificate or production service integration. Single-deletion minimality is not global smallest counterexample. The deepest legal prefix is diagnostic, not a proof of which operation caused a bug.
