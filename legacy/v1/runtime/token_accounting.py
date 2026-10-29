"""Pinned, exact *complete-request* accounting for the finite text executor.

This is a trusted Python implementation, separate from the C++ mock units and
the Lean resource-relation proof. No provider or chat serialization is inferred.
Only an explicitly identified raw-text tokenizer is supported. Dynamic static
bounds require UTF-8 byte contracts; input token counts are never added across
concatenation. A byte bound is available only for the audited GPT-2 artifact.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from .finite_reference import Unsupported, canonical
from .replay_adapter import Replay


TOKENIZERS_VERSION = "0.21.4"
GPT2_SHA256 = "8414cab924d8b9b33013f0d221c5862f365ee9be39c5c2bfae8a5a9e970478a6"


def natural(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(label + " must be a nonnegative integer")
    return value


def utf8_size(text):
    if not isinstance(text, str):
        raise ValueError("raw request/response must be text")
    # In particular, reject isolated surrogate code points before encoding.
    return len(text.encode("utf-8", errors="strict"))


class PinnedTokenizer:
    """A content- and library-version-bound encoder with explicit specials."""

    @classmethod
    def from_file(cls, path, expected_sha256, expected_version=TOKENIZERS_VERSION,
                  add_special_tokens=False):
        import tokenizers
        if tokenizers.__version__ != expected_version:
            raise Unsupported("tokenizers library version does not match the pin")
        if type(add_special_tokens) is not bool:
            raise ValueError("add_special_tokens must be Boolean")
        data = Path(path).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected_sha256:
            raise Unsupported("tokenizer artifact SHA-256 does not match the pin")
        result = cls()
        result.sha256, result.version = digest, expected_version
        result.add_special_tokens = add_special_tokens
        # Load the bytes that were hashed, avoiding a second path read.
        result._encoder = tokenizers.Tokenizer.from_str(data.decode("utf-8"))
        result._encoder.no_padding()
        result._encoder.no_truncation()
        result.identity = (f"hf-tokenizers/{expected_version}/sha256:{digest}/"
                           f"specials:{int(add_special_tokens)}/raw-text-v1")
        return result

    def ids(self, text):
        utf8_size(text)
        return self._encoder.encode(text, add_special_tokens=self.add_special_tokens).ids

    def count(self, text):
        return len(self.ids(text))

    def bound_utf8_bytes(self, maximum_bytes):
        natural(maximum_bytes, "UTF-8 byte bound")
        # Sufficient conditions are audited for this exact artifact and library:
        # no normalizer, byte-level BPE, no inserted prefix, specials disabled.
        # Each ordinary token consumes >=1 source byte; merges cannot increase
        # token count. The sole added token is nonempty and also consumes bytes.
        if (self.sha256 != GPT2_SHA256 or self.version != TOKENIZERS_VERSION or
                self.add_special_tokens):
            raise Unsupported("no audited UTF-8 byte bound for this tokenizer policy")
        return maximum_bytes

    def admit(self, text, maximum_tokens):
        natural(maximum_tokens, "input token ceiling")
        ids = self.ids(text)
        if len(ids) > maximum_tokens:
            raise ValueError("complete request exceeds exact input token ceiling")
        return ids

    def check_output(self, text, cap):
        natural(cap, "output token cap")
        count = self.count(text)
        if count > cap:
            raise ValueError("response exceeds exact output token cap")
        return count

    def provenance(self):
        return dict(identity=self.identity, sha256=self.sha256,
                    tokenizers_version=self.version,
                    add_special_tokens=self.add_special_tokens,
                    truncation=False, padding=False, serialization="raw-utf8-v1")


def replay_contract(tokenizer, revision, cap):
    natural(cap, "output token cap")
    if not isinstance(revision, str) or not revision:
        raise ValueError("a nonempty replay revision is required")
    return dict(provider="finite-replay", revision=revision,
                tokenizer=tokenizer.identity, serializer="raw-utf8-v1", cap=cap,
                sampling="explicit-table", error_policy="status-in-outcome",
                accounting="all-attempts-input-and-output", state="stateless")


@dataclass(frozen=True)
class Bound:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0

    def then(self, other):
        return Bound(*(a+b for a,b in zip(asdict(self).values(), asdict(other).values())))

    def alternative(self, other):
        return Bound(*(max(a,b) for a,b in zip(asdict(self).values(), asdict(other).values())))

    def repeat(self, count):
        return Bound(*(a*count for a in asdict(self).values()))


@dataclass(frozen=True)
class TextBound:
    # A literal remains exact until a response or externally supplied input is
    # substituted. Bytes are additive across valid UTF-8 string concatenation.
    exact: object
    bytes: object


class StaticAccounting:
    """Max/sum/bounded-retry analysis of the explicit finite JSON program.

    Responses have an exact token cap. A separate, runtime-enforced byte cap
    is needed only when response text feeds a later dynamic request. A token
    cap alone is deliberately never treated as a byte cap.
    """

    def __init__(self, tokenizer, contracts, input_byte_bounds=None,
                 response_byte_caps=None):
        self.tokenizer, self.contracts = tokenizer, contracts
        self.input_byte_bounds = dict(input_byte_bounds or {})
        self.response_byte_caps = dict(response_byte_caps or {})
        for name, count in self.input_byte_bounds.items():
            natural(count, "input byte bound for " + name)
        for name, count in self.response_byte_caps.items():
            if name not in contracts:
                raise ValueError("byte cap names an unknown model")
            natural(count, "response byte cap for " + name)
        for contract in contracts.values():
            canonical(contract)
            if contract["tokenizer"] != tokenizer.identity:
                raise Unsupported("contract tokenizer differs from the pinned encoder")

    def expression(self, term, env):
        if isinstance(term, str):
            return TextBound(term, utf8_size(term))
        if isinstance(term, dict) and set(term) == {"var"}:
            if term["var"] not in env:
                raise Unsupported("no text/byte contract for " + str(term["var"]))
            return env[term["var"]]
        if isinstance(term, dict) and set(term) == {"concat"}:
            parts = [self.expression(t, env) for t in term["concat"]]
            if all(p.exact is not None for p in parts):
                text = "".join(p.exact for p in parts)
                return TextBound(text, utf8_size(text))
            size = sum(p.bytes for p in parts) if all(p.bytes is not None for p in parts) else None
            return TextBound(None, size)
        raise Unsupported("unsupported accounting expression")

    def block(self, nodes, env, depth=0):
        if depth > 64:
            raise Unsupported("accounting nesting limit")
        result, env = Bound(), dict(env)
        for node in nodes:
            kind = node["kind"]
            if kind == "call":
                model = node["model"]
                c = self.contracts[model]
                request = self.expression(node["request"], env)
                if request.exact is not None:
                    # Count the final string once, never sum tokenized pieces.
                    count = self.tokenizer.count(request.exact)
                elif request.bytes is not None:
                    count = self.tokenizer.bound_utf8_bytes(request.bytes)
                else:
                    raise Unsupported("response-dependent request requires an enforced byte cap")
                cap = c["cap"]
                addition = Bound(count, cap, count+cap, 1)
                env[node["bind"]] = TextBound(None, self.response_byte_caps.get(model))
            elif kind == "if":
                left, _ = self.block(node["then"], env, depth+1)
                right, _ = self.block(node["else"], env, depth+1)
                addition = left.alternative(right)
            elif kind == "retry":
                count = natural(node["bound"], "retry bound")
                if count > 16:
                    raise Unsupported("retry bound outside executor range [0,16]")
                body, _ = self.block(node["body"], env, depth+1)
                addition = body.repeat(count)
            elif kind == "private_output":
                self.expression(node["value"], env)
                addition = Bound()
            else:
                raise Unsupported("unsupported accounting instruction")
            result = result.then(addition)
        return result, env

    def analyze(self, program):
        env = {name:TextBound(None, count) for name,count in self.input_byte_bounds.items()}
        return self.block(program, env)[0]


class ExactReplay(Replay):
    """Existing replay semantics with pinned complete-string token counting.

    Budget admission occurs before looking up/choosing the replay outcome. It
    reserves the declared output token cap, and bills each actual failed attempt.
    This executor is a finite replay backend, not a generative model adapter.
    """

    def __init__(self, tokenizer, contracts, kernels, input_byte_bounds=None,
                 response_byte_caps=None, budget_tokens=None, max_request_tokens=None):
        self.tokenizer = tokenizer
        self.input_byte_bounds = dict(input_byte_bounds or {})
        self.response_byte_caps = dict(response_byte_caps or {})
        self.budget_tokens, self.max_request_tokens = budget_tokens, max_request_tokens
        for name,count in self.input_byte_bounds.items():
            natural(count, "input byte bound for " + name)
        for value,label in ((budget_tokens,"budget"),(max_request_tokens,"request ceiling")):
            if value is not None:
                natural(value,label)
        for name,count in self.response_byte_caps.items():
            if name not in contracts:
                raise ValueError("byte cap names an unknown model")
            natural(count,"response byte cap for " + name)
        super().__init__(contracts, kernels)
        # Reject every violating alternative, even one never selected on a tape.
        for name,c in contracts.items():
            for outcomes in kernels[canonical(c)].values():
                for outcome in outcomes:
                    text = outcome["text"]
                    tokenizer.check_output(text, c["cap"])
                    if (name in self.response_byte_caps and
                            utf8_size(text) > self.response_byte_caps[name]):
                        raise ValueError("replay response exceeds its UTF-8 byte cap")

    def count(self, text, unit):
        if unit != self.tokenizer.identity:
            raise Unsupported("replay contract tokenizer does not match the pin")
        return self.tokenizer.count(text)

    def block(self, nodes, depth=0):
        for node in nodes:
            if node["kind"] == "call":
                request = self.text(node["request"])
                input_tokens = self.tokenizer.count(request)
                if self.max_request_tokens is not None:
                    self.tokenizer.admit(request, self.max_request_tokens)
                used = sum(event[2]+event[3] for event in self.trace)
                if (self.budget_tokens is not None and
                        used+input_tokens+self.contracts[node["model"]]["cap"] > self.budget_tokens):
                    raise ValueError("exact request plus output reservation exceeds remaining budget")
            super().block([node], depth)

    def run(self, program, env, tape):
        for name,cap in self.input_byte_bounds.items():
            if utf8_size(env[name]) > cap:
                raise ValueError("input exceeds declared UTF-8 byte bound: " + name)
        result = super().run(program, env, tape)
        result["usage"] = dict(input_tokens=sum(e[2] for e in result["trace"]),
                               output_tokens=sum(e[3] for e in result["trace"]),
                               calls=len(result["trace"]))
        result["usage"]["total_tokens"] = result["usage"]["input_tokens"]+result["usage"]["output_tokens"]
        return result


def analyze_source(data, tokenizer):
    """Conditional token bound for actual closed-request .orch source bytes.

    The source reader is trusted Python. Its mock backend identity is retained
    as source metadata, not relabeled as a deployed model. Source max_tokens is
    a declared output cap in the explicitly selected accounting policy; this
    command does not execute a primitive or establish its cap conformance.
    """
    from .source_gate import read_source
    try:
        source = read_source(data)
    except Unsupported as error:
        raise Unsupported("exact source analysis supports only closed requests; dynamic inputs, "
                          "responses, tools and retry require another adapter/byte contract: "+str(error)) from error
    calls = []

    def visit(node):
        kind = node[0]
        if kind == "skip":
            return Bound()
        if kind == "call":
            source_contract,request = json.loads(node[1]),node[2]
            ids = tokenizer.ids(request)
            cap = source_contract["cap"]
            calls.append(dict(source_contract=source_contract,request=request,
                              input_ids=ids,exact_input_tokens=len(ids),declared_output_cap=cap))
            return Bound(len(ids),cap,len(ids)+cap,1)
        if kind == "seq":
            return visit(node[1]).then(visit(node[2]))
        if kind == "branch":
            return visit(node[2]).alternative(visit(node[3]))
        raise Unsupported("unknown closed-source accounting constructor")

    bound = visit(source["program"])
    budget = source["declared_mock_budget"]
    return dict(format="orchlang-exact-source-accounting-v1",workflow=source["workflow"],
                source_sha256=source["source_sha256"],tokenizer=tokenizer.provenance(),
                accounting_mode="closed-source-conditional-static-bound",static_bound=asdict(bound),
                source_declared_budget=budget,within_budget=bound.total_tokens<=budget,calls=calls,
                output_cap_assumption="every attempt is capped in the selected tokenizer policy; not established by analysis",
                scope="trusted-source-reader-and-Python-accounting; no primitive execution or Lean/C++ cost correspondence")
