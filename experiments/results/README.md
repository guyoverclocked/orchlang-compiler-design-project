# Recorded results

Status: 24 October 2026. The full nine-workflow evaluation is still running; this
directory holds every result produced so far. `docs/TESTING.md` explains how to
regenerate each file.

| File | What it is |
|---|---|
| `logs/lean-check.log` | `lean proof/ShapeCore.lean`: axioms of every main theorem (only `propext`, `Quot.sound`) |
| `logs/unit-tests.log` | 11 unit tests, all passing (models configured) |
| `differential.json`, `logs/differential.log` | 1,000 random programs, 5,000 Lean checks; every shaped program accepted; 16,000/16,000 trace-equal pairs and store-equal runs; Python and detector agree with Lean on all originals |
| `mutation.json` | Fault injection, 12 operators, 210 mutants: 103 leak per the oracle, all 103 rejected; 18 accepted, none leaking |
| `transparency-inband.json`, `logs/transparency-inband.log` | Forced decoding vs natural decoding on in-band padded prompts, Llama 3.2 1B: 120/120 visible outputs equal (60 greedy, 60 sampled at T=0.8), 120/120 exact input and output counts |
| `runs-inband-preliminary/` | First full runs of the Prompt Flow switch (210 inputs), routing (150) and prompt chaining (150) with **in-band** padding: `compile.json` (findings, Lean verdicts, static shapes), `orig.jsonl` and `ours.jsonl` (one record per input with usage traces) |
| `cap-tuning-preliminary.json` | Cap-tuning analysis on the switch and routing runs |
| `pilots/` | Padding-filler and placement pilots (below) |
| `logs/queue-main.log` | Timeline of the experiment queue |

## What the preliminary in-band runs showed

- Security held exactly. Every shaped run emitted the single trace predicted by Lean
  (switch 210/210, routing 150/150, chaining 150/150 conformant), so attacks were at
  chance and the mutual information was zero.
- Undefended leakage was confirmed:
  - routing: decision recovered at 95% balanced accuracy (chance 50%);
  - chaining: gate outcome recovered at 100% (chance 50%);
  - switch: intent label recovered at 41% (chance 33%).
- In-band padding hurt a small model's routing. Inserting about 100 filler tokens
  into the prompt changed Llama 3.2 1B's router decisions, and routing accuracy fell
  from 64.7% to 35.3% (McNemar p ≈ 1e-12). Chaining decisions agreed in 86% of inputs,
  and the switch showed no significant accuracy change (35% vs 32%).
- Latency of the routing runs is not usable. The routing runs overlapped other
  CPU-heavy jobs on the same machine.

## Pilots that led to isolated padding

- `pilots/filler-pilot-qwen1.5b-agnews.json`: filler choice on 80 news
  classifications with Qwen 2.5 1.5B and 150 in-band padding tokens.
  - " ." changed 6.25% of decisions (accuracy 81.25% vs 80%).
  - " pad" changed 15% (accuracy unchanged).
  - " _" changed 17.5% and cost 12.5 accuracy points.
- `pilots/placement-pilot-llama1b.log`: in-band placement on 20 routing and 20
  switch inputs with Llama 3.2 1B.
  - Routing accuracy: 60% unpadded vs 25% with padding at the end, 20% after the
    system turn, 30% inside the system message.
  - A follow-up (`pilots/filler2.py`, results below) tried other fillers at the start,
    after the system turn and at the end. Every filler that actually reached the
    100-token target dropped routing accuracy to 20–25%. The one exception was
    repeating the instruction text at the end (75%).

  Console output of `pilots/filler2.py` (20 routing inputs, Llama 3.2 1B, target about
  100 padding tokens; "tokens" is the padding actually added):

  ```
  end dot agree 0.6 acc_orig 0.6 acc_pad 0.2 tokens 100
  end newline agree 0.6 acc_orig 0.6 acc_pad 0.2 tokens 24
  end space agree 0.6 acc_orig 0.6 acc_pad 0.25 tokens 11
  end reserved agree 0.6 acc_orig 0.6 acc_pad 0.2 tokens 100
  end instr agree 0.85 acc_orig 0.6 acc_pad 0.75 tokens 125
  after_system dot agree 0.6 acc_orig 0.6 acc_pad 0.2 tokens 100
  after_system newline agree 0.55 acc_orig 0.6 acc_pad 0.2 tokens 24
  after_system space agree 1.0 acc_orig 0.6 acc_pad 0.6 tokens 11
  after_system reserved agree 0.6 acc_orig 0.6 acc_pad 0.2 tokens 100
  after_system instr agree 0.6 acc_orig 0.6 acc_pad 0.2 tokens 125
  start dot agree 0.65 acc_orig 0.6 acc_pad 0.25 tokens 100
  start reserved agree 0.6 acc_orig 0.6 acc_pad 0.25 tokens 100
  start nl_dot agree 0.6 acc_orig 0.6 acc_pad 0.2 tokens 100
  ```

  The space and newline fillers merge into multi-character tokens and did not reach
  the target, so they are not comparable.

Conclusion: in-band padding is inherently disruptive for small models. The runtime
now defaults to **isolated padding**: the serving system processes and bills the
padding tokens in an attention-isolated pass that the response cannot see, so the
model receives exactly the original prompt. This is the same kind of serving-side
support that forced decoding already needs, and it makes the Transparency hypothesis
hold for inputs as well as outputs. In-band padding remains available
(`"pad_mode": "inband"` in `models.json`) for APIs that accept only text. The
preliminary in-band runs above are kept as its evaluation.
