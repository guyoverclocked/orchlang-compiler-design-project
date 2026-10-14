#!/usr/bin/env python3
"""Build and validate the dependency-free OrchLang analysis wheel.

The isolated install smoke suite runs from a temporary directory, using copied
small fixtures and only wheel-installed modules and entry points. The wheel
has no third-party runtime dependencies; build-time setuptools and wheel are
already present in the local environment. No package index or provider is
contacted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import venv


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/release"
VERSION = "0.5.0rc3"
MODULES = {
    "orchgraph": "audit/orchgraph.py",
    "replay_graph_certificate": "audit/replay_graph_certificate.py",
    "probabilistic_channels": "audit/probabilistic_channels.py",
    "probabilistic_reference": "audit/probabilistic_reference.py",
    "replay_probabilistic_report": "audit/replay_probabilistic_report.py",
    "stochastic_bisimulation": "audit/stochastic_bisimulation.py",
    "replay_stochastic_certificate": "audit/replay_stochastic_certificate.py",
    "trace_equivalence": "audit/trace_equivalence.py",
    "replay_trace_equivalence": "audit/replay_trace_equivalence.py",
}
CHANNEL_GRAPH = "examples/channels/equivalent_dependent_chain.graph.json"
CHANNEL_KERNEL = "examples/channels/equivalent_dependent_chain.kernel.json"
CHANNEL_SCENARIOS = [
    {"values": {"secret": False}, "prior": "1/2"},
    {"values": {"secret": True}, "prior": "1/2"},
]
STOCHASTIC_SCENARIOS = [{"secret": False}, {"secret": True}]
PUBLIC_STORE = {}
PUBLIC_JSON = "{}"
CHANNEL_SCENARIOS_JSON = json.dumps(CHANNEL_SCENARIOS, separators=(",", ":"))
STOCHASTIC_SCENARIOS_JSON = json.dumps(STOCHASTIC_SCENARIOS, separators=(",", ":"))
MAX_STATES = 100
MAX_TRANSITIONS = 1000
MAX_WORK_BYTES = 1024 * 1024
MAX_CONTROL_STEPS = 1000
MAX_REFERENCE_PATHS = 100
MAX_REFERENCE_STEPS = 1000


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_interpreter() -> str:
    """Find a local interpreter with the declared wheel build tools installed."""
    candidates = [sys.executable]
    for name in ("python3.14", "python3.13", "python3.12", "python3.11", "python3.10", "python3"):
        candidate = shutil.which(name)
        if candidate:
            candidates.append(candidate)
    checked: set[str] = set()
    for candidate in candidates:
        resolved = str(Path(candidate).resolve())
        if resolved in checked:
            continue
        checked.add(resolved)
        try:
            probe = subprocess.run(
                [resolved, "-c", "import setuptools, wheel"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=5, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0:
            return resolved
    raise RuntimeError(
        "offline wheel build needs a local Python with setuptools and wheel; "
        "no build tools will be downloaded"
    )


def _json_output(result: subprocess.CompletedProcess[str], label: str) -> dict:
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(label + " did not emit valid JSON: " + result.stdout[:400]) from error
    if not isinstance(value, dict):
        raise RuntimeError(label + " did not emit a JSON object")
    return value


def main() -> int:
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUT,
                        help="destination for wheel and smoke evidence")
    args = parser.parse_args()
    OUT = args.output_dir.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    wheel_dir = OUT / "wheels"
    wheel_dir.mkdir(parents=True, exist_ok=True)
    stages: list[dict] = []
    logs: list[str] = []
    results: dict[str, dict] = {}
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    environment["PIP_NO_INDEX"] = "1"

    def run(label: str, argv: list, cwd: Path, expected: int = 0) -> subprocess.CompletedProcess[str]:
        try:
            completed = subprocess.run(
                [str(arg) for arg in argv],
                cwd=cwd,
                env=environment,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            stages.append({"stage": label, "exit_code": None,
                           "expected_exit_code": expected, "timed_out": True})
            logs.append(label + "\nTIMEOUT after 180 seconds")
            raise RuntimeError(label + " timed out after 180 seconds") from error
        logs.append(label + "\n" + completed.stdout + completed.stderr)
        stages.append({"stage": label, "exit_code": completed.returncode,
                       "expected_exit_code": expected, "timed_out": False})
        if completed.returncode != expected:
            raise RuntimeError(label + " failed with exit " + str(completed.returncode)
                               + "; expected " + str(expected) + ": "
                               + completed.stderr[-1000:])
        return completed

    try:
        wheel_builder = build_interpreter()
        run(
            "offline-wheel-build",
            [wheel_builder, "-m", "pip", "wheel", "--no-cache-dir", "--no-deps",
             "--no-build-isolation", "--wheel-dir", wheel_dir, ROOT],
            ROOT,
        )
        wheels = list(wheel_dir.glob("orchlang_graph_tools-" + VERSION + "-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("expected exactly one versioned wheel, found " + str(len(wheels)))
        wheel = wheels[0]

        with tempfile.TemporaryDirectory(prefix="orchlang-installed-smoke-") as directory:
            temporary = Path(directory).resolve()
            isolated = temporary / "venv"
            fixtures = temporary / "fixtures"
            fixtures.mkdir()
            venv.EnvBuilder(with_pip=True).create(isolated)
            binaries = isolated / ("Scripts" if os.name == "nt" else "bin")
            python = binaries / ("python.exe" if os.name == "nt" else "python")
            suffix = ".exe" if os.name == "nt" else ""

            run("offline-isolated-install",
                [python, "-m", "pip", "install", "--no-deps", "--no-index", wheel], temporary)
            metadata = run("installed-wheel-metadata", [python, "-I", "-c",
                'import importlib.metadata, json; d=importlib.metadata.distribution("orchlang-graph-tools"); '
                'print(json.dumps({"version":d.version,"requires_python":d.metadata.get("Requires-Python"),'
                '"requires":d.requires or []}))'],
                temporary)
            installed_metadata = _json_output(metadata, "installed wheel metadata")
            if installed_metadata.get("version") != VERSION:
                raise RuntimeError("installed version mismatch")
            if installed_metadata.get("requires_python") != ">=3.10":
                raise RuntimeError("installed Python minimum metadata mismatch")
            if installed_metadata.get("requires"):
                raise RuntimeError("wheel unexpectedly declares runtime dependencies: "
                                   + repr(installed_metadata["requires"]))
            run("installed-wheel-imports", [python, "-I", "-c", (
                "import importlib, json, pathlib; "
                f"root=pathlib.Path({str(ROOT)!r}).resolve(); "
                f"names={list(MODULES)!r}; "
                "mods={name:importlib.import_module(name) for name in names}; "
                "paths={name:str(pathlib.Path(mod.__file__).resolve()) for name,mod in mods.items()}; "
                "assert all(root not in pathlib.Path(path).parents for path in paths.values()), paths; "
                "print(json.dumps(paths,sort_keys=True))"
            )], temporary)

            graph_source = ROOT / CHANNEL_GRAPH
            kernel_source = ROOT / CHANNEL_KERNEL
            graph = fixtures / "tiny.graph.json"
            kernel = fixtures / "tiny.kernel.json"
            graph.write_bytes(graph_source.read_bytes())
            kernel.write_bytes(kernel_source.read_bytes())
            channel_graph_sha = sha(graph)
            channel_kernel_sha = sha(kernel)
            graph_check_source = ROOT / "examples/graphs/accepted/matched_cyclic_chain.json"
            graph_check = fixtures / "matched_cyclic_chain.json"
            graph_check.write_bytes(graph_check_source.read_bytes())

            graph_check_tool = binaries / ("orchlang-graph-check" + suffix)
            graph_replay_tool = binaries / ("orchlang-graph-replay" + suffix)
            channel_tool = binaries / ("orchlang-channel-analyze" + suffix)
            channel_replay_tool = binaries / ("orchlang-channel-replay" + suffix)
            bisimulation_tool = binaries / ("orchlang-stochastic-bisimulation" + suffix)
            stochastic_replay_tool = binaries / ("orchlang-stochastic-replay" + suffix)
            trace_equivalence_tool = binaries / ("orchlang-trace-equivalence" + suffix)
            trace_replay_tool = binaries / ("orchlang-trace-replay" + suffix)

            graph_certificate = temporary / "graph-certificate.json"
            graph_attestation = temporary / "graph-attestation.json"
            run("installed-graph-check",
                [graph_check_tool, graph_check, "--report", graph_certificate], temporary)
            run("installed-graph-independent-replay",
                [graph_replay_tool, graph_check, graph_certificate,
                 "--attestation", graph_attestation], temporary)
            graph_evidence = json.loads(graph_attestation.read_text(encoding="utf-8"))
            if graph_evidence.get("status") != "verified" or graph_evidence.get(
                    "source_sha256") != sha(graph_check):
                raise RuntimeError("installed graph replay attestation mismatch")

            rejected_graph_source = ROOT / "examples/graphs/rejected/overwritten_result_relation.json"
            rejected_graph = fixtures / "overwritten_result_relation.json"
            rejected_graph.write_bytes(rejected_graph_source.read_bytes())
            rejected_graph_report = temporary / "rejected-graph.json"
            run("installed-stale-relation-rejection",
                [graph_check_tool, rejected_graph, "--report", rejected_graph_report],
                temporary, expected=1)
            if json.loads(rejected_graph_report.read_text(encoding="utf-8")).get("status") != "rejected":
                raise RuntimeError("graph rejection status mismatch")
            graph_tampered_doc = json.loads(graph_certificate.read_text(encoding="utf-8"))
            graph_tampered_doc["nodes"][0]["successors"] = []
            graph_tampered = temporary / "tampered-graph-certificate.json"
            graph_tampered.write_text(json.dumps(graph_tampered_doc), encoding="utf-8")
            run("installed-graph-tamper-rejection",
                [graph_replay_tool, graph_check, graph_tampered], temporary, expected=1)
            run("installed-wrong-graph-source-rejection",
                [graph_replay_tool, rejected_graph, graph_certificate], temporary, expected=1)

            channel_report_path = temporary / "finite-channel.json"
            channel_report_result = run("installed-finite-channel-analysis", [
                channel_tool, graph, kernel,
                "--public-json", PUBLIC_JSON,
                "--scenarios-json", CHANNEL_SCENARIOS_JSON,
                "--horizon", "2",
                "--max-states", str(MAX_STATES),
                "--max-work-bytes", str(MAX_WORK_BYTES),
                "--observer", "trace",
                "--report", channel_report_path,
            ], temporary)
            channel_report = _json_output(channel_report_result, "finite channel analyzer")
            if channel_report.get("status") != "complete":
                raise RuntimeError("installed finite channel analyzer did not complete")
            if channel_report.get("source_sha256") != channel_graph_sha or channel_report.get(
                    "kernel_sha256") != channel_kernel_sha:
                raise RuntimeError("finite channel report source hashes mismatch")
            channel_attestation_result = run("installed-finite-channel-independent-replay", [
                channel_replay_tool, channel_report_path, graph, kernel,
                "--max-reference-paths", str(MAX_REFERENCE_PATHS),
                "--max-reference-steps", str(MAX_REFERENCE_STEPS),
                "--max-reference-work-bytes", str(MAX_WORK_BYTES),
            ], temporary)
            channel_attestation = _json_output(channel_attestation_result,
                                               "finite channel independent replay")
            if channel_attestation.get("status") != "verified" or channel_attestation.get(
                    "scenario_rows_verified") != 2:
                raise RuntimeError("installed finite channel report failed independent replay")

            bisimulation_report_path = temporary / "finite-bisimulation.json"
            bisimulation_result = run("installed-all-horizon-bisimulation", [
                bisimulation_tool, graph, kernel,
                "--public-json", PUBLIC_JSON,
                "--scenarios-json", STOCHASTIC_SCENARIOS_JSON,
                "--max-states", str(MAX_STATES),
                "--max-work-bytes", str(MAX_WORK_BYTES),
                "--report", bisimulation_report_path,
            ], temporary)
            bisimulation_report = _json_output(bisimulation_result, "stochastic bisimulation")
            if bisimulation_report.get("status") != "proved_equal":
                raise RuntimeError("installed all-horizon checker did not prove fixture equality")
            stochastic_replay_args = [
                stochastic_replay_tool, bisimulation_report_path, graph, kernel,
                "--public-json", PUBLIC_JSON,
                "--scenarios-json", STOCHASTIC_SCENARIOS_JSON,
                "--max-states", str(MAX_STATES),
                "--max-transitions", str(MAX_TRANSITIONS),
                "--max-work-bytes", str(MAX_WORK_BYTES),
                "--max-control-steps", str(MAX_CONTROL_STEPS),
            ]
            bisimulation_attestation_result = run("installed-all-horizon-independent-replay",
                                                  stochastic_replay_args, temporary)
            bisimulation_attestation = _json_output(bisimulation_attestation_result,
                                                    "stochastic independent replay")
            if bisimulation_attestation.get("status") != "verified" or not bisimulation_attestation.get(
                    "equal_laws_claim"):
                raise RuntimeError("installed stochastic certificate failed independent replay")

            tampered_bisimulation = json.loads(bisimulation_report_path.read_text(encoding="utf-8"))
            transitions = tampered_bisimulation.get("closed_system", {}).get("transitions")
            if not isinstance(transitions, list) or not transitions:
                raise RuntimeError("fixture certificate has no transition to tamper")
            transitions.pop()
            tampered_bisimulation_path = temporary / "tampered-bisimulation.json"
            tampered_bisimulation_path.write_text(json.dumps(tampered_bisimulation), encoding="utf-8")
            tamper_result = run("installed-stochastic-certificate-tamper-rejection", [
                stochastic_replay_tool, tampered_bisimulation_path, graph, kernel,
                "--public-json", PUBLIC_JSON,
                "--scenarios-json", STOCHASTIC_SCENARIOS_JSON,
                "--max-states", str(MAX_STATES),
                "--max-transitions", str(MAX_TRANSITIONS),
                "--max-work-bytes", str(MAX_WORK_BYTES),
                "--max-control-steps", str(MAX_CONTROL_STEPS),
            ], temporary, expected=1)
            tamper_attestation = _json_output(tamper_result, "tampered certificate replay")
            if tamper_attestation.get("status") != "rejected" or tamper_attestation.get(
                    "equal_laws_claim"):
                raise RuntimeError("tampered stochastic certificate was not rejected")

            unknown_report_path = temporary / "resource-unknown-bisimulation.json"
            unknown_result = run("installed-bisimulation-resource-unknown", [
                bisimulation_tool, graph, kernel,
                "--public-json", PUBLIC_JSON,
                "--scenarios-json", STOCHASTIC_SCENARIOS_JSON,
                "--max-states", "1",
                "--max-work-bytes", str(MAX_WORK_BYTES),
                "--report", unknown_report_path,
            ], temporary, expected=3)
            unknown_report = _json_output(unknown_result, "resource-limited bisimulation")
            if unknown_report.get("status") != "unknown" or unknown_report.get(
                    "closed_system") is not None or unknown_report.get(
                    "partition_certificate") is not None:
                raise RuntimeError("resource-limited analysis did not fail closed as UNKNOWN")
            unknown_replay_result = run("installed-resource-unknown-replay", [
                stochastic_replay_tool, unknown_report_path, graph, kernel,
                "--public-json", PUBLIC_JSON,
                "--scenarios-json", STOCHASTIC_SCENARIOS_JSON,
                "--max-states", str(MAX_STATES),
                "--max-transitions", str(MAX_TRANSITIONS),
                "--max-work-bytes", str(MAX_WORK_BYTES),
                "--max-control-steps", str(MAX_CONTROL_STEPS),
            ], temporary, expected=2)
            unknown_attestation = _json_output(unknown_replay_result, "UNKNOWN certificate replay")
            if unknown_attestation.get("status") != "unknown" or unknown_attestation.get(
                    "equal_laws_claim"):
                raise RuntimeError("independent replay did not preserve UNKNOWN status")

            exact_graph = fixtures / "trace_equal_not_bisimilar.graph.json"
            exact_kernel = fixtures / "trace_equal_not_bisimilar.kernel.json"
            for target, relative in (
                (exact_graph, "examples/channels/trace_equal_not_bisimilar.graph.json"),
                (exact_kernel, "examples/channels/trace_equal_not_bisimilar.kernel.json"),
            ):
                target.write_bytes((ROOT / relative).read_bytes())
            unequal_graph = fixtures / "same_mean_distinct_laws.graph.json"
            unequal_kernel = fixtures / "same_mean_distinct_laws.kernel.json"
            for target, relative in (
                (unequal_graph, "examples/channels/same_mean_distinct_laws.graph.json"),
                (unequal_kernel, "examples/channels/same_mean_distinct_laws.kernel.json"),
            ):
                target.write_bytes((ROOT / relative).read_bytes())

            def exact_check(label, graph_file, kernel_file, report_file,
                            expected=0, max_states=MAX_STATES):
                return run(label, [trace_equivalence_tool, graph_file, kernel_file,
                    "--public-json", PUBLIC_JSON,
                    "--scenarios-json", STOCHASTIC_SCENARIOS_JSON,
                    "--max-states", str(max_states),
                    "--max-work-bytes", str(MAX_WORK_BYTES),
                    "--report", report_file], temporary, expected=expected)

            def exact_replay(label, graph_file, kernel_file, report_file, expected=0):
                return run(label, [trace_replay_tool, report_file, graph_file, kernel_file,
                    "--public-json", PUBLIC_JSON,
                    "--scenarios-json", STOCHASTIC_SCENARIOS_JSON,
                    "--max-states", str(MAX_STATES),
                    "--max-work-bytes", str(MAX_WORK_BYTES)], temporary, expected=expected)

            exact_report_path = temporary / "exact-trace-equality.json"
            exact_report = _json_output(exact_check("installed-exact-trace-equivalence",
                exact_graph, exact_kernel, exact_report_path), "exact trace equivalence")
            if exact_report.get("status") != "proved_equal":
                raise RuntimeError("exact finite-state checker did not prove the equal-law fixture")
            exact_attestation = _json_output(exact_replay("installed-exact-equality-replay",
                exact_graph, exact_kernel, exact_report_path), "exact equality replay")
            if exact_attestation.get("status") != "verified" or not exact_attestation.get("all_finite_horizons_claim"):
                raise RuntimeError("exact equality certificate did not replay")

            unequal_report_path = temporary / "exact-trace-inequality.json"
            unequal_report = _json_output(exact_check("installed-exact-trace-inequality",
                unequal_graph, unequal_kernel, unequal_report_path, expected=1), "exact trace inequality")
            if unequal_report.get("status") != "unequal":
                raise RuntimeError("exact finite-state checker did not produce an inequality witness")
            unequal_attestation = _json_output(exact_replay("installed-exact-witness-replay",
                unequal_graph, unequal_kernel, unequal_report_path), "exact witness replay")
            if unequal_attestation.get("status") != "verified" or unequal_attestation.get("all_finite_horizons_claim"):
                raise RuntimeError("finite inequality witness did not replay")

            wrong_source_attestation = _json_output(exact_replay("installed-exact-wrong-source-rejection",
                unequal_graph, unequal_kernel, exact_report_path, expected=1), "exact wrong-source replay")
            if wrong_source_attestation.get("status") != "rejected":
                raise RuntimeError("exact replay failed to reject the wrong bound inputs")

            exact_unknown_path = temporary / "exact-resource-unknown.json"
            exact_unknown_report = _json_output(exact_check("installed-exact-resource-unknown",
                exact_graph, exact_kernel, exact_unknown_path, expected=3, max_states=1), "exact UNKNOWN")
            if exact_unknown_report.get("status") != "unknown" or exact_unknown_report.get("closed_system") is not None:
                raise RuntimeError("resource-limited exact analysis did not fail closed")
            exact_unknown_attestation = _json_output(exact_replay("installed-exact-unknown-replay",
                exact_graph, exact_kernel, exact_unknown_path, expected=2), "exact UNKNOWN replay")
            if exact_unknown_attestation.get("status") != "unknown" or exact_unknown_attestation.get("all_finite_horizons_claim"):
                raise RuntimeError("exact independent replay did not preserve UNKNOWN")

            results = {
                "graph_checker_and_replayer": {
                    "checker_status": "accepted",
                    "replay_status": graph_evidence["status"],
                    "source_sha256": sha(graph_check),
                    "tamper_status": "rejected",
                    "wrong_source_status": "rejected",
                    "stale_relation_status": "rejected",
                },
                "finite_channel": {
                    "producer_status": channel_report["status"],
                    "observer": channel_report["observer"],
                    "horizon": channel_report["horizon"],
                    "replay_status": channel_attestation["status"],
                    "scenario_rows_verified": channel_attestation["scenario_rows_verified"],
                    "graph_sha256": channel_graph_sha,
                    "kernel_sha256": channel_kernel_sha,
                    "report_sha256": sha(channel_report_path),
                },
                "all_horizon_bisimulation": {
                    "producer_status": bisimulation_report["status"],
                    "state_count": bisimulation_report["closed_system"]["state_count"],
                    "transition_count": bisimulation_report["closed_system"]["transition_count"],
                    "replay_status": bisimulation_attestation["status"],
                    "equal_laws_claim": bisimulation_attestation["equal_laws_claim"],
                    "tamper_status": tamper_attestation["status"],
                    "report_sha256": sha(bisimulation_report_path),
                },
                "resource_probe": {
                    "producer_status": unknown_report["status"],
                    "producer_exit_code": unknown_result.returncode,
                    "replay_status": unknown_attestation["status"],
                    "replay_exit_code": unknown_replay_result.returncode,
                    "closed_system_present": unknown_report["closed_system"] is not None,
                },
                "exact_trace_equivalence": {
                    "equality_status": exact_report["status"],
                    "equality_replay_status": exact_attestation["status"],
                    "equality_report_sha256": sha(exact_report_path),
                    "unequal_status": unequal_report["status"],
                    "witness_replay_status": unequal_attestation["status"],
                    "unequal_report_sha256": sha(unequal_report_path),
                    "wrong_source_status": wrong_source_attestation["status"],
                    "resource_status": exact_unknown_report["status"],
                    "resource_replay_status": exact_unknown_attestation["status"],
                },
            }

        module_hashes = {name: sha(ROOT / relative) for name, relative in MODULES.items()}
        script_names = [
            "orchlang-graph-check", "orchlang-graph-replay",
            "orchlang-channel-analyze", "orchlang-channel-replay",
            "orchlang-stochastic-bisimulation", "orchlang-stochastic-replay",
            "orchlang-trace-equivalence", "orchlang-trace-replay",
        ]
        result = {
            "format": "orchlang-installed-wheel-validation",
            "version": 2,
            "software_version": VERSION,
            "status": "passed",
            "platform": platform.platform(),
            "python": platform.python_version(),
            "wheel_build_interpreter": wheel_builder,
            "requires_python": ">=3.10",
            "wheel": str(wheel.relative_to(ROOT)),
            "wheel_sha256": sha(wheel),
            "pyproject_sha256": sha(ROOT / "pyproject.toml"),
            "packager_sha256": sha(Path(__file__)),
            "module_sha256": module_hashes,
            "entry_points": script_names,
            "isolated_venv": True,
            "executed_outside_checkout": True,
            "network_used": False,
            "mandatory_runtime_dependencies": installed_metadata["requires"],
            "limits": {
                "channel": {"max_states": MAX_STATES, "max_work_bytes": MAX_WORK_BYTES,
                            "horizon": 2, "observer": "trace"},
                "channel_replay": {"max_reference_paths": MAX_REFERENCE_PATHS,
                                   "max_reference_steps": MAX_REFERENCE_STEPS,
                                   "max_reference_work_bytes": MAX_WORK_BYTES},
                "bisimulation": {"max_states": MAX_STATES,
                                 "max_work_bytes": MAX_WORK_BYTES},
                "bisimulation_replay": {"max_states": MAX_STATES,
                                        "max_transitions": MAX_TRANSITIONS,
                                        "max_work_bytes": MAX_WORK_BYTES,
                                        "max_control_steps": MAX_CONTROL_STEPS},
                "exact_trace_equivalence": {"max_states": MAX_STATES,
                                            "max_work_bytes": MAX_WORK_BYTES},
            },
            "results": results,
            "stages": stages,
            "limits_note": [
                "Offline wheel packaging and isolated CLI smoke checks; no provider calls.",
                "Finite channel replay covers its bound fixture, kernel, observer, and horizon.",
                "All-horizon replay covers equal finite trace laws under the supplied finite rational kernel and inputs.",
                "A separate compiler build and framework integration are outside this wheel.",
            ],
        }
        (OUT / "packaging_validation.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (OUT / "packaging_failed.json").unlink(missing_ok=True)
        (OUT / "packaging_validation.log").write_text("\n".join(logs), encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, json.JSONDecodeError) as error:
        failure = {"format": "orchlang-installed-wheel-validation", "version": 2,
                   "status": "failed", "error": str(error), "stages": stages}
        (OUT / "packaging_failed.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (OUT / "packaging_validation.json").unlink(missing_ok=True)
        (OUT / "packaging_validation.log").write_text("\n".join(logs), encoding="utf-8")
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
