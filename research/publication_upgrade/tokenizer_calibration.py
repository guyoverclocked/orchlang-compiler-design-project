#!/usr/bin/env python3
"""Calibrate character estimates on frozen offline call text and local BPEs.

Recover the historical branch's useful measurement question without importing
its different compiler semantics. This is text tokenization, not API usage,
chat envelopes, cache accounting, provider conformance, or invoice validation.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[2]
ENCODINGS = ("cl100k_base", "o200k_base", "r50k_base")
PIN = "0.12.0"
CONTROLS = [
    ("ascii", "The security team reviewed the incident report."),
    ("tamil", "பாதுகாப்பு குழு சம்பவ அறிக்கையை ஆய்வு செய்தது."),
    ("hindi", "सुरक्षा दल ने घटना की रिपोर्ट की समीक्षा की।"),
    ("japanese", "セキュリティチームはインシデント報告を確認しました。"),
    ("arabic", "راجع فريق الأمن تقرير الحادث."),
    ("emoji", "🔐🛡️🚨🔍✅"),
    ("combining", "e\u0301" * 16),
    ("composed", "é" * 16),
    ("digits", "0123456789" * 10),
    ("spaces", " " * 128),
    ("code", "def verify(x):\n    return x == {'status': 'passed'}\n"),
    ("special-looking-text", "<|endoftext|> <|im_start|>"),
]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--allow-download", action="store_true", help="one-time tokenizer data setup")
    cli.add_argument("--output", type=Path, default=ROOT / "output/publication_upgrade/tokenizer_calibration.json")
    args = cli.parse_args()
    if version("tiktoken") != PIN:
        raise SystemExit("this study requires tiktoken==" + PIN)
    cache = ROOT / "output/publication_upgrade/tokenizer_cache"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["TIKTOKEN_CACHE_DIR"] = str(cache)
    if not args.allow_download:
        import requests
        def no_network(*args, **kwargs):
            raise RuntimeError("tokenizer cache missing; run once with --allow-download")
        requests.get = no_network
    import tiktoken
    study_path = ROOT / "integrations/incident_triage/results/source_study.json"
    raw = study_path.read_bytes()
    source = json.loads(raw)
    samples = []
    for case in source["cases"]:
        for index, call in enumerate(case["calls"]):
            prefix = case["case_id"] + "/" + str(index)
            samples.extend([
                {"id": prefix + "/input", "stratum": "source-study-call", "text": call["system"] + call["user"]},
                {"id": prefix + "/output", "stratum": "source-study-call", "text": call["response"]},
            ])
    samples += [{"id": name, "stratum": "authored-control", "text": text} for name, text in CONTROLS]
    reports = []
    for name in ENCODINGS:
        enc = tiktoken.get_encoding(name)
        rows = []
        vocabulary_digest = hashlib.sha256()
        valid = 0
        max_bytes = 0
        specials = set(enc._special_tokens.values())
        for token_id in range(enc.n_vocab):
            if token_id in specials:
                continue
            try:
                token = enc.decode_single_token_bytes(token_id)
            except KeyError:
                continue
            valid += 1
            max_bytes = max(max_bytes, len(token))
            vocabulary_digest.update(token_id.to_bytes(4, "big") + len(token).to_bytes(4, "big") + token)
        for sample in samples:
            text = sample["text"]
            measured = len(enc.encode(text, disallowed_special=()))
            estimate = max(1, len(text) // 4)
            rows.append({"id": sample["id"], "stratum": sample["stratum"], "text_sha256": sha(text.encode()),
                         "codepoints": len(text), "utf8_bytes": len(text.encode()), "local_bpe_tokens": measured,
                         "character_estimate": estimate, "signed_error": estimate - measured})
        strata = {}
        for stratum in ("source-study-call", "authored-control"):
            selected = [r for r in rows if r["stratum"] == stratum]
            strata[stratum] = {"sample_count": len(selected), "underestimates": sum(r["signed_error"] < 0 for r in selected),
                              "overestimates": sum(r["signed_error"] > 0 for r in selected),
                              "exact": sum(r["signed_error"] == 0 for r in selected),
                              "signed_error_min": min(r["signed_error"] for r in selected),
                              "signed_error_max": max(r["signed_error"] for r in selected),
                              "mean_absolute_error": statistics.mean(abs(r["signed_error"]) for r in selected)}
        reports.append({"encoding": name, "ordinary_vocab_count": valid, "max_single_token_raw_bytes": max_bytes,
                        "ordinary_vocab_sha256": vocabulary_digest.hexdigest(), "strata": strata, "samples": rows})
    result = {"format": "orchlang-local-tokenizer-calibration", "version": 1, "status": "completed",
              "tiktoken_version": PIN, "source_study_sha256": sha(raw),
              "samples_sha256": sha(json.dumps(samples, ensure_ascii=False, sort_keys=True).encode()),
              "cache_files": {p.name: sha(p.read_bytes()) for p in sorted(cache.iterdir()) if p.is_file()},
              "encodings": reports,
              "scope": ["90 source-study call texts include repeated paired scenarios, not 90 independent applications",
                        "12 authored multilingual/adversarial controls; descriptive sample, no statistical generalization",
                        "full census of ordinary vocabulary token bytes; no response re-encoding bound is inferred",
                        "plain local text tokenization; provider envelopes, actual API measurements and invoices excluded"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "completed", "samples": len(samples), "encodings": [r["strata"] for r in reports]}, indent=2))


if __name__ == "__main__":
    main()
