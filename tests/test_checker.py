import copy
import itertools
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interleave import check, minimize, replay, validate
from interleave.__main__ import load


def op(ident, kind, arg=None, output=None, call=0, end=10, process=None):
    return {
        "id": str(ident),
        "process": process or str(ident),
        "kind": kind,
        "input": arg,
        "output": output,
        "call": call,
        "return": end,
    }


def history(ops, model="register", initial=0):
    return {"schema": 1, "model": model, "initial": initial, "operations": ops}


def oracle(h):
    """Independent factorial oracle: no production transitions/predecessors/search."""
    operations = h["operations"]
    completed = [i for i, operation in enumerate(operations) if operation["return"] is not None]
    pending = [i for i in range(len(operations)) if i not in completed]
    for bits in range(1 << len(pending)):
        chosen = completed + [p for j, p in enumerate(pending) if bits >> j & 1]
        for order in itertools.permutations(chosen):
            rank = {item: i for i, item in enumerate(order)}
            legal = True
            for a in chosen:
                for b in chosen:
                    x, y = operations[a], operations[b]
                    if (
                        a != b
                        and x["return"] is not None
                        and (
                            x["return"] < y["call"]
                            or (x["process"] == y["process"] and x["return"] <= y["call"])
                        )
                        and rank[a] >= rank[b]
                    ):
                        legal = False
            if not legal:
                continue
            value = h["initial"] if h["model"] == "register" else list(h["initial"]["values"])
            for index in order:
                operation = operations[index]
                kind, arg = operation["kind"], operation["input"]
                if h["model"] == "register":
                    if kind == "read":
                        result = value
                    elif kind == "write":
                        value = arg
                        result = None
                    else:
                        result = value == arg[0]
                        if result:
                            value = arg[1]
                elif kind == "enqueue":
                    result = len(value) < h["initial"]["capacity"]
                    if result:
                        value.append(arg)
                else:
                    result = value.pop(0) if value else None
                expected = operation["output"]
                if operation["return"] is not None and (
                    type(result) is not type(expected) or result != expected
                ):
                    legal = False
                    break
            if legal:
                return True
    return False


class CheckerTests(unittest.TestCase):
    def assertOracle(self, h):
        expected = oracle(h)
        result = check(h, timeout=10)
        self.assertEqual(result["status"], "linearizable" if expected else "nonlinearizable", h)
        if expected:
            replay(h, result["witness"])

    def test_real_time_stale_read_rejected_but_overlapping_read_can_precede_write(self):
        self.assertOracle(
            history(
                [
                    op("w", "write", 1, call=0, end=1),
                    op("r", "read", output=0, call=2, end=3),
                ]
            )
        )
        self.assertEqual(
            check(history([op("w", "write", 1), op("r", "read", output=0)]))["status"],
            "linearizable",
        )

    def test_two_successful_cas_cannot_both_replace_same_initial_value(self):
        h = history([op("a", "cas", [0, 1], True), op("b", "cas", [0, 2], True)])
        self.assertOracle(h)
        self.assertEqual(check(h)["status"], "nonlinearizable")

    def test_failed_cas_is_observed_and_bool_is_not_integer(self):
        self.assertOracle(history([op("a", "cas", [0, 1], False)]))
        for output in (0, 1, "true"):
            with self.assertRaises(ValueError):
                check(history([op("a", "cas", [0, 1], output)]))

    def test_pending_write_can_explain_later_read_or_can_be_omitted(self):
        h = history([op("p", "write", 7, end=None), op("r", "read", output=7, call=2, end=3)])
        result = check(h)
        self.assertEqual(result["status"], "linearizable")
        self.assertEqual([entry["id"] for entry in result["witness"]], ["p", "r"])
        replay(h, result["witness"])
        self.assertOracle(history([op("p", "write", 7, end=None), op("r", "read", output=0)]))
        self.assertOracle(history([op("p", "cas", [0, 7], end=None), op("r", "read", output=7)]))

    def test_pending_reads_do_not_invent_mutations_and_all_pending_empty_witness(self):
        h = history([op("p", "read", end=None), op("r", "read", output=1)])
        self.assertOracle(h)
        self.assertEqual(check(history([op("p", "write", 5, end=None)]))["witness"], [])

    def test_queue_fifo_duplicates_capacity_and_pending_enqueue(self):
        initial = {"capacity": 2, "values": []}
        self.assertOracle(
            history(
                [
                    op("a", "enqueue", 1, True, end=1),
                    op("b", "enqueue", 2, True, call=2, end=3),
                    op("c", "dequeue", output=2, call=4, end=5),
                ],
                "queue",
                initial,
            )
        )
        self.assertOracle(
            history(
                [op("a", "enqueue", 9, end=None), op("b", "dequeue", output=9)],
                "queue",
                initial,
            )
        )
        self.assertOracle(
            history([op("a", "enqueue", 1, False)], "queue", {"capacity": 1, "values": [1]})
        )

    def test_equal_cross_process_timestamps_overlap_but_process_order_is_preserved(
        self,
    ):
        h = history(
            [
                op("w", "write", 1, call=0, end=1),
                op("r", "read", output=0, call=1, end=2),
            ]
        )
        self.assertEqual(check(h)["status"], "linearizable")
        for item in h["operations"]:
            item["process"] = "one"
        self.assertEqual(check(h)["status"], "nonlinearizable")

    def test_limits_return_inconclusive_not_semantic_failure(self):
        h = history([op("a", "write", 1), op("b", "read", output=1)])
        self.assertEqual(check(h, max_states=1)["status"], "inconclusive")
        with patch("interleave.checker.time.monotonic", side_effect=[0, 2, 2]):
            self.assertEqual(check(h, timeout=1)["status"], "inconclusive")
        for kwargs in (
            {"timeout": float("nan")},
            {"timeout": -1},
            {"max_states": 0},
            {"max_states": True},
        ):
            with self.assertRaises(ValueError):
                check(h, **kwargs)

    def test_witness_tampering_omission_duplication_and_precedence_rejected(self):
        h = history([op("a", "write", 1, end=1), op("b", "read", output=1, call=2, end=3)])
        witness = check(h)["witness"]
        replay(h, witness)
        for bad in (
            witness[:-1],
            witness[::-1],
            witness + witness,
            [{"id": "b", "output": 0}],
            [{"id": "fake", "output": 1}],
        ):
            with self.assertRaises(ValueError):
                replay(h, bad)

    def test_counterexample_is_one_minimal_and_does_not_mutate_input(self):
        h = history(
            [
                op("a", "cas", [0, 1], True),
                op("b", "cas", [0, 2], True),
                op("noise", "read", output=0),
            ]
        )
        before = copy.deepcopy(h)
        result = minimize(h)
        self.assertEqual(h, before)
        self.assertTrue(result["one_minimal"])
        reduced = result["history"]
        self.assertEqual(len(reduced["operations"]), 2)
        self.assertEqual(check(reduced)["status"], "nonlinearizable")
        for i in range(2):
            candidate = dict(
                reduced,
                operations=reduced["operations"][:i] + reduced["operations"][i + 1 :],
            )
            self.assertEqual(check(candidate)["status"], "linearizable")
        with self.assertRaises(ValueError):
            minimize(history([]))

    def test_strict_schema_intervals_processes_duplicate_ids_and_bounds(self):
        good = history([op("a", "read", output=0)])
        mutations = [
            lambda h: h.update(schema=True),
            lambda h: h.update(initial=True),
            lambda h: h.update(extra=1),
            lambda h: h["operations"][0].update(call=True),
            lambda h: h["operations"][0].update(return_=1),
            lambda h: h["operations"][0].update(call=11),
            lambda h: h["operations"].append(dict(h["operations"][0])),
            lambda h: h.update(operations=[op(i, "read", output=0) for i in range(65)]),
            lambda h: h.update(
                operations=[
                    op("a", "read", output=0, process="p"),
                    op("b", "read", output=0, process="p"),
                ]
            ),
            lambda h: h["operations"][0].update(output=2**100),
            lambda h: h["operations"][0].update(process=1),
        ]
        for mutate in mutations:
            h = copy.deepcopy(good)
            mutate(h)
            with self.subTest(h=h), self.assertRaises(ValueError):
                validate(h)

    def test_400_seeded_histories_match_independent_factorial_oracle(self):
        rng = random.Random(981342)
        for index in range(400):
            model = "register" if index % 2 else "queue"
            ops = []
            for i in range(1 + rng.randrange(6)):
                start = rng.randrange(8)
                end = start + rng.randrange(1, 5)
                pending = rng.random() < 0.12
                kind = rng.choice(
                    ["read", "write", "cas"] if model == "register" else ["enqueue", "dequeue"]
                )
                if kind == "read":
                    arg = None
                    output = rng.randrange(3)
                elif kind == "write":
                    arg = rng.randrange(3)
                    output = None
                elif kind == "cas":
                    arg = [rng.randrange(3), rng.randrange(3)]
                    output = bool(rng.randrange(2))
                elif kind == "enqueue":
                    arg = rng.randrange(3)
                    output = bool(rng.randrange(2))
                else:
                    arg = None
                    output = rng.choice([None, 0, 1, 2])
                ops.append(
                    op(
                        i,
                        kind,
                        arg,
                        None if pending else output,
                        start,
                        None if pending else end,
                    )
                )
            h = history(ops, model, 0 if model == "register" else {"capacity": 2, "values": []})
            with self.subTest(index=index):
                self.assertOracle(h)

    def test_all_small_overlapping_register_pairs_match_oracle(self):
        choices = [
            ("write", 0, None),
            ("write", 1, None),
            ("read", None, 0),
            ("read", None, 1),
            ("cas", [0, 1], True),
            ("cas", [0, 1], False),
        ]
        for a, b in itertools.product(choices, repeat=2):
            self.assertOracle(history([op("a", *a), op("b", *b)]))

    def test_memoized_rejection_exhausts_subsets_not_factorial_duplicate_orders(self):
        h = history(
            [op(str(i), "write", 0, call=0, end=2) for i in range(10)]
            + [op("impossible", "read", output=1, call=3, end=4)]
        )
        result = check(h, max_states=2000, timeout=10)
        self.assertEqual(result["status"], "nonlinearizable")
        self.assertEqual(result["states"], 1024)
        self.assertEqual(check(h, max_states=100)["status"], "inconclusive")

    def test_minimization_does_not_claim_one_minimal_when_global_budget_expires(self):
        h = history([op("a", "cas", [0, 1], True), op("b", "cas", [0, 2], True)])
        verdict = check(h)
        with (
            patch("interleave.checker.check", return_value=verdict),
            patch("interleave.checker.time.monotonic", side_effect=[0, 2, 2]),
        ):
            reduced = minimize(h, timeout=1)
        self.assertFalse(reduced["one_minimal"])
        self.assertEqual(reduced["history"], h)

    def test_canonical_digest_is_key_order_independent_and_changes_with_history(self):
        h = history([op("a", "read", output=0)])
        reversed_keys = json.loads(json.dumps(h, sort_keys=True))
        self.assertEqual(check(h)["history_sha256"], check(reversed_keys)["history_sha256"])
        h["initial"] = 1
        self.assertNotEqual(check(h)["history_sha256"], check(reversed_keys)["history_sha256"])

    def test_cli_exit_codes_duplicate_json_keys_and_size_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "h.json"
            for h, code in [
                (history([]), 0),
                (history([op("x", "read", output=1)]), 1),
            ]:
                path.write_text(json.dumps(h), encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, "-m", "interleave", str(path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, code, result.stderr)
            path.write_text(
                json.dumps(history([op("a", "write", 1), op("b", "read", output=1)])),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, "-m", "interleave", str(path), "--max-states", "1"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 3)
            path.write_text('{"schema":1,"schema":1}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load(path)
            path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
            with self.assertRaises(ValueError):
                load(path)


if __name__ == "__main__":
    unittest.main()
