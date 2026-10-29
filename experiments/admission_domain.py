"""Reproduce the refusal channel and exhaustively check a stated finite domain.

Character-token mock backend only; this is neither a tokenizer bound nor a
certificate for arbitrary strings or real-model response trajectories.
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchlang import core as C, models as M, runtime as R


def observe(runtime, program, store, seed):
    try:
        result = runtime.run(program, store, seed)
        return dict(status="completed", trace=result.observed(), usage=result.usage)
    except R.ContractViolation as error:
        dispatched = getattr(error, "dispatched", False)
        prefix = [e.observed() for e in runtime.trace]
        return dict(status="unknown_dispatch" if dispatched else "refused" if not prefix else "failed",
                    trace=prefix, usage=runtime.ledger.snapshot(), reason=str(error))


def study():
    profile = M.Profile("m", "unused", "qwen2")
    backend = R.MockBackend(profile)
    request = lambda value: profile.tmpl.render([("user", value)])
    target = backend.count(request("abc"))
    expression = C.concat([C.ELit(request("PLACEHOLDER").split("PLACEHOLDER")[0]),
                           C.EVar(0), C.ELit(request("PLACEHOLDER").split("PLACEHOLDER")[1])])
    program = C.Call(0, 1, "m", expression, (target, 8), 4)
    runtime = R.Runtime({"m": backend}, {}, {})
    counterexample = [dict(secret=value, **observe(runtime, program, {0: value}, 0))
                      for value in ("a", "a" * 64)]
    inputs = ["".join(v) for n in range(4) for v in itertools.product("ab", repeat=n)]
    rows = [dict(secret=value, seed=seed, **observe(runtime, program, {0: value}, seed))
            for value in inputs for seed in (0, 1, 17)]
    expected = [list(event) for event in C.shape(program)]
    success = all(r["status"] == "completed" and [list(e) for e in r["trace"]] == expected for r in rows)
    assert [r["status"] for r in counterexample] == ["completed", "refused"]
    assert success
    return dict(schema="orchlang-finite-admission-study-v1", unit="characters, mock backend",
                public_store="empty; slot 0 secret", target=target, counterexample=counterexample,
                domain={"alphabet": "ab", "maximum_length": 3, "seeds": [0, 1, 17]},
                finite_cases=len(rows), all_completed_with_static_shape=success, rows=rows,
                limitation="Exhaustive only for these 15 strings and 3 tapes; not a deployment-domain proof.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    result = study()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "counterexample")}))
