# Why the problem matters, and how to present it

## The opening example

A private decision chooses one of two calls. Both calls have the same declared
token ceiling. One sends a short public message; the other sends a longer one.
An observer who knows those messages can distinguish the private decision from
the actual usage record. The ceiling remains correct.

This is the first HTML demonstration. It establishes the project's question:
**can private workflow decisions change an observable usage trace?** A bound
and a confidentiality property answer different questions.

## Why a usage observer deserves attention

Prior attacks show that length-related observations can reveal information
about LLM interactions. Weiss et al. study encrypted streaming traffic;
Zhang et al. study output count and timing; Li et al. study merged output
chunks. Their observation models differ from OrchLang's per-call usage
records. They motivate investigating metadata, but they do not establish an
OrchLang billing attack or validate its assumptions.

- [Weiss et al., USENIX Security 2024](https://www.usenix.org/conference/usenixsecurity24/presentation/weiss)
- [Zhang et al., *Time Will Tell*, arXiv preprint](https://arxiv.org/abs/2412.15431)
- [Li et al., USENIX Security 2026](https://www.usenix.org/conference/usenixsecurity26/presentation/li-sijia)

Billing accountability is a related concern with a different trust boundary.
The ICML 2026 position paper *Invisible Tokens, Visible Bills* discusses
hidden operations and auditability. A compiler cannot infer actual provider
execution or invoice correctness from its own abstract cost model. OrchLang
therefore states what its request and accounting contracts include, and
keeps provider attestation outside the current guarantee.
[Primary position paper](https://proceedings.mlr.press/v306/sun26bd.html).

The project's importance is consequently **credible but bounded**. Usage
metadata can matter for confidentiality; source workflows can create
distinctive call counts, lengths and order; and developers need evidence
that a proposed protection addresses their actual observer. Deployment
prevalence, incident frequency, economic losses and provider-specific risk
have not been measured here.

## What the software adds

The compiler checks declared accounting and request relationships. The graph
tools extend the request analysis to productive cycles. The quantitative
tools distinguish equal means, equal totals and equal ordered laws under a
supplied finite kernel. Separate replayers check the evidence. Source
adapters and offline framework execution expose the assumptions needed to
connect a model result to code.

Each level has its own result and limits. A cap proves a ceiling under its
accounting premise. A relational certificate establishes equality under a
shared outcome oracle and the admitted semantics. A stochastic certificate
concerns the supplied model and selected inputs. A direct source execution
is concrete evidence, with its source pin and execution scope recorded.
Neither a green test nor a source hash by itself proves a universal property.

The mathematical foundations are established. The contribution should be
presented as research software for an LLM workflow review, with inspectable
contracts and evidence that a reviewer can replay. See the
[prior-art matrix](PRIOR_ART_MATRIX.md) and the
[independent publication assessment](FINAL_PUBLICATION_REVIEW.md).

## A sequence that holds attention

1. Show the equal-ceiling counterexample. Let the audience identify the
   private arm from the usage record.
2. Show the dependent workflow admitted by the improved compiler. Explain
   how equality of the first request aligns the result used in the next call.
3. Run an independent certificate replay, including a rejected tamper probe.
4. Show equal aggregate totals with different call order, then equal means
   with disjoint distributions. State exactly what the observer sees.
5. Finish with HTML story 07: different hidden structure, equal observable
   laws, and a replayed exact certificate. State that the kernel is supplied,
   not fitted to a provider.

Use the source case as evidence of practical review obligations only to the
extent its current analysis and reproduction support. Distinguish the
sanitized-text relation from full incident confidentiality: raw incident
state/checkpoints and concurrency need their own treatment.

## A defensible closing sentence

“We built a compiler and replayable analysis tools that distinguish a token
budget from a usage confidentiality claim, and make the assumptions needed
for each result visible and checkable.”

The narrative ties each conclusion to a stated observer, contract and
replayable artifact. Novelty and acceptance remain matters for comparison
and review.
