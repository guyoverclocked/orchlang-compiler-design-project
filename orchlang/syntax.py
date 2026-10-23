"""Lexer, parser and AST for OrchLang workflows.

A workflow declares labelled inputs, models, chat prompts and deterministic
tools, then a body of model calls, tool calls, routing and bounded loops.

    workflow Router {
      input query: text secret max_tokens 128;
      model m = "qwen2.5-0.5b";
      prompt route(q) = system "Classify..." user "{q}";
      let raw = call route(query) using m max_tokens 8;
      let label = tool first_word(raw);
      if label == "story" { ... } else if label == "joke" { ... } else { ... }
      output answer;
    }
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union


class OrchError(Exception):
    def __init__(self, code: str, message: str, line: int = 0, col: int = 0):
        super().__init__(f"{code} {line}:{col}: {message}")
        self.code, self.line, self.col = code, line, col


KEYWORDS = {
    "workflow", "input", "text", "secret", "public", "max_tokens", "model", "prompt",
    "system", "user", "assistant", "tool", "let", "call", "using", "if", "else",
    "repeat", "until", "output", "startswith",
}

TOKEN_RE = re.compile(r"""
    (?P<ws>[ \t\r\n]+)
  | (?P<comment>//[^\n]*)
  | (?P<string>"(?:[^"\\\n]|\\.)*")
  | (?P<int>[0-9]+)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>==|[{}();:,=])
""", re.VERBOSE)

ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


@dataclass
class Tok:
    kind: str
    value: str
    line: int
    col: int


def lex(src: str) -> List[Tok]:
    out: List[Tok] = []
    pos, line, col = 0, 1, 1
    while pos < len(src):
        m = TOKEN_RE.match(src, pos)
        if not m:
            raise OrchError("L001", f"unexpected character {src[pos]!r}", line, col)
        text = m.group(0)
        kind = m.lastgroup
        if kind == "string":
            body, value, i = text[1:-1], [], 0
            while i < len(body):
                if body[i] == "\\":
                    if body[i + 1] not in ESCAPES:
                        raise OrchError("L003", f"unsupported escape \\{body[i+1]}", line, col)
                    value.append(ESCAPES[body[i + 1]])
                    i += 2
                else:
                    value.append(body[i])
                    i += 1
            out.append(Tok("string", "".join(value), line, col))
        elif kind == "ident":
            out.append(Tok("kw" if text in KEYWORDS else "ident", text, line, col))
        elif kind in ("int", "op"):
            out.append(Tok(kind, text, line, col))
        nl = text.count("\n")
        if nl:
            line += nl
            col = len(text) - text.rfind("\n")
        else:
            col += len(text)
        pos = m.end()
    out.append(Tok("eof", "", line, col))
    return out


# ---------------------------------------------------------------- AST

@dataclass
class Input:
    name: str
    secret: bool
    max_tokens: int
    line: int = 0


@dataclass
class Model:
    name: str
    key: str
    line: int = 0


@dataclass
class Prompt:
    name: str
    params: List[str]
    messages: List[Tuple[str, str]]  # (role, template)
    line: int = 0


@dataclass
class ToolDecl:
    name: str
    params: List[str]
    max_tokens: int
    line: int = 0


Arg = Union[str, "Lit"]


@dataclass
class Lit:
    value: str


@dataclass
class Call:
    target: str
    prompt: str
    args: List[Arg]
    model: str
    max_tokens: int
    line: int = 0


@dataclass
class ToolCall:
    target: str
    tool: str
    args: List[Arg]
    line: int = 0


@dataclass
class Const:
    target: str
    value: str
    line: int = 0


@dataclass
class Cond:
    var: str
    op: str  # "eq" | "prefix"
    value: str
    line: int = 0


@dataclass
class If:
    cond: Cond
    then: List["Stmt"]
    otherwise: List["Stmt"]
    line: int = 0


@dataclass
class Repeat:
    bound: int
    until: Cond
    body: List["Stmt"]
    line: int = 0


Stmt = Union[Call, ToolCall, Const, If, Repeat]


@dataclass
class Workflow:
    name: str
    inputs: List[Input] = field(default_factory=list)
    models: List[Model] = field(default_factory=list)
    prompts: List[Prompt] = field(default_factory=list)
    tools: List[ToolDecl] = field(default_factory=list)
    body: List[Stmt] = field(default_factory=list)
    output: Optional[str] = None


# ---------------------------------------------------------------- parser

class Parser:
    def __init__(self, src: str):
        self.toks = lex(src)
        self.i = 0

    @property
    def cur(self) -> Tok:
        return self.toks[self.i]

    def take(self, kind: str, value: Optional[str] = None) -> Tok:
        t = self.cur
        if t.kind != kind or (value is not None and t.value != value):
            want = value or kind
            raise OrchError("P001", f"expected {want}, found {t.value or t.kind}", t.line, t.col)
        self.i += 1
        return t

    def at(self, kind: str, value: Optional[str] = None) -> bool:
        t = self.cur
        return t.kind == kind and (value is None or t.value == value)

    def ident(self) -> str:
        return self.take("ident").value

    def integer(self) -> int:
        return int(self.take("int").value)

    def parse(self) -> Workflow:
        self.take("kw", "workflow")
        wf = Workflow(self.ident())
        self.take("op", "{")
        while not self.at("op", "}"):
            self.item(wf)
        self.take("op", "}")
        self.take("eof")
        return wf

    def item(self, wf: Workflow) -> None:
        t = self.cur
        if self.at("kw", "input"):
            self.i += 1
            name = self.ident()
            self.take("op", ":")
            self.take("kw", "text")
            if self.at("kw", "secret"):
                self.i += 1
                secret = True
            else:
                self.take("kw", "public")
                secret = False
            self.take("kw", "max_tokens")
            wf.inputs.append(Input(name, secret, self.integer(), t.line))
            self.take("op", ";")
        elif self.at("kw", "model"):
            self.i += 1
            name = self.ident()
            self.take("op", "=")
            wf.models.append(Model(name, self.take("string").value, t.line))
            self.take("op", ";")
        elif self.at("kw", "prompt"):
            self.i += 1
            name = self.ident()
            params = self.params()
            self.take("op", "=")
            messages = []
            while self.cur.kind == "kw" and self.cur.value in ("system", "user", "assistant"):
                role = self.take("kw").value
                messages.append((role, self.take("string").value))
            if not messages:
                raise OrchError("P002", "a prompt needs at least one message", t.line, t.col)
            wf.prompts.append(Prompt(name, params, messages, t.line))
            self.take("op", ";")
        elif self.at("kw", "tool"):
            self.i += 1
            name = self.ident()
            params = self.params()
            self.take("kw", "max_tokens")
            wf.tools.append(ToolDecl(name, params, self.integer(), t.line))
            self.take("op", ";")
        elif self.at("kw", "output"):
            self.i += 1
            if wf.output is not None:
                raise OrchError("E271", "a workflow has exactly one output", t.line, t.col)
            wf.output = self.ident()
            self.take("op", ";")
        else:
            wf.body.append(self.stmt())

    def params(self) -> List[str]:
        self.take("op", "(")
        out = []
        if not self.at("op", ")"):
            out.append(self.ident())
            while self.at("op", ","):
                self.i += 1
                out.append(self.ident())
        self.take("op", ")")
        return out

    def args(self) -> List[Arg]:
        self.take("op", "(")
        out: List[Arg] = []
        if not self.at("op", ")"):
            out.append(self.arg())
            while self.at("op", ","):
                self.i += 1
                out.append(self.arg())
        self.take("op", ")")
        return out

    def arg(self) -> Arg:
        if self.at("string"):
            return Lit(self.take("string").value)
        return self.ident()

    def block(self) -> List[Stmt]:
        self.take("op", "{")
        out = []
        while not self.at("op", "}"):
            out.append(self.stmt())
        self.take("op", "}")
        return out

    def cond(self) -> Cond:
        t = self.cur
        var = self.ident()
        if self.at("op", "=="):
            self.i += 1
            op = "eq"
        else:
            self.take("kw", "startswith")
            op = "prefix"
        return Cond(var, op, self.take("string").value, t.line)

    def stmt(self) -> Stmt:
        t = self.cur
        if self.at("kw", "let"):
            self.i += 1
            target = self.ident()
            self.take("op", "=")
            if self.at("kw", "call"):
                self.i += 1
                prompt = self.ident()
                args = self.args()
                self.take("kw", "using")
                model = self.ident()
                self.take("kw", "max_tokens")
                n = self.integer()
                self.take("op", ";")
                return Call(target, prompt, args, model, n, t.line)
            if self.at("kw", "tool"):
                self.i += 1
                tool = self.ident()
                args = self.args()
                self.take("op", ";")
                return ToolCall(target, tool, args, t.line)
            value = self.take("string").value
            self.take("op", ";")
            return Const(target, value, t.line)
        if self.at("kw", "if"):
            self.i += 1
            cond = self.cond()
            then = self.block()
            otherwise: List[Stmt] = []
            if self.at("kw", "else"):
                self.i += 1
                otherwise = [self.stmt()] if self.at("kw", "if") else self.block()
            return If(cond, then, otherwise, t.line)
        if self.at("kw", "repeat"):
            self.i += 1
            bound = self.integer()
            self.take("kw", "until")
            cond = self.cond()
            return Repeat(bound, cond, self.block(), t.line)
        raise OrchError("P001", f"unexpected {t.value or t.kind}", t.line, t.col)


def parse(src: str) -> Workflow:
    return Parser(src).parse()
