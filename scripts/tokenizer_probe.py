"""CPU-only tokenizer boundary observations under a fixed development protocol."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tokenizers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import tokenizers
    protocol_path = ROOT / "bench/protocols/tokenizers-development-v1.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if tokenizers.__version__ != protocol["tokenizers_version"]:
        raise ValueError("wrong tokenizer library version; no implicit substitution")
    files = json.loads((args.tokenizers / "manifest.json").read_text())
    if len(files) != len(protocol["families"]):
        raise ValueError("incomplete tokenizer family set")
    args.output.mkdir(parents=True, exist_ok=False)
    rows, combinations = [], []
    for family in protocol["families"]:
        entry = next(e for e in files if e["id"] == family["id"])
        if any(entry[k] != family[k] for k in ("repo", "revision", "license")):
            raise ValueError("tokenizer revision/metadata mismatch")
        path = args.tokenizers / entry["file"]
        if path.name != family["id"] + ".json" or sha(path) != entry["sha256"]:
            raise ValueError("tokenizer content/hash mismatch")
        tokenizer = tokenizers.Tokenizer.from_file(str(path))
        tokenizer.no_padding()
        tokenizer.no_truncation()
        for text in protocol["texts"]:
            plain = tokenizer.encode(text, add_special_tokens=False).ids
            serialized = tokenizer.encode(text, add_special_tokens=True).ids
            synthetic = (len(text.encode("utf-8")) + 3) // 4
            rows.append(dict(family=entry["id"], text=text, utf8_bytes=len(text.encode("utf-8")),
                             mock_estimate=synthetic, plain_ids=plain, special_ids=serialized,
                             plain_tokens=len(plain), with_special_tokens=len(serialized),
                             plain_exceeds_mock=len(plain) > synthetic))
        for a, b in protocol["concatenations"]:
            encode = lambda t: tokenizer.encode(t, add_special_tokens=False).ids
            split = len(encode(a)) + len(encode(b))
            joined = len(encode(a + b))
            combinations.append(dict(family=entry["id"], left=a, right=b,
                                     separate_tokens=split, joined_tokens=joined, additive=split == joined))
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    manifest = dict(schema_version="1", status="completed", purpose="development-boundary-probe",
                    timestamp_utc=datetime.now(timezone.utc).isoformat(), source_commit=commit,
                    dirty_tree=bool(dirty), script_sha256=sha(Path(__file__).resolve()),
                    protocol_sha256=sha(protocol_path), protocol_status=protocol["status"],
                    tokenizer_artifacts=files, tokenizers_version=tokenizers.__version__,
                    python=sys.version, platform=platform.platform(),
                    spent_usd="0.00", outstanding_reserved_usd="0.00", model_inference=False,
                    external_workflows=0)
    for name, value in (("manifest", manifest), ("tokens", rows), ("concatenations", combinations)):
        (args.output / (name + ".json")).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(dict(text_cases=len(rows), concatenations=len(combinations), spent_usd="0.00")))


if __name__ == "__main__":
    main()
