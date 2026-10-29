"""Retain deterministic exact-accounting boundary and finite-program evidence."""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import platform
import random
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime.finite_reference import canonical, Unsupported
from runtime.replay_adapter import enumerate_replay
from runtime.token_accounting import PinnedTokenizer, StaticAccounting, ExactReplay, replay_contract, analyze_source


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def call(request,bind="response"):
    return dict(kind="call",model="m",request=request,bind=bind)


def programs():
    """Independent fixed workload grammar; these are stress cases, not applications."""
    retry = lambda body:dict(kind="retry",bound=3,body=body)
    branch = lambda left,right:dict(kind="if",guard="public",then=left,**{"else":right})
    dynamic = {"concat":["Input:",{"var":"x"}]}
    following = {"concat":["Next:",{"var":"first"}]}
    yield "literal-concat",[call({"concat":["hello","world"]})],{},{}
    yield "unicode-literal-chain",[call("é é 你好 🙂"),call("\r\n\x00\t")],{},{}
    yield "public-branch-maximum",[branch([call("x")],[call("hello world"),call("hello")])],{},{}
    yield "bounded-failure-retry",[retry([call("attempt")])],{},{}
    yield "dynamic-input",[call(dynamic)],{"x":8},{}
    yield "response-dependent-chain",[call("Seed:","first"),call(following)],{}, {"m":8}
    yield "repeated-dynamic-variable",[call({"concat":[{"var":"x"},"/",{"var":"x"}]})],{"x":8},{}
    yield "dynamic-branch-retry",[branch([retry([call(dynamic)])],
                                        [call("Seed:","first"),call(following)])],{"x":8},{"m":8}


def corpus(protocol):
    texts = ["", "hello world", "helloworld", "qzqzqzqz", "!!!!!!!!", "é", "é", "你好世界", "🙂",
             "a\r\nb\tc", "<|endoftext|>", "[CLS]", "\x00"*4096, " "+"x"*1024,
             "👩\u200d🔬", "\U0010ffff", "\u202eabc\u202c", "\ufeff\u200b\u2060"]
    texts += [chr(cp) for low,high in protocol["scalar_ranges_inclusive"] for cp in range(low,high+1)]
    rng = random.Random(protocol["seed"])
    alphabet = [chr(cp) for low,high in protocol["scalar_ranges_inclusive"] for cp in range(low,high+1)]
    alphabet += ["\U0001f469", "\U0001f52c", "\U0010ffff", "\uffff", "\U00010000"]
    texts += ["".join(rng.choices(alphabet,k=rng.choice(protocol["random_unicode_lengths"])))
              for _ in range(protocol["random_unicode_cases"])]
    # Preserve first-occurrence order while excluding duplicate corpus strings.
    texts = list(dict.fromkeys(texts))
    pairs = list(itertools.product(protocol["concatenation_fragments"],repeat=2))
    pairs += [("".join(rng.choices("abcdefghijklmnopqrstuvwxyz",k=rng.randint(1,8))),
               "".join(rng.choices("abcdefghijklmnopqrstuvwxyz",k=rng.randint(1,8))))
              for _ in range(protocol["random_ascii_concat_cases"])]
    return texts,pairs


def finite_programs(tokenizer,policy):
    c = replay_contract(tokenizer,"exact-development-v1",8)
    outcomes = [dict(text="é🙂",p="1/2",status="ok"),dict(text="",p="1/2",status="error")]
    contracts,kernels = {"m":c},{canonical(c):{"*":outcomes}}
    rows = []
    for name,program,inputs,response_caps in programs():
        for public in (False,True):
            env = dict(public=public,x="你好")
            try:
                bound = StaticAccounting(tokenizer,contracts,inputs,response_caps).analyze(program)
            except Unsupported as error:
                rows.append(dict(policy=policy,program=name,public=public,
                                 supported_static=False,reason=str(error)))
                continue
            adapter = ExactReplay(tokenizer,contracts,kernels,inputs,response_caps,bound.total_tokens)
            paths = enumerate_replay(adapter,program,env)
            violations = [p for p in paths if p["usage"]["total_tokens"] > bound.total_tokens]
            if violations:
                raise AssertionError("static bound violated")
            observations = []
            for path in paths:
                observations.append(dict(weight=str(path["weight"]),usage=path["usage"],
                                         requests=[dict(text=text,ids=tokenizer.ids(text)) for text in path["requests"]],
                                         trace=path["trace"]))
            rows.append(dict(policy=policy,program=name,public=public,supported_static=True,
                             source_program=program,input_byte_bounds=inputs,response_byte_caps=response_caps,
                             env=env,contract=c,kernel=outcomes,static_bound=asdict(bound),paths=observations,
                             violations=len(violations)))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizers",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args = parser.parse_args()
    protocol_path = ROOT/"bench/protocols/exact-accounting-development-v1.json"
    family_protocol_path = ROOT/"bench/protocols/tokenizers-development-v1.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    families = json.loads(family_protocol_path.read_text(encoding="utf-8"))["families"]
    artifacts = json.loads((args.tokenizers/"manifest.json").read_text(encoding="utf-8"))
    args.output.mkdir(parents=True,exist_ok=False)
    texts,pairs = corpus(protocol)
    text_rows,concat_rows,program_rows,source_rows,summaries = [],[],[],[],[]
    for family,specials in itertools.product(families,protocol["special_tokens"]):
        artifact = next(e for e in artifacts if e["id"] == family["id"])
        if any(artifact[k] != family[k] for k in ("id","repo","revision","license")):
            raise ValueError("tokenizer artifact metadata differs from family protocol")
        if artifact["sha256"] != protocol["tokenizer_sha256"][family["id"]]:
            raise ValueError("tokenizer digest differs from frozen exact-accounting protocol")
        t = PinnedTokenizer.from_file(args.tokenizers/artifact["file"],artifact["sha256"],
                                      protocol["tokenizers_version"],specials)
        policy = family["id"]+("/special" if specials else "/plain")
        cache = {}
        def encode(text):
            if text not in cache:
                cache[text] = t.ids(text)
            return cache[text]
        for index,text in enumerate(texts):
            ids = encode(text)
            text_rows.append(dict(policy=policy,case=index,text=text,utf8_bytes=len(text.encode("utf-8")),
                                  token_count=len(ids),ids=ids))
        counts = Counter()
        for index,(left,right) in enumerate(pairs):
            separate,joined = len(encode(left))+len(encode(right)),len(encode(left+right))
            relation = "greater" if joined>separate else ("less" if joined<separate else "equal")
            counts[relation] += 1
            concat_rows.append(dict(policy=policy,case=index,left=left,right=right,
                                    separate_tokens=separate,joined_tokens=joined,relation=relation,
                                    joined_ids=encode(left+right)))
        byte_applicable = family["id"] == "gpt2-bpe" and not specials
        byte_violations = sum(len(encode(text)) > len(text.encode("utf-8")) for text in texts)
        if byte_applicable and byte_violations:
            raise AssertionError("audited GPT2 UTF-8 upper bound violated")
        program_rows += finite_programs(t,policy)
        for source_path in protocol["source_files"]:
            source_result = analyze_source((ROOT/source_path).read_bytes(),t)
            source_rows.append(dict(policy=policy,source=source_path,result=source_result))
        summaries.append(dict(policy=policy,text_cases=len(texts),concat_cases=len(pairs),
                              concat_relations=dict(counts),byte_bound_applicable=byte_applicable,
                              byte_bound_violations=byte_violations if byte_applicable else None))
    test_env = dict(os.environ,ORCHLANG_TOKENIZER_DIR=str(args.tokenizers.resolve()),PYTHONUTF8="1")
    test_command = [sys.executable,"-X","utf8","-m","unittest","tests.test_token_accounting","-v"]
    tests = subprocess.run(test_command,cwd=ROOT,env=test_env,capture_output=True,text=True,encoding="utf-8")
    test_text = tests.stdout+tests.stderr
    if tests.returncode or "skipped" in test_text:
        raise AssertionError("required exact-accounting tests failed or skipped: "+test_text)
    test_count = int(re.search(r"Ran (\d+) tests?",test_text).group(1))
    cli_commands = []
    for artifact in artifacts:
        command = [sys.executable,"-X","utf8",str(ROOT/"scripts/exact_tokenizer.py"),
                   "--tokenizer",str((args.tokenizers/artifact["file"]).resolve()),
                   "--tokenizer-sha256",artifact["sha256"],"analyze-source",
                   "--source",str(ROOT/protocol["source_files"][0])]
        completed = subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding="utf-8")
        if completed.returncode:
            raise AssertionError("exact .orch CLI smoke test failed: "+completed.stderr)
        parsed = json.loads(completed.stdout)
        expected = next(row["result"]["static_bound"] for row in source_rows
                        if row["policy"] == artifact["id"]+"/plain" and
                        row["source"] == protocol["source_files"][0])
        if parsed["static_bound"] != expected:
            raise AssertionError("CLI source bound differs from direct source API")
        cli_commands.append(dict(command=command,exit_code=completed.returncode,
                                 stdout=completed.stdout,stderr=completed.stderr))
    supported = [r for r in program_rows if r["supported_static"]]
    summary = dict(schema_version="orchlang-exact-accounting-summary-v1",status="completed",
                   policies=summaries,text_observations=len(text_rows),concat_observations=len(concat_rows),
                   finite_program_configurations=len(program_rows),supported_static_configurations=len(supported),
                   unsupported_static_configurations=len(program_rows)-len(supported),
                   enumerated_paths=sum(len(r["paths"]) for r in supported),
                   static_bound_violations=sum(r["violations"] for r in supported),
                   required_tests=test_count,required_test_failures=0,required_test_skips=0,
                   source_observations=len(source_rows),cli_source_checks=len(cli_commands),
                   program_families=len(list(programs())),spent_usd="0.00",model_inference=False,
                   scope="boundary-stress-and-finite-text-execution; not external application validation")
    sources = ["runtime/token_accounting.py","runtime/replay_adapter.py","runtime/finite_reference.py",
               "runtime/source_gate.py","scripts/exact_tokenizer.py","scripts/exact_tokenizer_probe.py",
               "tests/test_token_accounting.py"]+protocol["source_files"]
    manifest = dict(status="completed",timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    source_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                    dirty_tree=bool(subprocess.check_output(["git","status","--porcelain"],cwd=ROOT,text=True)),
                    files={name:sha(ROOT/name) for name in sources},
                    protocol_sha256=sha(protocol_path),family_protocol_sha256=sha(family_protocol_path),
                    tokenizer_artifacts=artifacts,python=sys.version,platform=platform.platform(),
                    protocol_status=protocol["status"],spent_usd="0.00",model_inference=False)
    manifest["required_tests"] = dict(command=test_command,exit_code=tests.returncode,
                                    stdout=tests.stdout,stderr=tests.stderr,
                                    env={"ORCHLANG_TOKENIZER_DIR":str(args.tokenizers.resolve()),"PYTHONUTF8":"1"})
    manifest["cli_source_checks"] = cli_commands
    for name,value in (("manifest",manifest),("summary",summary),("tokens",text_rows),
                       ("concatenations",concat_rows),("programs",program_rows),("source",source_rows)):
        (args.output/(name+".json")).write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",
                                               encoding="utf-8",newline="\n")
    print(json.dumps(summary,indent=2))


if __name__ == "__main__":
    main()
