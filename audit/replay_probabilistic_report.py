#!/usr/bin/env python3
"""Independently replay a finite success-only usage-channel report.

The verifier binds a report to the exact graph and kernel bytes and to the
canonical public/scenario inputs it records.  It then calls the separate
no-state-merging DFS oracle in :mod:`probabilistic_reference` for every secret
scenario and recomputes exact channel metrics locally.  A verified attestation
is finite evidence for these inputs, this finite kernel, this observer, and
this horizon; it is not a general proof, a provider model, a monetary bill, or
a differential-privacy guarantee.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any

try:  # support both `python audit/replay_...py` and `import audit.replay_...`
    from .probabilistic_reference import (
        MAX_HORIZON,
        MAX_TOKEN,
        _Kernel,
        ReferenceError as OracleInputError,
        _Graph,
        independent_histogram,
    )
except ImportError:  # direct script execution from the repository checkout
    from probabilistic_reference import (
        MAX_HORIZON,
        MAX_TOKEN,
        _Kernel,
        ReferenceError as OracleInputError,
        _Graph,
        independent_histogram,
    )


REPORT_FORMAT = "orchlang-finite-usage-channel"
ATTESTATION_FORMAT = "orchlang-finite-usage-channel-replay-attestation"
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_REPORT_BYTES = 128 * 1024 * 1024
MAX_REPORT_ITEMS = 1_000_000
MAX_SCENARIOS = 64
MAX_STATES = 1_000_000
MAX_WORK_BYTES = 1024 * 1024 * 1024
MAX_EXACT_BITS = 8192
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
RATIONAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?$")
PRIOR_RE = re.compile(r"^[1-9][0-9]{0,999}(?:/[1-9][0-9]{0,999})?$")
MAX_RATIONAL_CHARS = 4096
RULE_PRECEDENCE = "first matching rule in supplied order, otherwise resolved-contract default"
SCOPE = ("success-only integer usage plus stop/truncation under declared finite rational conditional kernels; "
         "no currency, errors, provider estimates or infinite-run law")
STUDY_SCOPE = ("authored synthetic finite success-only kernels; no provider distribution fitting, "
               "currency, errors or infinite-horizon analysis")
ACCEPTED_SCOPES = {SCOPE, STUDY_SCOPE}
LIMITS = [
    "exact probabilities/TV/vulnerability; log displays are floating approximations",
    "likelihood ratio is a channel statistic, not a differential-privacy claim without declared adjacency",
]
METRICS_KEYS = {
    "pairwise", "bayes_vulnerability", "prior_bayes_vulnerability",
    "min_entropy_vulnerability_ratio", "min_entropy_leakage_bits_approx",
    "mutual_information_bits_approx", "mutual_information_exact_expression",
    "all_pairwise_observation_laws_equal", "limits",
}
PAIR_KEYS = {
    "left", "right", "total_variation", "equal_observation_laws",
    "maximum_likelihood_ratio", "maximum_log_likelihood_ratio_nats_approx",
    "infinite_likelihood_ratio",
}
ROW_KEYS = {
    "status", "histogram", "mass", "state_visits", "peak_frontier",
    "call_transitions", "terminal_states", "observer", "horizon",
    "work_bytes_estimate", "max_work_bytes",
}
TOP_KEYS = {
    "format", "version", "status", "rows", "metrics", "observer", "horizon",
    "priors", "public_store", "secret_scenarios", "source_sha256", "kernel_sha256",
    "analyzer_sha256", "public_store_sha256", "secret_scenarios_sha256",
    "max_states", "max_work_bytes", "rule_precedence", "scope",
}
UNVERIFIED_FIELDS = [
    "analyzer_sha256 (digest shape only; producer executable was not replayed)",
    "rows[*].state_visits, peak_frontier, call_transitions, terminal_states, work_bytes_estimate "
    "(producer execution counters; checked for shape and declared-budget bounds, not recomputed by DFS)",
    "metrics.pairwise[*].maximum_log_likelihood_ratio_nats_approx",
    "metrics.min_entropy_leakage_bits_approx",
    "metrics.mutual_information_bits_approx",
]


class ReportReplayError(ValueError):
    """The report does not match its bound inputs or exact replay."""


class ReportReplayLimit(RuntimeError):
    """The independent verifier could not finish within its resource bounds."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as error:
        if isinstance(error, RecursionError):
            raise ReportReplayLimit("canonical JSON nesting resource limit reached") from error
        if _is_integer_display_limit(error):
            raise ReportReplayLimit(f"exact integer formatting resource limit: {error}") from error
        raise ReportReplayError(f"value is not canonical JSON: {error}") from error


def _is_integer_display_limit(error: BaseException) -> bool:
    message = str(error).lower()
    return "integer string conversion" in message or "max_str_digits" in message


def _fraction_bits(value: Fraction) -> int:
    return max(abs(value.numerator).bit_length(), value.denominator.bit_length())


def _bounded_fraction(value: Fraction, label: str) -> Fraction:
    if _fraction_bits(value) > MAX_EXACT_BITS:
        raise ReportReplayLimit(f"{label} exceeds the {MAX_EXACT_BITS}-bit exact-arithmetic limit")
    return value


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReportReplayError(f"{label} must be an object")
    return value


def _keys(value: Any, required: set[str], label: str,
          optional: set[str] | None = None) -> dict[str, Any]:
    obj = _object(value, label)
    optional = optional or set()
    missing = required - obj.keys()
    unknown = obj.keys() - required - optional
    if missing or unknown:
        raise ReportReplayError(
            f"{label} fields differ: missing {sorted(missing)}, unknown {sorted(unknown)}"
        )
    return obj


def _natural(value: Any, label: str, minimum: int = 0, maximum: int = MAX_TOKEN) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ReportReplayError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ReportReplayError(f"non-finite JSON number: {value}")
    return number


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReportReplayError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ReportReplayError(f"non-finite JSON number {value}")


def _parse_json(raw: bytes, label: str, limit: int) -> Any:
    if len(raw) > limit:
        raise ReportReplayLimit(f"{label} exceeds its {limit}-byte read limit")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs_no_duplicates,
                          parse_constant=_reject_constant, parse_float=_finite_float)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        if isinstance(error, ReportReplayError):
            raise
        if isinstance(error, RecursionError):
            raise ReportReplayLimit(f"{label} parser nesting resource limit reached") from error
        if _is_integer_display_limit(error):
            raise ReportReplayLimit(f"{label} exact integer parsing resource limit reached: {error}") from error
        raise ReportReplayError(f"invalid {label} JSON: {error}") from error


def _raw_bytes(source: Any, label: str, limit: int) -> bytes:
    if isinstance(source, bytes):
        raw = source
    elif isinstance(source, bytearray):
        raw = bytes(source)
    elif isinstance(source, os.PathLike):
        path = Path(source)
        try:
            with path.open("rb") as stream:
                if os.fstat(stream.fileno()).st_size > limit:
                    raise ReportReplayLimit(f"{label} exceeds its {limit}-byte read limit")
                # Bound actual I/O as well as the preflight stat so a file
                # that grows concurrently cannot trigger an unbounded read.
                raw = stream.read(limit + 1)
        except OSError as error:
            raise ReportReplayError(f"cannot read {label}: {error}") from error
    else:
        raise ReportReplayError(f"{label} must be raw bytes or a filesystem path")
    if len(raw) > limit:
        raise ReportReplayLimit(f"{label} exceeds its {limit}-byte read limit")
    return raw


def _report_bytes(source: Any) -> tuple[bytes, Any]:
    if isinstance(source, Mapping):
        _check_json_resources(source, "report")
        raw = _canonical(source).encode("utf-8")
        return raw, _parse_json(raw, "report", MAX_REPORT_BYTES)
    raw = _raw_bytes(source, "report", MAX_REPORT_BYTES)
    return raw, _parse_json(raw, "report", MAX_REPORT_BYTES)


def _valid_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ReportReplayError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _rational(value: Any, label: str, *, positive: bool = False,
              maximum_one: bool = False) -> Fraction:
    if isinstance(value, str) and len(value) > MAX_RATIONAL_CHARS and RATIONAL_RE.fullmatch(value):
        raise ReportReplayLimit(f"{label} exceeds the bounded exact-rational display limit")
    if not isinstance(value, str) or not RATIONAL_RE.fullmatch(value):
        raise ReportReplayError(f"{label} must be a canonical exact rational string")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ReportReplayError(f"{label} is not a rational number") from error
    if str(result) != value:
        raise ReportReplayError(f"{label} is not in reduced canonical form")
    _bounded_fraction(result, label)
    if positive and result <= 0:
        raise ReportReplayError(f"{label} must be positive")
    if maximum_one and result > 1:
        raise ReportReplayError(f"{label} must be at most one")
    return result


def _scenario_prior(value: Any, label: str) -> Fraction:
    if not isinstance(value, str) or len(value) > 2001 or not PRIOR_RE.fullmatch(value):
        raise ReportReplayError(f"{label} must be a positive exact integer/fraction string")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ReportReplayError(f"{label} is invalid") from error
    _bounded_fraction(result, label)
    if result <= 0 or result > 1:
        raise ReportReplayError(f"{label} must lie in (0,1]")
    return result


def _check_json_resources(value: Any, label: str) -> None:
    count = 0
    encoded_bytes = 0

    def walk(item: Any, depth: int = 0) -> None:
        nonlocal count, encoded_bytes
        if depth > 256:
            raise ReportReplayLimit(f"{label} nesting resource limit reached")
        count += 1
        if count > MAX_REPORT_ITEMS:
            raise ReportReplayLimit(f"{label} item resource limit reached")
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ReportReplayError(f"{label} has non-string keys")
                encoded_bytes += len(key.encode("utf-8")) + 1
                walk(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                walk(child, depth + 1)
        elif isinstance(item, str):
            try:
                encoded_bytes += len(item.encode("utf-8"))
            except UnicodeEncodeError as error:
                raise ReportReplayError(f"{label} has non-scalar Unicode") from error
        elif item is None or type(item) in (bool, int, float):
            if type(item) is float and not math.isfinite(item):
                raise ReportReplayError(f"{label} has a non-finite number")
            encoded_bytes += 16
        else:
            raise ReportReplayError(f"{label} contains a non-JSON value")
        if encoded_bytes > MAX_REPORT_BYTES:
            raise ReportReplayLimit(f"{label} canonical data byte-work limit reached")

    walk(value)


def _canonical_digest(value: Any, label: str) -> str:
    _check_json_resources(value, label)
    return _sha(_canonical(value).encode("utf-8"))


def _check_path_probability_growth(kernel: Any, horizon: int) -> None:
    """Conservatively bound exact path-probability integer growth before DFS.

    Every execution path multiplies at most ``horizon`` outcome probabilities.
    If that simple upper bound already exceeds the verifier's exact-arithmetic
    limit, the report is UNKNOWN. Invalid kernel structure is left for the
    independent reference parser to reject with its own diagnostics.
    """
    if not isinstance(kernel, dict):
        return
    defaults = kernel.get("defaults")
    rules = kernel.get("rules")
    if not isinstance(defaults, dict) or not isinstance(rules, list):
        return
    distributions: list[Any] = list(defaults.values())
    for rule in rules:
        if not isinstance(rule, dict):
            return
        distributions.append(rule.get("outcomes"))
    bit_bound = 1
    for distribution in distributions:
        if not isinstance(distribution, list):
            return
        for outcome in distribution:
            if not isinstance(outcome, dict):
                return
            text = outcome.get("probability")
            if not isinstance(text, str) or len(text) > 2001 or not RATIONAL_RE.fullmatch(text):
                return
            try:
                probability = Fraction(text)
            except (ValueError, ZeroDivisionError):
                return
            if probability <= 0:
                return
            bit_bound = max(bit_bound, _fraction_bits(probability))
    if bit_bound * horizon > MAX_EXACT_BITS:
        raise ReportReplayLimit(
            f"bounded path probability may exceed the {MAX_EXACT_BITS}-bit exact-arithmetic limit"
        )


def _oracle_error_is_resource_limit(error: BaseException) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in (
        "resource limit", "resource-limit", "resource cap", "resource byte",
        "resource work", "resource step", "exact-rational resource",
        "byte-work limit", "exceeds the json byte", "over the text byte",
    ))


def _check_replayed_fraction_sizes(histogram: Mapping[str, Fraction], label: str) -> None:
    for probability in histogram.values():
        _bounded_fraction(probability, f"{label} histogram probability")


def _canonical_histogram(row: Any, label: str) -> tuple[dict[str, Fraction], Fraction]:
    obj = _object(row, label)
    entries = obj.get("histogram")
    if not isinstance(entries, list) or len(entries) > MAX_REPORT_ITEMS:
        raise ReportReplayError(f"{label} histogram must be a bounded observation array")
    histogram: dict[str, Fraction] = {}
    ordered_keys: list[str] = []
    for index, raw in enumerate(entries):
        item = _keys(raw, {"observation", "probability"}, f"{label} histogram item {index}")
        observation = _object(item["observation"], f"{label} observation {index}")
        key = _canonical(observation)
        if key in histogram:
            raise ReportReplayError(f"{label} histogram repeats a canonical observation")
        probability = _rational(item["probability"], f"{label} observation probability",
                                positive=True, maximum_one=True)
        histogram[key] = probability
        ordered_keys.append(key)
    if not entries:
        raise ReportReplayError(f"{label} histogram cannot be empty")
    if ordered_keys != sorted(ordered_keys):
        raise ReportReplayError(f"{label} histogram observations are not canonically ordered")
    mass = sum(histogram.values(), Fraction(0, 1))
    if mass != 1:
        raise ReportReplayError(f"{label} histogram mass is {mass}, not one")
    declared_mass = _rational(obj.get("mass"), f"{label} declared mass", positive=True)
    if declared_mass != 1 or declared_mass != mass:
        raise ReportReplayError(f"{label} declared mass does not match its unit histogram")
    return histogram, mass


def _producer_row_shape(row: Any, index: int, observer: str, horizon: int,
                        max_states: int, max_work_bytes: int) -> dict[str, Any]:
    row = _keys(row, ROW_KEYS, f"row {index}")
    if row["status"] == "unknown":
        raise _UnknownReport(f"producer row {index} is UNKNOWN")
    if row["status"] != "complete":
        raise ReportReplayError(f"row {index} has an unsupported status")
    if row["observer"] != observer or row["horizon"] != horizon:
        raise ReportReplayError(f"row {index} observer/horizon differs from the report")
    if row["max_work_bytes"] != max_work_bytes:
        raise ReportReplayError(f"row {index} max_work_bytes differs from the report")
    state_visits = _natural(row["state_visits"], f"row {index} state_visits", 1, max_states)
    _natural(row["peak_frontier"], f"row {index} peak_frontier", 1, state_visits)
    _natural(row["call_transitions"], f"row {index} call_transitions", 0, max_states * 256)
    _natural(row["terminal_states"], f"row {index} terminal_states", 1, state_visits)
    _natural(row["work_bytes_estimate"], f"row {index} work_bytes_estimate", 1, max_work_bytes)
    return row


def _recompute_metrics(histograms: list[dict[str, Fraction]], priors: list[Fraction]) -> dict[str, Any]:
    outputs = sorted(set().union(*(row.keys() for row in histograms)))
    pairwise = []
    for left in range(len(histograms)):
        for right in range(left + 1, len(histograms)):
            a, b = histograms[left], histograms[right]
            tv = Fraction(0)
            for key in outputs:
                difference = _bounded_fraction(
                    abs(a.get(key, Fraction(0)) - b.get(key, Fraction(0))),
                    "pairwise total-variation difference",
                )
                tv = _bounded_fraction(tv + difference, "pairwise total variation")
            tv = _bounded_fraction(tv / 2, "pairwise total variation")
            maximum: Fraction | None = None
            infinite = False
            ratios: list[Fraction] = []
            for numerator, denominator in ((a, b), (b, a)):
                for key in outputs:
                    p, q = numerator.get(key, Fraction(0)), denominator.get(key, Fraction(0))
                    if p and not q:
                        infinite = True
                    elif p and q:
                        ratios.append(_bounded_fraction(p / q, "pairwise likelihood ratio"))
            if not infinite:
                maximum = max(ratios, default=Fraction(1))
            pairwise.append({
                "left": left,
                "right": right,
                "total_variation": tv,
                "equal_observation_laws": tv == 0,
                "maximum_likelihood_ratio": maximum,
                "infinite_likelihood_ratio": infinite,
            })

    marginal = {}
    for key in outputs:
        total = Fraction(0)
        for index, row in enumerate(histograms):
            weighted = _bounded_fraction(priors[index] * row.get(key, Fraction(0)),
                                          "Bayesian marginal term")
            total = _bounded_fraction(total + weighted, "Bayesian marginal")
        marginal[key] = total
    vulnerability = Fraction(0)
    for key in outputs:
        best = max(_bounded_fraction(priors[index] * row.get(key, Fraction(0)),
                                     "Bayes vulnerability term")
                   for index, row in enumerate(histograms))
        vulnerability = _bounded_fraction(vulnerability + best, "Bayes vulnerability")
    prior_vulnerability = max(priors)
    expression_terms: list[tuple[Fraction, Fraction]] = []
    for index, row in enumerate(histograms):
        for key in sorted(row):
            probability = row[key]
            coefficient = _bounded_fraction(priors[index] * probability,
                                             "mutual-information coefficient")
            ratio = _bounded_fraction(probability / marginal[key],
                                      "mutual-information likelihood ratio")
            expression_terms.append((coefficient, ratio))
    # The report's exact MI expression is compared as a multiset, so scenario
    # or observation insertion order cannot affect this validation.
    expression_terms.sort(key=lambda item: (_fraction_text(item[0]), _fraction_text(item[1])))
    return {
        "pairwise": pairwise,
        "bayes_vulnerability": vulnerability,
        "prior_bayes_vulnerability": prior_vulnerability,
        "min_entropy_vulnerability_ratio": _bounded_fraction(
            vulnerability / prior_vulnerability, "min-entropy vulnerability ratio"),
        "mi_terms": expression_terms,
        "all_pairwise_observation_laws_equal": all(
            item["equal_observation_laws"] for item in pairwise
        ),
    }


def _fraction_text(value: Fraction) -> str:
    return str(value)


def _finite_approx(value: Any, label: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ReportReplayError(f"{label} must be a finite numeric display value")


def _verify_metrics(raw: Any, expected: dict[str, Any]) -> None:
    metrics = _keys(raw, METRICS_KEYS, "metrics")
    pairwise = metrics["pairwise"]
    expected_pairs = expected["pairwise"]
    if not isinstance(pairwise, list) or len(pairwise) != len(expected_pairs):
        raise ReportReplayError("pairwise metric count differs from the recomputed result")
    for index, (item_raw, item_expected) in enumerate(zip(pairwise, expected_pairs)):
        item = _keys(item_raw, PAIR_KEYS, f"pairwise metric {index}")
        left = _natural(item["left"], f"pairwise metric {index} left", 0, MAX_SCENARIOS - 1)
        right = _natural(item["right"], f"pairwise metric {index} right", 0, MAX_SCENARIOS - 1)
        if (left, right) != (item_expected["left"], item_expected["right"]):
            raise ReportReplayError(f"pairwise metric {index} names the wrong scenarios")
        tv = _rational(item["total_variation"], f"pairwise metric {index} total variation")
        ratio_raw = item["maximum_likelihood_ratio"]
        ratio = None if ratio_raw is None else _rational(
            ratio_raw, f"pairwise metric {index} maximum likelihood ratio", positive=True)
        actual = {
            "left": left,
            "right": right,
            "total_variation": tv,
            "equal_observation_laws": item["equal_observation_laws"],
            "maximum_likelihood_ratio": ratio,
            "infinite_likelihood_ratio": item["infinite_likelihood_ratio"],
        }
        if type(actual["equal_observation_laws"]) is not bool or type(actual["infinite_likelihood_ratio"]) is not bool:
            raise ReportReplayError(f"pairwise metric {index} Boolean fields have invalid types")
        if actual != item_expected:
            raise ReportReplayError(f"pairwise metric {index} differs from exact recomputation")
        _finite_approx(item["maximum_log_likelihood_ratio_nats_approx"],
                       f"pairwise metric {index} approximate log", optional=item_expected["infinite_likelihood_ratio"])

    for field in ("bayes_vulnerability", "prior_bayes_vulnerability", "min_entropy_vulnerability_ratio"):
        value = _rational(metrics[field], f"metrics {field}", positive=True)
        if value != expected[field]:
            raise ReportReplayError(f"metric {field} differs from exact recomputation")
    all_equal = metrics["all_pairwise_observation_laws_equal"]
    if type(all_equal) is not bool or all_equal != expected["all_pairwise_observation_laws_equal"]:
        raise ReportReplayError("all-pairs equality metric differs from exact recomputation")

    expression = _keys(metrics["mutual_information_exact_expression"], {"form", "terms"},
                       "exact mutual-information expression")
    if expression["form"] != "sum(coefficient * log2(ratio))":
        raise ReportReplayError("unknown exact mutual-information expression form")
    terms = expression["terms"]
    if not isinstance(terms, list) or len(terms) > MAX_REPORT_ITEMS:
        raise ReportReplayError("exact mutual-information terms must be a bounded array")
    actual_terms = []
    for index, raw_term in enumerate(terms):
        term = _keys(raw_term, {"coefficient", "ratio"}, f"mutual-information term {index}")
        coefficient = _rational(term["coefficient"], "mutual-information coefficient", positive=True)
        ratio = _rational(term["ratio"], "mutual-information ratio", positive=True)
        actual_terms.append((coefficient, ratio))
    if Counter(actual_terms) != Counter(expected["mi_terms"]):
        raise ReportReplayError("exact mutual-information expression terms differ from recomputation")

    _finite_approx(metrics["min_entropy_leakage_bits_approx"],
                   "approximate min-entropy leakage")
    _finite_approx(metrics["mutual_information_bits_approx"],
                   "approximate mutual information")
    if metrics["limits"] != LIMITS:
        raise ReportReplayError("metrics limitation text differs from the report contract")


class _UnknownReport(Exception):
    pass


def _attestation(status: str, *, diagnostic: str | None = None,
                  details: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "format": ATTESTATION_FORMAT,
        "version": 1,
        "status": status,
        "verification_method": "independent finite DFS re-execution",
        "claim_scope": ("replayed finite scenario histograms and exact leakage metrics for the bound "
                        "inputs, kernel, observer, and horizon; not a general proof"),
        "verifier_exact_integer_bit_limit": MAX_EXACT_BITS,
        "unverified_fields": UNVERIFIED_FIELDS,
        "diagnostic": diagnostic,
    }
    if details:
        result.update(details)
    return result


def replay_report(report_source: Any, graph_source: Any, kernel_source: Any, *,
                  max_reference_paths: int = 100_000,
                  max_reference_steps: int = 1_000_000,
                  max_reference_work_bytes: int = 64 * 1024 * 1024) -> dict[str, Any]:
    """Replay a producer report without invoking its analyzer or metric code.

    Graph and kernel inputs must be raw bytes or paths so their hashes bind the
    exact source bytes.  The report may be raw JSON bytes, a path, or a mapping
    (mapping reports are canonically serialized for the attestation digest).
    Independent DFS resource limits are separate from the producer's
    state-merging counters; exhaustion returns ``unknown`` with no verified
    claim.
    """
    try:
        max_reference_paths = _natural(max_reference_paths, "max_reference_paths", 1, 1_000_000)
        max_reference_steps = _natural(max_reference_steps, "max_reference_steps", 1, 10_000_000)
        max_reference_work_bytes = _natural(
            max_reference_work_bytes, "max_reference_work_bytes", 1, MAX_WORK_BYTES)
        report_raw, report = _report_bytes(report_source)
        graph_raw = _raw_bytes(graph_source, "graph source", MAX_SOURCE_BYTES)
        kernel_raw = _raw_bytes(kernel_source, "kernel source", MAX_SOURCE_BYTES)
        report = _object(report, "report")

        # Basic identity checks are also applied to UNKNOWN reports; an
        # incomplete producer result can never turn into a verified result.
        if report.get("format") != REPORT_FORMAT or type(report.get("version")) is not int or report["version"] != 1:
            raise ReportReplayError("unsupported finite usage-channel report format/version")
        source_digest, kernel_digest = _sha(graph_raw), _sha(kernel_raw)
        if report.get("source_sha256") != source_digest:
            raise ReportReplayError("report graph SHA-256 differs from supplied raw graph bytes")
        if report.get("kernel_sha256") != kernel_digest:
            raise ReportReplayError("report kernel SHA-256 differs from supplied raw kernel bytes")
        if report.get("status") == "unknown":
            return _attestation("unknown", diagnostic="producer report is UNKNOWN; incomplete rows are not replayed",
                                details={"report_sha256": _sha(report_raw),
                                         "source_sha256": source_digest,
                                         "kernel_sha256": kernel_digest})
        if report.get("status") != "complete":
            raise ReportReplayError("report status must be complete or unknown")

        report = _keys(report, TOP_KEYS, "report")
        if not HASH_RE.fullmatch(report["source_sha256"] or "") or not HASH_RE.fullmatch(report["kernel_sha256"] or ""):
            raise ReportReplayError("source/kernel digest fields are malformed")
        analyzer_digest = _valid_sha(report["analyzer_sha256"], "analyzer_sha256")
        _natural(report["max_states"], "max_states", 1, MAX_STATES)
        max_work_bytes = _natural(report["max_work_bytes"], "max_work_bytes", 1, MAX_WORK_BYTES)
        horizon = _natural(report["horizon"], "horizon", 1, MAX_HORIZON)
        observer = report["observer"]
        if observer not in ("aggregate", "trace"):
            raise ReportReplayError("observer must be aggregate or trace")
        if report["rule_precedence"] != RULE_PRECEDENCE or report["scope"] not in ACCEPTED_SCOPES:
            raise ReportReplayError("report rule-precedence/scope declaration differs")

        graph_document = _parse_json(graph_raw, "graph source", MAX_SOURCE_BYTES)
        kernel_document = _parse_json(kernel_raw, "kernel source", MAX_SOURCE_BYTES)
        graph = _Graph(graph_document)
        # Validate the entire kernel independently before applying the
        # conservative arithmetic bound, so malformed kernels remain rejected
        # instead of being mislabeled as a resource-limited valid channel.
        _Kernel(kernel_document, graph)
        _check_path_probability_growth(kernel_document, horizon)
        public_names = {name for name, decl in graph.inputs.items() if decl["label"] == "public"}
        secret_names = set(graph.inputs) - public_names
        public_store = _object(report["public_store"], "public_store")
        if set(public_store) != public_names:
            raise ReportReplayError("public_store must assign every public input and no secret inputs")
        secret_scenarios = report["secret_scenarios"]
        if not isinstance(secret_scenarios, list) or not 2 <= len(secret_scenarios) <= MAX_SCENARIOS:
            raise ReportReplayError("report must contain 2..64 secret scenarios")
        if _canonical_digest(public_store, "public_store") != report["public_store_sha256"]:
            raise ReportReplayError("canonical public_store SHA-256 mismatch")
        if _canonical_digest(secret_scenarios, "secret_scenarios") != report["secret_scenarios_sha256"]:
            raise ReportReplayError("canonical secret_scenarios SHA-256 mismatch")

        stores_seen: set[str] = set()
        priors: list[Fraction] = []
        normalized_scenarios: list[dict[str, Any]] = []
        for index, raw_scenario in enumerate(secret_scenarios):
            scenario = _keys(raw_scenario, {"values", "prior"}, f"secret scenario {index}")
            values = _object(scenario["values"], f"secret scenario {index} values")
            if set(values) != secret_names:
                raise ReportReplayError(f"secret scenario {index} does not assign every secret input exactly")
            identity = _canonical(values)
            if identity in stores_seen:
                raise ReportReplayError("secret_scenarios contain a duplicate secret assignment")
            stores_seen.add(identity)
            prior = _scenario_prior(scenario["prior"], f"secret scenario {index} prior")
            priors.append(prior)
            normalized_scenarios.append({"values": values, "prior": prior})
        if sum(priors, Fraction(0, 1)) != 1:
            raise ReportReplayError("secret scenario priors must sum exactly to one")
        report_priors = report["priors"]
        if not isinstance(report_priors, list) or len(report_priors) != len(priors):
            raise ReportReplayError("report prior vector length differs from secret scenarios")
        for index, (raw_prior, expected_prior) in enumerate(zip(report_priors, priors)):
            if _rational(raw_prior, f"report prior {index}", positive=True) != expected_prior:
                raise ReportReplayError("report prior vector differs from the scenario priors")
        rows = report["rows"]
        if not isinstance(rows, list) or len(rows) != len(secret_scenarios):
            raise ReportReplayError("report row count differs from the secret scenario count")

        # A resource-limited row remains UNKNOWN.  We do not verify a partial
        # producer histogram, even when earlier rows were complete.
        checked_rows = []
        for index, row in enumerate(rows):
            if isinstance(row, dict) and row.get("status") == "unknown":
                return _attestation("unknown", diagnostic=f"producer row {index} is UNKNOWN",
                                    details={"report_sha256": _sha(report_raw),
                                             "source_sha256": source_digest,
                                             "kernel_sha256": kernel_digest,
                                             "observer": observer, "horizon": horizon})
            checked_rows.append(_producer_row_shape(row, index, observer, horizon,
                                                     report["max_states"], max_work_bytes))

        replay_histograms: list[dict[str, Fraction]] = []
        row_stats = []
        for index, (scenario, row) in enumerate(zip(normalized_scenarios, checked_rows)):
            store = {**public_store, **scenario["values"]}
            try:
                replayed = independent_histogram(
                    graph_document, kernel_document, store, horizon,
                    max_paths=max_reference_paths,
                    max_steps=max_reference_steps,
                    max_work_bytes=max_reference_work_bytes,
                    observer=observer,
                )
            except OracleInputError as error:
                if _oracle_error_is_resource_limit(error):
                    return _attestation("unknown", diagnostic=f"independent DFS resource limit: {error}",
                                        details={"report_sha256": _sha(report_raw),
                                                 "source_sha256": source_digest,
                                                 "kernel_sha256": kernel_digest,
                                                 "observer": observer, "horizon": horizon,
                                                 "replayed_rows": index})
                raise ReportReplayError(f"independent graph/kernel/store validation failed: {error}") from error
            except ValueError as error:
                if _is_integer_display_limit(error):
                    return _attestation("unknown", diagnostic=f"independent DFS exact-integer resource limit: {error}",
                                        details={"report_sha256": _sha(report_raw),
                                                 "source_sha256": source_digest,
                                                 "kernel_sha256": kernel_digest,
                                                 "observer": observer, "horizon": horizon,
                                                 "replayed_rows": index})
                raise ReportReplayError(f"independent DFS arithmetic/serialization failed: {error}") from error
            except (MemoryError, OverflowError, RecursionError) as error:
                raise ReportReplayLimit(f"independent DFS resource limit: {error}") from error
            if replayed["status"] == "unknown":
                return _attestation("unknown", diagnostic=f"independent DFS row {index}: {replayed['diagnostic']}",
                                    details={"report_sha256": _sha(report_raw),
                                             "source_sha256": source_digest,
                                             "kernel_sha256": kernel_digest,
                                             "observer": observer, "horizon": horizon,
                                             "max_reference_paths": max_reference_paths,
                                             "max_reference_steps": max_reference_steps,
                                             "max_reference_work_bytes": max_reference_work_bytes,
                                             "replayed_rows": index})
            _check_replayed_fraction_sizes(replayed["histogram"], f"independent DFS row {index}")
            candidate_histogram, candidate_mass = _canonical_histogram(row, f"row {index}")
            if candidate_histogram != replayed["histogram"] or candidate_mass != replayed["mass"]:
                raise ReportReplayError(f"row {index} histogram differs from independent finite DFS")
            replay_histograms.append(replayed["histogram"])
            row_stats.append({"leaf_paths": replayed["leaf_paths"],
                              "call_transitions": replayed["call_transitions"],
                              "control_steps": replayed["control_steps"],
                              "work_bytes": replayed["work_bytes"]})

        expected_metrics = _recompute_metrics(replay_histograms, priors)
        _verify_metrics(report["metrics"], expected_metrics)
        return _attestation("verified", details={
            "report_sha256": _sha(report_raw),
            "source_sha256": source_digest,
            "kernel_sha256": kernel_digest,
            "producer_analyzer_sha256": analyzer_digest,
            "public_store_sha256": report["public_store_sha256"],
            "secret_scenarios_sha256": report["secret_scenarios_sha256"],
            "observer": observer,
            "horizon": horizon,
            "declared_scope": report["scope"],
            "producer_max_states": report["max_states"],
            "producer_max_work_bytes": max_work_bytes,
            "max_reference_paths": max_reference_paths,
            "max_reference_steps": max_reference_steps,
            "max_reference_work_bytes": max_reference_work_bytes,
            "scenario_rows_verified": len(rows),
            "independent_rows": row_stats,
            "verified_exact_metrics": [
                "pairwise exact total variation",
                "pairwise symmetric finite/infinite likelihood ratios",
                "equal-observation-law predicates",
                "Bayes vulnerability and prior vulnerability",
                "exact min-entropy vulnerability ratio",
                "exact mutual-information symbolic terms (multiset comparison)",
            ],
        })
    except _UnknownReport as error:
        return _attestation("unknown", diagnostic=str(error))
    except ReportReplayLimit as error:
        return _attestation("unknown", diagnostic=str(error))
    except (MemoryError, OverflowError, RecursionError) as error:
        return _attestation("unknown", diagnostic=f"independent verifier resource limit: {error}")
    except OracleInputError as error:
        if _oracle_error_is_resource_limit(error):
            return _attestation("unknown", diagnostic=f"independent input resource limit: {error}")
        return _attestation("rejected", diagnostic=str(error))
    except (ReportReplayError, ValueError, TypeError, KeyError, OSError) as error:
        if _is_integer_display_limit(error):
            return _attestation("unknown", diagnostic=f"exact-integer resource limit: {error}")
        return _attestation("rejected", diagnostic=str(error))


def main(argv: list[str] | None = None) -> int:
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("report", type=Path)
    cli.add_argument("graph", type=Path)
    cli.add_argument("kernel", type=Path)
    cli.add_argument("--max-reference-paths", type=int, default=100_000)
    cli.add_argument("--max-reference-steps", type=int, default=1_000_000)
    cli.add_argument("--max-reference-work-bytes", type=int, default=64 * 1024 * 1024)
    args = cli.parse_args(argv)
    attestation = replay_report(args.report, args.graph, args.kernel,
                                max_reference_paths=args.max_reference_paths,
                                max_reference_steps=args.max_reference_steps,
                                max_reference_work_bytes=args.max_reference_work_bytes)
    print(json.dumps(attestation, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    return {"verified": 0, "unknown": 2, "rejected": 1}[attestation["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
