"""Reference runtime for the core IR with exact padding and forced decoding.

Semantics follow `exec` in proof/ShapeCore.lean: call site `i` on its k-th
execution reads randomness cell (run_seed, i, k); dummies and ghost loop
iterations read no cell. Every model call produces one telemetry record,
which is what a content-redacting observer sees.
"""
from __future__ import annotations

import hashlib
import random
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from . import core as C
from .models import Profile

SEP = "\x1f"


@dataclass
class Record:
    kind: str           # "llm" | "tool"
    name: str           # model key or tool name
    input_tokens: int = 0
    output_tokens: int = 0
    latency: float = 0.0
    dummy: bool = False  # hidden from the observer; kept only for analysis

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
                 cap: Optional[int] = None) -> Tuple[List[int], str, int]:
        """Returns (generated ids, visible text, prompt token count). The
        visible text stops at the first stop token and at `cap` tokens."""
        ...


class LlamaBackend(Backend):
    def __init__(self, profile: Profile, n_ctx: int = 4096, n_threads: int = 4, temperature: float = 0.0):
        from llama_cpp import Llama
        self.profile = profile
        self.temperature = temperature
        self.m = Llama(model_path=profile.gguf, n_ctx=n_ctx, n_threads=n_threads, verbose=False, seed=0)
        self.stop_ids = {self.m.token_eos()}
        for s in profile.stop:
            ids = self.m.tokenize(s.encode(), add_bos=False, special=True)
            if len(ids) == 1:
                self.stop_ids.add(ids[0])

    def encode(self, text):
        return self.m.tokenize(text.encode("utf-8"), add_bos=False, special=True)

    def encode_plain(self, text):
        return self.m.tokenize(text.encode("utf-8"), add_bos=False, special=False)

    def count(self, text):
        return len(self.encode(text))

    def decode(self, ids):
        return self.m.detokenize(ids).decode("utf-8", errors="ignore")

    def generate(self, prompt, max_tokens, seed, forced, cap=None):
        toks = self.encode(prompt)
        self.m.reset()
        self.m.set_seed(seed)
        out: List[int] = []
        visible_end: Optional[int] = None
        if max_tokens > 0:
            kw = dict(temp=self.temperature, reset=True)
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
        return out, self.decode(vis), len(toks)


class MockBackend(Backend):
    """Deterministic character-level backend for tests: the response is a
    pseudo-random function of (prompt, seed) whose length depends on content."""

    def __init__(self, profile: Profile):
        self.profile = profile

    def encode(self, text):
        return [ord(c) for c in text]

    encode_plain = encode

    def decode(self, ids):
        return "".join(chr(i) for i in ids)

    def count(self, text):
        return len(text)

    def generate(self, prompt, max_tokens, seed, forced, cap=None):
        t = self.profile.tmpl
        visible_prompt = re.sub(re.escape(t.pad_open) + ".*?" + re.escape(t.pad_close), "", prompt, flags=re.S)
        rng = random.Random(hashlib.sha256(f"{visible_prompt}|{seed}".encode()).digest())
        natural = rng.randint(1, max(1, cap if cap is not None else max_tokens))
        text = "".join(rng.choice("abcde") for _ in range(natural))
        if forced:
            ids = [ord(c) for c in text] + [0] * (max_tokens - natural)
            return ids, text, len(prompt)
        return [ord(c) for c in text], text, len(prompt)


# ---------------------------------------------------------------- padding

class Padder:
    """padReq: truncate the final user content if needed, then add a padding
    message of filler units so the request has exactly `target` tokens."""

    def __init__(self, backend: Backend):
        self.b = backend
        self.t = backend.profile.tmpl
        unit = backend.profile.filler
        self.unit = unit

    def pad(self, request: str, target: int) -> Tuple[str, bool]:
        gen = self.t.generation
        assert request.endswith(gen), "request must end with the generation header"
        head = request[: -len(gen)]
        wrap_open, wrap_close = self.t.pad_open, self.t.pad_close
        truncated = False

        def build(h, k):
            return h + wrap_open + self.unit * k + wrap_close + gen

        while self.b.count(build(head, 0)) > target:
            truncated = True
            head = self._shorten(head)
        base = self.b.count(build(head, 0))
        k = target - base
        for _ in range(64):
            cand = build(head, k)
            c = self.b.count(cand)
            if c == target:
                return cand, truncated
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
                 random_pad: int = 0):
        self.backends = backends
        self.padders = {k: Padder(b) for k, b in backends.items()}
        self.tools = dict(tools)
        self.tools.setdefault("const", lambda v: v)
        self.tool_caps = tool_caps
        self.dummy_request = dummy_request or (
            lambda m: self.backends[m].profile.tmpl.render([("user", "")]))
        self.random_pad = random_pad

    def run(self, prog: C.Stmt, store: Dict[int, str], run_seed: int = 0) -> RunResult:
        self.store = dict(store)
        self.count: Dict[int, int] = {}
        self.trace: List[Record] = []
        self.truncations = 0
        self.seed = run_seed
        self.rng = random.Random(run_seed * 7919 + 17)
        self.exec(prog)
        return RunResult(self.store, self.trace, self.truncations)

    def _llm(self, model: str, prompt: str, n: int, seed: int, forced: bool, dummy=False, cap=None) -> str:
        b = self.backends[model]
        t0 = time.perf_counter()
        ids, visible, ptoks = b.generate(prompt, n, seed, forced, cap)
        dt = time.perf_counter() - t0
        self.trace.append(Record("llm", model, ptoks, len(ids), dt, dummy))
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
                if self.random_pad:
                    req = self._random_pad(s.model, req)
                self.store[s.x] = self._llm(s.model, req, s.max_tokens, seed, False)
            else:
                t, n = s.pad
                padded, trunc = self.padders[s.model].pad(req, t)
                self.truncations += trunc
                self.store[s.x] = self._llm(s.model, padded, n, seed, True, cap=s.max_tokens)
            return
        if isinstance(s, C.Dummy):
            padded, _ = self.padders[s.model].pad(self.dummy_request(s.model), s.t)
            self._llm(s.model, padded, s.n, 0, True, dummy=True)
            return
        if isinstance(s, C.Tool):
            arg = C.eval_expr(self.store, s.arg)
            t0 = time.perf_counter()
            val = self.tools[s.name](*arg.split(SEP))
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
        return p.pad(req, self.backends[model].count(p.t.pad_open + p.t.pad_close) + extra
                     + self.backends[model].count(req))[0]
