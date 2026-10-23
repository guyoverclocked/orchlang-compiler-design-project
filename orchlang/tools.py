"""Deterministic tool library available to workflows.

Tools are pure functions of their string arguments. They model the glue code
of the ported workflows (label normalization, list indexing, retrieval over a
fixed local corpus, arithmetic).
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Callable, Dict, List

WORD = re.compile(r"[A-Za-z0-9_]+")


def first_word(x: str) -> str:
    m = WORD.search(x.lower())
    return m.group(0) if m else ""


def label_in(x: str, options: str) -> str:
    """First option (comma-separated) mentioned in x, else the last option."""
    low = x.lower()
    opts = [o.strip() for o in options.split(",") if o.strip()]
    best, pos = opts[-1], None
    for o in opts:
        i = low.find(o)
        if i >= 0 and (pos is None or i < pos):
            best, pos = o, i
    return best


def yes_no(x: str) -> str:
    w = first_word(x)
    if w in ("yes", "y", "true", "pass", "relevant", "grounded", "correct", "funny"):
        return "yes"
    return "no"


def line(x: str, k: str) -> str:
    rows = [r.strip(" -*\t0123456789.)") for r in x.splitlines() if r.strip(" -*\t0123456789.)")]
    i = int(k)
    return rows[i] if 0 <= i < len(rows) else ""


def has_line(x: str, k: str) -> str:
    return "yes" if line(x, k) else "no"


def inc(k: str) -> str:
    return str(int(k or "0") + 1)


def join_lines(a: str, b: str) -> str:
    return (a + "\n" + b).strip()


def calc(expr: str) -> str:
    """Evaluate an arithmetic expression found in the text (digits and + - * / ( ) .)."""
    m = re.findall(r"[0-9\.\s\+\-\*/\(\)]{3,}", expr)
    for cand in reversed(m):
        cand = cand.strip()
        if not re.search(r"\d", cand):
            continue
        try:
            v = eval(cand, {"__builtins__": {}}, {})  # restricted to arithmetic characters
            if isinstance(v, (int, float)) and math.isfinite(v):
                return str(round(v, 6)).rstrip("0").rstrip(".") if isinstance(v, float) else str(v)
        except Exception:
            continue
    return ""


def final_number(x: str) -> str:
    nums = re.findall(r"-?\d[\d,]*\.?\d*", x)
    return nums[-1].replace(",", "").rstrip(".") if nums else ""


def contains(x: str, word: str) -> str:
    return "yes" if word.lower() in x.lower() else "no"


class Retriever:
    """BM25 over a fixed local corpus; returns the top-k passages joined."""

    def __init__(self, passages: List[str], k: int = 2):
        self.docs = passages
        self.k = k
        self.toks = [[w for w in WORD.findall(p.lower())] for p in passages]
        self.df = Counter(w for t in self.toks for w in set(t))
        self.avg = sum(len(t) for t in self.toks) / max(1, len(self.toks))

    def __call__(self, query: str) -> str:
        q = WORD.findall(query.lower())
        n = len(self.docs)
        scores = []
        for i, t in enumerate(self.toks):
            tf = Counter(t)
            s = 0.0
            for w in q:
                if w in tf:
                    idf = math.log(1 + (n - self.df[w] + 0.5) / (self.df[w] + 0.5))
                    s += idf * tf[w] * 2.2 / (tf[w] + 1.2 * (0.25 + 0.75 * len(t) / self.avg))
            scores.append((s, i))
        scores.sort(reverse=True)
        return "\n\n".join(self.docs[i] for _, i in scores[: self.k])


BASE: Dict[str, Callable[..., str]] = {
    "first_word": first_word, "label_in": label_in, "yes_no": yes_no, "line": line,
    "has_line": has_line, "inc": inc, "join_lines": join_lines, "calc": calc,
    "final_number": final_number, "contains": contains,
}


def contains_any(x: str, chars: str) -> str:
    return "yes" if any(c in x for c in chars) else "no"


def after(x: str, marker: str) -> str:
    i = x.lower().find(marker.lower())
    return x[i + len(marker):].strip() if i >= 0 else x.strip()


def field(x: str, key: str, fallback: str) -> str:
    for row in x.splitlines():
        if row.strip().lower().startswith(key.lower() + ":"):
            v = row.split(":", 1)[1].strip().strip("*").strip().lower()
            return v.split()[0].strip(".,") if v else fallback
    return fallback


def email_route(cls: str) -> str:
    """Routing of classify_intent in thinking-in-langgraph.mdx, lines 562-569."""
    intent, urgency = field(cls, "intent", ""), field(cls, "urgency", "")
    if intent == "billing" or urgency == "critical":
        return "review"
    if intent in ("question", "feature"):
        return "docs"
    if intent == "bug":
        return "bug"
    return "draft"


def needs_review(cls: str) -> str:
    """Post-draft routing of draft_response, lines 775-781."""
    intent, urgency = field(cls, "intent", ""), field(cls, "urgency", "medium")
    return "yes" if urgency in ("high", "critical") or intent == "complex" else "no"


def route_source(r: str) -> str:
    return "web" if "web" in r.lower() else "vectorstore"


def doc(docs: str, i: str) -> str:
    parts = [p for p in docs.split("\n\n") if p.strip()]
    k = int(i)
    return parts[k] if k < len(parts) else ""


def keep_relevant(*args: str) -> str:
    """Pairs (document, verdict); keeps documents graded yes."""
    kept = [args[i] for i in range(0, len(args) - 1, 2) if args[i + 1] == "yes" and args[i]]
    return "\n\n".join(kept)


def any_no(*verdicts: str) -> str:
    return "yes" if any(v != "yes" for v in verdicts) else "no"


def nonempty(x: str) -> str:
    return "yes" if x.strip() else "no"


def join_docs(a: str, b: str) -> str:
    return "\n\n".join(p for p in (a, b) if p.strip())


def section_name(row: str) -> str:
    return row.split("::")[0].strip() if "::" in row else row.strip()


def section_desc(row: str) -> str:
    return row.split("::", 1)[1].strip() if "::" in row else ""


def join_sections(acc: str, sec: str) -> str:
    return (acc + "\n\n---\n\n" + sec) if acc else sec


def calculator(out: str) -> str:
    """Executes the first `CALL <add|multiply|divide> <a> <b>` line."""
    m = re.search(r"CALL\s+(add|multiply|divide)\s*\(?\s*<?\s*(-?[\d\.]+)\s*>?\s*,?\s*<?\s*(-?[\d\.]+)", out, re.I)
    if not m:
        return "error: use CALL <add|multiply|divide> <a> <b> or FINAL: <answer>"
    op, a, b = m.group(1).lower(), float(m.group(2)), float(m.group(3))
    try:
        v = a + b if op == "add" else a * b if op == "multiply" else a / b
    except ZeroDivisionError:
        return "error: division by zero"
    return str(int(v)) if float(v).is_integer() else str(round(v, 6))


def history(h: str, out: str, obs: str) -> str:
    return (h + "\nAssistant: " + out.strip() + "\nTool result: " + obs).strip()


def final_seen(out: str) -> str:
    return "yes" if "final:" in out.lower() else "no"


BASE.update({
    "contains_any": contains_any, "after": after, "field": field, "email_route": email_route,
    "needs_review": needs_review, "route_source": route_source, "doc": doc, "keep_relevant": keep_relevant,
    "any_no": any_no, "nonempty": nonempty, "join_docs": join_docs, "section_name": section_name,
    "section_desc": section_desc, "join_sections": join_sections, "calculator": calculator,
    "history": history, "final_seen": final_seen,
})


def copy(x: str) -> str:
    return x


def class_check(llm_result: str) -> str:
    """promptflow/examples/flows/standard/conditional-flow-for-switch/class_check.py"""
    intentions_list = ["order_search", "product_info", "product_recommendation"]
    matches = [intention for intention in intentions_list if intention in llm_result.lower()]
    return matches[0] if matches else "unknown"


def eval_stop(ev: str) -> str:
    """route_joke: 'not funny' loops back; 'funny' accepts; anything else stops."""
    g = field(ev, "grade", "").lower()
    low = ev.lower()
    if "not funny" in low.split("feedback:")[0]:
        return "go"
    return "stop"


def json_yes(x: str) -> str:
    """First of the words yes/no in the grader output (JSON {"score": "yes"})."""
    m = re.search(r"\b(yes|no)\b", x.lower())
    return "yes" if m and m.group(1) == "yes" else "no"


BASE.update({"copy": copy, "qcopy": copy, "class_check": class_check, "eval_stop": eval_stop, "json_yes": json_yes})
