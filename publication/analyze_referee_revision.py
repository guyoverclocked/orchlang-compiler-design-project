"""Reconcile every planned revision attempt without dropping negative results.

Pure JSON analysis; no OrchLang compiler/runtime imports. The local instrumentation
is a distinct measurement interface, not a trusted remote billing authority.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def usage(row):
    return sum(e[2] + 4 * e[3] for e in row["trace"] if e[0] == "llm")


def local_checks(local):
    errors = []
    if local["status"] != "completed":
        return errors
    expected = len(local["request_token_ids"]) + local["isolated_pad_tokens"]
    if local["reported_input"] != expected:
        errors.append("reported-input-vs-independent-request-length")
    prefill = sum(len(batch["token_ids"]) for batch in local["eval_submissions"] if batch["phase"] == "isolated_prefill")
    if prefill != local["isolated_pad_tokens"]:
        errors.append("isolated-prefill-submissions")
    yielded, returned = local["yielded_token_ids"], local["returned_ids"]
    generation_submissions = [token for batch in local["eval_submissions"] if batch["phase"] == "generation" for token in batch["token_ids"]]
    if generation_submissions != local["request_token_ids"] + yielded[:-1]:
        errors.append("eval-submissions-vs-request-and-decoding-prefix")
    if yielded[:len(returned)] != returned or len(yielded) - len(returned) not in (0, 1):
        errors.append("backend-yields-vs-returned-ids")
    if local["forced"] and (len(returned) != local["max_tokens"] or yielded != returned):
        errors.append("forced-generated-length")
    return errors


def analyze(directory):
    plan = json.loads((directory / "protocol.json").read_text(encoding="utf-8"))
    workflows = read_rows(directory / "workflow-attempts.jsonl")
    transparency = read_rows(directory / "transparency-attempts.jsonl")
    expected_workflow = set()
    for family, names in plan["workflow_selections"].items():
        for name, items in names.items():
            for temperature in plan["temperature"]:
                for index, item in enumerate(items):
                    for condition in ("orig", "ours"):
                        expected_workflow.add((family, name, temperature, item["id"], condition))
                    if name == "switch" and index == 0 and temperature == 0.0:
                        for condition in ("all_branches", "uniform", "random_padding"):
                            expected_workflow.add((family, name, temperature, item["id"], condition))
    actual_workflow = [(r["family"], r["workflow"], r["temperature"], r["id"], r["condition"]) for r in workflows]
    expected_transparency = {(family, stop, temperature, seed, prompt, cap, cap + gap)
                            for family in plan["workflow_selections"] for stop in ("declared", "extra-stop-OK")
                            for temperature in plan["temperature"] for seed in plan["seeds"]
                            for prompt in ("empty", "stop-seeking", "long-multilingual")
                            for cap in plan["transparency_caps"] for gap in plan["forced_gaps"]}
    actual_transparency = [(r["family"], r["stop_variant"], r["temperature"], r["seed"], r["prompt_class"], r["cap"], r["forced"]) for r in transparency]
    integrity_errors = []
    for name, actual, expected in (("workflows", actual_workflow, expected_workflow), ("transparency", actual_transparency, expected_transparency)):
        if set(actual) != expected or len(actual) != len(expected):
            integrity_errors.append(dict(group=name, missing=len(expected - set(actual)), foreign=len(set(actual) - expected), duplicates=len(actual) - len(set(actual))))
    pairs = defaultdict(dict)
    local_errors, local_count, eos_differences = [], 0, 0
    for row in workflows:
        if row["condition"] in ("orig", "ours"):
            pairs[(row["family"], row["workflow"], row["temperature"], row["id"])][row["condition"]] = row
        if row["status"] == "completed":
            if row["static_shape"] is not None and row["trace"] != row["static_shape"]:
                local_errors.append(dict(id=row["id"], condition=row["condition"], errors=["static-shape-mismatch"]))
            if len(row["execution_events"]) != len(row["local_observations"]):
                local_errors.append(dict(id=row["id"], errors=["event-count"]))
            model_trace = [event for event in row["trace"] if event[0] == "llm"]
            if len(model_trace) != len(row["local_observations"]):
                local_errors.append(dict(id=row["id"], errors=["trace-event-count"]))
            for event, local in zip(model_trace, row["local_observations"]):
                if event[2:] != [local.get("reported_input"), len(local.get("returned_ids", []))]:
                    local_errors.append(dict(id=row["id"], errors=["public-trace-vs-local-api-counts"]))
        for local in row["local_observations"]:
            local_count += 1
            eos_differences += len(local.get("yielded_token_ids", [])) > len(local.get("returned_ids", []))
            errors = local_checks(local)
            if errors:
                local_errors.append(dict(id=row["id"], condition=row["condition"], errors=errors))
        if row["status"] == "completed":
            for event, local in zip(row["execution_events"], row["local_observations"]):
                if (event["request_token_ids"] != local["request_token_ids"]
                    or event["generated_token_ids"] != local["returned_ids"]
                    or event["request_sha256"] != local["request_sha256"]
                    or event["visible_response"] != local["visible"]):
                    local_errors.append(dict(id=row["id"], errors=["runtime-vs-local-observation"]))
    pair_results, historical_comparisons = [], []
    for key, rows in sorted(pairs.items()):
        if set(rows) != {"orig", "ours"}:
            continue
        original, shaped = rows["orig"], rows["ours"]
        complete = original["status"] == shaped["status"] == "completed"
        pair_results.append(dict(family=key[0], workflow=key[1], temperature=key[2], id=key[3], completed=complete,
                                 saved_store_equal=complete and original["store"] == shaped["store"],
                                 all_store_equal=complete and original["all_store"] == shaped["all_store"],
                                 shaped_trace_matches=complete and shaped["trace"] == shaped["static_shape"],
                                 branches={"orig": original.get("store", {}), "ours": shaped.get("store", {})}))
        if original["temperature"] == 0.0 and original["historical_store"] is not None:
            old = original["historical_store"]
            overlap = sorted(set(old) & set(original.get("store", {})))
            historical_comparisons.append(dict(family=key[0], workflow=key[1], id=key[3], fields=overlap,
                                               equal=bool(overlap) and all(old[k] == original["store"][k] for k in overlap),
                                               limitation="Different frontend/version/selection seeds; descriptive divergence, not a matched-kernel equivalence theorem."))
    matrix = defaultdict(Counter)
    for row in transparency:
        group = matrix[(row["family"], row["stop_variant"], row["temperature"])]
        group["attempted"] += 1
        group["completed"] += row["status"] == "completed"
        group["equal"] += row.get("visible_equal", False)
        group["conformant"] += row.get("conformance", False)
        group["stop_observed"] += any(len(local.get("yielded_token_ids", [])) > len(local.get("returned_ids", [])) for local in row["local_observations"])
        for local in row["local_observations"]:
            local_count += 1
            eos_differences += len(local.get("yielded_token_ids", [])) > len(local.get("returned_ids", []))
            errors = local_checks(local)
            if errors:
                local_errors.append(dict(matrix_group=list(group), errors=errors))
    baselines = []
    for family in plan["workflow_selections"]:
        baseline_id = plan["workflow_selections"][family]["switch"][0]["id"]
        rows = [r for r in workflows if r["family"] == family and r["workflow"] == "switch" and r["temperature"] == 0.0 and r["id"] == baseline_id]
        original = next((r for r in rows if r["condition"] == "orig" and r["status"] == "completed"), None)
        for row in rows:
            baselines.append(dict(family=family, condition=row["condition"], status=row["status"],
                                  weighted_logical_usage=usage(row) if row["status"] == "completed" else None,
                                  saved_store_equal=bool(original and row.get("store") == original["store"]),
                                  events=len(row.get("trace", [])), model_calls=len(row["local_observations"])))
        if original:
            baselines.append(dict(family=family, condition="normalize-permitted-report-projection-only",
                                  status="no-extra-execution", weighted_logical_usage=usage(original), saved_store_equal=True,
                                  events=1, model_calls=len(original["local_observations"]),
                                  limitation="Changes the reporting contract; not faithful logical usage and not a server observer defense."))
    # Falsify the audit itself with a count corruption. Never edit retained data.
    sample = next(local for row in workflows for local in row["local_observations"] if local["status"] == "completed")
    damaged = {**sample, "reported_input": sample["reported_input"] + 1}
    negative_detected = bool(local_checks(damaged))
    return dict(schema="orchlang-referee-revision-summary-v1", protocol_version=plan["version"],
                raw_hashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.glob("*.jsonl")},
                completeness=dict(expected_workflow_executions=len(expected_workflow), observed_workflow_executions=len(workflows),
                                  expected_transparency_pairs=len(expected_transparency), observed_transparency_pairs=len(transparency),
                                  execution_complete=(directory / "execution-complete.json").exists(), integrity_errors=integrity_errors),
                workflow=dict(planned_pairs=plan["workflow_pairs"], completed_pairs=sum(r["completed"] for r in pair_results),
                              saved_store_equal=sum(r["saved_store_equal"] for r in pair_results),
                              all_store_equal=sum(r["all_store_equal"] for r in pair_results),
                              shaped_trace_matches=sum(r["shaped_trace_matches"] for r in pair_results), pair_results=pair_results,
                              historical_greedy_comparisons=historical_comparisons),
                transparency_matrix=[dict(family=key[0], stop_variant=key[1], temperature=key[2], **counts) for key, counts in sorted(matrix.items())],
                failed_workflow_attempts=[{k: r.get(k) for k in ("family", "workflow", "temperature", "id", "condition", "error")} for r in workflows if r["status"] != "completed"],
                transparency_mismatches=[{k: r.get(k) for k in ("family", "stop_variant", "temperature", "seed", "prompt_class", "cap", "forced", "status", "error")} for r in transparency if not r.get("visible_equal", False)],
                baselines=baselines, local_observer=dict(calls_checked=local_count, natural_stop_count_differences=eos_differences,
                    errors=local_errors, negative_count_control_detected=negative_detected,
                    scope="Trusted local eval/generate instrumentation; no gateway, invoice, timing or network attestation."))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("directory", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = analyze(args.directory)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k in ("completeness", "local_observer")}))
    raise SystemExit(int(bool(result["completeness"]["integrity_errors"] or result["local_observer"]["errors"]
                              or not result["completeness"]["execution_complete"])))
