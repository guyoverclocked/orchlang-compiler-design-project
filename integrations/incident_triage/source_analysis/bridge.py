#!/usr/bin/env python3
"""Strict, source-specific extractor for the pinned incident-triage workflow.

This does not translate the upstream LangGraph application. It recognizes a
recognized AST slice, emits a self-composed OrchLang request graph for the
exact first classifier call, and extracts the dependency protocol through the
pre-dispatch gate.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INTEGRATION = HERE.parent
MANIFEST_PATH = INTEGRATION / "UPSTREAM_MANIFEST.json"
DEFAULT_UPSTREAM = INTEGRATION / "upstream_snapshot"
DEFAULT_STUDY = INTEGRATION / "results" / "source_study.json"
SOURCE_STUDY_SHA256 = "3f10906bb8fdd2283c59b188863304ecb2431c662ca0be3c0a04aaadfa05e9ab"
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_PRODUCT_NODES = 1000
CLASSIFIER_PREFIX = "INCIDENT REPORT: "
EXPECTED_SOURCE_FILES = (
    "src/triage/graph.py",
    "src/triage/guardrails.py",
    "src/triage/models.py",
    "src/triage/costs.py",
    "src/triage/config.py",
    "src/triage/llm.py",
    "data/sites.json",
)
EXPECTED_PYTHON_FILES = EXPECTED_SOURCE_FILES[:-1]

# These normalized-AST digests pin the helper bodies whose behavior is part of
# the dependency protocol. They supplement (rather than replace) the upstream
# commit/tree and full-file manifest binding. A changed helper fails closed,
# even when a mutation remains syntactically valid.
HELPER_AST_SHA256 = {
    "graph.py:classify": "48eaa5566eab16288aed4b3994e2ec810c422fadbf6d92740dd455a1be66e714",
    "graph.py:enrich": "3f0a332b02dac194d50ee999e56541ff11e519b38c20a22a183b7ae18d68e793",
    "graph.py:prioritise": "d6b1e3c1895c874d6f6784c151555908a962f4a6c61906119ce8910e8184c03a",
    "graph.py:draft": "fb9f2887e9cf0773b88faff67850bd156f286edbb685ab544693b5babdd9cbd2",
    "graph.py:route_after": "c529af4ff8e20f3abb7d71d54fdd367946e1f3f0ed4ca600dc6df3fd6b5556e2",
    "graph.py:build_graph": "668545efc5222cf3ced3c075c76a001aba145e9dc0e29930c903967053e5d9b0",
    "guardrails.py:redact_pii": "f8ade865e5cdfaa8ee4d59f533f531f48f8409f938f9fc4a88f86203af3b5dcf",
    "guardrails.py:parse_structured": "ebad3330ecabaa957178d1af2d427674fca42a2a7acc53edbdd990626e34617a",
    "guardrails.py:call_with_repair": "4279abe8dc845eb592de93e5bfee33c7a2a5fdf872358990a759b273c227cb4c",
    "costs.py:estimate_tokens": "4703e938d4a4d9b4ffa02c42deb6b48f65d31cc4283bfc70f72e181bab085e88",
    "costs.py:record": "31c971c85338d3f7d22e6580315d1f5b7e76eb0679a08476fdfd43c07951b4e3",
    "costs.py:total_usd": "3f5540b6b70bf541c956a44f1d1fa0e4b7c317ae8dd39e0fe9da03b1525af124",
    "costs.py:over_budget": "2927ac2c288ab01ba4b1bf88b45351008a409a7d00b4be19f4f5b24a9d953381",
    "costs.py:complete": "7684b478cabfa1065e66afd303ead07b1f25c20b6003a59222a47969b7cb3ba4",
}

EXPECTED_PAIRS = {
    ("pii_email_a", "pii_email_b"),
    ("pii_phone_a", "pii_phone_b"),
    ("pii_national_insurance_a", "pii_national_insurance_b"),
    ("retry_email_a", "retry_email_b"),
    ("public_text_a", "public_text_b"),
    ("unlisted_name_a", "unlisted_name_b"),
    ("mock_marker_absent", "mock_marker_present"),
    ("pii_presence_absent", "pii_presence_present"),
    ("pii_count_one", "pii_count_two"),
    ("pii_type_email", "pii_type_phone"),
    ("public_text_a", "upstream_default_mock"),
}


class BridgeError(ValueError):
    """The checkout or source AST is outside the pinned recognized subset."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _portable_ast(value: Any) -> Any:
    """Serialize semantic AST fields while ignoring version-added empty fields.

    CPython releases can add optional empty AST fields (for example
    ``type_params``) and change ``ast.dump`` formatting. This representation
    keeps node kinds and populated fields, but omits ``None`` and empty-list
    fields so the pinned helper fingerprints are stable across supported
    Python versions.
    """
    if isinstance(value, ast.AST):
        fields = {}
        for name, child in ast.iter_fields(value):
            if child is None or (isinstance(child, list) and not child):
                continue
            fields[name] = _portable_ast(child)
        return {"node": type(value).__name__, "fields": fields}
    if isinstance(value, list):
        return [_portable_ast(item) for item in value]
    return value


def _same_ast(left: ast.AST, right: ast.AST) -> bool:
    return _portable_ast(left) == _portable_ast(right)


def _literal(node: ast.AST, label: str) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError) as error:
        raise BridgeError(f"{label} must be a literal in the recognized subset") from error


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _find_function(tree: ast.Module, name: str, *, parent: ast.AST | None = None) -> ast.FunctionDef | ast.AsyncFunctionDef:
    root = parent if parent is not None else tree
    matches = [node for node in ast.walk(root)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(matches) != 1 or not isinstance(matches[0], ast.FunctionDef):
        raise BridgeError(f"expected one synchronous function {name!r}")
    return matches[0]


def _parse(raw: bytes, label: str) -> ast.Module:
    if len(raw) > MAX_JSON_BYTES:
        raise BridgeError(f"{label} exceeds source byte cap")
    try:
        return ast.parse(raw.decode("utf-8"), filename=label)
    except (UnicodeDecodeError, SyntaxError, ValueError, RecursionError) as error:
        raise BridgeError(f"cannot parse {label}: {error}") from error


def _name_call(node: ast.AST, name: str, args: int | None = None) -> ast.Call:
    if not isinstance(node, ast.Call) or _call_name(node.func) != name:
        raise BridgeError(f"expected call to {name}")
    if args is not None and len(node.args) != args:
        raise BridgeError(f"{name} must have {args} positional arguments")
    if node.keywords:
        raise BridgeError(f"{name} keywords are outside the recognized subset")
    return node


def _assignments(tree: ast.Module) -> dict[str, ast.AST]:
    values: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            values[node.targets[0].id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            values[node.target.id] = node.value
    return values


def _regex_contract(tree: ast.Module) -> dict[str, Any]:
    assignments = _assignments(tree)
    patterns: dict[str, str] = {}
    for name in ("EMAIL_RE", "PHONE_RE", "NI_NUMBER_RE"):
        value = assignments.get(name)
        call = _name_call(value, "re.compile", 1)
        pattern = _literal(call.args[0], name)
        if not isinstance(pattern, str):
            raise BridgeError(f"{name} pattern must be text")
        try:
            re.compile(pattern)
        except re.error as error:
            raise BridgeError(f"invalid source regex {name}: {error}") from error
        patterns[name] = pattern

    fn = _find_function(tree, "redact_pii")
    if len(fn.body) != 3:
        raise BridgeError("redact_pii body changed; only the pinned three-step redactor is supported")
    expected = (
        ("EMAIL_RE", "[EMAIL]", "text", "assign"),
        ("PHONE_RE", "[PHONE]", "text", "assign"),
        ("NI_NUMBER_RE", "[NI-NUMBER]", "text", "return"),
    )
    for index, (regex_name, replacement, subject, kind) in enumerate(expected):
        statement = fn.body[index]
        if kind == "assign":
            if not isinstance(statement, ast.Assign) or len(statement.targets) != 1 \
                    or not isinstance(statement.targets[0], ast.Name) or statement.targets[0].id != subject:
                raise BridgeError("redact_pii substitution order or target changed")
            value = statement.value
        else:
            if not isinstance(statement, ast.Return) or statement.value is None:
                raise BridgeError("redact_pii must return the final NI-number substitution")
            value = statement.value
        call = _name_call(value, f"{regex_name}.sub", 2)
        if _literal(call.args[0], f"{regex_name} replacement") != replacement:
            raise BridgeError(f"redact_pii replacement for {regex_name} changed")
        if not isinstance(call.args[1], ast.Name) or call.args[1].id != subject:
            raise BridgeError(f"redact_pii input flow for {regex_name} changed")
    return {
        "function": "triage.guardrails.redact_pii",
        "source_line": fn.lineno,
        "order": ["EMAIL_RE", "PHONE_RE", "NI_NUMBER_RE"],
        "patterns": patterns,
        "replacements": {"EMAIL_RE": "[EMAIL]", "PHONE_RE": "[PHONE]",
                         "NI_NUMBER_RE": "[NI-NUMBER]"},
        "contract": "deterministic ordered Python re.sub calls on one text value",
    }


def _field_call(field: ast.AST) -> tuple[str, dict[str, Any]]:
    if not isinstance(field, ast.AnnAssign) or not isinstance(field.target, ast.Name):
        raise BridgeError("model fields must use annotated assignments")
    annotation = ast.unparse(field.annotation)
    constraints: dict[str, Any] = {"type": annotation}
    if isinstance(field.value, ast.Call) and _call_name(field.value.func) == "Field":
        for keyword in field.value.keywords:
            constraints[keyword.arg] = _literal(keyword.value, f"Field {keyword.arg}")
    return field.target.id, constraints


def _model_contract(tree: ast.Module, name: str) -> dict[str, Any]:
    matches = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name]
    if len(matches) != 1:
        raise BridgeError(f"expected one model class {name}")
    aliases = {
        node.targets[0].id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign) and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }
    fields: dict[str, Any] = {}
    for field in matches[0].body:
        if not isinstance(field, ast.AnnAssign):
            continue
        field_name, constraints = _field_call(field)
        if isinstance(field.annotation, ast.Name) and field.annotation.id in aliases:
            constraints["type"] = ast.unparse(aliases[field.annotation.id])
        fields[field_name] = constraints
    return fields


def _validate_incident_model(models_tree: ast.Module) -> dict[str, Any]:
    fields = _model_contract(models_tree, "IncidentReport")
    expected = {"incident_id": {"type": "str"}, "site": {"type": "str"},
                "reported_by": {"type": "str"},
                "text": {"type": "str", "min_length": 10, "max_length": 4000}}
    if fields != expected:
        raise BridgeError("IncidentReport field/type/length contract changed")
    return fields


def _classify_request(graph_tree: ast.Module, guardrails_tree: ast.Module,
                      models_tree: ast.Module) -> tuple[str, dict[str, Any]]:
    assignments = _assignments(graph_tree)
    system = _literal(assignments.get("CLASSIFY_SYSTEM", ast.Constant(None)), "CLASSIFY_SYSTEM")
    if not isinstance(system, str) or not system:
        raise BridgeError("CLASSIFY_SYSTEM must be a nonempty string literal")

    build = _find_function(graph_tree, "build_graph")
    classify = _find_function(graph_tree, "classify", parent=build)
    calls = [node for node in ast.walk(classify)
             if isinstance(node, ast.Call) and _call_name(node.func) == "call_with_repair"]
    if len(calls) != 1:
        raise BridgeError("classify must contain exactly one call_with_repair operation")
    call = calls[0]
    if call.keywords:
        raise BridgeError("classifier call_with_repair has an unrecognized extra input; raw-text repair injection is not allowed")
    if len(call.args) != 4:
        raise BridgeError("classification call_with_repair signature changed")
    if not isinstance(call.args[0], ast.Name) or call.args[0].id != "tracked" \
            or not isinstance(call.args[1], ast.Name) or call.args[1].id != "CLASSIFY_SYSTEM" \
            or not isinstance(call.args[3], ast.Name) or call.args[3].id != "Classification":
        raise BridgeError("classification helper arguments changed")
    prompt = call.args[2]
    if not isinstance(prompt, ast.JoinedStr) or len(prompt.values) != 2 \
            or not isinstance(prompt.values[0], ast.Constant) \
            or prompt.values[0].value != CLASSIFIER_PREFIX \
            or not isinstance(prompt.values[1], ast.FormattedValue) \
            or not isinstance(prompt.values[1].value, ast.Name) \
            or prompt.values[1].value.id != "clean_text":
        raise BridgeError("classifier user prompt no longer applies the approved clean_text projection")

    redaction_assignment = [node for node in ast.walk(classify)
                            if isinstance(node, ast.Assign) and len(node.targets) == 1
                            and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "clean_text"]
    if len(redaction_assignment) != 1:
        raise BridgeError("classify must assign clean_text once")
    redaction = _name_call(redaction_assignment[0].value, "redact_pii", 1)
    redacted_arg = redaction.args[0]
    if not isinstance(redacted_arg, ast.Attribute) or redacted_arg.attr != "text" \
            or not isinstance(redacted_arg.value, ast.Name) or redacted_arg.value.id != "incident":
        raise BridgeError("classifier redactor must consume the validated incident.text field")

    incident_validation = [node for node in ast.walk(classify)
                           if isinstance(node, ast.Call)
                           and _call_name(node.func) == "IncidentReport.model_validate"]
    if len(incident_validation) != 1 or len(incident_validation[0].args) != 1:
        raise BridgeError("classify must validate one IncidentReport before redaction")
    state_item = incident_validation[0].args[0]
    if not isinstance(state_item, ast.Subscript) or not isinstance(state_item.value, ast.Name) \
            or state_item.value.id != "state" or _literal(state_item.slice, "state field") != "incident":
        raise BridgeError("classify input must come from state['incident']")

    _validate_call_with_repair(guardrails_tree)

    # The prompt's stated summary length is checked against the Pydantic model;
    # a mismatch is retained as a source fact rather than silently normalized.
    prompt_summary = re.search(r"\"summary\": string \(max (\d+) chars\)", system)
    classification_fields = _model_contract(models_tree, "Classification")
    schema_summary_cap = classification_fields.get("summary", {}).get("max_length")
    prompt_summary_cap = int(prompt_summary.group(1)) if prompt_summary else None
    request = {
        "source_node": "classify",
        "source_call_line": call.lineno,
        "source_call_function": "call_with_repair",
        "source_call_phase": "first completion only",
        "system_symbol": "CLASSIFY_SYSTEM",
        "system": system,
        "user_expression": {
            "kind": "fstring",
            "prefix": CLASSIFIER_PREFIX,
            "value": {"kind": "redact_pii", "argument": "IncidentReport.text"},
        },
        "exact_message_pair": {
            "system": system,
            "user_prefix": CLASSIFIER_PREFIX,
            "dynamic_user_value": "redact_pii(incident.text)",
        },
        "source_helpers": ["IncidentReport.model_validate", "redact_pii", "call_with_repair"],
        "excluded_helper_phase": "the optional repair completion after SchemaViolation",
        "classification_prompt_summary_max": prompt_summary_cap,
        "classification_schema_summary_max": schema_summary_cap,
    }
    return system, request


def _validate_call_with_repair(tree: ast.Module) -> dict[str, Any]:
    fn = _find_function(tree, "call_with_repair")
    if [arg.arg for arg in fn.args.args] != ["llm", "system", "user", "schema"] \
            or fn.args.vararg is not None or fn.args.kwarg is not None or fn.args.kwonlyargs:
        raise BridgeError("repair helper accepts only the validated original user/system/schema values")
    complete = [node for node in ast.walk(fn)
                if isinstance(node, ast.Call) and _call_name(node.func) == "llm.complete"]
    if len(complete) != 2:
        raise BridgeError("call_with_repair must have exactly one initial and one repair completion")
    if any(len(node.args) != 2 or node.keywords for node in complete):
        raise BridgeError("call_with_repair completion signature changed")
    if not all(isinstance(arg, ast.Name) for arg in complete[0].args) \
            or [arg.id for arg in complete[0].args] != ["system", "user"]:
        raise BridgeError("initial model request must be complete(system, user)")
    if not all(isinstance(arg, ast.Name) for arg in complete[1].args) \
            or [arg.id for arg in complete[1].args] != ["system", "repair_user"]:
        raise BridgeError("repair model request must be complete(system, repair_user)")
    repair_assignments = [node for node in ast.walk(fn)
                          if isinstance(node, ast.Assign) and len(node.targets) == 1
                          and isinstance(node.targets[0], ast.Name)
                          and node.targets[0].id == "repair_user"]
    if len(repair_assignments) != 1 or not isinstance(repair_assignments[0].value, ast.JoinedStr):
        raise BridgeError("repair request must be one deterministic formatted string")
    expected_repair = ast.parse(
        "(f'{user}\\n\\nYour previous response failed validation with:\\n{exc}\\n' "
        "f'Respond again with ONLY valid JSON for the schema.')",
        mode="eval",
    ).body
    if not _same_ast(repair_assignments[0].value, expected_repair):
        raise BridgeError("repair prompt contains an unrecognized dependency; only original request and validation error are allowed")
    return {
        "function": "triage.guardrails.call_with_repair",
        "source_line": fn.lineno,
        "maximum_completions": 2,
        "initial_call_line": complete[0].lineno,
        "repair_call_line": complete[1].lineno,
        "repair_user_expression_is_formatted_from": ["user", "SchemaViolation text"],
    }


def _validate_draft_function(draft: ast.FunctionDef, actions_system: str) -> None:
    prompt_assignments = [node.value for node in ast.walk(draft)
                          if isinstance(node, ast.Assign) and len(node.targets) == 1
                          and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "prompt"]
    if len(prompt_assignments) != 1:
        raise BridgeError("draft prompt assignment changed")
    expected = ast.parse(
        "(f\"category: {state['classification']['category']}\\n\" "
        "f\"priority: {state['priority']['level']}\\n\" "
        "f\"summary: {state['classification']['summary']}\")",
        mode="eval",
    ).body
    if not _same_ast(prompt_assignments[0], expected):
        raise BridgeError("draft prompt contains an unrecognized dependency, including possible raw incident text")
    calls = [node for node in ast.walk(draft) if isinstance(node, ast.Call)
             and _call_name(node.func) == "tracked.complete"]
    if len(calls) != 1 or len(calls[0].args) != 2 or calls[0].keywords \
            or not isinstance(calls[0].args[0], ast.Name) or calls[0].args[0].id != "ACTIONS_SYSTEM" \
            or not isinstance(calls[0].args[1], ast.Name) or calls[0].args[1].id != "prompt":
        raise BridgeError("draft completion does not use the recognized system and prompt")


def _source_control(build: ast.FunctionDef) -> dict[str, Any]:
    node_rows: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    entry_points: list[str] = []
    interrupt_nodes: list[str] = []
    route_functions = [node for node in ast.walk(build)
                       if isinstance(node, ast.FunctionDef) and node.name == "route_after"]
    if len(route_functions) != 1:
        raise BridgeError("expected one route_after helper")
    route = route_functions[0]
    nested = [node for node in ast.walk(route)
              if isinstance(node, ast.FunctionDef) and node.name == "_route"]
    if len(nested) != 1:
        raise BridgeError("route_after must return one route function")
    returns = [node for node in nested[0].body if isinstance(node, ast.Return)]
    if len(returns) != 1 or not isinstance(returns[0].value, ast.IfExp):
        raise BridgeError("route_after must return one conditional expression")
    expression = returns[0].value
    test = expression.test
    if not isinstance(test, ast.Call) or _call_name(test.func) != "state.get" \
            or len(test.args) != 1 or _literal(test.args[0], "route error key") != "error" \
            or not isinstance(expression.body, ast.Constant) or expression.body.value != "human_review" \
            or not isinstance(expression.orelse, ast.Name) or expression.orelse.id != "key":
        raise BridgeError("route_after no longer sends state errors to human_review")

    for node in ast.walk(build):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) \
                or not isinstance(node.func.value, ast.Name) or node.func.value.id != "graph":
            continue
        method = node.func.attr
        if method == "add_node":
            if len(node.args) != 2:
                raise BridgeError("graph.add_node signature changed")
            name = _literal(node.args[0], "node name")
            fn = node.args[1].id if isinstance(node.args[1], ast.Name) else ast.unparse(node.args[1])
            node_rows.append({"name": name, "function": fn, "line": node.lineno})
        elif method == "add_edge":
            if len(node.args) != 2:
                raise BridgeError("graph.add_edge signature changed")
            source = _literal(node.args[0], "edge source")
            target = "END" if isinstance(node.args[1], ast.Name) and node.args[1].id == "END" \
                else _literal(node.args[1], "edge target")
            edges.append({"from": source, "to": target, "kind": "unconditional", "line": node.lineno})
        elif method == "add_conditional_edges":
            if len(node.args) != 2 or not isinstance(node.args[1], ast.Call) \
                    or _call_name(node.args[1].func) != "route_after" or len(node.args[1].args) != 1:
                raise BridgeError("conditional graph edges must use route_after(key)")
            source = _literal(node.args[0], "conditional edge source")
            key = _literal(node.args[1].args[0], "conditional edge destination")
            edges.append({"from": source, "to": {"on_error": "human_review", "otherwise": key},
                          "kind": "conditional", "line": node.lineno})
        elif method == "set_entry_point":
            if len(node.args) != 1:
                raise BridgeError("graph entry point call changed")
            entry_points.append(_literal(node.args[0], "entry point"))
        elif method == "compile":
            for keyword in node.keywords:
                if keyword.arg == "interrupt_before":
                    values = _literal(keyword.value, "interrupt_before")
                    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                        raise BridgeError("interrupt_before must be a literal string list")
                    interrupt_nodes.extend(values)

    node_names = {row["name"] for row in node_rows}
    expected_nodes = {"classify", "enrich", "prioritise", "draft", "dispatch", "human_review"}
    expected_edges = {
        ("classify", "conditional", "enrich"),
        ("enrich", "conditional", "prioritise"),
        ("prioritise", "unconditional", "draft"),
        ("draft", "conditional", "dispatch"),
        ("dispatch", "unconditional", "END"),
        ("human_review", "unconditional", "END"),
    }
    actual_edges = set()
    for edge in edges:
        target = edge["to"]["otherwise"] if edge["kind"] == "conditional" else edge["to"]
        actual_edges.add((edge["from"], edge["kind"], target))
    if node_names != expected_nodes or len(node_rows) != len(expected_nodes):
        raise BridgeError("StateGraph node topology changed")
    if set(entry_points) != {"classify"}:
        raise BridgeError("StateGraph entry point changed")
    if actual_edges != expected_edges or len(edges) != len(expected_edges):
        raise BridgeError("StateGraph edge topology changed")
    if interrupt_nodes != ["dispatch"]:
        raise BridgeError("pre-dispatch human interrupt changed")
    return {
        "source_entry": "classify",
        "nodes": sorted(node_rows, key=lambda row: row["line"]),
        "edges": sorted(edges, key=lambda row: row["line"]),
        "error_route": "human_review",
        "interrupt_before": interrupt_nodes,
        "checked_from_ast": True,
    }


def _extract_estimator(costs_tree: ast.Module) -> dict[str, Any]:
    fn = _find_function(costs_tree, "estimate_tokens")
    returns = [node for node in fn.body if isinstance(node, ast.Return)]
    if len(returns) != 1:
        raise BridgeError("estimate_tokens must have one return")
    normalized = _portable_ast(returns[0].value)
    expected = _portable_ast(ast.parse("max(1, len(text) // 4)", mode="eval").body)
    if normalized != expected:
        raise BridgeError("upstream source token estimator changed")
    return {
        "function": "triage.costs.estimate_tokens",
        "expression": "max(1, len(text) // 4)",
        "length_unit": "Python Unicode code points",
        "source_line": fn.lineno,
        "not_equivalent_to_graph_accounting": "OrchGraph estimates ceil(UTF8-bytes / divisor) per template/argument fragment",
    }


def _function_node(tree: ast.Module, name: str, *, parent: ast.AST | None = None) -> ast.FunctionDef:
    return _find_function(tree, name, parent=parent)


def _check_helper_ast_fingerprints(trees: dict[str, ast.Module]) -> dict[str, Any]:
    observed: dict[str, str] = {}
    for key, expected in HELPER_AST_SHA256.items():
        filename, function_name = key.split(":", 1)
        tree = trees[filename]
        node = _function_node(tree, function_name)
        digest = _sha(json.dumps(_portable_ast(node), ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")).encode("utf-8"))
        if digest != expected:
            raise BridgeError(f"source helper AST changed: {key}")
        observed[key] = digest
    return observed


def _dependency_protocol(
    *,
    source_files: dict[str, bytes],
    trees: dict[str, ast.Module],
    redactor: dict[str, Any],
    incident_fields: dict[str, Any],
    request: dict[str, Any],
    control: dict[str, Any],
    estimator: dict[str, Any],
) -> dict[str, Any]:
    graph_tree = trees["graph.py"]
    guardrails_tree = trees["guardrails.py"]
    models_tree = trees["models.py"]
    costs_tree = trees["costs.py"]
    config_tree = trees["config.py"]
    llm_tree = trees["llm.py"]
    build = _find_function(graph_tree, "build_graph")

    model_contracts = {
        name: _model_contract(models_tree, name)
        for name in ("Classification", "Enrichment", "Priority", "TriageReport", "NodeCost")
    }
    expected_classification = {
        "category": {"type": "Literal['physical_security', 'cyber', 'safety', 'operational', 'environmental']"},
        "severity": {"type": "Literal['low', 'medium', 'high', 'critical']"},
        "summary": {"type": "str", "max_length": 300},
        "people_at_risk": {"type": "bool"},
    }
    if model_contracts["Classification"] != expected_classification:
        raise BridgeError("Classification field contract changed")

    assignments = _assignments(config_tree)
    try:
        priority_matrix = ast.literal_eval(assignments["PRIORITY_MATRIX"])
        pricing = ast.literal_eval(assignments["PRICING"])
    except (KeyError, ValueError, TypeError) as error:
        raise BridgeError("priority/pricing configuration must remain literal") from error
    if not isinstance(priority_matrix, dict) or len(priority_matrix) != 8:
        raise BridgeError("priority matrix shape changed")
    if pricing != {
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "mock": {"input": 0.0, "output": 0.0},
    }:
        raise BridgeError("pricing table changed")

    try:
        sites = json.loads(source_files["data/sites.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BridgeError("site registry is not valid UTF-8 JSON") from error
    if not isinstance(sites, dict) or set(sites) != {"GTS-01", "NCL-02", "SUN-03"}:
        raise BridgeError("pinned site registry keys changed")

    graph_assignments = _assignments(graph_tree)
    actions_system = _literal(graph_assignments.get("ACTIONS_SYSTEM", ast.Constant(None)), "ACTIONS_SYSTEM")
    if not isinstance(actions_system, str) or not actions_system:
        raise BridgeError("ACTIONS_SYSTEM must remain a nonempty source literal")
    guardrails = _validate_call_with_repair(guardrails_tree)
    classify_fn = _find_function(graph_tree, "classify", parent=build)
    enrich_fn = _find_function(graph_tree, "enrich", parent=build)
    prioritise_fn = _find_function(graph_tree, "prioritise", parent=build)
    draft_fn = _find_function(graph_tree, "draft", parent=build)
    route_fn = _find_function(graph_tree, "route_after", parent=build)
    parse_fn = _find_function(guardrails_tree, "parse_structured")
    repair_fn = _find_function(guardrails_tree, "call_with_repair")
    record_fn = _find_function(costs_tree, "record")
    total_fn = _find_function(costs_tree, "total_usd")
    over_budget_fn = _find_function(costs_tree, "over_budget")
    wrapper_fn = _find_function(costs_tree, "complete")
    _validate_draft_function(draft_fn, actions_system)

    helper_files = {
        "src/triage/graph.py": _sha(source_files["src/triage/graph.py"]),
        "src/triage/guardrails.py": _sha(source_files["src/triage/guardrails.py"]),
        "src/triage/models.py": _sha(source_files["src/triage/models.py"]),
        "src/triage/costs.py": _sha(source_files["src/triage/costs.py"]),
        "src/triage/config.py": _sha(source_files["src/triage/config.py"]),
        "src/triage/llm.py": _sha(source_files["src/triage/llm.py"]),
        "data/sites.json": _sha(source_files["data/sites.json"]),
    }
    line_map = {
        "classify": {"file": "src/triage/graph.py", "line": classify_fn.lineno},
        "enrich": {"file": "src/triage/graph.py", "line": enrich_fn.lineno},
        "prioritise": {"file": "src/triage/graph.py", "line": prioritise_fn.lineno},
        "draft": {"file": "src/triage/graph.py", "line": draft_fn.lineno},
        "route_after": {"file": "src/triage/graph.py", "line": route_fn.lineno},
        "redact_pii": {"file": "src/triage/guardrails.py", "line": redactor["source_line"]},
        "parse_structured": {"file": "src/triage/guardrails.py", "line": parse_fn.lineno},
        "call_with_repair": {"file": "src/triage/guardrails.py", "line": repair_fn.lineno},
        "estimate_tokens": {"file": "src/triage/costs.py", "line": estimator["source_line"]},
        "CostTracker.record": {"file": "src/triage/costs.py", "line": record_fn.lineno},
        "CostTracker.total_usd": {"file": "src/triage/costs.py", "line": total_fn.lineno},
        "CostTracker.over_budget": {"file": "src/triage/costs.py", "line": over_budget_fn.lineno},
        "TrackingLLM.complete": {"file": "src/triage/costs.py", "line": wrapper_fn.lineno},
    }
    helper_ast = _check_helper_ast_fingerprints(trees)

    # Preserve the parsed fields because `summary` is an arbitrary validated
    # string that is interpolated into a later model request. A Boolean/length
    # abstraction would lose the request dependency.
    return {
        "format": "orchlang-incident-triage-dependency-protocol",
        "version": 1,
        "source_files_sha256": helper_files,
        "source_line_map": line_map,
        "recognized_helper_ast_sha256": helper_ast,
        "input_relation": {
            "public_fields_equal": ["incident_id", "site", "reported_by", "thread_id"],
            "validity": {
                "model": "IncidentReport",
                "fields": incident_fields,
                "validation_precedes_classifier_try": True,
                "invalid_input_behavior": "Pydantic validation may raise before the graph's SchemaViolation route",
            },
            "secret_relation": "redact_pii(text_left) == redact_pii(text_right)",
            "redactor": redactor,
            "release_scope": "only exact equality of the ordered sanitizer output is released; residual text is assumed public under this pair relation",
            "not_released": ["PII marker presence", "PII count", "PII pattern type", "unmatched sensitive text", "raw state/checkpoint storage"],
        },
        "classification": {
            "request": request["exact_message_pair"],
            "response_schema": model_contracts["Classification"],
            "prompt_schema_note": {
                "prompt_summary_max_chars": request["classification_prompt_summary_max"],
                "validated_summary_max_chars": request["classification_schema_summary_max"],
                "mismatch": request["classification_prompt_summary_max"] != request["classification_schema_summary_max"],
            },
            "typed_result_dependencies": {
                "category": ["enrich.related_procedures", "draft.user.category", "report payload"],
                "severity": ["priority matrix", "priority rationale", "report payload"],
                "summary": ["draft.user.summary", "report payload"],
                "people_at_risk": ["priority matrix", "priority rationale", "report payload"],
            },
        },
        "validation_and_repair": {
            "parser_contract": {
                "strip_raw_response": True,
                "fence_condition": "cleaned.startswith('```')",
                "fence_regex": r"^```(?:json)?\s*|\s*```$",
                "fence_flags": ["re.S"],
                "decoder": "json.loads(cleaned)",
                "validator": "schema.model_validate(decoded)",
                "wrapped_errors": ["json.JSONDecodeError", "pydantic.ValidationError"],
                "wrapped_as": "SchemaViolation(str(error))",
            },
            "parser_source_line": parse_fn.lineno,
            "repair": {
                **guardrails,
                "source_expression": ast.unparse(next(
                    node.value for node in ast.walk(repair_fn)
                    if isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "repair_user"
                )),
                "exact_user_formula": "original user + '\\n\\nYour previous response failed validation with:\\n' + str(SchemaViolation) + '\\nRespond again with ONLY valid JSON for the schema.'",
                "same_complete_oracle_required_for": ["initial completion", "optional repair completion"],
                "failure_effect": "a second SchemaViolation becomes classify error; classify returns no costs field, so request/usage trace must be read from the tracker or wrapper",
                "failure_error_format": "classification failed schema validation: {exc}",
            },
        },
        "deterministic_dependencies": {
            "enrichment": {
                "operation": "lookup valid incident.site in the bound JSON registry; use classification.category to select procedures; unknown key sets error",
                "source_line": enrich_fn.lineno,
                "registry_sha256": helper_files["data/sites.json"],
                "registry": sites,
                "fields": model_contracts["Enrichment"],
                "dependencies": ["incident.site", "classification.category", "registry bytes"],
                "unknown_site_route": "human_review before priority/draft",
                "unknown_site_error_format": "unknown site {incident.site!r}",
            },
            "priority": {
                "source_line": prioritise_fn.lineno,
                "matrix": [{"severity": key[0], "people_at_risk": key[1], "level": value[0], "response_sla_minutes": value[1]}
                           for key, value in sorted(priority_matrix.items())],
                "critical_site_rule": "if site_criticality == 'critical' and level != 'P1', decrement P number and set SLA from {P1:15,P2:60,P3:240}",
                "rationale_fields": ["severity", "people_at_risk", "site_criticality"],
                "fields": model_contracts["Priority"],
                "dependencies": ["classification.severity", "classification.people_at_risk", "enrichment.site_criticality", "config.PRIORITY_MATRIX"],
            },
        },
        "usage_and_budget": {
            "estimator": estimator,
            "record_formula": {
                "input_tokens": "max(1, len(system + user) // 4)",
                "output_tokens": "max(1, len(response) // 4)",
                "length_unit": "Python Unicode code points",
                "cost_usd": "round((input_tokens * pricing.input + output_tokens * pricing.output) / 1_000_000, 6)",
                "pricing_lookup": "PRICING.get(model_name, PRICING['mock'])",
                "source_line": record_fn.lineno,
            },
            "total_formula": "round(sum(per_call_rounded_cost_usd), 6)",
            "budget_predicate": "rounded_total_usd > MAX_COST_PER_INCIDENT_USD",
            "numeric_semantics": "Python float arithmetic and built-in round at six decimal places for each row and total",
            "total_source_line": total_fn.lineno,
            "budget_usd": 0.05,
            "budget_guard": "draft checks tracker.over_budget before issuing ACTIONS_SYSTEM request; true returns error and routes to human_review",
            "budget_guard_source_line": draft_fn.lineno,
            "over_budget_source_line": over_budget_fn.lineno,
            "pricing": pricing,
            "mock_price": 0.0,
            "observer": "source tracker/wrapper call rows, including classifier failures whose returned state omits costs",
            "not_provider_billing": True,
        },
        "draft_and_gate": {
            "draft_source_line": draft_fn.lineno,
            "system": actions_system,
            "user_template": "category: {classification.category}\\npriority: {priority.level}\\nsummary: {classification.summary}",
            "raw_incident_text_dependency": False,
            "response_handling": "JSON list parsing with a fixed fallback action on JSON/assertion failure; response content does not affect routing",
            "fallback_action": "Review incident manually; drafting agent returned invalid output",
            "actions_coercion_and_limit": "[str(action) for action in parsed_actions][:5]",
            "budget_error_format": "cost budget exceeded (${tracker.total_usd})",
            "report_fields": model_contracts["TriageReport"],
            "control": control,
            "gate": "interrupt_before=['dispatch']; theorem endpoint is the pending pre-dispatch state",
            "maximum_model_completions_pre_dispatch": 3,
            "full_state_checkpoint_privacy": "excluded: raw incident remains in state/checkpointer and human_review returns state",
        },
        "shared_outcome_oracle": {
            "key": ["resolved provider/model contract", "per-contract call ordinal", "exact system string", "exact user string"],
            "coupled_outcome": ["response text", "any source-observed provider usage metadata"],
            "scope": "premise for paired requests at classify, repair, and draft; the pinned MockLLM is deterministic for identical complete requests in the captured source study",
            "not_established_for": ["arbitrary live providers", "network errors", "retries outside call_with_repair", "provider usage receipts not exposed by this source wrapper"],
        },
        "execution_premises": {
            "fresh_graph_and_checkpointer_per_run": True,
            "serialized_nonconcurrent_invocations": True,
            "reason": "build_graph closes over mutable tracker/current_node; classify clears shared tracker.entries",
            "fixed_assets_config_dependency_versions_and_provider": True,
            "source_graph_topology": control,
            "terminal_scope": "all request, source-estimated usage, error-route, node and interrupt events through the pre-dispatch human gate",
        },
        "conditional_result": "equal exact redacted text plus equal valid public metadata/configuration and the shared complete outcome oracle yields equal pre-dispatch request/usage/route observations for this recognized source version",
        "trust_boundary": [
            "pinned source bytes and Python/Pydantic/LangGraph semantics",
            "the exact redactor is an approved release under the stated relation",
            "the shared complete outcome oracle premise",
            "serial fresh graph/tracker/checkpointer execution",
        ],
        "excluded": [
            "generic Python-to-OrchGraph translation",
            "proof of sanitizer adequacy or general PII coverage",
            "checkpoint/full-state storage privacy",
            "external human decision or dispatch effects",
            "provider-side tokenization, usage receipts, currency charges, or output caps",
            "invalid Pydantic inputs, concurrent use of one graph, provider failures, or arbitrary source/config mutations",
            "source report payload equality beyond the dependencies needed for later requests and control",
        ],
    }


def extract_source_contract(source_files: dict[str, bytes]) -> dict[str, Any]:
    """Recognize the pinned source's request and pre-dispatch dependency slice."""
    missing = set(EXPECTED_SOURCE_FILES) - source_files.keys()
    if missing:
        raise BridgeError(f"source bundle misses files: {sorted(missing)}")
    trees = {
        filename.rsplit("/", 1)[-1]: _parse(source_files[filename], filename)
        for filename in EXPECTED_PYTHON_FILES
    }
    graph_tree = trees["graph.py"]
    guardrails_tree = trees["guardrails.py"]
    models_tree = trees["models.py"]
    costs_tree = trees["costs.py"]
    config_tree = trees["config.py"]
    llm_tree = trees["llm.py"]
    redactor = _regex_contract(guardrails_tree)
    incident_fields = _validate_incident_model(models_tree)
    system, request = _classify_request(graph_tree, guardrails_tree, models_tree)
    build = _find_function(graph_tree, "build_graph")
    control = _source_control(build)
    estimator = _extract_estimator(costs_tree)
    config = _assignments(config_tree)
    llm_provider_default = config.get("LLM_PROVIDER")
    if not isinstance(llm_provider_default, ast.Call) or _call_name(llm_provider_default.func) != "os.environ.get" \
            or len(llm_provider_default.args) != 2 or _literal(llm_provider_default.args[0], "provider env key") != "TRIAGE_LLM" \
            or _literal(llm_provider_default.args[1], "provider default") != "mock":
        raise BridgeError("source default provider contract changed")
    max_cost = config.get("MAX_COST_PER_INCIDENT_USD")
    if _literal(max_cost, "source max budget") != 0.05:
        raise BridgeError("source cost budget changed")
    mock_classes = [node for node in llm_tree.body if isinstance(node, ast.ClassDef) and node.name == "MockLLM"]
    if len(mock_classes) != 1:
        raise BridgeError("pinned MockLLM definition changed")
    mock_name = _assignments(ast.Module(body=mock_classes[0].body, type_ignores=[])).get("name")
    if not isinstance(mock_name, ast.Constant) or mock_name.value != "mock":
        raise BridgeError("MockLLM resolved name changed")
    try:
        registry = json.loads(source_files["data/sites.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BridgeError("site registry must be valid UTF-8 JSON") from error
    if not isinstance(registry, dict) or set(registry) != {"GTS-01", "NCL-02", "SUN-03"}:
        raise BridgeError("pinned site registry keys changed")
    protocol = _dependency_protocol(
        source_files=source_files,
        trees=trees,
        redactor=redactor,
        incident_fields=incident_fields,
        request=request,
        control=control,
        estimator=estimator,
    )
    helper_ast = protocol["recognized_helper_ast_sha256"]
    return {
        "system": system,
        "request": request,
        "redactor": redactor,
        "incident_fields": incident_fields,
        "control": control,
        "source_estimator": estimator,
        "source_provider_default": "mock",
        "source_mock_name": "mock",
        "source_budget_usd": 0.05,
        "source_scope": "pinned source, exact pre-dispatch request/usage/route dependencies under stated helper and oracle contracts",
        "dependency_protocol": protocol,
        "recognized_helper_ast_sha256": helper_ast,
        "source_model_summary_mismatch": {
            "prompt_max_chars": request["classification_prompt_summary_max"],
            "schema_max_chars": request["classification_schema_summary_max"],
            "mismatch": request["classification_prompt_summary_max"] != request["classification_schema_summary_max"],
        },
    }


def _literal_message(user: str) -> str:
    if not isinstance(user, str):
        raise BridgeError("classifier user message must be text")
    return user


def build_request_graph(contract: dict[str, Any], *, source_commit: str) -> dict[str, Any]:
    """Build a two-lane product graph; the secret selector is analysis harness only."""
    system = contract["system"]
    # Each of the three re.sub replacements has length at most twice the
    # matched span. The raw field is <= 4,000 code points, hence after three
    # substitutions <= 8*4,000 code points. Four UTF-8 bytes/code point and the
    # fixed prefix give a conservative byte-unit graph input cap.
    input_cap = 4 * (8 * 4000 + len(CLASSIFIER_PREFIX))
    return {
        "format": "orchlang-request-graph",
        "version": 1,
        "name": "incident_triage_classifier_request_slice",
        "chars_per_token": 1,
        "inputs": {
            "classifier_user_message": {"type": "text", "label": "public", "max_tokens": input_cap},
            "pair_side": {"type": "boolean", "label": "secret"},
        },
        "registers": {
            "left_response": {"model": "source_mock"},
            "right_response": {"model": "source_mock"},
        },
        "models": {
            "source_mock": {
                "provider": "pinned-source-fixture",
                "model": f"MockLLM@{source_commit}",
                # OrchGraph requires a cap. Upstream MockLLM has no output cap;
                # this synthetic value is irrelevant to the one-call relation.
                "max_tokens": 1,
            },
        },
        "states": {
            "entry": {"calls": [], "next": {
                "kind": "secret", "guard": {"value": "pair_side"},
                "then": "left_call", "else": "right_call",
            }},
            "left_call": {"calls": [{
                "model": "source_mock", "template": contract["system"],
                "arguments": [{"value": "classifier_user_message"}],
                "result": "left_response",
            }], "next": {"kind": "stop"}},
            "right_call": {"calls": [{
                "model": "source_mock", "template": contract["system"],
                "arguments": [{"value": "classifier_user_message"}],
                "result": "right_response",
            }], "next": {"kind": "stop"}},
        },
        "entry": "entry",
    }


def _load_study(path: Path) -> tuple[bytes, dict[str, Any]]:
    if path.stat().st_size > MAX_JSON_BYTES:
        raise BridgeError("source study artifact exceeds byte cap")
    raw = path.read_bytes()
    if _sha(raw) != SOURCE_STUDY_SHA256:
        raise BridgeError("source study artifact hash differs from root-verified reproduction")
    try:
        report = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BridgeError(f"invalid source study JSON: {error}") from error
    if not isinstance(report, dict) or report.get("format") != "orchlang-incident-triage-source-study":
        raise BridgeError("unexpected source study artifact format")
    return raw, report


def _independent_redact(text: str, redactor: dict[str, Any]) -> str:
    patterns = redactor["patterns"]
    replacements = redactor["replacements"]
    text = re.sub(patterns["EMAIL_RE"], replacements["EMAIL_RE"], text)
    text = re.sub(patterns["PHONE_RE"], replacements["PHONE_RE"], text)
    return re.sub(patterns["NI_NUMBER_RE"], replacements["NI_NUMBER_RE"], text)


def check_study_projection(report: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Check source-study request rows against the AST-derived first-call formula.

    This validates finite captured cases; the graph proof is generated without
    consulting these rows.
    """
    cases_list = report.get("cases")
    if not isinstance(cases_list, list) or len(cases_list) != 22:
        raise BridgeError("source study must contain the pinned 22 cases")
    cases: dict[str, dict[str, Any]] = {}
    for case in cases_list:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
            raise BridgeError("malformed source study case")
        case_id = case["case_id"]
        if case_id in cases:
            raise BridgeError("duplicate source case id")
        cases[case_id] = case
        input_row = case.get("input")
        if not isinstance(input_row, dict) or not isinstance(input_row.get("text"), str):
            raise BridgeError(f"source case {case_id} has no text input")
        raw_text = input_row["text"]
        if not 10 <= len(raw_text) <= 4000:
            raise BridgeError(f"source case {case_id} violates IncidentReport.text length contract")
        redacted = _independent_redact(raw_text, contract["redactor"])
        user = _literal_message(CLASSIFIER_PREFIX + redacted)
        calls = case.get("calls")
        if not isinstance(calls, list) or not calls or not isinstance(calls[0], dict):
            raise BridgeError(f"source case {case_id} has no first completion")
        first = calls[0]
        if first.get("system") != contract["system"] or first.get("user") != user:
            raise BridgeError(f"source case {case_id} first completion differs from AST-derived request")
        if case.get("source_redacted_text") != redacted:
            raise BridgeError(f"source case {case_id} redaction differs from AST-derived helper contract")

    expected_ids = {"pii_email_a", "pii_email_b", "pii_phone_a", "pii_phone_b",
                    "pii_national_insurance_a", "pii_national_insurance_b",
                    "retry_email_a", "retry_email_b", "public_text_a", "public_text_b",
                    "unlisted_name_a", "unlisted_name_b", "mock_marker_absent",
                    "mock_marker_present", "unknown_site_route", "pii_presence_absent",
                    "pii_presence_present", "pii_count_one", "pii_count_two",
                    "pii_type_email", "pii_type_phone", "upstream_default_mock"}
    if set(cases) != expected_ids:
        raise BridgeError("source study case identifiers differ")
    equal_pairs = different_pairs = 0
    pair_checks = []
    for left_id, right_id in sorted(EXPECTED_PAIRS):
        left, right = cases[left_id], cases[right_id]
        left_input, right_input = left["input"], right["input"]
        public_fields = ("incident_id", "site", "reported_by", "thread_id")
        same_metadata = all(left_input.get(name) == right_input.get(name) for name in public_fields)
        if not same_metadata:
            raise BridgeError(f"paired cases {left_id}/{right_id} change public metadata")
        same_projection = left["source_redacted_text"] == right["source_redacted_text"]
        first_equal = (left["calls"][0]["system"], left["calls"][0]["user"]) == \
            (right["calls"][0]["system"], right["calls"][0]["user"])
        if same_projection != first_equal:
            raise BridgeError(f"pair {left_id}/{right_id} violates the exact redaction quotient")
        pair_checks.append({
            "left": left_id, "right": right_id,
            "same_public_metadata": True,
            "same_redacted_text": same_projection,
            "same_first_classifier_request": first_equal,
            "captured_source_calls_agree": True,
        })
        if same_projection:
            equal_pairs += 1
        else:
            different_pairs += 1
    return {
        "source_case_count": len(cases),
        "source_pair_count": len(pair_checks),
        "equal_projection_pairs": equal_pairs,
        "different_projection_pairs": different_pairs,
        "pair_checks": pair_checks,
        "finite_source_corpus_only": True,
    }


def _authored_mutation_probes(source_files: dict[str, bytes]) -> list[dict[str, Any]]:
    probes: list[tuple[str, str, dict[str, bytes], str, str]] = []

    classify_files = dict(source_files)
    marker = b"clean_text = redact_pii(incident.text)"
    raw_classify = b"clean_text = incident.text"
    if classify_files["src/triage/graph.py"].count(marker) != 1:
        raise BridgeError("cannot construct classifier raw-text mutation")
    classify_files["src/triage/graph.py"] = classify_files["src/triage/graph.py"].replace(marker, raw_classify, 1)
    probes.append((
        "AUTHORED-CLASSIFY-RAW-BYPASS",
        "replace the classifier's redacted source with incident.text",
        classify_files,
        "classifier request may contain raw incident text",
        "classify.clean_text must be exactly redact_pii(validated_incident.text)",
    ))

    repair_files = dict(source_files)
    graph_bytes = repair_files["src/triage/graph.py"]
    call_marker = b"f\"INCIDENT REPORT: {clean_text}\", Classification,\n            )"
    call_mutation = b"f\"INCIDENT REPORT: {clean_text}\", Classification,\n                raw_text=incident.text,\n            )"
    helper_bytes = repair_files["src/triage/guardrails.py"]
    signature_marker = b"schema: type[T]) -> T:"
    signature_mutation = b"schema: type[T], raw_text: str | None = None) -> T:"
    repair_marker = b"f\"Respond again with ONLY valid JSON for the schema.\""
    repair_mutation = b"f\"Raw incident: {raw_text}\\n\"\n            f\"Respond again with ONLY valid JSON for the schema.\""
    repair_start = helper_bytes.index(b"def call_with_repair")
    repair_head = helper_bytes[:repair_start]
    repair_body = helper_bytes[repair_start:]
    if graph_bytes.count(call_marker) != 1 or repair_body.count(signature_marker) != 1 \
            or helper_bytes.count(repair_marker) != 1:
        raise BridgeError("cannot construct repair raw-text mutation")
    repair_files["src/triage/graph.py"] = graph_bytes.replace(call_marker, call_mutation, 1)
    repair_files["src/triage/guardrails.py"] = repair_head + repair_body.replace(
        signature_marker, signature_mutation, 1
    ).replace(repair_marker, repair_mutation, 1)
    probes.append((
        "AUTHORED-REPAIR-RAW-BYPASS",
        "add raw_text to call_with_repair and interpolate it only in the validation-repair request",
        repair_files,
        "repair prompt may contain raw incident text after an initial schema failure",
        "repair helper accepts only system/user/schema and formats only original user plus SchemaViolation",
    ))

    draft_files = dict(source_files)
    draft_bytes = draft_files["src/triage/graph.py"]
    draft_marker = b"f\"summary: {state['classification']['summary']}\""
    draft_mutation = b"f\"summary: {state['classification']['summary']}\\n\"\n            f\"raw: {state['incident']['text']}\""
    if draft_bytes.count(draft_marker) != 1:
        raise BridgeError("cannot construct draft raw-text mutation")
    draft_files["src/triage/graph.py"] = draft_bytes.replace(draft_marker, draft_mutation, 1)
    probes.append((
        "AUTHORED-DRAFT-RAW-BYPASS",
        "append state['incident']['text'] to the action-drafting request",
        draft_files,
        "draft request may contain raw incident text after classification",
        "draft prompt depends only on Classification.category, Priority.level, Classification.summary",
    ))

    outcomes = []
    for mutation_id, mutation, mutated, expected_risk, obligation in probes:
        try:
            extract_source_contract(mutated)
        except BridgeError as error:
            outcomes.append({
                "id": mutation_id,
                "mutation": mutation,
                "status": "rejected_by_source_ast_contract",
                "rejection_basis": "semantic_AST_dependency_check",
                "upstream_modified": False,
                "expected_risk": expected_risk,
                "checked_obligation": obligation,
                "diagnostic": str(error),
            })
        else:
            raise BridgeError(f"authored mutation unexpectedly accepted: {mutation_id}")
    return outcomes


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(root), *args],
                                       stderr=subprocess.STDOUT, text=True).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise BridgeError(f"git {' '.join(args)} failed: {getattr(error, 'output', '') or error}") from error


def load_verified_source(root: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    root = root.resolve(strict=True)
    manifest_raw = MANIFEST_PATH.read_bytes()
    manifest = json.loads(manifest_raw.decode("utf-8"))
    if manifest.get("commit") != "c08f710acfeefe233329df613fe8358eaac5f350" \
            or manifest.get("git_tree") != "2f6e2058052e4cccd48ae41230d9d5dd1ba5aa02":
        raise BridgeError("local upstream manifest identity differs from the source pin")
    if (root / ".git").exists():
        if _git(root, "rev-parse", "HEAD") != manifest["commit"] \
                or _git(root, "rev-parse", "HEAD^{tree}") != manifest["git_tree"]:
            raise BridgeError("upstream commit/tree differs from source manifest")
        if _git(root, "status", "--porcelain", "--untracked-files=all"):
            raise BridgeError("upstream checkout must be clean")
    else:
        # The checked-in byte snapshot can be replayed without a clone or git
        # history. Verify every manifest member before accepting its declared
        # original commit/tree identity.
        for relative, expected in manifest["tracked_file_sha256"].items():
            try:
                observed = _sha((root / relative).read_bytes())
            except OSError as error:
                raise BridgeError(f"snapshot misses pinned file {relative}") from error
            if observed != expected:
                raise BridgeError(f"snapshot file differs from source manifest: {relative}")
    files: dict[str, bytes] = {}
    for relative in EXPECTED_SOURCE_FILES:
        raw = (root / relative).read_bytes()
        expected = manifest["tracked_file_sha256"].get(relative)
        if expected != _sha(raw):
            raise BridgeError(f"pinned source hash mismatch: {relative}")
        files[relative] = raw
    source = {
        "repository": manifest["repository"],
        "commit": manifest["commit"],
        "git_tree": manifest["git_tree"],
        "license": manifest["license"],
        "manifest_sha256": _sha(manifest_raw),
        "checked_source_files": {name: _sha(files[name]) for name in sorted(files)},
    }
    return files, source


def _load_graph_tools():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from audit.orchgraph import Graph, check
    from audit.replay_graph_certificate import replay
    return Graph, check, replay


def build_analysis(upstream: Path, study_path: Path, output_dir: Path) -> dict[str, Any]:
    files, source = load_verified_source(upstream)
    contract = extract_source_contract(files)
    mutation_probes = _authored_mutation_probes(files)
    _, study = _load_study(study_path)
    finite_cases = check_study_projection(study, contract)
    runtime_provenance = {
        "python": study["harness"]["python"],
        "langgraph": study["harness"]["langgraph"],
        "pydantic": study["harness"]["pydantic"],
        "dependency_lock_sha256": study["harness"]["dependency_lock_sha256"],
        "provider": study["execution"]["provider"],
        "network_calls": study["execution"]["network_calls"],
        "outbound_provider_calls": study["execution"]["outbound_provider_calls"],
    }
    graph_doc = build_request_graph(contract, source_commit=source["commit"])
    graph_raw = _canonical(graph_doc)
    Graph, check, replay = _load_graph_tools()
    product = check(Graph(json.loads(graph_raw)), max_nodes=MAX_PRODUCT_NODES)
    if product.get("status") != "accepted":
        raise BridgeError(f"generated source request graph did not verify: {product.get('diagnostic')}")
    product["source_sha256"] = _sha(graph_raw)
    product["checker_sha256"] = _sha((ROOT / "audit" / "orchgraph.py").read_bytes())
    certificate_raw = _canonical(product)
    attestation = replay(graph_raw, certificate_raw)
    if attestation.get("status") != "verified":
        raise BridgeError("independent replay did not verify generated graph certificate")
    mapping = {
        "source_node": "classify",
        "source_file": "src/triage/graph.py",
        "source_operation_line": contract["request"]["source_call_line"],
        "source_operation": "call_with_repair(tracked, CLASSIFY_SYSTEM, f'INCIDENT REPORT: {redact_pii(incident.text)}', Classification)",
        "graph_self_composition_lanes": ["left_call", "right_call"],
        "graph_analysis_input": "classifier_user_message",
        "input_projection": "'INCIDENT REPORT: ' + redact_pii(IncidentReport.text)",
        "graph_template_equals_source_system": True,
        "graph_argument_equals_source_user_message": True,
        "self_composition_secret_selector_is_synthetic": True,
        "request_equivalence": "redact_pii(t_left) == redact_pii(t_right), with identical valid public metadata",
        "scope": "the OrchGraph certificate covers the exact first classifier system/user pair only",
    }
    result = {
        "format": "orchlang-incident-triage-source-analysis",
        "version": 1,
        "status": "generated; see independent source_analysis.attestation.json",
        "source": source,
        "source_ast_contract": contract,
        "source_to_graph_mapping": mapping,
        "graph": {
            "path": "classifier_request.graph.json",
            "sha256": _sha(graph_raw),
            "document": graph_doc,
            "certificate": {
                "path": "classifier_request.certificate.json",
                "sha256": _sha(certificate_raw),
                "status": product["status"],
                "product_nodes": product["product_nodes"],
                "product_edges": product["product_edges"],
                "checker_sha256": product["checker_sha256"],
            },
            "independent_replay": attestation,
        },
        "source_study_projection": finite_cases,
        "runtime_provenance": runtime_provenance,
        "authored_mutation_probes": mutation_probes,
        "claim": "For this recognized pinned source version, equality of the exact ordered redactor output plus equality of valid public metadata/configuration, serialized fresh graph execution, and the shared complete outcome oracle implies equal pre-dispatch model request, source-estimated usage, error-route, node, and interrupt observations.",
        "not_claimed": [
            "machine-checked semantics for arbitrary Python or full LangGraph translation",
            "source provider output cap or provider usage receipt",
            "PII protection for marker presence, count, pattern type, non-matching values, or raw state/checkpoint storage",
            "provider-side billing or provider tokenization conformance",
            "real-provider behavior, upstream vulnerability, or universal PII coverage",
        ],
        "graph_output_cap_note": "The generated graph schema requires an output cap; the value 1 is adapter-only and is not sourced from or claimed for upstream MockLLM.",
        "accounting_note": "No source billing conformance is claimed: upstream estimates max(1, len(system + user) // 4) using Python code points, whereas OrchGraph uses ceil(UTF8 bytes / divisor) per template/argument fragment.",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "classifier_request.graph.json").write_bytes(graph_raw)
    (output_dir / "classifier_request.certificate.json").write_bytes(certificate_raw)
    (output_dir / "classifier_request.attestation.json").write_bytes(_canonical(attestation))
    (output_dir / "source_analysis.json").write_bytes(_canonical(result))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from integrations.incident_triage.source_analysis.replay_projection import replay_projection
    source_attestation = replay_projection(
        output_dir / "source_analysis.json", upstream, study_path,
    )
    if source_attestation.get("status") != "verified":
        raise BridgeError(f"independent source projection replay failed: {source_attestation.get('diagnostics')}")
    (output_dir / "source_analysis.attestation.json").write_bytes(_canonical(source_attestation))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path,
                        default=Path(os.environ.get("INCIDENT_TRIAGE_UPSTREAM", DEFAULT_UPSTREAM)))
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    parser.add_argument("--output-dir", type=Path, default=HERE / "artifacts")
    args = parser.parse_args(argv)
    try:
        report = build_analysis(args.upstream, args.study, args.output_dir)
    except (BridgeError, OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print(f"incident-triage source analysis failed closed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "verified", "source": report["source"],
                      "graph": report["graph"]["certificate"],
                      "source_study_projection": {
                          k: report["source_study_projection"][k]
                          for k in ("source_case_count", "source_pair_count",
                                    "equal_projection_pairs", "different_projection_pairs")
                      }}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
