# Formal Contract: Bounded Cost and Shared-Oracle Billing Equality

This note states the conditions under which OrchLang's current analyses support
two claims: a structural upper bound on abstract token use, and equality of
per-contract billing observations when only secret state changes. These are
conditional claims about the language's abstract execution model. They are not
claims about a real provider's wire protocol or invoice.

## 1. Scope and machine model

The analyzed fragment has lexically scoped declarations, prompt calls, finite
`if` statements, bounded `retry n` statements, outputs, tool effects, and
explicit relabelling. It has no unbounded loop, arithmetic expression, network
tool result, or dynamically discovered call. A call resolves to a model contract

\[
c=(provider, modelId, outputCap, priced?, unitPrice?).
\]

The source alias is not part of `c`. The cap and price fields are part of the
contract identity used by the analyzer and mock runtime. A separate tokenizer
identity is the declared resolved provider/model pair; this string is not an
independent check of the provider's tokenizer version. The analyzer rejects a
model-generated value used as another tokenizer's input unless the identities
match (`E267`). Thus two aliases resolve as one contract only when provider,
model id, output cap, and price metadata all agree. Price metadata participates
in identity, but the theorem's bill is still token/call usage rather than an
external currency invoice.

Each binding has a lexical identity distinct from its spelling. A value alias
created by `declassify` or `endorse` retains the source value identity, while a
shadowing declaration gets a new identity. For the relational analysis, an
argument is represented by one of:

* an exact decoded literal;
* an outer lexical value identity, whose public value is fixed between the
  compared executions; or
* a positional reference to an earlier call result in the same matched call
  sequence.

The semantic pass keeps an effective label and a content label separately.
The effective label includes the current program-counter dependence; the
content label records explicit data dependence and excludes control dependence.
It alone does not establish secret independence. A call rejects secret
content (`E230`), while a value produced under a secret guard can have public
contents but a secret effective label. Such calls are admitted only when the
relational obligation for the controlling secret branch matches their request
signatures. A branch is classified by the guard's intrinsic content label: a
public guard nested under a secret program counter is retained as a public
branch in that enclosing secret signature, where its guard is compared by
resolved value identity. Output and tool checks use effective labels/program
counter; they are separate from the billing theorem below. `declassify` changes
content confidentiality explicitly and is excluded from the theorem; `endorse`
changes integrity, not confidentiality.

The call descriptor compared by the implementation is the resolved contract,
exact decoded prompt-template bytes, and ordered argument descriptors. This is
an **abstract request descriptor**. It does not establish that the compiler
serializes a byte-for-byte provider request: no provider adapter or request
serializer is part of this implementation.

For a fixed workflow and seed, the abstract request is `Q = (templateBytes,
orderedArgumentValues)`, using the DSL's prompt representation and concrete
values in the abstract semantics. It does not include provider-added messages,
request options, tool schemas, or wire serialization. The shared
request-sensitive oracle is

\[
\Omega(c,k,Q)=(response_{c,k,Q}, outputUsage_{c,k,Q}),
\qquad 0\le outputUsage_{c,k,Q}\le c.outputCap,
\]

where `k` is the zero-based invocation ordinal for that exact resolved
contract. The notation suppresses the fixed workflow and seed. The C++
ordinal-only mock derives draws from the seed, workflow, contract key, and
ordinal. Its request-sensitive mode derives draws from the seed and a key made
from the resolved contract, ordinal, exact template/literal fields, and
identifier projections `(tokens, flag)`; workflow spelling is omitted. The
same oracle mode and seed are used by both executions being compared. Equal
`(c,k,Q)` keys give the same complete abstract outcome:
response content, output usage, and any metadata that can affect later guards,
arguments, or retry decisions. The theorem does not assume that equal
ordinals with different requests produce equal outcomes.

Retry decisions are also coupled. Corresponding retry events use the same
retry schedule and therefore the same number of attempts. In the C++ mock this
schedule is deterministically derived from the seed, workflow, dynamic retry
event ordinal, and attempt number. In ordinal-only mode, model responses are
derived from the seed, workflow, resolved contract key, and per-contract call
ordinal. In request-sensitive mode, response draws use the request key just
described and omit workflow spelling. Both modes preserve the per-contract
call ordinal; neither is a real provider model.

For one execution, the **invocation trace** is the ordered sequence

\[
((c_0,Q_0,I_0,O_0),(c_1,Q_1,I_1,O_1),\ldots),
\]

where `Q_j` is the call's abstract request, `I_j` is its abstract input charge,
and `O_j` is the oracle's output usage. The **billing trace** drops `Q_j` and
keeps the ordered triples `(c_j,I_j,O_j)`. The **billing observation** groups
that trace by resolved contract and records call count, input usage, and output
usage. This is the observation compared by the runtime's `sameBilling` helper.
Lexical result names, source aliases, output values, tool arguments, timing,
and monetary invoice adjustments are not part of this observation.

## 2. Assumptions for the input-token bound

Let `d = chars_per_token`, with `d >= 1`. For a prompt template `t`, let
`|UTF8(t)|` be its byte length. At call site `j`, let `b_i` be the bound for
argument `i`, in the target call's common tokenizer unit. The input-cost premise
for every reachable call is:

\[
I_j \le \left\lceil\frac{|UTF8(t_j)|}{d}\right\rceil
       + \sum_i b_i.
\]

This is a **per-call full abstract request-accounting assumption**. It must
cover every charged input component. In particular, there may be no uncounted
system prompt, tool schema, provider framing, or other request overhead, and
tokenization across concatenation boundaries must not make the full request
cost exceed the stated sum. The density parameter `d` alone does not establish
these conditions. A real provider's tokenizer and serialization are not
verified here.

The compiler derives the terms as follows:

* Template bytes and literal bytes use `ceil(byte_length / d)`.
* An external input's declared `max_tokens` is assumed to be a true bound in
  the target call's tokenizer unit. That cross-provider fact comes from the
  environment or its adapter; the compiler does not infer it from `d`.
* A model result's declared bound is its producer's `max_tokens`. It can be
  reused as an input bound only when producer and target tokenizer identities
  match. The current check uses provider and model id equality (`E267`); this
  may reject safe cross-model conversions, but it does not provide a conversion
  when identities differ.
* Literal and template accounting follows the implementation's abstract
  additive cost model. It does not count a concrete provider request.

For a concrete abstract descriptor, that additive estimate is a deterministic
function of the exact template bytes and argument values. The premise above
requires the whole abstract input charge to stay below the estimate formed from
the declared argument bounds. Matching descriptors therefore have equal
abstract input charges; this does not imply that a provider tokenizer has the
same additive behavior.

The output-cost premise is that each invocation honors the resolved contract's
`max_tokens` cap. An `n`-bounded retry can execute its body at most `n` times.
These premises are explicit requirements of the cost claim, not facts proved
about an external service.

## 3. Unary token-bound claim

For a workflow block `B`, define `C(B) = (G(B), I(B), T(B))`, where `G` bounds
output usage, `I` bounds abstract input usage, and `T` bounds their sum. The
structural rules are:

\[
\begin{aligned}
C(\epsilon) &= (0,0,0),\\
C(s;B) &= C(s)+C(B),\\
C(\text{if }g\text{ then }A\text{ else }B)
  &= (\max(G(A),G(B)),\max(I(A),I(B)),\max(T(A),T(B))),\\
C(\text{retry }n\{A\}) &= n\cdot C(A),\\
C(\text{call }c,t,(a_i))
  &= (c.outputCap,\lceil|UTF8(t)|/d\rceil+\sum_i b_i,
      c.outputCap+\lceil|UTF8(t)|/d\rceil+\sum_i b_i).
\end{aligned}
\]

Non-call statements contribute zero model tokens. The C++ implementation uses
saturating arithmetic at `SIZE_MAX` to avoid integer wraparound. This value is
an overflow sentinel, not a finite upper bound on an arbitrary mathematical
resource count greater than `SIZE_MAX`. The cost analyzer rejects a workflow
whose total bound is saturated with `E266`; therefore the theorem below applies
only to accepted, representable bounds. At branches the three components are
maximized separately, so `T` bounds the actual path total even when the largest
input and output components come from different arms. The sum `G+I` can
therefore be looser than `T`.

**Theorem (conditional abstract cost bound).** If every reached call satisfies
the input-cost premise above, every model respects its output cap, every
external value respects its declared bound, every retry obeys its source
bound, and the accepted workflow's computed total is representable without
saturation, then any execution has input usage at most `I(B)`, output usage at
most `G(B)`, and total abstract usage at most `T(B)`.

**Proof sketch.** Induct on the syntax tree. A call is bounded by its
per-call premises. Sequential composition adds the upper bounds. A conditional
executes one arm, so each component is bounded by that component's arm maximum.
A bounded retry executes at most `n` copies of its body. Other statements add
no model usage. Over mathematical integers, the recurrence uses ordinary
addition, componentwise maxima, and multiplication by the retry bound. The C++
implementation's arithmetic agrees with this recurrence for accepted
representable totals; if saturation reaches a workflow total, `E266` rejects
it instead of certifying `SIZE_MAX` as a finite proof bound. The certificate's
workflow total uses `T(B)` for the budget comparison.

The theorem is not a provider-independent statement that `d=1` or any other
value of `d` alone bounds real tokenization. The full per-call input premise is
required in addition to the declared input units.

## 4. Billing noninterference claim

Consider two initial stores for the same workflow. All non-secret external
values (including untrusted inputs) agree; secret values may differ, subject
to declarations. Use the
same shared oracle `\Omega` and the same retry schedule in both executions.
Require that the program contains no confidentiality `declassify` operation.
This whole-program condition is intentionally simple and conservative.

An outer-value request atom denotes the same value in both executions. A
prior-result atom denotes the result at a matched earlier call position. A
public branch node retains its guard and arms: corresponding executions take
the same arm when the guard's contents agree. A secret branch is accepted only
when both arm signatures are defined and structurally equal. A call signature
compares the complete resolved model contract, exact template bytes, and the
ordered literal/value atoms. Guard matching uses the resolved lexical value
identity rather than the variable's spelling, so shadowed names do not merge;
alias bindings preserve the source value identity. Retry signatures compare
their bound and body.
The equality is conservative: different outer variables are treated as
different even if an external invariant might make their lengths equal.

**Theorem (conditional per-contract billing equality).** Suppose the program
passes the semantic, cost, and relational checks; has no confidentiality
declassification; its two executions agree on public external values; and both
executions use the same complete oracle and retry schedule as defined above.
Then their invocation traces are equal:

\[
InvocationTrace(W,public,secret_1,\Omega,\rho)
 = InvocationTrace(W,public,secret_2,\Omega,\rho).
\]

Dropping requests from these traces gives equal ordered billing traces;
grouping those events by contract gives equal per-contract billing
observations.

This theorem concerns the abstract charge `I_j` from §2 and shared-oracle
output usage. It does not prove equality of a real provider's itemized invoice.

**Proof sketch.** Proceed by induction through the workflow and maintain equal
values for public bindings and corresponding prior-call results, as well as
equal per-contract invocation ordinals. For a call, the signature atoms denote
equal values: literals are identical, outer values agree by the paired-store
hypothesis, and prior results agree by the induction hypothesis and shared
oracle. The template and resolved contract are identical, so both calls have
the same modeled request `Q`. Thus the abstract input charge is equal, and the
same `(contract, ordinal, Q)` selects the same complete oracle result and
output usage. For a public branch, equal guard values select
the same arm, to which the induction hypothesis applies. For a secret branch,
either guard may be selected, but the two arm signatures are equal, so each
choice produces the same billing events. The signature construction checks
nested secret branches recursively and preserves public branches, allowing the
same reasoning inside them. For a retry, equal body signatures and the shared
schedule give equal attempt counts; apply the body argument for each attempt.
Sequential composition concatenates equal traces. Aggregating equal events by
contract yields equal observations.

### What this theorem excludes

* A `declassify` directive invalidates the theorem's side condition. A released
  value can still vary with the original secret, and can change request cost.
  The relational check is not release-aware. A local branch obligation may
  still be discharged for such a program, but certificate version 3 records
  `declassification_present: true` and withholds the workflow-level
  `billing_noninterference_claimed` flag. A discharged branch obligation alone
  is not a billing noninterference theorem for a program that declassifies.
* The theorem requires the **same** deterministic oracle coupling and retry
  schedule. It does not claim pathwise equality of independently sampled
  executions. A conditional distributional corollary is stated in §6; it is
  not implemented or empirically validated for any provider.
* It covers billing only. It does not establish equality of workflow outputs,
  tool effects, effect arguments, timing, or other observable traces.
* It does not eliminate prompt injection or prove that a model follows a
  prompt. The integrity labels and explicit endorsement checks are separate
  static checks with their own assumptions.
* The source signature is not an independently verified proof object. The
  compiler implementation and this proof sketch have not been checked by a
  proof assistant or a separate certificate verifier.

## 5. Relation to the executable mock and run gate

The C++ `run` command is deterministic and offline. It computes mock input usage
as the estimated template count plus argument token counts. Its mock model
produces a token count capped by `max_tokens` and a boolean derived from that
count. The default output oracle ignores `Q` and is keyed by workflow, seed,
resolved contract, and per-contract ordinal. The optional
`--request-sensitive-oracle` mode includes the exact template and literal bytes
in its key; identifier values are represented only by the mock's token-count
and boolean fields, because the runtime has no actual text values. The mock
does not generate text, serialize requests, or contact a provider. Both modes
therefore execute projections of the complete request-sensitive abstract
oracle in §1. They do not test arbitrary response text or provider request
contents beyond those projections.

With the default options, `run` invokes semantic, cost, and relational
analysis and refuses to execute when those analyses report errors.
`--audit-unsafe` skips the cost and relational gates for counterexample runs;
it does not bypass syntax, type, or semantic checks. A concrete run used as a
bound witness must also respect every declared external token bound. The CLI's
`--pin` option is a test override; the runtime rejects a pin above a declared
bound (or a pin with the wrong declaration type) with `R002`. A pin accepted
for an unbounded declaration still does not create a static input bound for a
prompt call.

The `run` gate can still permit a declassifying program whose local checks
pass. Consult the version 3 certificate's workflow-level claim flag; a
discharged local relational obligation does not override that flag.

The reported monetary amount is a multiplication by declared unit prices. It
does not account for provider rounding, cached-token rates, discounts, retries
charged differently, or other invoice rules. The formal observation is the
per-contract token/call trace, not currency.

## 6. Conditional stochastic-provider distribution corollary

The deterministic shared oracle in §1 is a sufficient special case of a
stochastic call contract. Let a complete call outcome be

\[
Y_j=(response_j, inputUsage_j, outputUsage_j, status_j, metadata_j),
\]

including every returned field that can affect a later request, branch,
retry, or observable usage event. Assume the outcome and history spaces are
measurable, and that each call is described by a conditional kernel

\[
K_{c,k,Q,H}(dy),
\]

where `c` is the resolved contract, `k` its ordinal, `Q` the complete modeled
request, and `H` the complete relevant API history/state. `H` is the history
that conditions the API law; it is not the entire source-program state. The
contract must be **secret-independent at matched histories**: for every pair
of related source states with the same `c`, `k`, `Q`, and `H`, the two calls
use the same conditional law. Any provider, account, session, cache, region,
or other hidden state that changes that law must either be included in `H` and
aligned, or the resulting conditional laws must otherwise be shown equal; if
neither holds, the premise fails. No independence between successive calls is
required; dependence on prior outcomes is allowed through `H`.

**Corollary (equal usage-trace laws under a matched kernel).** Suppose the
relational source argument establishes that, for every pair of secret stores
sharing public inputs and every pair of related histories, the next resolved
contract, ordinal, and complete modeled request match; the kernel premise
above holds at those matched histories; and control decisions and stopping
are determined by the coupled outcomes and the checked public/secret-branch
rules. Then the executions admit a coupling under which each pair of call
outcomes is equal almost surely. Their finite usage prefixes therefore have
identical distributions. For a bounded terminating program, their complete
usage-trace distributions are identical. For a graph with a productive cycle,
this gives equality of every finite prefix; it gives no finite whole-run token
or price bound. Any randomized retry controller or other random transition
must also be included in the complete outcome/kernel contract; otherwise the
retry behavior must be deterministic from the coupled state.

**Proof sketch.** Start from stores with equal public inputs and use the
relational invariant. At the next call, both sides have the same `(c,k,Q,H)`,
so their conditional outcome kernels are equal. Couple the two outcomes by
the identity coupling: draw one `Y` from that common kernel and assign it to
both executions. This preserves each side's required marginal law and makes
the next outcomes equal with probability one. The relational argument then
keeps later request descriptors and public decisions aligned; induction gives
the result for every finite prefix. In a bounded terminating program the
checked control rules synchronize stopping, so the same argument gives the
complete trace result. This is a coupling witness on an auxiliary probability
space. It does **not** require, or assert, that two independently sampled
actual runs use the same random seed or produce the same responses path by
path. Equality in law follows because the constructed joint distribution has
the required marginals and is supported on equal usage traces.

This is standard probabilistic coupling reasoning, not a new coupling
principle. Barthe and Hsu explain that a coupling is a joint distribution with
the prescribed marginals and use it to establish relational properties of
probabilistic programs; Barthe et al. present coupling proofs as probabilistic
product programs ([primary sources](https://doi.org/10.1017/9781108770750.006),
[POPL 2017](https://doi.org/10.1145/3009837.3009896)). The corollary only
clarifies how a deterministic shared-outcome theorem can imply equality in
distribution when a real system satisfies a suitable conditional-kernel
contract.

The current compiler, graph checker, and mock do not specify, infer, or
validate a provider's kernel. They do not show that a real provider has the
same conditional response/usage law at matched descriptors, that hidden
provider state is aligned, or that a provider exposes complete per-call usage
records. Consequently the corollary is a conditional semantic observation,
not an empirical provider result or an implemented stochastic analysis. The
mock is a deterministic special case; seeded probes are not evidence about a
provider's distributions. This result proves no numerical expected cost, tail
bound, mutual-information bound, differential-privacy guarantee, or invoice
equality.
