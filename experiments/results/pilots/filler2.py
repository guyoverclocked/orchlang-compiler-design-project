import json, sys, random
sys.path.insert(0,'/home/user/orchlang-compiler-design-project')
from orchlang import models as M, runtime as R, tools as T
prof = M.load_profiles(sys.argv[1])["llama1b"]
b = R.LlamaBackend(prof, n_ctx=2048)
t = prof.tmpl
INSTR = "Route the input to story, joke, or poem based on the user's request.\nRespond with exactly one word: poem, story, or joke."
def mk(req, filler_text, how):
    close = "<|eot_id|>"; gen = t.generation
    if how == "end":
        return req[:-len(gen)] + t.pad_open + filler_text + t.pad_close + gen
    if how == "start":
        i = len("<|begin_of_text|>")
        return req[:i] + t.pad_open + filler_text + t.pad_close + req[i:]
    i = req.index(close) + len(close)
    return req[:i] + t.pad_open + filler_text + t.pad_close + req[i:]
def fill(req, target, unit, how):
    lo, hi = 0, 3000
    while lo < hi:
        mid = (lo + hi) // 2
        if b.count(mk(req, unit * mid, how)) < target: lo = mid + 1
        else: hi = mid
    return mk(req, unit * lo, how)
rows = [json.loads(l) for l in open("experiments/data/routing.jsonl")]
random.Random(1).shuffle(rows)
fillers = {"dot": " .", "reserved": "<|reserved_special_token_10|>", "nl_dot": "\n."}
for how in ["start"]:
    for name, unit in fillers.items():
        agree = acc0 = acc1 = 0
        for r in rows[:20]:
            req = t.render([("system", INSTR), ("user", r["inputs"]["user_input"])])
            _, v0, n0 = b.generate(req, 4, 1, False)
            p = fill(req, n0 + 100, unit, how)
            _, v1, n1 = b.generate(p, 4, 1, False)
            l0, l1 = T.label_in(v0, "story,joke,poem"), T.label_in(v1, "story,joke,poem")
            agree += l0 == l1; acc0 += l0 == r["label"]; acc1 += l1 == r["label"]
        print(how, name, "agree", agree/20, "acc_orig", acc0/20, "acc_pad", acc1/20, "tokens", n1 - n0, flush=True)
