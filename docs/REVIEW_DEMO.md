# OrchLang demonstration script

About ten minutes. Nothing here needs internet access except the optional
tokenizer check in §6; the compiler makes no network requests. Every command and
expected output below was run against the current build.

Run everything from the repository root after `make clean && make check`.

---

## 0:00 – 0:45  The problem

Say: "A program that calls a language model can go wrong in three ways before
the model says anything. It can spend more than you meant. It can let data go
where it shouldn't: a secret into a prompt, or text from a web page into a tool
call. And the requests it sends can themselves reveal a secret, because anyone
who sees the traffic or the bill sees which requests were made. OrchLang checks
all three from the source, before anything runs."

---

## 0:45 – 1:15  Build, test, proofs

```sh
make clean && make check
```

Expected: a strict C++17 build with `-Wall -Wextra -pedantic` and no warnings,
`Passed 137/137 tests.`, the valid corpus accepted, every invalid example
rejected, and a certificate for each valid workflow.

```sh
make proofs
```

Expected (needs Coq 8.18): seven lines `Closed under the global context`, one
per main theorem. Say: "Four results of the paper are checked by Coq, with no
axioms."

---

## 1:15 – 2:15  Cost is structural, not a sum

```sh
./orchc cost examples/valid/branching_cost.orch
```

Expected: the derivation ends with
`branch-max  max(then=432, else=1211)  => 1211 tokens`. The branch costs its more
expensive arm, not the sum.

```sh
./orchc cost examples/valid/bounded_retry.orch
```

Expected: `retry-scale  3 x 1110  => 3330 tokens`. Say: "A flat sum over call
sites says 1110. The workflow can spend 3330. On the benchmark, a flat sum is
exceeded on 14.9% of executions; the certified bound on none."

---

## 2:15 – 3:15  Indirect prompt injection is a type error

```sh
./orchc check examples/invalid/untrusted_sink.orch
```

Expected: `error [E233] untrusted value reaches tool 'publish'`. Say: "A model's
answer is only as trustworthy as what reached its prompt."

```sh
./orchc check bench/security/unsafe/InjectionTransitive.orch
./orchc check bench/security/safe/InjectionTransitiveEndorsed.orch
```

Expected: `E233` through two model calls; then accepted. The difference is one
`endorse(...) because "..."` line, which the certificate records verbatim.

```sh
./orchc check examples/invalid/implicit_flow.orch
```

Expected: `E234`: a secret decides *whether* a tool fires, which reveals it.

---

## 3:15 – 5:15  The requests reveal the secret — and two wrong answers

```sh
./orchc check examples/invalid/cost_channel.orch
```

Expected: `E236`, saying the arms call different endpoints, and
`has 2 distinguishable behaviours ... may reveal up to 1 bits`.

Say: "No secret value goes anywhere. But one arm calls the large model and the
other the small one, and the bill says which."

```sh
./orchc check examples/invalid/equal_bounds.orch
```

Expected: `E236`: `then-arm sends [m(x)] and else-arm sends [m(y)]`.

Say: "My first rule accepted this, because both arms have the same worst-case
cost. An external audit showed the bill still moves with the secret: a maximum is
not a value. My second rule compared the *sizes* of the requests instead."

```sh
./orchc check audit/2026-09-25/equal_size_template.orch --relational-rule sizes
./orchc check audit/2026-09-25/equal_size_template.orch
```

Expected: the size rule accepts; the content rule rejects with `E236`, naming
the two request texts, `"Escalate in detail!: " + ticket` against
`"Acknowledge briefly: " + ticket`, which have the same size.

```sh
./orchc run audit/2026-09-25/equal_size_template.orch --seed 3 --pin ticket=20 --pin enterprise=true  --provider content
./orchc run audit/2026-09-25/equal_size_template.orch --seed 3 --pin ticket=20 --pin enterprise=false --provider content
```

Expected: the billing lines differ (`out 0` against `out 39`) with the same seed
and the same input. Say: "A provider answers what it is asked, not how long the
question is. A real model does the same: fifteen pairs of requests of identical
token length, fifteen different answer lengths. And there's a theorem, checked in
Coq, that no analysis comparing sizes can be sound without rejecting a branch
whose two arms are identical."

---

## 5:15 – 6:00  A little leakage, on purpose

```sh
./orchc check bench/leakage/accept/OneBitTier.orch
```

Expected: `warning [W238] ... may reveal up to 1 bits ... within its declared
budget`, then accepted. Say: "When the requests must depend on a secret, the
workflow declares how many bits it may reveal, and the compiler proves the bound:
log2 of the number of distinct request patterns."

---

## 6:00 – 7:00  Token bounds that hold for real tokenizers

Optional, needs `pip install tiktoken`:

```sh
python3 -c "import tiktoken; e=tiktoken.get_encoding('cl100k_base'); print([len(e.encode(s)) for s in [' Attribute','profiles',' Attributeprofiles']])"
```

Expected: `[1, 1, 6]`. Say: "Token counts don't add up, so you can't bound a
prompt by adding the token counts of its parts. Bytes do add up. OrchLang bounds
bytes and converts once per request through a measured contract for the model's
tokenizer."

```sh
./orchc check bench/real/lg-reflection.orch
```

Expected: `input <= 702913 @ 4 chars/token` as the estimate and
`guaranteed input <= 17262535`. Say: "The guarantee is 25 times the estimate,
because nothing stops a Mistral token from decoding to 25 bytes. A client-side byte
cap on the model closes that gap; the language supports one."

---

## 7:00 – 8:30  Real workflows

```sh
./orchc check bench/real/ad-banking-0.orch
./orchc check bench/real/ad-banking-0.annotated.orch
```

Expected: `E233 untrusted value reaches tool 'send_money'`, then accepted with
one endorsement. Say: "This is AgentDojo's pay-the-bill task: the bill is a file
an attacker can write to, and the amount and recipient come from it. The checker
marks exactly where that trust decision is made."

Open `bench/real/PROTOCOL.md` and `bench/real/EXCLUSIONS.md`. Say: "52 candidate
workflows from three public sources, pinned by commit. Labels were committed
before any port was written, and the compiler was frozen before the held-out
ports. 30 are ported, 22 excluded with reasons: most because the model decides
what runs next. And none has a secret, so the side-channel analysis found nothing
to check. The paper says that in the abstract."

---

## 8:30 – 9:15  The certificate

```sh
./orchc certify examples/valid/untrusted_endorsed.orch
```

Expected: JSON with `"version": 2`, a `source_sha256`, the relational rule, the
bounds, the leakage report, and the endorsement with its justification
(`passed the offline schema and length validator`).

---

## 9:15 – 10:00  The claims are falsifiable

```sh
python bench/evaluate.py --offline
```

Expected: exits 0; the report is marked PARTIAL because the experiments that
download tokenizers and a model are skipped. Say: "The harness fails on any
certificate violation, any accepted workflow whose observer can tell two secrets
apart, any real workflow whose labelled error is missed, and any port whose prompt
is not the source's text. It was rewritten twice because earlier versions could
not fail in the ways that mattered."

---

## If asked

* **"Isn't this Ngo et al. with tokens?"** Their analysis compares sizes; Theorem 6
  shows that cannot be sound for content-dependent providers. Their quantitative
  bound is at least log2(cap+1) bits for any workflow with a call: 6 to 9 bits on
  workflows we prove leak nothing.
* **"Does anyone's real workflow have this problem?"** Not in our corpus. The
  pattern is a branch on private data that is not itself sent to a model: user
  tier, a risk flag, a local PII detector. We haven't shown deployed workflows
  contain it.
* **"Is the C++ verified?"** No. The Coq development covers the core calculus; the
  implementation is tested against it through the runtime.
