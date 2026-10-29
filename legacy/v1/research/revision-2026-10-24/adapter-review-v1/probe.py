"""No-inference review probes of LocalModel admission/accounting edge cases."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from runtime.local_model import LocalModel


class Encoding:
    ids = [1]


class Tokenizer:
    def encode(self,*args,**kwargs):
        return Encoding()


def backend(fail=False):
    b = LocalModel.__new__(LocalModel)
    b.tokenizer = Tokenizer()
    b.model, b.lock = "stub-no-model", threading.RLock()
    b.begin(input_cap=512,output_cap=64,max_calls=1,seed=1)
    b.dispatched = []
    def api(path,body):
        b.dispatched.append(body)
        if fail:
            raise OSError("deliberate no-inference transport failure")
        return dict(response="",prompt_eval_count=1,eval_count=0,done_reason="stop")
    b.api = api
    return b


rows = []
for cap in [None,0,-1,0.5,False]:
    b = backend()
    try:
        b.generate(prompt="one",upstream_cap=cap)
        status,problem = "returned",None
    except Exception as caught:
        status,problem = "rejected",repr(caught)
    rows.append(dict(upstream_cap=cap,status=status,error=problem,
                     dispatched=len(b.dispatched),
                     num_predict=b.dispatched[0]["options"]["num_predict"] if b.dispatched else None))
b = backend(True)
try:
    b.generate(prompt="one")
except Exception:
    pass
result = dict(timestamp_utc=datetime.now(timezone.utc).isoformat(),
              source_sha256=hashlib.sha256((ROOT/"runtime/local_model.py").read_bytes()).hexdigest(),
              rows=rows,transport_failure_trace=b.trace,transport_failure_totals=b.totals(),
              model_inference=False,scope="stub transport confirms pre-dispatch validation and missing-usage behavior only")
path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("observations.json")
with path.open("x",encoding="utf-8",newline="\n") as stream:
    json.dump(result,stream,indent=2)
    stream.write("\n")
print(json.dumps(result,indent=2))
