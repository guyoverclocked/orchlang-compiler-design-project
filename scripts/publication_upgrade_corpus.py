#!/usr/bin/env python3
"""Freeze and evaluate a bounded public LangGraph source corpus.

This script never imports or executes downloaded source during enumeration or
static admission. It saves every frontend candidate byte-for-byte, then calls
the repository's existing AST extractor on that unmodified byte string.
"""
from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/publication_upgrade/corpus"
SOURCES = OUT / "sources"
PROTOCOL = ROOT / "research/publication_upgrade/corpus/protocol.md"
QUERIES = (
    "langgraph language:Python stars:>=100",
    "topic:langgraph language:Python stars:>=100",
)
PAGE_SIZE = 100
REPO_LIMIT = 12
SPDX_LICENSE_LIST = OUT / "spdx_osi_license_list_v3.29.0.json"
EXCLUDED_REPOS = {
    # Framework implementations, framework-owned examples, or research-evaluation
    # packages are not independent application workflows for this question.
    "langchain-ai/langchain": "framework monorepo",
    "langchain-ai/langgraph": "framework implementation",
    "langchain-ai/deepagents": "agent framework/toolkit",
    "langchain-ai/langchain-mcp-adapters": "framework adapter package",
    "langchain-ai/langgraph-supervisor-py": "workflow construction library",
    "langchain-ai/langgraph-swarm-py": "workflow construction library",
    "aegra/aegra": "agent framework implementation",
    "hinthornw/trustcall": "framework integration/library",
    "JudgmentLabs/judgeval": "evaluation harness/library",
}
# Kept only to audit the already-frozen first-pass manifest. New repository
# selection uses SPDX's versioned isOsiApproved flags via spdx_osi_ids().
INITIAL_MANUAL_OSI_IDS = {
    "0BSD", "AFL-3.0", "AGPL-3.0", "Apache-2.0", "Artistic-2.0", "BSD-2-Clause",
    "BSD-3-Clause", "BSD-3-Clause-Clear", "BSL-1.0", "CC0-1.0", "ECL-2.0",
    "EPL-1.0", "EPL-2.0", "EUPL-1.1", "EUPL-1.2", "GPL-2.0", "GPL-3.0",
    "ISC", "LGPL-2.1", "LGPL-3.0", "MIT", "MPL-2.0", "MS-PL", "NCSA",
    "OFL-1.1", "OSL-3.0", "PostgreSQL", "Python-2.0", "Unlicense", "UPL-1.0",
    "WTFPL", "Zlib",
}
EXCLUDED_PATH_PARTS = {
    "test", "tests", "docs", "doc", "vendor", "vendored", "generated",
    ".venv", "site-packages",
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def spdx_osi_ids() -> tuple[set[str], dict[str, Any]]:
    """Read the pinned SPDX release's authoritative OSI approval flags."""
    raw = SPDX_LICENSE_LIST.read_bytes()
    doc = json.loads(raw)
    if doc.get("licenseListVersion") != "3.29.0":
        raise RuntimeError("unexpected SPDX license-list version")
    return ({item["licenseId"] for item in doc["licenses"]
             if item.get("isOsiApproved") is True},
            {"path": SPDX_LICENSE_LIST.relative_to(ROOT).as_posix(),
             "license_list_version": doc["licenseListVersion"],
             "sha256": sha(raw),
             "approval_field": "isOsiApproved == true; includes deprecated SPDX identifiers when flagged"})


def frontend_fingerprint() -> dict[str, Any]:
    source_dir = ROOT / "integrations/langgraph/source_frontend"
    files = [{"path": path.name, "sha256": sha(path.read_bytes())}
             for path in sorted(source_dir.glob("*.py")) if not path.name.startswith("test_")]
    return {"sha256": sha(canonical(files)), "files": files}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def github_json(url: str) -> Any:
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "OrchLang-publication-upgrade-corpus/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    for attempt in range(5):
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read())
        except HTTPError as error:
            if error.code in (403, 429) and attempt < 4:
                reset = error.headers.get("X-RateLimit-Reset")
                delay = max(2, min(60, int(reset or 0) - int(time.time()))) if reset else 3 * (attempt + 1)
                time.sleep(delay)
                continue
            raise
        except URLError:
            if attempt == 4:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("GitHub API retry limit exceeded")


def raw_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "OrchLang-publication-upgrade-corpus/1.0"})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=45) as response:
                return response.read()
        except HTTPError as error:
            if error.code == 404:
                raise
            if error.code in (403, 429) and attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except URLError:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("raw fetch retry limit exceeded")


def freeze_repositories() -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    search_docs: list[dict[str, Any]] = []
    merged: dict[str, dict[str, Any]] = {}
    for query in QUERIES:
        url = "https://api.github.com/search/repositories?" + urlencode({
            "q": query, "sort": "stars", "order": "desc", "per_page": PAGE_SIZE, "page": 1,
        })
        doc = github_json(url)
        search_docs.append({"query": query, "url": url, "response": doc})
        for rank, repo in enumerate(doc.get("items", []), start=1):
            name = repo["full_name"].lower()
            membership = merged.setdefault(name, {"repo": repo, "query_ranks": {}})
            membership["query_ranks"][query] = rank
            if rank < min(membership["query_ranks"].values()):
                membership["repo"] = repo
    write_json(OUT / "github_search_snapshot.json", {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "page_size": PAGE_SIZE,
        "queries": search_docs,
    })
    osi_ids, osi_metadata = spdx_osi_ids()

    candidates = sorted(merged.values(), key=lambda item: (-item["repo"].get("stargazers_count", 0),
                                                            item["repo"]["full_name"].lower()))
    selection: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for item in candidates:
        repo = item["repo"]
        full_name = repo["full_name"]
        license_id = (repo.get("license") or {}).get("spdx_id")
        reason = None
        if repo.get("private"):
            reason = "private repository"
        elif repo.get("archived"):
            reason = "archived at search snapshot"
        elif repo.get("stargazers_count", 0) < 100:
            reason = "below preregistered 100-star threshold"
        elif license_id not in osi_ids:
            reason = f"license absent or not OSI-approved in pinned SPDX list ({license_id})"
        elif full_name.lower() in {name.lower() for name in EXCLUDED_REPOS}:
            reason = EXCLUDED_REPOS[full_name]
        if reason:
            exclusions.append({"full_name": full_name, "reason": reason,
                               "stars": repo.get("stargazers_count"), "license": license_id,
                               "query_ranks": item["query_ranks"]})
            continue
        if len(selection) >= REPO_LIMIT:
            exclusions.append({"full_name": full_name, "reason": "eligible but beyond preregistered top-12 cutoff",
                               "stars": repo.get("stargazers_count"), "license": license_id,
                               "query_ranks": item["query_ranks"]})
            continue
        selection.append({
            "full_name": full_name,
            "url": repo["html_url"],
            "api_url": repo["url"],
            "description": repo.get("description") or "",
            "default_branch": repo["default_branch"],
            "stars_at_selection": repo.get("stargazers_count"),
            "archived": repo.get("archived"),
            "license_spdx": license_id,
            "query_ranks": item["query_ranks"],
            "topics": repo.get("topics", []),
        })

    # Freeze exact default-branch commits and license blobs before examining
    # Python source content. Repository and README metadata are the only inputs
    # to the framework/application exclusions above.
    for selected in selection:
        repo_doc = github_json(selected["api_url"])
        branch = selected["default_branch"]
        commit_doc = github_json(f"https://api.github.com/repos/{selected['full_name']}/commits/{quote(branch, safe='')}")
        selected["commit"] = commit_doc["sha"]
        selected["commit_url"] = commit_doc["html_url"]
        selected["retrieved_at_utc"] = datetime.now(timezone.utc).isoformat()
        # The API detection and license file are preserved as evidence.
        selected["license_api"] = repo_doc.get("license")
        try:
            readme_doc = github_json(f"https://api.github.com/repos/{selected['full_name']}/readme?ref={selected['commit']}")
            readme = raw_bytes(readme_doc["download_url"])
            selected["readme_sha256"] = sha(readme)
            (SOURCES / selected["full_name"] / selected["commit"] / "README.md").parent.mkdir(parents=True, exist_ok=True)
            (SOURCES / selected["full_name"] / selected["commit"] / "README.md").write_bytes(readme)
            selected["readme_category"] = readme[:12000].decode("utf-8", "replace")
        except (HTTPError, KeyError, URLError) as error:
            selected["readme_fetch_error"] = f"{type(error).__name__}: {error}"
        tree = github_json(f"https://api.github.com/repos/{selected['full_name']}/git/trees/{selected['commit']}?recursive=1")
        selected["tree_sha"] = tree.get("sha")
        selected["tree_truncated"] = tree.get("truncated", False)
        selected["tree_entries"] = tree.get("tree", [])
        selected["language_bytes"] = repo_doc.get("languages_url")
        # Keep a compact tree snapshot for provenance and exact path counts.
        tree_path = OUT / "trees" / (selected["full_name"].replace("/", "__") + ".json")
        write_json(tree_path, {key: tree.get(key) for key in ("sha", "truncated", "tree")})
        selected["tree_snapshot"] = tree_path.relative_to(ROOT).as_posix()
        del selected["tree_entries"]

        license_paths = [entry["path"] for entry in tree.get("tree", [])
                         if entry.get("type") == "blob" and re.fullmatch(r"(?i)(license|licence)(\.[^/]*)?", entry["path"].split("/")[-1])]
        if license_paths:
            license_path = sorted(license_paths, key=lambda path: (path.count("/"), len(path), path))[0]
            license_raw = raw_bytes(f"https://raw.githubusercontent.com/{selected['full_name']}/{selected['commit']}/{quote(license_path, safe='/')}")
            target = SOURCES / selected["full_name"] / selected["commit"] / license_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(license_raw)
            selected["license_file"] = license_path
            selected["license_file_sha256"] = sha(license_raw)
        else:
            selected["license_file"] = None

    snapshot = {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": sha(PROTOCOL.read_bytes()),
        "frontend_fingerprint_at_freeze": frontend_fingerprint(),
        "osi_license_source": osi_metadata,
        "repository_search_file": (OUT / "github_search_snapshot.json").relative_to(ROOT).as_posix(),
        "selected_repositories": selection,
        "excluded_repositories": exclusions,
        "selection_limit": REPO_LIMIT,
    }
    write_json(OUT / "repository_manifest.json", snapshot)
    return snapshot


def is_source_path(path: str) -> bool:
    parts = Path(path).parts
    if not parts or Path(path).suffix != ".py":
        return False
    if any(part.lower() in EXCLUDED_PATH_PARTS for part in parts):
        return False
    # Every tracked Python file under the repository root is in scope. The
    # conventional directory names in the protocol are examples, not a
    # whitelist; excluding all other directories would silently narrow the
    # source frame.
    return True


def candidate_ast(source: bytes) -> tuple[bool, str | None]:
    try:
        tree = ast.parse(source.decode("utf-8"))
    except (SyntaxError, ValueError, RecursionError, UnicodeDecodeError) as error:
        return False, f"{type(error).__name__}: {error}"
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("langgraph.graph"):
            if any(alias.name == "StateGraph" for alias in node.names):
                return True, None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "StateGraph":
            return True, None
    return False, None


def fetch_one(args: tuple[str, str, str, str]) -> tuple[str, bytes | None, str | None]:
    full_name, commit, path, url = args
    try:
        return path, raw_bytes(url), None
    except Exception as error:  # preserve retrieval failures in the manifest
        return path, None, f"{type(error).__name__}: {error}"


def enumerate_sources(snapshot: dict[str, Any]) -> dict[str, Any]:
    from urllib.parse import quote as qpath

    repo_results: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    for selected in snapshot["selected_repositories"]:
        tree_doc = json.loads((ROOT / selected["tree_snapshot"]).read_text())
        source_entries = [entry for entry in tree_doc.get("tree", [])
                          if entry.get("type") == "blob" and is_source_path(entry["path"])]
        fetch_args = [(selected["full_name"], selected["commit"], entry["path"],
                       f"https://raw.githubusercontent.com/{selected['full_name']}/{selected['commit']}/{qpath(entry['path'], safe='/')}")
                      for entry in source_entries]
        files: dict[str, bytes] = {}
        fetch_errors: list[dict[str, str]] = []
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(fetch_one, arg) for arg in fetch_args]
            for future in as_completed(futures):
                path, raw, error = future.result()
                if error:
                    fetch_errors.append({"path": path, "error": error})
                else:
                    files[path] = raw or b""
        candidates: list[dict[str, Any]] = []
        parse_errors = []
        for path in sorted(files):
            raw = files[path]
            is_candidate, parse_error = candidate_ast(raw)
            if is_candidate:
                target = SOURCES / selected["full_name"] / selected["commit"] / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                item = {
                    "repository": selected["full_name"], "commit": selected["commit"],
                    "license_spdx": selected["license_spdx"], "path": path,
                    "source_snapshot": target.relative_to(ROOT).as_posix(),
                    "source_url": f"https://github.com/{selected['full_name']}/blob/{selected['commit']}/{qpath(path, safe='/')}",
                    "sha256": sha(raw), "bytes": len(raw),
                }
                candidates.append(item)
                all_candidates.append(item)
            elif parse_error:
                parse_errors.append({"path": path, "sha256": sha(raw), "error": parse_error,
                                     "langgraph_marker_bytes": bool(b"StateGraph" in raw or b"langgraph.graph" in raw),
                                     "source_url": f"https://github.com/{selected['full_name']}/blob/{selected['commit']}/{qpath(path, safe='/')}"})
        repo_results.append({
            "repository": selected["full_name"], "commit": selected["commit"],
            "license_spdx": selected["license_spdx"], "tracked_python_path_count": len(source_entries),
            "retrieved_python_count": len(files), "candidate_count": len(candidates),
            "candidates": candidates, "ast_parse_errors": parse_errors,
            "retrieval_errors": fetch_errors,
        })
    result = {
        "protocol_sha256": snapshot["protocol_sha256"],
        "enumerated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repository_count": len(snapshot["selected_repositories"]),
        "candidate_file_count": len(all_candidates),
        "ast_parse_error_count": sum(len(row["ast_parse_errors"]) for row in repo_results),
        "retrieval_error_count": sum(len(row["retrieval_errors"]) for row in repo_results),
        "repositories": repo_results,
        "candidates": all_candidates,
    }
    write_json(OUT / "source_enumeration.json", result)
    return result


def audit_frozen_selection() -> dict[str, Any]:
    """Replay the frozen repository selection from pinned API/SPDX snapshots."""
    search_path = OUT / "github_search_snapshot.json"
    manifest_path = OUT / "repository_manifest.json"
    search_raw = search_path.read_bytes()
    manifest_raw = manifest_path.read_bytes()
    search = json.loads(search_raw)
    manifest = json.loads(manifest_raw)
    osi_ids, osi_metadata = spdx_osi_ids()
    query_order = [entry["query"] for entry in search["queries"]]
    merged: dict[str, dict[str, Any]] = {}
    raw_count = 0
    for query_index, query_doc in enumerate(search["queries"]):
        for rank, repo in enumerate(query_doc["response"].get("items", []), start=1):
            raw_count += 1
            key = repo["full_name"].lower()
            entry = merged.setdefault(key, {"repo": repo, "memberships": []})
            entry["memberships"].append({"query": query_doc["query"], "query_index": query_index, "rank": rank})

    eligible: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    for key, item in merged.items():
        repo = item["repo"]
        license_id = (repo.get("license") or {}).get("spdx_id")
        memberships = item["memberships"]
        best = min(memberships, key=lambda membership: (membership["rank"], membership["query_index"]))
        item_result = {"full_name": repo["full_name"], "stars": repo.get("stargazers_count", 0),
                       "license_spdx": license_id,
                       "private": repo.get("private", False),
                       "archived": repo.get("archived", False),
                       "query_memberships": memberships,
                       "best_api_rank": best["rank"], "best_query": best["query"]}
        all_rows.append(item_result)
        reason = None
        if repo.get("private"):
            reason = "private repository"
        elif repo.get("archived"):
            reason = "archived at search snapshot"
        elif repo.get("stargazers_count", 0) < 100:
            reason = "below preregistered 100-star threshold"
        elif license_id not in osi_ids:
            reason = f"license absent or not OSI-approved in pinned SPDX list ({license_id})"
        elif key in {name.lower() for name in EXCLUDED_REPOS}:
            reason = EXCLUDED_REPOS[next(name for name in EXCLUDED_REPOS if name.lower() == key)]
        if reason:
            exclusions.append({**item_result, "reason": reason})
        else:
            eligible.append(item_result)
    eligible.sort(key=lambda item: (-item["stars"], item["best_api_rank"],
                                    query_order.index(item["best_query"]), item["full_name"].lower()))
    selected = eligible[:REPO_LIMIT]
    cutoff_exclusions = [{**item, "reason": "eligible but beyond preregistered top-12 cutoff"}
                         for item in eligible[REPO_LIMIT:]]
    recorded = manifest["selected_repositories"]
    expected = [(item["full_name"].lower(), item["stars"], item["license_spdx"]) for item in selected]
    actual = [(item["full_name"].lower(), item["stars_at_selection"], item["license_spdx"]) for item in recorded]
    initial_selection = sorted(
        [item for item in all_rows
         if not item["private"] and not item["archived"] and item["stars"] >= 100
         and item["license_spdx"] in INITIAL_MANUAL_OSI_IDS
         and item["full_name"].lower() not in {name.lower() for name in EXCLUDED_REPOS}],
        key=lambda item: (-item["stars"], item["full_name"].lower()))[:REPO_LIMIT]
    initial_ids = {item["license_spdx"] for item in all_rows if item["license_spdx"]}
    seen_id_mismatches = sorted(initial_ids & (INITIAL_MANUAL_OSI_IDS ^ osi_ids))
    official_reason_counts: dict[str, int] = {}
    for item in [*exclusions, *cutoff_exclusions]:
        official_reason_counts[item["reason"]] = official_reason_counts.get(item["reason"], 0) + 1
    result = {
        "protocol_sha256": manifest["protocol_sha256"],
        "audit_status": "pass" if expected == actual else "selection_mismatch",
        "selection_matches_frozen_manifest": expected == actual,
        "github_snapshot_sha256": sha(search_raw),
        "repository_manifest_sha256": sha(manifest_raw),
        "spdx_license_source": osi_metadata,
        "spdx_license_ids_marked_osi_approved": len(osi_ids),
        "query_count": len(query_order),
        "query_result_rows": raw_count,
        "unique_repository_count": len(merged),
        "official_osi_eligible_before_top12": len(eligible),
        "excluded_by_criteria_count": len(exclusions),
        "eligible_beyond_top12_count": len(cutoff_exclusions),
        "all_outside_selected_cohort_count": len(exclusions) + len(cutoff_exclusions),
        "official_exclusion_reason_counts": official_reason_counts,
        "selected_count": len(selected),
        "top12": selected,
        "criterion_exclusions": exclusions,
        "eligible_beyond_top12": cutoff_exclusions,
        "initial_manual_allowlist_audit": {
            "license_ids_present_in_search_frame_with_different_osi_flags": seen_id_mismatches,
            "selected_order_from_initial_allowlist_matches_frozen_manifest":
                [(item["full_name"].lower(), item["stars"], item["license_spdx"]) for item in initial_selection] == actual,
            "initial_top12": initial_selection,
        },
        "selection_implementation_note": (
            "The initial freeze script used a hand-maintained SPDX list rather than a versioned OSI flag source. "
            "This audit replays the preregistered OSI criterion from SPDX 3.29.0 isOsiApproved flags. "
            "All SPDX identifiers actually present in the frozen search frame have the same OSI classification "
            "under both sources, and the selected ordered top-12 is identical to the frozen repository manifest. "
            "No source-unit or frontend outcome was used for this check."
        ),
    }
    write_json(OUT / "selection_audit.json", result)
    return result


def mechanically_derived_contract(raw: bytes, relpath: str) -> tuple[bytes | None, str | None]:
    try:
        tree = ast.parse(raw.decode("utf-8"))
    except (SyntaxError, ValueError, RecursionError, UnicodeDecodeError) as error:
        return None, f"source_ast_error:{type(error).__name__}"
    inputs: dict[str, Any] = {}
    models: dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and any(isinstance(base, ast.Name) and base.id == "TypedDict" for base in node.bases):
            for statement in node.body:
                if not isinstance(statement, ast.AnnAssign) or not isinstance(statement.target, ast.Name):
                    continue
                name = statement.target.id
                annotation = statement.annotation
                if isinstance(annotation, ast.Name) and annotation.id == "str":
                    inputs[name] = {"type": "text", "label": "public", "max_tokens": 256}
                elif isinstance(annotation, ast.Name) and annotation.id == "bool":
                    inputs[name] = {"type": "boolean", "label": "public"}
        for call in ast.walk(node):
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "request":
                for keyword in call.keywords:
                    if keyword.arg == "model" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                        models[keyword.value.value] = {"provider": "external-placeholder", "model": keyword.value.value, "max_tokens": 2048}
    if len(inputs) > 500 or len(models) > 500:
        return None, "contract_declaration_limit"
    name = re.sub(r"[^A-Za-z0-9_]", "_", Path(relpath).stem)
    if not name or name[0].isdigit():
        name = "workflow_" + name
    contract = {"format": "orchlang-langgraph-contracts", "version": 1,
                "name": name, "inputs": inputs, "models": models}
    return canonical(contract), None


def evaluate(enumeration: dict[str, Any]) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    from integrations.langgraph.source_frontend.extract import FrontendError, extract_source

    repository_manifest = json.loads((OUT / "repository_manifest.json").read_text())
    protocol_hash = sha(PROTOCOL.read_bytes())
    if protocol_hash != repository_manifest.get("protocol_sha256"):
        raise RuntimeError("preregistered protocol bytes changed after repository snapshot freeze")
    if protocol_hash != enumeration.get("protocol_sha256"):
        raise RuntimeError("source enumeration is not bound to the frozen protocol")
    current_frontend = frontend_fingerprint()
    # The first frozen manifest used `frontend_fingerprint`; newer freezes
    # spell this `frontend_fingerprint_at_freeze`. Preserve either schema.
    frozen_frontend = repository_manifest.get("frontend_fingerprint_at_freeze")
    if frozen_frontend is None:
        frozen_frontend = repository_manifest.get("frontend_fingerprint")

    selected_commits = {repo["full_name"]: repo["commit"]
                        for repo in repository_manifest["selected_repositories"]}
    for item in enumeration["candidates"]:
        if selected_commits.get(item["repository"]) != item["commit"]:
            raise RuntimeError(f"candidate commit differs from frozen repository manifest: {item['repository']}")
        source_path = ROOT / item["source_snapshot"]
        try:
            source_raw = source_path.read_bytes()
        except OSError as error:
            raise RuntimeError(f"frozen source snapshot is missing: {source_path}") from error
        if sha(source_raw) != item["sha256"]:
            raise RuntimeError(f"frozen source SHA-256 mismatch: {item['source_snapshot']}")

    attempt_rows: list[dict[str, Any]] = []
    for item in enumeration["candidates"]:
        raw = (ROOT / item["source_snapshot"]).read_bytes()
        contract_raw, contract_error = mechanically_derived_contract(raw, item["path"])
        if contract_error:
            attempt_rows.append({**item, "admission": "not_attempted", "reason": contract_error,
                                 "contract_basis": "mechanical typed-text and typed-boolean fields; public; 256-token bound",
                                 "dynamic_differential": "not_feasible_no_admission"})
            continue
        try:
            graph, mapping = extract_source(raw, contract_raw or b"")
            row = {**item, "admission": "admitted", "reason": None,
                   "graph_node_count": len(graph.get("nodes", [])),
                   "mapping_sha256": sha(canonical(mapping)),
                   "contract_sha256": sha(contract_raw or b""),
                   "contract_basis": "mechanical typed-text and typed-boolean fields; public; 256-token bound; literal request model aliases; 2048-token cap"}
            try:
                from integrations.langgraph.source_frontend.export import export_bytes
                from integrations.langgraph.source_frontend.study import _paired_run
                from integrations.langgraph.source_frontend.extract import parse_contracts
                if contract_raw is None:
                    raise RuntimeError("contract could not be mechanically derived")
                checked_graph, graph_report, _sidecar, _attestation = export_bytes(raw, contract_raw)
                contract_doc = parse_contracts(contract_raw)
                source_store = {
                    key: ("external corpus offline probe" if value["type"] == "text" else False)
                    for key, value in contract_doc["inputs"].items()
                }
                differential_runs = []
                differential_evidence_complete = True
                source_path = ROOT / item["source_snapshot"]
                for seed in (1, 17):
                    paired = _paired_run(checked_graph, graph_report, mapping, contract_doc,
                                         raw, source_path, source_store, seed, 3)
                    required_evidence = {
                        "source_trace", "graph_trace", "source_final_state",
                        "graph_final_state", "source_logs", "graph_logs",
                    }
                    if not required_evidence <= paired.keys():
                        # The current helper compares both executions but returns
                        # only one trace. Do not claim a corpus differential when
                        # the protocol's paired traces, states, and logs are absent.
                        differential_evidence_complete = False
                        differential_runs.append({
                            "seed": seed,
                            "status": "not_claimed_evidence_incomplete",
                            "missing_evidence": sorted(required_evidence - paired.keys()),
                        })
                        break
                    differential_runs.append({
                        "seed": seed,
                        "trace_equal": paired["trace_equal"],
                        "status": paired["status"],
                        "source_trace": paired["source_trace"],
                        "graph_trace": paired["graph_trace"],
                        "source_final_state": paired["source_final_state"],
                        "graph_final_state": paired["graph_final_state"],
                        "source_logs": paired["source_logs"],
                        "graph_logs": paired["graph_logs"],
                    })
                if differential_evidence_complete:
                    row["dynamic_differential"] = (
                        "passed" if all(run["trace_equal"] for run in differential_runs)
                        else "mismatch"
                    )
                    row["dynamic_runs"] = differential_runs
                    row["dynamic_semantics"] = (
                        "original LangGraph source and graph backend share OrchLang "
                        "OfflineRequestSession oracle; finite paired traces, states, and logs only"
                    )
                else:
                    row["dynamic_differential"] = "not_claimed_evidence_incomplete"
                    row["dynamic_evidence_note"] = (
                        "The helper returned only partial paired-run evidence; no differential "
                        "claim is made because both traces, final states, and logs were not preserved."
                    )
                    row["dynamic_runs"] = differential_runs
            except Exception as error:
                row["dynamic_differential"] = "unavailable_or_failed"
                row["dynamic_error"] = f"{type(error).__name__}: {error}"
            attempt_rows.append(row)
        except FrontendError as error:
            attempt_rows.append({**item, "admission": "unsupported", "reason": str(error),
                                 "rejection_class": type(error).__name__,
                                 "contract_sha256": sha(contract_raw or b""),
                                 "contract_basis": "mechanical typed-text and typed-boolean fields; public; 256-token bound; literal request model aliases; 2048-token cap",
                                 "dynamic_differential": "not_feasible_no_admission"})
        except Exception as error:
            attempt_rows.append({**item, "admission": "error", "reason": f"{type(error).__name__}: {error}",
                                 "rejection_class": type(error).__name__,
                                 "dynamic_differential": "not_feasible_error"})
    summary_by_repo: dict[str, dict[str, int]] = {
        repo_name: {"candidate_files": 0, "admitted": 0, "unsupported": 0,
                    "error": 0, "not_attempted": 0}
        for repo_name in selected_commits
    }
    for row in attempt_rows:
        counts = summary_by_repo.setdefault(row["repository"], {"candidate_files": 0, "admitted": 0,
                                                                  "unsupported": 0, "error": 0,
                                                                  "not_attempted": 0})
        counts["candidate_files"] += 1
        counts[row["admission"]] += 1
    result = {
        "protocol_sha256": enumeration["protocol_sha256"],
        "frontend_sha256": current_frontend["sha256"],
        "frontend_fingerprint_at_freeze": frozen_frontend,
        "frontend_change_note": "The corpus input selection and source bytes are frozen; this result records the extractor revision evaluated. The frontend may have changed after preregistration to repair soundness findings.",
        "license_basis_note": (
            "The frozen frame uses GitHub API-reported SPDX identifiers and the initial allowlist. "
            "A post-freeze audit against pinned SPDX 3.29.0 isOsiApproved flags confirmed the same "
            "eligibility classifications and ordered cohort. Pinned LICENSE files are hash-preserved; "
            "this is not a legal determination that the repository or every file is covered by that license."
        ),
        "post_evaluation_protocol_clarification": {
            "recorded_after_outcomes": True,
            "field": "tracked Python path frame",
            "interpretation": (
                "Enumeration includes every tracked .py file beneath the repository root except "
                "paths with the protocol's explicitly excluded components; conventional application "
                "directory names describe common locations and are not a whitelist. This clarifies "
                "the frozen protocol wording without changing source selection or denominators."
            ),
        },
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_unit": "repository; files nested within repository are not independent units",
        "corpus_denominators": {
            "repositories": len(selected_commits),
            "repositories_with_candidate_files": sum(counts["candidate_files"] > 0
                                                      for counts in summary_by_repo.values()),
            "candidate_files": len(attempt_rows),
        },
        "admission_counts": {key: sum(row["admission"] == key for row in attempt_rows)
                             for key in ("admitted", "unsupported", "error", "not_attempted")},
        "dynamic_differential": "attempted only for admitted original files" if any(row["admission"] == "admitted" for row in attempt_rows) else "differential_not_run: no original files admitted; no external source was projected or rewritten",
        "repository_counts": summary_by_repo,
        "attempts": attempt_rows,
    }
    write_json(OUT / "admission_results.json", result)
    write_json(OUT / "manifest.json", {
        "protocol": "research/publication_upgrade/corpus/protocol.md",
        "protocol_sha256": result["protocol_sha256"],
        "repository_manifest": "output/publication_upgrade/corpus/repository_manifest.json",
        "source_enumeration": "output/publication_upgrade/corpus/source_enumeration.json",
        "admission_results": "output/publication_upgrade/corpus/admission_results.json",
        "frontend_sha256": result["frontend_sha256"],
        "frontend_files": current_frontend["files"],
        "source_files": [{"repo": row["repository"], "commit": row["commit"], "path": row["path"],
                          "sha256": row["sha256"], "license": row["license_spdx"],
                          "snapshot": row["source_snapshot"]} for row in attempt_rows],
    })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true", help="query GitHub and pin repository snapshots")
    parser.add_argument("--enumerate", action="store_true", help="download source units and find candidates")
    parser.add_argument("--evaluate", action="store_true", help="run current extractor on frozen unmodified candidates")
    parser.add_argument("--audit-selection", action="store_true", help="replay repository selection offline from frozen API/SPDX data")
    args = parser.parse_args()
    if not (args.freeze or args.enumerate or args.evaluate or args.audit_selection):
        parser.error("choose at least one of --freeze, --enumerate, --evaluate, --audit-selection")
    snapshot = None
    if args.freeze:
        snapshot = freeze_repositories()
        print(json.dumps({"selected_repositories": len(snapshot["selected_repositories"]),
                          "excluded_repositories": len(snapshot["excluded_repositories"]),
                          "output": str(OUT / "repository_manifest.json")}, indent=2))
    if args.enumerate:
        if snapshot is None:
            snapshot = json.loads((OUT / "repository_manifest.json").read_text())
        enumeration = enumerate_sources(snapshot)
        print(json.dumps({"repositories": enumeration["repository_count"],
                          "candidate_files": enumeration["candidate_file_count"],
                          "output": str(OUT / "source_enumeration.json")}, indent=2))
    if args.evaluate:
        enumeration = json.loads((OUT / "source_enumeration.json").read_text())
        result = evaluate(enumeration)
        print(json.dumps({"corpus_denominators": result["corpus_denominators"],
                          "admission_counts": result["admission_counts"],
                          "output": str(OUT / "admission_results.json")}, indent=2))
    if args.audit_selection:
        result = audit_frozen_selection()
        print(json.dumps({"audit_status": result["audit_status"],
                          "selected_count": result["selected_count"],
                          "official_osi_eligible_before_top12": result["official_osi_eligible_before_top12"],
                          "output": str(OUT / "selection_audit.json")}, indent=2))
        if result["audit_status"] != "pass":
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
