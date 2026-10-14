#!/usr/bin/env python3
"""Run reviewed workflow source capsules under a restricted macOS Seatbelt.

Docker is not available in this environment (CLI present, daemon absent), so
this runner uses macOS sandbox-exec with a path allowlist and a scrubbed env.
It launches only the two fixed workers in this directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile
import time

from strict_json import StrictJSONError, loads as strict_loads, validate_tree


ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = ROOT / "integrations" / "workflow_capsules"
PREFLIGHT = INTEGRATION / "sandbox_preflight.py"
PYTHON = Path(
    "/Users/nambi/Documents/ChatGPT/Compiler Project/"
    "orchlang-publication-upgrade/.venv/bin/python"
)
PYTHON_FRAMEWORK = Path(
    "/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/"
    "Versions/3.14/bin/python3.14"
)
PYTHON_LAUNCHER = Path(
    "/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/"
    "Versions/3.14/Resources/Python.app/Contents/MacOS/Python"
)
VENV = PYTHON.parent.parent
FRAMEWORK_ROOT = Path("/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework")
ALLOWED_WORKERS = {
    "didilili": INTEGRATION / "worker.py",
    "joshua": INTEGRATION / "joshua_kb_worker.py",
}
MAX_CHILD_OUTPUT_BYTES = 32 * 1024 * 1024
PREFLIGHT_KEYS = {"fork_denied", "network_denied", "unlisted_user_file_denied", "writes_denied"}


def _quote(path: Path | str) -> str:
    return json.dumps(str(path), ensure_ascii=False)


def profile_text(worker: Path) -> str:
    readable = [
        VENV,
        FRAMEWORK_ROOT,
        Path("/System/Library/Frameworks"),
        Path("/System/Library/PrivateFrameworks"),
        Path("/usr/lib"),
        Path("/usr/share/zoneinfo"),
    ]
    exact = [
        worker,
        PREFLIGHT,
        INTEGRATION / "run_capsule.py",
        ROOT / "output/publication_upgrade/corpus/sources/didilili/ai-agents-from-zero/9de20be80dad6d410268ae75f75cf94c355dd364/案例与源码-3-LangGraph框架/01-helloworld/LangGraphLLM.py",
        ROOT / "output/publication_upgrade/corpus/sources/JoshuaC215/agent-service-toolkit/88ebfa1fadd1a207aa92115635abf7ed20d66a88/src/agents/knowledge_base_agent.py",
    ]
    parent_metadata = [
        Path("/Users"),
        Path("/Users/nambi"),
        Path("/Users/nambi/Documents"),
        Path("/Users/nambi/Documents/ChatGPT"),
        Path("/Users/nambi/Documents/ChatGPT/Compiler Project"),
        Path("/Users/nambi/Documents/ChatGPT/Compiler Project/orchlang-publication-upgrade"),
        Path("/Users/nambi/Documents/ChatGPT/Compiler Project/orchlang-publication-upgrade/.venv"),
        Path("/Users/nambi/Documents/ChatGPT/Compiler Project/orchlang-publication-upgrade/.venv/bin"),
        ROOT,
        ROOT / "integrations",
        INTEGRATION,
        ROOT / "output",
        ROOT / "output/publication_upgrade",
        ROOT / "output/publication_upgrade/corpus",
        ROOT / "output/publication_upgrade/corpus/sources",
        ROOT / "output/publication_upgrade/corpus/sources/didilili",
        ROOT / "output/publication_upgrade/corpus/sources/didilili/ai-agents-from-zero",
        ROOT / "output/publication_upgrade/corpus/sources/didilili/ai-agents-from-zero/9de20be80dad6d410268ae75f75cf94c355dd364",
        ROOT / "output/publication_upgrade/corpus/sources/didilili/ai-agents-from-zero/9de20be80dad6d410268ae75f75cf94c355dd364/案例与源码-3-LangGraph框架",
        ROOT / "output/publication_upgrade/corpus/sources/didilili/ai-agents-from-zero/9de20be80dad6d410268ae75f75cf94c355dd364/案例与源码-3-LangGraph框架/01-helloworld",
        ROOT / "output/publication_upgrade/corpus/sources/JoshuaC215",
        ROOT / "output/publication_upgrade/corpus/sources/JoshuaC215/agent-service-toolkit",
        ROOT / "output/publication_upgrade/corpus/sources/JoshuaC215/agent-service-toolkit/88ebfa1fadd1a207aa92115635abf7ed20d66a88",
        ROOT / "output/publication_upgrade/corpus/sources/JoshuaC215/agent-service-toolkit/88ebfa1fadd1a207aa92115635abf7ed20d66a88/src",
        ROOT / "output/publication_upgrade/corpus/sources/JoshuaC215/agent-service-toolkit/88ebfa1fadd1a207aa92115635abf7ed20d66a88/src/agents",
        Path("/opt"),
        Path("/opt/homebrew"),
        Path("/opt/homebrew/opt"),
        Path("/opt/homebrew/opt/python@3.14"),
        Path("/opt/homebrew/Cellar"),
        Path("/opt/homebrew/Cellar/python@3.14"),
        Path("/opt/homebrew/Cellar/python@3.14/3.14.6"),
        Path("/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks"),
    ]
    denied_reads = [
        "/Users",
        "/private/var",
        "/var",
        "/private/tmp",
        "/tmp",
        "/private/etc",
        "/etc",
        "/Library/Keychains",
        "/System/Library/Keychains",
        "/Volumes",
        "/Network",
        "/Applications",
        "/Library",
        "/usr/local",
    ]
    rules = [
        "(version 1)",
        "(allow default)",
        "(deny network*)",
        "(deny file-write*)",
        "(deny process-fork)",
        "(deny process-info*)",
        "(deny mach-lookup)",
        "(deny process-exec)",
    ]
    rules.extend(f"(deny file-read* (subpath {_quote(path)}))" for path in denied_reads)
    # Exact later exceptions restore only these project/runtime reads after the
    # sensitive-path denials. Parent directories get metadata alone.
    rules.extend(f"(allow file-read* (subpath {_quote(path)}))" for path in readable)
    rules.append(f"(allow file-read* (subpath {_quote('/opt/homebrew/opt/python@3.14')}))")
    rules.extend(f"(allow file-read* (literal {_quote(path)}))" for path in exact)
    rules.extend(f"(allow file-read-metadata (literal {_quote(path)}))" for path in parent_metadata)
    rules.extend(
        [
            f"(allow file-read-metadata (subpath {_quote(FRAMEWORK_ROOT)}))",
            f"(allow file-read-metadata (subpath {_quote(VENV)}))",
        ]
    )
    # The venv symlink resolves through /opt/homebrew/opt to this pinned
    # framework executable, which launches the app-bundle interpreter.
    for executable in (
        PYTHON,
        Path("/opt/homebrew/opt/python@3.14/bin/python3.14"),
        PYTHON_FRAMEWORK,
        PYTHON_LAUNCHER,
    ):
        rules.append(f"(allow process-exec (literal {_quote(executable)}))")
    rules.append("(allow signal (target self))")
    return "\n".join(rules) + "\n"


def _limits() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (18, 20))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))


def _parse_preflight(stdout: str) -> dict[str, bool] | None:
    lines = [line for line in stdout.splitlines() if line.startswith("PREFLIGHT_JSON:")]
    if len(lines) != 1:
        return None
    try:
        checks = strict_loads(lines[0][len("PREFLIGHT_JSON:"):], where="sandbox preflight JSON")
    except StrictJSONError:
        return None
    if type(checks) is not dict or set(checks) != PREFLIGHT_KEYS:
        return None
    if not all(type(value) is bool and value is True for value in checks.values()):
        return None
    return checks


def _parse_capsule_output(stdout: str) -> tuple[dict[str, object] | None, str | None]:
    try:
        output_bytes = stdout.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        return None, f"worker stdout contains invalid Unicode: {exc}"
    if len(output_bytes) > MAX_CHILD_OUTPUT_BYTES:
        return None, f"worker stdout exceeds {MAX_CHILD_OUTPUT_BYTES} bytes"
    lines = [line for line in stdout.splitlines() if line.startswith("CAPSULE_JSON:")]
    if len(lines) != 1:
        return None, f"expected one CAPSULE_JSON line, got {len(lines)}"
    try:
        result = strict_loads(lines[0][len("CAPSULE_JSON:"):], where="worker result JSON")
        validate_tree(result, where="worker result")
    except StrictJSONError as exc:
        return None, str(exc)
    if type(result) is not dict:
        return None, "worker result must be a JSON object"
    return result, None


def _run_child(worker: Path, timeout: float) -> dict[str, object]:
    worker_sha256 = hashlib.sha256(worker.read_bytes()).hexdigest()
    env = {
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "AWS_KB_ID": "finite-kb-fixture",
        "CAPSULE_WORKER_SHA256": worker_sha256,
    }
    with tempfile.NamedTemporaryFile(prefix="workflow-capsule-", suffix=".sb", mode="w", encoding="utf-8") as profile:
        profile.write(profile_text(worker))
        profile.flush()
        preflight_command = ["/usr/bin/sandbox-exec", "-f", profile.name, str(PYTHON), "-B", str(PREFLIGHT)]
        preflight = subprocess.Popen(
            preflight_command,
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            preexec_fn=_limits,
        )
        try:
            preflight_stdout, preflight_stderr = preflight.communicate(timeout=min(timeout, 8.0))
        except subprocess.TimeoutExpired:
            os.killpg(preflight.pid, signal.SIGKILL)
            preflight_stdout, preflight_stderr = preflight.communicate()
            return {
                "worker": worker.name,
                "worker_sha256": worker_sha256,
                "exit_code": preflight.returncode,
                "timed_out": True,
                "preflight": {"timed_out": True, "stdout_tail": preflight_stdout[-1000:], "stderr_tail": preflight_stderr[-1000:]},
                "result": None,
                "parse_error": "sandbox preflight timed out; original source was not run",
            }
        preflight_checks = _parse_preflight(preflight_stdout)
        if (
            preflight.returncode != 0
            or preflight_checks is None
        ):
            return {
                "worker": worker.name,
                "worker_sha256": worker_sha256,
                "exit_code": preflight.returncode,
                "timed_out": False,
                "preflight": {"checks": preflight_checks, "stdout_tail": preflight_stdout[-1000:], "stderr_tail": preflight_stderr[-1000:]},
                "result": None,
                "parse_error": "Seatbelt preflight failed; original source was not run",
            }
        command = ["/usr/bin/sandbox-exec", "-f", profile.name, str(PYTHON), "-B", str(worker)]
        started = time.monotonic()
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            preexec_fn=_limits,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
            return {
                "worker": worker.name,
                "worker_sha256": worker_sha256,
                "exit_code": process.returncode,
                "timed_out": True,
                "preflight": {"checks": preflight_checks},
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "stdout_tail": stdout[-4000:],
                "stderr_tail": stderr[-4000:],
            }
    parsed, parse_error = _parse_capsule_output(stdout)
    return {
        "worker": worker.name,
        "worker_sha256": worker_sha256,
        "exit_code": process.returncode,
        "timed_out": False,
        "preflight": {"checks": preflight_checks},
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "result": parsed,
        "parse_error": parse_error,
        "stdout_unparsed": stdout[-4000:] if parsed is None else None,
        "stderr_tail": stderr[-4000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("worker", choices=sorted(ALLOWED_WORKERS) + ["all"])
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    choices = list(ALLOWED_WORKERS) if args.worker == "all" else [args.worker]
    results = [_run_child(ALLOWED_WORKERS[choice], args.timeout) for choice in choices]
    output_dir = ROOT / "research/scp_strengthening/workflow_capsules"
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for item in results:
        result = item.get("result")
        capsule_id = result.get("capsule_id") if isinstance(result, dict) else item["worker"]
        filename = str(capsule_id).replace("/", "_") + ".json"
        path = output_dir / filename
        validate_tree(item, where="capsule artifact wrapper")
        payload = json.dumps(item, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if len(payload.encode("utf-8", errors="strict")) > MAX_CHILD_OUTPUT_BYTES:
            raise RuntimeError("capsule artifact wrapper exceeds byte limit")
        path.write_text(payload, encoding="utf-8")
        item["artifact"] = str(path)
        law_data = result.get("exact_laws", {}) if isinstance(result, dict) else {}
        summaries.append({
            "capsule_id": capsule_id,
            "result": result.get("result") if isinstance(result, dict) else None,
            "elementary_world_count": result.get("finite_support", {}).get("elementary_world_count") if isinstance(result, dict) else None,
            "complete_trace_classes": len(law_data.get("complete_trace_law", [])),
            "content_only_classes": len(law_data.get("content_only_law", [])),
            "artifact": str(path),
            "elapsed_seconds": item.get("elapsed_seconds"),
            "exit_code": item.get("exit_code"),
            "parse_error": item.get("parse_error"),
            "preflight": item.get("preflight", {}).get("checks") if isinstance(item.get("preflight"), dict) else None,
            "stderr_tail": item.get("stderr_tail"),
        })
    print(json.dumps({"sandbox": "macOS Seatbelt with explicit network/write/process and sensitive-path denies; isolated child environment", "runs": summaries}, ensure_ascii=False, indent=2))
    return 0 if all(
        isinstance(item.get("result"), dict)
        and item["result"].get("result") == "PASS_CONDITIONAL_FINITE_DOMAIN"
        and item.get("exit_code") == 0
        and not item.get("timed_out")
        for item in results
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
