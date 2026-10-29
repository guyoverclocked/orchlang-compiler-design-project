"""Count raw requests or execute finite text programs using a pinned tokenizer.

Example: python scripts/exact_tokenizer.py --tokenizer tokenizer.json
  --tokenizer-sha256 SHA256 count --text-file request.txt
No credentials, network requests or model inference are performed.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime.finite_reference import canonical
from runtime.replay_adapter import enumerate_replay
from runtime.token_accounting import PinnedTokenizer, StaticAccounting, ExactReplay, replay_contract, analyze_source


def case_objects(case, tokenizer):
    if case.get("format") != "orchlang-exact-replay-v1":
        raise ValueError("unsupported exact replay input format")
    contracts, kernels, response_caps = {}, {}, {}
    for name,model in case["models"].items():
        contract = replay_contract(tokenizer, model["revision"], model["max_tokens"])
        contracts[name] = contract
        key, table = canonical(contract), case["kernels"][name]
        if key in kernels and kernels[key] != table:
            raise ValueError("model aliases disagree on their semantic replay kernel")
        kernels[key] = table
        if "max_output_bytes" in model:
            response_caps[name] = model["max_output_bytes"]
    return contracts, kernels, response_caps


def execute_case(case, tokenizer, runtime_only=False):
    contracts,kernels,response_caps = case_objects(case,tokenizer)
    input_bounds = case.get("input_byte_bounds", {})
    if runtime_only:
        bound = None
        budget = case.get("budget_tokens")
        if type(budget) is not int or budget < 0:
            raise ValueError("runtime-only admission requires an explicit nonnegative budget_tokens")
    else:
        bound = StaticAccounting(tokenizer,contracts,input_bounds,response_caps).analyze(case["program"])
        budget = case.get("budget_tokens", bound.total_tokens)
        if type(budget) is not int or budget < bound.total_tokens:
            raise ValueError("declared budget is below the derived whole-program token bound")
    adapter = ExactReplay(tokenizer,contracts,kernels,input_bounds,response_caps,budget,
                          case.get("max_request_tokens"))
    paths = enumerate_replay(adapter,case["program"],case.get("env",{}))
    for path in paths:
        if bound is not None and path["usage"]["total_tokens"] > bound.total_tokens:
            raise AssertionError("execution exceeds derived static bound")
        path["weight"] = str(path["weight"])
        path["requests"] = [dict(text=text,ids=tokenizer.ids(text),
                                  input_tokens=tokenizer.count(text)) for text in path["requests"]]
    return dict(format="orchlang-exact-accounting-result-v1", tokenizer=tokenizer.provenance(),
                static_bound=asdict(bound) if bound is not None else None,
                accounting_mode="runtime-admission" if runtime_only else "whole-program-static-bound",
                budget_tokens=budget, paths=paths,
                scope="trusted-python-finite-text-executor; not C++ source certification or provider billing")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--tokenizer-sha256", required=True)
    parser.add_argument("--tokenizers-version", default="0.21.4")
    parser.add_argument("--special-tokens", action="store_true")
    commands = parser.add_subparsers(dest="command",required=True)
    count = commands.add_parser("count",help="encode one complete raw request")
    count.add_argument("--text-file",type=Path,required=True)
    run = commands.add_parser("run",help="analyze and enumerate a finite text program")
    run.add_argument("--case",type=Path,required=True)
    run.add_argument("--runtime-only",action="store_true",
                     help="enforce exact per-call admission without claiming a static source bound")
    source = commands.add_parser("analyze-source",help="derive a conditional bound for closed-request .orch source")
    source.add_argument("--source",type=Path,required=True)
    for sub in (count,run,source):
        sub.add_argument("--output",type=Path)
    args = parser.parse_args()
    tokenizer = PinnedTokenizer.from_file(args.tokenizer,args.tokenizer_sha256,
                                          args.tokenizers_version,args.special_tokens)
    if args.command == "count":
        # Preserve every newline byte; read_text() would normalize CRLF.
        text = args.text_file.read_bytes().decode("utf-8",errors="strict")
        ids = tokenizer.ids(text)
        result = dict(tokenizer=tokenizer.provenance(),text=text,ids=ids,input_tokens=len(ids))
    elif args.command == "run":
        result = execute_case(json.loads(args.case.read_text(encoding="utf-8")),tokenizer,args.runtime_only)
    else:
        result = analyze_source(args.source.read_bytes(),tokenizer)
    data = json.dumps(result,indent=2,ensure_ascii=False)+"\n"
    if args.output:
        # Do not silently replace retained observations.
        with args.output.open("x",encoding="utf-8",newline="\n") as stream:
            stream.write(data)
    else:
        print(data,end="")


if __name__ == "__main__":
    main()
