# Compare the Requests, Not Their Sizes: Resource Side Channels and Sound Token Bounds for LLM Workflows

**Nambi Rajan M** (24BAI0072)
Vellore Institute of Technology

---

## Abstract

A program that orchestrates calls to a large language model (LLM) can leak a
secret without the secret reaching a prompt: if the secret decides which requests
are sent, whoever sees the traffic or the bill can learn it. Resource-aware
noninterference handles such channels by charging each operation a cost
determined by its inputs' sizes. We show that this cannot work for LLM calls: any
analysis that sees prompt text only through a size measure is either
unsound for providers whose answers depend on content, or rejects a secret branch
whose two arms are identical. The theorem is mechanised in Coq and explains two
size-based rules we previously built, whose failures we measure with real
tokenizers and a real model. We instead compare requests by content, resolving
each secret branch by the outcomes its secret can realise. If every resolution
sends the same requests, the workflow is noninterfering for every provider,
tokenizer and observer of its transcript; if k request classes remain, it leaks at
most log2 k bits of min-capacity. Because tokenization is not subadditive, we
compute worst-case token bounds in bytes, converted through tokenizer contracts
measured on fourteen tokenizers. Both analyses are implemented in OrchLang, a
small workflow language, and evaluated on synthetic suites and on thirty
workflows ported from LangGraph, the Anthropic cookbook and AgentDojo under a
protocol fixed before porting. No certified bound was exceeded. No ported workflow
has a secret, so the relational analysis is so far exercised only on synthetic
workflows.

**Keywords:** information flow; resource side channels; relational analysis;
quantitative information flow; tokenization; LLM workflows; Coq

**Highlights**

- Any size-based side-channel analysis of LLM calls is unsound or trivial (Coq)
- Comparing requests by content gives provider-independent noninterference
- Leakage is bounded by log2 of the number of request classes (min-capacity)
- Sound token bounds are built from bytes: tokenization is not subadditive
- Thirty real workflows ported under a fixed protocol; no bound was exceeded

---

## 1. Introduction

Consider a support workflow that answers a ticket with a small model, but sends
it to a larger model for review when the customer's account carries a private
fraud-risk flag:

```orchlang
secret high_risk: boolean;
input ticket: text max_bytes 4096;
if high_risk {
  let reply: text = call review(ticket) using large;
} else {
  let reply: text = call answer(ticket) using small;
}
```

The flag never reaches a prompt, an output or a tool. An information-flow type
system with a program-counter label has nothing to object to, since nothing
observable at a sink depends on the flag. But the requests do. The provider
bills per model, so a tenant's invoice shows which model ran; a network observer
of the encrypted traffic sees request and response sizes, from which
token-length and packet-size attacks recover prompt topics and response text
[Weiss et al. 2024; McDonald and Bar Or 2025]; a provider-side prompt cache
shared across users turns the requests into a timing channel [Gu et al. 2025].
Each of these observers sees a function of the workflow's requests and
responses. If the secret changes the requests, it can change what they see.

### 1.1 Why the classical answer does not transfer

This is a resource side channel, and the classical treatment is mature. Ngo,
Dehesa-Azuara, Fredrikson and Hoffmann define *resource-aware noninterference*
and *constant resource*, and certify both by combining information-flow typing
with automatic amortised resource analysis (AARA) [Ngo et al. 2017]. Çiçek,
Barthe, Gaboardi, Garg and Hoffmann's RelCost bounds the *difference* in cost
between two executions with relational refinement types [Çiçek et al. 2017].
Ngo et al. quantify over environments that agree on the *sizes* of secret data;
RelCost bounds cost differences in terms of sizes and of how much two inputs
differ. Both charge each operation a cost the program's data determines.

An LLM call's cost is not determined by sizes. Two requests of exactly the same
token length can receive answers of different lengths, because the model answers
what it is asked: a real instruction-tuned model, run on fifteen pairs of chat
requests padded to identical token counts, gave different output lengths for
all fifteen pairs under a shared sampling seed (§9, E10). Two strings of the same
length are billed differently by real tokenizers in 84–92% of random pairs (E9).
So one might hope to repair the classical analysis by using a finer size
measure. §4 shows that no size measure works. **Any analysis that sees prompt
text only through a size measure is either unsound for some content-dependent
provider, or rejects a secret-guarded branch whose two arms are identical**
(Theorem 6, mechanised in Coq). Instantiating Ngo et al. with a call charged by
its sizes gives such an analysis. RelCost can do better, because it can also say
that two runs with *identical* inputs cost the same; charging a call a zero
difference exactly when its two requests are identical is sound, and it is, in
essence, the comparison of §5. Ngo et al.'s quantitative bound fails
differently: it counts the possible values of a cost interval, and an LLM call
can return anywhere from zero to its cap, so the bound is at least
`log2(cap + 1)` bits for any workflow that calls a model, including one that
provably leaks nothing (6.0–9.4 bits on our leak-free workflows, E7).

This paper is, in part, a record of learning that lesson twice. The first
version of our compiler accepted a secret branch when its arms had equal
certified cost *bounds*; an external audit showed that equal maxima do not make
equal bills. The repair compared symbolic *sizes* of requests; our own audit
showed that equal sizes do not make equal bills either (§4.1). Theorem 6 says why
every such repair fails.

### 1.2 What this paper contributes

1. **A size-blindness theorem** (§4). Any analysis whose verdict depends on the
   text of a program only through a size measure is unsound for
   content-dependent providers or rejects identical arms, even when soundness is
   required only for deterministic providers and only for the total output
   count. The theorem, mechanised in Coq, explains both of our withdrawn rules
   and the classical instantiation; mechanising it also exposed a gap in our
   own pen-and-paper proof.

2. **Content-level request signatures** (§5). A branch guarded by secret content
   is resolved by every outcome vector the secret can realise, and the resulting
   request signatures are compared by content: model identity, text as sent,
   bindings by identity, earlier responses by position. If all resolutions
   agree, the workflow is noninterfering for every provider, tokenizer and
   observer of its transcript (Theorem 1, mechanised); if `k` classes remain, the
   channel from secrets to any such observer has min-capacity at most `log2 k`,
   across any number of adaptively chosen invocations (Theorem 2). Coarser
   observers (per provider, per bill) admit reordering of independent calls,
   except inside retry bodies (Theorem 3). A rejection is justified up to dead
   code (Theorem 4).

3. **Token bounds that hold for real tokenizers** (§6). Measured on fourteen
   tokenizers, token counts are not subadditive (`tokens(u·v)` exceeds
   `tokens(u) + tokens(v)` by as much as 3 to 6, depending on the tokenizer), a response re-encodes to up to nine
   tokens per generated token, and six tokenizers emit more tokens than bytes on
   some input. We build the guaranteed input bound from bytes, which add up, and
   convert once per request through per-tokenizer contracts
   `tokens ≤ κ·bytes + σ` generated from the measurements; the bound is proved
   (Theorem 5, mechanised) relative to those contracts.

4. **An evaluation designed to be able to fail** (§9), including a corpus of
   real workflows: 52 candidates from three pinned sources, 30 ported and 22
   excluded with reasons, labelled from the sources before porting, with a
   development split and a held-out split checked once against a frozen
   compiler.

We also report what went wrong, because each error was of the same kind as the
thing the paper is about: the two withdrawn rules, a harness that shared the
withdrawn rules' blind spot (§8), a reordering optimisation that was unsound
inside retry bodies (§5.4), and the proof gap (§7).

### 1.3 What we do not claim

Combining information flow with resource analysis is not new [Ngo et al. 2017];
nor is relational cost analysis [Çiçek et al. 2017]; nor is leakage through LLM
token counts, sizes and timing [Weiss et al. 2024; Zhang et al. 2024; McDonald
and Bar Or 2025; Gu et al. 2025]. The flow half of OrchLang is conventional
two-point confidentiality and integrity typing; for agents, CaMeL and FIDES
enforce richer flow policies at run time [Debenedetti et al. 2025; Costa et al.
2025]. Accepting a secret branch whose arms perform the same observable
operations is the constant-time discipline [Agat 2000; Molnar et al. 2005];
what we add is the proof that for LLM calls "the same operation" must mean the
same *request content*, and an analysis built on that. The leakage bound is an
application of min-capacity [Smith 2009] to the right partition. On the corpus
of real workflows, the relational analysis never fires, because none of them
has a secret in its source's threat model (§9.6): its practical relevance is
argued from the threat model, not demonstrated on deployed workflows.

---

## 2. Setting

### 2.1 Workflows, providers and observers

A workflow sends requests to models and branches on data. We model a provider as
a pair `(Π, V)`. `Π(m, q, ω)` returns, for model identity `m`, request text `q`
and a random draw `ω`, a response text and the number of output tokens the
provider reports, at most `m`'s cap. `V(T, ω)` decides from the transcript `T` of
one retry attempt whether it succeeded. **Nothing else is assumed**: both may
depend on every character of the request. We write 𝒫 for the class of all
providers. A provider with state, such as a prompt cache or a rate limiter,
is covered as long as its state is a function of the requests it has seen.

Randomness is a tape `ρ` of independent draws indexed by keys, and each call or
retry decision reads the tape at a key computed from the execution so far: by
position (global scheme), by model and occurrence (model scheme), or by request
content and occurrence (request scheme). Each scheme is *fresh*: no key is read
twice in one execution. Under a fresh scheme a tape-driven execution has the
same distribution as one that samples every event independently (Lemma 1 of
`docs/FORMAL_MODEL.md`), so running two executions on one tape is a proof device
(a coupling) that never changes what a single execution does.

An **observer** is a function of the execution's history, the sequence of
`call(m, q, response, output tokens)` and `attempt(success)` events. We use four,
each a function of the one before:

| Observer | Sees |
|---|---|
| `trace` | every event, in order |
| `provider` | each provider's own events, in order |
| `bill` | per model: number of calls, total input tokens, total output tokens |
| `spend` | the sum of price × tokens |

Input tokens are `τ_m(q) + env_m(q)` for the model's tokenizer `τ_m` and
envelope `env_m`, both arbitrary. A network observer who sees encrypted
request and response sizes sees a function of the trace.

A workflow is **O-noninterfering** if any two executions whose secrets differ
but whose public inputs agree give `O` the same distribution; it leaks at most
`b` bits to `O` if the channel from secrets to `O`'s view has min-capacity at
most `b` [Smith 2009].

### 2.2 What the guarantee excludes

Timing is not in the history, so it is not covered, except insofar as it is a
function of the history (a cache keyed by requests). Providers whose randomness
is correlated with the secret through a channel outside the program are
excluded. Declassification and endorsement are trusted. Declassification is all
or nothing: a value declassified so that one provider may see it is public to
every observer, which is coarser than the setting deserves when the provider is
trusted with content but the network is not (§12).

---

## 3. OrchLang

OrchLang is a small, statically typed language for LLM workflows, compiled by a
C++17 compiler (`orchc`) that makes no network requests. A workflow declares
inputs, secrets, models, prompt templates and tools, then calls models,
branches, retries, emits tool calls and returns one output:

```orchlang
workflow Triage budget 1000000 {
  input ticket: text untrusted max_bytes 4096;
  secret high_risk: boolean;
  model small = mock("openai/gpt-4o-mini") max_tokens 300 tokenizer o200k_base overhead 9;
  model large = mock("openai/gpt-4o") max_tokens 900 tokenizer o200k_base overhead 9;
  prompt answer(t: text) -> text = "Answer this support ticket: {t}";
  let reply: text = call answer(ticket) using small;
  if high_risk {
    let review: text = call answer(reply) using large;
  }
  output reply;
}
```

Three commitments make the analyses decidable. Repetition is `retry n` with a
literal `n`, and the only branch reads a declared value, so the shape of a
workflow is fixed before it runs. Lengths the compiler cannot see are declared
in a stated unit: bytes (`max_bytes`), tokens of a named tokenizer
(`max_tokens N tokenizer T`), or, for an estimate only, tokens. Leaving the
security lattice requires a written justification (`declassify`, `endorse`).
Every declaration has a unique binding identity, and all analyses refer to
bindings, models and prompts by identity; inputs and secrets are declared only
at the top level.

**Labels.** Values carry a label in `{Public ≤ Secret} × {Trusted ≤ Untrusted}`,
and a model's answer carries the join of everything in its request, so
untrusted text stays untrusted through any number of calls. Each value also
carries a *data label*, recording what its content depends on, separately from
the program counter under which it was computed. A secret may not reach a prompt
by content (`E230`), but a value computed from public data inside a secret arm
may, because only its existence depends on the secret, and existence is what the
relational analysis accounts for (§5.6). Outputs and effects are checked against
the program counter as well. The full rules are in `docs/LANGUAGE_SPEC.md`.

In the example, `review` exists only when `high_risk` holds, so the trace and the
bill reveal `high_risk`: the compiler rejects the workflow (`E236`) unless it
declares a leakage budget of at least one bit (`leaks 1`), in which case it is
accepted with a warning and the certificate records one bit.

---

## 4. Why comparing sizes cannot work

### 4.1 Two rules that failed

**Equal bounds.** The first rule accepted a secret branch when its arms had equal
certified worst-case costs. An upper bound constrains a maximum, and two
quantities with the same maximum need not be equal. The external audit's
counterexample, `if tokens(s) == 0 { call p(x) } else { call p(y) }` with `x` and
`y` both declared at most 100 tokens, has equal bounds (111 tokens) in both arms
and different bills whenever `x` and `y` differ in length; it billed differently
in 225 of 425 paired runs. It is still rejected and still leaks under the
runtime (E0).

**Equal sizes.** The repair abstracted each arm to a sequence of
`Call(model, size)` nodes, with sizes symbolic in the lengths of variables, and
accepted equal sequences. It was unsound for three independent reasons, each
with a counterexample in `audit/2026-09-25/` that the rule accepts and the
runtime shows leaking:

* **Tokenizers.** Sizes were estimated tokens (`bytes/4`). Real tokenizers bill
  equal-size strings differently: `"aaaa"` and `"bbbb"` are one and two tokens
  under `r50k_base`, and 84–92% of random equal-length string pairs differ under
  the fourteen tokenizers we measured (E9). Re-billing the requests of the rule's four
  accepted counterexamples with `r50k_base`, `cl100k_base` and `o200k_base`,
  with the provider held fixed, shows the bill moving with the secret for three
  of them (E6).
* **Providers.** Even an exact token count does not help: the provider answers
  content, not size (E10: 15 of 15 equal-token-length pairs answered at
  different lengths, mean difference 34 tokens).
* **Names.** Signatures named models and prompts by local name, so a
  redeclaration inside one arm was invisible (`shadowed_model`,
  `shadowed_prompt`).

On the relational suite, the size rule accepts 12 workflows of which 4 leak, and
the bounds rule 15 of which 6 leak (E5).

### 4.2 The theorem

A **size measure** is any function `μ : Σ* → ℕ`: bytes, characters, `bytes/4`,
tokens under some tokenizer. An analysis `A`, a predicate on programs, is
**μ-indexed** if it cannot distinguish two programs of the same shape whose text
constants have pairwise equal sizes. The measure has **fresh twins** if for every
string `t` with `μ(t) > 0` and every finite set `W` of strings, some `t'` with
`μ(t') = μ(t)` contains a character occurring in no member of `W`. Every measure
used in practice has fresh twins.

**Theorem 6 (size-blindness).** Let `μ` have fresh twins and `A` be μ-indexed and
sound, in the weakest sense: every accepted program gives the same *total
output-token count* from any two stores that agree on public variables, for
every *deterministic* provider that respects the caps. Let `c` be a well-typed
program with a secret-guarded branch, both outcomes feasible, whose then-arm
unconditionally calls a model with a positive cap on a request containing a
text constant `t` with `μ(t) > 0`. Then `A` rejects `c`, whatever the else-arm
is, including a copy of the then-arm.

*Proof.* Take a fresh twin `t'` of `t` containing a character `★` absent from
every text constant of `c`, and let `c'` be `c` with `t` replaced by `t'` in that
call. `A` cannot tell `c'` from `c`. Let the provider answer the empty string,
reporting the full cap when the request contains `★` and zero otherwise, and let
public inputs be empty. Every request of `c'` is a concatenation of `c`'s
constants, `t'` and empty strings (secrets never reach a request), so it contains
`★` exactly when it is the modified call. The then-arm execution reports at least
the cap; the else-arm execution reports zero. So `c'` is not sound for this
provider, and since `A` accepts `c'` if and only if it accepts `c`, `A` must
reject `c`. ∎

The theorem is mechanised (`size_blind` in `proofs/OrchLang.v`, §7). It is the
formal content of both withdrawn rules: each compared something coarser than
what determines the observation, a maximum in one case and a size in the other.

### 4.3 The classical instantiation

Ngo et al.'s resource-aware noninterference [Ngo et al. 2017, Definition 2] and
constant resource [Definition 1] quantify over environments that are
*size-equivalent* on secret data, and their type system charges operations by
potential attached to sizes. Instantiating it with an LLM call, charging the call
a function of the sizes of its template and arguments and its output as a
constant or an unknown in `[0, cap]`, gives an analysis whose verdict depends on
text constants only through their sizes: a μ-indexed analysis. By Theorem 6 it is
unsound for content-dependent providers or rejects every secret branch that calls
a model with a non-empty prompt.

RelCost is not confined to sizes [Çiçek et al. 2017]. Its relational refinements
also track how much the two runs' inputs differ (for lists, the number of
positions at which they differ), so it can state that a call on identical inputs
has a zero cost difference, and a call on different inputs a difference of at
most its cap. Under the coupling of §2.1 that instantiation is sound, and it
compares requests by content: it is, in essence, §5's rule for the trace
observer. What RelCost does not supply, and what §5 adds, is the resolution of a
secret branch by the outcome vectors the secret can realise (RelCost relates two
fixed runs), coarser observers, a leakage bound in bits, and an account of why
comparing sizes cannot work. To our knowledge it has not been applied to this
setting. Treating the call's cost instead as secret data
inside a secret branch makes every such call a secret-dependent cost, and the
constant-resource discipline then rejects the branch outright; so does the
program-counter discipline if calls are low-observable events [Volpano et al.
1996]; and if calls are unobservable, the channel is not detected at all.

Their quantitative bound fails differently. Ngo et al. bound the Shannon entropy of a
program's resource observations, for uniformly sampled environments, by
`log2(u − l + 1)` for upper and lower cost bounds `u` and `l` [Lemmas 6–7]. For a workflow with a call, `u − l ≥ cap` whether or not a secret
exists, so the bound is at least `log2(cap + 1)` bits for a workflow that
provably leaks nothing: 6.0 to 9.4 bits on the eleven such workflows of our
leakage suite, where our bound is 0 (E7).

---

## 5. Comparing requests

### 5.1 Request signatures and resolution

The analysis abstracts a region of a workflow to a **signature**, a list of nodes

```
node   ::= Call(m, pieces) | Retry(n, sig) | Branch(guard, sig, sig)
piece  ::= text(t) | var(b) | res(p)
```

where `m` is a model identity (provider, model name, cap, byte cap), `text(t)` is
static text as sent (template text and literal arguments, adjacent text merged),
`var(b)` a binding made outside the region with public content, identified by
declaration, and `res(p)` the response of the call at position `p` of the region.
A branch whose guard's content is public contributes a `Branch` node.

A branch whose guard reads secret content is **resolved**. Because only secrets
and their endorsed copies carry secret content, and `E230` keeps both out of
requests, every secret guard is a predicate of the secrets alone. For a secret
with a declared bound `B`, the predicates `tokens(s) ⋈ k` partition `[0, B]`
into intervals; the analysis enumerates the outcome vectors that some value
realises and takes the product over independent secrets. This set `F` is exactly
the set of feasible outcome vectors. For each `v ∈ F`, `sig_v(c)` inlines the arm
`v` selects at every secret branch. Let `k(c) = |{sig_v(c) : v ∈ F}|`.

### 5.2 Noninterference

**Lemma 2 (equal signatures, equal histories).** If `sig_{v1}(c1) = sig_{v2}(c2)`,
`vi` is the outcome vector of store `σi`, and `σ1, σ2` agree on every `var`
piece, then on every tape and from every common history, `c1` from `σ1` and `c2`
from `σ2` produce the same history extension under any keying scheme that is a
function of the history and the request, and bind equal values at corresponding
positions.

*Proof sketch.* By induction on the signature. At a call, equal pieces denote
equal text (`var` by hypothesis, `res` by induction), so the same request goes to
the same model identity from the same history; the scheme reads the same key,
the same draw, and the provider returns the same response. At a retry, equal
bodies produce equal attempt transcripts, and `V` reads the same transcript and
draw, so both stop after the same attempt. A public branch reads equal values;
a resolved branch inlines the arm the store actually takes. ∎

**Theorem 1 (request-trace noninterference).** If `k(c) = 1`, then `c` is pointwise
trace-noninterfering under the global, model and request schemes, and hence
O-noninterfering for every provider in 𝒫, every tokenizer, every envelope, and
every observer that is a function of the history.

No tokenizer assumption is used: equal histories contain equal request texts,
and any tokenizer bills equal texts equally. That is the practical difference
from comparing sizes. Lemma 2 and Theorem 1 are mechanised (§7), for an abstract
provider, validator, keying scheme and observer.

In pRHL terms [Barthe et al. 2009], Lemma 2 is a derivation in which every
provider call is related by the identity coupling on its draw; the `[rnd]` rule
that justifies this requires the two samplings to come from the same
distribution, which requests with equal content satisfy and requests with equal
size do not. The size rule, read as a pRHL derivation, applies `[rnd]` to two
different distributions.

### 5.3 Quantitative leakage

Rejecting every workflow with `k(c) > 1` is too strict for workflows that must
reveal a little, such as the one-bit tier routing of §3. A workflow may declare
a budget `leaks b`.

**Theorem 2 (leakage bound).** For every provider in 𝒫, fresh scheme and observer
of the history, together with the workflow's outputs and effects, the channel
from the secrets to the observer has min-capacity at most `log2 k(c)`, for any
number of invocations with the same secrets and public inputs chosen
adaptively.

*Proof sketch.* Partition secret assignments by the class of their signature.
By Lemma 2, two assignments in one class produce equal histories on every tape
and for every public input, since signatures are symbolic in the public inputs.
Outputs and effects are functions of public data and responses (the type system
rejects outputs and effects under a secret program counter), so each
invocation's observation is a function of the class, the public inputs and the
tape. Over adaptively chosen invocations, the whole observation sequence is a
function of the class, the tapes and the adversary's coins. The channel is a
cascade whose first stage is a deterministic map onto at most `k(c)` classes;
the min-entropy leakage of a cascade is at most that of its first stage
[Espinoza and Smith 2011], and a deterministic channel with `k` outputs has
min-capacity `log2 k` [Smith 2009]. ∎

This is the counting argument of Köpf and Basin [2007], applied to signature
classes rather than to observations. Counting observations directly would be
useless here: the provider's noise gives every workflow with a call an enormous
number of possible observations, which is exactly why the interval bound of §4.3
is vacuous. The coupling removes the noise from the count.

### 5.4 Coarser observers, and a bug

A bill does not record order, and a provider sees only its own requests. Define
the **provider normal form** of a signature by stably sorting, by provider, every
maximal run of calls none of which references another, and the **bill normal
form** likewise by full request key, rewriting `res` references to follow the
moved calls.

**Theorem 3.** If the provider (bill) normal forms of `sig_v(c)` agree for all
feasible `v`, then `c` is provider- (bill-) noninterfering under the request
scheme.

Under the request scheme a call's draw is keyed by its request and occurrence,
not its position, so a stably sorted run sends the same multiset of requests
and each copy of a request receives the same response. Calls inside a retry body
are *not* reordered: the validator sees an attempt's transcript in order, and a
validator may depend on order. An intermediate version of our analysis did
reorder there; `audit/2026-09-25/retry_reorder.orch` was accepted and the
runtime showed one attempt against three under the same seed. It is now a
regression test.

### 5.5 Completeness relative to dead code

**Theorem 4.** If `sig_{v1}(c) ≠ sig_{v2}(c)` for feasible `v1, v2`, and every public
guard on the path to the first difference can go either way for some public
inputs and responses, then some provider in 𝒫 distinguishes the two secrets;
for `k` classes, some provider and prior attain the `log2 k` bound.

*Proof sketch.* Choose public inputs that are distinct fresh strings and a
provider whose responses are fresh strings encoding the request and draw, with
a validator that always fails. Rendering signatures to histories is then
injective, and the histories agree up to the first difference by Lemma 2. ∎

So a rejection is justified except when the difference sits under a public
guard that can never go the relevant way. An open problem of the earlier design,
"two different public variables of equal length are rejected", disappears: two
different variables can hold different text, and some provider answers them
differently, so the rejection is required.

### 5.6 Data labels and the program counter

A program-counter discipline labels every value computed in a secret arm secret.
Applied to prompts, it rejects every chain of two calls inside a secret arm,
since the second call's argument is the first call's response. But the content
of that response depends only on public data; only its existence depends on the
secret, and existence is exactly what Theorem 1 accounts for. OrchLang therefore
checks prompts against the *data* label (§3), while outputs and effects, whose
occurrence is observable outside the request trace, remain checked against the
program counter. Thirteen adversarial attempts to exploit the relaxation are
regression tests: a chain whose length, input, prior result or model depends on
the secret; a value computed in a secret arm emitted, returned, used outside
its arm, or declassified to launder an effect; an endorsed secret reaching a
prompt; and the relaxation under nested branches and retries. Each is caught.

---

## 6. Token bounds that hold for real tokenizers

A worst-case token bound needs the input side too, and the obvious composition,
`tokens(template) + Σ tokens(argument)`, is not a bound.

### 6.1 What fails

We measured fourteen tokenizers pinned to exact revisions (GPT-2, `r50k_base`,
`cl100k_base`, `o200k_base`, Llama 2 and 3, Mistral, Phi-3, Gemma 2, Qwen2.5,
DeepSeek-V3, OLMo 2, T5, XLM-R) over every Unicode scalar value, 388 languages
of the Universal Declaration of Human Rights, source code and JSON
(`bench/tokenizers/measure.py`, E9):

1. **Tokenization is not subadditive.** `tokens(u·v) − tokens(u) − tokens(v)`
   reaches 3–6 in every tokenizer: `" Attribute"` and `"profiles"` are one
   `cl100k_base` token each, and `" Attributeprofiles"` is six.
2. **Responses inflate when re-encoded.** Decoding generated tokens and
   re-encoding the text with the same tokenizer gives up to nine tokens per
   generated token (Qwen2.5), so a model's output cap is not a bound on the next
   call's input.
3. **`tokens ≤ bytes` fails** for six of the fourteen tokenizers: SentencePiece
   tokenizers add a dummy prefix no byte pays for, Qwen2.5's NFC normaliser
   turns the three-byte U+0FAC into six tokens, and T5's and XLM-R's NFKC-like
   normalisers produce up to 194 more tokens than bytes on one string.
4. **The usual estimate is an estimate.** `bytes/4`, which a compiler can
   compute, is exceeded on 67.0–99.8% of 256-character multilingual windows and
   45.7–95.1% of code windows, depending on the tokenizer.

### 6.2 Bytes and contracts

Bytes add up under concatenation and do not depend on the tokenizer. OrchLang
therefore computes each request's bytes (template bytes plus each argument's byte
bound) and converts once per request through a **tokenizer contract**
`tokens_T(s) ≤ κ_T · bytes(s) + σ_T` for all strings `s`, plus the envelope
overhead the model declares. For a byte-level BPE tokenizer, `κ = 1, σ = 0`
holds structurally: every token covers at least one byte. SentencePiece with byte
fallback needs `σ` for its prefix and specials; Qwen2.5 needs `κ = 3` because it
tokenizes after NFC normalisation, and canonical decomposition can make a
string at most three times longer in bytes (Unicode UAX #15). T5 and XLM-R have
no structural contract, and the compiler refuses to certify through them
(`W267`). `bench/tokenizers/contracts.py` generates the contract table from the
measurements and refuses any contract the measurements contradict.

A response's byte length is bounded by `λ_T · o` for `o` output tokens, where
`λ_T` is the most bytes one vocabulary entry decodes to (128 for the tiktoken
encodings), provided decoding a token sequence, with invalid UTF-8 replaced by
U+FFFD, never yields more bytes than its tokens do separately: a property we
checked exhaustively on short byte strings and on random pairs, not proved. A
client-side byte cap on the model, if declared, replaces the product.

**Theorem 5 (guaranteed bound).** Assume each provider reports at most its cap,
each tokenizer satisfies its contract, each envelope adds at most the declared
overhead, each input satisfies its declared byte bound, and each response has
at most `λ × cap` bytes (or the declared cap). Then for every execution, output
tokens and billed input tokens are at most the certificate's `output_tokens` and
`input_tokens_guaranteed`.

The proof is an induction with sum for sequencing, componentwise maximum for a
branch and multiplication for `retry`, mechanised (`unary_bound`) with the
assumptions as hypotheses. The contracts and `λ` are measured, not proved: that
`tokens ≤ κ·bytes + σ` holds for *every* string rests on the structural argument,
which the exhaustive per-code-point measurement checks but cannot prove.

The price of soundness is `λ`. A response of 4,096 tokens may decode to 512 KiB,
and a chain of calls compounds it: on the real workflows the guaranteed bound
exceeds the estimate by up to 25× (§9.6). A client-side byte cap (`max_bytes`)
on the model is the practical remedy, and the language supports it.

---

## 7. Mechanisation

`proofs/OrchLang.v` (about 1,100 lines of Coq 8.18, no axioms, builds in about
four seconds with `make proofs`) mechanises Lemma 2 as the soundness of a
request-equivalence judgment, exactness of resolution, Theorem 1, Theorem 5 and
Theorem 6 for the core calculus: calls, public and secret branches, and retry, over
an abstract provider, validator, keying scheme, tape and guard predicates, all
section variables. `Print Assumptions` reports every main theorem closed under
the global context.

Modelling choices are stated in `proofs/README.md`. Strings are Coq strings, so
length is a byte length. The store is flat, and block scoping appears as
freshness side conditions of the judgment, which the implementation meets by
giving each declaration its own identity. The judgment is a relation; that equal
signatures, as the implementation computes them, give a derivation of it is
argued on paper. Lemma 1 (coupling validity) is not mechanised, so the Coq
theorems are pointwise, per tape. Theorems 2–4 are pen-and-paper. The C++
implementation is not verified against the model.

Mechanising Theorem 6 exposed a gap in its original proof. The draft defined a
fresh twin as a string that occurs in no member of the program's constants, and
no constant occurs in it. That does not prevent a *concatenation* of constants
from containing the twin across a boundary (`ab·ab` contains `ba`). The Coq
proof needs the twin to contain a character absent from every constant, and the
definition now says so.

---

## 8. Implementation

`orchc` is about 7,900 lines of C++17 with no dependencies: lexer, parser,
semantic analysis with binding identities and both labels, an IR, the cost
analysis, the relational analysis (with the two withdrawn rules kept as
selectable baselines for evaluation), a certificate emitter, and a runtime. The
certificate (JSON, format version 2) binds the result to the source by SHA-256
and to the analysis version, and records the bounds, the derivation, the labels,
every reclassification with its justification, the relational rule and the
leakage report. It is a report, not a proof object: no independent checker
exists yet. `make check` builds with `-Wall -Wextra -pedantic` and runs 137
tests.

**The runtime exists to falsify the analyses.** Its first version shared the
blind spot of the rule it was checking: it drew every output length uniformly
whatever the request said and billed input with the analysis's own estimate,
which are precisely the assumptions under which the size rule is sound. It could
not have caught §4.1. The runtime now has a content-dependent provider mode (the
draw is mixed with a hash of the request), a content-sensitive mock tokenizer
that, like real ones, is not subadditive, the three keying schemes, and an
invoice keyed by the provider's model name; `run --json` emits the full
transcript. The harness `bench/evaluate.py` checks every relational verdict in
every combination of these modes, re-bills requests with real tokenizers, and
exits nonzero on any violation. It was also rewritten because an earlier version
skipped failures, counted any nonzero exit as a security success and returned 0
despite recorded violations.

---

## 9. Evaluation

The evaluation asks:

* **RQ1** Is a certified bound ever exceeded?
* **RQ2** Does the content rule accept only workflows whose observers cannot tell
  secrets apart, and are its rejections real?
* **RQ3** How do the withdrawn rules and the classical quantitative bound fare on
  the same workflows?
* **RQ4** Are the leakage bounds respected, and how tight are they?
* **RQ5** What do real tokenizers and a real model say about the assumptions?
* **RQ6** What happens on real workflows?

Every number below is printed by `python bench/evaluate.py`, which exits nonzero
if any assertion fails; the experiment identifiers (E0–E11) are its sections.

### 9.1 RQ1: certified bounds

On 23 generated cost workflows (chains, branches, retries, nesting, wide inputs),
4,600 executions under the estimate model never exceeded the certified total, the
output component or the estimated input component, each checked separately (E1).
A flat per-call sum is exceeded on 14.9% of executions and a control-flow-aware
rule that charges a retry body once on 15.4% (E2); the certified bound's median
slack over the observed peak is 1.17× (E3). Under the content-sensitive
tokenizer and both provider modes, on the byte-bounded variants of the same 23
workflows, the guaranteed input bound was never exceeded in 4,600 executions
while the estimate was exceeded in 43.9% of them (E4). The counterexamples of the
external audit to the first unary bound still hold (E0).

### 9.2 RQ2: the content rule

The relational suite has 25 workflows: 11 whose observers cannot tell the secret
apart, and 14 that leak, including the audit counterexamples. For each, the
harness enumerates every secret value under 10 seeds, both provider modes, all
three couplings and both accounting modes, and compares what the workflow's
declared observer sees (E5). The content rule accepts the 11 and rejects the 14.
Across the accepted workflows, 21,080 paired comparisons showed no difference.
Every rejected workflow has a concrete witness: a seed and mode under which two
secret values give different observations.

### 9.3 RQ3: the withdrawn rules and the classical bound

On the same suite the bounds rule accepts 15 workflows, 6 of which leak, and the
size rule accepts 12, 4 of which leak (E5). Of the size rule's leaking
acceptances, the harness configuration used before this work (uniform provider,
global coupling, estimate accounting) sees none except where the model differs:
the blind spot of §8, measured. With the provider held fixed, three of the size rule's four
leaking acceptances already bill differently under real tokenizers (E6); the
fourth, `ShadowedPrompt`, sends equal token counts under all three, so its leak
shows only through a provider that reads content. The
interval-counting bound of Ngo et al. gives 6.0–9.4 bits on the workflows the
content rule proves leak-free (E7).

### 9.4 RQ4: leakage bounds

On eight leakage workflows with one or two secret flags or length intervals and
budgets of 0 to 2 bits, the number of distinct observations any seed and mode
produced never exceeded the certified class count, and reached it in every case
(E7): the bound is attained, as Theorem 4 predicts. Workflows over budget are
rejected.

### 9.5 RQ5: real tokenizers and a real model

The tokenizer facts of §6.1 are E9, re-checked live on the headline examples.
For the provider assumption, `bench/provider/measure.py` runs
SmolLM2-135M-Instruct (pinned revision) locally on fifteen pairs of chat
requests padded to exactly equal token counts under the model's own tokenizer and
chat template: under a shared sampling seed, all fifteen pairs gave different
output lengths, with a mean absolute difference of 34.1 tokens, while identical
requests with the same seed gave identical outputs (E10). Output length is a
function of content, not size, as Theorem 6 assumes a provider may make it.

### 9.6 RQ6: real workflows

TODO-E11

### 9.7 Analysis cost

TODO-COST

---

## 10. Threats to validity

**Internal.** The runtime is a mock. Its content-dependent provider is a hash,
which is adversarial in the sense that matters (any change to a request changes
the answer) but is not a model; E10 supplies one real model, and only a small
one. Real-tokenizer re-billing (E6, E11) uses real tokenizers on the runtime's
requests, whose variable parts are mock text. The relational verdicts are
checked by enumeration over declared secret values, which is exhaustive for the
suites' small bounds and would not be for large ones.

**Construct.** The benchmark suites are author-written. The paired design (each
unsafe workflow has a safe twin differing by one edit) prevents a checker from
scoring well by rejecting everything, but not designer bias; the real-workflow
corpus addresses that, but has no secrets. The tokenizer contracts and `λ` rest
on measurement and a structural argument, not proof; a tokenizer revision that
changes normalisation could break a contract, which is why contracts are pinned
to revisions and regenerated from measurements.

**External.** The real-workflow corpus is three sources and 52 candidates, sampled
by a fixed rule, not a random sample of deployed workflows. Its labels are derived
by rules applied by the author; for AgentDojo the untrusted labels are AgentDojo's
own canary mechanism, and the cross-check uses AgentDojo's recorded runs.
Declared byte bounds on inputs (8 KiB where a source gives none) are
assumptions, and the certificate holds only when a deployment enforces them.
Every assumption the guaranteed bound makes about a provider (its caps, its
envelope overhead) is taken from documentation or framework defaults, not
observed on a hosted endpoint; no hosted provider was tested.

---

## 11. Related work

**Resource-aware noninterference and relational cost.** Ngo et al. [2017] and
RelCost [Çiçek et al. 2017] are the closest work and are discussed in §1.1 and
§4.3; AARA [Hoffmann et al. 2012; Kahn and Hoffmann 2020] supplies the potential
method both build on. Relative to Ngo et al., our contribution is the theorem
that indexing by size cannot be sound for opaque, content-dependent operations.
Relative to RelCost, whose refinements can express the content comparison for a
fixed pair of runs, it is the resolution over feasible secret outcomes, the
observers, the leakage bound, and the application to LLM calls.

**Constant time and cross-copying.** Accepting a secret branch whose arms perform
the same observable operations is Agat's transformation [2000] and the
program-counter security model [Molnar et al. 2005]; CacheAudit bounds cache
leakage by counting observations [Doychev et al. 2013]. Here the observable
operation is a request, and "the same" must mean the same content.

**Quantitative information flow.** Min-entropy leakage and min-capacity [Smith
2009], their behaviour under cascade [Espinoza and Smith 2011], and bounds by
counting equivalence classes under adaptive attack [Köpf and Basin 2007] are
what Theorem 2 applies.

**Couplings and pRHL.** Lemma 2 is a pRHL derivation with identity couplings
[Barthe et al. 2009]; couplings as a proof technique for relational properties of
probabilistic programs are developed by Barthe et al. [2017].

**Side channels of LLM services.** Token lengths of streamed responses leak
response text to a network observer [Weiss et al. 2024]; output token counts leak
input properties through timing [Zhang et al. 2024]; packet sizes and timing of
encrypted streams reveal prompt topics across 28 models [McDonald and Bar Or
2025]; shared prompt caches are a cross-user timing channel at seven providers
[Gu et al. 2025]. These establish the channel at the level of one call; we
address how a workflow's control flow feeds it.

**Security of LLM agents.** Indirect prompt injection [Greshake et al. 2023] is
what the integrity half of OrchLang's typing targets. CaMeL separates a planner
from untrusted data and tracks capabilities through a custom interpreter at run
time [Debenedetti et al. 2025]; FIDES tracks confidentiality and integrity labels
dynamically in an agent planner [Costa et al. 2025]; Beurer-Kellner et al. [2025]
catalogue design patterns, among them plan-then-execute, which our AgentDojo
ports follow. AgentFlow combines a policy language with a runtime monitor and a
bounded verifier [arXiv:2608.22868]; NeuroTaint audits execution traces offline
[arXiv:2604.23374]; Agentproof verifies extracted workflow graphs statically
[arXiv:2603.20356]. None reasons about resources or about what the requests reveal
through their content. AgentDojo [Debenedetti et al. 2024] supplies our injection
benchmark tasks and recorded attack runs.

**Budgets and tokenization.** Token Budgets catalogues 63 production
budget-overrun incidents and enforces caps at run time with affine types
[arXiv:2606.04056]; its reservation slack is measured on a different corpus and
is not comparable with ours. Tokenizers are known to charge languages unequally
[Petrov et al. 2023]; we measure the consequences for bounds (§6).

---

## 12. Limitations and future work

**The relational analysis has not met a real secret.** None of the 30 real
workflows declares or implies a secret in its source's threat model, so the
analysis that motivates the paper verified nothing on them. The pattern it
targets, a branch on private data that is not itself sent to a model (a user's
tier, a risk flag, a local PII detector), is plausible and simple to write, but
we have not shown that deployed workflows contain it.

**Declassification is too coarse.** Real workflows send private data to a
provider, which requires declassifying it, which makes it public to every
observer. An observer-relative policy, in which the provider may see content that
the network and the bill observer may not, would let the analysis reason about
those workflows. Theorems 1 and 2 would need an observer-indexed notion of
equivalence.

**The integrity half over-reports.** A value computed in an arm guarded by
untrusted data is labelled untrusted even when computed only from trusted data
(§9.6); separating data and program-counter labels for integrity, as §5.6 does for
confidentiality, would remove the two false positives found on the held-out split.

**Retry cannot carry feedback.** Self-correction loops that show the model its
earlier attempts had to be unrolled in five of the thirty ports. A retry with an
accumulator of declared byte growth would keep the bound finite.

**Agents are out of scope by design.** Thirteen of the 22 exclusions are workflows
whose shape is decided at run time, nine of them because the model chooses what
runs next. OrchLang's fixed shape is what makes its analyses decidable; a type
system for agent loops would need bounds on the model's choices, which is a
different paper.

**The guaranteed bound is loose** by the factor `λ`, up to 25× the estimate on
real workflows, unless models declare client-side byte caps.

**The certificate is not independently checked.** A small checker that re-derives
the bound from the certificate and the source, with tampering tests, would make
the certificate evidence rather than a report.

**The implementation is not verified** against the Coq model, only tested
against it through the runtime.

---

## 13. Conclusion

An analysis that compares LLM requests by anything coarser than their content
cannot be sound against providers that answer content, unless it gives up on every
branch; comparing content gives noninterference that needs no assumption about
providers, tokenizers or observers, and a leakage bound that counts request
classes instead of noisy observations. Token bounds likewise have to be built from
the one measure that adds up. Both results are mechanised, implemented and tested
by a harness built to fail. On real workflows, the bounds hold and the flow checks
find the injection surfaces, but the side channel we set out to close did not
appear: whether it matters in practice depends on whether deployed workflows
branch on private data they do not send, which we leave open.

---

## Data availability

`https://github.com/guyoverclocked/orchlang-compiler-design-project`

```sh
make check                     # build and 137 tests
make proofs                    # Coq 8.18: build the development, print its axioms
python bench/generate.py       # regenerate the synthetic suites
python bench/evaluate.py       # every number in §9; exits nonzero on failure
python bench/evaluate.py --offline   # without downloads; the report is marked PARTIAL
```

Tokenizer measurements: `bench/tokenizers/measure.py`; the real model:
`bench/provider/measure.py`; the real-workflow sources at their pinned revisions:
`bench/real/fetch_sources.sh`. The audits and their counterexamples are in
`docs/AUDIT_2026-09-25.md`, `docs/RESEARCH_AUDIT_2026-09-17.md` and `audit/`.

## Declaration of generative AI use

The implementation, proofs, experiments and text of this revision were produced
with substantial assistance from an AI coding assistant (Anthropic's Claude),
working under the author's direction and brief. The author takes responsibility
for the content.

## Declaration of competing interest

None.

---

## References

Agat, J. (2000). Transforming out timing leaks. *POPL*.

Barthe, G., Grégoire, B., Zanella-Béguelin, S. (2009). Formal certification of
code-based cryptographic proofs. *POPL*.

Barthe, G., Grégoire, B., Hsu, J., Strub, P.-Y. (2017). Coupling proofs are
probabilistic product programs. *POPL*.

Beurer-Kellner, L., et al. (2025). Design patterns for securing LLM agents against
prompt injections. arXiv:2506.08837.

Çiçek, E., Barthe, G., Gaboardi, M., Garg, D., Hoffmann, J. (2017). Relational cost
analysis. *POPL*.

Costa, M., et al. (2025). Securing AI agents with information-flow control (FIDES).
arXiv:2505.23643.

Debenedetti, E., Zhang, J., Balunović, M., Beurer-Kellner, L., Fischer, M.,
Tramèr, F. (2024). AgentDojo: A dynamic environment to evaluate prompt injection
attacks and defenses for LLM agents. *NeurIPS Datasets and Benchmarks*.

Debenedetti, E., et al. (2025). Defeating prompt injections by design (CaMeL).
arXiv:2503.18813.

Doychev, G., Feld, D., Köpf, B., Mauborgne, L., Reineke, J. (2013). CacheAudit: A
tool for the static analysis of cache side channels. *USENIX Security*.

Espinoza, B., Smith, G. (2011). Min-entropy leakage of channels in cascade.
*FAST*, LNCS 7140 (2012).

Greshake, K., et al. (2023). Not what you've signed up for: Compromising
real-world LLM-integrated applications with indirect prompt injection. *AISec*.

Gu, C., Li, X. L., Kuditipudi, R., Liang, P., Hashimoto, T. (2025). Auditing
prompt caching in language model APIs. *ICML*.

Hoffmann, J., Aehlig, K., Hofmann, M. (2012). Multivariate amortized resource
analysis. *ACM TOPLAS* 34(3).

Kahn, D. M., Hoffmann, J. (2020). Exponential automatic amortized resource
analysis. *FoSSaCS*.

Köpf, B., Basin, D. (2007). An information-theoretic model for adaptive
side-channel attacks. *CCS*.

McDonald, G., Bar Or, J. (2025). Whisper Leak: a side-channel attack on large
language models. arXiv:2511.03675.

Molnar, D., Piotrowski, M., Schultz, D., Wagner, D. (2005). The program counter
security model: Automatic detection and removal of control-flow side channel
attacks. *ICISC*.

Ngo, V. C., Dehesa-Azuara, M., Fredrikson, M., Hoffmann, J. (2017). Verifying and
synthesizing constant-resource implementations with types. *IEEE S&P*.
arXiv:1801.01896.

Petrov, A., La Malfa, E., Torr, P., Bibi, A. (2023). Language model tokenizers
introduce unfairness between languages. *NeurIPS*.

Sabelfeld, A., Myers, A. C. (2003). Language-based information-flow security.
*IEEE JSAC* 21(1).

Smith, G. (2009). On the foundations of quantitative information flow. *FoSSaCS*.

Volpano, D., Smith, G., Irvine, C. (1996). A sound type system for secure flow
analysis. *Journal of Computer Security* 4(2–3).

Weiss, R., Ayzenshteyn, D., Amit, G., Mirsky, Y. (2024). What was your prompt? A
remote keylogging attack on AI assistants. *USENIX Security*.

Zhang, T., Saileshwar, G., Lie, D. (2024). Time will tell: Timing side channels via
output token count in large language models. arXiv:2412.15431.

AgentFlow: A flow-centric policy language and framework for securing LLM agent
systems. arXiv:2608.22868.

Ghost in the agent: Redefining information flow tracking for LLM agents
(NeuroTaint). arXiv:2604.23374.

Agentproof: Static verification of agent workflow graphs. arXiv:2603.20356.

Token Budgets: An empirical catalog of 63 LLM-agent budget-overrun incidents,
with an affine-typed Rust mitigation as a case study. arXiv:2606.04056.
