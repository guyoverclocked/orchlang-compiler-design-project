"""Pinned public source census. Store upstream material outside the repository."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request

SOURCES = [
    ("microsoft/promptflow", "33a68c9d3cf349d7fdfad1f41969af27543c0406"),
    ("langchain-ai/docs", "ecda7f522a6ffd5faaabb843b581fe57cd5eb782"),
]


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "OrchLang-research-census"})
    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read(5_000_001)
    if len(content) > 5_000_000:
        raise ValueError("unexpectedly large source file")
    return content


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    for repo, revision in SOURCES:
        tree = json.loads(fetch(f"https://api.github.com/repos/{repo}/git/trees/{revision}?recursive=1"))
        if tree.get("truncated"):
            raise ValueError("source census tree truncated")
        paths = [n["path"] for n in tree["tree"] if n["type"] == "blob" and (
            n["path"] == "LICENSE" or
            (repo == "microsoft/promptflow" and n["path"].startswith("examples/flows/standard/") and
             Path(n["path"]).suffix in {".py", ".yaml", ".jinja2", ".j2", ".md"}) or
            (repo == "langchain-ai/docs" and n["path"] == "src/oss/langgraph/workflows-agents.mdx"))]
        def one(path):
            data = fetch(f"https://raw.githubusercontent.com/{repo}/{revision}/{path}")
            local = args.output / repo.replace("/", "--") / path
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(data)
            return dict(repo=repo, revision=revision, path=path, sha256=hashlib.sha256(data).hexdigest(),
                        bytes=len(data), url=f"https://github.com/{repo}/blob/{revision}/{path}")
        with ThreadPoolExecutor(max_workers=4) as pool:
            records.extend(pool.map(one, sorted(paths)))
    (args.output / "manifest.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    flows = [r for r in records if r["path"].endswith("flow.dag.yaml")]
    print(json.dumps(dict(files=len(records), promptflow_standard_flows=len(flows),
                          flow_paths=[r["path"] for r in flows]), indent=2))


if __name__ == "__main__":
    main()
