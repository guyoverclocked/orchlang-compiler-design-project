"""Lowering, information-flow labels, exact token bounds, leak detection and
shaping strategies. Everything here is untrusted: a shaped program is accepted
only if the Lean validator in proof/ShapeCore.lean accepts it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from . import core as C
from . import syntax as S
from .models import PLACEHOLDER, Profile

PARAM_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
SEP = "\x1f"


@dataclass
class Program:
    workflow: S.Workflow
    slots: Dict[str, int]
    body: C.Stmt
    gamma: Dict[int, str]
    site_lines: Dict[int, int]
    site_caps: Dict[int, int]
    var_bounds: Dict[int, int] = field(default_factory=dict)
    output: Optional[int] = None

    @property
    def names(self) -> Dict[int, str]:
        return {v: k for k, v in self.slots.items()}

    def high_vars(self) -> List[int]:
        return sorted(x for x, l in self.gamma.items() if l == C.HIGH)


# ---------------------------------------------------------------- lowering

class Lowerer:
    def __init__(self, wf: S.Workflow, profiles: Dict[str, Profile]):
        self.wf = wf
        self.profiles = profiles
        self.slots: Dict[str, int] = {}
        self.models = {m.name: m for m in wf.models}
        self.prompts = {p.name: p for p in wf.prompts}
        self.tools = {t.name: t for t in wf.tools}
        self.site = 0
        self.site_lines: Dict[int, int] = {}
        self.site_caps: Dict[int, int] = {}
        for decls, code in ((wf.inputs, "E201"), (wf.models, "E201"), (wf.prompts, "E201"), (wf.tools, "E201")):
            seen = set()
            for d in decls:
                if d.name in seen:
                    raise S.OrchError(code, f"duplicate declaration {d.name}", d.line)
                seen.add(d.name)
        for i in wf.inputs:
            self.slots[i.name] = len(self.slots)

    def slot(self, name: str, line: int, define: bool = False) -> int:
        if name not in self.slots:
            if not define:
                raise S.OrchError("E202", f"{name} is not defined before use", line)
            if name in self.models or name in self.prompts or name in self.tools:
                raise S.OrchError("E201", f"{name} names a declaration", line)
            self.slots[name] = len(self.slots)
        return self.slots[name]

    def arg_expr(self, a: S.Arg, line: int) -> C.Expr:
        return C.ELit(a.value) if isinstance(a, S.Lit) else C.EVar(self.slot(a, line))

    def request(self, call: S.Call) -> C.Expr:
        if call.prompt not in self.prompts:
            raise S.OrchError("E220", f"unknown prompt {call.prompt}", call.line)
        if call.model not in self.models:
            raise S.OrchError("E241", f"unknown model {call.model}", call.line)
        p = self.prompts[call.prompt]
        if len(call.args) != len(p.params):
            raise S.OrchError("E221", f"{p.name} expects {len(p.params)} arguments", call.line)
        args = {name: self.arg_expr(a, call.line) for name, a in zip(p.params, call.args)}
        used = set()
        msgs = []
        for role, content in p.messages:
            def sub(m):
                if m.group(1) not in args:
                    raise S.OrchError("E222", f"placeholder {{{m.group(1)}}} is not a parameter", p.line)
                used.add(m.group(1))
                return PLACEHOLDER.format(m.group(1))
            msgs.append((role, PARAM_RE.sub(sub, content)))
        unused = set(p.params) - used
        if unused:
            raise S.OrchError("E222", f"unused parameters {sorted(unused)}", p.line)
        key = self.models[call.model].key
        rendered = self.profiles[key].tmpl.render(msgs)
        parts: List[C.Expr] = []
        for i, chunk in enumerate(rendered.split("\x00")):
            parts.append(args[chunk] if i % 2 else C.ELit(chunk))
        return C.concat(parts)

    def stmts(self, items: List[S.Stmt]) -> C.Stmt:
        return C.seq([self.stmt(s) for s in items])

    def guard(self, c: S.Cond) -> C.Guard:
        return C.Guard(c.op, self.slot(c.var, c.line), c.value)

    def stmt(self, s: S.Stmt) -> C.Stmt:
        if isinstance(s, S.Call):
            req = self.request(s)
            x = self.slot(s.target, s.line, define=True)
            self.site += 1
            self.site_lines[self.site] = s.line
            self.site_caps[self.site] = s.max_tokens
            return C.Call(self.site, x, self.models[s.model].key, req, None, s.max_tokens)
        if isinstance(s, S.ToolCall):
            if s.tool not in self.tools:
                raise S.OrchError("E242", f"unknown tool {s.tool}", s.line)
            if len(s.args) != len(self.tools[s.tool].params):
                raise S.OrchError("E243", f"{s.tool} arity mismatch", s.line)
            parts: List[C.Expr] = []
            for i, a in enumerate(s.args):
                if i:
                    parts.append(C.ELit(SEP))
                parts.append(self.arg_expr(a, s.line))
            arg = C.concat(parts)
            return C.Tool(self.slot(s.target, s.line, define=True), s.tool, arg)
        if isinstance(s, S.Const):
            return C.Tool(self.slot(s.target, s.line, define=True), "const", C.ELit(s.value))
        if isinstance(s, S.If):
            g = self.guard(s.cond)
            return C.Ite(g, self.stmts(s.then), self.stmts(s.otherwise))
        if isinstance(s, S.Repeat):
            if s.bound < 1:
                raise S.OrchError("P005", "repeat bound must be at least 1", s.line)
            g = self.guard(s.until)
            return C.Loop(s.bound, g, self.stmts(s.body), False)
        raise TypeError(s)


def infer_labels(body: C.Stmt, gamma: Dict[int, str]) -> Dict[int, str]:
    """Least flow-insensitive labelling satisfying the Lean discipline."""
    gamma = dict(gamma)
    changed = True

    def mark(x: int, lab: str):
        nonlocal changed
        if lab == C.HIGH and gamma.get(x, C.LOW) != C.HIGH:
            gamma[x] = C.HIGH
            changed = True

    def walk(s: C.Stmt, pc: str):
        if isinstance(s, C.Seq):
            walk(s.a, pc); walk(s.b, pc)
        elif isinstance(s, C.Call):
            mark(s.x, C.join(pc, C.expr_label(gamma, s.req)))
        elif isinstance(s, C.Tool):
            mark(s.x, C.join(pc, C.expr_label(gamma, s.arg)))
        elif isinstance(s, C.Ite):
            p2 = C.join(pc, gamma.get(s.g.x, C.LOW))
            walk(s.a, p2); walk(s.b, p2)
        elif isinstance(s, C.Loop):
            walk(s.body, C.join(pc, gamma.get(s.g.x, C.LOW)))

    while changed:
        changed = False
        walk(body, C.LOW)
    return gamma


def lower(wf: S.Workflow, profiles: Dict[str, Profile]) -> Program:
    lw = Lowerer(wf, profiles)
    body = lw.stmts(wf.body)
    if wf.output is None:
        raise S.OrchError("E270", "a workflow must declare one output")
    out = lw.slot(wf.output, 0)
    gamma = {lw.slots[i.name]: (C.HIGH if i.secret else C.LOW) for i in wf.inputs}
    gamma = infer_labels(body, gamma)
    for x in lw.slots.values():
        gamma.setdefault(x, C.LOW)
    prog = Program(wf, lw.slots, body, gamma, lw.site_lines, lw.site_caps, output=out)
    prog.var_bounds = var_bounds(prog, lw)
    return prog


# ---------------------------------------------------------------- bounds

def var_bounds(prog: Program, lw: Lowerer) -> Dict[int, int]:
    """Token bound of every variable: declared inputs, call caps, tool caps."""
    b: Dict[int, int] = {}
    for i in prog.workflow.inputs:
        b[prog.slots[i.name]] = i.max_tokens

    def walk(s):
        if isinstance(s, C.Seq):
            walk(s.a); walk(s.b)
        elif isinstance(s, C.Call):
            b[s.x] = max(b.get(s.x, 0), s.max_tokens)
        elif isinstance(s, C.Tool):
            cap = lw.tools[s.name].max_tokens if s.name in lw.tools else max(1, len(C.eval_expr({}, s.arg)))
            b[s.x] = max(b.get(s.x, 0), cap)
        elif isinstance(s, C.Ite):
            walk(s.a); walk(s.b)
        elif isinstance(s, C.Loop):
            walk(s.body)
    walk(prog.body)
    return b


def input_bound(call: C.Call, bounds: Dict[int, int], profile: Profile, tok) -> int:
    """Static bound on the padded request size, including the padding message
    wrapper; the runtime truncates and pads every request to exactly this."""
    total = 0
    parts = C.pieces(call.req)
    for p in parts:
        if isinstance(p, C.ELit):
            total += tok.count(p.value)
        else:
            total += bounds.get(p.x, 0)
    total += len(parts)  # one token of slack per boundary
    total += tok.count(profile.tmpl.pad_open + profile.tmpl.pad_close)
    return total


# ---------------------------------------------------------------- leak detection

@dataclass
class Finding:
    kind: str
    line: int
    detail: str


def detect_core(prog) -> List[Finding]:
    return detect(prog)


def detect(prog) -> List[Finding]:
    """Report every construct through which a secret can change the usage trace."""
    out: List[Finding] = []
    gamma = prog.gamma
    lines = getattr(prog, "site_lines", {})
    names = getattr(prog, "names", {}) if hasattr(prog, "slots") else {}

    def line_of(s) -> int:
        cs = C.calls(s)
        return lines.get(cs[0].site, 0) if cs else 0

    def walk(s, pc):
        if isinstance(s, C.Seq):
            walk(s.a, pc); walk(s.b, pc)
        elif isinstance(s, C.Call):
            lab = C.expr_label(gamma, s.req)
            if lab == C.HIGH and s.pad is None:
                out.append(Finding("secret-dependent-size", lines.get(s.site, 0),
                                   "request contains secret-derived text; input and output token counts may vary"))
            elif pc == C.HIGH and s.pad is None:
                out.append(Finding("secret-context-call", lines.get(s.site, 0),
                                   "call runs under secret control"))
        elif isinstance(s, C.Ite):
            p2 = C.join(pc, gamma.get(s.g.x, C.LOW))
            if p2 == C.HIGH and pc == C.LOW and C.shape(s) is None:
                out.append(Finding("secret-dependent-branch", line_of(s),
                                   f"branch on secret {names.get(s.g.x, s.g.x)} selects arms with different usage"))
            walk(s.a, p2); walk(s.b, p2)
        elif isinstance(s, C.Loop):
            p2 = C.join(pc, gamma.get(s.g.x, C.LOW))
            if p2 == C.HIGH and not s.padded:
                out.append(Finding("secret-dependent-loop", line_of(s),
                                   f"iteration count depends on secret {names.get(s.g.x, s.g.x)}"))
            walk(s.body, p2)
    walk(prog.body, C.LOW)
    return out


# ---------------------------------------------------------------- shaping

@dataclass
class Costs:
    w_in: float = 1.0
    w_out: float = 4.0
    w_tool: float = 1.0


def unit_of(s: C.Stmt):
    if isinstance(s, C.Call):
        return ("llm", s.model, s.pad[0], s.pad[1])
    if isinstance(s, C.Dummy):
        return ("llm", s.model, s.t, s.n)
    if isinstance(s, (C.Tool, C.DummyTool)):
        return ("tool", s.name)
    sh = C.shape(s)
    assert sh is not None, "high-context statement without static shape"
    return ("atomic", tuple(sh))


def unit_cost(u, costs: Costs) -> float:
    if u[0] == "llm":
        return costs.w_in * u[2] + costs.w_out * u[3]
    if u[0] == "tool":
        return costs.w_tool
    return sum(unit_cost(e, costs) for e in u[1])


def compatible(p, a) -> bool:
    if p[0] != a[0]:
        return False
    if p[0] == "llm":
        return p[1] == a[1]
    return p[1] == a[1]


def merge(p, a):
    if p[0] == "llm":
        return ("llm", p[1], max(p[2], a[2]), max(p[3], a[3]))
    return p


def align(profile: List, arm: List, costs: Costs):
    """Min-cost common supersequence of a profile and an arm. Returns the new
    profile and, for profile and arm positions, their new profile indices."""
    n, m = len(profile), len(arm)
    INF = float("inf")
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if i == 0 and j == 0:
                continue
            best, how = INF, None
            if i > 0 and j > 0 and compatible(profile[i - 1], arm[j - 1]):
                c = dp[i - 1][j - 1] + unit_cost(merge(profile[i - 1], arm[j - 1]), costs)
                if c < best:
                    best, how = c, "match"
            if i > 0:
                c = dp[i - 1][j] + unit_cost(profile[i - 1], costs)
                if c < best:
                    best, how = c, "p"
            if j > 0:
                c = dp[i][j - 1] + unit_cost(arm[j - 1], costs)
                if c < best:
                    best, how = c, "a"
            dp[i][j], back[i][j] = best, how
    i, j, ops = n, m, []
    while i or j:
        how = back[i][j]
        ops.append(how)
        if how == "match":
            i, j = i - 1, j - 1
        elif how == "p":
            i -= 1
        else:
            j -= 1
    ops.reverse()
    new, pmap, amap = [], [], []
    i = j = 0
    for how in ops:
        if how == "match":
            new.append(merge(profile[i], arm[j])); pmap.append(len(new) - 1); amap.append(len(new) - 1)
            i += 1; j += 1
        elif how == "p":
            new.append(profile[i]); pmap.append(len(new) - 1); i += 1
        else:
            new.append(arm[j]); amap.append(len(new) - 1); j += 1
    return new, pmap, amap


def dummies_for(u) -> List[C.Stmt]:
    if u[0] == "llm":
        return [C.Dummy(u[1], u[2], u[3])]
    if u[0] == "tool":
        return [C.DummyTool(u[1])]
    return [d for e in u[1] for d in dummies_for(e)]


def repad(item: C.Stmt, u) -> C.Stmt:
    if u[0] != "llm":
        return item
    if isinstance(item, C.Call):
        return replace(item, pad=(u[2], u[3]))
    return C.Dummy(u[1], u[2], u[3])


def rebuild(arms_items: List[List[C.Stmt]], profile: List, maps: List[List[int]]) -> List[C.Stmt]:
    out = []
    for items, mp in zip(arms_items, maps):
        at = {p: k for k, p in enumerate(mp)}
        stmts: List[C.Stmt] = []
        for p, u in enumerate(profile):
            if p in at:
                stmts.append(repad(items[at[p]], u))
            else:
                stmts.extend(dummies_for(u))
        out.append(C.seq(stmts))
    return out


def chain(s: C.Ite, gamma) -> Tuple[List[C.Guard], List[C.Stmt]]:
    """Flatten `if g1 A else if g2 B else C` into guards [g1, g2] and arms [A, B, C]."""
    guards, arms = [s.g], [s.a]
    rest = s.b
    while isinstance(rest, C.Ite):
        guards.append(rest.g)
        arms.append(rest.a)
        rest = rest.b
    arms.append(rest)
    return guards, arms


def rechain(guards, arms) -> C.Stmt:
    out = arms[-1]
    for g, a in zip(reversed(guards), reversed(arms[:-1])):
        out = C.Ite(g, a, out)
    return out


class Shaper:
    """Strategies:
    - ours: taint-guided padding, k-way min-cost alignment of secret arms.
    - padall: like ours but pads every call (no taint guidance).
    - naive: taint-guided padding, secret arms linearized (each arm pays for
      every other arm's calls as dummies, as in execute-both-branches).
    - uniform: every padded call of a model uses one global cell size.
    """

    def __init__(self, prog: Program, profiles, tokenizers, strategy="ours", costs=Costs()):
        self.prog, self.profiles, self.toks = prog, profiles, tokenizers
        self.strategy, self.costs = strategy, costs
        self.cell: Dict[str, Tuple[int, int]] = {}
        if strategy == "uniform":
            for c in C.calls(prog.body):
                t, n = self.natural_pad(c)
                a, b = self.cell.get(c.model, (0, 0))
                self.cell[c.model] = (max(a, t), max(b, n))

    def natural_pad(self, c: C.Call) -> Tuple[int, int]:
        prof = self.profiles[c.model]
        return input_bound(c, self.prog.var_bounds, prof, self.toks[c.model]), c.max_tokens

    def pad_of(self, c: C.Call) -> Tuple[int, int]:
        if self.strategy == "uniform":
            return self.cell[c.model]
        return self.natural_pad(c)

    def needs_pad(self, c: C.Call, pc: str) -> bool:
        if self.strategy == "padall":
            return True
        return C.join(pc, C.expr_label(self.prog.gamma, c.req)) == C.HIGH

    def run(self) -> C.Stmt:
        return self.walk(self.prog.body, C.LOW)

    def walk(self, s: C.Stmt, pc: str) -> C.Stmt:
        g = self.prog.gamma
        if isinstance(s, C.Seq):
            return C.Seq(self.walk(s.a, pc), self.walk(s.b, pc))
        if isinstance(s, C.Call):
            return replace(s, pad=self.pad_of(s)) if self.needs_pad(s, pc) else s
        if isinstance(s, C.Ite):
            p2 = C.join(pc, g.get(s.g.x, C.LOW))
            if p2 == C.LOW:
                return C.Ite(s.g, self.walk(s.a, p2), self.walk(s.b, p2))
            guards, arms = chain(s, g)
            arms = [self.walk(a, C.HIGH) for a in arms]
            return rechain(guards, self.align_arms(arms))
        if isinstance(s, C.Loop):
            p2 = C.join(pc, g.get(s.g.x, C.LOW))
            body = self.walk(s.body, p2)
            return C.Loop(s.n, s.g, body, p2 == C.HIGH or self.strategy == "padall" and C.shape(body) is not None)
        return s

    def align_arms(self, arms: List[C.Stmt]) -> List[C.Stmt]:
        items = [C.flatten(a) for a in arms]
        units = [[unit_of(i) for i in it] for it in items]
        if self.strategy == "naive":
            out = []
            for k, it in enumerate(items):
                before = [d for us in units[:k] for u in us for d in dummies_for(u)]
                after = [d for us in units[k + 1:] for u in us for d in dummies_for(u)]
                out.append(C.seq(before + list(it) + after))
            return out
        order = sorted(range(len(arms)), key=lambda k: -sum(unit_cost(u, self.costs) for u in units[k]))
        profile: List = []
        maps: Dict[int, List[int]] = {}
        for k in order:
            new, pmap, amap = align(profile, units[k], self.costs)
            for j in maps:
                maps[j] = [pmap[p] for p in maps[j]]
            maps[k] = amap
            profile = new
        return rebuild(items, profile, [maps[k] for k in range(len(arms))])


def static_cost(s: C.Stmt) -> Optional[Tuple[int, int, int]]:
    sh = C.shape(s)
    if sh is None:
        return None
    llm = [e for e in sh if e[0] == "llm"]
    return len(llm), sum(e[2] for e in llm), sum(e[3] for e in llm)
