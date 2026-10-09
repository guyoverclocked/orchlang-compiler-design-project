#!/usr/bin/env python3
"""Independent standard-library replay for the pinned incident source bridge.

This checker recognizes a fixed upstream source version. It does not import
the source bridge, execute upstream Python, import LangGraph, or invoke a graph
producer. It independently binds source bytes, rebuilds the declared AST
contract, replays the embedded OrchGraph certificate, and checks the finite
captured source-study projection. Its result is a source-specific replay
attestation, not a general Python translation proof.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INTEGRATION = HERE.parent
MANIFEST_PATH = INTEGRATION / "UPSTREAM_MANIFEST.json"
DEFAULT_STUDY = INTEGRATION / "results" / "source_study.json"
SOURCE_COMMIT = "c08f710acfeefe233329df613fe8358eaac5f350"
SOURCE_TREE = "2f6e2058052e4cccd48ae41230d9d5dd1ba5aa02"
SOURCE_REPOSITORY = "https://github.com/codewithkachi/agent-incident-triage"
SOURCE_LICENSE = "MIT"
SOURCE_STUDY_SHA256 = "3f10906bb8fdd2283c59b188863304ecb2431c662ca0be3c0a04aaadfa05e9ab"
MANIFEST_SHA256 = "38e804b6470ad0c58f0da526f71ab39b7a7ad5a4a241c0e156569ba0ad203500"
MAX_FILE_BYTES = 16 * 1024 * 1024
CLASSIFIER_PREFIX = "INCIDENT REPORT: "

PINNED_FILE_SHA256 = {
    "src/triage/graph.py": "0fc931ff7edb64cc26d9eb8b7aa8ec3b05bcefbb667641a30610456ddde4138b",
    "src/triage/guardrails.py": "94d086fb139eff7c7b3bf7ca0b49055c4a7b0a13509913ca855fb6a04a110b5d",
    "src/triage/models.py": "23987632467f7475efa7964c8d83157c9e4a9267f03df494a7a2f5a9da8816be",
    "src/triage/costs.py": "f1393f1ceada49308d689b47ed736fb864a872ca31bc6bbe7e84265be288d92f",
    "src/triage/config.py": "54400bc276090cea7bbf9eed4322b988b5ef73652ce1d343897caac7c62b37aa",
    "src/triage/llm.py": "2a92f378b51921e312b678ad3aab5a6d7aadd5a7f96d5cc641488e7833ce710a",
    "data/sites.json": "51d9b3fa3c1711e85e26708ebd59b43320d191c044a5e11d2893cb5964819d98",
}
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


class ProjectionReplayError(ValueError):
    """The report or its source binding fails the independent replay."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _portable_ast(value: Any) -> Any:
    """Version-stable semantic AST fields, excluding empty optional fields."""
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


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ProjectionReplayError(f"duplicate JSON key {key!r}")
        obj[key] = value
    return obj


def _read_json(path: Path, label: str) -> tuple[bytes, Any]:
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ProjectionReplayError(f"{label} exceeds {MAX_FILE_BYTES} bytes")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        if isinstance(error, ProjectionReplayError):
            raise
        raise ProjectionReplayError(f"invalid {label} JSON: {error}") from error
    return raw, value


def _source_tree(root: Path) -> tuple[dict[str, bytes], dict[str, Any]]:
    try:
        manifest_raw, manifest = _read_json(MANIFEST_PATH, "upstream manifest")
    except OSError as error:
        raise ProjectionReplayError(f"cannot read local upstream manifest: {error}") from error
    if _sha(manifest_raw) != MANIFEST_SHA256:
        raise ProjectionReplayError("local upstream manifest digest differs from the replay pin")
    if not isinstance(manifest, dict) or manifest.get("format") != "orchlang-upstream-source-manifest" \
            or manifest.get("version") != 1 or manifest.get("commit") != SOURCE_COMMIT \
            or manifest.get("git_tree") != SOURCE_TREE or manifest.get("repository") != SOURCE_REPOSITORY \
            or manifest.get("license") != SOURCE_LICENSE:
        raise ProjectionReplayError("upstream manifest identity differs from the replay pin")
    hashes = manifest.get("tracked_file_sha256")
    if not isinstance(hashes, dict):
        raise ProjectionReplayError("manifest tracked_file_sha256 must be an object")
    files: dict[str, bytes] = {}
    root = root.resolve(strict=True)
    for relative, expected in PINNED_FILE_SHA256.items():
        if hashes.get(relative) != expected:
            raise ProjectionReplayError(f"manifest file pin differs: {relative}")
        path = root / relative
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise ProjectionReplayError(f"cannot read source file {relative}: {error}") from error
        if len(raw) > MAX_FILE_BYTES or _sha(raw) != expected:
            raise ProjectionReplayError(f"pinned source bytes differ: {relative}")
        files[relative] = raw
    source = {
        "repository": SOURCE_REPOSITORY,
        "commit": SOURCE_COMMIT,
        "git_tree": SOURCE_TREE,
        "license": SOURCE_LICENSE,
        "manifest_sha256": MANIFEST_SHA256,
        "checked_source_files": {name: _sha(files[name]) for name in sorted(files)},
    }
    return files, source


def _parse(files: dict[str, bytes], relative: str) -> ast.Module:
    try:
        return ast.parse(files[relative].decode("utf-8"), filename=relative)
    except (UnicodeDecodeError, SyntaxError, ValueError, RecursionError) as error:
        raise ProjectionReplayError(f"cannot parse pinned source {relative}: {error}") from error


def _find_fn(tree: ast.AST, name: str) -> ast.FunctionDef:
    found = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(found) != 1:
        raise ProjectionReplayError(f"expected one pinned synchronous helper {name!r}")
    return found[0]


def _assignments(tree: ast.Module) -> dict[str, ast.AST]:
    values: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            values[node.targets[0].id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            values[node.target.id] = node.value
    return values


def _literal(node: ast.AST, label: str) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError) as error:
        raise ProjectionReplayError(f"{label} must be a literal") from error


def _ast_fingerprints(trees: dict[str, ast.Module]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for name, expected in HELPER_AST_SHA256.items():
        module, function = name.split(":", 1)
        digest = _sha(json.dumps(_portable_ast(_find_fn(trees[module], function)), ensure_ascii=False,
                                 sort_keys=True, separators=(",", ":")).encode("utf-8"))
        if digest != expected:
            raise ProjectionReplayError(f"recognized source helper AST differs: {name}")
        observed[name] = digest
    return observed


def _model_contract(tree: ast.Module, name: str) -> dict[str, Any]:
    found = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name]
    if len(found) != 1:
        raise ProjectionReplayError(f"expected model {name}")
    aliases = {
        node.targets[0].id: node.value for node in tree.body
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
    }
    result: dict[str, Any] = {}
    for field in found[0].body:
        if not isinstance(field, ast.AnnAssign) or not isinstance(field.target, ast.Name):
            continue
        value: dict[str, Any] = {"type": ast.unparse(field.annotation)}
        if isinstance(field.annotation, ast.Name) and field.annotation.id in aliases:
            value["type"] = ast.unparse(aliases[field.annotation.id])
        if isinstance(field.value, ast.Call) and ast.unparse(field.value.func) == "Field":
            for kw in field.value.keywords:
                value[kw.arg] = _literal(kw.value, f"{name}.{field.target.id}.{kw.arg}")
        result[field.target.id] = value
    return result


def _redactor_contract(tree: ast.Module) -> dict[str, Any]:
    values = _assignments(tree)
    patterns: dict[str, str] = {}
    for name in ("EMAIL_RE", "PHONE_RE", "NI_NUMBER_RE"):
        call = values.get(name)
        if not isinstance(call, ast.Call) or ast.unparse(call.func) != "re.compile" or len(call.args) != 1:
            raise ProjectionReplayError(f"redactor regex declaration changed: {name}")
        patterns[name] = _literal(call.args[0], name)
    fn = _find_fn(tree, "redact_pii")
    positions = ("EMAIL_RE", "PHONE_RE", "NI_NUMBER_RE")
    replacements = ("[EMAIL]", "[PHONE]", "[NI-NUMBER]")
    for index, (pattern, replacement) in enumerate(zip(positions, replacements)):
        statement = fn.body[index]
        expression = statement.value if isinstance(statement, (ast.Assign, ast.Return)) else None
        if not isinstance(expression, ast.Call) or ast.unparse(expression.func) != f"{pattern}.sub" \
                or len(expression.args) != 2 or _literal(expression.args[0], "redactor replacement") != replacement:
            raise ProjectionReplayError("ordered redactor function body changed")
    return {
        "function": "triage.guardrails.redact_pii",
        "source_line": fn.lineno,
        "order": list(positions),
        "patterns": patterns,
        "replacements": dict(zip(positions, replacements)),
        "contract": "deterministic ordered Python re.sub calls on one text value",
    }


def _source_control(build: ast.FunctionDef) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    entries: list[str] = []
    interrupts: list[str] = []
    for node in ast.walk(build):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) \
                or not isinstance(node.func.value, ast.Name) or node.func.value.id != "graph":
            continue
        if node.func.attr == "add_node":
            if len(node.args) != 2:
                raise ProjectionReplayError("source add_node call changed")
            name = _literal(node.args[0], "node name")
            function = node.args[1].id if isinstance(node.args[1], ast.Name) else ast.unparse(node.args[1])
            nodes.append({"name": name, "function": function, "line": node.lineno})
        elif node.func.attr == "add_edge":
            if len(node.args) != 2:
                raise ProjectionReplayError("source add_edge call changed")
            source = _literal(node.args[0], "edge source")
            target = "END" if isinstance(node.args[1], ast.Name) and node.args[1].id == "END" else _literal(node.args[1], "edge target")
            edges.append({"from": source, "to": target, "kind": "unconditional", "line": node.lineno})
        elif node.func.attr == "add_conditional_edges":
            if len(node.args) != 2 or ast.unparse(node.args[1].func) != "route_after" or len(node.args[1].args) != 1:
                raise ProjectionReplayError("source conditional route changed")
            source = _literal(node.args[0], "route source")
            key = _literal(node.args[1].args[0], "route target")
            edges.append({"from": source, "to": {"on_error": "human_review", "otherwise": key},
                          "kind": "conditional", "line": node.lineno})
        elif node.func.attr == "set_entry_point":
            entries.append(_literal(node.args[0], "entry node"))
        elif node.func.attr == "compile":
            for kw in node.keywords:
                if kw.arg == "interrupt_before":
                    interrupts.extend(_literal(kw.value, "interrupt_before"))
    if {row["name"] for row in nodes} != {"classify", "enrich", "prioritise", "draft", "dispatch", "human_review"} \
            or set(entries) != {"classify"} or interrupts != ["dispatch"]:
        raise ProjectionReplayError("source StateGraph node/entry/interrupt set changed")
    edge_targets = {(row["from"], row["kind"], row["to"].get("otherwise") if isinstance(row["to"], dict) else row["to"])
                    for row in edges}
    expected_edges = {
        ("classify", "conditional", "enrich"),
        ("enrich", "conditional", "prioritise"),
        ("prioritise", "unconditional", "draft"),
        ("draft", "conditional", "dispatch"),
        ("dispatch", "unconditional", "END"),
        ("human_review", "unconditional", "END"),
    }
    if edge_targets != expected_edges or len(edges) != len(expected_edges):
        raise ProjectionReplayError("source StateGraph edge set changed")
    return {
        "source_entry": "classify",
        "nodes": sorted(nodes, key=lambda item: item["line"]),
        "edges": sorted(edges, key=lambda item: item["line"]),
        "error_route": "human_review",
        "interrupt_before": interrupts,
        "checked_from_ast": True,
    }


def _expected_source_contract(files: dict[str, bytes]) -> dict[str, Any]:
    trees = {path.rsplit("/", 1)[-1]: _parse(files, path) for path in PINNED_FILE_SHA256 if path.endswith(".py")}
    helper_hashes = _ast_fingerprints(trees)
    graph = trees["graph.py"]
    guard = trees["guardrails.py"]
    models = trees["models.py"]
    costs = trees["costs.py"]
    config_tree = trees["config.py"]
    build = _find_fn(graph, "build_graph")
    classify = _find_fn(build, "classify")
    repair_fn = _find_fn(guard, "call_with_repair")
    parse_fn = _find_fn(guard, "parse_structured")
    record_fn = _find_fn(costs, "record")
    total_fn = _find_fn(costs, "total_usd")
    over_fn = _find_fn(costs, "over_budget")
    wrapper_fn = _find_fn(costs, "complete")
    enrich_fn = _find_fn(build, "enrich")
    priority_fn = _find_fn(build, "prioritise")
    draft_fn = _find_fn(build, "draft")
    route_fn = _find_fn(build, "route_after")
    redact = _redactor_contract(guard)

    graph_assign = _assignments(graph)
    system = _literal(graph_assign["CLASSIFY_SYSTEM"], "CLASSIFY_SYSTEM")
    actions_system = _literal(graph_assign["ACTIONS_SYSTEM"], "ACTIONS_SYSTEM")
    incident = _model_contract(models, "IncidentReport")
    expected_incident = {"incident_id": {"type": "str"}, "site": {"type": "str"},
                         "reported_by": {"type": "str"}, "text": {"type": "str", "min_length": 10, "max_length": 4000}}
    if incident != expected_incident:
        raise ProjectionReplayError("IncidentReport model fields differ from the source contract")
    classification = _model_contract(models, "Classification")
    expected_classification = {
        "category": {"type": "Literal['physical_security', 'cyber', 'safety', 'operational', 'environmental']"},
        "severity": {"type": "Literal['low', 'medium', 'high', 'critical']"},
        "summary": {"type": "str", "max_length": 300},
        "people_at_risk": {"type": "bool"},
    }
    if classification != expected_classification:
        raise ProjectionReplayError("Classification schema differs from the recognized source contract")
    model_contracts = {name: _model_contract(models, name) for name in ("Classification", "Enrichment", "Priority", "TriageReport", "NodeCost")}

    classify_calls = [n for n in ast.walk(classify) if isinstance(n, ast.Call) and ast.unparse(n.func) == "call_with_repair"]
    if len(classify_calls) != 1 or len(classify_calls[0].args) != 4 or classify_calls[0].keywords:
        raise ProjectionReplayError("classifier source call shape changed")
    clean_assignments = [n.value for n in ast.walk(classify) if isinstance(n, ast.Assign) and len(n.targets) == 1
                         and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "clean_text"]
    if len(clean_assignments) != 1 or ast.unparse(clean_assignments[0]) != "redact_pii(incident.text)":
        raise ProjectionReplayError("classifier source fails redactor dependency obligation")
    repair_args = [arg.arg for arg in repair_fn.args.args]
    repair_value = next(n.value for n in ast.walk(repair_fn) if isinstance(n, ast.Assign) and len(n.targets) == 1
                        and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "repair_user")
    repair_expected = ast.parse(
        "(f'{user}\\n\\nYour previous response failed validation with:\\n{exc}\\n' "
        "f'Respond again with ONLY valid JSON for the schema.')", mode="eval"
    ).body
    if repair_args != ["llm", "system", "user", "schema"] \
            or not _same_ast(repair_value, repair_expected):
        raise ProjectionReplayError("repair helper fails exact input/error dependency obligation")
    call = classify_calls[0]
    prompt_summary = re.search(r"\"summary\": string \(max (\d+) chars\)", system)
    system_schema_max = int(prompt_summary.group(1)) if prompt_summary else None
    schema_max = classification["summary"].get("max_length")
    request = {
        "source_node": "classify",
        "source_call_line": call.lineno,
        "source_call_function": "call_with_repair",
        "source_call_phase": "first completion only",
        "system_symbol": "CLASSIFY_SYSTEM",
        "system": system,
        "user_expression": {"kind": "fstring", "prefix": CLASSIFIER_PREFIX,
                            "value": {"kind": "redact_pii", "argument": "IncidentReport.text"}},
        "exact_message_pair": {"system": system, "user_prefix": CLASSIFIER_PREFIX,
                               "dynamic_user_value": "redact_pii(incident.text)"},
        "source_helpers": ["IncidentReport.model_validate", "redact_pii", "call_with_repair"],
        "excluded_helper_phase": "the optional repair completion after SchemaViolation",
        "classification_prompt_summary_max": system_schema_max,
        "classification_schema_summary_max": schema_max,
    }
    estimator_fn = _find_fn(costs, "estimate_tokens")
    estimate_body = _portable_ast(estimator_fn.body[-1].value)
    expected_expr = _portable_ast(ast.parse("max(1, len(text) // 4)", mode="eval").body)
    if estimate_body != expected_expr:
        raise ProjectionReplayError("source estimator expression differs")
    estimator = {"function": "triage.costs.estimate_tokens", "expression": "max(1, len(text) // 4)",
                 "length_unit": "Python Unicode code points", "source_line": estimator_fn.lineno,
                 "not_equivalent_to_graph_accounting": "OrchGraph estimates ceil(UTF8-bytes / divisor) per template/argument fragment"}

    expected_draft_prompt = ast.parse(
        "(f\"category: {state['classification']['category']}\\n\" "
        "f\"priority: {state['priority']['level']}\\n\" "
        "f\"summary: {state['classification']['summary']}\")", mode="eval"
    ).body
    actual_draft_prompt = next(n.value for n in ast.walk(draft_fn) if isinstance(n, ast.Assign) and len(n.targets) == 1
                               and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "prompt")
    if not _same_ast(actual_draft_prompt, expected_draft_prompt):
        raise ProjectionReplayError("draft prompt fails source-derived dependency obligation")

    control = _source_control(build)
    config_assign = _assignments(config_tree)
    try:
        priority_matrix = ast.literal_eval(config_assign["PRIORITY_MATRIX"])
        pricing = ast.literal_eval(config_assign["PRICING"])
        max_cost = ast.literal_eval(config_assign["MAX_COST_PER_INCIDENT_USD"])
    except (ValueError, TypeError, KeyError) as error:
        raise ProjectionReplayError("priority/pricing/budget config is not literal") from error
    if pricing != {"gpt-4o-mini": {"input": 0.15, "output": 0.60}, "mock": {"input": 0.0, "output": 0.0}} or max_cost != 0.05:
        raise ProjectionReplayError("pricing or budget config differs")
    try:
        sites = json.loads(files["data/sites.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProjectionReplayError("site registry JSON is invalid") from error
    site_hash = _sha(files["data/sites.json"])
    hashes = {name: _sha(files[name]) for name in sorted(files)}
    line_map = {
        "classify": {"file": "src/triage/graph.py", "line": _find_fn(build, "classify").lineno},
        "enrich": {"file": "src/triage/graph.py", "line": enrich_fn.lineno},
        "prioritise": {"file": "src/triage/graph.py", "line": priority_fn.lineno},
        "draft": {"file": "src/triage/graph.py", "line": draft_fn.lineno},
        "route_after": {"file": "src/triage/graph.py", "line": route_fn.lineno},
        "redact_pii": {"file": "src/triage/guardrails.py", "line": redact["source_line"]},
        "parse_structured": {"file": "src/triage/guardrails.py", "line": parse_fn.lineno},
        "call_with_repair": {"file": "src/triage/guardrails.py", "line": repair_fn.lineno},
        "estimate_tokens": {"file": "src/triage/costs.py", "line": estimator_fn.lineno},
        "CostTracker.record": {"file": "src/triage/costs.py", "line": record_fn.lineno},
        "CostTracker.total_usd": {"file": "src/triage/costs.py", "line": total_fn.lineno},
        "CostTracker.over_budget": {"file": "src/triage/costs.py", "line": over_fn.lineno},
        "TrackingLLM.complete": {"file": "src/triage/costs.py", "line": wrapper_fn.lineno},
    }
    guardrails = {"function": "triage.guardrails.call_with_repair", "source_line": repair_fn.lineno,
                  "maximum_completions": 2,
                  "initial_call_line": next(n for n in ast.walk(repair_fn) if isinstance(n, ast.Call) and ast.unparse(n.func) == "llm.complete" and isinstance(n.args[1], ast.Name) and n.args[1].id == "user").lineno,
                  "repair_call_line": next(n for n in ast.walk(repair_fn) if isinstance(n, ast.Call) and ast.unparse(n.func) == "llm.complete" and isinstance(n.args[1], ast.Name) and n.args[1].id == "repair_user").lineno,
                  "repair_user_expression_is_formatted_from": ["user", "SchemaViolation text"]}
    repair_assignment = next(n for n in ast.walk(repair_fn) if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "repair_user")
    protocol = {
        "format": "orchlang-incident-triage-dependency-protocol", "version": 1,
        "source_files_sha256": hashes, "source_line_map": line_map,
        "recognized_helper_ast_sha256": helper_hashes,
        "input_relation": {
            "public_fields_equal": ["incident_id", "site", "reported_by", "thread_id"],
            "validity": {"model": "IncidentReport", "fields": incident,
                         "validation_precedes_classifier_try": True,
                         "invalid_input_behavior": "Pydantic validation may raise before the graph's SchemaViolation route"},
            "secret_relation": "redact_pii(text_left) == redact_pii(text_right)",
            "redactor": redact,
            "release_scope": "only exact equality of the ordered sanitizer output is released; residual text is assumed public under this pair relation",
            "not_released": ["PII marker presence", "PII count", "PII pattern type", "unmatched sensitive text", "raw state/checkpoint storage"],
        },
        "classification": {
            "request": request["exact_message_pair"], "response_schema": classification,
            "prompt_schema_note": {"prompt_summary_max_chars": system_schema_max,
                                   "validated_summary_max_chars": schema_max,
                                   "mismatch": system_schema_max != schema_max},
            "typed_result_dependencies": {
                "category": ["enrich.related_procedures", "draft.user.category", "report payload"],
                "severity": ["priority matrix", "priority rationale", "report payload"],
                "summary": ["draft.user.summary", "report payload"],
                "people_at_risk": ["priority matrix", "priority rationale", "report payload"],
            },
        },
        "validation_and_repair": {
            "parser_contract": {"strip_raw_response": True,
                                "fence_condition": "cleaned.startswith('```')",
                                "fence_regex": r"^```(?:json)?\s*|\s*```$",
                                "fence_flags": ["re.S"], "decoder": "json.loads(cleaned)",
                                "validator": "schema.model_validate(decoded)",
                                "wrapped_errors": ["json.JSONDecodeError", "pydantic.ValidationError"],
                                "wrapped_as": "SchemaViolation(str(error))"},
            "parser_source_line": parse_fn.lineno,
            "repair": {**guardrails, "source_expression": ast.unparse(repair_assignment.value),
                       "exact_user_formula": "original user + '\\n\\nYour previous response failed validation with:\\n' + str(SchemaViolation) + '\\nRespond again with ONLY valid JSON for the schema.'",
                       "same_complete_oracle_required_for": ["initial completion", "optional repair completion"],
                       "failure_effect": "a second SchemaViolation becomes classify error; classify returns no costs field, so request/usage trace must be read from the tracker or wrapper",
                       "failure_error_format": "classification failed schema validation: {exc}"},
        },
        "deterministic_dependencies": {
            "enrichment": {"operation": "lookup valid incident.site in the bound JSON registry; use classification.category to select procedures; unknown key sets error",
                           "source_line": enrich_fn.lineno, "registry_sha256": site_hash, "registry": sites,
                           "fields": model_contracts["Enrichment"], "dependencies": ["incident.site", "classification.category", "registry bytes"],
                           "unknown_site_route": "human_review before priority/draft",
                           "unknown_site_error_format": "unknown site {incident.site!r}"},
            "priority": {"source_line": priority_fn.lineno,
                         "matrix": [{"severity": k[0], "people_at_risk": k[1], "level": v[0], "response_sla_minutes": v[1]} for k, v in sorted(priority_matrix.items())],
                         "critical_site_rule": "if site_criticality == 'critical' and level != 'P1', decrement P number and set SLA from {P1:15,P2:60,P3:240}",
                         "rationale_fields": ["severity", "people_at_risk", "site_criticality"],
                         "fields": model_contracts["Priority"],
                         "dependencies": ["classification.severity", "classification.people_at_risk", "enrichment.site_criticality", "config.PRIORITY_MATRIX"]},
        },
        "usage_and_budget": {
            "estimator": estimator,
            "record_formula": {"input_tokens": "max(1, len(system + user) // 4)", "output_tokens": "max(1, len(response) // 4)",
                               "length_unit": "Python Unicode code points",
                               "cost_usd": "round((input_tokens * pricing.input + output_tokens * pricing.output) / 1_000_000, 6)",
                               "pricing_lookup": "PRICING.get(model_name, PRICING['mock'])", "source_line": record_fn.lineno},
            "total_formula": "round(sum(per_call_rounded_cost_usd), 6)",
            "budget_predicate": "rounded_total_usd > MAX_COST_PER_INCIDENT_USD", "total_source_line": total_fn.lineno,
            "numeric_semantics": "Python float arithmetic and built-in round at six decimal places for each row and total",
            "budget_usd": max_cost,
            "budget_guard": "draft checks tracker.over_budget before issuing ACTIONS_SYSTEM request; true returns error and routes to human_review",
            "budget_guard_source_line": draft_fn.lineno, "over_budget_source_line": over_fn.lineno,
            "pricing": pricing, "mock_price": 0.0,
            "observer": "source tracker/wrapper call rows, including classifier failures whose returned state omits costs",
            "not_provider_billing": True,
        },
        "draft_and_gate": {
            "draft_source_line": draft_fn.lineno, "system": actions_system,
            "user_template": "category: {classification.category}\\npriority: {priority.level}\\nsummary: {classification.summary}",
            "raw_incident_text_dependency": False,
            "response_handling": "JSON list parsing with a fixed fallback action on JSON/assertion failure; response content does not affect routing",
            "fallback_action": "Review incident manually; drafting agent returned invalid output",
            "actions_coercion_and_limit": "[str(action) for action in parsed_actions][:5]",
            "budget_error_format": "cost budget exceeded (${tracker.total_usd})",
            "report_fields": model_contracts["TriageReport"], "control": control,
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
            "fresh_graph_and_checkpointer_per_run": True, "serialized_nonconcurrent_invocations": True,
            "reason": "build_graph closes over mutable tracker/current_node; classify clears shared tracker.entries",
            "fixed_assets_config_dependency_versions_and_provider": True, "source_graph_topology": control,
            "terminal_scope": "all request, source-estimated usage, error-route, node and interrupt events through the pre-dispatch human gate",
        },
        "conditional_result": "equal exact redacted text plus equal valid public metadata/configuration and the shared complete outcome oracle yields equal pre-dispatch request/usage/route observations for this recognized source version",
        "trust_boundary": ["pinned source bytes and Python/Pydantic/LangGraph semantics", "the exact redactor is an approved release under the stated relation", "the shared complete outcome oracle premise", "serial fresh graph/tracker/checkpointer execution"],
        "excluded": ["generic Python-to-OrchGraph translation", "proof of sanitizer adequacy or general PII coverage", "checkpoint/full-state storage privacy", "external human decision or dispatch effects", "provider-side tokenization, usage receipts, currency charges, or output caps", "invalid Pydantic inputs, concurrent use of one graph, provider failures, or arbitrary source/config mutations", "source report payload equality beyond the dependencies needed for later requests and control"],
    }
    return {
        "system": system,
        "request": request,
        "redactor": redact,
        "incident_fields": incident,
        "control": control,
        "source_estimator": estimator,
        "source_provider_default": "mock",
        "source_mock_name": "mock",
        "source_budget_usd": max_cost,
        "source_scope": "pinned source, exact pre-dispatch request/usage/route dependencies under stated helper and oracle contracts",
        "dependency_protocol": protocol,
        "recognized_helper_ast_sha256": helper_hashes,
        "source_model_summary_mismatch": {"prompt_max_chars": system_schema_max, "schema_max_chars": schema_max,
                                           "mismatch": system_schema_max != schema_max},
    }


def _redact(text: str, contract: dict[str, Any]) -> str:
    for key in contract["order"]:
        text = re.sub(contract["patterns"][key], contract["replacements"][key], text)
    return text


def _verify_source_study(study: Any, contract: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(study, dict) or study.get("format") != "orchlang-incident-triage-source-study":
        raise ProjectionReplayError("source study format differs")
    rows = study.get("cases")
    if not isinstance(rows, list) or len(rows) != 22:
        raise ProjectionReplayError("source study must contain 22 fixed cases")
    cases: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("case_id"), str) or row["case_id"] in cases:
            raise ProjectionReplayError("malformed or duplicate source study case")
        case_id = row["case_id"]
        cases[case_id] = row
        input_row = row.get("input")
        if not isinstance(input_row, dict) or not isinstance(input_row.get("text"), str):
            raise ProjectionReplayError(f"source study input missing for {case_id}")
        text = input_row["text"]
        if not 10 <= len(text) <= 4000:
            raise ProjectionReplayError(f"source study text outside IncidentReport bound: {case_id}")
        sanitized = _redact(text, contract["redactor"])
        calls = row.get("calls")
        if not isinstance(calls, list) or not calls:
            raise ProjectionReplayError(f"source study call missing for {case_id}")
        first = calls[0]
        if first.get("system") != contract["system"] or first.get("user") != CLASSIFIER_PREFIX + sanitized \
                or row.get("source_redacted_text") != sanitized:
            raise ProjectionReplayError(f"source study first call fails AST-derived request formula: {case_id}")
    expected_ids = {"pii_email_a", "pii_email_b", "pii_phone_a", "pii_phone_b", "pii_national_insurance_a", "pii_national_insurance_b", "retry_email_a", "retry_email_b", "public_text_a", "public_text_b", "unlisted_name_a", "unlisted_name_b", "mock_marker_absent", "mock_marker_present", "unknown_site_route", "pii_presence_absent", "pii_presence_present", "pii_count_one", "pii_count_two", "pii_type_email", "pii_type_phone", "upstream_default_mock"}
    if set(cases) != expected_ids:
        raise ProjectionReplayError("source study identifiers differ")
    pairs = []
    equal = different = 0
    for left_id, right_id in sorted(EXPECTED_PAIRS):
        left, right = cases[left_id], cases[right_id]
        public = ("incident_id", "site", "reported_by", "thread_id")
        if any(left["input"].get(name) != right["input"].get(name) for name in public):
            raise ProjectionReplayError(f"source study pair changes public metadata: {left_id}/{right_id}")
        projection_equal = left["source_redacted_text"] == right["source_redacted_text"]
        call_equal = (left["calls"][0]["system"], left["calls"][0]["user"]) == (right["calls"][0]["system"], right["calls"][0]["user"])
        if projection_equal != call_equal:
            raise ProjectionReplayError(f"source study pair violates redaction quotient: {left_id}/{right_id}")
        pairs.append({"left": left_id, "right": right_id, "same_public_metadata": True,
                      "same_redacted_text": projection_equal,
                      "same_first_classifier_request": call_equal,
                      "captured_source_calls_agree": True})
        if projection_equal:
            equal += 1
        else:
            different += 1
    return {"source_case_count": 22, "source_pair_count": 11,
            "equal_projection_pairs": equal, "different_projection_pairs": different,
            "pair_checks": pairs, "finite_source_corpus_only": True}


def _verify_authored_mutations(files: dict[str, bytes], rows: Any) -> None:
    expected_meta = {
        "AUTHORED-CLASSIFY-RAW-BYPASS": (
            "classify.clean_text must be exactly redact_pii(validated_incident.text)",
            "replace the classifier's redacted source with incident.text",
        ),
        "AUTHORED-REPAIR-RAW-BYPASS": (
            "repair helper accepts only system/user/schema and formats only original user plus SchemaViolation",
            "add raw_text to call_with_repair and interpolate it only in the validation-repair request",
        ),
        "AUTHORED-DRAFT-RAW-BYPASS": (
            "draft prompt depends only on Classification.category, Priority.level, Classification.summary",
            "append state['incident']['text'] to the action-drafting request",
        ),
    }
    if not isinstance(rows, list) or len(rows) != len(expected_meta):
        raise ProjectionReplayError("all three authored mutation probes are required")
    by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
    if set(by_id) != set(expected_meta):
        raise ProjectionReplayError("authored mutation identifiers differ")

    base_graph = files["src/triage/graph.py"]
    base_guard = files["src/triage/guardrails.py"]

    classify_mutation = base_graph.replace(b"clean_text = redact_pii(incident.text)", b"clean_text = incident.text", 1)
    classify_tree = ast.parse(classify_mutation.decode("utf-8"))
    classify_fn = _find_fn(classify_tree, "classify")
    clean_value = next(n.value for n in ast.walk(classify_fn) if isinstance(n, ast.Assign) and len(n.targets) == 1
                       and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "clean_text")
    if ast.unparse(clean_value) == "redact_pii(incident.text)":
        raise ProjectionReplayError("classifier mutation did not violate its dependency obligation")

    call_pattern = b'f"INCIDENT REPORT: {clean_text}", Classification,\n            )'
    call_mutated = b'f"INCIDENT REPORT: {clean_text}", Classification,\n                raw_text=incident.text,\n            )'
    repair_start = base_guard.index(b"def call_with_repair")
    guard_head, guard_tail = base_guard[:repair_start], base_guard[repair_start:]
    sig_pattern = b"schema: type[T]) -> T:"
    sig_mutated = b"schema: type[T], raw_text: str | None = None) -> T:"
    repair_pattern = b'f"Respond again with ONLY valid JSON for the schema."'
    repair_mutated = b'f"Raw incident: {raw_text}\\n"\n            f"Respond again with ONLY valid JSON for the schema."'
    if base_graph.count(call_pattern) != 1 or guard_tail.count(sig_pattern) != 1 or base_guard.count(repair_pattern) != 1:
        raise ProjectionReplayError("cannot reproduce repair mutation from bound source")
    repair_graph = ast.parse(base_graph.replace(call_pattern, call_mutated, 1).decode("utf-8"))
    repair_guard = ast.parse((guard_head + guard_tail.replace(sig_pattern, sig_mutated, 1).replace(repair_pattern, repair_mutated, 1)).decode("utf-8"))
    repair_fn = _find_fn(repair_guard, "call_with_repair")
    repair_value = next(n.value for n in ast.walk(repair_fn) if isinstance(n, ast.Assign) and len(n.targets) == 1
                        and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "repair_user")
    if "raw_text" not in {arg.arg for arg in repair_fn.args.args} or "raw_text" not in ast.unparse(repair_value) \
            or not any(isinstance(n, ast.Call) and ast.unparse(n.func) == "call_with_repair" and n.keywords for n in ast.walk(repair_graph)):
        raise ProjectionReplayError("repair mutation did not add a raw-text repair dependency")

    draft_pattern = b'f"summary: {state[\'classification\'][\'summary\']}"'
    draft_mutated = b'f"summary: {state[\'classification\'][\'summary\']}\\n"\n            f"raw: {state[\'incident\'][\'text\']}"'
    if base_graph.count(draft_pattern) != 1:
        raise ProjectionReplayError("cannot reproduce draft mutation from bound source")
    draft_tree = ast.parse(base_graph.replace(draft_pattern, draft_mutated, 1).decode("utf-8"))
    draft_fn = _find_fn(draft_tree, "draft")
    draft_prompt = next(n.value for n in ast.walk(draft_fn) if isinstance(n, ast.Assign) and len(n.targets) == 1
                        and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "prompt")
    allowed_prompt = ast.parse(
        "(f\"category: {state['classification']['category']}\\n\" "
        "f\"priority: {state['priority']['level']}\\n\" "
        "f\"summary: {state['classification']['summary']}\")", mode="eval"
    ).body
    if _same_ast(draft_prompt, allowed_prompt):
        raise ProjectionReplayError("draft mutation did not violate its dependency obligation")

    for mutation_id, (obligation, mutation) in expected_meta.items():
        row = by_id[mutation_id]
        if row.get("mutation") != mutation or row.get("checked_obligation") != obligation \
                or row.get("status") != "rejected_by_source_ast_contract" \
                or row.get("rejection_basis") != "semantic_AST_dependency_check" \
                or row.get("upstream_modified") is not False:
            raise ProjectionReplayError(f"mutation ledger does not describe semantic rejection: {mutation_id}")


def _verify_graph_artifacts(report: dict[str, Any], report_path: Path) -> dict[str, Any]:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from audit.replay_graph_certificate import replay as replay_graph

    graph_meta = report.get("graph")
    if not isinstance(graph_meta, dict):
        raise ProjectionReplayError("graph metadata missing")
    graph_path = report_path.parent / "classifier_request.graph.json"
    cert_path = report_path.parent / "classifier_request.certificate.json"
    att_path = report_path.parent / "classifier_request.attestation.json"
    graph_raw = graph_path.read_bytes()
    cert_raw = cert_path.read_bytes()
    graph_att_raw = att_path.read_bytes()
    if any(len(raw) > MAX_FILE_BYTES for raw in (graph_raw, cert_raw, graph_att_raw)):
        raise ProjectionReplayError("graph certificate artifact exceeds byte cap")
    if _sha(graph_raw) != graph_meta.get("sha256") or _sha(cert_raw) != graph_meta.get("certificate", {}).get("sha256"):
        raise ProjectionReplayError("graph or certificate raw hash differs from report")
    graph_doc = json.loads(graph_raw.decode("utf-8"))
    cert_doc = json.loads(cert_raw.decode("utf-8"))
    if graph_doc != graph_meta.get("document"):
        raise ProjectionReplayError("embedded graph document differs from its raw artifact")
    mapping = report.get("source_to_graph_mapping")
    if not isinstance(mapping, dict) or mapping.get("graph_analysis_input") != "classifier_user_message" \
            or mapping.get("graph_template_equals_source_system") is not True \
            or mapping.get("graph_argument_equals_source_user_message") is not True \
            or mapping.get("self_composition_secret_selector_is_synthetic") is not True:
        raise ProjectionReplayError("source-to-graph classifier mapping is incomplete")
    if graph_doc.get("format") != "orchlang-request-graph" or graph_doc.get("version") != 1 \
            or set(graph_doc.get("states", {})) != {"entry", "left_call", "right_call"}:
        raise ProjectionReplayError("classifier graph shape differs from the source-slice graph")
    system = report["source_ast_contract"]["system"]
    left = graph_doc["states"]["left_call"]["calls"]
    right = graph_doc["states"]["right_call"]["calls"]
    if len(left) != 1 or len(right) != 1 \
            or {k: v for k, v in left[0].items() if k != "result"} != {k: v for k, v in right[0].items() if k != "result"} \
            or left[0].get("template") != system \
            or left[0].get("arguments") != [{"value": "classifier_user_message"}]:
        raise ProjectionReplayError("classifier graph call does not match the source system/user contract")
    replayed = replay_graph(graph_raw, cert_raw)
    if replayed.get("status") != "verified":
        raise ProjectionReplayError("independent OrchGraph certificate replay rejected")
    saved = json.loads(graph_att_raw.decode("utf-8"))
    if saved != replayed or graph_meta.get("independent_replay") != replayed:
        raise ProjectionReplayError("saved graph replay attestation differs from independent replay")
    certificate_meta = graph_meta.get("certificate", {})
    if certificate_meta.get("status") != "accepted" or certificate_meta.get("product_nodes") != cert_doc.get("product_nodes") \
            or certificate_meta.get("product_edges") != cert_doc.get("product_edges") \
            or certificate_meta.get("checker_sha256") != cert_doc.get("checker_sha256"):
        raise ProjectionReplayError("graph certificate summary differs from raw certificate")
    return {"graph_sha256": _sha(graph_raw), "certificate_sha256": _sha(cert_raw),
            "graph_product_nodes": cert_doc.get("product_nodes"),
            "graph_product_edges": cert_doc.get("product_edges"),
            "graph_replay_status": replayed.get("status")}


def replay_projection(report_path: Path, upstream_root: Path, study_path: Path | None = None) -> dict[str, Any]:
    checks: list[str] = []
    report_raw, report = _read_json(report_path, "source analysis report")
    if not isinstance(report, dict) or report.get("format") != "orchlang-incident-triage-source-analysis" \
            or report.get("version") != 1:
        raise ProjectionReplayError("unknown source analysis report format/version")
    report_keys = {"format", "version", "status", "source", "source_ast_contract", "source_to_graph_mapping",
                   "graph", "source_study_projection", "runtime_provenance", "authored_mutation_probes",
                   "claim", "not_claimed", "graph_output_cap_note", "accounting_note"}
    if set(report) != report_keys or report.get("status") != "generated; see independent source_analysis.attestation.json":
        raise ProjectionReplayError("source report fields/status differ from the recognized schema")
    files, source = _source_tree(upstream_root)
    if report.get("source") != source:
        raise ProjectionReplayError("report source identity or file hashes differ from pinned source")
    checks.append("pinned upstream selected file bytes and source manifest identity")

    expected_contract = _expected_source_contract(files)
    if report.get("source_ast_contract") != expected_contract:
        raise ProjectionReplayError("serialized AST contract does not match independent source re-extraction")
    checks.append("independent AST re-extraction of request, helper, schema, control, cost and gate dependencies")

    expected_claim = (
        "For this recognized pinned source version, equality of the exact ordered redactor output plus equality of valid "
        "public metadata/configuration, serialized fresh graph execution, and the shared complete outcome oracle implies "
        "equal pre-dispatch model request, source-estimated usage, error-route, node, and interrupt observations."
    )
    expected_not_claimed = [
        "machine-checked semantics for arbitrary Python or full LangGraph translation",
        "source provider output cap or provider usage receipt",
        "PII protection for marker presence, count, pattern type, non-matching values, or raw state/checkpoint storage",
        "provider-side billing or provider tokenization conformance",
        "real-provider behavior, upstream vulnerability, or universal PII coverage",
    ]
    expected_mapping = {
        "source_node": "classify", "source_file": "src/triage/graph.py",
        "source_operation_line": expected_contract["request"]["source_call_line"],
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
    if report.get("claim") != expected_claim or report.get("not_claimed") != expected_not_claimed \
            or report.get("source_to_graph_mapping") != expected_mapping \
            or report.get("graph_output_cap_note") != "The generated graph schema requires an output cap; the value 1 is adapter-only and is not sourced from or claimed for upstream MockLLM." \
            or report.get("accounting_note") != "No source billing conformance is claimed: upstream estimates max(1, len(system + user) // 4) using Python code points, whereas OrchGraph uses ceil(UTF8 bytes / divisor) per template/argument fragment.":
        raise ProjectionReplayError("claim, scope, mapping, or limitation declarations were altered")
    checks.append("serialized theorem claim, classifier-only lowering scope, and exclusions")

    protocol = expected_contract["dependency_protocol"]
    if protocol["classification"]["response_schema"].get("summary") != {"type": "str", "max_length": 300} \
            or "draft.user.summary" not in protocol["classification"]["typed_result_dependencies"]["summary"]:
        raise ProjectionReplayError("full Classification summary dependency was not preserved")
    if protocol["validation_and_repair"]["repair"]["maximum_completions"] != 2 \
            or protocol["usage_and_budget"]["record_formula"]["input_tokens"] != "max(1, len(system + user) // 4)" \
            or protocol["draft_and_gate"]["raw_incident_text_dependency"] is not False \
            or protocol["draft_and_gate"]["control"]["interrupt_before"] != ["dispatch"]:
        raise ProjectionReplayError("dependency protocol omitted a required source obligation")
    checks.append("typed summary, repair, exact source estimator/budget, draft, and human gate obligations")

    study_path = study_path or DEFAULT_STUDY
    study_raw, study = _read_json(study_path, "source study")
    if _sha(study_raw) != SOURCE_STUDY_SHA256:
        raise ProjectionReplayError("source study raw digest differs from root-verified reproduction")
    projected = _verify_source_study(study, expected_contract)
    if report.get("source_study_projection") != projected:
        raise ProjectionReplayError("declared source-study projection differs from independent recomputation")
    expected_runtime = {
        "python": study["harness"]["python"],
        "langgraph": study["harness"]["langgraph"],
        "pydantic": study["harness"]["pydantic"],
        "dependency_lock_sha256": study["harness"]["dependency_lock_sha256"],
        "provider": study["execution"]["provider"],
        "network_calls": study["execution"]["network_calls"],
        "outbound_provider_calls": study["execution"]["outbound_provider_calls"],
    }
    if report.get("runtime_provenance") != expected_runtime:
        raise ProjectionReplayError("runtime/provider provenance differs from the fixed source study")
    checks.append("22 finite source runs and 11 exact-redaction pair projections")

    mutation_rows = report.get("authored_mutation_probes")
    _verify_authored_mutations(files, mutation_rows)
    checks.append("authored raw-text classifier, repair, and draft mutations rejected")

    graph = _verify_graph_artifacts(report, report_path)
    checks.append("independent replay of the source-bound classifier OrchGraph certificate")
    verifier_raw = Path(__file__).read_bytes()
    return {
        "format": "orchlang-incident-triage-source-analysis-attestation",
        "version": 1,
        "status": "verified",
        "claim_kind": "independent pinned-source AST contract re-extraction plus classifier graph certificate replay",
        "attestation_scope": "conditional source-specific pre-dispatch request/usage/route dependency argument; not generic source translation or a mechanized proof of Python semantics",
        "source": source,
        "report_sha256": _sha(report_raw),
        "source_study_sha256": _sha(study_raw),
        "graph": graph,
        "replay_checker_sha256": _sha(verifier_raw),
        "checks": checks,
        "limitations": [
            "The upstream redactor is a trusted approved release under the exact equality relation.",
            "The shared complete outcome oracle and serial fresh graph/tracker/checkpointer are premises.",
            "The OrchGraph proof covers the classifier request pair only; the remainder is a strict source-specific dependency contract.",
            "No checkpoint/full-state privacy, general PII coverage, provider billing, live-provider behavior, or external dispatch claim is verified.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("--study", type=Path, default=DEFAULT_STUDY)
    parser.add_argument("--attestation", type=Path)
    args = parser.parse_args(argv)
    try:
        attestation = replay_projection(args.report, args.upstream, args.study)
        encoded = _canonical(attestation)
        if args.attestation:
            args.attestation.write_bytes(encoded)
        print(json.dumps({"status": attestation["status"], "report_sha256": attestation["report_sha256"],
                          "source_commit": attestation["source"]["commit"], "checks": len(attestation["checks"]),
                          "graph_replay": attestation["graph"]["graph_replay_status"]}, indent=2))
        return 0
    except (ProjectionReplayError, OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print(f"incident-triage source replay failed closed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
