import sys, json, random, time
sys.path.insert(0, "/home/user/orchlang-compiler-design-project")
import pandas as pd
from huggingface_hub import hf_hub_download
from orchlang import models as M, runtime as R, tools as T
df = pd.read_parquet(hf_hub_download("fancyzhx/ag_news","data/test-00000-of-00001.parquet",repo_type="dataset"))
names = ["world","sports","business","technology"]
rng = random.Random(0); idx = rng.sample(range(len(df)), 80)
prof = M.load_profiles(sys.argv[1])
p = prof["qwen1.5b"]
b = R.LlamaBackend(p, n_ctx=2048)
tmpl = p.tmpl
def prompt(text):
    return tmpl.render([("system","Classify the news article into one of: world, sports, business, technology. Answer with one word."),("user",text)])
res = {}
fillers = [" .", " pad", " _"]
for fill in fillers:
    b.profile.filler = fill
    pad = R.Padder(b)
    agree=acc0=acc1=0
    t=time.time()
    for i in idx:
        text = df.text[i]; gold = names[df.label[i]]
        r = prompt(text)
        _, v0, n0 = b.generate(r, 4, 1, False)
        target = n0 + 150
        rp,_ = pad.pad(r, target)
        _, v1, n1 = b.generate(rp, 4, 1, True, cap=4)
        assert n1 == target
        l0, l1 = T.label_in(v0, ",".join(names)), T.label_in(v1, ",".join(names))
        agree += l0==l1; acc0 += l0==gold; acc1 += l1==gold
    res[fill] = dict(agree=agree/len(idx), acc_orig=acc0/len(idx), acc_padded=acc1/len(idx), secs=time.time()-t)
    print(repr(fill), res[fill], flush=True)
json.dump(res, open("filler_pilot.json","w"), indent=1)
