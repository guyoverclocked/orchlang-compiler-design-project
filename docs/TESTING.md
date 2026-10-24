# Testing and validation guide

This guide lists every check in the artifact, what it establishes, how to run it,
and where the recorded output from our runs is kept (`experiments/results/`).
Commands are run from the repository root.

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
# Lean 4.19.0 from https://github.com/leanprover/lean4/releases/tag/v4.19.0
export LEAN=/path/to/lean-4.19.0-linux/bin/lean
# Models (needed only for model-backed checks), pinned and checksummed:
python experiments/fetch_models.py models && export ORCHLANG_MODELS=$PWD/models/models.json
```

## 1. Proof check (seconds)

```bash
$LEAN proof/ShapeCore.lean
```

Expected: one line per main theorem listing only `propext` and `Quot.sound`
(`erase_correct` lists only `propext`), and no errors. A `sorry` would appear as
`sorryAx`. The file's `#guard` regression tests run as part of the check.
Recorded: `experiments/results/logs/lean-check.log`.

## 2. Unit tests (seconds)

```bash
python -m unittest discover -s tests -v
```

11 tests: parser diagnostics, label inference, leak detection, all four shaping
strategies against the padding discipline, alignment cost and model separation,
mock-runtime noninterference and functional preservation, and exact padding in
both padding modes. With `ORCHLANG_MODELS` set, two more tests check that the chat
renderers reproduce each model's own Jinja template byte for byte and that padding
is exact with the real tokenizers on multi-byte text; without it they are skipped.
Recorded: `experiments/results/logs/unit-tests.log`.

## 3. Differential test of compiler, runtime and validator (minutes)

```bash
python experiments/differential.py --programs 1000 --runs 4 --output out/differential.json
```

Generates random core programs with random secret labellings, shapes each with all
four strategies, validates every original and shaped program in Lean, and runs each
shaped program under pairs of different secrets with a mock model. Expected: all
shaped programs accepted; Python and the detector agree with Lean on every original;
identical traces in every pair; traces equal to Lean's static shape; final stores
equal to the original program's. Recorded: `experiments/results/differential.json`
and `logs/differential.log`.

## 4. Fault injection (minutes; needs model tokenizers)

```bash
python experiments/mutation.py --output out/mutation.json
```

Applies 12 compiler-bug operators to the shaped versions of the nine workflows and
checks each mutant with Lean and with an independent oracle (runtime plus a mock
model whose words drive the workflows' routing tests). Expected: `leak_accepted` is
0, meaning that no mutant the oracle shows to leak is accepted. Recorded:
`experiments/results/mutation.json`.

## 5. Transparency and conformance (about 20 minutes on 4 CPU cores)

```bash
python experiments/transparency.py --output out/transparency.json                 # isolated padding
python experiments/transparency.py --mode inband --output out/transparency-inband.json
```

Compares natural decoding of the original request with the shaped call (padded to
T tokens, forced to N > cap tokens, visible output cut at the stop token and cap)
on the same seed, greedy and sampled. Expected: every visible output equal and every
call reporting exactly T input and N output tokens. The in-band run, recorded in
`experiments/results/transparency-inband.json`, tests the forced-decoding half on an
in-band padded prompt: 120 of 120 cases equal, 120 of 120 exact counts.

## 6. Workflow experiments (about 13 CPU hours)

```bash
bash experiments/run_all.sh out/runs
```

Resumable; see `docs/REPRODUCE.md` for the aggregation and paper build. Run nothing
else CPU-intensive at the same time: llama.cpp uses all cores, and concurrent jobs
distort latency measurements.

## 7. Legacy prototype

```bash
cd legacy/v1 && make check && python -m unittest discover -s tests -p "test_*.py"
```

Expected: 106/106 C++ tests and the legacy Python tests pass.

## Continuous integration

`.github/workflows/ci.yml` runs checks 1–3 and the legacy C++ suite on every push.
