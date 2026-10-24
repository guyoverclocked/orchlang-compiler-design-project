"""Independent closed-request source gate. Does not import the C++ analyzer.

Supported: one workflow, secret Boolean guards, lexical mock models, text-only
prompt parameters, literal call arguments, and literal outputs. No inputs,
response-dependent requests, reclassification, tools, prices, or retry syntax.
The source reader/serializer and hash binding are trusted Python, NOT proved.
The reconstructed finite core is checked by the executable Lean normalizer.
"""
import hashlib
import json
import re
from .finite_reference import Unsupported, canonical


def sha(data):
    return hashlib.sha256(data).hexdigest()


def lex(source):
    result, pos = [], 0
    pattern = re.compile(r'[ \t\r\n]+|//[^\n]*|"(?:[^"\\\n\r]|\\[nt"\\])*"|'
                         r'[A-Za-z_][A-Za-z_0-9]*|[0-9]+|->|[{}():;,=]')
    while pos < len(source):
        match = pattern.match(source, pos)
        if match is None:
            raise Unsupported(f"unsupported source token at character {pos}")
        token = match.group()
        if not token.isspace() and not token.startswith("//"):
            result.append(token)
        pos = match.end()
    return result


def sequence(nodes):
    if not nodes:
        return ["skip"]
    result = nodes[-1]
    for node in reversed(nodes[:-1]):
        result = ["seq", node, result]
    return result


def normalize(program):
    kind = program[0]
    if kind in {"skip", "call"}:
        return program
    if kind == "seq":
        a, b = normalize(program[1]), normalize(program[2])
        return None if a is None or b is None else [kind, a, b]
    if kind == "branch":
        a, b = normalize(program[2]), normalize(program[3])
        return a if a is not None and a == b else None
    raise Unsupported("unsupported core node")


class Reader:
    def __init__(self, source):
        self.tokens = lex(source)
        self.pos = 0
        self.guards = []
        self.actions = []
        self.scopes = [{}]

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else "<eof>"

    def take(self, expected=None):
        token = self.peek()
        if token == "<eof>" or (expected is not None and token != expected):
            raise Unsupported(f"expected {expected}, got {token}, token {self.pos}")
        self.pos += 1
        return token

    def ident(self):
        token = self.take()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", token):
            raise Unsupported("expected ASCII identifier")
        # Avoid differences with the production keyword lexer.
        if token in {"workflow", "budget", "input", "secret", "model", "mock", "max_tokens",
                     "prompt", "let", "call", "using", "output", "if", "else", "retry",
                     "text", "boolean", "true", "false", "tool", "require", "tokens",
                     "untrusted", "emit", "declassify", "endorse", "as", "because",
                     "integer", "decimal", "json", "cost_per_token"}:
            raise Unsupported("keyword cannot be an identifier")
        return token

    def natural(self):
        token = self.take()
        if not re.fullmatch(r"[0-9]+", token) or len(token) > 18:
            raise Unsupported("natural number outside source-gate range")
        return int(token)

    def string(self):
        token = self.take()
        if not token.startswith('"'):
            raise Unsupported("only literal text is supported")
        # lex admits exactly the production lexer's four escapes.
        try:
            return json.loads(token)
        except ValueError as error:
            raise Unsupported("invalid literal") from error

    def bind(self, name, value):
        if name in self.scopes[-1]:
            raise Unsupported("duplicate declaration")
        self.scopes[-1][name] = value

    def lookup(self, name, kind):
        for scope in reversed(self.scopes):
            if name in scope:
                value = scope[name]
                if value[0] != kind:
                    raise Unsupported("binding has wrong kind")
                return value[1]
        raise Unsupported("unbound identifier: " + name)

    def block(self, depth=0):
        if depth > 64:
            raise Unsupported("source nesting limit")
        self.take("{")
        self.scopes.append({})
        nodes = []
        while self.peek() != "}":
            tag = self.take()
            if tag == "secret":
                name = self.ident()
                self.take(":"); self.take("boolean"); self.take("max_tokens")
                if self.natural() != 1:
                    raise Unsupported("Boolean declaration bound must be 1")
                self.take(";")
                index = len(self.guards)
                self.guards.append(dict(id=index, name=name))
                self.bind(name, ("guard", index))
            elif tag == "model":
                name = self.ident()
                self.take("="); self.take("mock"); self.take("(")
                revision = self.string()
                self.take(")"); self.take("max_tokens")
                cap = self.natural()
                self.take(";")
                contract = dict(provider="finite-replay", revision=revision,
                                tokenizer="utf8-bytes-v1", serializer="raw-utf8-v1",
                                cap=cap, sampling="explicit-table", error_policy="status-in-outcome",
                                accounting="all-attempts-input-and-output", state="stateless")
                self.bind(name, ("model", contract))
            elif tag == "prompt":
                name = self.ident()
                self.take("(")
                params = []
                if self.peek() != ")":
                    while True:
                        param = self.ident()
                        self.take(":"); self.take("text")
                        if param in params:
                            raise Unsupported("duplicate prompt parameter")
                        params.append(param)
                        if self.peek() != ",":
                            break
                        self.take(",")
                self.take(")"); self.take("->"); self.take("text"); self.take("=")
                template = self.string()
                self.take(";")
                stripped = re.sub(r"\{([A-Za-z_][A-Za-z_0-9]*)\}", "", template)
                names = re.findall(r"\{([A-Za-z_][A-Za-z_0-9]*)\}", template)
                if ("{" in stripped or "}" in stripped or any(n not in params for n in names) or
                        any(p not in names for p in params)):
                    raise Unsupported("unknown/malformed template substitution")
                self.bind(name, ("prompt", (params, template)))
            elif tag == "let":
                name = self.ident()
                self.take(":"); self.take("text"); self.take("="); self.take("call")
                params, template = self.lookup(self.ident(), "prompt")
                self.take("(")
                values = []
                if self.peek() != ")":
                    while True:
                        values.append(self.string())
                        if self.peek() != ",":
                            break
                        self.take(",")
                self.take(")"); self.take("using")
                contract = self.lookup(self.ident(), "model")
                self.take(";")
                if len(params) != len(values):
                    raise Unsupported("prompt arity mismatch")
                substitutions = dict(zip(params, values))
                request = re.sub(r"\{([A-Za-z_][A-Za-z_0-9]*)\}",
                                 lambda m: substitutions[m[1]], template)
                action = ["call", canonical(contract), request]
                self.actions.append(action)
                nodes.append(action)
                self.bind(name, ("response", None))
            elif tag == "if":
                guard = self.lookup(self.ident(), "guard")
                left = self.block(depth + 1)
                self.take("else")
                right = self.block(depth + 1)
                nodes.append(["branch", guard, left, right])
            elif tag == "output":
                self.string(); self.take(";")
            else:
                raise Unsupported("statement outside closed-request fragment: " + tag)
        self.take("}")
        self.scopes.pop()
        return sequence(nodes)

    def read(self):
        self.take("workflow")
        workflow = self.ident()
        self.take("budget")
        budget = self.natural()
        program = self.block()
        if self.pos != len(self.tokens):
            raise Unsupported("only one complete workflow supported")
        return dict(workflow=workflow, declared_mock_budget=budget, program=program,
                    guards=self.guards, actions=self.actions)


def read_source(data):
    if len(data) > 1_000_000:
        raise Unsupported("source byte limit")
    result = Reader(data.decode("utf-8", errors="strict")).read()
    result["source_sha256"] = sha(data)
    return result


def issue(data):
    source = read_source(data)
    plan = normalize(source["program"])
    if plan is None:
        raise Unsupported("closed requests/contracts do not normalize to equal plans")
    return dict(format="orchlang-closed-request-v1", source_sha256=source["source_sha256"],
                program=source["program"], plan=plan)


def bind_certificate(data, certificate):
    if set(certificate) != {"format", "source_sha256", "program", "plan"}:
        raise Unsupported("unknown certificate fields")
    source = read_source(data)
    if (certificate["format"] != "orchlang-closed-request-v1" or
            certificate["source_sha256"] != source["source_sha256"] or
            certificate["program"] != source["program"]):
        raise Unsupported("certificate does not match independently reconstructed source")
    return [source["program"], certificate["plan"]]
