# OrchLang: formal model, theorems, and proofs

This document states precisely what OrchLang's analyses guarantee and proves
it. It is the reference for `docs/PAPER.md`, which gives the same results with
proof sketches. What is mechanised in Coq is listed in §10; everything else
here is a pen-and-paper proof, and the C++ implementation is **not** verified
against any of it. The implementation is connected to the model only
empirically, by the differential tests in `tests/tests.cpp` and the harness
`bench/evaluate.py`.

Notation: Σ\* is the set of strings; `bytes(s)` is the length of the UTF-8
encoding of `s`; `·` is concatenation.

---

## 1. The core calculus

The core abstracts the parts of OrchLang the relational analysis is about.
Declarations are resolved away: a *model identity* `m` stands for everything
that determines the endpoint and its request parameters (provider, model name,
`max_tokens`, client byte cap), and a *request expression* stands for a prompt
template with its arguments substituted.

```
arguments        a  ::= "t"                  literal text
                      | x                    variable
request exprs    r  ::= (m, t0, a1, t1, …, an, tn)
guards           g  ::= π(x)                 π : Σ* → {tt, ff}, from a fixed family
commands         c  ::= skip | c1 ; c2
                      | x ← call r
                      | if g then c1 else c2
                      | retry n c            n ≥ 1
```

`π` ranges over the guard predicates the surface language has: `tokens(x) ⋈ k`
for a comparison `⋈` and a constant `k`, and truthiness of a boolean. Block
scoping (a binding made in an arm or a retry body is not visible after it) is a
well-formedness condition checked by the type system; the semantics below
assumes it.

A store `σ : Var ⇀ Σ*` maps variables to strings. Variables are partitioned
into public inputs `P`, secrets `S`, and local bindings. Declassified values
are modelled as public inputs (§5).

## 2. Providers, randomness, and couplings

**Provider.** A provider is a pair `(Π, V)`:

* `Π : M × Σ* × Ω → Σ* × ℕ` gives, for a model identity, a request text and a
  random draw, the response text and the output-token count the provider
  reports, with the count at most `cap(m)`;
* `V : Σ* × Ω → {tt, ff}` decides, from the transcript of one retry attempt and
  a random draw, whether the attempt succeeded.

`Ω` is a probability space. Nothing else is assumed about `Π` and `V`: they
may depend on every character of the request. We write **𝒫** for the class of
all providers. (A provider with state — a prompt cache, rate limits — is a
function of the history of requests as well; every result below holds for it
unchanged, because the results establish that the histories are equal. §6.4.)

**Tapes and keys.** Randomness is supplied by a tape `ρ : K → Ω` whose entries
are independent and distributed as `Ω`. Each random event in an execution —
one call, or one retry decision — reads the tape at a *key*, computed by a
*keying scheme* from the execution so far. Three schemes are used:

| scheme | key of a call | key of a retry decision |
|---|---|---|
| global | the event's index in the execution | the event's index |
| model | `(m, how many calls to m so far)` | the index among retry decisions |
| request | `(m, q, how many earlier calls sent q to m)` | `(attempt transcript, occurrences)` |

A scheme is **fresh** if no two events of one execution read the same key. All
three are fresh.

**Lemma 1 (coupling validity).** Under a fresh keying scheme, for every
program and store, the transcript of an execution driven by a random tape has
the same distribution as when every random event draws independently from Ω.

*Proof.* The i-th event reads `ρ(k_i)` where `k_i` is a function of the
events before it, and `k_i ∉ {k_1, …, k_{i−1}}` by freshness. For an
independent family `ρ`, the draws `ρ(k_1), ρ(k_2), …` at adaptively chosen
distinct indices are independent and identically distributed: conditioned on
the first i−1 draws (which determine `k_i`), `ρ(k_i)` is an unread entry, hence
independent of them and distributed as Ω. The transcript is the same function
of the draw sequence in both processes. ∎

So a *coupling* of two executions — running both on the same tape — is a
proof device only: it never changes what a single execution does.

## 3. Semantics and observations

Big-step judgement `⟨c, σ, h⟩ ⇓_ρ ⟨σ', h'⟩`, where `h` is the history of events
so far. Events are `call(m, q, resp, o)` and `attempt(b)`.

* **call.** `q = eval(r, σ)` substitutes `σ` into `r`. Let `k` be the scheme's
  key for this event given `h`, and `(resp, o) = Π(m, q, ρ(k))`. Then
  `σ' = σ[x ↦ resp]` and `h' = h · call(m, q, resp, o)`.
* **if.** Run the arm selected by `π(σ(x))`.
* **retry n c.** Run `c`; let `b = V(T, ρ(k))` for the attempt's transcript
  `T` and its key `k`; append `attempt(b)`; stop if `b` or `n = 1`, otherwise
  run `retry (n−1) c`.
* `skip` and `;` as usual.

Given `ρ` the semantics is deterministic.

**Observers.** An observer is a function `O` of the history. The ones used:

| observer | sees |
|---|---|
| `trace` | the whole history, in order |
| `provider` | for each provider (the model name up to its first `/`), its own events in order |
| `bill` | for each model name: calls, Σ input tokens, Σ output tokens |
| `spend` | Σ price(m) × tokens |

Input tokens are `τ_m(q) + env(m)` for the model's tokenizer `τ_m` and envelope
`env(m)`, both arbitrary functions of `q`; output tokens are the reported `o`.
Each observer in the table is a function of the one above it, so security
against an observer implies security against every observer below it.

## 4. Security

For a secret assignment, write `v(σ_S)` for the vector of values of the secret
guard predicates (§5). Two stores are *related*, `σ1 ~ σ2`, when they agree on
all public inputs (including declassified values).

**Definition (O-noninterference).** A program `c` is *O-NI* if for all related
`σ1 ~ σ2` the distributions of `O(h1)` and `O(h2)` are equal, where `h_i` is the
history of `c` from `σ_i` with independent randomness.

**Definition (pointwise O-NI under a scheme).** For every tape `ρ`,
`O(h1(ρ)) = O(h2(ρ))`.

By Lemma 1, pointwise O-NI under any fresh scheme implies O-NI.

## 5. Request signatures

The analysis abstracts a command to a **signature**: a list of nodes

```
node   ::= Call(m, pieces)
         | Retry(n, sig)
         | Branch(guardterm, sig, sig)
piece  ::= text(t)          literal text, adjacent texts merged
         | var(b)           a binding b made outside the region, public content
         | res(p)           the response of the call at position p of the region
```

Positions are paths from the region's root (`3`, `3.0.1`, …). Model identities
are compared by identity, never by local name; bindings by declaration, never
by name.

The signature of a region is built by structural recursion. A call contributes
`Call(m, pieces)` where the pieces are the template text and, for each
argument, its literal text, `var(b)` for a binding outside the region, or
`res(p)` for the response bound at position `p` inside it. A retry contributes
`Retry`. A branch whose guard's *content* is public contributes `Branch`, with
its guard term built the same way. A branch whose guard reads secret content is
**resolved**: given an outcome vector `v` for the secret predicates, the
selected arm is inlined. `sig_v(c)` denotes the signature of `c` with every
secret guard resolved by `v`.

**Data labels and the program counter.** The type system tracks, for every
binding, a *data* label (what its content depends on) separately from the
program counter under which it was made. `E230` forbids an argument whose data
label is secret. A result computed inside a secret-guarded arm from public
arguments has a public data label and a secret program counter; it may reach a
prompt (open problem OP-1), and in the signature it is a `res(p)` piece. Secret
content never appears in a signature: the only bindings with secret data labels
are secrets and their endorsed copies, and `E230` keeps them out of requests.
Declassified copies of secrets are `var` pieces standing for themselves; the
guarantee is stated for secret assignments that agree on them, which is what
declassification means. Declassification is trusted, not checked.

**Secret predicates.** Because only secrets and their endorsed copies carry
secret content, every secret guard is a predicate of the secrets alone. For a
secret `s` with declared bound `B`, the predicates `tokens(s) ⋈ k` partition
`[0, B]` into intervals; the analysis enumerates the outcome vectors that some
value realises (evaluating each predicate at every value that could change an
outcome), and takes the product over independent secrets. This set, `F`, is
exactly the set of *feasible* outcome vectors.

### Lemma 2 (equal signatures, equal histories)

Let `c1, c2` be commands, `σ1, σ2` stores, and `v1, v2` outcome vectors with
`v_i = v(σ_i)`. Suppose `sig_{v1}(c1) = sig_{v2}(c2)`, and every `var(b)`
piece denotes a binding on which `σ1` and `σ2` agree. Then for every tape `ρ`
and history `h`, running `c1` from `(σ1, h)` and `c2` from `(σ2, h)` under any
scheme whose keys are functions of the history and the request (global, model,
request) produces the same history extension, and the bindings at
corresponding positions receive equal values.

*Proof.* By induction on the length of the (common) signature, and within it
on the nesting of nodes.

* *Call.* The pieces are equal. `text` pieces denote equal text; `var(b)`
  pieces denote equal values by hypothesis; `res(p)` pieces denote the responses
  at position `p`, equal by the induction hypothesis. So `eval` gives the same
  request text `q` in both executions, sent to the same model identity `m`. The
  histories so far are equal, so the scheme gives the same key `k`, hence the
  same draw, hence the same `(resp, o) = Π(m, q, ρ(k))`. Both histories are
  extended by the same event, and both bindings receive `resp`.
* *Retry.* The bounds are equal. Each attempt runs a body with equal signature
  from equal histories, so by induction produces equal transcripts; `V` reads
  the same transcript and the same draw, so both executions stop after the same
  attempt.
* *Branch.* The guard terms are equal and denote equal values (a `var` by
  hypothesis, a `res` by induction), so both executions take the same arm; its
  signatures are equal, and the induction hypothesis applies.
* *Resolved secret branch.* `sig_{v_i}` inlines the arm that `v_i` selects,
  and `v_i = v(σ_i)` is exactly the arm execution `i` takes. The inlined nodes
  are compared like any others. ∎

### Theorem 1 (request-trace noninterference)

Let `k(c) = |{ sig_v(c) : v ∈ F }|`. If `k(c) = 1` then `c` is pointwise
trace-NI under the global, model and request schemes, and therefore O-NI for
every provider in 𝒫, every tokenizer, every envelope and every observer that is
a function of the history.

*Proof.* Take `σ1 ~ σ2` and let `v_i = v(σ_i)`; both are feasible, so
`sig_{v1}(c) = sig_{v2}(c)`. In the global resolution the region is the whole
workflow, so every `var(b)` is a public input or a declassified value, on which
`σ1, σ2` agree. Lemma 2 with the empty history gives equal histories for every
tape. Lemma 1 turns this into equality of distributions. Every observer is a
function of the history. ∎

No tokenizer assumption is used: equal histories contain equal request texts,
and any tokenizer bills equal texts equally. That is the practical difference
from comparing sizes, which is only as good as a tokenizer assumption, and
§8 shows it is not even that good.

### Theorem 2 (leakage bound)

For every provider in 𝒫, fresh scheme, and observer `O` of the history —
together with the workflow's outputs and effects — the channel from the
secrets to `O` has min-capacity at most `log2 k(c)`. The bound holds for any
number of invocations with the same secrets and any public inputs, even chosen
adaptively from earlier observations.

*Proof.* Partition the secret assignments by the class of `sig_{v(σ_S)}(c)`;
there are at most `k(c)` classes. By Lemma 2, two assignments in one class
produce equal histories for every tape and every public input, because
signatures are symbolic and do not depend on the values of the public inputs.
Outputs and effects are functions of public data and responses, since the type
system rejects any output or effect under a secret program counter (`E231`,
`E234`) and any secret content reaching them (`E231`, `E232`). So an
invocation's observation is `G(class(σ_S), σ_P, ρ)`. For a sequence of
invocations with public inputs chosen by an adversary from earlier
observations and its own coins, induction on the number of invocations shows
the whole observation sequence is a function of `class(σ_S)`, the tapes and
the adversary's coins; the latter are independent of the secrets. The channel
from secrets to observations is therefore a cascade whose first stage is the
deterministic map to one of `k(c)` classes. The min-entropy leakage of a
cascade is at most that of its first stage [Espinoza & Smith 2011], and the
min-capacity of a deterministic channel with `k` outputs is `log2 k`
[Smith 2009]. Shannon capacity is bounded by min-capacity, so the same bound
holds for it. ∎

`k(c) = 1` recovers Theorem 1. The bound is independent of the provider's
noise, which is what separates it from counting observations directly (§9).

### Theorem 3 (coarser observers)

Define the *provider normal form* of a signature by stably sorting, by
provider, every maximal run of `Call` nodes none of which references another in
the run, outside any `Retry` body, and rewriting `res` references to follow the
moved calls; the *bill normal form* likewise sorts such runs by the full
request key. If the provider (bill) normal forms of `sig_v(c)` agree for all
feasible `v`, then `c` is pointwise provider-NI (bill-NI) under the request
scheme, and so provider-NI (bill-NI).

*Proof sketch.* Within a sorted run every request is determined by pieces
outside the run, so both executions send the same multiset of requests (bill)
or the same per-provider sequences (provider). Under the request scheme a
call's draw is keyed by `(m, q, occurrence)`, independent of its position in
the run; stable sorting keeps equal requests in execution order, so the
i-th copy of a request has the same occurrence index in both executions, and
receives the same response. Per-model sums are order-independent; each
provider's own sequence is preserved by the stable sort. References are
rewritten to the same copies. Control nodes are compared exactly and sit
between runs, so the induction of Lemma 2 continues past them.

Retry bodies are *not* reordered. `V` sees the attempt's transcript in order,
and a validator may depend on order, so reordering inside a body can change
how many attempts are made. An earlier version of this analysis reordered there
and was unsound; `tests/tests.cpp` keeps the counterexample. ∎

**Separating examples.** `if s {m1(x); m2(x)} else {m2(x); m1(x)}` with `m1`,
`m2` at different providers is provider-NI but not trace-NI; with both at one
provider it is bill-NI but not provider-NI. All three are in the test suite and
the benchmark.

## 6. Completeness, and what is excluded

### Theorem 4 (relative completeness)

Suppose `sig_{v1}(c) ≠ sig_{v2}(c)` for feasible `v1, v2`, and that every
public guard on the path to their first difference can be made to go either
way by some choice of public inputs and responses. Then there are public
inputs, secrets realising `v1` and `v2`, and a provider in 𝒫 under which the
trace distributions differ. The same holds for `k` classes at once, so the
bound of Theorem 2 is attained: `log2 k(c)` bits are leaked to some observer
under some provider and prior.

*Proof sketch.* Choose public inputs that are pairwise distinct fresh strings
over a character absent from the program, and a provider whose responses are
fresh strings encoding the request and the draw, and whose validator always
fails. Then the rendering from signatures to histories is injective: distinct
piece sequences give distinct request texts, distinct retry bounds give
distinct attempt counts, a call present in one signature and not the other
changes the history's length. At the first difference the histories differ;
before it they agree by Lemma 2. The feasibility hypothesis supplies the public
guard outcomes needed to reach it. For `k` classes, this provider makes the
observation an injective function of the class, i.e. a deterministic channel
with `k` distinct outputs, whose min-capacity is `log2 k`. ∎

So a rejection is justified relative to 𝒫 except when the difference sits under
a public guard that can never go the relevant way — dead code. Open problem
OP-6, "different variables of equal length are rejected", disappears under
this reading: two different public variables can hold different text, and some
provider answers them differently, so the rejection is required, not
incomplete.

### 6.4 What the guarantee excludes

The coupling is a proof device (Lemma 1), so the guarantee is about
distributions under independent sampling per call. It excludes:

* providers whose randomness is correlated with the secret by a channel
  outside the program (for instance, a provider that sees the secret
  elsewhere);
* timing, which is not in the history;
* observers who see more than the history — a network observer of packet
  sizes of the *responses* sees a function of the history, and is covered; one
  who sees the provider's internal activations is not;
* declassified values, which are trusted.

Stateful providers are included: if the state is a function of the history of
requests (a prompt cache, a rate limiter), equal histories give equal states,
and across invocations the state is a function of earlier invocations'
histories, which are themselves secret-independent (Theorem 1) or
class-determined (Theorem 2).

## 7. The unary bound

A tokenizer `τ` satisfies the contract `(κ, σ)` if `τ(s) ≤ κ·bytes(s) + σ`
for every string `s`; `λ` bounds the bytes one generated token decodes to,
after lossy UTF-8 decoding.

### Theorem 5 (guaranteed bound)

Assume each provider reports at most `cap(m)` output tokens; each model's
tokenizer satisfies its declared contract; each envelope adds at most the
declared overhead; each input's value satisfies its declared byte bound; and
responses are decoded losslessly or with U+FFFD replacement. Then for every
execution, output tokens ≤ `G`, input tokens ≤ `I`, and their sum ≤ `T`, where
`G`, `I`, `T` are the certificate's `output_tokens`,
`input_tokens_guaranteed` and `total_tokens_guaranteed`.

*Proof.* By induction on the command, with `G`, `I`, `T` combined by sum for
`;`, componentwise maximum for `if` (for `T`, the maximum of the arms' totals),
and multiplication by `n` for `retry n` (a body runs at most `n` times). For a
call: the output count is at most `cap(m)` by assumption. The billed input is
`τ_m(q) + env ≤ κ·bytes(q) + σ + overhead`. `bytes` is additive under
concatenation, so `bytes(q)` is the template's bytes plus the sum of the
arguments' bytes. An argument is a literal (its bytes are known), an input
(bounded by its declaration, or by `λ_T · N` for `N` tokens under a lossless
tokenizer `T`), or a response of a model with tokenizer `T'`: a response of
`o ≤ cap` tokens decodes to at most `λ_{T'} · o` bytes, because lossy UTF-8
decoding is subadditive in output length (checked exhaustively on all byte
strings of length ≤ 3 over every byte class, and on 300,000 random pairs), or
to at most the client byte cap if one is declared. Saturating arithmetic only
rounds up; a saturated bound is rejected (`E266`). ∎

**What makes the bound sound, and what does not.** Byte lengths are additive
and tokenizer-independent; token counts are neither. The following were
measured on 14 real tokenizers (`bench/results/tokenizers.json`) and are why
the bound is built from bytes:

1. Tokenization is not subadditive: `tokens(u·v)` exceeds `tokens(u) +
   tokens(v)` by up to 4–6 in every tokenizer measured (`" Attribute"` and
   `"profiles"` are one cl100k token each; `" Attributeprofiles"` is six).
2. A response re-encodes to more tokens than were generated, under the same
   tokenizer: up to 3–9 tokens per generated token.
3. `tokens ≤ bytes` fails for SentencePiece tokenizers (a dummy prefix no byte
   pays for), for NFC normalisation (Qwen2.5: U+0FAC is 3 bytes and 6 tokens),
   and badly for NFKC-like normalisation (T5: 194 more tokens than bytes on one
   string). The contracts in `src/tokenizer_contracts.cpp` account for the
   first two structurally; for the third no structural contract exists and
   the compiler refuses to certify through it.

The *estimated* component (`input_tokens_estimated`, bytes/4 per part) is an
estimate, not a bound: it is exceeded on 67–99.8% of 256-character multilingual
windows, depending on the tokenizer.

## 8. Size-blindness: why comparing sizes cannot work

A **size measure** is any function `μ : Σ* → ℕ` (bytes/4, characters, tokens
under some tokenizer). A relational analysis `A` (a predicate on programs,
"accepted") is **μ-indexed** if `A(c) = A(c')` whenever `c'` is `c` with one
text constant `t` replaced by `t'` with `μ(t') = μ(t)`. Both withdrawn rules
are μ-indexed: the equal-bounds rule compared upper bounds computed from sizes,
and the billing-signature rule compared symbolic sizes.

Say `μ` has **fresh twins** if for every string `t` with `μ(t) > 0` and every
finite set of strings `W`, some `t' ≠ t` with `μ(t') = μ(t)` occurs in no
member of `W`, and no member of `W` occurs in `t'`. Every size measure used in
practice has fresh twins (strings of a given size can be built from characters
the program never uses).

### Theorem 6 (sound size-indexed analyses reject identical arms)

Let `μ` have fresh twins and let `A` be μ-indexed and sound for 𝒫 (every
accepted program is bill-NI for every provider in 𝒫). Let `c` contain a
secret-guarded branch, both of whose outcomes are feasible, whose then-arm
unconditionally makes a call to a model with `cap > 0` whose request contains
a text constant `t` with `μ(t) > 0`. Then `A(c)` is false — even if the two
arms are identical.

*Proof.* Let `W` be the text constants of `c` and choose a fresh twin `t'` of
`t`. Let `c'` be `c` with that occurrence of `t` replaced by `t'` in the
then-arm only. `A(c') = A(c)` because `A` is μ-indexed. Let `Π*` answer
`(ε, cap(m))` to any request containing `t'` and `(ε, 0)` otherwise, with a
validator that always succeeds. Take public inputs equal to the empty string.
Every request of `c'` is a concatenation of text constants from `W ∪ {t'}` and
empty strings, so a request contains `t'` exactly when it comes from the
modified call. Executions of `c'` whose secret takes the then-arm report
`cap(m) > 0` output tokens for `m` from that call; executions taking the
else-arm report 0 for every call containing no `t'`, and in the else arm no
request contains `t'`. The difference in `m`'s output tokens differs between
the two secrets, so `c'` is not bill-NI under `Π* ∈ 𝒫`. If `A(c)` held, `A(c')`
would, contradicting soundness. ∎

The theorem is the formal content of the audit's counterexample and of this
project's own second mistake. It says more than "this rule is wrong": *no*
analysis that compares only sizes can be sound for content-dependent providers
without rejecting a program as harmless as `if s { p(x) } else { p(x) }` with a
non-empty template.

### Corollary (the classical instantiation)

Resource-aware noninterference [Ngo et al. 2017, Definition 2] and constant
resource [Definition 1] quantify over *size-equivalent* environments: cost must
be a function of sizes. Their type systems attach potential to data by size and
charge each operation a constant `tick`. Instantiating them with an LLM call —
charging a call a function of the sizes of its template and arguments, and its
output as either a constant or an unknown in `[0, cap]` — gives an analysis
whose verdict depends on text constants only through their sizes, i.e. a
μ-indexed one. By Theorem 6 it is unsound for content-dependent providers or
rejects every secret branch that calls a model with a non-empty prompt. The
alternative, treating the call's cost as data that depends on the request
content and hence as secret inside a secret branch, makes every call in a
secret branch a secret-dependent cost, and constant-resource typing then
rejects the branch outright; that is Proposition 7.

Their *quantitative* bound fails differently. Lemma 6–7 of Ngo et al. bound
leakage by `log2(u − l + 1)` for upper and lower cost bounds `u, l`. An LLM call
may return anywhere from 0 to `cap` tokens, so `u − l ≥ cap` for any workflow
with a call, whether or not it has a secret: the bound is at least
`log2(cap + 1)` bits for a program that provably leaks nothing.
`bench/evaluate.py` (E7) computes it for every workflow the content rule proves
leak-free.

### Proposition 7 (the program-counter discipline)

If calls are treated as low-observable events and typed with the standard
program-counter rule [Volpano, Smith, Irvine 1996], every secret-guarded branch
containing a call is rejected. If calls are treated as unobservable, the
billing channel is not detected at all (the audit's starting point).

So the four options are: calls invisible (unsound), calls as low events
(rejects every call in a secret branch), sizes compared (unsound, or rejects
identical arms, Theorem 6), requests compared (sound for all providers and
tokenizers, Theorem 1, and complete relative to public-guard feasibility,
Theorem 4).

## 9. Relation to the literature, in formal terms

* **pRHL and couplings** [Barthe et al. 2009, 2017]. Lemma 2 is a pRHL
  derivation in which every provider call is related by the identity coupling
  on the draw. pRHL's `[rnd]` rule requires the two samplings to be from the
  same distribution. Requests with equal content satisfy that; requests with
  equal size do not, because `D(q1) ≠ D(q2)` in general. The size rule, read
  as a pRHL derivation, applies `[rnd]` to two different distributions.
* **Cross-copying and PC-security** [Agat 2000; Molnar et al. 2005]. Accepting
  a secret branch whose arms perform the same observable operations is the
  constant-time idea; here the observable operation is a request, and
  "the same" must mean the same content.
* **Counting observations** [Köpf & Basin 2007; Doychev et al. 2013 (CacheAudit)].
  Bounding leakage by the number of possible observations is standard. For an
  LLM workflow the number of possible observations is enormous for any program,
  because of the provider's noise; Theorem 2 counts *signature classes*, the
  observations modulo the coupling, which is what makes the bound small and
  independent of the provider.

## 10. What is mechanised

See `proofs/README.md` for the Coq development, which mechanises Lemma 2 and
Theorem 1 for the core calculus of §1 over an abstract provider, keying
scheme and observer, and the unary bound of Theorem 5 for the output component.
Theorems 2, 3, 4 and 6 are pen-and-paper.
