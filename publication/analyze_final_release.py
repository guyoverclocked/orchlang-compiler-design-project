"""Audit uniform-release records and render only fully completed evidence."""
from collections import Counter
from copy import deepcopy
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from publication.audit_execution import audit_record
from publication.analyze_referee_revision import local_checks
from orchlang import models as M


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--models", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads((args.directory / "summary.json").read_text())
    assert summary["passed"] and summary["pairs"] == 24 and len(summary["workflows"]) == 12
    profiles = M.load_profiles(str(args.models))
    by_contract = {value.key: value for value in profiles.values()}
    tokenizers = {key: M.tokenizer_for(value.gguf) for key, value in by_contract.items()}
    identities, calls, records = set(), 0, 0
    table = []
    first = None
    for planned in summary["workflows"]:
        directory = args.directory / planned["group"] / planned["workflow"]
        manifest = json.loads((directory / "run-manifest.json").read_text())
        identities.add((manifest["git_commit"], json.dumps(manifest["implementation_sha256"], sort_keys=True)))
        original, shaped = rows(directory / "orig.jsonl"), rows(directory / "ours.jsonl")
        assert len(original) == len(shaped) == len(manifest["selected_ids"]) == 2
        assert len(set(manifest["selected_ids"])) == 2
        assert {r["id"] for r in original} == {r["id"] for r in shaped} == set(manifest["selected_ids"])
        assert all(a["store"] == b["store"] for a, b in zip(original, shaped))
        events = []
        for row in original + shaped:
            calls += audit_record(row, tokenizers, by_contract)
            records += 1
            events.extend(row["execution_events"])
            first = first or row
        local = json.loads((directory / "local-calls.json").read_text())
        assert len(events) == len(local) == planned["local_calls"]
        for observation in local:
            assert not local_checks(observation)
        event_keys = Counter((e["request_sha256"], e["seed"], tuple(e["request_token_ids"]),
                              tuple(e["generated_token_ids"]), e["visible_response"]) for e in events)
        local_keys = Counter((e["request_sha256"], e["seed"], tuple(e["request_token_ids"]),
                              tuple(e["returned_ids"]), e["visible"]) for e in local)
        assert event_keys == local_keys
        distinct = len({json.dumps([[e[0], e[1], e[2], e[3]] if e[0] == "llm" else [e[0], e[1]] for e in r["trace"]]) for r in shaped})
        assert distinct == 1
        table.append(f"{planned['group'].capitalize()}: {planned['workflow']} & 2 & 2 & {distinct} & {len(local)} " + r"\\")
    assert len(identities) == 1
    damaged = deepcopy(first)
    next(e for e in damaged["trace"] if e[0] == "llm")[2] += 1
    try:
        audit_record(damaged)
    except AssertionError:
        detected = True
    else:
        raise AssertionError("independent auditor missed altered count")
    diagnosis = []
    for row in rows(ROOT / "publication/evidence/completion/replication/crag/orig.jsonl"):
        normalized = []
        for event in row["execution_events"][:4]:
            text = event["visible_response"].strip()
            if text.startswith("```json") and text.endswith("```"):
                text = text[7:-3].strip()
            value = str(json.loads(text)["score"]).lower()
            normalized.append(value in ("yes", "1"))
        diagnosis.append("no" if all(normalized) else "yes")
    audit = dict(schema="orchlang-final-release-audit-v1", passed=True, records=records,
                 model_calls=calls, pairs=24, version_cohorts=len(identities),
                 commit=next(iter(identities))[0], count_tamper_detected=detected,
                 normalized_qwen_crag_search_counts=dict(Counter(diagnosis)),
                 full_corpus_rerun=False)
    target = args.directory / "independent-audit.json"
    with target.open("x", encoding="utf-8") as stream:
        json.dump(audit, stream, indent=2)
        stream.write("\n")
    generated = ROOT / "paper/generated"
    (generated / "final-release-table.tex").write_text("\n".join(table) + "\n", encoding="utf-8")
    (generated / "final-release-results.tex").write_text(
        f"\\newcommand{{\\finalReleasePairs}}{{24}}\n\\newcommand{{\\finalReleaseCalls}}{{{calls}}}\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
