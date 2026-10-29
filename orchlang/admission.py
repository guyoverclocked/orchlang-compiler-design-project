"""Executable byte-bounded adapter for the compositional admission theorem.

Both the original and shaped programs use the same explicit bounded-value
interface. Byte clipping is part of this interface, never an invisible repair
applied only to a shaped run. Native tokenizer/serving code remains trusted.
"""
from dataclasses import replace
from . import core as C, runtime as R


def clip_utf8(value: str, cap: int) -> str:
    if type(cap) is not int or cap < 0:
        raise ValueError("byte cap must be a nonnegative integer")
    return value.encode("utf-8")[:cap].decode("utf-8", errors="ignore")


def expression_bytes(expression, bounds):
    if isinstance(expression, C.ELit):
        return len(expression.value.encode("utf-8"))
    if isinstance(expression, C.EVar):
        return bounds.get(expression.x, 0)
    if isinstance(expression, C.EApp):
        return expression_bytes(expression.a, bounds) + expression_bytes(expression.b, bounds)
    if isinstance(expression, C.EEscape):
        return 2 * expression_bytes(expression.value, bounds)
    if isinstance(expression, C.ETrim):
        return expression_bytes(expression.value, bounds)
    raise TypeError(expression)


def segmentation_receipt(backend, text):
    """Check the premises of Lean's ``tokenizer_alpha_one`` on one complete request.

    The receiving tokenizer must split the request's UTF-8 bytes into nonempty
    pieces whose concatenation is exactly those bytes. Then its token count is at
    most the byte count (alpha = 1, delta = 0). Native pieces are read with the
    special-token convention used for request tokenization.
    """
    from . import models as M
    data = text.encode("utf-8")
    ids = backend.encode(text)
    native = getattr(backend, "m", None)
    if native is None:
        native = getattr(getattr(backend, "tok", None), "_m", None)
    if native is not None:
        pieces = [M.token_piece_bytes(native, token, special=True) for token in ids]
    else:
        pieces = [backend.decode([token]).encode("utf-8") for token in ids]
    segmented = b"".join(pieces) == data and all(pieces)
    return dict(tokens=len(ids), bytes=len(data), segmented=segmented,
                bound_holds=len(ids) <= len(data))


def byte_contract(program, input_bytes_per_declared_token=4, response_bytes_per_token=16,
                  tool_bytes_per_declared_token=4, context=16384):
    inputs = {program.slots[item.name]: item.max_tokens * input_bytes_per_declared_token
              for item in program.workflow.inputs}
    tool_bounds = {item.name: item.max_tokens * tool_bytes_per_declared_token
                   for item in program.workflow.tools}
    bounds = dict(inputs)
    tool_writes = []
    def visit(stmt):
        if isinstance(stmt, C.Call):
            bounds[stmt.x] = max(bounds.get(stmt.x, 0), response_bytes_per_token * stmt.max_tokens)
        elif isinstance(stmt, C.Tool):
            if stmt.name == "const" and isinstance(stmt.arg, C.ELit):
                tool_bounds["const"] = max(tool_bounds.get("const", 0), len(stmt.arg.value.encode("utf-8")))
            if stmt.name not in tool_bounds:
                raise ValueError("a certified tool needs an explicit byte bound: " + stmt.name)
            tool_writes.append(stmt)
        elif isinstance(stmt, C.Seq):
            visit(stmt.a); visit(stmt.b)
        elif isinstance(stmt, C.Ite):
            visit(stmt.a); visit(stmt.b)
        elif isinstance(stmt, C.Loop):
            visit(stmt.body)
    visit(program.body)
    for stmt in tool_writes:
        bounds[stmt.x] = max(bounds.get(stmt.x, 0), tool_bounds[stmt.name])
    return dict(schema="orchlang-byte-value-contract-v1", input_bytes=inputs,
                value_bounds=bounds, tool_bytes=tool_bounds,
                response_bytes_per_token=response_bytes_per_token,
                tokenizer_alpha=1, tokenizer_delta=0, context=context,
                dummy_request=".", overflow_policy="reject-input-before-dispatch; clip-results-at-declared-byte-interface")


class ByteBoundedRuntime(R.Runtime):
    def __init__(self, *args, byte_contract, **kwargs):
        self.byte_contract = byte_contract
        kwargs["dummy_request"] = lambda model: byte_contract["dummy_request"]
        super().__init__(*args, **kwargs)

    def run(self, program, store, run_seed=0):
        self.trace = []
        self.ledger = R.UsageLedger(self.budgets)
        self.byte_clips = []
        bounds = self.byte_contract["value_bounds"]
        if any(len(value.encode("utf-8")) > bounds.get(slot, 0) for slot, value in store.items()):
            raise R.ContractViolation("entry store exceeds the certified UTF-8 byte guard")
        return super().run(program, store, run_seed)

    def _llm(self, model, prompt, n, seed, forced, dummy=False, cap=None, site=0, pad_tokens=0):
        segmentation = segmentation_receipt(self.backends[model], prompt)
        if not segmentation["segmented"]:
            raise R.ContractViolation("complete request violates the tokenizer segmentation premise")
        value = super()._llm(model, prompt, n, seed, forced, dummy, cap, site, pad_tokens)
        self.trace[-1].audit.update(segmentation=segmentation)
        limit = self.byte_contract["response_bytes_per_token"] * (n if cap is None else cap)
        bounded = clip_utf8(value, limit)
        if value != bounded:
            self.byte_clips.append(dict(kind="llm", site=site, limit=limit,
                                        before=len(value.encode("utf-8")), after=len(bounded.encode("utf-8"))))
        self.trace[-1].audit.update(visible_response_before_byte_bound=value,
                                   visible_byte_limit=limit, visible_response=bounded,
                                   byte_clipped=(value != bounded))
        return bounded

    def exec(self, statement):
        super().exec(statement)
        if isinstance(statement, C.Tool):
            value = self.store[statement.x]
            limit = self.byte_contract["tool_bytes"][statement.name]
            bounded = clip_utf8(value, limit)
            self.store[statement.x] = bounded
            if value != bounded:
                self.byte_clips.append(dict(kind="tool", name=statement.name, limit=limit,
                                            before=len(value.encode("utf-8")), after=len(bounded.encode("utf-8"))))


class ByteEnvelopeShaperMixin:
    """Overrides heuristic request sizing; useful-call order and caps are retained."""
    def natural_pad(self, call):
        target = expression_bytes(call.req, self.byte_contract["value_bounds"])
        if target + call.max_tokens > self.byte_contract["context"]:
            raise ValueError(f"certified envelope exceeds context at site {call.site}: {target}+{call.max_tokens}")
        return target, call.max_tokens


def certified_shaper(program, profiles, tokenizers, contract, strategy="ours"):
    from .compiler import Shaper
    class ByteShaper(ByteEnvelopeShaperMixin, Shaper):
        def __init__(self):
            self.byte_contract = contract
            super().__init__(program, profiles, tokenizers, strategy)
    return ByteShaper().run()


def check_certificate(candidate, contract, backends_or_tokenizers):
    """Ask Lean's actual staticCertificate to check the serialized candidate."""
    import json
    import os
    from pathlib import Path
    import subprocess
    import tempfile
    root = Path(__file__).resolve().parents[1]
    bounds = contract["value_bounds"]
    item = dict(program=C.stmt_json(candidate),
                bounds=[bounds.get(i, 0) for i in range(max(bounds, default=-1) + 1)],
                tools=sorted(contract["tool_bytes"].items()),
                dummy_tokens=[[model, backend.count(contract["dummy_request"])]
                              for model, backend in sorted(backends_or_tokenizers.items())],
                response_bytes_per_token=contract["response_bytes_per_token"],
                context=contract["context"], alpha=contract["tokenizer_alpha"], delta=contract["tokenizer_delta"])
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "certificate.json"
        path.write_text(json.dumps([item], ensure_ascii=False), encoding="utf-8")
        environment = dict(os.environ, ORCHLANG_ADMISSION_INPUT=str(path), LEAN_PATH=str(root / "proof"))
        result = subprocess.run([os.environ.get("LEAN", "lean"), str(root / "proof/StaticAdmissionCLI.lean")],
                                cwd=root, env=environment, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise ValueError("Lean admission checker failed: " + result.stdout + result.stderr)
    verdicts = json.loads(result.stdout.rstrip("\r\n").rsplit("\n", 1)[-1])
    if len(verdicts) != 1 or type(verdicts[0].get("accepted")) is not bool:
        raise ValueError("invalid Lean admission verdict")
    return dict(payload=item, verdict=verdicts[0])
