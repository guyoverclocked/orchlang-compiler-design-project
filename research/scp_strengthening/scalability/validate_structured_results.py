#!/usr/bin/env python3
"""Regression-check version-separated summaries and validate frozen study rows."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import sys

from run_structured_study import PREOPT_SAMPLE, _summarize_by_case

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RESULTS = ROOT / "output/scp_strengthening/scalability/structured_results.json"
DEFAULT_MANIFEST = ROOT / "output/scp_strengthening/scalability/frozen_inputs.json"
DEFAULT_REPORTS = ROOT / "output/scp_strengthening/scalability/reports"


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def aggregation_regression() -> None:
    """Exercise the real aggregator on tiny version-separated synthetic rows."""
    rows: list[dict] = []
    samples = {
        ("toy_equal", "current"): [("proved_equal", 1.0), ("proved_equal", 2.0), ("proved_equal", 3.0)],
        ("toy_equal", "5aa-preoptimization"): [("proved_equal", 9.0), ("proved_equal", 10.0), ("proved_equal", 11.0)],
        ("toy_unequal", "current"): [("unequal", 3.0), ("unknown", 100.0), ("unequal", 5.0)],
        ("toy_unequal", "5aa-preoptimization"): [("unequal", 13.0), ("unknown", 100.0), ("unequal", 15.0)],
        ("toy_unknown", "current"): [("unknown", 21.0), ("unknown", 22.0), ("unknown", 23.0)],
        ("toy_unknown", "5aa-preoptimization"): [("unknown", 31.0), ("unknown", 32.0), ("unknown", 33.0)],
    }
    for (case_id, implementation), entries in samples.items():
        status = entries[0][0]
        rows.append({"case_id": case_id, "implementation": implementation,
                     "operation": "exact_producer", "run_id": "warmup-1",
                     "warmup": True, "status": status, "analysis_seconds": 99.0})
        for index, (status, seconds) in enumerate(entries, start=1):
            rows.append({"case_id": case_id, "implementation": implementation,
                         "operation": "exact_producer", "run_id": f"rep-{index}",
                         "warmup": False, "status": status,
                         "analysis_seconds": seconds})

    grouped = _summarize_by_case(rows)
    _check(len(grouped) == 6,
           f"synthetic regression expected six version/case groups, got {len(grouped)}")
    expected_medians = {
        "toy_equal/current/exact_producer": 2.0,
        "toy_equal/5aa-preoptimization/exact_producer": 10.0,
        "toy_unequal/current/exact_producer": 4.0,
        "toy_unequal/5aa-preoptimization/exact_producer": 14.0,
    }
    for key, median in expected_medians.items():
        expected_samples = 2 if "toy_unequal" in key else 3
        _check(grouped[key]["latency_samples_used"] == expected_samples,
               f"synthetic completed sample count mismatch for {key}")
        _check(grouped[key]["latency_median_seconds"] == median,
               f"synthetic version-separated median mismatch for {key}")
    for version, count in (("current", 2), ("5aa-preoptimization", 2)):
        key = f"toy_unequal/{version}/exact_producer"
        _check(grouped[key]["status_counts"] == {"unequal": count, "unknown": 1},
               f"synthetic mixed unequal/UNKNOWN statuses were lost for {key}")
    for version in ("current", "5aa-preoptimization"):
        key = f"toy_unknown/{version}/exact_producer"
        _check(grouped[key]["status_counts"] == {"unknown": 3},
               f"synthetic UNKNOWN statuses were lost for {key}")
        _check(grouped[key]["latency_samples_used"] == 0
               and grouped[key]["latency_median_seconds"] is None,
               f"synthetic UNKNOWN was treated as a latency sample for {key}")
    _check(len(rows) == 24 and all(row["analysis_seconds"] != 0 for row in rows),
           "synthetic raw timing rows were changed or zero-imputed")


def _real_rows(results_path: Path, manifest_path: Path, reports_root: Path) -> dict:
    result = json.loads(results_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows = result["rows"]
    reps = result["protocol"]["measured_repetitions_per_case_operation"]
    warmups = result["protocol"]["warmups_per_case_operation"]
    _check(reps >= 5 and warmups == 1, "result protocol does not match the preregistered repetition floor")

    manifest_cases = {case["case_id"]: case for case in manifest["cases"]
                      if not case["family"].startswith("symmetric_equal_chain_primary")}
    result_cases = {case["case_id"]: case for case in result["cases"]}
    _check(result_cases == manifest_cases,
           "timed case list differs from the frozen non-primary manifest")
    current_cases = set(manifest_cases)
    old_cases = current_cases & PREOPT_SAMPLE
    expected_groups = {
        (case_id, "current", operation)
        for case_id in current_cases
        for operation in ("exact_producer", "exact_replay", "bisim_producer", "bisim_replay")
    } | {
        (case_id, "5aa-preoptimization", operation)
        for case_id in old_cases
        for operation in ("exact_producer", "exact_replay")
    }

    measured: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    warmup_rows: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    errors = []
    for row in rows:
        key = (row["case_id"], row["implementation"], row["operation"])
        (warmup_rows if row.get("warmup") else measured)[key].append(row)
        if row.get("error") or row.get("status") in {"error", "timeout", "invalid", "admission_failure"}:
            errors.append((key, row.get("run_id"), row.get("status"), row.get("error")))
        time_key = "analysis_seconds" if "analysis_seconds" in row else "replay_seconds"
        _check(isinstance(row.get(time_key), (int, float)) and math.isfinite(row[time_key])
               and row[time_key] >= 0,
               f"missing/invalid raw elapsed time at {key} {row.get('run_id')}")
        if row.get("status") in {"unknown", "timeout", "invalid", "admission_failure"}:
            _check(row[time_key] > 0,
                   f"non-completed status was zero-imputed at {key} {row.get('run_id')}")
    _check(not errors, f"worker error, timeout, invalid/admission row found: {errors[:3]}")
    _check(set(measured) == expected_groups,
           f"measured groups differ from preregistration; missing={sorted(expected_groups-set(measured))}, "
           f"unexpected={sorted(set(measured)-expected_groups)}")
    _check(set(warmup_rows) == expected_groups,
           "warmup groups differ from the preregistered case/version/operation matrix")
    for key in sorted(expected_groups):
        group = measured[key]
        _check(len(group) == reps,
               f"{key} has {len(group)} measured rows; preregistered count is {reps}")
        _check({row["run_id"] for row in group} == {f"rep-{index}" for index in range(1, reps + 1)},
               f"{key} does not have exactly rep-1 through rep-{reps}")
        _check(len(warmup_rows[key]) == warmups,
               f"{key} has {len(warmup_rows[key])} warmups; preregistered count is {warmups}")

    recomputed = _summarize_by_case(rows)
    _check(result["summaries"] == recomputed,
           "saved summaries do not equal a fresh aggregation of preserved raw rows")
    _check(len(recomputed) == len(expected_groups),
           f"summary has {len(recomputed)} groups; expected {len(expected_groups)}")
    for key, summary in recomputed.items():
        if summary["status_counts"].get("unknown"):
            _check(summary["latency_samples_used"] == 0
                   and summary["latency_median_seconds"] is None,
                   f"UNKNOWN rows entered completed-latency summary for {key}")

    statuses = Counter(row["status"] for row in rows if not row.get("warmup"))
    expected_statuses = {
        "current exact producer": {"proved_equal": 125, "unequal": 5, "unknown": 5},
        "current exact replay": {"verified": 130, "unknown": 5},
        "current bisim producer": {"proved_equal": 120, "inconclusive": 10, "unknown": 5},
        "current bisim replay": {"verified": 130, "unknown": 5},
        "5aa-preoptimization exact producer": {"proved_equal": 30, "unequal": 5},
        "5aa-preoptimization exact replay": {"verified": 35},
    }
    for label, expected in expected_statuses.items():
        implementation, operation = label.split(" ", 1)
        actual = Counter(row["status"] for row in rows if not row.get("warmup")
                         and row["implementation"] == implementation
                         and row["operation"] == operation.replace(" ", "_"))
        _check(dict(actual) == expected, f"unexpected true status counts for {label}: {dict(actual)}")

    by_key = {(row["case_id"], row["implementation"], row["operation"]): row
              for row in rows if not row.get("warmup")}
    unequal_rows = measured[("history_conditioned_unequal", "current", "exact_producer")]
    _check(all(row["status"] == "unequal" and row["finite_witness_lengths"] == [2]
               for row in unequal_rows),
           "history-conditioned exact witness/status changed across repetitions")
    unequal_report = json.loads((reports_root / "current/history_conditioned_unequal.json")
                                .read_text(encoding="utf-8"))
    witness = unequal_report["result"]["pairs"][0]["counterexample"]
    _check(witness["left_probability"] == "1" and witness["right_probability"] == "0"
           and len(witness["word"]) == 2
           and all(label["input_tokens"] == 1 and label["output_tokens"] == 1
                   for label in witness["word"]),
           "saved history-conditioned witness does not have the registered two-step 1-vs-0 form")
    _check(by_key[("history_conditioned_unequal", "current", "exact_replay")]["status"] == "verified",
           "independent replay did not verify the unequal witness")
    _check(by_key[("bisim_inconclusive_exact_equal", "current", "exact_producer")]["status"] == "proved_equal"
           and by_key[("bisim_inconclusive_exact_equal", "current", "exact_replay")]["status"] == "verified"
           and by_key[("bisim_inconclusive_exact_equal", "current", "bisim_producer")]["status"] == "inconclusive"
           and by_key[("bisim_inconclusive_exact_equal", "current", "bisim_replay")]["status"] == "verified",
           "registered exact-equal/bisim-inconclusive result pattern changed")
    for operation in ("exact_producer", "exact_replay", "bisim_producer", "bisim_replay"):
        group = measured[("resource_unknown_probe", "current", operation)]
        _check(all(row["status"] == "unknown" for row in group),
               f"resource probe ceased to retain UNKNOWN for {operation}")
    _check(all(row["diagnostics"]["reason"] == "STATE_CAP"
               for row in measured[("resource_unknown_probe", "current", "exact_producer")]),
           "exact resource probe did not preserve its STATE_CAP reason")
    return {"groups": len(expected_groups), "measured_rows": len(rows) - len(expected_groups) * warmups,
            "status_counts": dict(statuses), "results": result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--reports", type=Path, default=DEFAULT_REPORTS)
    args = parser.parse_args()
    aggregation_regression()
    checked = _real_rows(args.results, args.manifest, args.reports)
    print("aggregation regression: PASS (6 version-separated groups; expected equal/unequal medians; UNKNOWN excluded)")
    print(f"frozen real data: PASS ({checked['groups']} groups; {checked['measured_rows']} measured rows; "
          f"{sum(checked['status_counts'].values())} total measured rows)")
    print("measured statuses: " + json.dumps(checked["status_counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
