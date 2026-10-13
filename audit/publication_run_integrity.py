"""Fixed source, claim and output profile for the publication reproduction.

The profile binds custody and stage completeness. It does not validate the
truth of a theorem, the quality of a study, or provider behavior.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any


RUN_PATH = "output/publication_upgrade/reproduction/run.json"
INCIDENT_SOURCE_COMMIT = "c08f710acfeefe233329df613fe8358eaac5f350"
UPSTREAM_BUNDLE = "integrations/incident_triage/upstream_c08f710.bundle"

REQUIRED_STAGES = (
    "core-and-langgraph",
    "observer-ablation",
    "incident-original-source",
    "external-original-source-corpus",
    "local-tokenizer-calibration",
    "solver-scaling",
    "solver-paired-baseline",
    "solver-plot",
    "proof-AtomicUpdates",
    "proof-Assumptions",
)

EVIDENCE_PATHS = {
    "core": "audit/final/manifest.json",
    "incident": "audit/incident_triage/manifest.json",
    "corpus": "output/publication_upgrade/corpus/admission_results.json",
    "selection": "output/publication_upgrade/corpus/selection_audit.json",
    "solver": "research/publication_upgrade/solver_scaling.json",
    "solver_baseline": "research/publication_upgrade/solver_scaling_baseline.json",
    "tokenizer": "output/publication_upgrade/tokenizer_calibration.json",
    "observer": "output/publication_upgrade/observer_ablation.json",
    "proof": "output/publication_upgrade/reproduction/proof-Assumptions.log",
    "run": RUN_PATH,
}

CLAIM_PROFILE = {
    "software-checks": {
        "source_paths": {"audit/reproduce_final.py", "scripts/package_graph_tools.py"},
        "evidence_ids": {"core", "run"},
    },
    "source-boundary": {
        "source_paths": {
            "integrations/langgraph/source_frontend/extract.py",
            "scripts/publication_upgrade_corpus.py",
            "research/publication_upgrade/corpus/protocol.md",
        },
        "evidence_ids": {"core", "corpus", "selection"},
    },
    "prefix-replay": {
        "source_paths": {
            "audit/trace_equivalence.py",
            "audit/replay_trace_equivalence.py",
            "research/publication_upgrade/solver_scaling.py",
        },
        "evidence_ids": {"solver", "solver_baseline"},
    },
    "atomic-ir": {
        "source_paths": {
            "proofs/publication_upgrade/AtomicUpdates.v",
            "proofs/publication_upgrade/Assumptions.v",
        },
        "evidence_ids": {"proof"},
    },
    "source-specific-study": {
        "source_paths": {
            "integrations/incident_triage/source_analysis/bridge.py",
            "integrations/incident_triage/concurrency/run_concurrency_study.py",
        },
        "evidence_ids": {"incident"},
    },
    "measurement-boundary": {
        "source_paths": {"research/publication_upgrade/tokenizer_calibration.py"},
        "evidence_ids": {"tokenizer"},
    },
    "observer-sensitivity": {
        "source_paths": {
            "research/publication_upgrade/observer_ablation.py",
            "audit/trace_equivalence.py",
        },
        "evidence_ids": {"observer", "run"},
    },
    "manuscript-provenance": {
        "source_paths": {
            "audit/publication_provenance.py",
            "scripts/package_publication_upgrade.py",
        },
        "evidence_ids": {"manuscript", "run"},
    },
}

REQUIRED_EVIDENCE_IDS = set(EVIDENCE_PATHS) | {"manuscript", "manuscript_pdf"}
OPTIONAL_EVIDENCE_IDS: set[str] = set()

REQUIRED_SOURCE_PATHS = set().union(
    *(profile["source_paths"] for profile in CLAIM_PROFILE.values())
) | {
    "audit/publication_provenance.py",
    "audit/publication_run_integrity.py",
    "audit/reproduce_incident_triage.py",
    "scripts/reproduce_publication_upgrade.py",
    "scripts/package_publication_upgrade.py",
    "research/publication_upgrade/plot_solver_scaling.py",
    "research/publication_upgrade/run_solver_baseline.py",
    "integrations/incident_triage/requirements.lock",
    UPSTREAM_BUNDLE,
    "research/publication_upgrade/corpus/results.md",
    "research/publication_upgrade/literature_verified.md",
    "research/publication_upgrade/literature_sources.csv",
    "research/publication_upgrade/literature_verified.bib",
    "output/publication_upgrade/corpus/repository_manifest.json",
    "output/publication_upgrade/corpus/source_enumeration.json",
    "output/publication_upgrade/corpus/github_search_snapshot.json",
    "output/publication_upgrade/corpus/selection_audit.json",
    "output/publication_upgrade/corpus/spdx_osi_license_list_v3.29.0.json",
    "output/publication_upgrade/tokenizer_cache/README.md",
    "output/publication_upgrade/tokenizer_cache/0ea1e91bbb3a60f729a8dc8f777fd2fc07cd8df4",
    "output/publication_upgrade/tokenizer_cache/9b5ad71b2ce5302211f9c61530b329a4922fc6a4",
    "output/publication_upgrade/tokenizer_cache/fb374d419588a4632f3f557e76b4b70aebbca790",
}

SOURCE_PREFIXES = (
    "src/", "include/", "tests/", "audit/", "bench/", "examples/", "demo/",
    "scripts/", "integrations/", "proofs/", "research/publication_upgrade/",
    "output/publication_upgrade/corpus/", "output/publication_upgrade/tokenizer_cache/",
)
SOURCE_SUFFIXES = {
    ".py", ".cpp", ".hpp", ".v", ".orch", ".lock", ".in", ".json",
    ".jsonl", ".md", ".csv", ".bib", ".txt", ".yaml", ".yml", ".toml",
    ".html", ".js", ".sh", ".bundle",
}
EXPLICIT_SOURCE_PATHS = {
    "Makefile", "pyproject.toml", "LICENSE", "README.md", "requirements.txt",
    UPSTREAM_BUNDLE,
}
GENERATED_SOURCE_PATHS = {
    "audit/final/manifest.json",
    "output/publication_upgrade/corpus/admission_results.json",
    "output/publication_upgrade/corpus/manifest.json",
    "research/publication_upgrade/solver_scaling.json",
    "research/publication_upgrade/solver_scaling_baseline.json",
    "research/publication_upgrade/solver_scaling_plot_metadata.json",
}

RUN_OUTPUT_DIRS = (
    "audit/final", "audit/incident_triage", "bench/results", "output/release",
    "output/publication_upgrade/reproduction", "proofs/publication_upgrade",
    "integrations/langgraph/source_frontend/artifacts",
)
RUN_OUTPUT_FILES = {
    "output/publication_upgrade/corpus/admission_results.json",
    "output/publication_upgrade/corpus/manifest.json",
    "output/publication_upgrade/corpus/selection_audit.json",
    "output/publication_upgrade/tokenizer_calibration.json",
    "output/publication_upgrade/observer_ablation.json",
    "research/publication_upgrade/solver_scaling.json",
    "research/publication_upgrade/solver_scaling_baseline.json",
    "research/publication_upgrade/solver_scaling_plot_metadata.json",
    "research/publication_upgrade/solver_scaling.svg",
    "research/publication_upgrade/solver_scaling.pdf",
}


class RunIntegrityError(ValueError):
    """A publication run is missing, stale, incomplete, or internally inconsistent."""


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _generated_source(path: str) -> bool:
    return path in GENERATED_SOURCE_PATHS or path.startswith((
        "audit/final/", "audit/incident_triage/", "bench/results/", "output/release/",
        "integrations/langgraph/source_frontend/artifacts/",
    ))


def _source_candidate(path: str) -> bool:
    if _generated_source(path):
        return False
    if path in EXPLICIT_SOURCE_PATHS:
        return True
    if not path.startswith(SOURCE_PREFIXES):
        return False
    if "/__pycache__/" in path or "/.venv/" in path or path.startswith((".venv/",)):
        return False
    if path.startswith("integrations/incident_triage/"):
        # The incident runner fingerprints every file below this pinned input
        # tree, including data and upstream license files without extensions.
        return True
    return (Path(path).suffix.lower() in SOURCE_SUFFIXES or path.endswith("/.gitignore")
            or path == ".gitignore" or path.endswith("/LICENSE"))


def frozen_source_inventory(root: Path, revision: str) -> dict[str, str]:
    """Hash all fixed-profile code/data at a commit and reject working-tree overlays."""
    root = root.resolve()
    names = subprocess.check_output(
        ["git", "ls-tree", "-rz", "--name-only", revision], cwd=root
    ).decode("utf-8").rstrip("\0").split("\0")
    tracked = {name for name in names if name and _source_candidate(name)}
    missing = REQUIRED_SOURCE_PATHS - set(names)
    if missing:
        raise RunIntegrityError(
            "source revision lacks required publication source/data: " + ", ".join(sorted(missing))
        )
    tracked |= REQUIRED_SOURCE_PATHS

    # Git-tree enumeration alone misses untracked Python/data files which the
    # commands could import or read from the working checkout.
    disk_candidates: set[str] = set()
    for prefix in SOURCE_PREFIXES:
        directory = root / prefix
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() and not path.is_symlink():
                continue
            relative = path.relative_to(root).as_posix()
            if _source_candidate(relative):
                if path.is_symlink():
                    raise RunIntegrityError("symlinked source/data is not an immutable input: " + relative)
                disk_candidates.add(relative)
    untracked = disk_candidates - set(names)
    if untracked:
        raise RunIntegrityError(
            "untracked publication source/data is executable or readable by the studies: "
            + ", ".join(sorted(untracked)[:12])
        )

    inventory: dict[str, str] = {}
    for name in sorted(tracked):
        try:
            frozen = subprocess.check_output(
                ["git", "show", revision + ":" + name], cwd=root, stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError as error:
            raise RunIntegrityError("required source absent from frozen commit: " + name) from error
        current = root / name
        if not current.is_file() or current.is_symlink() or current.read_bytes() != frozen:
            raise RunIntegrityError("source not frozen at declared revision: " + name)
        inventory[name] = sha256(frozen)
    return inventory


def capture_run_outputs(root: Path) -> dict[str, str]:
    """Hash all reproduction outputs except the self-referential run record."""
    root = root.resolve()
    paths: set[Path] = set()
    for relative in RUN_OUTPUT_DIRS:
        directory = root / relative
        if directory.exists():
            paths.update(path for path in directory.rglob("*") if path.is_file())
    paths.update(root / relative for relative in RUN_OUTPUT_FILES if (root / relative).is_file())
    result: dict[str, str] = {}
    for path in sorted(paths):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        if relative == RUN_PATH:
            continue
        if path.is_symlink():
            raise RunIntegrityError("symlinked run output cannot be attested: " + relative)
        result[relative] = sha256(path.read_bytes())
    return result


STAGE_SCRIPTS = {
    "core-and-langgraph": "audit/reproduce_final.py",
    "observer-ablation": "research/publication_upgrade/observer_ablation.py",
    "incident-original-source": "audit/reproduce_incident_triage.py",
    "external-original-source-corpus": "scripts/publication_upgrade_corpus.py",
    "local-tokenizer-calibration": "research/publication_upgrade/tokenizer_calibration.py",
    "solver-scaling": "research/publication_upgrade/solver_scaling.py",
    "solver-paired-baseline": "research/publication_upgrade/run_solver_baseline.py",
    "solver-plot": "research/publication_upgrade/plot_solver_scaling.py",
    "proof-AtomicUpdates": "proofs/publication_upgrade/AtomicUpdates.v",
    "proof-Assumptions": "proofs/publication_upgrade/Assumptions.v",
}


def _option(argv: list[str], flag: str, stage_name: str) -> str:
    if flag not in argv or argv.index(flag) + 1 >= len(argv):
        raise RunIntegrityError("stage omitted " + flag + ": " + stage_name)
    return argv[argv.index(flag) + 1]


def _validate_stage_invocation(stage: dict[str, Any]) -> None:
    name = stage["name"]
    argv = stage.get("argv")
    if not isinstance(argv, list) or not argv or any(not isinstance(item, str) for item in argv):
        raise RunIntegrityError("stage lacks its executed argument vector: " + name)
    expected = STAGE_SCRIPTS[name]
    if not any(item == expected or item.endswith("/" + expected) for item in argv):
        raise RunIntegrityError("stage command does not invoke its required producer: " + name)
    if name == "core-and-langgraph":
        if not {"--sanitize", "--package", "--integration-python"} <= set(argv):
            raise RunIntegrityError("core stage omitted sanitizer, packaging, or pinned LangGraph checks")
    elif name == "observer-ablation":
        if _option(argv, "--output", name) != EVIDENCE_PATHS["observer"]:
            raise RunIntegrityError("observer stage does not write its fixed evidence file")
    elif name == "incident-original-source":
        _option(argv, "--integration-python", name)
    elif name == "external-original-source-corpus":
        if "--evaluate" not in argv:
            raise RunIntegrityError("corpus stage did not evaluate the frozen source cohort")
    elif name == "solver-scaling":
        try:
            repetitions = int(_option(argv, "--repetitions", name))
        except ValueError as error:
            raise RunIntegrityError("solver repetition count is invalid") from error
        if (_option(argv, "--sizes", name) != "2,8,16,32,64,128,256"
                or _option(argv, "--output", name) != EVIDENCE_PATHS["solver"]
                or _option(argv, "--input-dir", name) != "research/publication_upgrade/solver_inputs"
                or repetitions < 5):
            raise RunIntegrityError("solver stage omitted the fixed inputs, sizes, output, or repetitions")
    elif name == "solver-paired-baseline":
        try:
            repetitions = int(_option(argv, "--repetitions", name))
        except ValueError as error:
            raise RunIntegrityError("baseline repetition count is invalid") from error
        if (_option(argv, "--sizes", name) != "2,8,16,32,64,128,256"
                or _option(argv, "--output", name) != EVIDENCE_PATHS["solver_baseline"]
                or _option(argv, "--warmups", name) != "1" or repetitions < 5):
            raise RunIntegrityError("paired baseline omitted the fixed sizes, output, warmup, or repetitions")
    elif name == "solver-plot":
        expected_args = [
            EVIDENCE_PATHS["solver"], "research/publication_upgrade/solver_scaling",
            "--baseline", EVIDENCE_PATHS["solver_baseline"],
        ]
        if len(argv) < len(expected_args) or argv[-len(expected_args):] != expected_args:
            raise RunIntegrityError("solver plot does not use both paired study outputs")
    elif name.startswith("proof-"):
        expected_file = Path(expected)
        if not any(Path(item).as_posix().endswith(expected_file.as_posix()) for item in argv):
            raise RunIntegrityError("proof stage does not compile its expected source file")


def _validate_study_outputs(
    root: Path, source_inventory: dict[str, str], output_hashes: dict[str, str]
) -> None:
    corpus = _read_json(root, EVIDENCE_PATHS["corpus"])
    if corpus.get("corpus_denominators") != {
        "candidate_files": 59, "repositories": 12, "repositories_with_candidate_files": 9,
    }:
        raise RunIntegrityError("corpus evidence differs from the frozen 59-file, 12-repository denominator")
    if corpus.get("admission_counts") != {
        "admitted": 0, "error": 0, "not_attempted": 0, "unsupported": 59,
    } or len(corpus.get("attempts", [])) != 59:
        raise RunIntegrityError("corpus evidence does not preserve all 59 unsupported source outcomes")
    if corpus.get("dynamic_differential") != (
        "differential_not_run: no original files admitted; no external source was projected or rewritten"
    ):
        raise RunIntegrityError("corpus evidence misstates the zero-admission dynamic differential")
    selection = _read_json(root, EVIDENCE_PATHS["selection"])
    if selection.get("audit_status") != "pass":
        raise RunIntegrityError("corpus selection audit did not pass")
    corpus_manifest = _read_json(root, "output/publication_upgrade/corpus/manifest.json")
    if corpus_manifest.get("admission_results") != EVIDENCE_PATHS["corpus"]:
        raise RunIntegrityError("corpus run manifest does not point to the evaluated admission results")

    tokenizer = _read_json(root, EVIDENCE_PATHS["tokenizer"])
    cache_files = {
        name.removeprefix("output/publication_upgrade/tokenizer_cache/"): file_sha
        for name, file_sha in source_inventory.items()
        if name.startswith("output/publication_upgrade/tokenizer_cache/")
    }
    if (tokenizer.get("status") != "completed" or tokenizer.get("cache_files") != cache_files
            or tokenizer.get("source_study_sha256") != source_inventory.get(
                "integrations/incident_triage/results/source_study.json")):
        raise RunIntegrityError("tokenizer calibration cache bytes differ from the frozen data inputs")

    observer = _read_json(root, EVIDENCE_PATHS["observer"])
    summary = observer.get("summary", {})
    if (observer.get("status") != "passed" or observer.get("failures") != []
            or summary.get("fixture_count") != 12
            or summary.get("fixtures_with_finite_observer_comparison") != 3
            or summary.get("independent_replay_status_counts") != {"verified": 12}):
        raise RunIntegrityError("observer-ablation evidence is incomplete or failed")

    optimized = _read_json(root, EVIDENCE_PATHS["solver"])
    baseline = _read_json(root, EVIDENCE_PATHS["solver_baseline"])
    expected_sizes = [2, 8, 16, 32, 64, 128, 256]
    for label, study in (("optimized", optimized), ("baseline", baseline)):
        if (study.get("study", {}).get("calls_per_arm") != expected_sizes
                or len(study.get("samples", [])) != 35):
            raise RunIntegrityError("solver " + label + " lacks the fixed seven-size, five-run study")

    def input_fingerprints(study: dict[str, Any]) -> dict[str, str]:
        rows = study.get("inputs", {}).get("graphs", [])
        kernel = study.get("inputs", {}).get("kernel", {})
        if not isinstance(rows, list) or not isinstance(kernel, dict):
            return {}
        result = {row.get("path"): row.get("sha256") for row in rows if isinstance(row, dict)}
        result[kernel.get("path")] = kernel.get("sha256")
        return result

    expected_solver_inputs = {
        "research/publication_upgrade/solver_inputs/scale_" + str(size) + ".graph.json":
            source_inventory.get("research/publication_upgrade/solver_inputs/scale_" + str(size) + ".graph.json")
        for size in expected_sizes
    }
    expected_solver_inputs["research/publication_upgrade/solver_inputs/scale.kernel.json"] = source_inventory.get(
        "research/publication_upgrade/solver_inputs/scale.kernel.json"
    )
    if (not input_fingerprints(optimized) or input_fingerprints(optimized) != input_fingerprints(baseline)
            or input_fingerprints(optimized) != expected_solver_inputs):
        raise RunIntegrityError("paired solver studies did not use the same frozen input bytes")
    metadata = _read_json(root, "research/publication_upgrade/solver_scaling_plot_metadata.json")
    for key, evidence_id in (("optimized_json_sha256", "solver"), ("baseline_json_sha256", "solver_baseline")):
        if metadata.get("inputs", {}).get(key) != output_hashes[EVIDENCE_PATHS[evidence_id]]:
            raise RunIntegrityError("solver plot metadata is stale relative to the paired study")
    for key, path in (("svg_sha256", "research/publication_upgrade/solver_scaling.svg"),
                      ("pdf_sha256", "research/publication_upgrade/solver_scaling.pdf")):
        if metadata.get("outputs", {}).get(key) != output_hashes.get(path):
            raise RunIntegrityError("solver plot output is missing or stale")

    for path in (
        EVIDENCE_PATHS["core"], EVIDENCE_PATHS["incident"], EVIDENCE_PATHS["corpus"],
        EVIDENCE_PATHS["selection"], EVIDENCE_PATHS["tokenizer"], EVIDENCE_PATHS["observer"],
        EVIDENCE_PATHS["solver"], EVIDENCE_PATHS["solver_baseline"], EVIDENCE_PATHS["proof"],
        "output/publication_upgrade/corpus/manifest.json",
        "research/publication_upgrade/solver_scaling_plot_metadata.json",
        "research/publication_upgrade/solver_scaling.svg",
        "research/publication_upgrade/solver_scaling.pdf",
    ):
        _require_output(output_hashes, path)


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise RunIntegrityError("missing timestamp: " + field)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise RunIntegrityError("invalid timestamp: " + field) from error
    if parsed.tzinfo is None:
        raise RunIntegrityError("timestamp must include a timezone: " + field)
    return parsed.astimezone(timezone.utc)


def _read_json(root: Path, relative: str) -> dict[str, Any]:
    try:
        value = json.loads((root / relative).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RunIntegrityError("missing or invalid run evidence: " + relative) from error
    if not isinstance(value, dict):
        raise RunIntegrityError("run evidence must be an object: " + relative)
    return value


def _require_output(output_hashes: dict[str, str], path: str) -> None:
    expected = output_hashes.get(path)
    if not isinstance(expected, str) or len(expected) != 64:
        raise RunIntegrityError("required output is not bound by the run: " + path)


def validate_run_record(
    run: dict[str, Any], root: Path, revision: str, source_inventory: dict[str, str]
) -> None:
    """Validate ordered stages, output custody and in-run core/incident manifests."""
    if not isinstance(run, dict) or run.get("format") != "orchlang-publication-upgrade-reproduction" or type(run.get("version")) is not int or run["version"] != 2:
        raise RunIntegrityError("unsupported or incomplete publication run record")
    if run.get("status") != "passed" or run.get("source_revision") != revision:
        raise RunIntegrityError("publication run did not pass at this source revision")
    if run.get("source_files_sha256") != source_inventory:
        raise RunIntegrityError("publication run source inventory differs from the frozen source revision")
    start, finish = _time(run.get("started_utc"), "run.started_utc"), _time(run.get("completed_utc"), "run.completed_utc")
    if finish < start:
        raise RunIntegrityError("publication run completes before it starts")
    stages = run.get("stages")
    if not isinstance(stages, list) or [item.get("name") if isinstance(item, dict) else None for item in stages] != list(REQUIRED_STAGES):
        raise RunIntegrityError("publication stages are missing, duplicated, extra, or out of order")
    windows: dict[str, tuple[datetime, datetime]] = {}
    previous_end = start
    for stage in stages:
        if type(stage.get("exit_code")) is not int or stage["exit_code"] != 0:
            raise RunIntegrityError("publication stage did not exit successfully: " + str(stage.get("name")))
        began, ended = _time(stage.get("started_utc"), "stage.started_utc"), _time(stage.get("completed_utc"), "stage.completed_utc")
        if began < previous_end or ended < began or began < start or ended > finish:
            raise RunIntegrityError("stage times are invalid or overlap: " + stage["name"])
        expected_log = "output/publication_upgrade/reproduction/" + stage["name"] + ".log"
        if stage.get("log") != expected_log:
            raise RunIntegrityError("stage log path does not match its required stage: " + stage["name"])
        _validate_stage_invocation(stage)
        previous_end = ended
        windows[stage["name"]] = (began, ended)

    output_hashes = run.get("outputs_sha256")
    if not isinstance(output_hashes, dict) or not output_hashes:
        raise RunIntegrityError("publication run lacks its final output digest inventory")
    current_outputs = capture_run_outputs(root)
    if current_outputs != output_hashes:
        raise RunIntegrityError("reproduction outputs changed after the passing run")
    for stage in stages:
        log = stage.get("log")
        log_hash = stage.get("log_sha256")
        if not isinstance(log, str) or log not in output_hashes or not isinstance(log_hash, str) or output_hashes[log] != log_hash:
            raise RunIntegrityError("stage log is not covered by the output digest inventory: " + stage["name"])
        if not log_hash or len(log_hash) != 64 or not (root / log).stat().st_size:
            raise RunIntegrityError("stage log is empty or has an invalid digest: " + stage["name"])

    for evidence_id, relative in EVIDENCE_PATHS.items():
        if evidence_id == "run":
            continue
        _require_output(output_hashes, relative)

    core = _read_json(root, EVIDENCE_PATHS["core"])
    if core.get("status") != "passed" or core.get("base_revision") != revision or core.get("quick") is not False:
        raise RunIntegrityError("core reproduction is stale, incomplete, or bound to another revision")
    for field in ("sanitizer_requested", "packaging_requested", "optional_langgraph_requested", "inputs_unchanged_during_run"):
        if core.get(field) is not True:
            raise RunIntegrityError("core reproduction omitted required condition: " + field)
    core_input_maps = (
        "executable_input_sha256", "core_source_sha256", "graph_fixture_sha256",
        "channel_fixture_sha256", "integration_source_sha256", "demo_snapshot_sha256",
        "package_source_sha256",
    )
    for field in core_input_maps:
        values = core.get(field)
        if not isinstance(values, dict) or not values:
            raise RunIntegrityError("core reproduction lacks its input digest map: " + field)
        for path, expected in values.items():
            if source_inventory.get(path) != expected:
                raise RunIntegrityError("core input is absent from or differs from this source revision: " + str(path))
    integration_artifacts = core.get("integration_artifact_sha256")
    expected_integration_artifacts = {
        path: expected for path, expected in output_hashes.items()
        if path.startswith("integrations/langgraph/source_frontend/artifacts/")
        and path.endswith(".json")
    }
    if (not isinstance(integration_artifacts, dict) or not integration_artifacts
            or integration_artifacts != expected_integration_artifacts):
        raise RunIntegrityError("core LangGraph artifacts are incomplete or differ from this run's outputs")
    core_start, core_finish = _time(core.get("started_utc"), "core.started_utc"), _time(core.get("completed_utc"), "core.completed_utc")
    if not (windows["core-and-langgraph"][0] <= core_start <= core_finish <= windows["core-and-langgraph"][1]):
        raise RunIntegrityError("core manifest was not produced during this publication run")

    incident = _read_json(root, EVIDENCE_PATHS["incident"])
    if incident.get("status") != "passed" or incident.get("inputs_unchanged_during_run") is not True:
        raise RunIntegrityError("incident source study is not a successful unchanged run")
    if incident.get("source_commit") != INCIDENT_SOURCE_COMMIT:
        raise RunIntegrityError("incident study does not use its declared immutable upstream revision")
    if incident.get("source_bundle_sha256") != source_inventory.get(UPSTREAM_BUNDLE):
        raise RunIntegrityError("incident study bundle does not match the frozen source inventory")
    incident_start, incident_finish = _time(incident.get("started_utc"), "incident.started_utc"), _time(incident.get("completed_utc"), "incident.completed_utc")
    if not (windows["incident-original-source"][0] <= incident_start <= incident_finish <= windows["incident-original-source"][1]):
        raise RunIntegrityError("incident manifest was not produced during this publication run")

    incident_inputs = incident.get("input_sha256")
    if not isinstance(incident_inputs, dict) or not incident_inputs:
        raise RunIntegrityError("incident source study lacks its input digest inventory")
    expected_incident_inputs = {
        path: expected for path, expected in source_inventory.items()
        if path.startswith("integrations/incident_triage/")
        or (path.startswith("audit/") and path.endswith(".py"))
    }
    if incident_inputs != expected_incident_inputs:
        raise RunIntegrityError("incident source inventory is incomplete, stale, or differs from this source revision")
    incident_results = incident.get("result_sha256")
    if not isinstance(incident_results, dict) or not incident_results:
        raise RunIntegrityError("incident source study lacks its result digest inventory")
    expected_incident_results = {
        path: expected for path, expected in output_hashes.items()
        if path.startswith("audit/incident_triage/") and path != EVIDENCE_PATHS["incident"]
    }
    if incident_results != expected_incident_results:
        raise RunIntegrityError("incident result inventory is incomplete, stale, or outside this publication run")

    core_results = core.get("results_sha256")
    if not isinstance(core_results, dict) or not core_results:
        raise RunIntegrityError("core study lacks its result digest inventory")
    expected_core_results = {
        path: expected for path, expected in output_hashes.items() if path.startswith("bench/results/")
    }
    if core_results != expected_core_results:
        raise RunIntegrityError("core result inventory is incomplete, stale, or outside this publication run")
    package_results = core.get("package_result_sha256")
    if not isinstance(package_results, dict) or not package_results:
        raise RunIntegrityError("core study lacks its package output digest inventory")
    for path, expected in package_results.items():
        if output_hashes.get(path) != expected:
            raise RunIntegrityError("core package output is not bound by the publication run: " + str(path))

    proof_log = (root / EVIDENCE_PATHS["proof"]).read_text(encoding="utf-8")
    if proof_log.count("Closed under the global context") != 2:
        raise RunIntegrityError("proof assumption output does not show both expected closed theorems")

    _validate_study_outputs(root, source_inventory, output_hashes)


def parse_run_file(root: Path, revision: str, source_inventory: dict[str, str]) -> dict[str, Any]:
    run = _read_json(root, RUN_PATH)
    validate_run_record(run, root, revision, source_inventory)
    return run
