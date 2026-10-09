#!/usr/bin/env python3
"""Independent deterministic stress study for OrchLang relational request checks.

The generated AST is rendered to OrchLang and checked by ``orchc check``. The
reference interpreter below evaluates that AST directly; it does not call the
C++ interpreter, consume analyzer facts, or parse compiler certificates.

The reference tokenizer is deliberately a byte-token abstraction: one UTF-8
byte is one input-use unit and mock output text is ASCII with at most
``max_tokens`` bytes. This makes the generated complete-request accounting
compositional under ``--chars-per-token 1``. It is a controlled model, not a
provider tokenizer or a claim about deployed billing.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import re
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
FAMILIES = (
    "balanced_chain",
    "public_nested_chain",
    "bounded_retry_chain",
    "nested_secret_chain",
    "public_outer_secret",
    "shadowed_public_chain",
)
MUTATIONS = ("cap", "template", "argument", "order", "retry")
TEXT_PAIRS = (
    ("", "z"),
    ("ordinary public text", "other value"),
    ("é", "Ω"),
    ("雪🙂", "café"),
    ('quote " slash \\', "brace {a} stays data"),
    ("line\nbreak\tvalue", "tab\tand newline\n"),
)
STATIC_PREFIXES = ("", "ask:", "λ:", "雪 request:", "ctx ")
STATIC_SEPARATORS = ("", ":", " / ", "→")
LITERALS = ("", "ok", "é", "雪", '"quoted"', "{literal}", "line\nfeed")
DEFAULT_SEEDS = (1, 7, 19, 41, 73, 101)
DEFAULT_FAILURE_PERCENT = 40
DEFAULT_INPUT_BOUND = 96
DEFAULT_BUDGET = 10_000_000


@dataclass(frozen=True)
class Contract:
    provider: str
    model_id: str
    max_tokens: int
    unit_price: str | None = None

    def key(self) -> str:
        return json.dumps(
            [self.provider, self.model_id, self.max_tokens, self.unit_price],
            ensure_ascii=False,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class InputDecl:
    name: str
    type_name: str
    max_tokens: int


@dataclass(frozen=True)
class ModelDecl:
    alias: str
    contract: Contract


@dataclass(frozen=True)
class PromptDecl:
    name: str
    parameters: tuple[str, ...]
    template: str


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Lit:
    text: str


Argument = Var | Lit


@dataclass
class Call:
    target: str
    prompt: str
    model: str
    arguments: list[Argument]


@dataclass
class Branch:
    guard: str
    then_body: list[Statement]
    else_body: list[Statement]


@dataclass
class Retry:
    bound: int
    body: list[Statement]


Statement = Call | Branch | Retry


@dataclass
class Workflow:
    name: str
    inputs: list[InputDecl]
    secrets: list[InputDecl]
    models: list[ModelDecl]
    prompts: list[PromptDecl]
    body: list[Statement]
    budget: int = DEFAULT_BUDGET

    def prompt_map(self) -> dict[str, PromptDecl]:
        return {prompt.name: prompt for prompt in self.prompts}

    def model_map(self) -> dict[str, Contract]:
        return {model.alias: model.contract for model in self.models}


@dataclass
class GeneratedCase:
    case_id: str
    family: str
    mutation: str | None
    generation_seed: int
    workflow: Workflow
    source: str


@dataclass(frozen=True)
class RuntimeValue:
    text: str
    bound_bytes: int


class StudyFailure(RuntimeError):
    pass


def utf8_bytes(value: str) -> int:
    return len(value.encode("utf-8"))


def quote_orch(value: str) -> str:
    """Quote the language's supported escapes without inserting raw C0 bytes."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\t", "\\t")
    return '"' + escaped + '"'


def render_argument(argument: Argument) -> str:
    return argument.name if isinstance(argument, Var) else quote_orch(argument.text)


def render_block(statements: Sequence[Statement], depth: int = 1) -> str:
    lines: list[str] = []
    pad = "  " * depth
    for statement in statements:
        if isinstance(statement, Call):
            args = ", ".join(render_argument(arg) for arg in statement.arguments)
            lines.append(
                f"{pad}let {statement.target}: text = call {statement.prompt}({args}) "
                f"using {statement.model};"
            )
        elif isinstance(statement, Branch):
            lines.append(f"{pad}if {statement.guard} {{")
            lines.append(render_block(statement.then_body, depth + 1).rstrip())
            lines.append(f"{pad}}} else {{")
            lines.append(render_block(statement.else_body, depth + 1).rstrip())
            lines.append(f"{pad}}}")
        elif isinstance(statement, Retry):
            lines.append(f"{pad}retry {statement.bound} {{")
            lines.append(render_block(statement.body, depth + 1).rstrip())
            lines.append(f"{pad}}}")
        else:  # pragma: no cover - protects future AST extensions
            raise TypeError(f"unsupported generated statement: {statement!r}")
    return "\n".join(lines) + ("\n" if lines else "")


def render_source(workflow: Workflow) -> str:
    lines = [f"workflow {workflow.name} budget {workflow.budget} {{"]
    for secret in workflow.secrets:
        lines.append(
            f"  secret {secret.name}: {secret.type_name} max_tokens {secret.max_tokens};"
        )
    for declaration in workflow.inputs:
        lines.append(
            f"  input {declaration.name}: {declaration.type_name} "
            f"max_tokens {declaration.max_tokens};"
        )
    for model in workflow.models:
        contract = model.contract
        price = (
            f" cost_per_token {contract.unit_price}" if contract.unit_price is not None else ""
        )
        lines.append(
            f"  model {model.alias} = mock({quote_orch(contract.model_id)}) "
            f"max_tokens {contract.max_tokens}{price};"
        )
    for prompt in workflow.prompts:
        parameters = ", ".join(f"{name}: text" for name in prompt.parameters)
        lines.append(
            f"  prompt {prompt.name}({parameters}) -> text = {quote_orch(prompt.template)};"
        )
    rendered = render_block(workflow.body).rstrip()
    if rendered:
        lines.append(rendered)
    lines.append('  output "study-complete";')
    lines.append("}")
    return "\n".join(lines) + "\n"


def _prompts(rng: random.Random, chain_length: int) -> list[PromptDecl]:
    prompts: list[PromptDecl] = []
    for index in range(max(2, chain_length)):
        prefix = rng.choice(STATIC_PREFIXES)
        separator = rng.choice(STATIC_SEPARATORS)
        suffix = rng.choice(("", "!", "?", " ✓"))
        template = f"{prefix}{{a}}{separator}{index}{separator}{{b}}{suffix}"
        prompts.append(PromptDecl(f"p{index}", ("a", "b"), template))
    return prompts


def _chain(
    prefix: str,
    chain_length: int,
    prompt_names: Sequence[str],
    aliases: Sequence[str],
    literals: Sequence[str],
) -> list[Statement]:
    statements: list[Statement] = []
    previous = "x"
    for step in range(chain_length):
        target = f"{prefix}_v{step}"
        statements.append(
            Call(
                target=target,
                prompt=prompt_names[step % len(prompt_names)],
                model=aliases[step % len(aliases)],
                arguments=[Var(previous), Lit(literals[step % len(literals)])],
            )
        )
        previous = target
    return statements


def _shadow_chain(
    prefix: str,
    prompt_names: Sequence[str],
    aliases: Sequence[str],
    literals: Sequence[str],
) -> list[Statement]:
    # `current` intentionally shadows the previous result in each nested
    # branch. The first RHS resolves the outer binding before the inner let
    # creates its lexical binding, then `tail` resolves the inner one.
    return [
        Call("current", prompt_names[0], aliases[0], [Var("x"), Lit(literals[0])]),
        Branch(
            "route",
            [
                Call("current", prompt_names[1], aliases[1], [Var("current"), Lit(literals[1])]),
                Call("tail", prompt_names[0], aliases[0], [Var("current"), Lit(literals[2])]),
            ],
            [
                Call("current", prompt_names[1], aliases[0], [Var("current"), Lit(literals[1])]),
                Call("tail", prompt_names[0], aliases[1], [Var("current"), Lit(literals[2])]),
            ],
        ),
    ]


def build_case(case_id: str, seed: int, family: str, mutation: str | None = None) -> GeneratedCase:
    rng = random.Random(seed)
    if family not in FAMILIES:
        raise ValueError(f"unknown shape family {family!r}")
    if mutation is not None and mutation not in MUTATIONS:
        raise ValueError(f"unknown mutation {mutation!r}")

    model_cap = rng.randint(2, 12)
    model_id = f"stress-model-{seed % 13}"
    left = "model_left"
    right = "model_right"
    base_contract = Contract("mock", model_id, model_cap)
    models = [ModelDecl(left, base_contract), ModelDecl(right, base_contract)]
    prompt_list = _prompts(rng, rng.randint(2, 4))
    prompt_names = [prompt.name for prompt in prompt_list]
    literals = [rng.choice(LITERALS) for _ in range(4)]
    chain_length = rng.randint(2, min(4, len(prompt_names)))
    aliases_left = [left, right]
    aliases_right = [right, left]
    retry_bound = rng.randint(1, 4)
    secrets = [InputDecl("s0", "boolean", 1)]
    if family == "nested_secret_chain":
        secrets.append(InputDecl("s1", "boolean", 1))
    inputs = [
        InputDecl("route", "boolean", 1),
        InputDecl("x", "text", DEFAULT_INPUT_BOUND),
        InputDecl("y", "text", DEFAULT_INPUT_BOUND),
    ]

    def chain(prefix: str, aliases: Sequence[str] = aliases_left) -> list[Statement]:
        return _chain(prefix, chain_length, prompt_names, aliases, literals)

    if family == "balanced_chain":
        body: list[Statement] = [
            Branch("s0", chain("left", aliases_left), chain("right", aliases_right))
        ]
    elif family == "public_nested_chain":
        body = [
            Branch(
                "s0",
                [
                    Branch(
                        "route",
                        chain("left_then", aliases_left),
                        chain("left_else", aliases_right),
                    )
                ],
                [
                    Branch(
                        "route",
                        chain("right_then", aliases_right),
                        chain("right_else", aliases_left),
                    )
                ],
            )
        ]
    elif family == "bounded_retry_chain":
        body = [
            Branch(
                "s0",
                [Retry(retry_bound, chain("left_retry", aliases_left))],
                [Retry(retry_bound, chain("right_retry", aliases_right))],
            )
        ]
    elif family == "nested_secret_chain":
        body = [
            Branch(
                "s0",
                [
                    Branch(
                        "s1",
                        chain("left_inner_then", aliases_left),
                        chain("left_inner_else", aliases_right),
                    )
                ],
                [
                    Branch(
                        "s1",
                        chain("right_inner_then", aliases_right),
                        chain("right_inner_else", aliases_left),
                    )
                ],
            )
        ]
    elif family == "public_outer_secret":
        body = [
            Branch(
                "route",
                [
                    Branch(
                        "s0",
                        chain("route_then_left", aliases_left),
                        chain("route_then_right", aliases_right),
                    )
                ],
                [
                    Branch(
                        "s0",
                        chain("route_else_left", aliases_right),
                        chain("route_else_right", aliases_left),
                    )
                ],
            )
        ]
    else:  # shadowed_public_chain
        body = [
            Branch(
                "s0",
                _shadow_chain("left", prompt_names, aliases_left, literals),
                _shadow_chain("right", prompt_names, aliases_right, literals),
            )
        ]

    workflow = Workflow(
        name=f"Stress{seed:04d}",
        inputs=inputs,
        secrets=secrets,
        models=models,
        prompts=prompt_list,
        body=body,
    )

    if mutation == "cap":
        changed_alias = "model_changed"
        models.append(ModelDecl(changed_alias, Contract("mock", model_id, model_cap + 1)))
        _first_call(_outer_secret_branch(workflow).else_body).model = changed_alias
    elif mutation == "template":
        original = prompt_list[0]
        changed = PromptDecl("p_changed", original.parameters, original.template + "!")
        prompt_list.append(changed)
        _first_call(_outer_secret_branch(workflow).else_body).prompt = changed.name
    elif mutation == "argument":
        target = _first_call(_outer_secret_branch(workflow).else_body)
        target.arguments[0] = Var("y")
    elif mutation == "order":
        target = _first_call(_outer_secret_branch(workflow).else_body)
        target.arguments = list(reversed(target.arguments))
    elif mutation == "retry":
        if family != "bounded_retry_chain":
            raise ValueError("retry mutation requires bounded_retry_chain shape")
        retry = _first_retry(_outer_secret_branch(workflow).else_body)
        retry.bound += 1

    case = GeneratedCase(case_id, family, mutation, seed, workflow, "")
    case.source = render_source(workflow)
    return case


def _walk(statements: Iterable[Statement]) -> Iterable[Statement]:
    for statement in statements:
        yield statement
        if isinstance(statement, Branch):
            yield from _walk(statement.then_body)
            yield from _walk(statement.else_body)
        elif isinstance(statement, Retry):
            yield from _walk(statement.body)


def _outer_secret_branch(workflow: Workflow) -> Branch:
    for statement in _walk(workflow.body):
        if isinstance(statement, Branch) and statement.guard in {s.name for s in workflow.secrets}:
            # The outermost matching secret branch is the first encountered
            # in source traversal; public wrappers may precede it.
            return statement
    raise StudyFailure("generated workflow has no secret branch")


def _first_call(statements: Iterable[Statement]) -> Call:
    for statement in _walk(statements):
        if isinstance(statement, Call):
            return statement
    raise StudyFailure("generated branch arm contains no model call")


def _first_retry(statements: Iterable[Statement]) -> Retry:
    for statement in _walk(statements):
        if isinstance(statement, Retry):
            return statement
    raise StudyFailure("generated retry case contains no retry block")


def substitute(template: str, parameters: Sequence[str], values: Sequence[str]) -> str:
    if len(parameters) != len(values):
        raise StudyFailure("reference call arity differs from prompt declaration")
    replacements = dict(zip(parameters, values))

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in replacements:
            raise StudyFailure(f"unknown generated template placeholder {name!r}")
        return replacements[name]

    return re.sub(r"\{([^{}]+)\}", replace, template)


def oracle_response(contract: Contract, ordinal: int, request: str, seed: int) -> str:
    """A complete-text, cap-respecting deterministic oracle Ω(M,k,Q)."""
    key = json.dumps(
        [contract.key(), ordinal, request], ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(seed.to_bytes(8, "big", signed=False) + key).digest()
    output_bytes = int.from_bytes(digest[:8], "big") % (contract.max_tokens + 1)
    # ASCII x means the reference tokenizer charges exactly one byte per
    # generated output token. The complete text is retained for later calls.
    return "x" * output_bytes


def _retry_succeeds(seed: int, retry_ordinal: int, attempt: int, failure_percent: int) -> bool:
    key = f"retry-v1:{seed}:{retry_ordinal}:{attempt}".encode("ascii")
    value = int.from_bytes(hashlib.sha256(key).digest()[:8], "big") % 100
    return value >= failure_percent


def run_reference(
    workflow: Workflow,
    public_values: dict[str, str | bool],
    secret_values: dict[str, bool],
    seed: int,
    failure_percent: int = DEFAULT_FAILURE_PERCENT,
) -> dict[str, object]:
    """Interpret the generated AST with concrete UTF-8 text and shared Ω."""
    prompts = workflow.prompt_map()
    contracts = workflow.model_map()
    root_env: dict[str, RuntimeValue | bool] = {}
    bounds = {declaration.name: declaration.max_tokens for declaration in workflow.inputs}
    bounds.update({declaration.name: declaration.max_tokens for declaration in workflow.secrets})
    for declaration in workflow.inputs:
        value = public_values[declaration.name]
        if declaration.type_name == "text":
            if not isinstance(value, str):
                raise StudyFailure(f"input {declaration.name} requires full text")
            if utf8_bytes(value) > declaration.max_tokens:
                raise StudyFailure(f"public input {declaration.name} exceeds its declared byte bound")
            root_env[declaration.name] = RuntimeValue(value, declaration.max_tokens)
        else:
            if not isinstance(value, bool):
                raise StudyFailure(f"input {declaration.name} requires a boolean")
            root_env[declaration.name] = value
    for declaration in workflow.secrets:
        if declaration.name not in secret_values:
            raise StudyFailure(f"missing secret assignment {declaration.name}")
        root_env[declaration.name] = bool(secret_values[declaration.name])

    scopes: list[dict[str, RuntimeValue | bool]] = [root_env]
    call_ordinals: dict[str, int] = defaultdict(int)
    retry_ordinal = 0
    request_trace: list[dict[str, object]] = []
    usage_trace: list[dict[str, object]] = []
    retry_trace: list[int] = []
    accounting_checks = 0
    total_input = 0
    total_output = 0

    def lookup(name: str) -> RuntimeValue | bool:
        for scope in reversed(scopes):
            if name in scope:
                return scope[name]
        raise StudyFailure(f"reference interpreter cannot resolve {name!r}")

    def execute(statements: Sequence[Statement]) -> None:
        nonlocal retry_ordinal, accounting_checks, total_input, total_output
        for statement in statements:
            if isinstance(statement, Call):
                contract = contracts[statement.model]
                prompt = prompts[statement.prompt]
                concrete_values: list[str] = []
                argument_bound = 0
                for argument in statement.arguments:
                    if isinstance(argument, Lit):
                        concrete_values.append(argument.text)
                        argument_bound += utf8_bytes(argument.text)
                    else:
                        value = lookup(argument.name)
                        if not isinstance(value, RuntimeValue):
                            raise StudyFailure("boolean value reached generated text prompt")
                        concrete_values.append(value.text)
                        argument_bound += value.bound_bytes
                request = substitute(prompt.template, prompt.parameters, concrete_values)
                input_bytes = utf8_bytes(request)
                input_bound = utf8_bytes(prompt.template) + argument_bound
                if input_bytes > input_bound:
                    raise StudyFailure(
                        f"request accounting premise failed: {input_bytes} > {input_bound}"
                    )
                accounting_checks += 1
                ordinal = call_ordinals[contract.key()]
                call_ordinals[contract.key()] += 1
                response = oracle_response(contract, ordinal, request, seed)
                output_bytes = utf8_bytes(response)
                if output_bytes > contract.max_tokens:
                    raise StudyFailure("oracle exceeded a declared output cap")
                total_input += input_bytes
                total_output += output_bytes
                request_trace.append(
                    {
                        "contract": contract.key(),
                        "ordinal": ordinal,
                        "request": request,
                    }
                )
                usage_trace.append(
                    {
                        "contract": contract.key(),
                        "input_bytes": input_bytes,
                        "output_bytes": output_bytes,
                    }
                )
                # A call result's declared bound is the provider cap, and its
                # full concrete response is what a later prompt receives.
                scopes[-1][statement.target] = RuntimeValue(response, contract.max_tokens)
            elif isinstance(statement, Branch):
                guard = lookup(statement.guard)
                if not isinstance(guard, bool):
                    raise StudyFailure("generated branch guard is not boolean")
                scopes.append({})
                try:
                    execute(statement.then_body if guard else statement.else_body)
                finally:
                    scopes.pop()
            elif isinstance(statement, Retry):
                current_retry = retry_ordinal
                retry_ordinal += 1
                attempts = 0
                for attempt in range(statement.bound):
                    scopes.append({})
                    try:
                        execute(statement.body)
                    finally:
                        scopes.pop()
                    attempts += 1
                    if _retry_succeeds(seed, current_retry, attempt, failure_percent):
                        break
                retry_trace.append(attempts)
            else:  # pragma: no cover
                raise TypeError(f"unsupported reference statement {statement!r}")

    execute(workflow.body)
    total_usage = total_input + total_output
    if total_usage > workflow.budget:
        raise StudyFailure(f"actual usage {total_usage} exceeds workflow budget {workflow.budget}")
    billing: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for call in usage_trace:
        entry = billing[str(call["contract"])]
        entry[0] += int(call["input_bytes"])
        entry[1] += int(call["output_bytes"])
        entry[2] += 1
    return {
        "request_trace": request_trace,
        "usage_trace": usage_trace,
        "billing": {key: value for key, value in sorted(billing.items())},
        "retry_attempts": retry_trace,
        "total_input_bytes": total_input,
        "total_output_bytes": total_output,
        "total_usage": total_usage,
        "accounting_checks": accounting_checks,
    }


def secret_assignments(workflow: Workflow) -> list[dict[str, bool]]:
    names = [secret.name for secret in workflow.secrets]
    return [dict(zip(names, values)) for values in itertools.product((False, True), repeat=len(names))]


def public_scenarios(workflow: Workflow) -> list[dict[str, str | bool]]:
    scenarios: list[dict[str, str | bool]] = []
    for left, right in TEXT_PAIRS:
        for route in (False, True):
            scenarios.append({"x": left, "y": right, "route": route})
    return scenarios


def _observation(run: dict[str, object], field: str) -> str:
    return json.dumps(run[field], ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compare_secret_assignments(
    workflow: Workflow,
    scenarios: Sequence[dict[str, str | bool]],
    seeds: Sequence[int],
    failure_percent: int,
) -> dict[str, object]:
    comparisons = 0
    request_mismatches = 0
    usage_mismatches = 0
    first_mismatch: dict[str, object] | None = None
    reference_runs = 0
    call_total = 0
    retry_attempt_total = 0
    input_checks = 0
    for public_values in scenarios:
        for seed in seeds:
            baseline: dict[str, object] | None = None
            for secrets in secret_assignments(workflow):
                run = run_reference(workflow, public_values, secrets, seed, failure_percent)
                reference_runs += 1
                call_total += len(run["usage_trace"])  # type: ignore[arg-type]
                retry_attempt_total += sum(run["retry_attempts"])  # type: ignore[arg-type]
                input_checks += int(run["accounting_checks"])
                if baseline is None:
                    baseline = run
                    continue
                comparisons += 1
                request_diff = _observation(run, "request_trace") != _observation(
                    baseline, "request_trace"
                )
                usage_diff = (
                    _observation(run, "usage_trace") != _observation(baseline, "usage_trace")
                    or _observation(run, "billing") != _observation(baseline, "billing")
                )
                request_mismatches += int(request_diff)
                usage_mismatches += int(usage_diff)
                if first_mismatch is None and (request_diff or usage_diff):
                    first_mismatch = {
                        "public_values": public_values,
                        "secret_values": secrets,
                        "seed": seed,
                        "request_trace_diff": request_diff,
                        "usage_diff": usage_diff,
                        "baseline_request_trace": baseline["request_trace"],
                        "variant_request_trace": run["request_trace"],
                        "baseline_usage_trace": baseline["usage_trace"],
                        "variant_usage_trace": run["usage_trace"],
                        "baseline_billing": baseline["billing"],
                        "variant_billing": run["billing"],
                    }
    return {
        "comparisons": comparisons,
        "request_mismatches": request_mismatches,
        "usage_mismatches": usage_mismatches,
        "first_mismatch": first_mismatch,
        "reference_runs": reference_runs,
        "model_calls": call_total,
        "retry_attempts": retry_attempt_total,
        "input_accounting_checks": input_checks,
    }


def compiler_check(compiler: Path, source: str) -> tuple[bool, list[str], str]:
    with tempfile.TemporaryDirectory(prefix="orchlang-relstress-") as temp_dir:
        source_path = Path(temp_dir) / "case.orch"
        source_path.write_text(source, encoding="utf-8", newline="")
        process = subprocess.run(
            [str(compiler), "check", str(source_path), "--chars-per-token", "1"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    diagnostic_codes = sorted(set(re.findall(r"\[([A-Z]\d{3})\]", process.stderr)))
    return process.returncode == 0, diagnostic_codes, process.stderr.strip()


def generate_cases(cases_per_family: int, mutations_per_kind: int) -> list[GeneratedCase]:
    cases: list[GeneratedCase] = []
    serial = 0
    for family_index, family in enumerate(FAMILIES):
        for variant in range(cases_per_family):
            serial += 1
            seed = 10_000 + family_index * 1_000 + variant * 17 + 1
            cases.append(build_case(f"accept-{family}-{variant:03d}", seed, family))
    for mutation_index, mutation in enumerate(MUTATIONS):
        family = "bounded_retry_chain" if mutation == "retry" else FAMILIES[mutation_index % len(FAMILIES)]
        for variant in range(mutations_per_kind):
            serial += 1
            seed = 90_000 + mutation_index * 1_000 + variant * 19 + 3
            cases.append(
                build_case(f"reject-{mutation}-{variant:03d}", seed, family, mutation)
            )
    return cases


def _case_manifest(cases: Sequence[GeneratedCase]) -> tuple[list[dict[str, object]], str]:
    rows: list[dict[str, object]] = []
    for case in cases:
        source_hash = hashlib.sha256(case.source.encode("utf-8")).hexdigest()
        rows.append(
            {
                "case_id": case.case_id,
                "family": case.family,
                "mutation": case.mutation,
                "generation_seed": case.generation_seed,
                "source_sha256": source_hash,
                "source_bytes": len(case.source.encode("utf-8")),
            }
        )
    encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return rows, hashlib.sha256(encoded).hexdigest()


def run_study(
    compiler: Path,
    cases_per_family: int = 24,
    mutations_per_kind: int = 24,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    failure_percent: int = DEFAULT_FAILURE_PERCENT,
) -> dict[str, object]:
    compiler = compiler.resolve()
    cases = generate_cases(cases_per_family, mutations_per_kind)
    manifest, manifest_hash = _case_manifest(cases)
    failures: list[dict[str, object]] = []
    accepted_stats: dict[str, dict[str, int]] = {
        family: {"cases": 0, "cxx_accepted": 0, "comparisons": 0,
                 "request_mismatches": 0, "usage_mismatches": 0,
                 "reference_runs": 0, "model_calls": 0, "retry_attempts": 0,
                 "input_accounting_checks": 0}
        for family in FAMILIES
    }
    mutation_stats: dict[str, dict[str, int]] = {
        mutation: {"cases": 0, "cxx_rejected": 0, "e236": 0,
                   "witnessed_request_trace": 0, "witnessed_usage_trace": 0,
                   "unknown_no_witness_in_grid": 0, "equal_value_subcases": 0,
                   "equal_value_subcases_without_witness": 0,
                   "reference_runs": 0, "comparisons": 0}
        for mutation in MUTATIONS
    }
    case_results: list[dict[str, object]] = []
    accepted_case_count = 0
    accepted_cxx_count = 0
    rejected_case_count = 0
    rejected_cxx_count = 0
    accepted_comparisons = 0
    accepted_reference_runs = 0
    accepted_model_calls = 0
    accepted_retry_attempts = 0
    accepted_accounting_checks = 0
    accepted_request_mismatches = 0
    accepted_usage_mismatches = 0
    rejected_request_witnesses = 0
    rejected_usage_witnesses = 0
    rejected_unknowns = 0

    for case in cases:
        cxx_accepted, codes, stderr = compiler_check(compiler, case.source)
        expected_accept = case.mutation is None
        row: dict[str, object] = {
            "case_id": case.case_id,
            "family": case.family,
            "mutation": case.mutation,
            "generation_seed": case.generation_seed,
            "cxx_accepted": cxx_accepted,
            "diagnostic_codes": codes,
            "source_sha256": hashlib.sha256(case.source.encode("utf-8")).hexdigest(),
        }
        if expected_accept:
            accepted_case_count += 1
            stats = accepted_stats[case.family]
            stats["cases"] += 1
            if not cxx_accepted:
                failures.append(
                    {
                        "case_id": case.case_id,
                        "kind": "unexpected_compiler_rejection",
                        "diagnostic_codes": codes,
                        "stderr": stderr,
                    }
                )
                row["reference_status"] = "not_run_after_unexpected_reject"
            else:
                accepted_cxx_count += 1
                stats["cxx_accepted"] += 1
                reference = compare_secret_assignments(
                    case.workflow,
                    public_scenarios(case.workflow),
                    seeds,
                    failure_percent,
                )
                row["reference"] = reference
                for key in (
                    "comparisons", "request_mismatches", "usage_mismatches",
                    "reference_runs", "model_calls", "retry_attempts",
                    "input_accounting_checks",
                ):
                    stats[key] += int(reference[key])
                accepted_comparisons += int(reference["comparisons"])
                accepted_reference_runs += int(reference["reference_runs"])
                accepted_model_calls += int(reference["model_calls"])
                accepted_retry_attempts += int(reference["retry_attempts"])
                accepted_accounting_checks += int(reference["input_accounting_checks"])
                accepted_request_mismatches += int(reference["request_mismatches"])
                accepted_usage_mismatches += int(reference["usage_mismatches"])
                if reference["request_mismatches"] or reference["usage_mismatches"]:
                    failures.append(
                        {
                            "case_id": case.case_id,
                            "kind": "accepted_reference_mismatch",
                            "first_mismatch": reference["first_mismatch"],
                        }
                    )
        else:
            rejected_case_count += 1
            mutation = str(case.mutation)
            stats = mutation_stats[mutation]
            stats["cases"] += 1
            if cxx_accepted:
                failures.append(
                    {"case_id": case.case_id, "kind": "unexpected_mutation_acceptance"}
                )
                row["reference_status"] = "not_run_after_unexpected_accept"
            else:
                rejected_cxx_count += 1
                stats["cxx_rejected"] += 1
                has_e236 = "E236" in codes
                stats["e236"] += int(has_e236)
                if not has_e236:
                    failures.append(
                        {
                            "case_id": case.case_id,
                            "kind": "rejected_without_relational_diagnostic",
                            "diagnostic_codes": codes,
                            "stderr": stderr,
                        }
                    )
                probe = compare_secret_assignments(
                    case.workflow,
                    public_scenarios(case.workflow),
                    seeds,
                    failure_percent,
                )
                row["reference_probe"] = probe
                stats["reference_runs"] += int(probe["reference_runs"])
                stats["comparisons"] += int(probe["comparisons"])
                request_witness = bool(probe["request_mismatches"])
                usage_witness = bool(probe["usage_mismatches"])
                stats["witnessed_request_trace"] += int(request_witness)
                stats["witnessed_usage_trace"] += int(usage_witness)
                rejected_request_witnesses += int(request_witness)
                rejected_usage_witnesses += int(usage_witness)
                if not request_witness and not usage_witness:
                    stats["unknown_no_witness_in_grid"] += 1
                    rejected_unknowns += 1
                if mutation == "argument":
                    # The public values coincide in this explicit subgrid.
                    # The static rule still rejects distinct lexical bindings;
                    # that is a conservative structural outcome, not a
                    # quantified false-positive claim over the full domain.
                    equal_scenarios = [
                        {"x": left, "y": left, "route": route}
                        for left, _right in TEXT_PAIRS
                        for route in (False, True)
                    ]
                    equal_probe = compare_secret_assignments(
                        case.workflow, equal_scenarios, seeds, failure_percent
                    )
                    stats["equal_value_subcases"] += int(equal_probe["comparisons"])
                    if not equal_probe["request_mismatches"] and not equal_probe["usage_mismatches"]:
                        stats["equal_value_subcases_without_witness"] += int(
                            equal_probe["comparisons"]
                        )
                row["witness_status"] = (
                    "usage_and_request_trace_witness"
                    if usage_witness and request_witness
                    else "usage_trace_witness"
                    if usage_witness
                    else "request_trace_only_witness"
                    if request_witness
                    else "unknown_no_witness_in_finite_grid"
                )
        case_results.append(row)

    source_manifest_hash = manifest_hash
    compiler_hash = hashlib.sha256(compiler.read_bytes()).hexdigest()
    generator_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    all_sources_acceptance_ok = accepted_case_count == accepted_cxx_count
    all_mutations_rejected = rejected_case_count == rejected_cxx_count
    no_reference_mismatches = accepted_request_mismatches == 0 and accepted_usage_mismatches == 0
    report: dict[str, object] = {
        "format": "orchlang-independent-relational-stress",
        "version": 1,
        "study": {
            "method": "deterministic synthetic AST generation plus a separate Python full-text reference interpreter",
            "compiler_check_only": True,
            "reference_uses_cpp_runtime_or_facts": False,
            "generator_sha256": generator_hash,
            "compiler_sha256": compiler_hash,
            "source_manifest_sha256": source_manifest_hash,
            "case_generation_seed_formula": "accepted: 10000 + family_index*1000 + variant*17 + 1; mutations: 90000 + mutation_index*1000 + variant*19 + 3",
            "generated_case_count": len(cases),
            "accepted_case_count": accepted_case_count,
            "expected_rejection_case_count": rejected_case_count,
            "per_family_accepted_cases": cases_per_family,
            "per_mutation_cases": mutations_per_kind,
            "families": list(FAMILIES),
            "mutations": list(MUTATIONS),
            "seeds": list(seeds),
            "public_text_pairs": len(TEXT_PAIRS),
            "public_route_values": [False, True],
            "failure_percent": failure_percent,
            "token_accounting_model": "one UTF-8 byte equals one abstract input-use token; compiler invoked with --chars-per-token 1",
            "complete_request": "decoded template placeholders are substituted with full UTF-8 argument text before byte usage is counted",
            "oracle": "Omega(M,k,Q): SHA-256 of the fixed seed, canonical resolved contract M, per-contract ordinal k, and complete rendered request Q chooses a full ASCII response of 0..max_tokens bytes",
            "retry_oracle": "retry success/failure is a deterministic shared schedule keyed by seed, retry ordinal, and attempt index",
            "scope_limitations": [
                "synthetic generated workflows; not exhaustive over the language",
                "no provider adapter, real tokenizer, provider request envelope, invoice, timing, or output-text claim",
                "only no-declassification generated cases are included",
                "finite no-witness rejection probes are unknown, not labeled false positives",
                "the generated byte-token assumption is controlled and does not imply provider billing soundness",
            ],
        },
        "checks": {
            "accepted_cases_all_cxx_check_success": all_sources_acceptance_ok,
            "expected_mutations_all_rejected_by_cxx_check": all_mutations_rejected,
            "accepted_reference_usage_and_request_traces_equal_across_secret_assignments": no_reference_mismatches,
            "accepted_secret_assignment_comparisons": accepted_comparisons,
            "accepted_reference_runs": accepted_reference_runs,
            "accepted_model_calls": accepted_model_calls,
            "accepted_retry_attempts": accepted_retry_attempts,
            "accepted_per_call_input_accounting_checks": accepted_accounting_checks,
            "accepted_request_trace_mismatches": accepted_request_mismatches,
            "accepted_usage_trace_mismatches": accepted_usage_mismatches,
            "rejected_mutation_cases_cxx_rejected": rejected_cxx_count,
            "rejected_mutation_request_trace_witness_cases": rejected_request_witnesses,
            "rejected_mutation_usage_trace_witness_cases": rejected_usage_witnesses,
            "rejected_mutation_unknown_no_witness_cases": rejected_unknowns,
        },
        "accepted_by_shape": accepted_stats,
        "rejected_by_mutation": mutation_stats,
        "source_manifest": manifest,
        "case_results": case_results,
        "failure_criteria": [
            "exit nonzero if any generated accepted case is rejected by orchc check",
            "exit nonzero if any accepted case has differing reference request or usage traces across secret assignments",
            "exit nonzero if a generated request exceeds its byte-accounting premise, a response exceeds its cap, or an execution exceeds budget",
            "exit nonzero if any expected mutation is accepted or lacks the relational E236 diagnostic",
            "do not fail solely because a rejected case has no distinguishing witness in the finite probe grid",
        ],
        "failures": failures,
        "exit_status": 1 if failures else 0,
    }
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, default=ROOT / "orchc")
    parser.add_argument("--output", type=Path, default=ROOT / "bench/results/relational_stress.json")
    parser.add_argument("--cases-per-family", type=int, default=24)
    parser.add_argument("--mutations-per-kind", type=int, default=24)
    parser.add_argument("--seeds", default=",".join(str(seed) for seed in DEFAULT_SEEDS))
    parser.add_argument("--failure-percent", type=int, default=DEFAULT_FAILURE_PERCENT)
    args = parser.parse_args(argv)
    try:
        seeds = tuple(int(part) for part in args.seeds.split(",") if part)
        if not seeds or any(seed < 0 or seed >= 2**64 for seed in seeds):
            raise ValueError("seeds must be one or more unsigned 64-bit integers")
        if args.cases_per_family < 1 or args.mutations_per_kind < 1:
            raise ValueError("case counts must be positive")
        if args.failure_percent < 0 or args.failure_percent > 100:
            raise ValueError("failure percent must be in [0,100]")
        if not args.compiler.is_file():
            raise ValueError(f"compiler not found: {args.compiler}")
        report = run_study(
            args.compiler,
            args.cases_per_family,
            args.mutations_per_kind,
            seeds,
            args.failure_percent,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary = report["checks"]
        print(
            "relational stress: "
            f"{report['study']['generated_case_count']} cases; "
            f"{summary['accepted_secret_assignment_comparisons']} accepted secret comparisons; "
            f"{summary['accepted_request_trace_mismatches']} request mismatches; "
            f"{summary['accepted_usage_trace_mismatches']} usage mismatches; "
            f"{len(report['failures'])} failures"
        )
        print(f"wrote {args.output}")
        return int(report["exit_status"])
    except (OSError, ValueError, StudyFailure, subprocess.SubprocessError) as error:
        print(f"relational_stress: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
