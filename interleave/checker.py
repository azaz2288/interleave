"""Interval partial-order search with memoized (selected operations, model state)."""

import hashlib
import itertools
import json
import math
import time


def integer(value, *, low=-(2**63), high=2**63 - 1):
    return type(value) is int and low <= value <= high


def same(left, right):
    # JSON bool and integer must not compare equal (Python True == 1).
    return type(left) is type(right) and left == right


def validate(history):
    if type(history) is not dict or set(history) != {
        "schema",
        "model",
        "initial",
        "operations",
    }:
        raise ValueError("history requires exactly schema, model, initial, operations")
    if not same(history["schema"], 1) or history["model"] not in ("register", "queue"):
        raise ValueError("unsupported schema/model")
    initial = history["initial"]
    if history["model"] == "register":
        if not integer(initial):
            raise ValueError("register initial must be signed 64-bit integer")
        state = initial
    else:
        if type(initial) is not dict or set(initial) != {"capacity", "values"}:
            raise ValueError("queue initial requires capacity and values")
        if (
            not integer(initial["capacity"], low=1, high=10000)
            or type(initial["values"]) is not list
        ):
            raise ValueError("invalid queue initial")
        if len(initial["values"]) > initial["capacity"] or not all(
            integer(v) for v in initial["values"]
        ):
            raise ValueError("invalid queue initial values")
        state = tuple(initial["values"])
    operations = history["operations"]
    if type(operations) is not list or len(operations) > 64:
        raise ValueError("at most 64 operations per exact check")
    ids = set()
    processes = {}
    for op in operations:
        if type(op) is not dict or set(op) != {
            "id",
            "process",
            "call",
            "return",
            "kind",
            "input",
            "output",
        }:
            raise ValueError("invalid operation fields")
        if type(op["id"]) is not str or not 1 <= len(op["id"]) <= 128 or op["id"] in ids:
            raise ValueError("operation IDs must be unique nonempty short strings")
        ids.add(op["id"])
        if type(op["process"]) is not str or not 1 <= len(op["process"]) <= 128:
            raise ValueError("invalid process")
        if not integer(op["call"], low=0) or (
            op["return"] is not None and not integer(op["return"], low=op["call"])
        ):
            raise ValueError("invalid invocation/return interval")
        if op["return"] is None and op["output"] is not None:
            raise ValueError("pending output must be null")
        kind, arg, output = op["kind"], op["input"], op["output"]
        if history["model"] == "register":
            valid = (
                (kind == "write" and integer(arg) and output is None)
                or (kind == "read" and arg is None and (integer(output) or op["return"] is None))
                or (
                    kind == "cas"
                    and type(arg) is list
                    and len(arg) == 2
                    and all(integer(x) for x in arg)
                    and (type(output) is bool or op["return"] is None)
                )
            )
        else:
            valid = (
                kind == "enqueue"
                and integer(arg)
                and (type(output) is bool or op["return"] is None)
            ) or (kind == "dequeue" and arg is None and (output is None or integer(output)))
        if not valid:
            raise ValueError("input/output does not match model operation")
        processes.setdefault(op["process"], []).append(op)
    for ops in processes.values():
        ordered = sorted(
            ops,
            key=lambda op: (
                op["call"],
                op["return"] is None,
                op["return"] or 0,
                op["id"],
            ),
        )
        for first, second in itertools.pairwise(ordered):
            if (
                first["return"] is None
                or first["return"] > second["call"]
                or first["call"] == second["call"]
            ):
                raise ValueError("one process cannot have overlapping or ambiguous same-time calls")
    return state


def transition(history, state, op):
    kind, arg = op["kind"], op["input"]
    if history["model"] == "register":
        if kind == "write":
            return arg, None
        if kind == "read":
            return state, state
        success = state == arg[0]
        return (arg[1] if success else state), success
    if kind == "enqueue":
        success = len(state) < history["initial"]["capacity"]
        return (state + (arg,) if success else state), success
    return (state[1:], state[0]) if state else (state, None)


def predecessors(ops):
    return [
        sum(
            1 << j
            for j, other in enumerate(ops)
            if j != i
            and other["return"] is not None
            and (
                other["return"] < op["call"]
                or (other["process"] == op["process"] and other["return"] <= op["call"])
            )
        )
        for i, op in enumerate(ops)
    ]


class Exhausted(Exception):
    pass


def check(history, *, max_states=200000, timeout=5.0):
    state = validate(history)
    if (
        not integer(max_states, low=1, high=10000000)
        or type(timeout) not in (int, float)
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("budget must have positive finite time and 1..10000000 states")
    started = time.monotonic()
    ops = history["operations"]
    pred = predecessors(ops)
    required = sum(1 << i for i, op in enumerate(ops) if op["return"] is not None)
    memo = set()
    path = []
    deepest = []
    checks = 0

    def search(mask, current):
        nonlocal deepest, checks
        checks += 1
        if time.monotonic() - started >= timeout:
            raise Exhausted("time budget exhausted")
        if mask & required == required:
            return tuple(path)
        identity = (mask, current)
        if identity in memo:
            return None
        if len(memo) >= max_states:
            raise Exhausted("state budget exhausted")
        memo.add(identity)
        if len(path) > len(deepest):
            deepest = list(path)
        # Required-first is a heuristic only. Pending calls remain search candidates.
        for i in sorted(
            range(len(ops)),
            key=lambda i: (ops[i]["return"] is None, ops[i]["return"] or 0, i),
        ):
            bit = 1 << i
            op = ops[i]
            if mask & bit or pred[i] & mask != pred[i]:
                continue
            after, output = transition(history, current, op)
            if op["return"] is not None and not same(output, op["output"]):
                continue
            path.append({"id": op["id"], "output": output})
            found = search(mask | bit, after)
            if found is not None:
                return found
            path.pop()
        return None

    try:
        witness = search(0, state)
        status = "linearizable" if witness is not None else "nonlinearizable"
        reason = (
            "legal sequential witness found"
            if witness is not None
            else "all legal interval-respecting orders exhausted"
        )
    except Exhausted as error:
        witness = None
        status = "inconclusive"
        reason = str(error)
    digest = hashlib.sha256(
        json.dumps(history, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return {
        "schema": 1,
        "status": status,
        "reason": reason,
        "history_sha256": digest,
        "model": history["model"],
        "operations": len(ops),
        "completed": required.bit_count(),
        "states": len(memo),
        "search_calls": checks,
        "elapsed_seconds": time.monotonic() - started,
        "budget": {"max_states": max_states, "timeout_seconds": timeout},
        "witness": list(witness) if witness is not None else None,
        "deepest_legal_prefix": deepest,
        "assumptions": [
            "one shared monotonic clock",
            "sequential processes",
            "equal cross-process timestamps overlap",
            "pending calls may complete or be omitted",
        ],
    }


def replay(history, witness):
    current = validate(history)
    ops = history["operations"]
    by_id = {op["id"]: (i, op) for i, op in enumerate(ops)}
    pred = predecessors(ops)
    mask = 0
    if type(witness) is not list:
        raise ValueError("witness must be list")
    for item in witness:
        if type(item) is not dict or set(item) != {"id", "output"} or item["id"] not in by_id:
            raise ValueError("invalid witness entry")
        i, op = by_id[item["id"]]
        if mask & (1 << i) or pred[i] & mask != pred[i]:
            raise ValueError("duplicate operation or violated precedence")
        current, output = transition(history, current, op)
        if not same(output, item["output"]) or (
            op["return"] is not None and not same(output, op["output"])
        ):
            raise ValueError("invalid witness result")
        mask |= 1 << i
    if any(op["return"] is not None and not mask & (1 << i) for i, op in enumerate(ops)):
        raise ValueError("witness omits completed operation")
    return current


def minimize(history, *, max_states=200000, timeout=5.0):
    """Greedy single-operation reduction; global time cap, no false minimality claims."""
    started = time.monotonic()
    result = check(history, max_states=max_states, timeout=timeout)
    if result["status"] != "nonlinearizable":
        raise ValueError("only an exactly rejected history can be minimized")
    current = dict(history, operations=list(history["operations"]))
    attempts = 0
    inconclusive = False
    changed = True
    while changed:
        changed = False
        for i in range(len(current["operations"])):
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                inconclusive = True
                break
            candidate = dict(
                current,
                operations=current["operations"][:i] + current["operations"][i + 1 :],
            )
            decision = check(candidate, max_states=max_states, timeout=remaining)
            attempts += 1
            if decision["status"] == "inconclusive":
                inconclusive = True
            elif decision["status"] == "nonlinearizable":
                current = candidate
                changed = True
                break
        if inconclusive:
            break
    return {
        "history": current,
        "original_operations": len(history["operations"]),
        "attempts": attempts,
        "one_minimal": not inconclusive,
        "elapsed_seconds": time.monotonic() - started,
        "meaning": "no single operation removable"
        if not inconclusive
        else "reduction budget incomplete",
    }
