"""Independent, finite text semantics for development falsification.

No production analyzer, IR or RNG is imported. Probabilities are exact Fractions.
This deliberately small JSON core is hand-authored, not a verified lowering of
OrchLang. Tokenizers here are exact synthetic byte/codepoint counters, NOT model
tokenizers. Exhaustive results concern only the supplied finite kernels/worlds.
"""
from collections import Counter
from dataclasses import dataclass, replace
from fractions import Fraction
import json


class Unsupported(ValueError):
    pass


def canonical(contract):
    required = {"provider", "revision", "tokenizer", "serializer", "cap",
                "sampling", "error_policy", "accounting", "state"}
    if set(contract) != required:
        raise Unsupported("contract fields must be explicit and exact")
    if contract["state"] != "stateless" or contract["serializer"] != "raw-utf8-v1":
        raise Unsupported("only stateless raw UTF-8 requests supported")
    if type(contract["cap"]) is not int or contract["cap"] < 0:
        raise ValueError("invalid output cap")
    if contract["accounting"] != "all-attempts-input-and-output":
        raise Unsupported("unknown usage accounting")
    return json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def tokens(text, unit):
    if unit == "utf8-bytes-v1":
        return len(text.encode("utf-8"))
    if unit == "unicode-codepoints-v1":
        return len(text)
    raise Unsupported("unknown tokenizer unit: " + unit)


def expression(term, env):
    if isinstance(term, str):
        return term
    if isinstance(term, dict) and set(term) == {"var"}:
        value = env[term["var"]]
        if not isinstance(value, str):
            raise ValueError("request variables must be text")
        return value
    if isinstance(term, dict) and set(term) == {"concat"}:
        return "".join(expression(t, env) for t in term["concat"])
    raise Unsupported("unknown text expression")


@dataclass(frozen=True)
class Event:
    contract: str
    unit: str
    input: int
    output: int
    status: str


@dataclass
class State:
    env: dict
    trace: tuple = ()
    private_outputs: tuple = ()


def aggregate(trace):
    result = Counter()
    for e in trace:
        key = (e.contract, e.unit)
        result[(key, "input")] += e.input
        result[(key, "output")] += e.output
        result[(key, "calls")] += 1
        result[(key, "failures")] += int(e.status == "error")
    return tuple(sorted(result.items()))


class Reference:
    def __init__(self, contracts, kernels, max_paths=100000):
        self.contracts = contracts
        self.kernels = kernels
        self.max_paths = max_paths
        for contract in contracts.values():
            canonical(contract)
            if contract["sampling"] != "explicit-table" or contract["error_policy"] != "status-in-outcome":
                raise Unsupported("only explicit finite tables with status-in-outcome errors are executable")

    def run(self, program, env):
        paths = self.block(program, [(State(dict(env)), Fraction(1))])
        if sum(p for _, p in paths) != 1:
            raise AssertionError("execution lost probability mass")
        return paths

    def block(self, program, paths):
        for node in program:
            next_paths = []
            for state, weight in paths:
                for target, conditional in self.step(node, state):
                    next_paths.append((target, weight * conditional))
                    if len(next_paths) > self.max_paths:
                        raise Unsupported("finite enumeration path limit exceeded")
            paths = next_paths
        return paths

    def step(self, node, state):
        kind = node["kind"]
        if kind == "call":
            contract = self.contracts[node["model"]]
            key = canonical(contract)
            request = expression(node["request"], state.env)
            # Kernels are indexed by semantic contract, not declaration alias.
            table = self.kernels[key]
            outcomes = table.get(request, table.get("*"))
            if outcomes is None:
                raise Unsupported("finite kernel has no entry for request")
            if sum(Fraction(o["p"]) for o in outcomes) != 1:
                raise ValueError("kernel probabilities must sum to one")
            result = []
            for outcome in outcomes:
                p = Fraction(outcome["p"])
                if p < 0:
                    raise ValueError("negative probability")
                if outcome["status"] not in {"ok", "error"}:
                    raise ValueError("unknown response status")
                unit = contract["tokenizer"]
                out = tokens(outcome["text"], unit)
                if out > contract["cap"]:
                    raise ValueError("kernel violates primitive output cap")
                event = Event(key, unit, tokens(request, unit), out, outcome["status"])
                env = dict(state.env)
                env[node["bind"]] = outcome["text"]
                result.append((replace(state, env=env, trace=state.trace + (event,)), p))
            return result
        if kind == "if":
            flag = state.env[node["guard"]]
            if type(flag) is not bool:
                raise ValueError("guard must be boolean")
            arm = node["then"] if flag else node["else"]
            # Block-local value bindings do not escape the join.
            return [(replace(s, env=dict(state.env)), p)
                    for s, p in self.block(arm, [(state, Fraction(1))])]
        if kind == "retry":
            bound = node["bound"]
            if type(bound) is not int or not 0 <= bound <= 16:
                raise Unsupported("retry bound outside development core [0,16]")
            # An attempt succeeds iff every call in that attempt succeeded.
            # Empty attempt succeeds. Every failed call remains billed.
            pending = [(state, Fraction(1))]
            done = []
            for attempt in range(bound):
                following = []
                for before, weight in pending:
                    paths = self.block(node["body"], [(before, Fraction(1))])
                    for after, conditional in paths:
                        after = replace(after, env=dict(state.env))
                        item = (after, weight * conditional)
                        failed = any(e.status == "error" for e in after.trace[len(before.trace):])
                        (following if failed and attempt + 1 < bound else done).append(item)
                pending = following
                if len(done) + len(pending) > self.max_paths:
                    raise Unsupported("retry enumeration limit exceeded")
            return done if bound else pending
        if kind == "private_output":
            return [(replace(state, private_outputs=state.private_outputs +
                             (expression(node["value"], state.env),)), Fraction(1))]
        raise Unsupported("unknown instruction: " + str(kind))


def distribution(paths, observer="ordered"):
    result = Counter()
    for state, weight in paths:
        if observer == "ordered":
            observation = state.trace
        elif observer == "aggregate":
            observation = aggregate(state.trace)
        else:
            raise Unsupported("unknown observer")
        result[observation] += weight
    return {key: value for key, value in result.items() if value}
