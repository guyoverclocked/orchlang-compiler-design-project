import json, sys, random
sys.path.insert(0,'/home/user/orchlang-compiler-design-project')
from orchlang import models as M, runtime as R, tools as T
prof = M.load_profiles(sys.argv[1])["llama1b"]
b = R.LlamaBackend(prof, n_ctx=2048)
t = prof.tmpl
def place(req, target, how):
    """Insert a padding turn of filler so the request has exactly target tokens."""
    close = "<|eot_id|>"
    gen = t.generation
    def mk(k):
        filler = prof.filler * k
        if how == "end":
            return req[:-len(gen)] + t.pad_open + filler + t.pad_close + gen
        if how == "after_system":
            i = req.index(close) + len(close)
            return req[:i] + t.pad_open + filler + t.pad_close + req[i:]
        i = req.index(close)
        return req[:i] + "\n" + filler + req[i:]
    k = max(0, target - b.count(mk(0)))
    return mk(k)
cases = []
rows = [json.loads(l) for l in open("experiments/data/routing.jsonl")]
random.Random(1).shuffle(rows)
for r in rows[:20]:
    cases.append(("routing", [("system","Route the input to story, joke, or poem based on the user's request.\nRespond with exactly one word: poem, story, or joke."),("user",r["inputs"]["user_input"])], r["label"], lambda v: T.label_in(v,"story,joke,poem"), 4))
rows = [json.loads(l) for l in open("experiments/data/switch.jsonl")]
random.Random(1).shuffle(rows)
SW = "There is a search bar in the mall APP and users can enter any query in the search bar.\n\nThe user may want to search for orders, view product information, or seek recommended products.\n\nTherefore, please classify user intentions into the following three types according to the query: product_recommendation, order_search, product_info\n\nPlease note that only the above three situations can be returned, and try not to include other return values."
for r in rows[:20]:
    cases.append(("switch", [("system",SW),("user","The user's query is "+r["inputs"]["query"])], r["label"], T.class_check, 32))
res = {}
for how in ["end", "after_system", "in_system"]:
    for name, msgs, gold, parse, cap in cases:
        req = t.render(msgs)
        _, v0, n0 = b.generate(req, cap, 1, False)
        p = place(req, n0 + 120, how)
        _, v1, _ = b.generate(p, cap, 1, False)
        d = res.setdefault((name, how), [0,0,0,0])
        d[0] += parse(v0) == parse(v1); d[1] += parse(v0) == gold; d[2] += parse(v1) == gold; d[3] += 1
        print(name, how, gold, repr(v0[:30]), repr(v1[:30]), flush=True)
for k, d in res.items():
    print(k, "agree %.2f acc_orig %.2f acc_pad %.2f n %d" % (d[0]/d[3], d[1]/d[3], d[2]/d[3], d[3]), flush=True)
