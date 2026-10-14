"""Optional, offline LangGraph execution for replay-accepted request graphs.

The graph/certificate gate is intentionally performed before LangGraph is
imported or any StateGraph is built.  The executor implements the version-1
graph transition and full-value test-oracle semantics independently of
``orchgraph.reference_run``; the latter is used only by the differential
benchmark harness.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
from typing import Any, TypedDict

try:
    from replay_graph_certificate import NormalizedGraph, ReplayError, replay, strict_json
except ImportError:  # package import from the repository root
    import sys

    _AUDIT = Path(__file__).resolve().parents[2] / "audit"
    if str(_AUDIT) not in sys.path:
        sys.path.insert(0, str(_AUDIT))
    from replay_graph_certificate import NormalizedGraph, ReplayError, replay, strict_json


MAX_PROBE_CALLS = 10_000
MAX_PROBE_VALUE_BYTES = 1024 * 1024
MAX_PROBE_TRACE_BYTES = 16 * 1024 * 1024
MAX_PROBE_CONTROL_STEPS = 1_000_000
MAX_LANGGRAPH_STATE_NODES = 10_000
MAX_SEED = 2**64 - 1
_ALPHABET = "abcdefghijklmNOPQRSTUVWXYZ0123456789"
_VERIFIED_SEAL = object()


class BackendError(ValueError):
    """A malformed runtime request or resource-limited execution."""


class _EngineState(TypedDict, total=False):
    route: str


@dataclass(frozen=True)
class OracleRequest:
    """One complete abstract request passed to an offline outcome oracle."""

    graph_name: str
    seed: int
    contract: Mapping[str, Any]
    ordinal: int
    template: str
    arguments: tuple[str, ...]
    chars_per_token: int


@dataclass(frozen=True)
class OracleOutcome:
    """Full response text and its usage in the graph's model token unit."""

    response: str
    output_tokens: int


Oracle = Callable[[OracleRequest], OracleOutcome]


@dataclass(frozen=True)
class ExecutionResult:
    """Trace and completion state produced by the real LangGraph engine."""

    status: str
    trace: list[dict[str, Any]]
    stopped: bool
    control_steps: int
    call_count: int
    trace_bytes: int
    graph_sha256: str
    certificate_sha256: str
    replay_attestation: Mapping[str, Any]
    langgraph_version: str
    langgraph_recursion_limit: int
    truncated_at_calls: int | None = None
    failure: Mapping[str, Any] | None = None
    # Eager registers may contain a partial node update at a call/resource cap.
    # Publish a completed value store only after a normal graph stop.
    final_values: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "format": "orchlang-langgraph-execution",
            "version": 2,
            "status": self.status,
            "trace": self.trace,
            "stopped": self.stopped,
            "control_steps": self.control_steps,
            "call_count": self.call_count,
            "trace_bytes": self.trace_bytes,
            "final_values": dict(self.final_values) if self.final_values is not None else None,
            "graph_sha256": self.graph_sha256,
            "certificate_sha256": self.certificate_sha256,
            "replay_attestation": dict(self.replay_attestation),
            "backend": {
                "name": "langgraph",
                "version": self.langgraph_version,
                "recursion_limit": self.langgraph_recursion_limit,
            },
        }
        if self.truncated_at_calls is not None:
            result["truncated_at_calls"] = self.truncated_at_calls
        if self.failure is not None:
            result["failure"] = dict(self.failure)
        return result


class VerifiedGraph:
    """Graph bytes that passed the independent source-bound replay gate."""

    __slots__ = ("_raw_graph", "_raw_certificate", "_attestation_json", "_seal")

    def __init__(self, raw_graph: bytes, raw_certificate: bytes,
                 attestation: Mapping[str, Any], *,
                 _seal: object | None = None):
        if _seal is not _VERIFIED_SEAL:
            raise TypeError("VerifiedGraph values must be created by prepare_graph")
        # Store only immutable source bytes and a serialized attestation.  The
        # normalized graph is deliberately reconstructed on access, so a
        # caller cannot mutate a prepared view and later execute those edits.
        object.__setattr__(self, "_raw_graph", bytes(raw_graph))
        object.__setattr__(self, "_raw_certificate", bytes(raw_certificate))
        object.__setattr__(
            self,
            "_attestation_json",
            json.dumps(dict(attestation), ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")),
        )
        object.__setattr__(self, "_seal", _seal)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("VerifiedGraph values are read-only")

    @property
    def raw_graph(self) -> bytes:
        return self._raw_graph

    @property
    def raw_certificate(self) -> bytes:
        return self._raw_certificate

    @property
    def graph(self) -> NormalizedGraph:
        return NormalizedGraph(strict_json(self._raw_graph, "source graph"))

    @property
    def attestation(self) -> Mapping[str, Any]:
        # Return a fresh nested object; mutations cannot change the stored
        # source-binding evidence associated with this verified handle.
        return json.loads(self._attestation_json)


@dataclass
class _Run:
    graph: NormalizedGraph
    values: dict[str, Any]
    seed: int
    oracle: Oracle
    max_calls: int
    max_control_steps: int
    trace: list[dict[str, Any]] = field(default_factory=list)
    ordinals: dict[str, int] = field(default_factory=dict)
    control_steps: int = 0
    trace_bytes: int = 0
    status: str = "running"
    stopped: bool = False
    truncated_at_calls: int | None = None
    failure: dict[str, Any] | None = None

    def consume_control_step(self, state_name: str, event_name: str) -> None:
        self.control_steps += 1
        if self.control_steps > self.max_control_steps:
            raise BackendError(
                f"control-step cap {self.max_control_steps} exceeded at "
                f"{state_name}:{event_name}"
            )

    def add_trace(self, event: dict[str, Any], request_bytes: int,
                  response_bytes: int) -> None:
        next_total = self.trace_bytes + request_bytes + response_bytes
        if next_total > MAX_PROBE_TRACE_BYTES:
            raise BackendError("request/response trace byte resource cap reached")
        self.trace.append(event)
        self.trace_bytes = next_total


class OfflineOmegaOracle:
    """Deterministic full-text implementation of the declared test Ω oracle.

    This recreates the documented offline oracle key and response generator.
    It is a test provider, not a real model client or a claim about production
    provider behavior.
    """

    def __call__(self, request: OracleRequest) -> OracleOutcome:
        key = json.dumps(
            [request.graph_name, request.seed, dict(request.contract), request.ordinal,
             request.template, list(request.arguments)],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        cap = int(request.contract["max_tokens"])
        output_tokens = int.from_bytes(digest[:8], "big") % (min(cap, 32) + 1)
        response_bytes = output_tokens * request.chars_per_token
        if response_bytes > MAX_PROBE_VALUE_BYTES:
            raise BackendError("offline Ω response exceeds the value byte limit")
        response = "".join(
            _ALPHABET[digest[index % len(digest)] % len(_ALPHABET)]
            for index in range(response_bytes)
        )
        return OracleOutcome(response=response, output_tokens=output_tokens)


class OfflineRequestSession:
    """Full-text request helper for source-authored LangGraph nodes.

    The source frontend can bind this session to a static model-alias map and
    expose its ``request`` and ``tokens`` methods as offline helpers.  The
    session has the same normalized request identity, per-contract ordinals,
    outcome validation, and trace record shape as the graph backend.
    """

    def __init__(self, graph_name: str, seed: int,
                 contracts: Mapping[str, Mapping[str, Any]],
                 chars_per_token: int = 4, oracle: Oracle | None = None,
                 max_calls: int = 100):
        if not isinstance(graph_name, str) or not graph_name:
            raise BackendError("graph_name must be nonempty text")
        self.seed = _natural(seed, "seed", maximum=MAX_SEED)
        self.divisor = _natural(chars_per_token, "chars_per_token", minimum=1)
        self.max_calls = _natural(max_calls, "max_calls", minimum=1,
                                  maximum=MAX_PROBE_CALLS)
        if not isinstance(contracts, Mapping) or not contracts:
            raise BackendError("contracts must be a nonempty model-alias mapping")
        self.contracts = {alias: self._normal_contract(contract)
                          for alias, contract in contracts.items()}
        if not all(isinstance(alias, str) and alias for alias in self.contracts):
            raise BackendError("model aliases must be nonempty text")
        self.graph_name = graph_name
        self.oracle = oracle if oracle is not None else OfflineOmegaOracle()
        self.ordinals: dict[str, int] = {}
        self.trace: list[dict[str, Any]] = []
        self.trace_bytes = 0

    @staticmethod
    def _normal_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(contract, Mapping):
            raise BackendError("model contract must be a mapping")
        if "has_unit_price" in contract:
            required = {"provider", "model", "max_tokens", "has_unit_price", "unit_price"}
            if set(contract) != required:
                raise BackendError("normalized model contract has unexpected fields")
            has_price = contract["has_unit_price"]
            price = contract["unit_price"]
        else:
            required = {"provider", "model", "max_tokens"}
            if set(contract) not in (required, required | {"unit_price"}):
                raise BackendError("model contract has unexpected fields")
            has_price = "unit_price" in contract
            price = contract.get("unit_price", 0)
        if not all(isinstance(contract.get(field), str) and contract[field]
                   for field in ("provider", "model")):
            raise BackendError("model provider and identifier must be nonempty text")
        cap = _natural(contract.get("max_tokens"), "model max_tokens", minimum=1)
        if type(has_price) is not bool or type(price) not in (int, float):
            raise BackendError("model price-presence/value fields are malformed")
        try:
            finite_price = float(price)
        except (OverflowError, ValueError) as error:
            raise BackendError("model unit_price is not finite") from error
        if not math.isfinite(finite_price) or finite_price < 0:
            raise BackendError("model unit_price must be finite and nonnegative")
        if not has_price and finite_price != 0:
            raise BackendError("an absent model unit_price must normalize to zero")
        return {
            "provider": contract["provider"],
            "model": contract["model"],
            "max_tokens": cap,
            "has_unit_price": has_price,
            "unit_price": finite_price,
        }

    def tokens(self, text: str) -> int:
        encoded = _utf8(text, "token-count input")
        if len(encoded) > MAX_PROBE_VALUE_BYTES:
            raise BackendError("token-count input exceeds the value byte limit")
        return (len(encoded) + self.divisor - 1) // self.divisor

    def request(self, model_alias: str, template: str,
                arguments: list[str] | tuple[str, ...]) -> str:
        if model_alias not in self.contracts:
            raise BackendError(f"unknown model alias {model_alias!r}")
        contract = self.contracts[model_alias]
        return self.invoke(contract=contract, template=template, arguments=arguments)

    def invoke(self, *, contract: Mapping[str, Any], template: str,
               arguments: list[str] | tuple[str, ...]) -> str:
        if len(self.trace) >= self.max_calls:
            raise BackendError(f"offline request-session call cap {self.max_calls} reached")
        normalized = self._normal_contract(contract)
        if not isinstance(template, str) or not isinstance(arguments, (list, tuple)):
            raise BackendError("offline request requires a template and ordered argument sequence")
        _utf8(template, "request template")
        values = list(arguments)
        if not all(isinstance(argument, str) for argument in values):
            raise BackendError("request arguments must all be text")
        request_bytes = len(template.encode("utf-8"))
        for argument in values:
            request_bytes += len(_utf8(argument, "request argument"))
        if request_bytes > MAX_PROBE_VALUE_BYTES:
            raise BackendError("request exceeds the value byte limit")
        contract_key = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        ordinal = self.ordinals.get(contract_key, 0)
        request = OracleRequest(
            graph_name=self.graph_name,
            seed=self.seed,
            contract=normalized,
            ordinal=ordinal,
            template=template,
            arguments=tuple(values),
            chars_per_token=self.divisor,
        )
        outcome = self.oracle(request)
        # The request helper has no graph object, but output limits depend only
        # on the shared byte divisor.  Use the same validator's interface.
        response_bytes = _utf8(outcome.response, "oracle response") if isinstance(
            outcome, OracleOutcome
        ) else b""
        if len(response_bytes) > MAX_PROBE_VALUE_BYTES:
            raise BackendError("oracle response exceeds the value byte limit")
        if not isinstance(outcome, OracleOutcome):
            raise BackendError("oracle must return an OracleOutcome")
        output_tokens = _natural(
            outcome.output_tokens, "oracle output_tokens", maximum=normalized["max_tokens"]
        )
        if self.tokens(outcome.response) > output_tokens:
            raise BackendError("oracle full response exceeds its reported output-token usage")
        next_trace_bytes = self.trace_bytes + request_bytes + len(response_bytes)
        if next_trace_bytes > MAX_PROBE_TRACE_BYTES:
            raise BackendError("request/response trace byte resource cap reached")
        self.trace.append({
            "contract": normalized,
            "ordinal": ordinal,
            "template": template,
            "arguments": values,
            "response": outcome.response,
            "input_tokens": self.tokens(template) + sum(self.tokens(value) for value in values),
            "output_tokens": output_tokens,
        })
        self.trace_bytes = next_trace_bytes
        self.ordinals[contract_key] = ordinal + 1
        return outcome.response


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _natural(value: Any, label: str, *, minimum: int = 0,
             maximum: int = 2**64 - 2) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise BackendError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _utf8(value: Any, label: str) -> bytes:
    if not isinstance(value, str):
        raise BackendError(f"{label} must be UTF-8 text")
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise BackendError(f"{label} contains a non-scalar Unicode code point") from error


def _estimate(graph: NormalizedGraph, text: str) -> int:
    size = len(_utf8(text, "text value"))
    return (size + graph.divisor - 1) // graph.divisor


def _validate_store(graph: NormalizedGraph, store: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(store, Mapping) or not all(isinstance(key, str) for key in store):
        raise BackendError("store must be a mapping with string keys")
    if set(store) != set(graph.inputs):
        raise BackendError("store must name every graph input exactly once")
    values = dict(store)
    for name, declaration in graph.inputs.items():
        value = values[name]
        if declaration["type"] == "boolean":
            if type(value) is not bool:
                raise BackendError(f"Boolean input {name} has the wrong type")
        else:
            encoded = _utf8(value, f"text input {name}")
            if len(encoded) > MAX_PROBE_VALUE_BYTES:
                raise BackendError(f"text input {name} exceeds the value byte limit")
            if _estimate(graph, value) > declaration["max_tokens"]:
                raise BackendError(f"text input {name} exceeds its declared token bound")
    return values


def prepare_graph(graph_bytes: bytes, certificate_bytes: bytes) -> VerifiedGraph:
    """Replay the certificate against these exact graph bytes before use."""

    if not isinstance(graph_bytes, bytes) or not isinstance(certificate_bytes, bytes):
        raise TypeError("graph and certificate must be bytes")
    # This is deliberately the first semantic operation.  No LangGraph module
    # is imported and no StateGraph is built until replay returns verified.
    attestation = replay(graph_bytes, certificate_bytes)
    if attestation.get("status") != "verified":
        raise ReplayError("independent certificate replay did not verify")
    document = strict_json(graph_bytes, "source graph")
    graph = NormalizedGraph(document)
    if attestation.get("source_sha256") != _sha256(graph_bytes):
        raise ReplayError("replay attestation is not bound to the supplied graph bytes")
    if attestation.get("certificate_sha256") != _sha256(certificate_bytes):
        raise ReplayError("replay attestation is not bound to the supplied certificate bytes")
    return VerifiedGraph(graph_bytes, certificate_bytes, attestation,
                         _seal=_VERIFIED_SEAL)


def _validate_outcome(outcome: Any, request: OracleRequest,
                      graph: NormalizedGraph) -> tuple[str, int, int]:
    if isinstance(outcome, Mapping):
        try:
            outcome = OracleOutcome(outcome["response"], outcome["output_tokens"])
        except (KeyError, TypeError) as error:
            raise BackendError("oracle result must contain response and output_tokens") from error
    if not isinstance(outcome, OracleOutcome):
        raise BackendError("oracle must return an OracleOutcome")
    response_bytes = _utf8(outcome.response, "oracle response")
    if len(response_bytes) > MAX_PROBE_VALUE_BYTES:
        raise BackendError("oracle response exceeds the value byte limit")
    output_tokens = _natural(
        outcome.output_tokens, "oracle output_tokens", maximum=request.contract["max_tokens"]
    )
    if _estimate(graph, outcome.response) > output_tokens:
        raise BackendError("oracle full response exceeds its reported output-token usage")
    return outcome.response, output_tokens, len(response_bytes)


def _request_arguments(run: _Run, call: Mapping[str, Any]) -> list[str]:
    arguments: list[str] = []
    for atom in call["arguments"]:
        if "literal" in atom:
            arguments.append(atom["literal"])
        else:
            variable = atom["value"]
            if variable not in run.values:
                raise BackendError(f"request uses uninitialized value {variable}")
            value = run.values[variable]
            if not isinstance(value, str):
                raise BackendError(f"request value {variable} is not text")
            arguments.append(value)
    return arguments


def _eval_guard(run: _Run, decision: Mapping[str, Any]) -> bool:
    guard = decision["guard"]
    variable = guard["value"]
    if variable not in run.values:
        raise BackendError(f"guard uses uninitialized value {variable}")
    value = run.values[variable]
    if "op" not in guard:
        if type(value) is not bool:
            raise BackendError(f"Boolean guard {variable} received a non-Boolean value")
        return value
    if not isinstance(value, str):
        raise BackendError(f"token guard {variable} received a non-text value")
    actual, limit, op = _estimate(run.graph, value), guard["limit"], guard["op"]
    return {
        "<": actual < limit,
        "<=": actual <= limit,
        ">": actual > limit,
        ">=": actual >= limit,
        "==": actual == limit,
        "!=": actual != limit,
    }[op]


def _state_handler(run: _Run, graph: NormalizedGraph,
                   state_name: str) -> Callable[[_EngineState], dict[str, str]]:
    def handle(_: _EngineState) -> dict[str, str]:
        try:
            body = graph.states[state_name]
            for call_index, call in enumerate(body["calls"]):
                run.consume_control_step(state_name, f"call[{call_index}]")
                # Match reference_run's horizon: count this next call event,
                # then truncate without constructing a request or calling Ω.
                if len(run.trace) >= run.max_calls:
                    run.status = "truncated"
                    run.truncated_at_calls = run.max_calls
                    return {"route": "__finish__"}
                contract = graph.models[call["model"]]
                contract_key = json.dumps(
                    contract, sort_keys=True, separators=(",", ":")
                )
                ordinal = run.ordinals.get(contract_key, 0)
                arguments = _request_arguments(run, call)
                request_bytes = len(_utf8(call["template"], "request template"))
                for argument in arguments:
                    request_bytes += len(_utf8(argument, "request argument"))
                if request_bytes > MAX_PROBE_VALUE_BYTES:
                    raise BackendError("request exceeds the value byte limit")
                request = OracleRequest(
                    graph_name=graph.name,
                    seed=run.seed,
                    contract=contract,
                    ordinal=ordinal,
                    template=call["template"],
                    arguments=tuple(arguments),
                    chars_per_token=graph.divisor,
                )
                outcome = run.oracle(request)
                response, output_tokens, response_bytes = _validate_outcome(
                    outcome, request, graph
                )
                input_tokens = _estimate(graph, call["template"]) + sum(
                    _estimate(graph, argument) for argument in arguments
                )
                trace_event = {
                    "contract": contract,
                    "ordinal": ordinal,
                    "template": call["template"],
                    "arguments": arguments,
                    "response": response,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                }
                run.add_trace(trace_event, request_bytes, response_bytes)
                run.ordinals[contract_key] = ordinal + 1
                run.values[call["result"]] = response

            decision = body["next"]
            run.consume_control_step(state_name, decision["kind"])
            kind = decision["kind"]
            if kind == "stop":
                run.status = "stopped"
                run.stopped = True
                return {"route": "__finish__"}
            if kind == "goto":
                target = decision["target"]
            else:
                target = decision["then" if _eval_guard(run, decision) else "else"]
            return {"route": "state:" + target}
        except BackendError as error:
            run.status = "resource_limited" if "cap" in str(error) or "limit" in str(error) else "runtime_error"
            run.failure = {"type": type(error).__name__, "message": str(error)}
            raise

    return handle


def _compile_state_graph(run: _Run):
    """Build the real LangGraph StateGraph; only called after replay success."""

    try:
        from importlib.metadata import version as package_version
        from langgraph.errors import GraphRecursionError
        from langgraph.graph import END, START, StateGraph
    except ImportError as error:  # pragma: no cover - optional runtime missing
        raise BackendError("install integrations/langgraph/requirements.lock first") from error

    graph = run.graph
    node_names = {state: "state__" + state for state in graph.reachable}
    builder = StateGraph(_EngineState)
    routes = {"__finish__": END}
    routes.update({"state:" + state: node_names[state] for state in graph.reachable})
    for state_name in sorted(graph.reachable):
        node_name = node_names[state_name]
        builder.add_node(node_name, _state_handler(run, graph, state_name))
        builder.add_conditional_edges(
            node_name,
            lambda state: state["route"],
            routes,
        )
    builder.add_edge(START, node_names[graph.entry])
    app = builder.compile()
    return app, package_version("langgraph"), GraphRecursionError


def execute_verified(verified: VerifiedGraph, store: Mapping[str, Any], seed: int,
                     oracle: Oracle | None = None, *, max_calls: int = 100,
                     max_control_steps: int = MAX_PROBE_CONTROL_STEPS,
                     recursion_limit: int | None = None) -> ExecutionResult:
    """Execute a replayed graph with the actual pinned LangGraph runtime."""

    if not isinstance(verified, VerifiedGraph) or verified._seal is not _VERIFIED_SEAL:
        raise TypeError("execute_verified requires a value returned by prepare_graph")
    seed = _natural(seed, "seed", maximum=MAX_SEED)
    max_calls = _natural(max_calls, "max_calls", minimum=1, maximum=MAX_PROBE_CALLS)
    max_control_steps = _natural(
        max_control_steps, "max_control_steps", minimum=1,
        maximum=MAX_PROBE_CONTROL_STEPS,
    )
    if recursion_limit is None:
        # Each LangGraph super-step visits at most one source state; each such
        # visit consumes at least one graph control event.  The small cushion
        # lets the explicit event counter report its own cap first.  A tighter
        # engine limit supplied by the caller remains an independent fail-closed
        # guard and is never translated into a successful stop/truncation.
        recursion_limit = max_control_steps + 2
    recursion_limit = _natural(recursion_limit, "recursion_limit", minimum=1,
                               maximum=MAX_PROBE_CONTROL_STEPS + 2)
    graph = verified.graph
    if len(graph.reachable) > MAX_LANGGRAPH_STATE_NODES:
        raise BackendError(
            f"LangGraph reachable-state node cap {MAX_LANGGRAPH_STATE_NODES} exceeded"
        )
    values = _validate_store(graph, store)
    runtime = _Run(
        graph=graph,
        values=values,
        seed=seed,
        oracle=oracle if oracle is not None else OfflineOmegaOracle(),
        max_calls=max_calls,
        max_control_steps=max_control_steps,
    )
    try:
        app, langgraph_version, recursion_error = _compile_state_graph(runtime)
    except BackendError:
        raise
    except Exception as error:
        raise BackendError(f"could not build LangGraph StateGraph: {error}") from error

    try:
        app.invoke({"route": "__start__"}, config={"recursion_limit": recursion_limit})
    except recursion_error as error:
        runtime.status = "resource_limited"
        runtime.failure = {
            "type": "langgraph_recursion_limit",
            "message": str(error),
        }
    except BackendError as error:
        if runtime.failure is None:
            runtime.status = "runtime_error"
            runtime.failure = {"type": type(error).__name__, "message": str(error)}
    except Exception as error:
        runtime.status = "runtime_error"
        runtime.failure = {"type": type(error).__name__, "message": str(error)}

    return ExecutionResult(
        status=runtime.status,
        trace=runtime.trace,
        stopped=runtime.stopped,
        control_steps=runtime.control_steps,
        call_count=len(runtime.trace),
        trace_bytes=runtime.trace_bytes,
        graph_sha256=_sha256(verified.raw_graph),
        certificate_sha256=_sha256(verified.raw_certificate),
        replay_attestation=verified.attestation,
        langgraph_version=langgraph_version,
        langgraph_recursion_limit=recursion_limit,
        truncated_at_calls=runtime.truncated_at_calls,
        failure=runtime.failure,
        final_values=dict(runtime.values) if runtime.status == "stopped" and runtime.stopped else None,
    )


def execute_graph(graph_bytes: bytes, certificate_bytes: bytes,
                  store: Mapping[str, Any], seed: int,
                  oracle: Oracle | None = None, *, max_calls: int = 100,
                  max_control_steps: int = MAX_PROBE_CONTROL_STEPS,
                  recursion_limit: int | None = None) -> ExecutionResult:
    """Replay, validate inputs, then compile and run an optional LangGraph."""

    verified = prepare_graph(graph_bytes, certificate_bytes)
    return execute_verified(
        verified,
        store,
        seed,
        oracle,
        max_calls=max_calls,
        max_control_steps=max_control_steps,
        recursion_limit=recursion_limit,
    )
