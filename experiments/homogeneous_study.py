"""Execute one immutable, post-correction full study with streaming API evidence."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments import run_workflow as runner
from experiments.referee_revision import InstrumentedBackend
from experiments.final_release import KEEP
from orchlang import runtime as R, assurance as A

PLAN = [(name, count, False) for name, count in
        (("switch",210),("routing",150),("chaining",150),("evaluator",100),
         ("email",152),("orchestrator",100),("calculator",100),("crag",150),("adaptive",60))]
PLAN += [(name,count,True) for name,count in (("switch",210),("email",152),("crag",150))]


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def worker(args):
    class StreamingBackend(InstrumentedBackend):
        def generate(self, *values, **options):
            try:
                return super().generate(*values, **options)
            finally:
                with (args.output / "local-calls.jsonl").open("a", encoding="utf-8") as stream:
                    for call in self.calls:
                        stream.write(json.dumps(dict(model=self.profile.key, **call)) + "\n")
                self.calls.clear()
    R.LlamaBackend = StreamingBackend
    workflow = (f"workflows/replication/{args.workflow}_qwen.orch" if args.replication
                else f"workflows/{args.workflow}.orch")
    sys.argv = ["run_workflow", "--workflow", workflow, "--data", f"experiments/data/{args.workflow}.jsonl",
                "--out", str(args.output), "--models", str(args.models), "--limit", str(args.limit),
                "--keep", KEEP[args.workflow], "--context", str(args.context)]
    if args.byte_bounded:
        sys.argv += ["--byte-bounded", "--response-bytes", str(args.response_bytes)]
    if args.workflow in ("crag", "adaptive"):
        sys.argv += ["--corpus", f"experiments/data/{args.workflow}_corpus.jsonl",
                     "--web", f"experiments/data/{args.workflow}_web.jsonl"]
    runner.main()


def campaign(args):
    args.output.mkdir(parents=True, exist_ok=False)
    identity = runner.source_checkout_identity(ROOT)
    if identity.get("git_dirty") or not identity.get("git_commit"):
        raise ValueError("a full campaign requires a clean immutable Git checkout")
    protocol = dict(schema="orchlang-homogeneous-full-study-v1", implementation=identity,
                    implementation_hashes=A.implementation_hashes(ROOT),
                    plan=[dict(workflow=n, pairs=c, replication=r) for n,c,r in PLAN],
                    expected_pairs=sum(c for _,c,_ in PLAN), byte_bounded=args.byte_bounded,
                    response_bytes_per_token=args.response_bytes if args.byte_bounded else None,
                    context=args.context, model_config_sha256=A.sha256(args.models),
                    backend_libraries={p.name:A.sha256(p) for p in Path(os.environ["ORCHLANG_GGML_BACKENDS"]).glob("*.dll")}
                      if os.environ.get("ORCHLANG_GGML_BACKENDS") else {},
                    failure_policy="retain all errors/mismatches; never filter completed denominators",
                    primary_stop_or_prompt_policy="unchanged source templates; repaired grader is a separate ablation")
    dump(args.output / "protocol.json", protocol)
    results = []
    for name,count,replication in PLAN:
        group = "replication" if replication else "main"
        target = args.output / group / name
        command = [sys.executable, str(Path(__file__).resolve()), "worker", "--workflow", name,
                   "--limit", str(count), "--models", str(args.models), "--output", str(target),
                   "--context", str(args.context)]
        if replication: command += ["--replication"]
        if args.byte_bounded: command += ["--byte-bounded", "--response-bytes", str(args.response_bytes)]
        print("START",group,name,count,flush=True)
        with (args.output / f"{group}-{name}.log").open("w",encoding="utf-8") as stream:
            result = subprocess.run(command,cwd=ROOT,env=os.environ,stdout=stream,stderr=subprocess.STDOUT)
        results.append(dict(workflow=name,group=group,expected=count,exit=result.returncode))
        dump(args.output / "progress.json", results)
        print("EXIT",group,name,result.returncode,flush=True)
        if result.returncode:
            raise SystemExit(result.returncode)
    dump(args.output / "execution-finished.json",dict(workers=results, expected_pairs=protocol["expected_pairs"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("campaign","worker"))
    ap.add_argument("--models",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--workflow")
    ap.add_argument("--replication",action="store_true")
    ap.add_argument("--limit",type=int,default=0)
    ap.add_argument("--byte-bounded",action="store_true")
    ap.add_argument("--context",type=int,default=4096)
    ap.add_argument("--response-bytes",type=int,default=128,
                    help="byte-bounded mode: maximum native token-piece bytes per visible token")
    args = ap.parse_args()
    args.models=args.models.resolve(); args.output=args.output.resolve()
    os.chdir(ROOT)
    (worker if args.mode=="worker" else campaign)(args)
