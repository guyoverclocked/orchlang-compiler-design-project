"""Independent text-valued interpreter for sequential OrchLang call kernels.

It reads the source rather than the production analyzer/IR, retains actual
responses, and implements root text inputs, prompts, calls and a text output.
Deployment replacement of mock models is explicit. Host predicates, scheduling,
JSON parsing and postprocessing belong to the benchmark composition, not here.
This interpreter is tested engineering code, not covered by the Lean theorem.
"""
import hashlib
import json
import re


TOKEN = re.compile(r'\s+|//[^\n]*|"(?:[^"\\]|\\.)*"|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|->|[{}():;,=]')


class Kernel:
    def __init__(self, source):
        self.sha256 = hashlib.sha256(source.encode()).hexdigest()
        self.tokens, pos = [], 0
        while pos < len(source):
            m = TOKEN.match(source, pos)
            if m is None:
                raise ValueError(f"unsupported kernel source at {pos}")
            t, pos = m.group(), m.end()
            if not t.isspace() and not t.startswith("//"):
                self.tokens.append(t)
        self.position, self.inputs, self.prompts, self.calls, self.models = 0, {}, {}, [], {}
        self.take("workflow"); self.name = self.ident(); self.take("budget")
        self.declared_mock_budget = int(self.take()); self.take("{")
        self.output = None
        while self.peek() != "}":
            kind = self.take()
            if kind == "input":
                name = self.ident(); self.take(":"); self.take("text"); self.take("max_tokens")
                self.inputs[name] = int(self.take()); self.take(";")
            elif kind == "model":
                name = self.ident(); self.take("="); self.take("mock"); self.take("(")
                revision = json.loads(self.take()); self.take(")"); self.take("max_tokens")
                cap = int(self.take()); self.take(";")
                self.models[name] = dict(revision=revision, cap=cap)
            elif kind == "prompt":
                name = self.ident(); self.take("("); parameters = []
                while self.peek() != ")":
                    parameters.append(self.ident()); self.take(":"); self.take("text")
                    if self.peek() != ")":
                        self.take(",")
                self.take(")"); self.take("->"); self.take("text"); self.take("=")
                template = json.loads(self.take()); self.take(";")
                names = re.findall(r'\{([A-Za-z_][A-Za-z_0-9]*)\}', template)
                if set(names) != set(parameters):
                    raise ValueError("template/parameter mismatch")
                self.prompts[name] = parameters, template
            elif kind == "let":
                name = self.ident(); self.take(":"); self.take("text"); self.take("="); self.take("call")
                prompt = self.ident(); self.take("("); arguments = []
                while self.peek() != ")":
                    t = self.take()
                    arguments.append(("literal", json.loads(t)) if t.startswith('"') else ("var", t))
                    if self.peek() != ")":
                        self.take(",")
                self.take(")"); self.take("using"); model = self.ident(); self.take(";")
                if len(arguments) != len(self.prompts[prompt][0]) or model not in self.models:
                    raise ValueError("invalid kernel call")
                self.calls.append(dict(bind=name, prompt=prompt, arguments=arguments, model=model))
            elif kind == "output":
                if self.output is not None:
                    raise ValueError("multiple outputs")
                self.output = self.ident(); self.take(";")
            else:
                raise ValueError("unsupported kernel statement: " + kind)
        self.take("}")
        if self.position != len(self.tokens) or self.output is None:
            raise ValueError("incomplete kernel")

    def peek(self):
        return self.tokens[self.position] if self.position < len(self.tokens) else "<eof>"

    def take(self, expected=None):
        t = self.peek()
        if t == "<eof>" or (expected is not None and t != expected):
            raise ValueError(f"expected {expected}, got {t}")
        self.position += 1
        return t

    def ident(self):
        t = self.take()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', t):
            raise ValueError("identifier required")
        return t

    def run(self, values, backend, schema=None):
        if set(values) != set(self.inputs) or any(not isinstance(v, str) for v in values.values()):
            raise ValueError("kernel text inputs mismatch")
        env = dict(values)
        for call in self.calls:
            parameters, template = self.prompts[call["prompt"]]
            args = [v if kind == "literal" else env[v] for kind, v in call["arguments"]]
            substitutions = dict(zip(parameters, args))
            rendered = re.sub(r'\{([A-Za-z_][A-Za-z_0-9]*)\}',
                              lambda m: substitutions[m[1]], template)
            env[call["bind"]] = backend.generate(prompt=rendered, schema=schema,
                upstream_cap=self.models[call["model"]]["cap"])
        self.last_env = env
        return env[self.output]
