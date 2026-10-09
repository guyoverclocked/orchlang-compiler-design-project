#!/usr/bin/env python3
"""Fail-closed bridge from a small OrchLang source subset to request graphs.

This bridge is an experimental billing-projection adapter. It requires the
OrchLang compiler's full ``check`` gate, then validates the emitted graph with
the graph producer and independent certificate replayer before writing files.
It is not a verified source translation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Union

try:  # works both as ``python audit/source_to_graph.py`` and ``import audit...``
    from certificate_audit import SourceCost, TOKEN
except ImportError:  # pragma: no cover - package import path
    from .certificate_audit import SourceCost, TOKEN


ROOT = Path(__file__).resolve().parents[1]
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_SOURCE_TOKENS = 250_000
MAX_NESTING = 128
MAX_GRAPH_ITEMS = 100_000
MAX_UTF8_BYTES = 1 * 1024 * 1024
MAX_PROBE_TRACE_BYTES = 16 * 1024 * 1024
MAX_PROBE_CONTROL_STEPS = 1_000_000
MAX_UINT = 2**64 - 2
MAX_SEED = 2**64 - 1
MAX_PROBE_CALLS = 10_000
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")
NUMBER = re.compile(r"^(?:[0-9]+(?:\.[0-9]+)?)$")
COMPARISONS = {"<", "<=", ">", ">=", "==", "!="}
KEYWORDS = {
    "workflow", "budget", "input", "secret", "model", "mock", "max_tokens",
    "cost_per_token", "prompt", "tool", "let", "call", "using", "require",
    "tokens", "output", "untrusted", "emit", "if", "else", "retry",
    "declassify", "endorse", "as", "because", "text", "integer", "decimal",
    "boolean", "json", "true", "false",
}


class BridgeError(ValueError):
    """The source is malformed, outside the supported subset, or fails a gate."""


@dataclass(frozen=True)
class Token:
    text: str
    line: int
    column: int

    def location(self) -> dict[str, int]:
        return {"line": self.line, "column": self.column}


@dataclass(frozen=True)
class Expr:
    kind: str  # literal | identifier
    value: str
    type_name: str
    token: Token


@dataclass(frozen=True)
class InputDecl:
    name: str
    type_name: str
    confidential: str
    max_tokens: int | None
    token: Token


@dataclass(frozen=True)
class ModelDecl:
    name: str
    model_id: str
    max_tokens: int
    unit_price: float | None
    token: Token


@dataclass(frozen=True)
class PromptDecl:
    name: str
    parameters: tuple[tuple[str, str], ...]
    return_type: str
    template: str
    token: Token


@dataclass(frozen=True)
class LetStmt:
    name: str
    type_name: str
    prompt_name: str
    arguments: tuple[Expr, ...]
    model_name: str
    token: Token
    call_token: Token


@dataclass(frozen=True)
class Condition:
    subject: str
    operator: str | None
    limit: int | None
    token: Token


@dataclass
class IfStmt:
    condition: Condition
    then_body: list[Statement]
    else_body: list[Statement]
    has_else: bool
    token: Token


@dataclass(frozen=True)
class OutputStmt:
    expression: Expr
    token: Token


Statement = Union[InputDecl, ModelDecl, PromptDecl, LetStmt, IfStmt, OutputStmt]


@dataclass(frozen=True)
class Workflow:
    name: str
    budget: int
    body: tuple[Statement, ...]
    token: Token


@dataclass
class Binding:
    source_name: str
    type_name: str
    graph_name: str
    kind: str  # input | secret | result
    confidential: str
    source_token: Token
    binding_id: int
    max_tokens: int | None = None


@dataclass
class ResolvedCall:
    prompt: PromptDecl
    model_alias: str
    arguments: list[dict[str, str]]
    register: str
    contract: dict[str, Any]


@dataclass
class ResolvedIf:
    kind: str
    guard: dict[str, Any]


@dataclass
class Scope:
    symbols: dict[str, tuple[str, Any]] = field(default_factory=dict)


@dataclass
class Translation:
    graph: dict[str, Any]
    mapping: dict[str, Any]
    workflow: Workflow
    output: dict[str, Any]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _scalar_utf8(value: str, what: str) -> int:
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise BridgeError(f"{what} contains a non-scalar Unicode code point") from error
    if size > MAX_UTF8_BYTES:
        raise BridgeError(f"{what} exceeds {MAX_UTF8_BYTES} UTF-8 bytes")
    return size


def _decode_string(token: Token) -> str:
    try:
        value = SourceCost.string(token.text)
    except (ValueError, json.JSONDecodeError) as error:
        raise BridgeError(f"invalid string at {token.line}:{token.column}: {error}") from error
    _scalar_utf8(value, f"string at {token.line}:{token.column}")
    return value


class SourceParser:
    """Small strict parser over the independent cost auditor's lexical token rule."""

    def __init__(self, text: str):
        self.items: list[Token] = []
        position = 0
        while position < len(text):
            match = TOKEN.match(text, position)
            if not match:
                raise BridgeError(f"unsupported or invalid source token near character {position}")
            word = match.group()
            if not word.isspace() and not word.startswith("//"):
                line = text.count("\n", 0, position) + 1
                line_start = text.rfind("\n", 0, position) + 1
                column = len(text[line_start:position].encode("utf-8")) + 1
                self.items.append(Token(word, line, column))
                if len(self.items) > MAX_SOURCE_TOKENS:
                    raise BridgeError("source token limit exceeded")
            position = match.end()
        self.cursor = 0
        self.depth = 0

    def peek(self) -> str:
        return self.items[self.cursor].text if self.cursor < len(self.items) else "<EOF>"

    def take(self, expected: str | None = None) -> Token:
        if self.cursor >= len(self.items):
            raise BridgeError("unexpected end of source")
        token = self.items[self.cursor]
        if expected is not None and token.text != expected:
            raise BridgeError(f"expected {expected!r}, found {token.text!r} at {token.line}:{token.column}")
        self.cursor += 1
        return token

    def identifier(self) -> Token:
        token = self.take()
        if not IDENTIFIER.fullmatch(token.text) or token.text in KEYWORDS:
            raise BridgeError(f"expected identifier at {token.line}:{token.column}, found {token.text!r}")
        return token

    def natural(self, what: str, minimum: int = 0) -> int:
        token = self.take()
        if not token.text.isdecimal():
            raise BridgeError(f"expected {what} integer at {token.line}:{token.column}")
        value = int(token.text)
        if not minimum <= value <= MAX_UINT:
            raise BridgeError(f"{what} is outside [{minimum}, {MAX_UINT}] at {token.line}:{token.column}")
        return value

    def parse(self) -> Workflow:
        if self.peek() != "workflow":
            raise BridgeError("exactly one workflow declaration is required")
        token = self.take("workflow")
        name = self.identifier().text
        self.take("budget")
        budget = self.natural("workflow budget")
        body = self.block()
        if self.peek() != "<EOF>":
            extra = self.take()
            raise BridgeError(f"multiple workflows or trailing tokens are unsupported at {extra.line}:{extra.column}")
        return Workflow(name, budget, tuple(body), token)

    def block(self) -> list[Statement]:
        self.take("{")
        self.depth += 1
        if self.depth > MAX_NESTING:
            raise BridgeError(f"source nesting exceeds {MAX_NESTING} blocks")
        result: list[Statement] = []
        while self.peek() != "}":
            if self.peek() == "<EOF>":
                raise BridgeError("unterminated workflow/block")
            result.append(self.statement())
            if len(result) > MAX_GRAPH_ITEMS:
                raise BridgeError("source statement limit exceeded")
        self.take("}")
        self.depth -= 1
        return result

    def statement(self) -> Statement:
        start = self.take()
        if start.text in ("input", "secret"):
            name = self.identifier().text
            if start.text == "input":
                self.take(":")
                type_name = self.take().text
                if type_name not in ("text", "boolean"):
                    raise BridgeError(f"only text/boolean external inputs are supported at {start.line}:{start.column}")
                confidential = "public"
                if self.peek() == "untrusted":
                    self.take("untrusted")
                max_tokens = self.natural("input max_tokens") if self.peek() == "max_tokens" and self.take("max_tokens") else None
            else:
                type_name = "text"
                if self.peek() == ":":
                    self.take(":")
                    type_name = self.take().text
                if type_name not in ("text", "boolean"):
                    raise BridgeError(f"only text/boolean secrets are supported at {start.line}:{start.column}")
                confidential = "secret"
                max_tokens = self.natural("secret max_tokens") if self.peek() == "max_tokens" and self.take("max_tokens") else None
            self.take(";")
            if type_name == "text" and max_tokens is None:
                raise BridgeError(f"unbounded text input {name!r} cannot be represented by the graph schema")
            return InputDecl(name, type_name, confidential, max_tokens, start)
        if start.text == "model":
            name = self.identifier().text
            self.take("=")
            self.take("mock")
            self.take("(")
            model_token = self.take()
            if not model_token.text.startswith('"'):
                raise BridgeError("mock model ID must be a quoted string")
            model_id = _decode_string(model_token)
            self.take(")")
            self.take("max_tokens")
            max_tokens = self.natural("model max_tokens", minimum=1)
            unit_price: float | None = None
            if self.peek() == "cost_per_token":
                self.take("cost_per_token")
                raw_price = self.take().text
                if not NUMBER.fullmatch(raw_price):
                    raise BridgeError(f"invalid model price at {start.line}:{start.column}")
                unit_price = float(raw_price)
                if not math.isfinite(unit_price) or unit_price < 0:
                    raise BridgeError(f"model price must be finite and nonnegative at {start.line}:{start.column}")
            self.take(";")
            return ModelDecl(name, model_id, max_tokens, unit_price, start)
        if start.text == "prompt":
            name = self.identifier().text
            self.take("(")
            parameters: list[tuple[str, str]] = []
            if self.peek() != ")":
                while True:
                    parameter = self.identifier().text
                    self.take(":")
                    parameter_type = self.take().text
                    if parameter_type != "text":
                        raise BridgeError(f"only text prompt parameters are supported at {start.line}:{start.column}")
                    parameters.append((parameter, parameter_type))
                    if self.peek() != ",":
                        break
                    self.take(",")
            self.take(")")
            self.take("->")
            return_type = self.take().text
            if return_type != "text":
                raise BridgeError(f"only text-returning prompts are supported at {start.line}:{start.column}")
            self.take("=")
            template_token = self.take()
            if not template_token.text.startswith('"'):
                raise BridgeError("prompt template must be a quoted string")
            template = _decode_string(template_token)
            self.take(";")
            return PromptDecl(name, tuple(parameters), return_type, template, start)
        if start.text == "let":
            name = self.identifier().text
            self.take(":")
            type_name = self.take().text
            if type_name != "text":
                raise BridgeError(f"only text call results are supported at {start.line}:{start.column}")
            self.take("=")
            call_token = self.take("call")
            prompt_name = self.identifier().text
            arguments = self.arguments()
            self.take("using")
            model_name = self.identifier().text
            self.take(";")
            return LetStmt(name, type_name, prompt_name, tuple(arguments), model_name, start, call_token)
        if start.text == "if":
            condition = self.condition(start)
            then_body = self.block()
            has_else = self.peek() == "else"
            else_body: list[Statement] = []
            if has_else:
                self.take("else")
                else_body = self.block()
            return IfStmt(condition, then_body, else_body, has_else, start)
        if start.text == "output":
            expression = self.expression()
            self.take(";")
            return OutputStmt(expression, start)
        raise BridgeError(
            f"unsupported statement {start.text!r} at {start.line}:{start.column}; "
            "supported statements are input, secret, model, prompt, let, if/else, and final text output"
        )

    def arguments(self) -> list[Expr]:
        self.take("(")
        result: list[Expr] = []
        if self.peek() != ")":
            while True:
                result.append(self.expression())
                if self.peek() != ",":
                    break
                self.take(",")
        self.take(")")
        return result

    def expression(self) -> Expr:
        token = self.take()
        if token.text.startswith('"'):
            return Expr("literal", _decode_string(token), "text", token)
        if token.text in ("true", "false"):
            return Expr("literal", token.text, "boolean", token)
        if NUMBER.fullmatch(token.text):
            return Expr("literal", token.text, "decimal" if "." in token.text else "integer", token)
        if IDENTIFIER.fullmatch(token.text) and token.text not in KEYWORDS:
            return Expr("identifier", token.text, "unknown", token)
        raise BridgeError(f"unsupported expression at {token.line}:{token.column}: {token.text!r}")

    def condition(self, start: Token) -> Condition:
        if self.peek() == "tokens":
            self.take("tokens")
            self.take("(")
            subject = self.identifier().text
            self.take(")")
            operator = self.take().text
            if operator not in COMPARISONS:
                raise BridgeError(f"unsupported token comparison at {start.line}:{start.column}")
            limit = self.natural("token comparison limit")
            return Condition(subject, operator, limit, start)
        subject = self.identifier().text
        return Condition(subject, None, None, start)


def parse_source(raw: bytes) -> Workflow:
    if len(raw) > MAX_SOURCE_BYTES:
        raise BridgeError(f"source exceeds {MAX_SOURCE_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BridgeError(f"source is not valid UTF-8: {error}") from error
    return SourceParser(text).parse()


def _location(token: Token) -> dict[str, int]:
    return token.location()


class Resolver:
    def __init__(self, workflow: Workflow, divisor: int):
        if type(divisor) is not int or not 1 <= divisor <= 2**32 - 1:
            raise BridgeError("chars_per_token must be an integer in [1, 2^32-1]")
        self.workflow = workflow
        self.divisor = divisor
        self.scopes: list[Scope] = [Scope()]
        self.models: dict[str, dict[str, Any]] = {}
        self.registers: dict[str, dict[str, str]] = {}
        self.inputs: dict[str, dict[str, Any]] = {}
        self.mapping: dict[str, list[dict[str, Any]]] = {
            "inputs": [], "models": [], "prompts": [], "values": [], "states": []
        }
        self.next_binding = 1
        self.next_model = 0
        self.next_register = 0
        self.next_state = 0
        self.resolved: dict[int, Any] = {}
        self.final_output: dict[str, Any] | None = None
        self.model_declarations = 0
        self.prompt_declarations = 0
        self.call_count = 0

    def _lookup(self, name: str) -> tuple[str, Any] | None:
        for scope in reversed(self.scopes):
            if name in scope.symbols:
                return scope.symbols[name]
        return None

    def _define(self, name: str, kind: str, value: Any, token: Token) -> None:
        frame = self.scopes[-1]
        if name in frame.symbols:
            raise BridgeError(f"duplicate declaration {name!r} at {token.line}:{token.column}")
        frame.symbols[name] = (kind, value)

    def _text_bound(self, input_decl: InputDecl) -> None:
        if input_decl.type_name == "text" and input_decl.max_tokens is None:
            raise BridgeError(f"text input {input_decl.name!r} requires max_tokens")

    def resolve(self) -> Translation:
        self._walk_block(list(self.workflow.body), top=True)
        if self.final_output is None:
            raise BridgeError("the supported source projection requires one final public text output")
        graph = self._lower()
        self.mapping["models"].sort(key=lambda item: item["declaration_id"])
        self.mapping["prompts"].sort(key=lambda item: item["declaration_id"])
        self.mapping["inputs"].sort(key=lambda item: item["binding_id"])
        self.mapping["values"].sort(key=lambda item: item["binding_id"])
        return Translation(graph, self.mapping, self.workflow, self.final_output)

    def _walk_block(self, statements: list[Statement], *, top: bool = False) -> None:
        if not top:
            self.scopes.append(Scope())
        try:
            for index, statement in enumerate(statements):
                key = id(statement)
                if isinstance(statement, InputDecl):
                    if not top:
                        raise BridgeError(f"external input declarations must be in the workflow body at {statement.token.line}:{statement.token.column}")
                    self._text_bound(statement)
                    graph_name = f"in_{len(self.inputs)}"
                    binding = Binding(statement.name, statement.type_name, graph_name,
                                      "secret" if statement.confidential == "secret" else "input",
                                      statement.confidential, statement.token,
                                      self.next_binding, statement.max_tokens)
                    self.next_binding += 1
                    label = statement.confidential
                    declaration: dict[str, Any] = {"type": statement.type_name, "label": label}
                    if statement.type_name == "text":
                        declaration["max_tokens"] = statement.max_tokens
                    self.inputs[graph_name] = declaration
                    self.mapping["inputs"].append({"source_name": statement.name,
                        "location": _location(statement.token), "binding_id": binding.binding_id,
                        "graph_name": graph_name, "type": statement.type_name,
                        "label": label, "max_tokens": statement.max_tokens})
                    self._define(statement.name, "value", binding, statement.token)
                elif isinstance(statement, ModelDecl):
                    self.model_declarations += 1
                    if self.model_declarations > MAX_GRAPH_ITEMS:
                        raise BridgeError("model declaration limit exceeded")
                    alias = f"model_{self.next_model}"
                    declaration_id = self.next_model
                    self.next_model += 1
                    contract: dict[str, Any] = {"provider": "mock", "model": statement.model_id,
                                                "max_tokens": statement.max_tokens}
                    if statement.unit_price is not None:
                        contract["unit_price"] = statement.unit_price
                    _scalar_utf8(statement.model_id, "model identifier")
                    self.models[alias] = contract
                    value = {"alias": alias, "contract": contract,
                             "declaration_id": declaration_id, "token": statement.token}
                    self.mapping["models"].append({"source_name": statement.name,
                        "location": _location(statement.token), "declaration_id": declaration_id,
                        "graph_alias": alias, "contract": contract})
                    self._define(statement.name, "model", value, statement.token)
                elif isinstance(statement, PromptDecl):
                    self.prompt_declarations += 1
                    if self.prompt_declarations > MAX_GRAPH_ITEMS:
                        raise BridgeError("prompt declaration limit exceeded")
                    _scalar_utf8(statement.template, "prompt template")
                    value = {"prompt": statement, "declaration_id": self.prompt_declarations - 1}
                    self.mapping["prompts"].append({"source_name": statement.name,
                        "location": _location(statement.token),
                        "declaration_id": self.prompt_declarations - 1,
                        "template": statement.template,
                        "parameters": [{"name": n, "type": t} for n, t in statement.parameters]})
                    self._define(statement.name, "prompt", value, statement.token)
                elif isinstance(statement, LetStmt):
                    self.call_count += 1
                    if self.call_count > MAX_GRAPH_ITEMS:
                        raise BridgeError("call declaration limit exceeded")
                    prompt_symbol = self._lookup(statement.prompt_name)
                    model_symbol = self._lookup(statement.model_name)
                    if not prompt_symbol or prompt_symbol[0] != "prompt":
                        raise BridgeError(f"unknown prompt {statement.prompt_name!r} at {statement.call_token.line}:{statement.call_token.column}")
                    if not model_symbol or model_symbol[0] != "model":
                        raise BridgeError(f"unknown model {statement.model_name!r} at {statement.call_token.line}:{statement.call_token.column}")
                    prompt: PromptDecl = prompt_symbol[1]["prompt"]
                    if len(statement.arguments) != len(prompt.parameters):
                        raise BridgeError(f"prompt {statement.prompt_name!r} argument count differs at {statement.call_token.line}:{statement.call_token.column}")
                    atoms: list[dict[str, str]] = []
                    for index, (argument, parameter) in enumerate(zip(statement.arguments, prompt.parameters)):
                        parameter_type = parameter[1]
                        if argument.kind == "literal":
                            if argument.type_name != "text":
                                raise BridgeError(f"only quoted text literals are supported as request arguments at {argument.token.line}:{argument.token.column}")
                            actual_type = argument.type_name
                            atom = {"literal": argument.value}
                            _scalar_utf8(argument.value, "literal argument")
                        else:
                            value_symbol = self._lookup(argument.value)
                            if not value_symbol or value_symbol[0] != "value":
                                raise BridgeError(f"unknown text value {argument.value!r} at {argument.token.line}:{argument.token.column}")
                            binding: Binding = value_symbol[1]
                            actual_type = binding.type_name
                            if binding.type_name != "text":
                                raise BridgeError(f"only text identifiers are request values at {argument.token.line}:{argument.token.column}")
                            if binding.confidential == "secret" and binding.kind != "result":
                                raise BridgeError(f"secret inputs cannot be passed to calls at {argument.token.line}:{argument.token.column}")
                            atom = {"value": binding.graph_name}
                        if actual_type != parameter_type:
                            raise BridgeError(f"argument {index + 1} type differs from prompt parameter at {argument.token.line}:{argument.token.column}")
                        atoms.append(atom)
                    register = f"r_{self.next_register}"
                    binding = Binding(statement.name, "text", register, "result", "public",
                                      statement.token, self.next_binding,
                                      model_symbol[1]["contract"]["max_tokens"])
                    self.next_binding += 1
                    self.next_register += 1
                    self.registers[register] = {"model": model_symbol[1]["alias"]}
                    call = ResolvedCall(prompt, model_symbol[1]["alias"], atoms, register,
                                        model_symbol[1]["contract"])
                    self.resolved[key] = call
                    self.mapping["values"].append({"source_name": statement.name,
                        "location": _location(statement.token), "binding_id": binding.binding_id,
                        "graph_register": register, "type": "text",
                        "producer_contract": model_symbol[1]["contract"]})
                    self._define(statement.name, "value", binding, statement.token)
                elif isinstance(statement, IfStmt):
                    guard_symbol = self._lookup(statement.condition.subject)
                    if not guard_symbol or guard_symbol[0] != "value":
                        raise BridgeError(f"unknown branch value {statement.condition.subject!r} at {statement.condition.token.line}:{statement.condition.token.column}")
                    binding: Binding = guard_symbol[1]
                    if statement.condition.operator is None:
                        if binding.type_name != "boolean" or binding.kind == "result":
                            raise BridgeError(f"flag guard must name an external Boolean at {statement.condition.token.line}:{statement.condition.token.column}")
                    elif binding.type_name != "text":
                        raise BridgeError(f"tokens guard must name text at {statement.condition.token.line}:{statement.condition.token.column}")
                    if binding.kind == "result":
                        kind = "public"
                    else:
                        kind = "secret" if binding.confidential == "secret" else "public"
                    guard: dict[str, Any] = {"value": binding.graph_name}
                    if statement.condition.operator is not None:
                        guard.update(op=statement.condition.operator, limit=statement.condition.limit)
                    self.resolved[key] = ResolvedIf(kind, guard)
                    self.mapping["states"].append({"source_location": _location(statement.token),
                        "kind": kind, "source_guard": statement.condition.subject,
                        "graph_guard": guard})
                    self._walk_block(statement.then_body)
                    self._walk_block(statement.else_body)
                elif isinstance(statement, OutputStmt):
                    if not top or index != len(statements) - 1:
                        raise BridgeError(f"output is supported only as the final workflow statement at {statement.token.line}:{statement.token.column}")
                    if self.final_output is not None:
                        raise BridgeError("exactly one final output is supported")
                    expression = statement.expression
                    if expression.kind == "literal":
                        if expression.type_name != "text":
                            raise BridgeError("the final output must be text")
                        _scalar_utf8(expression.value, "final output")
                        self.final_output = {
                            "kind": "literal",
                            "text": expression.value,
                            "source_location": _location(expression.token),
                        }
                    elif expression.kind == "identifier":
                        symbol = self._lookup(expression.value)
                        if not symbol or symbol[0] != "value":
                            raise BridgeError(f"output identifier {expression.value!r} is unbound or not a value at {expression.token.line}:{expression.token.column}")
                        binding: Binding = symbol[1]
                        if binding.type_name != "text":
                            raise BridgeError(f"output identifier {expression.value!r} must have text type at {expression.token.line}:{expression.token.column}")
                        if binding.confidential != "public":
                            raise BridgeError(f"output identifier {expression.value!r} is private at {expression.token.line}:{expression.token.column}")
                        self.final_output = {
                            "kind": "identifier",
                            "source_name": expression.value,
                            "binding_id": binding.binding_id,
                            "graph_value_name": binding.graph_name,
                            "value_kind": binding.kind,
                            "type": binding.type_name,
                            "confidentiality": binding.confidential,
                            "source_location": _location(expression.token),
                        }
                    else:  # pragma: no cover - Expr parser currently fixes the union
                        raise BridgeError("the final output expression kind is unsupported")
                else:  # pragma: no cover - parser currently fixes this union
                    raise BridgeError(f"unsupported statement object {type(statement).__name__}")
        finally:
            if not top:
                self.scopes.pop()

    def _new_state(self, states: dict[str, Any], body: dict[str, Any], source: Token | None = None) -> str:
        if self.next_state >= MAX_GRAPH_ITEMS:
            raise BridgeError("lowered state limit exceeded")
        name = f"state_{self.next_state}"
        self.next_state += 1
        states[name] = body
        if source is not None:
            self.mapping["states"].append({"source_location": _location(source), "graph_state": name})
        return name

    def _lower_sequence(self, statements: list[Statement], continuation: str,
                        states: dict[str, Any]) -> str:
        current = continuation
        for statement in reversed(statements):
            if isinstance(statement, (InputDecl, ModelDecl, PromptDecl, OutputStmt)):
                continue
            if isinstance(statement, LetStmt):
                resolved: ResolvedCall = self.resolved[id(statement)]
                state = self._new_state(states, {
                    "calls": [{"model": resolved.model_alias,
                               "template": resolved.prompt.template,
                               "arguments": resolved.arguments,
                               "result": resolved.register}],
                    "next": {"kind": "goto", "target": current}}, statement.token)
                current = state
                continue
            if isinstance(statement, IfStmt):
                resolved_if: ResolvedIf = self.resolved[id(statement)]
                then_target = self._lower_sequence(statement.then_body, current, states)
                else_target = self._lower_sequence(statement.else_body, current, states)
                state = self._new_state(states, {"calls": [], "next": {
                    "kind": resolved_if.kind, "guard": resolved_if.guard,
                    "then": then_target, "else": else_target}}, statement.token)
                current = state
                continue
            raise BridgeError(f"unsupported source statement during lowering: {type(statement).__name__}")
        return current

    def _lower(self) -> dict[str, Any]:
        states: dict[str, Any] = {}
        stop = self._new_state(states, {"calls": [], "next": {"kind": "stop"}})
        entry = self._lower_sequence(list(self.workflow.body), stop, states)
        return {"format": "orchlang-request-graph", "version": 1,
                "name": self.workflow.name, "chars_per_token": self.divisor,
                "inputs": self.inputs, "registers": self.registers,
                "models": self.models, "states": states, "entry": entry}


def translate_text(text: str, chars_per_token: int = 4) -> Translation:
    """Parse and lower without external gates; intended for inspection/tests only."""
    try:
        raw = text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise BridgeError("source contains a non-scalar Unicode code point") from error
    workflow = parse_source(raw)
    return Resolver(workflow, chars_per_token).resolve()


@dataclass
class RuntimeValue:
    text: str | None = None
    flag: bool | None = None
    type_name: str = "text"


class SourceReferenceInterpreter:
    """Independent source-AST evaluator over full text values and the graph Ω."""

    def __init__(self, workflow: Workflow, store: dict[str, Any], seed: int,
                 divisor: int = 4, max_calls: int = 10_000):
        if type(seed) is not int or not 0 <= seed <= MAX_SEED:
            raise BridgeError("seed must be an integer in [0, 2^64-1]")
        if type(divisor) is not int or not 1 <= divisor <= 2**32 - 1:
            raise BridgeError("chars_per_token must be an integer in [1, 2^32-1]")
        if type(max_calls) is not int or not 1 <= max_calls <= MAX_PROBE_CALLS:
            raise BridgeError(f"max_calls must be an integer in [1, {MAX_PROBE_CALLS}]")
        self.workflow, self.store, self.seed = workflow, store, seed
        self.divisor, self.max_calls = divisor, max_calls
        self.frames: list[dict[str, tuple[str, Any]]] = [{}]
        self.ordinals: dict[str, int] = {}
        self.trace: list[dict[str, Any]] = []
        self.trace_bytes = 0
        self.control_steps = 0
        self.output_value: str | None = None
        self.inputs: dict[str, InputDecl] = {}
        if not isinstance(store, dict) or not all(type(key) is str for key in store):
            raise BridgeError("reference store must be an object with string keys")
        for statement in workflow.body:
            if isinstance(statement, InputDecl):
                self.inputs[statement.name] = statement
        if set(store) != set(self.inputs):
            raise BridgeError("reference store must name every source input/secret exactly once")
        for name, declaration in self.inputs.items():
            value = store[name]
            if declaration.type_name == "boolean":
                if type(value) is not bool:
                    raise BridgeError(f"Boolean input {name!r} has wrong type")
            else:
                if not isinstance(value, str):
                    raise BridgeError(f"text input {name!r} has wrong type")
                size = _scalar_utf8(value, f"input {name}")
                estimate = (size + divisor - 1) // divisor
                if estimate > declaration.max_tokens:
                    raise BridgeError(f"text input {name!r} exceeds its declared token bound")
            self._define(name, "value", RuntimeValue(
                text=value if isinstance(value, str) else None,
                flag=value if type(value) is bool else None,
                type_name=declaration.type_name))

    def _define(self, name: str, kind: str, value: Any) -> None:
        if name in self.frames[-1]:
            raise BridgeError(f"duplicate runtime binding {name!r}")
        self.frames[-1][name] = (kind, value)

    def _lookup(self, name: str) -> tuple[str, Any]:
        for frame in reversed(self.frames):
            if name in frame:
                return frame[name]
        raise BridgeError(f"unbound source reference {name!r}")

    def _estimate(self, text: str) -> int:
        return (len(text.encode("utf-8")) + self.divisor - 1) // self.divisor

    def _expr(self, expression: Expr) -> str:
        if expression.kind == "literal":
            return expression.value
        kind, value = self._lookup(expression.value)
        if kind != "value" or value.text is None:
            raise BridgeError(f"source value {expression.value!r} is not text")
        return value.text

    @staticmethod
    def _contract(model: ModelDecl) -> dict[str, Any]:
        result: dict[str, Any] = {"provider": "mock", "model": model.model_id,
                                  "max_tokens": model.max_tokens,
                                  "has_unit_price": model.unit_price is not None,
                                  "unit_price": float(model.unit_price or 0.0)}
        return result

    def _model_response(self, contract: dict[str, Any], template: str,
                        arguments: list[str]) -> tuple[str, int, int, int]:
        request_bytes = _scalar_utf8(template, "request template")
        for argument in arguments:
            request_bytes += _scalar_utf8(argument, "request argument")
            if request_bytes > MAX_UTF8_BYTES:
                raise BridgeError(f"complete request exceeds {MAX_UTF8_BYTES} UTF-8 bytes")
        contract_key = json.dumps(contract, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"))
        ordinal = self.ordinals.get(contract_key, 0)
        self.ordinals[contract_key] = ordinal + 1
        key = json.dumps([self.workflow.name, self.seed, contract, ordinal,
                          template, arguments], ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        output_tokens = int.from_bytes(digest[:8], "big") % (min(contract["max_tokens"], 32) + 1)
        response_bytes = output_tokens * self.divisor
        if response_bytes > MAX_UTF8_BYTES:
            raise BridgeError(f"abstract response exceeds {MAX_UTF8_BYTES} UTF-8 bytes")
        if self.trace_bytes + request_bytes + response_bytes > MAX_PROBE_TRACE_BYTES:
            raise BridgeError(f"reference trace exceeds {MAX_PROBE_TRACE_BYTES} bytes")
        self.trace_bytes += request_bytes + response_bytes
        alphabet = "abcdefghijklmNOPQRSTUVWXYZ0123456789"
        response = "".join(alphabet[digest[i % 32] % len(alphabet)]
                           for i in range(response_bytes))
        input_tokens = self._estimate(template) + sum(self._estimate(arg) for arg in arguments)
        return response, ordinal, input_tokens, output_tokens

    def _condition(self, condition: Condition) -> bool:
        kind, value = self._lookup(condition.subject)
        if kind != "value":
            raise BridgeError(f"guard {condition.subject!r} is not a value")
        if condition.operator is None:
            if value.flag is None:
                raise BridgeError(f"guard {condition.subject!r} is not Boolean")
            return value.flag
        if value.text is None:
            raise BridgeError(f"guard {condition.subject!r} is not text")
        left, right = self._estimate(value.text), condition.limit
        return {"<": left < right, "<=": left <= right, ">": left > right,
                ">=": left >= right, "==": left == right, "!=": left != right}[condition.operator]

    def _block(self, statements: list[Statement], *, root: bool = False) -> None:
        if not root:
            self.frames.append({})
        try:
            for statement in statements:
                self.control_steps += 1
                if self.control_steps > MAX_PROBE_CONTROL_STEPS:
                    raise BridgeError(f"reference control-step limit {MAX_PROBE_CONTROL_STEPS} exceeded")
                if isinstance(statement, (InputDecl,)):
                    continue  # supplied as the initial store
                if isinstance(statement, ModelDecl):
                    self._define(statement.name, "model", statement)
                elif isinstance(statement, PromptDecl):
                    self._define(statement.name, "prompt", statement)
                elif isinstance(statement, LetStmt):
                    if len(self.trace) >= self.max_calls:
                        raise BridgeError(f"reference call limit {self.max_calls} reached")
                    prompt_kind, prompt = self._lookup(statement.prompt_name)
                    model_kind, model = self._lookup(statement.model_name)
                    if prompt_kind != "prompt" or model_kind != "model":
                        raise BridgeError("call target kind mismatch in reference interpreter")
                    arguments: list[str] = []
                    request_size = _scalar_utf8(prompt.template, "request template")
                    for expression in statement.arguments:
                        argument = self._expr(expression)
                        request_size += _scalar_utf8(argument, "request argument")
                        if request_size > MAX_UTF8_BYTES:
                            raise BridgeError(f"complete request exceeds {MAX_UTF8_BYTES} UTF-8 bytes")
                        arguments.append(argument)
                    response, ordinal, input_tokens, output_tokens = self._model_response(
                        self._contract(model), prompt.template, arguments)
                    self.trace.append({"contract": self._contract(model), "ordinal": ordinal,
                                       "template": prompt.template, "arguments": arguments,
                                       "response": response, "input_tokens": input_tokens,
                                       "output_tokens": output_tokens})
                    self._define(statement.name, "value", RuntimeValue(text=response,
                                                                       type_name="text"))
                elif isinstance(statement, IfStmt):
                    branch = statement.then_body if self._condition(statement.condition) else statement.else_body
                    self._block(branch)
                elif isinstance(statement, OutputStmt):
                    # Output is not in the graph's billing observation, but
                    # the direct source evaluator still records its value.
                    self.output_value = self._expr(statement.expression)
                else:  # pragma: no cover
                    raise BridgeError(f"unsupported source AST node {type(statement).__name__}")
        finally:
            if not root:
                self.frames.pop()

    def run(self) -> dict[str, Any]:
        self._block(list(self.workflow.body), root=True)
        return {"trace": self.trace, "stopped": True,
                "output": self.output_value}


def source_reference_run(source: str, store: dict[str, Any], seed: int,
                         chars_per_token: int = 4, max_calls: int = 10_000) -> dict[str, Any]:
    """Evaluate the parsed source AST directly, independently of graph lowering."""
    try:
        raw = source.encode("utf-8")
    except UnicodeEncodeError as error:
        raise BridgeError("source contains a non-scalar Unicode code point") from error
    workflow = parse_source(raw)
    Resolver(workflow, chars_per_token).resolve()
    return SourceReferenceInterpreter(workflow, store, seed, chars_per_token,
                                      max_calls).run()


def _run_json(command: list[str], what: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BridgeError(f"could not run {what}: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise BridgeError(f"{what} failed (exit {completed.returncode}): {detail[-2000:]}")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise BridgeError(f"{what} did not return valid JSON") from error
    if not isinstance(result, dict):
        raise BridgeError(f"{what} returned a non-object JSON value")
    return result


def check_compiler_snapshot(raw: bytes, compiler_path: Path,
                            chars_per_token: int = 4) -> tuple[subprocess.CompletedProcess[str], str]:
    """Run the compiler on private snapshots of the parsed bytes and executable."""
    if len(raw) > MAX_SOURCE_BYTES:
        raise BridgeError(f"source exceeds {MAX_SOURCE_BYTES} bytes")
    compiler_path = compiler_path.resolve()
    if not compiler_path.is_file():
        raise BridgeError(f"compiler gate executable not found: {compiler_path}")
    compiler_bytes = compiler_path.read_bytes()
    compiler_hash = _sha256(compiler_bytes)
    with tempfile.TemporaryDirectory(prefix="orchlang-compiler-gate-") as temp_name:
        root = Path(temp_name)
        compiler_snapshot = root / "orchc-snapshot"
        compiler_snapshot.write_bytes(compiler_bytes)
        compiler_snapshot.chmod(0o700)
        source_snapshot = root / "source-snapshot.orch"
        source_snapshot.write_bytes(raw)
        try:
            result = subprocess.run(
                [str(compiler_snapshot), "--chars-per-token", str(chars_per_token),
                 "check", str(source_snapshot)], capture_output=True, text=True,
                timeout=45, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise BridgeError(f"compiler check could not complete: {error}") from error
    return result, compiler_hash


def _atomic_outputs(outputs: list[tuple[Path, bytes]]) -> None:
    temporary_paths: list[Path] = []
    try:
        for destination, content in outputs:
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix="." + destination.name + ".",
                                                       dir=destination.parent)
            temp_path = Path(temporary)
            temporary_paths.append(temp_path)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        # All conversion, semantic, graph and replay checks have passed before
        # these replacements. If a multi-file replacement is interrupted, the
        # cross-hashes let readers detect that the set is inconsistent.
        for temporary, (destination, _) in zip(temporary_paths, outputs):
            os.replace(temporary, destination)
    finally:
        for temporary in temporary_paths:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def translate_file(source_path: Path, graph_path: Path, *,
                   sidecar_path: Path | None = None,
                   certificate_path: Path | None = None,
                   compiler_path: Path = ROOT / "orchc",
                   chars_per_token: int = 4) -> tuple[dict[str, Any], dict[str, Any]]:
    """Translate, gate, independently certify/replay, bind provenance, then write."""
    source_path = source_path.resolve()
    graph_path = graph_path.resolve()
    sidecar_path = (sidecar_path or Path(str(graph_path) + ".provenance.json")).resolve()
    certificate_path = (certificate_path or Path(str(graph_path) + ".certificate.json")).resolve()
    compiler_path = compiler_path.resolve()
    paths = (source_path, graph_path, sidecar_path, certificate_path)
    if len(set(paths)) != len(paths):
        raise BridgeError("source, graph, certificate, and provenance sidecar must use distinct paths")
    try:
        if source_path.stat().st_size > MAX_SOURCE_BYTES:
            raise BridgeError(f"source exceeds {MAX_SOURCE_BYTES} bytes")
    except OSError as error:
        raise BridgeError(f"cannot inspect source file: {error}") from error
    raw = source_path.read_bytes()
    parsed = parse_source(raw)
    translation = Resolver(parsed, chars_per_token).resolve()
    graph_bytes = (json.dumps(translation.graph, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    compiler_check, compiler_hash = check_compiler_snapshot(
        raw, compiler_path, chars_per_token)
    if compiler_check.returncode != 0:
        detail = compiler_check.stderr.strip() or compiler_check.stdout.strip()
        raise BridgeError(f"compiler check gate failed (exit {compiler_check.returncode}): {detail[-2000:]}")
    with tempfile.TemporaryDirectory(prefix="orchlang-source-graph-") as temp_name:
        temp_root = Path(temp_name)
        temp_graph = temp_root / "graph.json"
        temp_cert = temp_root / "certificate.json"
        temp_graph.write_bytes(graph_bytes)
        audit_root = Path(__file__).resolve().parent
        checker = audit_root / "orchgraph.py"
        replayer = audit_root / "replay_graph_certificate.py"
        check_report = _run_json([sys.executable, str(checker), str(temp_graph),
                                  "--report", str(temp_cert)], "request-graph check")
        if check_report.get("status") != "accepted":
            raise BridgeError(f"request-graph check did not accept: {check_report.get('diagnostic', 'unknown result')}")
        replay_report = _run_json([sys.executable, str(replayer), str(temp_graph),
                                   str(temp_cert)], "independent certificate replay")
        if replay_report.get("status") != "verified":
            raise BridgeError("independent graph certificate replay did not verify")
        certificate_bytes = temp_cert.read_bytes()

    sidecar = {
        "format": "orchlang-source-graph-provenance",
        "version": 1,
        "workflow": parsed.name,
        "workflow_budget_tokens": parsed.budget,
        "chars_per_token": chars_per_token,
        "source_sha256": _sha256(raw),
        "graph_sha256": _sha256(graph_bytes),
        "certificate_sha256": _sha256(certificate_bytes),
        "adapter_sha256": _sha256(Path(__file__).read_bytes()),
        "source_cost_parser_sha256": _sha256((Path(__file__).resolve().parent / "certificate_audit.py").read_bytes()),
        "compiler_sha256": compiler_hash,
        "graph_format": translation.graph["format"],
        "graph_version": translation.graph["version"],
        "semantic_gate": "orchc check passed before export",
        "graph_checker": {"status": check_report["status"],
                          "product_nodes": check_report.get("product_nodes"),
                          "product_edges": check_report.get("product_edges")},
        "independent_replay": {"status": replay_report["status"]},
        "claim_scope": "billing projection for the supported source subset under the graph's shared-oracle and complete request-accounting premises",
        "omitted_output": {**translation.output,
                           "reason": "one unconditional final public text output has no continuation; output content is outside the billing observation"},
        "mapping": translation.mapping,
    }
    sidecar_bytes = (json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _atomic_outputs([(graph_path, graph_bytes), (certificate_path, certificate_bytes),
                     (sidecar_path, sidecar_bytes)])
    return translation.graph, sidecar


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", type=Path)
    cli.add_argument("graph", type=Path)
    cli.add_argument("--sidecar", type=Path)
    cli.add_argument("--certificate", type=Path)
    cli.add_argument("--compiler", type=Path, default=ROOT / "orchc")
    cli.add_argument("--chars-per-token", type=int, default=4)
    args = cli.parse_args(argv)
    try:
        graph, sidecar = translate_file(args.source, args.graph,
                                        sidecar_path=args.sidecar,
                                        certificate_path=args.certificate,
                                        compiler_path=args.compiler,
                                        chars_per_token=args.chars_per_token)
        print(json.dumps({"status": "translated", "graph": str(args.graph.resolve()),
                          "sidecar": str((args.sidecar or Path(str(args.graph) + ".provenance.json")).resolve()),
                          "certificate": str((args.certificate or Path(str(args.graph) + ".certificate.json")).resolve()),
                          "graph_sha256": sidecar["graph_sha256"],
                          "certificate_sha256": sidecar["certificate_sha256"],
                          "product_nodes": sidecar["graph_checker"]["product_nodes"],
                          "product_edges": sidecar["graph_checker"]["product_edges"]}, indent=2))
        return 0
    except (BridgeError, OSError, ValueError, TypeError, KeyError, IndexError) as error:
        print("source graph conversion refused: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
