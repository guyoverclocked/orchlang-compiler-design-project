"""Reference runtime for the core IR with exact padding and forced decoding.

Semantics follow `exec` in proof/ShapeCore.lean: call site `i` on its k-th
execution reads randomness cell (run_seed, i, k); dummies and ghost loop
iterations read no cell. Every model call produces one telemetry record,
which is what a content-redacting observer sees.
"""
from __future__ import annotations

import hashlib
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from . import core as C
from .models import Profile, initialize_backends, detokenize_bytes
from .ledger import UsageLedger, AdmissionRefused

SEP = "\x1f"


def tool_arguments(value):
    result = []
    for field in value.split(SEP):
        out, index = [], 0
        while index < len(field):
            char = field[index]
            if char == "\\" and index + 1 < len(field) and field[index + 1] in ("\\", "s"):
                index += 1
                char = SEP if field[index] == "s" else "\\"
            out.append(char)
            index += 1
        result.append("".join(out))
    return result


class ContractViolation(RuntimeError):
    """The execution cannot establish its declared accounting contract.

    Post-dispatch failures do not imply zero consumed resources, and detecting a
    failure cannot retract observations already visible outside the trusted host.
    """

    def __init__(self, message, *, dispatched=False):
        super().__init__(message)
        self.dispatched = dispatched
        self.usage_complete = not dispatched


@dataclass
class Record:
    kind: str           # "llm" | "tool"
    name: str           # model key or tool name
    input_tokens: int = 0
    output_tokens: int = 0
    latency: float = 0.0
    dummy: bool = False  # hidden from the observer; kept only for analysis
    site: int = 0        # call site (0 for dummies/tools); analysis only
    natural: int = 0     # tokens before the first stop token; analysis only
    audit: Dict = field(default_factory=dict)  # private evidence, never observer features

    def observed(self):
        if self.kind == "llm":
            return ("llm", self.name, self.input_tokens, self.output_tokens)
        return ("tool", self.name)


@dataclass
class RunResult:
    store: Dict[int, str]
    trace: List[Record]
    truncations: int = 0
    pad_errors: int = 0
    usage: Dict = field(default_factory=dict)

    def observed(self) -> List[Tuple]:
        return [r.observed() for r in self.trace]


def cell_seed(run_seed: int, site: int, k: int) -> int:
    h = hashlib.sha256(f"{run_seed}:{site}:{k}".encode()).digest()
    return int.from_bytes(h[:4], "little")


# ---------------------------------------------------------------- backends

class Backend:
    """Interface: tokenization plus natural and forced generation over raw
    prompt text (chat template already applied)."""

    profile: Profile

    def count(self, text: str) -> int: ...
    def encode(self, text: str) -> List[int]: ...
    def encode_plain(self, text: str) -> List[int]: ...
    def decode(self, ids: List[int]) -> str: ...
    def generate(self, prompt: str, max_tokens: int, seed: int, forced: bool,
                 cap: Optional[int] = None, pad_tokens: int = 0) -> Tuple[List[int], str, int]:
        """Returns (generated ids, visible text, prompt token count). The
        visible text stops at the first stop token and at `cap` tokens.
        `pad_tokens` contribute to logical input usage and are evaluated in an
        isolated pass the response cannot see. This does not certify an external
        provider's bill or telemetry interface."""
        ...


class LlamaBackend(Backend):
    @staticmethod
    def declared_stop_ids(model, stops):
        """Only atomic stop IDs have the prefix semantics implemented here.

        Reject string-level stops that would require buffering across token or
        visible-cap boundaries. Silently ignoring them changes the contract.
        """
        result = {model.token_eos()}
        for stop in stops:
            ids = model.tokenize(stop.encode("utf-8"), add_bos=False, special=True)
            if len(ids) != 1:
                raise ValueError("unsupported stop string: declared stops must encode as one token ID: " + repr(stop))
            result.add(ids[0])
        return result

    def __init__(self, profile: Profile, n_ctx: int = 4096, n_threads: int = 4, temperature: float = 0.0):
        from llama_cpp import Llama
        initialize_backends()
        self.profile = profile
        self.temperature = temperature
        self.m = Llama(model_path=profile.gguf, n_ctx=n_ctx, n_threads=n_threads, verbose=False, seed=0,
                       n_batch=int(os.environ.get("ORCHLANG_BATCH", "128")), n_ubatch=128,
                       n_gpu_layers=int(os.environ.get("ORCHLANG_GPU_LAYERS", "0")))
        self.stop_ids = self.declared_stop_ids(self.m, profile.stop)

    def encode(self, text):
        return self.m.tokenize(text.encode("utf-8"), add_bos=False, special=True)

    def encode_plain(self, text):
        return self.m.tokenize(text.encode("utf-8"), add_bos=False, special=False)

    def count(self, text):
        return len(self.encode(text))

    def decode(self, ids):
        return detokenize_bytes(self.m, ids).decode("utf-8", errors="ignore")

    def isolated_prefill(self, n: int) -> None:
        """Process n filler tokens in a context the response never attends to."""
        if n <= 0:
            return
        unit = self.encode_plain(self.profile.filler)[-1]
        self.m.reset()
        for i in range(0, n, 512):
            self.m.eval([unit] * min(512, n - i))
        self.m.reset()

    def generate(self, prompt, max_tokens, seed, forced, cap=None, pad_tokens=0):
        toks = self.encode(prompt)
        self.isolated_prefill(pad_tokens)
        self.m.reset()
        self.m.set_seed(seed)
        out: List[int] = []
        visible_end: Optional[int] = None
        if max_tokens > 0:
            kw = dict(temp=self.temperature, reset=True)
            if self.profile.decoding_grammar is not None:
                from llama_cpp import LlamaGrammar
                kw["grammar"] = LlamaGrammar.from_string(self.profile.decoding_grammar, verbose=False)
            if self.temperature == 0.0:
                kw.update(top_k=1)
            for t in self.m.generate(toks, **kw):
                if t in self.stop_ids and visible_end is None:
                    visible_end = len(out)
                    if not forced:
                        break
                out.append(t)
                if len(out) >= max_tokens:
                    break
        vis = out if visible_end is None else out[:visible_end]
        if cap is not None:
            vis = vis[:cap]
        self.last_natural = len(out) if visible_end is None else visible_end
        return out, self.decode(vis), len(toks) + pad_tokens


class MockBackend(Backend):
    """Deterministic backend for tests: the response is a pseudo-random function
    of (visible prompt, seed) whose length depends on content. With `tok`, counts
    use that tokenizer; otherwise one token per character. The padding message
    is removed before hashing, so forced decoding is transparent by design."""

    WORDS = [" a", " b", " c", " d", " e"]

    def __init__(self, profile: Profile, tok=None):
        self.profile = profile
        self.tok = tok

    def encode(self, text):
        return self.tok.encode(text) if self.tok else [ord(c) for c in text]

    def encode_plain(self, text):
        return self.tok.encode_plain(text) if self.tok else [ord(c) for c in text]

    def decode(self, ids):
        return self.tok.decode(ids) if self.tok else "".join(chr(i) for i in ids)

    def count(self, text):
        return len(self.encode(text))

    def visible(self, prompt):
        t = self.profile.tmpl
        pat = re.escape(t.pad_open) + "(?:" + re.escape(self.profile.filler) + ")*" + re.escape(t.pad_close)
        return re.sub(pat, "", prompt, count=1, flags=re.S)

    def generate(self, prompt, max_tokens, seed, forced, cap=None, pad_tokens=0):
        rng = random.Random(hashlib.sha256(f"{self.visible(prompt)}|{seed}".encode()).digest())
        limit = cap if cap is not None else max_tokens
        natural = rng.randint(1, max(1, limit))
        if self.tok:
            text = "".join(rng.choice(self.WORDS) for _ in range(natural))
            ids = self.encode_plain(text)[:natural]
            text = self.decode(ids)
        else:
            text = "".join(rng.choice("abcde") for _ in range(natural))
            ids = [ord(c) for c in text]
        self.last_natural = len(ids)
        if forced:
            return ids + [0] * (max_tokens - len(ids)), text, self.count(prompt) + pad_tokens
        return ids, text, self.count(prompt) + pad_tokens


# ---------------------------------------------------------------- padding

class Padder:
    """padReq: bring a request to exactly `target` tokens.

    mode "isolated" (default): the request text is kept and oversized complete
    requests are refused. Remaining tokens are processed in an attention-isolated
    local prefill and included in logical usage. This is not a provider invoice.
    Only explicit legacy overflow="truncate" may shorten an oversized request.
    mode "inband": a padding turn of filler units is inserted into the prompt
    itself (for APIs that accept only text), right after the first turn or,
    with position "end", just before the assistant header. Turn delimiters are
    special tokens, so counts are additive across the padding turn.
    Returns (text, isolated_pad_tokens, truncated)."""

    def __init__(self, backend: Backend, overflow="reject"):
        self.b = backend
        self.t = backend.profile.tmpl
        self.unit = backend.profile.filler
        self.mode = getattr(backend.profile, "pad_mode", "isolated")
        self.position = getattr(backend.profile, "pad_position", "end")
        if overflow not in ("reject", "truncate"):
            raise ValueError("overflow must be reject or explicit legacy truncate")
        self.overflow = overflow
        self.close = self.t.turn.split("{content}")[1]

    def pad(self, request: str, target: int) -> Tuple[str, int, bool]:
        if type(target) is not int or target < 0:
            raise ContractViolation("padding target must be a nonnegative integer")
        gen = self.t.generation
        if self.mode == "isolated" and self.overflow == "reject":
            count = self.b.count(request)
            if count > target:
                raise ContractViolation("complete request exceeds its declared padding target")
            return request, target - count, False
        assert request.endswith(gen), "request must end with the generation header"
        head = request[: -len(gen)]
        truncated = False
        if self.b.count(request) > target and self.overflow == "reject":
            raise ContractViolation("complete request exceeds its declared padding target")
        if self.mode == "isolated":
            while self.b.count(head + gen) > target:
                truncated = True
                head = self._shorten(head)
            text = head + gen
            return text, target - self.b.count(text), truncated
        wrap_open, wrap_close = self.t.pad_open, self.t.pad_close

        def build(h, k):
            pad = wrap_open + self.unit * k + wrap_close
            if self.position == "end":
                return h + pad + gen
            i = h.find(self.close)
            i = len(h) if i < 0 else i + len(self.close)
            return h[:i] + pad + h[i:] + gen

        while self.b.count(build(head, 0)) > target:
            if self.overflow == "reject":
                raise ContractViolation("in-band request and padding envelope exceed target")
            truncated = True
            head = self._shorten(head)
        k = target - self.b.count(build(head, 0))
        for _ in range(64):
            cand = build(head, k)
            c = self.b.count(cand)
            if c == target:
                return cand, 0, truncated
            k += target - c
            if k < 0:
                head = self._shorten(head)
                truncated = True
                k = target - self.b.count(build(head, 0))
        raise RuntimeError(f"could not pad request to {target} tokens")

    def _shorten(self, head: str) -> str:
        """Drop the last content token before the final turn terminator."""
        close = self.t.turn.split("{content}")[1]
        cut = head.rfind(close)
        if cut <= 0:
            raise RuntimeError("request template cannot fit the padding target")
        content_start = head.rfind("\n", 0, cut)
        prefix, content, suffix = head[: content_start + 1], head[content_start + 1: cut], head[cut:]
        ids = self.b.encode_plain(content)
        if not ids:
            # shorten an earlier line of the same turn
            return head[:content_start] + suffix
        return prefix + self.b.decode(ids[: max(0, len(ids) - max(1, len(ids) // 16))]) + suffix


# ---------------------------------------------------------------- interpreter

class Runtime:
    def __init__(self, backends: Dict[str, Backend], tools: Dict[str, Callable[..., str]],
                 tool_caps: Dict[str, int], dummy_request: Optional[Callable[[str], str]] = None,
                 random_pad: int = 0, overflow="reject", input_contracts=None, budgets=None):
        self.backends = backends
        self.padders = {k: Padder(b, overflow=overflow) for k, b in backends.items()}
        self.input_contracts = input_contracts or {}
        self.budgets = budgets or {}
        if set(self.budgets)-set(self.backends):
            raise ValueError("budget names must identify configured model contracts")
        self.tools = dict(tools)
        self.tools.setdefault("const", lambda v: v)
        self.tool_caps = tool_caps
        self.dummy_request = dummy_request or (
            lambda m: self.backends[m].profile.tmpl.render([("user", "")]))
        self.random_pad = random_pad

    def run(self, prog: C.Stmt, store: Dict[int, str], run_seed: int = 0) -> RunResult:
        self.trace = []
        self.count = {}
        self.truncations = 0
        self.ledger=UsageLedger(self.budgets)
        try:
            self.ledger.admit_shape(C.shape(prog))
        except AdmissionRefused as error:
            raise ContractViolation(str(error)) from error
        # This admission occurs before the first dispatch. Token caps are checked
        # in every explicitly named model unit, never transferred between units.
        for slot, units in self.input_contracts.items():
            value = store.get(slot, "")
            if not isinstance(value, str):
                raise ContractViolation("input values must be text")
            value.encode("utf-8", errors="strict")
            for model, cap in units.items():
                if type(cap) is not int or cap < 0 or model not in self.backends:
                    raise ContractViolation("invalid input token contract")
                if self.backends[model].count(value) > cap:
                    raise ContractViolation("input exceeds its declared model-specific token cap")
        self.store = dict(store)
        self.count: Dict[int, int] = {}
        self.trace: List[Record] = []
        self.truncations = 0
        self.seed = run_seed
        self.rng = random.Random(run_seed * 7919 + 17)
        self.exec(prog)
        return RunResult(self.store, self.trace, self.truncations, usage=self.ledger.snapshot())

    def _llm(self, model: str, prompt: str, n: int, seed: int, forced: bool, dummy=False, cap=None,
             site=0, pad_tokens=0) -> str:
        b = self.backends[model]
        if type(n) is not int or n < 0 or type(pad_tokens) is not int or pad_tokens < 0:
            raise ContractViolation("invalid generation or isolated-padding cap")
        if cap is not None and (type(cap) is not int or not 0 <= cap <= n):
            raise ContractViolation("visible output cap exceeds forced generation contract")
        expected_input = b.count(prompt) + pad_tokens
        try:
            attempt=self.ledger.reserve(model,expected_input,n)
        except AdmissionRefused as error:
            raise ContractViolation(str(error)) from error
        t0 = time.perf_counter()
        try:
            ids, visible, ptoks = b.generate(prompt, n, seed, forced, cap, pad_tokens)
        except Exception as error:
            raise ContractViolation("backend dispatch failed; actual usage is unknown", dispatched=True) from error
        dt = time.perf_counter() - t0
        if type(ptoks) is not int or ptoks != expected_input:
            raise ContractViolation("backend input count disagrees with complete request", dispatched=True)
        if not isinstance(ids, list) or any(type(i) is not int or i < 0 for i in ids):
            raise ContractViolation("backend returned invalid generated token IDs", dispatched=True)
        if (forced and len(ids) != n) or (not forced and len(ids) > n):
            raise ContractViolation("backend generated-output count violates its contract", dispatched=True)
        if not isinstance(visible, str):
            raise ContractViolation("backend returned non-text visible output", dispatched=True)
        try:
            visible.encode("utf-8", errors="strict")
        except UnicodeError as error:
            raise ContractViolation("backend returned invalid Unicode", dispatched=True) from error
        self.ledger.confirm(attempt,ptoks,len(ids))
        self.trace.append(Record("llm", model, ptoks, len(ids), dt, dummy, site,
                                 getattr(b, "last_natural", len(ids)),
                                 dict(request=prompt, request_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                                      request_token_ids=b.encode(prompt), generated_token_ids=ids,
                                      visible_response=visible, isolated_pad_tokens=pad_tokens,
                                      forced=forced, generation_cap=n, visible_cap=cap, seed=seed,
                                      accounting="generated token IDs plus explicit logical isolated prefill")))
        return visible

    def exec(self, s: C.Stmt) -> None:
        if isinstance(s, C.Skip):
            return
        if isinstance(s, C.Seq):
            self.exec(s.a); self.exec(s.b); return
        if isinstance(s, C.Call):
            k = self.count.get(s.site, 0)
            self.count[s.site] = k + 1
            seed = cell_seed(self.seed, s.site, k)
            req = C.eval_expr(self.store, s.req)
            if s.pad is None:
                iso=0
                if self.random_pad:
                    req,iso = self._random_pad(s.model, req)
                self.store[s.x] = self._llm(s.model, req, s.max_tokens, seed, False, site=s.site,pad_tokens=iso)
            else:
                t, n = s.pad
                padded, iso, trunc = self.padders[s.model].pad(req, t)
                self.truncations += trunc
                self.store[s.x] = self._llm(s.model, padded, n, seed, True, cap=s.max_tokens, site=s.site,
                                            pad_tokens=iso)
            return
        if isinstance(s, C.Dummy):
            padded, iso, _ = self.padders[s.model].pad(self.dummy_request(s.model), s.t)
            self._llm(s.model, padded, s.n, 0, True, dummy=True, pad_tokens=iso)
            return
        if isinstance(s, C.Tool):
            arg = C.eval_expr(self.store, s.arg)
            t0 = time.perf_counter()
            val = self.tools[s.name](*([arg] if s.name=="const" else tool_arguments(arg)))
            cap = self.tool_caps.get(s.name)
            if cap is not None:
                any_b = next(iter(self.backends.values()))
                ids = any_b.encode_plain(val)
                if len(ids) > cap:
                    val = any_b.decode(ids[:cap])
            self.store[s.x] = val
            self.trace.append(Record("tool", s.name, latency=time.perf_counter() - t0))
            return
        if isinstance(s, C.DummyTool):
            self.trace.append(Record("tool", s.name, dummy=True))
            return
        if isinstance(s, C.Ite):
            self.exec(s.a if C.holds(self.store, s.g) else s.b)
            return
        if isinstance(s, C.Loop):
            for i in range(s.n):
                if C.holds(self.store, s.g):
                    if s.padded:
                        sh = C.shape(s.body) or []
                        for _ in range(s.n - i):
                            for e in sh:
                                self.exec(C.Dummy(e[1], e[2], e[3]) if e[0] == "llm" else C.DummyTool(e[1]))
                    return
                self.exec(s.body)
            return
        raise TypeError(s)

    def _random_pad(self, model: str, req: str) -> str:
        p = self.padders[model]
        extra = self.rng.randint(0, self.random_pad)
        text, iso, _ = p.pad(req, self.backends[model].count(p.t.pad_open + p.t.pad_close) + extra
                             + self.backends[model].count(req))
        return text,iso
