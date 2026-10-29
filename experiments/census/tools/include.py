# Expand verbatim-include markers in a Markdown template.
#   <<<INCLUDE repo_root|relpath|start|end|lang>>>   -> exact file lines start..end (1-based, inclusive)
#   <<<NBINCLUDE repo_root|relpath|start|end|lang>>> -> decoded notebook source for raw JSON lines start..end
# Usage: include.py template.md out.md
import sys, json, re

ROOTS = {
    "langgraph": "/home/user/langchain-ai/langgraph",
    "docs": "/home/user/langchain-ai/docs",
    "promptflow": "/home/user/microsoft/promptflow",
}

def file_lines(root, rel, a, b):
    L = open(f"{ROOTS[root]}/{rel}", encoding="utf-8").read().split("\n")
    return "\n".join(L[a - 1:b])

def nb_lines(root, rel, a, b):
    raw = open(f"{ROOTS[root]}/{rel}", encoding="utf-8").read().split("\n")
    out = []
    for i in range(a, b + 1):
        s = raw[i - 1].strip()
        if not s.startswith('"'):
            raise SystemExit(f"{rel}:{i} is not a JSON string line: {s[:60]}")
        s = s[:-1] if s.endswith(",") else s
        v = json.loads(s)
        out.append(v[:-1] if v.endswith("\n") else v)
    return "\n".join(out)

def expand(m, nb):
    root, rel, a, b, lang = m.group(1).split("|")
    a, b = int(a), int(b)
    body = nb_lines(root, rel, a, b) if nb else file_lines(root, rel, a, b)
    kind = "decoded notebook source, raw JSON lines" if nb else "lines"
    return f"_Verbatim from `{root}/{rel}` {kind} {a}-{b}:_\n\n```{lang}\n{body}\n```"

t = open(sys.argv[1], encoding="utf-8").read()
t = re.sub(r"<<<NBINCLUDE ([^>]+)>>>", lambda m: expand(m, True), t)
t = re.sub(r"<<<INCLUDE ([^>]+)>>>", lambda m: expand(m, False), t)
open(sys.argv[2], "w", encoding="utf-8").write(t)
