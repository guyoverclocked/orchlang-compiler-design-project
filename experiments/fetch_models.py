"""Download the pinned GGUF models used in the evaluation and write models.json.

Usage: python experiments/fetch_models.py MODEL_DIR [--all]
By default fetches the two Llama 3.2 models used by the evaluated workflows;
--all also fetches the Qwen 2.5 models used in the pilots and the replication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os

MODELS = {
    "llama1b": ("bartowski/Llama-3.2-1B-Instruct-GGUF", "067b946cf014b7c697f3654f621d577a3e3afd1c",
                "Llama-3.2-1B-Instruct-Q4_K_M.gguf", "llama3",
                "6f85a640a97cf2bf5b8e764087b1e83da0fdb51d7c9fab7d0fece9385611df83"),
    "llama3b": ("bartowski/Llama-3.2-3B-Instruct-GGUF", "5ab33fa94d1d04e903623ae72c95d1696f09f9e8",
                "Llama-3.2-3B-Instruct-Q4_K_M.gguf", "llama3",
                "6c1a2b41161032677be168d354123594c0e6e67d2b9227c84f296ad037c728ff"),
}
PILOT = {
    "qwen0.5b": ("Qwen/Qwen2.5-0.5B-Instruct-GGUF", "9217f5db79a29953eb74d5343926648285ec7e67",
                 "qwen2.5-0.5b-instruct-q4_k_m.gguf", "qwen2",
                 "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"),
    "qwen1.5b": ("Qwen/Qwen2.5-1.5B-Instruct-GGUF", "91cad51170dc346986eccefdc2dd33a9da36ead9",
                 "qwen2.5-1.5b-instruct-q4_k_m.gguf", "qwen2",
                 "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"),
}
STOPS = {"llama3": ["<|eot_id|>", "<|eom_id|>", "<|end_of_text|>"], "qwen2": ["<|im_end|>", "<|endoftext|>"]}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--replication",action="store_true",help="include Qwen 1.5B without the older 0.5B pilot")
    ap.add_argument("--completion-profile",action="store_true",help="exact two-stop Llama profile used by unified-completion-v1")
    ap.add_argument("--configure-only",action="store_true",help="verify existing local weights and write configuration without network")
    args = ap.parse_args()
    os.makedirs(args.dir, exist_ok=True)
    chosen = dict(MODELS, **(PILOT if args.all else {}))
    if args.replication:chosen['qwen1.5b']=PILOT['qwen1.5b']
    cfg = {}
    for key, (repo, rev, fn, tmpl, digest) in chosen.items():
        path=os.path.join(args.dir,fn)
        if not os.path.isfile(path):
            if args.configure_only:raise SystemExit('required pinned model is missing: '+fn)
            from huggingface_hub import hf_hub_download
            path = hf_hub_download(repo, fn, revision=rev, local_dir=args.dir)
        if digest and sha256(path) != digest:
            raise SystemExit(f"checksum mismatch for {fn}")
        stops=(["<|eot_id|>","<|end_of_text|>"] if args.completion_profile and tmpl=='llama3' else STOPS[tmpl])
        cfg[key] = {"gguf": fn, "template": tmpl,"sha256":digest,"pad_mode":"isolated", "stop": stops}
        print(key, path)
    with open(os.path.join(args.dir, "models.json"), "w") as f:
        json.dump(cfg, f, indent=1)


if __name__ == "__main__":
    main()
