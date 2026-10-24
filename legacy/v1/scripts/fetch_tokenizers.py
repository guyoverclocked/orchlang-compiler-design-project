"""Fetch only public pinned tokenizer JSON files, never weights or credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads((ROOT / "bench/protocols/tokenizers-development-v1.json").read_text(encoding="utf-8"))
    records = []
    for family in protocol["families"]:
        url = f'https://huggingface.co/{family["repo"]}/resolve/{family["revision"]}/tokenizer.json'
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(20_000_001)
        if len(data) > 20_000_000:
            raise ValueError("unexpectedly large tokenizer; no fallback allowed")
        json.loads(data)
        name = family["id"] + ".json"
        (args.output / name).write_bytes(data)
        records.append(dict(**family, file=name, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), url=url))
    (args.output / "manifest.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
