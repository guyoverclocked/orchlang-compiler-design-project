#!/usr/bin/env python3
"""Generate and schema-validate the preregistered structured solver inputs.

This command does not invoke an equivalence solver and does not collect timing.
Run it before appending the generated SHA-256 inventory to PREREGISTRATION.md.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
AUDIT = ROOT / "audit"
if str(AUDIT) not in sys.path:
    sys.path.insert(0, str(AUDIT))
PUBLICATION_RESEARCH = ROOT / "research/publication_upgrade"
if str(PUBLICATION_RESEARCH) not in sys.path:
    sys.path.insert(0, str(PUBLICATION_RESEARCH))

from orchgraph import Graph
from probabilistic_channels import Kernel, normalized_store
from solver_scaling import _graph as primary_graph, _kernel as primary_kernel

OUT = ROOT / "output/scp_strengthening/scalability"
INPUTS = OUT / "inputs"
STRUCTURED = INPUTS / "structured"
CASES: list[dict[str, Any]] = []


def _bytes(document: Any) -> bytes:
    return (json.dumps(document, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_case(case_id: str, family: str, level: Any,
                graph: dict[str, Any], kernel: dict[str, Any],
                public: dict[str, Any], scenarios: list[dict[str, Any]],
                *, max_states: int = 10_000,
                expected_class: str = "equal_or_finite-result") -> None:
    graph_path = STRUCTURED / f"{case_id}.graph.json"
    kernel_path = STRUCTURED / f"{case_id}.kernel.json"
    graph_raw, kernel_raw = _bytes(graph), _bytes(kernel)
    graph_path.write_bytes(graph_raw)
    kernel_path.write_bytes(kernel_raw)
    CASES.append({
        "case_id": case_id,
        "family": family,
        "level": level,
        "graph_path": str(graph_path.relative_to(ROOT)),
        "kernel_path": str(kernel_path.relative_to(ROOT)),
        "graph_sha256": _sha(graph_raw),
        "kernel_sha256": _sha(kernel_raw),
        "input_sha256": _sha(graph_raw + b"\0" + kernel_raw),
        "graph_bytes": len(graph_raw),
        "kernel_bytes": len(kernel_raw),
        "public_store": public,
        "secret_scenarios": scenarios,
        "max_states": max_states,
        "expected_class": expected_class,
    })


def _model(cap: int = 8, model: str = "finite-worker") -> dict[str, Any]:
    return {"m": {"provider": "offline", "model": model, "max_tokens": cap}}


def _registers(names: list[str]) -> dict[str, Any]:
    return {name: {"model": "m"} for name in names}


def _default_kernel(outcomes: list[dict[str, Any]], history_window: int = 0,
                   rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"format": "orchlang-finite-outcome-kernel", "version": 1,
            "history_window": history_window, "defaults": {"m": outcomes},
            "rules": [] if rules is None else rules}


def _outcome(response: str, output_tokens: int, probability: str) -> dict[str, Any]:
    return {"response": response, "output_tokens": output_tokens,
            "probability": probability}


def _secret_cases(names: list[str]) -> list[dict[str, Any]]:
    return [dict(zip(names, bits)) for bits in itertools.product((False, True), repeat=len(names))]


def _secret_fanout(leaves: int) -> None:
    depth = (leaves - 1).bit_length()
    bit_names = [f"secret_{index}" for index in range(depth)]
    states: dict[str, Any] = {
        "work": {"calls": [{"model": "m", "template": "Leaf",
                             "arguments": [], "result": "r"}],
                 "next": {"kind": "stop"}}
    }

    def build(level: int, prefix: str) -> str:
        if level == depth:
            return "work"
        state = f"branch_{level}_{prefix or 'root'}"
        left = build(level + 1, prefix + "0")
        right = build(level + 1, prefix + "1")
        states[state] = {
            "calls": [],
            "next": {"kind": "secret", "guard": {"value": bit_names[level]},
                     "then": right, "else": left},
        }
        return state

    entry = build(0, "")
    graph = {"format": "orchlang-request-graph", "version": 1,
             "name": f"scale_secret_fanout_{leaves}", "chars_per_token": 1,
             "inputs": {name: {"type": "boolean", "label": "secret"}
                        for name in bit_names},
             "models": _model(1), "registers": _registers(["r"]),
             "entry": entry, "states": states}
    kernel = _default_kernel([_outcome("x", 1, "1")])
    _write_case(f"secret_fanout_{leaves}", "secret_branch_fanout", leaves,
                graph, kernel, {}, _secret_cases(bit_names))


def _public_context(guards: int) -> None:
    public_names = [f"public_{i}" for i in range(guards)]
    states: dict[str, Any] = {}
    for side, template in (("left", "A"), ("right", "B")):
        next_state = f"{side}_call"
        states[next_state] = {
            "calls": [{"model": "m", "template": template,
                       "arguments": [], "result": "r"}],
            "next": {"kind": "stop"},
        }
        for index in reversed(range(guards)):
            state = f"{side}_public_{index}"
            states[state] = {
                "calls": [],
                "next": {"kind": "public", "guard": {"value": public_names[index]},
                         "then": next_state, "else": next_state},
            }
            next_state = state
        states[f"{side}_entry"] = {"calls": [],
                                   "next": {"kind": "goto", "target": next_state}}
    states["choose"] = {"calls": [], "next": {
        "kind": "secret", "guard": {"value": "secret"},
        "then": "left_entry", "else": "right_entry"}}
    graph = {"format": "orchlang-request-graph", "version": 1,
             "name": f"scale_public_context_{guards}", "chars_per_token": 1,
             "inputs": {"secret": {"type": "boolean", "label": "secret"},
                        **{name: {"type": "boolean", "label": "public"}
                           for name in public_names}},
             "models": _model(1), "registers": _registers(["r"]),
             "entry": "choose", "states": states}
    kernel = _default_kernel([_outcome("x", 1, "1")])
    public = {name: bool(index % 2) for index, name in enumerate(public_names)}
    _write_case(f"public_context_{guards}", "public_branch_context", guards,
                graph, kernel, public, [{"secret": False}, {"secret": True}])


def _mutable_registers(register_count: int) -> None:
    count = 2 * register_count
    register_names = [f"r{i}" for i in range(register_count)]
    calls = []
    for index in range(count):
        arguments = [] if index == 0 else [{"value": register_names[(index - 1) % register_count]}]
        calls.append({"model": "m", "template": f"M{index % register_count}",
                      "arguments": arguments, "result": register_names[index % register_count]})
    graph = {"format": "orchlang-request-graph", "version": 1,
             "name": f"scale_mutable_registers_{register_count}",
             "chars_per_token": 1,
             "inputs": {"secret": {"type": "boolean", "label": "secret"}},
             "models": _model(2), "registers": _registers(register_names),
             "entry": "choose", "states": {
                 "choose": {"calls": [], "next": {"kind": "secret",
                     "guard": {"value": "secret"}, "then": "work", "else": "work"}},
                 "work": {"calls": calls, "next": {"kind": "stop"}},
             }}
    kernel = _default_kernel([_outcome("x", 1, "1/2"), _outcome("xx", 2, "1/2")])
    _write_case(f"mutable_registers_{register_count}", "mutable_registers_dependent_requests",
                {"registers": register_count, "writes": count}, graph, kernel, {},
                [{"secret": False}, {"secret": True}])


def _productive_cycle(period: int) -> None:
    states: dict[str, Any] = {"choose": {"calls": [], "next": {
        "kind": "secret", "guard": {"value": "secret"},
        "then": "left_0", "else": "right_0"}}}
    for side in ("left", "right"):
        for index in range(period):
            state = f"{side}_{index}"
            target = f"{side}_{(index + 1) % period}"
            states[state] = {
                "calls": [{"model": "m", "template": f"T{index}",
                           "arguments": [], "result": "r"}],
                "next": {"kind": "goto", "target": target},
            }
    graph = {"format": "orchlang-request-graph", "version": 1,
             "name": f"scale_productive_cycle_{period}", "chars_per_token": 1,
             "inputs": {"secret": {"type": "boolean", "label": "secret"}},
             "models": _model(1), "registers": _registers(["r"]),
             "entry": "choose", "states": states}
    kernel = _default_kernel([_outcome("x", 1, "1")])
    _write_case(f"productive_cycle_{period}", "productive_cycle", period,
                graph, kernel, {}, [{"secret": False}, {"secret": True}])


def _outcome_support(support: int) -> None:
    outcomes = [_outcome(chr(ord("a") + i), 1, f"1/{support}")
                for i in range(support)]
    graph = {"format": "orchlang-request-graph", "version": 1,
             "name": f"scale_outcome_support_{support}", "chars_per_token": 1,
             "inputs": {"secret": {"type": "boolean", "label": "secret"}},
             "models": _model(1), "registers": _registers(["r"]),
             "entry": "choose", "states": {
                 "choose": {"calls": [], "next": {"kind": "secret",
                     "guard": {"value": "secret"}, "then": "work", "else": "work"}},
                 "work": {"calls": [{"model": "m", "template": "S", "arguments": [],
                                      "result": "r"}], "next": {"kind": "stop"}},
             }}
    _write_case(f"outcome_support_{support}", "oracle_outcome_support", support,
                graph, _default_kernel(outcomes), {}, [{"secret": False}, {"secret": True}])


def _observation_alphabet(alphabet: int) -> None:
    outcomes = [_outcome(chr(ord("a") + i), 1 + (i % alphabet), "1/8")
                for i in range(8)]
    graph = {"format": "orchlang-request-graph", "version": 1,
             "name": f"scale_observation_alphabet_{alphabet}", "chars_per_token": 1,
             "inputs": {"secret": {"type": "boolean", "label": "secret"}},
             "models": _model(8), "registers": _registers(["r"]),
             "entry": "choose", "states": {
                 "choose": {"calls": [], "next": {"kind": "secret",
                     "guard": {"value": "secret"}, "then": "work", "else": "work"}},
                 "work": {"calls": [{"model": "m", "template": "O", "arguments": [],
                                      "result": "r"}], "next": {"kind": "stop"}},
             }}
    _write_case(f"observation_alphabet_{alphabet}", "usage_observation_alphabet",
                {"alphabet_labels": alphabet, "support": 8}, graph,
                _default_kernel(outcomes), {}, [{"secret": False}, {"secret": True}])


def _history_growth(window: int) -> None:
    prefix_calls = [{"model": "m", "template": f"P{i}", "arguments": [], "result": "r"}
                    for i in range(3)]
    final_call = {"model": "m", "template": "C", "arguments": [], "result": "r"}
    graph = {"format": "orchlang-request-graph", "version": 1,
             "name": f"scale_retained_history_{window}", "chars_per_token": 1,
             "inputs": {"secret": {"type": "boolean", "label": "secret"}},
             "models": _model(2), "registers": _registers(["r"]),
             "entry": "choose", "states": {
                 "choose": {"calls": [], "next": {"kind": "secret",
                     "guard": {"value": "secret"}, "then": "work", "else": "work"}},
                 "work": {"calls": prefix_calls + [final_call], "next": {"kind": "stop"}},
             }}
    prior = [_outcome("a", 1, "1/2"), _outcome("b", 1, "1/2")]
    defaults = prior
    rules = []
    contract = {"provider": "offline", "model": "finite-worker", "max_tokens": 2,
                "has_unit_price": False, "unit_price": 0.0}
    for bits in itertools.product(("a", "b"), repeat=window):
        start = 3 - window
        history = [{"contract": contract, "ordinal": index, "template": f"P{index}",
                    "arguments": [], "response": response,
                    "input_tokens": len(f"P{index}"), "output_tokens": 1}
                   for index, response in zip(range(start, 3), bits)]
        output = 1 + (sum(value == "b" for value in bits) % 2)
        rules.append({"model": "m", "template": "C", "ordinal": 3,
                      "history": history, "outcomes": [_outcome("z", output, "1")]})
    kernel = _default_kernel(defaults, history_window=window, rules=rules)
    _write_case(f"retained_history_{window}", "retained_history_state_growth", window,
                graph, kernel, {}, [{"secret": False}, {"secret": True}])


def _special_from_example(filename: str, case_id: str, family: str,
                          expected: str) -> None:
    graph = json.loads((ROOT / "examples/channels" / f"{filename}.graph.json").read_text())
    kernel = json.loads((ROOT / "examples/channels" / f"{filename}.kernel.json").read_text())
    graph["name"] = f"scale_{case_id}"
    _write_case(case_id, family, "fixed-authored-shape", graph, kernel, {},
                [{"secret": False}, {"secret": True}], expected_class=expected)


def _resource_probe() -> None:
    outcomes = [_outcome(chr(ord("a") + i), 1, "1/8") for i in range(8)]
    graph = {"format": "orchlang-request-graph", "version": 1,
             "name": "scale_resource_unknown_probe", "chars_per_token": 1,
             "inputs": {"secret": {"type": "boolean", "label": "secret"}},
             "models": _model(1), "registers": _registers(["r"]),
             "entry": "choose", "states": {
                 "choose": {"calls": [], "next": {"kind": "secret",
                     "guard": {"value": "secret"}, "then": "work", "else": "work"}},
                 "work": {"calls": [{"model": "m", "template": "U", "arguments": [],
                                      "result": "r"}], "next": {"kind": "stop"}},
             }}
    kernel = _default_kernel(outcomes)
    _write_case("resource_unknown_probe", "resource_unknown", "max_states=1",
                graph, kernel, {}, [{"secret": False}, {"secret": True}],
                max_states=1, expected_class="unknown-resource")


def _validate(case: dict[str, Any]) -> None:
    graph_doc = json.loads((ROOT / case["graph_path"]).read_bytes())
    kernel_doc = json.loads((ROOT / case["kernel_path"]).read_bytes())
    graph = Graph(graph_doc)
    Kernel(graph, kernel_doc)
    if set(case["public_store"]) != {name for name, decl in graph.inputs.items()
                                      if decl["label"] == "public"}:
        raise ValueError(f"{case['case_id']}: public assignment is incomplete")
    for scenario in case["secret_scenarios"]:
        if set(scenario) != {name for name, decl in graph.inputs.items()
                             if decl["label"] == "secret"}:
            raise ValueError(f"{case['case_id']}: secret assignment is incomplete")
        normalized_store(graph, {**case["public_store"], **scenario})


def main() -> None:
    INPUTS.mkdir(parents=True, exist_ok=True)
    STRUCTURED.mkdir(parents=True, exist_ok=True)

    primary_kernel_raw = _bytes(primary_kernel())
    (INPUTS / "scale.kernel.json").write_bytes(primary_kernel_raw)
    primary_cases = []
    for size in (2, 8, 16, 32, 64, 128, 256):
        graph_raw = _bytes(primary_graph(size))
        path = INPUTS / f"scale_{size}.graph.json"
        path.write_bytes(graph_raw)
        primary_cases.append({
            "case_id": f"symmetric_chain_{size}",
            "family": "symmetric_equal_chain_primary",
            "level": size,
            "graph_path": str(path.relative_to(ROOT)),
            "kernel_path": str((INPUTS / "scale.kernel.json").relative_to(ROOT)),
            "graph_sha256": _sha(graph_raw),
            "kernel_sha256": _sha(primary_kernel_raw),
            "input_sha256": _sha(graph_raw + b"\0" + primary_kernel_raw),
            "graph_bytes": len(graph_raw),
            "kernel_bytes": len(primary_kernel_raw),
            "public_store": {},
            "secret_scenarios": [{"route": False}, {"route": True}],
            "max_states": 10_000,
            "expected_class": "proved_equal",
            "generator": "research/publication_upgrade/solver_scaling.py::_graph,_kernel",
        })

    for leaves in (2, 4, 8):
        _secret_fanout(leaves)
    for guards in (0, 2, 4):
        _public_context(guards)
    for registers in (1, 2, 4):
        _mutable_registers(registers)
    for period in (1, 2, 4):
        _productive_cycle(period)
    for support in (1, 2, 4, 8):
        _outcome_support(support)
    for alphabet in (1, 2, 4, 8):
        _observation_alphabet(alphabet)
    for window in (0, 1, 2, 3):
        _history_growth(window)
    _special_from_example("history_conditioned_usage", "history_conditioned_unequal",
                          "history_conditioned_request_distinguishing_witness",
                          "proved_unequal_finite_witness")
    _special_from_example("trace_equal_not_bisimilar", "bisim_inconclusive_exact_equal",
                          "bisimulation_inconclusive_exact_equal",
                          "proved_equal_bisim_inconclusive")
    _resource_probe()

    for case in primary_cases + CASES:
        _validate(case)
    all_cases = primary_cases + CASES
    if len({case["input_sha256"] for case in all_cases}) != len(all_cases):
        raise ValueError("generated cases do not have distinct graph/kernel input identities")
    generator_path = Path(__file__).resolve()
    manifest = {
        "format": "orchlang-structured-scalability-frozen-inputs",
        "version": 1,
        "generator_path": str(generator_path.relative_to(ROOT)),
        "generator_sha256": _sha(generator_path.read_bytes()),
        "source_scaling_generator_sha256": _sha((ROOT / "research/publication_upgrade/solver_scaling.py").read_bytes()),
        "case_count": len(all_cases),
        "schema_validation": {
            "graph": "audit.orchgraph.Graph v1 construction",
            "kernel": "audit.probabilistic_channels.Kernel v1 construction",
            "assignments": "normalized_store for every fixed public/secret pair",
            "solver_invoked": False,
        },
        "cases": all_cases,
    }
    raw = json.dumps(manifest, ensure_ascii=False, indent=2,
                     sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
    manifest_path = OUT / "frozen_inputs.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(raw)
    print(f"validated and froze {len(all_cases)} cases: {manifest_path.relative_to(ROOT)}")
    print(f"generator_sha256={manifest['generator_sha256']}")
    print(f"manifest_sha256={_sha(raw)}")
    for case in all_cases:
        print(f"{case['case_id']} graph={case['graph_sha256']} kernel={case['kernel_sha256']} "
              f"input={case['input_sha256']} expected={case['expected_class']}")


if __name__ == "__main__":
    main()
