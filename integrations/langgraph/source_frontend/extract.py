#!/usr/bin/env python3
"""Static extraction of a small, real LangGraph StateGraph source subset.

Source is parsed as Python and never executed here. The resulting JSON graph
uses the separate request-graph checker and certificate replayer. This module
is deliberately a narrow frontend, not a general Python or LangGraph port.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from typing import Any


FORMAT = "orchlang-langgraph-contracts"
VERSION = 1
GRAPH_FORMAT = "orchlang-request-graph"
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_CONTRACT_BYTES = 1 * 1024 * 1024
MAX_AST_NODES = 250_000
MAX_AST_DEPTH = 128
MAX_ITEMS = 100_000
MAX_TOKEN = 2**64 - 2
MAX_VALUE_BYTES = 1024 * 1024


class FrontendError(ValueError):
    """Source or contract is outside the explicitly supported subset."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FrontendError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise FrontendError(f"non-finite JSON number {value}")


def _reject_json_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise FrontendError(f"non-finite JSON number {value}")
    return number


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FrontendError(f"{label} must be an object")
    return value


def _keys(value: Any, required: set[str], optional: set[str] = (),
          label: str = "object") -> dict[str, Any]:
    obj = _object(value, label)
    missing = required - obj.keys()
    unknown = obj.keys() - required - optional
    if missing or unknown:
        raise FrontendError(
            f"{label} fields differ: missing {sorted(missing)}, unknown {sorted(unknown)}"
        )
    return obj


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not NAME_RE.fullmatch(value):
        raise FrontendError(f"{label} must be a Python identifier")
    return value


def _natural(value: Any, label: str, *, minimum: int = 0,
              maximum: int = MAX_TOKEN) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise FrontendError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _text(value: Any, label: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        raise FrontendError(f"{label} must be a {'nonempty ' if nonempty else ''}string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise FrontendError(f"{label} contains a non-scalar Unicode code point") from error
    return value


def parse_contracts(raw: bytes) -> dict[str, Any]:
    """Strictly parse and normalize source-independent declarations.

    Contracts describe only the initial state labels/bounds and canonical
    model contracts. They cannot describe source calls, routing, or control.
    """
    if not isinstance(raw, bytes) or len(raw) > MAX_CONTRACT_BYTES:
        raise FrontendError(f"contracts exceed {MAX_CONTRACT_BYTES} bytes")
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs_no_duplicates,
                         parse_constant=_reject_json_constant, parse_float=_reject_json_float)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise FrontendError(f"invalid contracts JSON: {error}") from error
    root = _keys(doc, {"format", "version", "name", "inputs", "models"},
                 {"chars_per_token"}, "contracts")
    if root["format"] != FORMAT or type(root["version"]) is not int or root["version"] != VERSION:
        raise FrontendError("unknown contract format or version")
    name = _identifier(root["name"], "workflow name")
    divisor = _natural(root.get("chars_per_token", 4), "chars_per_token", minimum=1)
    raw_inputs = _object(root["inputs"], "inputs")
    raw_models = _object(root["models"], "models")
    if len(raw_inputs) + len(raw_models) > MAX_ITEMS:
        raise FrontendError("contract declaration limit exceeded")

    inputs: dict[str, dict[str, Any]] = {}
    for key, source in raw_inputs.items():
        _identifier(key, "input key")
        item = _keys(source, {"type", "label"}, {"max_tokens"}, f"input {key}")
        if item["type"] not in ("text", "boolean"):
            raise FrontendError(f"input {key} type must be text or boolean")
        if item["label"] not in ("public", "secret"):
            raise FrontendError(f"input {key} label must be public or secret")
        normalized: dict[str, Any] = {"type": item["type"], "label": item["label"]}
        if item["type"] == "text":
            if "max_tokens" not in item:
                raise FrontendError(f"text input {key} needs max_tokens")
            normalized["max_tokens"] = _natural(item["max_tokens"], f"input {key} max_tokens")
        elif "max_tokens" in item:
            raise FrontendError(f"Boolean input {key} must not declare max_tokens")
        inputs[key] = normalized

    models: dict[str, dict[str, Any]] = {}
    for alias, source in raw_models.items():
        _identifier(alias, "model alias")
        item = _keys(source, {"provider", "model", "max_tokens"}, {"unit_price"},
                     f"model {alias}")
        provider = _text(item["provider"], f"model {alias} provider", nonempty=True)
        model = _text(item["model"], f"model {alias} id", nonempty=True)
        cap = _natural(item["max_tokens"], f"model {alias} max_tokens", minimum=1)
        normalized = {"provider": provider, "model": model, "max_tokens": cap}
        if "unit_price" in item:
            price = item["unit_price"]
            if type(price) not in (int, float):
                raise FrontendError(f"model {alias} unit_price must be numeric")
            try:
                finite = float(price)
            except (OverflowError, ValueError) as error:
                raise FrontendError(f"model {alias} unit_price must be finite") from error
            if not math.isfinite(finite) or finite < 0:
                raise FrontendError(f"model {alias} unit_price must be finite and nonnegative")
            normalized["unit_price"] = finite
        models[alias] = normalized

    for key, item in inputs.items():
        if item["type"] == "text" and item["max_tokens"] * divisor > MAX_VALUE_BYTES:
            raise FrontendError(f"text input {key} declared bound exceeds the offline value-byte limit")
    for alias, item in models.items():
        if item["max_tokens"] * divisor > MAX_VALUE_BYTES:
            raise FrontendError(f"model {alias} output cap exceeds the offline value-byte limit")

    return {"format": FORMAT, "version": VERSION, "name": name,
            "chars_per_token": divisor, "inputs": inputs, "models": models}


def _location(node: ast.AST) -> dict[str, int]:
    return {"line": int(getattr(node, "lineno", 1)),
            "column": int(getattr(node, "col_offset", 0)) + 1}


def _docstring(stmt: ast.stmt) -> bool:
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) \
        and isinstance(stmt.value.value, str)


def _validate_ast_size(tree: ast.AST) -> None:
    count = 0
    stack: list[tuple[ast.AST, int]] = [(tree, 1)]
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > MAX_AST_NODES:
            raise FrontendError(f"Python AST exceeds {MAX_AST_NODES} nodes")
        if depth > MAX_AST_DEPTH:
            raise FrontendError(f"Python AST nesting exceeds {MAX_AST_DEPTH}")
        stack.extend((child, depth + 1) for child in ast.iter_child_nodes(node))


@dataclass
class _Arg:
    kind: str
    value: str
    location: dict[str, int]


@dataclass
class _Call:
    local: str
    model: str
    template: str
    arguments: list[_Arg]
    location: dict[str, int]
    graph_result: str = ""


@dataclass
class _Node:
    source_name: str
    function_name: str
    function: ast.FunctionDef
    graph_name: str
    calls: list[_Call] = field(default_factory=list)
    returns: dict[str, str] = field(default_factory=dict)  # source key -> local call result
    edge: tuple[str, str] | None = None
    conditional: tuple[str, str, dict[str, str], ast.FunctionDef] | None = None
    source_location: dict[str, int] = field(default_factory=dict)


class _Extractor:
    def __init__(self, source_raw: bytes, contracts_raw: bytes,
                 contracts: dict[str, Any]):
        if not isinstance(source_raw, bytes) or len(source_raw) > MAX_SOURCE_BYTES:
            raise FrontendError(f"source exceeds {MAX_SOURCE_BYTES} bytes")
        try:
            source_text = source_raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise FrontendError("Python source must be UTF-8") from error
        try:
            self.tree = ast.parse(source_text, filename="<langgraph-source>", mode="exec")
        except (SyntaxError, ValueError, RecursionError) as error:
            raise FrontendError(f"invalid Python source: {error}") from error
        _validate_ast_size(self.tree)
        self.source_raw = source_raw
        self.contracts_raw = contracts_raw
        self.contracts = contracts
        self.functions: dict[str, ast.FunctionDef] = {}
        self.state_name = ""
        self.state_fields: dict[str, str] = {}
        self.builder_name = ""
        self.compiled_name = ""
        self.node_specs: list[tuple[str, str, ast.AST]] = []
        self.edges: list[tuple[ast.AST, ast.AST, ast.AST]] = []
        self.conditionals: list[tuple[ast.AST, ast.AST, ast.AST, ast.AST]] = []
        self._router_functions: set[str] = set()

    def extract(self) -> tuple[dict[str, Any], dict[str, Any]]:
        self._parse_module()
        self._validate_state()
        nodes = self._parse_nodes()
        self._parse_edges(nodes)
        self._derive_registers(nodes)
        graph, mapping = self._lower(nodes)
        return graph, mapping

    def _parse_module(self) -> None:
        saw_typing = saw_langgraph = saw_runtime = False
        saw_typed_dict = False
        saw_builder = saw_compile = False
        for index, statement in enumerate(self.tree.body):
            if index == 0 and _docstring(statement):
                continue
            if isinstance(statement, ast.ImportFrom):
                if statement.level != 0 or any(alias.asname for alias in statement.names):
                    raise FrontendError(f"unsupported import at {_location(statement)}")
                names = {alias.name for alias in statement.names}
                if statement.module == "typing" and names == {"TypedDict"} and not saw_typing:
                    saw_typing = True
                elif statement.module == "langgraph.graph" and names == {"StateGraph", "START", "END"} and not saw_langgraph:
                    saw_langgraph = True
                elif statement.module == "integrations.langgraph.source_frontend.runtime" and names == {"request", "tokens"} and not saw_runtime:
                    saw_runtime = True
                else:
                    raise FrontendError(f"unsupported import at {_location(statement)}")
                continue
            if isinstance(statement, ast.ClassDef):
                if saw_typed_dict:
                    raise FrontendError("exactly one TypedDict state class is supported")
                if not saw_typing or saw_builder:
                    raise FrontendError("TypedDict state class must follow its import and precede StateGraph construction")
                self._parse_state_class(statement)
                saw_typed_dict = True
                continue
            if isinstance(statement, ast.FunctionDef):
                if saw_builder:
                    raise FrontendError("all node and route functions must be defined before StateGraph construction")
                if statement.name in self.functions:
                    raise FrontendError(f"duplicate function {statement.name!r}")
                if statement.name in {"TypedDict", "StateGraph", "START", "END", "request", "tokens", self.state_name}:
                    raise FrontendError(f"function {statement.name!r} shadows a required API name")
                self.functions[statement.name] = statement
                continue
            if isinstance(statement, ast.Assign):
                if len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
                    raise FrontendError(f"unsupported top-level assignment at {_location(statement)}")
                value = statement.value
                if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                        and value.func.id == "StateGraph" and len(value.args) == 1
                        and not value.keywords and isinstance(value.args[0], ast.Name)):
                    if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                            and isinstance(value.func.value, ast.Name) and value.func.attr == "compile"
                            and value.func.value.id == self.builder_name and not value.args and not value.keywords):
                        raise FrontendError(f"only builder and compile assignments are supported at {_location(statement)}")
                    if not self.builder_name or saw_compile:
                        raise FrontendError("compile must be assigned exactly once after StateGraph construction")
                    self.compiled_name = statement.targets[0].id
                    if self.compiled_name in {"TypedDict", "StateGraph", "START", "END", "request", "tokens", self.state_name}:
                        raise FrontendError("compiled graph variable shadows a required API name")
                    if self.compiled_name in self.functions:
                        raise FrontendError("compiled graph variable shadows a node or route function")
                    saw_compile = True
                    if index != len(self.tree.body) - 1:
                        raise FrontendError("compiled workflow assignment must be the last top-level statement")
                    continue
                if saw_builder:
                    raise FrontendError("exactly one StateGraph construction is supported")
                if not saw_typing or not saw_langgraph or not saw_runtime:
                    raise FrontendError("required TypedDict, LangGraph, and pure-helper imports must precede StateGraph")
                if saw_compile:
                    raise FrontendError("StateGraph cannot be constructed after compile")
                if value.args[0].id != self.state_name:
                    raise FrontendError("StateGraph must use the declared TypedDict class")
                self.builder_name = statement.targets[0].id
                if self.builder_name in {"TypedDict", "StateGraph", "START", "END", "request", "tokens"}:
                    raise FrontendError("builder variable shadows a required API name")
                if self.builder_name == self.state_name or self.builder_name in self.functions:
                    raise FrontendError("builder variable shadows the state class or a node/route function")
                saw_builder = True
                continue
            if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
                call = statement.value
                if not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name) \
                        or call.func.value.id != self.builder_name or not self.builder_name:
                    raise FrontendError(f"unsupported top-level expression at {_location(statement)}")
                if call.keywords:
                    raise FrontendError(f"builder methods may not use keyword arguments at {_location(statement)}")
                if call.func.attr == "add_node" and len(call.args) == 2:
                    if not isinstance(call.args[0], ast.Constant) or not isinstance(call.args[0].value, str) \
                            or not isinstance(call.args[1], ast.Name):
                        raise FrontendError(f"add_node requires a literal name and named function at {_location(call)}")
                    self.node_specs.append((call.args[0].value, call.args[1].id, call))
                elif call.func.attr == "add_edge" and len(call.args) == 2:
                    self.edges.append((call.args[0], call.args[1], call))
                elif call.func.attr == "add_conditional_edges" and len(call.args) == 3:
                    self.conditionals.append((call.args[0], call.args[1], call.args[2], call))
                else:
                    raise FrontendError(f"unsupported StateGraph method {call.func.attr!r} at {_location(call)}")
                continue
            raise FrontendError(f"unsupported top-level statement {type(statement).__name__} at {_location(statement)}")
        if not all((saw_typing, saw_langgraph, saw_runtime, saw_typed_dict, saw_builder, saw_compile)):
            raise FrontendError("source needs the three allowed imports, one TypedDict, one StateGraph, and one compiled assignment")

    def _parse_state_class(self, node: ast.ClassDef) -> None:
        if node.name in {"TypedDict", "StateGraph", "START", "END", "request", "tokens"}:
            raise FrontendError(f"state class {node.name!r} shadows a required API name")
        if node.decorator_list or node.keywords or getattr(node, "type_params", []) or len(node.bases) != 1 \
                or not isinstance(node.bases[0], ast.Name) or node.bases[0].id != "TypedDict":
            raise FrontendError("state must be one undecorated TypedDict class")
        if self.state_name:
            raise FrontendError("exactly one state TypedDict is supported")
        if node.name in self.functions:
            raise FrontendError("state class shadows a node or route function")
        self.state_name = node.name
        fields: dict[str, str] = {}
        for statement in node.body:
            if _docstring(statement) and statement is node.body[0]:
                continue
            if not isinstance(statement, ast.AnnAssign) or not statement.simple or statement.value is not None \
                    or not isinstance(statement.target, ast.Name) or not isinstance(statement.annotation, ast.Name) \
                    or statement.annotation.id not in ("str", "bool"):
                raise FrontendError(f"state fields must have plain str/bool annotations at {_location(statement)}")
            key = _identifier(statement.target.id, "state field")
            if key in fields:
                raise FrontendError(f"duplicate state field {key!r}")
            fields[key] = "text" if statement.annotation.id == "str" else "boolean"
        self.state_fields = fields

    def _validate_state(self) -> None:
        inputs = self.contracts["inputs"]
        if set(inputs) - self.state_fields.keys():
            raise FrontendError(f"contract inputs absent from TypedDict: {sorted(set(inputs) - self.state_fields.keys())}")
        if set(self.state_fields) - inputs.keys() and any(
            self.state_fields[key] != "text" for key in set(self.state_fields) - inputs.keys()
        ):
            raise FrontendError("non-input result state fields must be text")
        for key, item in inputs.items():
            if self.state_fields[key] != item["type"]:
                raise FrontendError(f"TypedDict type for input {key!r} differs from contracts")
        if not self.contracts["models"] and self.node_specs:
            # A graph with no model calls can still use the frontend. A
            # request itself will fail validation below if no model exists.
            pass

    def _function_args(self, function: ast.FunctionDef) -> str:
        args = function.args
        if function.decorator_list or function.returns is not None or function.type_comment \
                or getattr(function, "type_params", []) \
                or args.vararg or args.kwarg or args.kwonlyargs or args.kw_defaults \
                or len(args.args) != 1 or args.posonlyargs or args.defaults \
                or args.args[0].arg != "state" or args.args[0].annotation is not None:
            raise FrontendError(f"function {function.name!r} must be undecorated def f(state):")
        return "state"

    def _parse_nodes(self) -> dict[str, _Node]:
        nodes: dict[str, _Node] = {}
        used_functions: set[str] = set()
        for source_name, function_name, syntax in self.node_specs:
            _text(source_name, "node name", nonempty=True)
            if source_name in nodes:
                raise FrontendError(f"duplicate StateGraph node {source_name!r}")
            if function_name not in self.functions:
                raise FrontendError(f"node function {function_name!r} is not defined")
            if function_name in used_functions:
                raise FrontendError(f"function {function_name!r} is reused as a node")
            used_functions.add(function_name)
            function = self.functions[function_name]
            self._function_args(function)
            body = list(function.body)
            if body and _docstring(body[0]):
                body.pop(0)
            if not body or not isinstance(body[-1], ast.Return):
                raise FrontendError(f"node {source_name!r} must end by returning a state-update dict")
            return_stmt = body.pop()
            calls: list[_Call] = []
            locals_: dict[str, int] = {}
            reads: list[tuple[str, int, dict[str, int]]] = []
            for statement in body:
                if not isinstance(statement, ast.Assign) or len(statement.targets) != 1 \
                        or not isinstance(statement.targets[0], ast.Name):
                    raise FrontendError(f"node {source_name!r} allows only local=request(...) assignments at {_location(statement)}")
                local = _identifier(statement.targets[0].id, "request result local")
                if local in {"state", "request", "tokens"} or local in locals_:
                    raise FrontendError(f"node {source_name!r} reassigns local {local!r}")
                call = self._parse_request(statement.value, local, calls, locals_, reads)
                locals_[local] = len(calls)
                calls.append(call)
            returns = self._parse_return(return_stmt, locals_, source_name)
            writer_index = {field: locals_[local] for field, local in returns.items()}
            for field, call_index, location in reads:
                if field in writer_index and call_index > writer_index[field]:
                    raise FrontendError(
                        f"node {source_name!r} reads state[{field!r}] after its returned result is produced at {location}; "
                        "LangGraph applies returned state updates atomically, but graph registers update per call"
                    )
            nodes[source_name] = _Node(
                source_name, function_name, function,
                graph_name=f"lg_state_{len(nodes):04d}", calls=calls,
                returns=returns, source_location=_location(syntax),
            )
        # Every top-level function must be bound to exactly one node or route.
        self._node_function_names = used_functions
        return nodes

    def _parse_request(self, value: ast.AST, local: str, calls: list[_Call],
                       locals_: dict[str, int], reads: list[tuple[str, int, dict[str, int]]]) -> _Call:
        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Name) \
                or value.func.id != "request" or value.args:
            raise FrontendError(f"request assignment must call request with named keywords at {_location(value)}")
        if any(keyword.arg is None for keyword in value.keywords):
            raise FrontendError(f"request does not support keyword expansion at {_location(value)}")
        kwargs: dict[str, ast.AST] = {}
        for keyword in value.keywords:
            if keyword.arg in kwargs:
                raise FrontendError(f"duplicate request keyword {keyword.arg!r}")
            kwargs[keyword.arg] = keyword.value
        if set(kwargs) != {"model", "template", "arguments"}:
            raise FrontendError(f"request requires exactly model, template, and arguments at {_location(value)}")
        alias = self._constant_text(kwargs["model"], "request model alias")
        if alias not in self.contracts["models"]:
            raise FrontendError(f"request names undeclared model alias {alias!r}")
        template = self._constant_text(kwargs["template"], "request template")
        if len(template.encode("utf-8")) > MAX_VALUE_BYTES:
            raise FrontendError("request template exceeds the offline value-byte limit")
        raw_args = kwargs["arguments"]
        if not isinstance(raw_args, ast.List):
            raise FrontendError(f"request arguments must be an ordered list at {_location(raw_args)}")
        atoms: list[_Arg] = []
        for argument in raw_args.elts:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                _text(argument.value, "request literal")
                if len(argument.value.encode("utf-8")) > MAX_VALUE_BYTES:
                    raise FrontendError("request literal exceeds the offline value-byte limit")
                atoms.append(_Arg("literal", argument.value, _location(argument)))
            elif isinstance(argument, ast.Subscript):
                field_name = self._state_subscript(argument)
                if field_name not in self.state_fields:
                    raise FrontendError(f"request reads undeclared state field {field_name!r}")
                if self.state_fields[field_name] != "text":
                    raise FrontendError(f"request cannot use non-text state field {field_name!r}")
                declared = self.contracts["inputs"].get(field_name)
                if declared is not None and declared["label"] == "secret":
                    raise FrontendError(f"request cannot consume direct secret input state field {field_name!r}")
                atoms.append(_Arg("state", field_name, _location(argument)))
                reads.append((field_name, len(calls), _location(argument)))
            elif isinstance(argument, ast.Name) and argument.id in locals_:
                atoms.append(_Arg("local", argument.id, _location(argument)))
            else:
                raise FrontendError(
                    f"request arguments must be text literals, state['key'], or earlier local results at {_location(argument)}"
                )
        return _Call(local, alias, template, atoms, _location(value))

    def _parse_return(self, statement: ast.Return, locals_: dict[str, int],
                      node_name: str) -> dict[str, str]:
        value = statement.value
        if not isinstance(value, ast.Dict):
            raise FrontendError(f"node {node_name!r} must return a plain dict literal")
        result: dict[str, str] = {}
        used_locals: set[str] = set()
        for key, item in zip(value.keys, value.values):
            if key is None:
                raise FrontendError(f"node {node_name!r} return dict cannot use ** expansion")
            state_key = self._constant_text(key, "returned state key")
            if state_key not in self.state_fields:
                raise FrontendError(f"node {node_name!r} returns undeclared state field {state_key!r}")
            if state_key in self.contracts["inputs"]:
                raise FrontendError(f"external input state field {state_key!r} is immutable in this subset")
            if state_key in result:
                raise FrontendError(f"node {node_name!r} returns state field {state_key!r} more than once")
            if not isinstance(item, ast.Name) or item.id not in locals_:
                raise FrontendError(f"node {node_name!r} return values must be unique local request results")
            if item.id in used_locals:
                raise FrontendError(f"node {node_name!r} cannot copy one result into multiple state fields")
            used_locals.add(item.id)
            result[state_key] = item.id
        return result

    @staticmethod
    def _constant_text(node: ast.AST, label: str) -> str:
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            raise FrontendError(f"{label} must be a literal string at {_location(node)}")
        return _text(node.value, label)

    @staticmethod
    def _state_subscript(node: ast.Subscript) -> str:
        if not isinstance(node.value, ast.Name) or node.value.id != "state" \
                or not isinstance(node.slice, ast.Constant) or not isinstance(node.slice.value, str):
            raise FrontendError(f"only state['literal_key'] indexing is supported at {_location(node)}")
        return _identifier(node.slice.value, "state key")

    def _parse_edges(self, nodes: dict[str, _Node]) -> None:
        entry: str | None = None
        for source_node, target_node, syntax in self.edges:
            if isinstance(source_node, ast.Name) and source_node.id == "START":
                if entry is not None:
                    raise FrontendError("exactly one START edge is supported")
                target = self._edge_target(target_node, nodes, allow_end=False)
                entry = target
                continue
            source = self._constant_text(source_node, "edge source")
            target = self._edge_target(target_node, nodes, allow_end=True)
            if source not in nodes:
                raise FrontendError(f"edge names unknown source node {source!r}")
            node = nodes[source]
            if node.edge is not None or node.conditional is not None:
                raise FrontendError(f"node {source!r} has more than one transition definition")
            node.edge = (target, "end" if isinstance(target_node, ast.Name) and target_node.id == "END" else "node")
            node.source_location = _location(syntax)
        for source_node, route_node, mapping_node, syntax in self.conditionals:
            source = self._constant_text(source_node, "conditional source")
            if source not in nodes:
                raise FrontendError(f"conditional edges name unknown source node {source!r}")
            if not isinstance(route_node, ast.Name) or route_node.id not in self.functions:
                raise FrontendError(f"conditional route must name a top-level function at {_location(route_node)}")
            route_function = self.functions[route_node.id]
            if route_node.id in getattr(self, "_node_function_names", set()):
                raise FrontendError(f"function {route_node.id!r} cannot be both node and router")
            node = nodes[source]
            if node.edge is not None or node.conditional is not None:
                raise FrontendError(f"node {source!r} has more than one transition definition")
            mapping = self._route_map(mapping_node, nodes)
            guard, true_label, false_label = self._parse_router(route_function)
            if set(mapping) != {true_label, false_label} or true_label == false_label:
                raise FrontendError(f"conditional mapping for {source!r} must match the two router labels")
            node.conditional = (guard, true_label, mapping, route_function)
            node.source_location = _location(syntax)
            self._router_functions.add(route_node.id)
        if entry is None:
            raise FrontendError("one add_edge(START, node) entry is required")
        self.entry_source = entry
        for source, node in nodes.items():
            if node.edge is None and node.conditional is None:
                raise FrontendError(f"node {source!r} has no outgoing edge or conditional route")
        if set(self.functions) != getattr(self, "_node_function_names", set()) | getattr(self, "_router_functions", set()):
            unused = sorted(set(self.functions) - getattr(self, "_node_function_names", set()) - getattr(self, "_router_functions", set()))
            multiply = sorted((getattr(self, "_node_function_names", set()) & getattr(self, "_router_functions", set())))
            raise FrontendError(f"unbound or multiply bound top-level functions: unused={unused}, overlap={multiply}")
        self._validate_reachability(nodes)

    def _edge_target(self, node: ast.AST, nodes: dict[str, _Node], *, allow_end: bool) -> str:
        if isinstance(node, ast.Name) and node.id == "END":
            if not allow_end:
                raise FrontendError("START cannot connect directly to END")
            return "END"
        target = self._constant_text(node, "edge target")
        if target not in nodes:
            # add_node declarations are collected before edges, so this also
            # rejects forward-looking names that were never registered.
            raise FrontendError(f"edge names unknown target node {target!r}")
        return target

    def _route_map(self, node: ast.AST, nodes: dict[str, _Node]) -> dict[str, str]:
        if not isinstance(node, ast.Dict) or not node.keys or len(node.keys) != len(node.values):
            raise FrontendError(f"conditional route map must be a nonempty literal dict at {_location(node)}")
        result: dict[str, str] = {}
        for key_node, target_node in zip(node.keys, node.values):
            label = self._constant_text(key_node, "route label")
            if label in result:
                raise FrontendError(f"duplicate route label {label!r}")
            result[label] = self._edge_target(target_node, nodes, allow_end=True)
        return result

    def _parse_router(self, function: ast.FunctionDef) -> tuple[dict[str, Any], str, str]:
        self._function_args(function)
        body = list(function.body)
        if body and _docstring(body[0]):
            body.pop(0)
        test: ast.AST
        true_label: str
        false_label: str
        if len(body) == 1 and isinstance(body[0], ast.Return) and isinstance(body[0].value, ast.IfExp):
            expr = body[0].value
            test = expr.test
            true_label = self._constant_text(expr.body, "true route label")
            false_label = self._constant_text(expr.orelse, "false route label")
        elif len(body) in (1, 2) and isinstance(body[0], ast.If):
            conditional = body[0]
            if len(conditional.body) != 1:
                raise FrontendError(f"router {function.name!r} requires one return in each arm")
            true_label = self._return_label(conditional.body[0], "true route")
            if conditional.orelse:
                if len(conditional.orelse) != 1 or not isinstance(conditional.orelse[0], ast.Return):
                    raise FrontendError(f"router {function.name!r} does not support elif or nested branches")
                false_label = self._return_label(conditional.orelse[0], "false route")
                if len(body) != 1:
                    raise FrontendError(f"router {function.name!r} has extra statements")
            else:
                if len(body) != 2:
                    raise FrontendError(f"router {function.name!r} needs a fall-through route return")
                false_label = self._return_label(body[1], "false route")
            test = conditional.test
        else:
            raise FrontendError(f"router {function.name!r} must be one if/else or conditional return")
        if true_label == false_label:
            raise FrontendError(f"router {function.name!r} must return two distinct labels")
        guard = self._router_test(test)
        return guard, true_label, false_label

    def _return_label(self, node: ast.stmt, label: str) -> str:
        if not isinstance(node, ast.Return) or node.value is None:
            raise FrontendError(f"router arm must directly return a literal {label} label")
        return self._constant_text(node.value, label + " label")

    def _router_test(self, test: ast.AST) -> dict[str, Any]:
        if isinstance(test, ast.Subscript):
            field_name = self._state_subscript(test)
            type_name = self.state_fields.get(field_name)
            if type_name != "boolean":
                raise FrontendError("truth-value router tests require a Boolean state field")
            return {"source_field": field_name}
        if isinstance(test, ast.Compare):
            if len(test.ops) != 1 or len(test.comparators) != 1:
                raise FrontendError("router comparisons must have one operator and one literal bound")
            field_node: ast.AST
            operator = test.ops[0]
            limit_node: ast.AST
            if isinstance(test.left, ast.Call) and self._is_tokens_call(test.left):
                field_node, limit_node = test.left.args[0], test.comparators[0]
            elif isinstance(test.comparators[0], ast.Call) and self._is_tokens_call(test.comparators[0]):
                field_node, limit_node = test.comparators[0].args[0], test.left
                operator = self._reverse_operator(operator)
            else:
                raise FrontendError("token routes must compare tokens(state['key']) with one integer literal")
            field_name = self._state_subscript(field_node)
            if self.state_fields.get(field_name) != "text":
                raise FrontendError("tokens() routes require a text state field")
            if not isinstance(limit_node, ast.Constant) or type(limit_node.value) is not int:
                raise FrontendError("token route limit must be an integer literal")
            limit = _natural(limit_node.value, "token route limit")
            op_names = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!="}
            op = next((symbol for kind, symbol in op_names.items() if isinstance(operator, kind)), None)
            if op is None:
                raise FrontendError("unsupported token route comparison")
            return {"source_field": field_name, "op": op, "limit": limit}
        raise FrontendError("router test must be state['bool'] or a tokens(state['text']) comparison")

    @staticmethod
    def _is_tokens_call(node: ast.AST) -> bool:
        return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id == "tokens" and len(node.args) == 1 and not node.keywords

    @staticmethod
    def _reverse_operator(operator: ast.cmpop) -> ast.cmpop:
        reverse: dict[type[ast.cmpop], type[ast.cmpop]] = {
            ast.Lt: ast.Gt, ast.LtE: ast.GtE, ast.Gt: ast.Lt,
            ast.GtE: ast.LtE, ast.Eq: ast.Eq, ast.NotEq: ast.NotEq,
        }
        kind = next((kind for kind in reverse if isinstance(operator, kind)), None)
        if kind is None:
            raise FrontendError("unsupported token route comparison")
        return reverse[kind]()

    def _derive_registers(self, nodes: dict[str, _Node]) -> None:
        writers: dict[str, list[str]] = {}
        for node in nodes.values():
            for field_name, local in node.returns.items():
                writer = node.calls[next(index for index, call in enumerate(node.calls) if call.local == local)]
                writers.setdefault(field_name, []).append(writer.model)
        state_slot_model: dict[str, str] = {}
        for field_name, aliases in writers.items():
            units = {(self.contracts["models"][alias]["provider"],
                      self.contracts["models"][alias]["model"]) for alias in aliases}
            if len(units) != 1:
                raise FrontendError(
                    f"result field {field_name!r} has writers with different provider/model token units"
                )
            state_slot_model[field_name] = sorted(
                set(aliases),
                key=lambda alias: (-self.contracts["models"][alias]["max_tokens"], alias),
            )[0]
        self.state_slot_model = state_slot_model

    def _lower(self, nodes: dict[str, _Node]) -> tuple[dict[str, Any], dict[str, Any]]:
        model_names = {alias: f"lg_model_{index:04d}"
                       for index, alias in enumerate(self.contracts["models"])}
        input_names = {field_name: f"lg_input_{index:04d}"
                       for index, field_name in enumerate(self.contracts["inputs"])}
        state_registers = {field_name: f"lg_slot_{index:04d}"
                           for index, field_name in enumerate(self.state_slot_model)}
        registers: dict[str, dict[str, str]] = {}
        inputs: dict[str, dict[str, Any]] = {}
        models = {model_names[alias]: dict(contract)
                  for alias, contract in self.contracts["models"].items()}
        for field_name, item in self.contracts["inputs"].items():
            inputs[input_names[field_name]] = dict(item)
        for field_name, alias in self.state_slot_model.items():
            registers[state_registers[field_name]] = {"model": model_names[alias]}

        per_function_result: dict[tuple[str, str], str] = {}
        temp_counter = 0
        all_calls_mapping: list[dict[str, Any]] = []
        for node in nodes.values():
            returned = {local: field_name for field_name, local in node.returns.items()}
            for call_index, call in enumerate(node.calls):
                maximum_request_bytes = len(call.template.encode("utf-8"))
                for atom in call.arguments:
                    if atom.kind == "literal":
                        maximum_request_bytes += len(atom.value.encode("utf-8"))
                    elif atom.kind == "state":
                        if atom.value in self.contracts["inputs"]:
                            item = self.contracts["inputs"][atom.value]
                            bound = item.get("max_tokens", 1)
                        else:
                            slot_alias = self.state_slot_model.get(atom.value)
                            if slot_alias is None:
                                raise FrontendError(f"request reads text state field {atom.value!r} with no result writer")
                            bound = self.contracts["models"][slot_alias]["max_tokens"]
                        maximum_request_bytes += bound * self.contracts["chars_per_token"]
                    else:
                        prior = next((item for item in node.calls if item.local == atom.value), None)
                        if prior is None:
                            raise FrontendError(f"request reads unknown local result {atom.value!r}")
                        bound = self.contracts["models"][prior.model]["max_tokens"]
                        maximum_request_bytes += bound * self.contracts["chars_per_token"]
                if maximum_request_bytes > MAX_VALUE_BYTES:
                    raise FrontendError(
                        f"worst-case complete request at {call.location} exceeds the offline value-byte limit"
                    )
                if call.local in returned:
                    result_name = state_registers[returned[call.local]]
                else:
                    result_name = f"lg_temp_{temp_counter:04d}"
                    temp_counter += 1
                    registers[result_name] = {"model": model_names[call.model]}
                call.graph_result = result_name
                per_function_result[(node.function_name, call.local)] = result_name

        # A stable slot may have writers with aliases of different caps. Its
        # declared model alias was selected at the maximum cap above, so the
        # graph schema's result-bound check covers every writer.
        graph_states: dict[str, Any] = {}
        route_mapping: list[dict[str, Any]] = []
        stop_states: dict[str, Any] = {}
        next_stop = 0
        source_to_graph = {node.source_name: node.graph_name for node in nodes.values()}

        def target_name(source_target: str) -> str:
            nonlocal next_stop
            if source_target == "END":
                stop = f"lg_stop_{next_stop:04d}"
                next_stop += 1
                stop_states[stop] = {"calls": [], "next": {"kind": "stop"}}
                return stop
            return source_to_graph[source_target]

        for source_name, node in nodes.items():
            lowered_calls: list[dict[str, Any]] = []
            for call in node.calls:
                args: list[dict[str, str]] = []
                for atom in call.arguments:
                    if atom.kind == "literal":
                        args.append({"literal": atom.value})
                    elif atom.kind == "local":
                        # Local results always name an earlier call in this
                        # same function; lexical bindings are unique.
                        prior = next((item for item in node.calls if item.local == atom.value), None)
                        if prior is None or prior is call:
                            raise FrontendError(f"invalid local request result {atom.value!r}")
                        args.append({"value": prior.graph_result})
                    else:
                        field_name = atom.value
                        if field_name in input_names:
                            graph_value = input_names[field_name]
                        elif field_name in state_registers:
                            graph_value = state_registers[field_name]
                        else:
                            raise FrontendError(f"request reads text state field {field_name!r} with no declared input or result writer")
                        args.append({"value": graph_value})
                lowered_calls.append({"model": model_names[call.model],
                                      "template": call.template,
                                      "arguments": args,
                                      "result": call.graph_result})
                all_calls_mapping.append({
                    "source_node": source_name,
                    "source_function": node.function_name,
                    "local_result": call.local,
                    "graph_result": call.graph_result,
                    "source_model_alias": call.model,
                    "graph_model_alias": model_names[call.model],
                    "template": call.template,
                    "arguments": [{"kind": atom.kind, "value": atom.value,
                                   "location": atom.location} for atom in call.arguments],
                    "location": call.location,
                })
            if node.edge is not None:
                target, kind = node.edge
                if kind == "end":
                    decision = {"kind": "stop"}
                else:
                    decision = {"kind": "goto", "target": target_name(target)}
            else:
                assert node.conditional is not None
                guard, true_label, path_map, router = node.conditional
                true_target = target_name(path_map[true_label])
                false_label = next(label for label in path_map if label != true_label)
                false_target = target_name(path_map[false_label])
                field_name = guard["source_field"]
                guard_value = input_names.get(field_name, state_registers.get(field_name))
                if guard_value is None:
                    raise FrontendError(f"router reads state field {field_name!r} without an input or result writer")
                guard_doc: dict[str, Any] = {"value": guard_value}
                if "op" in guard:
                    guard_doc.update(op=guard["op"], limit=guard["limit"])
                label = (self.contracts["inputs"].get(field_name, {}).get("label")
                         if field_name in self.contracts["inputs"] else "public")
                decision = {"kind": "secret" if label == "secret" else "public",
                            "guard": guard_doc, "then": true_target, "else": false_target}
                route_mapping.append({"source_node": source_name,
                                      "source_function": router.name,
                                      "guard_source_field": field_name,
                                      "guard": guard_doc,
                                      "true_label": true_label,
                                      "false_label": false_label,
                                      "path_map": path_map,
                                      "location": _location(router)})
            graph_states[node.graph_name] = {"calls": lowered_calls, "next": decision}
        graph_states.update(stop_states)
        graph = {
            "format": GRAPH_FORMAT,
            "version": 1,
            "name": self.contracts["name"],
            "chars_per_token": self.contracts["chars_per_token"],
            "inputs": inputs,
            "registers": registers,
            "models": models,
            "states": graph_states,
            "entry": source_to_graph[self.entry_source],
        }

        # A finite must-definition pass rejects reads of result slots that can
        # be absent on a path. The graph interpreter also checks initialization
        # dynamically, but this static gate covers every reachable path.
        self._check_definite_initialization(graph, input_names, state_registers, nodes, source_to_graph)
        mapping = {
            "state_type": self.state_name,
            "builder_variable": self.builder_name,
            "compiled_variable": self.compiled_name,
            "inputs": [{"source_key": key, "graph_name": input_names[key],
                        "type": item["type"], "label": item["label"],
                        **({"max_tokens": item["max_tokens"]} if "max_tokens" in item else {})}
                       for key, item in self.contracts["inputs"].items()],
            "models": [{"source_alias": alias, "graph_alias": model_names[alias],
                        "contract": contract}
                       for alias, contract in self.contracts["models"].items()],
            "result_slots": [{"source_key": field_name,
                              "graph_register": state_registers[field_name],
                              "token_unit": {"provider": self.contracts["models"][alias]["provider"],
                                             "model": self.contracts["models"][alias]["model"]},
                              "max_writer_cap": self.contracts["models"][alias]["max_tokens"],
                              "writer_model_alias": alias}
                             for field_name, alias in self.state_slot_model.items()],
            "nodes": [{"source_node": node.source_name,
                       "source_function": node.function_name,
                       "graph_state": node.graph_name,
                       "location": node.source_location,
                       "calls": [call.local for call in node.calls],
                       "returns": dict(node.returns)} for node in nodes.values()],
            "calls": all_calls_mapping,
            "routers": route_mapping,
            "entry_source_node": self.entry_source,
            "limitations": [
                "source extraction is Python AST only and does not execute source",
                "returned StateGraph updates are atomic; destination reads after a producing request are rejected",
                "external input fields are immutable and result registers require definite initialization",
                "only straight-line request nodes, two-way static conditional routing, and one active graph path are supported",
            ],
        }
        return graph, mapping

    def _check_definite_initialization(self, graph: dict[str, Any],
                                       input_names: dict[str, str],
                                       state_registers: dict[str, str],
                                       nodes: dict[str, _Node],
                                       source_to_graph: dict[str, str]) -> None:
        reachable: set[str] = set()
        todo = [graph["entry"]]
        while todo:
            state = todo.pop()
            if state in reachable:
                continue
            reachable.add(state)
            decision = graph["states"][state]["next"]
            if decision["kind"] == "goto":
                todo.append(decision["target"])
            elif decision["kind"] in ("public", "secret"):
                todo.extend((decision["then"], decision["else"]))
        registers = set(graph["registers"])
        initial = set(input_names.values())
        preds: dict[str, set[str]] = {state: set() for state in reachable}
        for state in reachable:
            decision = graph["states"][state]["next"]
            targets = ([decision["target"]] if decision["kind"] == "goto" else
                       [decision["then"], decision["else"]] if decision["kind"] in ("public", "secret") else [])
            for target in targets:
                if target in reachable:
                    preds[target].add(state)
        writes: dict[str, set[str]] = {}
        uses: dict[str, set[str]] = {}
        for state in reachable:
            body = graph["states"][state]
            written: set[str] = set()
            used: set[str] = set()
            for call in body["calls"]:
                for atom in call["arguments"]:
                    if "value" in atom and atom["value"] in registers and atom["value"] not in written:
                        used.add(atom["value"])
                written.add(call["result"])
            decision = body["next"]
            if decision["kind"] in ("public", "secret"):
                value = decision["guard"]["value"]
                if value in registers and value not in written:
                    used.add(value)
            writes[state] = written
            uses[state] = used

        # Greatest fixed point for must-defined values. START contributes the
        # external inputs to the entry state even if the graph cycles back.
        universe = initial | registers
        incoming = {state: set(universe) for state in reachable}
        outgoing = {state: set(universe) for state in reachable}
        changed = True
        while changed:
            changed = False
            for state in sorted(reachable):
                predecessor_out = [outgoing[pred] for pred in preds[state]]
                if state == graph["entry"]:
                    predecessor_out.append(initial)
                if not predecessor_out:
                    new_in = set(initial)
                else:
                    new_in = set.intersection(*(set(item) for item in predecessor_out))
                new_out = new_in | writes[state]
                if new_in != incoming[state] or new_out != outgoing[state]:
                    incoming[state], outgoing[state] = new_in, new_out
                    changed = True
        for state in sorted(reachable):
            missing = uses[state] - incoming[state]
            if missing:
                raise FrontendError(
                    f"graph state {state!r} may read result register(s) before a writer on every path: {sorted(missing)}"
                )

    def _validate_reachability(self, nodes: dict[str, _Node]) -> None:
        adjacency: dict[str, set[str]] = {name: set() for name in nodes}
        for name, node in nodes.items():
            if node.edge is not None:
                target, kind = node.edge
                if kind == "node":
                    adjacency[name].add(target)
            elif node.conditional is not None:
                _, _, path_map, _ = node.conditional
                adjacency[name].update(target for target in path_map.values() if target != "END")
        reachable: set[str] = set()
        todo = [self.entry_source]
        while todo:
            current = todo.pop()
            if current in reachable:
                continue
            reachable.add(current)
            todo.extend(adjacency[current] - reachable)
        dead = set(nodes) - reachable
        if dead:
            raise FrontendError(f"unreachable StateGraph nodes are outside the subset: {sorted(dead)}")


def extract_source(source_raw: bytes, contracts_raw: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a version-1 request graph and an auditable source mapping."""
    contracts = parse_contracts(contracts_raw)
    return _Extractor(source_raw, contracts_raw, contracts).extract()


def source_hash(source_raw: bytes) -> str:
    return _sha(source_raw)
