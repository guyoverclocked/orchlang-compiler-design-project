"""Core IR mirroring proof/ShapeCore.lean.

The Lean file is authoritative; these Python definitions are used by the
untrusted compiler and runtime, and every shaped program is re-validated by
the Lean checker (`orchlang.validate`).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Optional, Tuple, Union

HIGH, LOW = "high", "low"


def join(a: str, b: str) -> str:
    return HIGH if HIGH in (a, b) else LOW


# ---------------------------------------------------------------- expressions

@dataclass(frozen=True)
class ELit:
    value: str


@dataclass(frozen=True)
class EVar:
    x: int


@dataclass(frozen=True)
class EApp:
    a: "Expr"
    b: "Expr"


@dataclass(frozen=True)
class EEscape:
    value: "Expr"


@dataclass(frozen=True)
class ETrim:
    value: "Expr"


Expr = Union[ELit, EVar, EApp, EEscape, ETrim]


def escape_tool_arg(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\x1f", "\\s")


def concat(parts: List[Expr]) -> Expr:
    """Right-nested append; adjacent literals are merged."""
    merged: List[Expr] = []
    for p in parts:
        if isinstance(p, ELit) and p.value == "":
            continue
        if merged and isinstance(p, ELit) and isinstance(merged[-1], ELit):
            merged[-1] = ELit(merged[-1].value + p.value)
        else:
            merged.append(p)
    if not merged:
        return ELit("")
    out = merged[-1]
    for p in reversed(merged[:-1]):
        out = EApp(p, out)
    return out


def pieces(e: Expr) -> List[Expr]:
    if isinstance(e,ETrim):
        return pieces(e.value)  # sizing heuristic; the full request is admitted exactly
    if isinstance(e, EApp):
        return pieces(e.a) + pieces(e.b)
    return [e]


def eval_expr(store, e: Expr) -> str:
    if isinstance(e, ELit):
        return e.value
    if isinstance(e, EVar):
        return store.get(e.x, "")
    if isinstance(e, EEscape):
        return escape_tool_arg(eval_expr(store, e.value))
    if isinstance(e,ETrim):
        return eval_expr(store,e.value).strip()
    return eval_expr(store, e.a) + eval_expr(store, e.b)


def expr_label(gamma, e: Expr) -> str:
    if isinstance(e, ELit):
        return LOW
    if isinstance(e, EVar):
        return gamma.get(e.x, LOW)
    if isinstance(e, (EEscape,ETrim)):
        return expr_label(gamma, e.value)
    return join(expr_label(gamma, e.a), expr_label(gamma, e.b))


@dataclass(frozen=True)
class Guard:
    kind: str  # "eq" | "prefix"
    x: int
    value: str


def holds(store, g: Guard) -> bool:
    v = store.get(g.x, "")
    return v == g.value if g.kind == "eq" else v.startswith(g.value)


# ---------------------------------------------------------------- statements

@dataclass(frozen=True)
class Skip:
    pass


@dataclass(frozen=True)
class Seq:
    a: "Stmt"
    b: "Stmt"


@dataclass(frozen=True)
class Call:
    site: int
    x: int
    model: str
    req: Expr
    pad: Optional[Tuple[int, int]] = None
    max_tokens: int = 0  # the call's own visible cap (`cap` in the Lean IR)


@dataclass(frozen=True)
class Tool:
    x: int
    name: str
    arg: Expr


@dataclass(frozen=True)
class Dummy:
    model: str
    t: int
    n: int


@dataclass(frozen=True)
class DummyTool:
    name: str


@dataclass(frozen=True)
class Ite:
    g: Guard
    a: "Stmt"
    b: "Stmt"


@dataclass(frozen=True)
class Loop:
    n: int
    g: Guard
    body: "Stmt"
    padded: bool = False


Stmt = Union[Skip, Seq, Call, Tool, Dummy, DummyTool, Ite, Loop]

# events: ("llm", model, input, output) | ("tool", name)
Event = Tuple


def seq(items: List[Stmt]) -> Stmt:
    items = [s for s in items if not isinstance(s, Skip)]
    if not items:
        return Skip()
    out = items[-1]
    for s in reversed(items[:-1]):
        out = Seq(s, out)
    return out


def flatten(s: Stmt) -> List[Stmt]:
    if isinstance(s, Seq):
        return flatten(s.a) + flatten(s.b)
    if isinstance(s, Skip):
        return []
    return [s]


def shape(s: Stmt) -> Optional[List[Event]]:
    if isinstance(s, Skip):
        return []
    if isinstance(s, Seq):
        a, b = shape(s.a), shape(s.b)
        return None if a is None or b is None else a + b
    if isinstance(s, Call):
        return None if s.pad is None else [("llm", s.model, s.pad[0], s.pad[1])]
    if isinstance(s, Tool):
        return [("tool", s.name)]
    if isinstance(s, Dummy):
        return [("llm", s.model, s.t, s.n)]
    if isinstance(s, DummyTool):
        return [("tool", s.name)]
    if isinstance(s, Ite):
        a, b = shape(s.a), shape(s.b)
        return a if a is not None and a == b else None
    if isinstance(s, Loop):
        if not s.padded:
            return None
        body = shape(s.body)
        return None if body is None else body * s.n
    raise TypeError(s)


def erase(s: Stmt) -> Stmt:
    if isinstance(s, Seq):
        return Seq(erase(s.a), erase(s.b))
    if isinstance(s, Call):
        return replace(s, pad=None)
    if isinstance(s, (Dummy, DummyTool)):
        return Skip()
    if isinstance(s, Ite):
        return Ite(s.g, erase(s.a), erase(s.b))
    if isinstance(s, Loop):
        return Loop(s.n, s.g, erase(s.body), False)
    return s


def wt(gamma, pc: str, s: Stmt) -> bool:
    """Python mirror of the Lean padding discipline (for diagnostics only)."""
    if isinstance(s, Seq):
        return wt(gamma, pc, s.a) and wt(gamma, pc, s.b)
    if isinstance(s, Call):
        lab = join(pc, expr_label(gamma, s.req))
        target_ok = lab == LOW or gamma.get(s.x, LOW) == HIGH
        return target_ok and (lab == LOW or s.pad is not None)
    if isinstance(s, Tool):
        lab = join(pc, expr_label(gamma, s.arg))
        return lab == LOW or gamma.get(s.x, LOW) == HIGH
    if isinstance(s, Ite):
        p2 = join(pc, gamma.get(s.g.x, LOW))
        return wt(gamma, p2, s.a) and wt(gamma, p2, s.b) and (p2 == LOW or shape(s) is not None)
    if isinstance(s, Loop):
        p2 = join(pc, gamma.get(s.g.x, LOW))
        return wt(gamma, p2, s.body) and (p2 == LOW or (s.padded and shape(s.body) is not None))
    return True


# ---------------------------------------------------------------- JSON (Lean format)

def expr_json(e: Expr):
    if isinstance(e, ELit):
        return ["lit", e.value]
    if isinstance(e, EVar):
        return ["var", e.x]
    if isinstance(e, EEscape):
        return ["escape", expr_json(e.value)]
    if isinstance(e,ETrim):
        return ["trim",expr_json(e.value)]
    return ["app", expr_json(e.a), expr_json(e.b)]


def stmt_json(s: Stmt):
    if isinstance(s, Skip):
        return ["skip"]
    if isinstance(s, Seq):
        return ["seq", stmt_json(s.a), stmt_json(s.b)]
    if isinstance(s, Call):
        return ["call", s.site, s.x, s.model, s.max_tokens, expr_json(s.req), list(s.pad) if s.pad else None]
    if isinstance(s, Tool):
        return ["tool", s.x, s.name, expr_json(s.arg)]
    if isinstance(s, Dummy):
        return ["dummy", s.model, s.t, s.n]
    if isinstance(s, DummyTool):
        return ["dummyTool", s.name]
    if isinstance(s, Ite):
        return ["ite", [s.g.kind, s.g.x, s.g.value], stmt_json(s.a), stmt_json(s.b)]
    if isinstance(s, Loop):
        return ["loop", s.n, [s.g.kind, s.g.x, s.g.value], stmt_json(s.body), s.padded]
    raise TypeError(s)


def calls(s: Stmt) -> List[Call]:
    if isinstance(s, Seq):
        return calls(s.a) + calls(s.b)
    if isinstance(s, Call):
        return [s]
    if isinstance(s, Ite):
        return calls(s.a) + calls(s.b)
    if isinstance(s, Loop):
        return calls(s.body)
    return []
