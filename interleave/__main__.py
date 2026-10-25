import argparse
import json
import sys
from pathlib import Path

from .checker import check, minimize, replay


def load(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("history exceeds 2MiB input limit")

    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate JSON key")
            out[key] = value
        return out

    return json.loads(
        raw,
        object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Exact bounded interval-history linearizability audit"
    )
    parser.add_argument("history")
    parser.add_argument("--max-states", type=int, default=200000)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--minimize", action="store_true")
    args = parser.parse_args(argv)
    try:
        history = load(args.history)
        result = check(history, max_states=args.max_states, timeout=args.timeout)
        if result["status"] == "linearizable":
            replay(history, result["witness"])
        if args.minimize and result["status"] == "nonlinearizable":
            result["counterexample"] = minimize(
                history, max_states=args.max_states, timeout=args.timeout
            )
        print(json.dumps(result, indent=2))
        return {"linearizable": 0, "nonlinearizable": 1, "inconclusive": 3}[result["status"]]
    except (ValueError, TypeError, OSError, RecursionError) as error:
        print(json.dumps({"status": "invalid", "reason": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
