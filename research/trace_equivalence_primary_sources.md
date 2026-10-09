# Primary-source check: probabilistic trace equivalence

**Checked:** 9 October 2026. This note records what the cited prior work
supports, so the OSP manuscript can describe the new checker as a bounded
software application of established equivalence methods.

## Exact equivalence and span exploration

Wen-Guey Tzeng, “A Polynomial-Time Algorithm for the Equivalence of
Probabilistic Automata,” *SIAM Journal on Computing* 21(2), April 1992,
216–227, DOI [10.1137/0221017](https://doi.org/10.1137/0221017). The SIAM
abstract defines equivalence by equality of acceptance probability for every
string and gives an `O((n1+n2)^4)` decision algorithm. Its accessible abstract
does not spell out the vector-space construction.

The algorithm detail is stated explicitly in the primary CAV paper by Stefan
Kiefer, Andrzej S. Murawski, Joël Ouaknine, Björn Wachter, and James Worrell,
“Language Equivalence for Probabilistic Automata,” in *Computer Aided
Verification (CAV 2011)*, LNCS 6806, pp. 526–540, DOI
[10.1007/978-3-642-22110-1_42](https://doi.org/10.1007/978-3-642-22110-1_42),
[author-hosted full text](https://people.mpi-sws.org/~joel/publications/langeqprobaut11.pdf).
It describes Tzeng's procedure as exploring word-generated state-distribution
vectors and pruning vectors linearly dependent on the basis already found; a
non-equivalent pair has a distinguishing word of length at most the sum of the
automata's state counts. The paper also gives a backward basis algorithm and
discusses probabilistic program equivalence, obliviousness, and anonymity.
Its implementation uses numerical methods; it should not be cited as evidence
that OrchLang's exact-fraction implementation is an inherited implementation
or that exact arithmetic has no resource cost.

The rational-field setting has a more direct reference in Stefan Kiefer,
Andrzej S. Murawski, Joël Ouaknine, Björn Wachter, and James Worrell, “On the
Complexity of Equivalence and Minimisation for Q-weighted Automata,” *Logical
Methods in Computer Science* 9(1), article 8, 2013, DOI
[10.2168/LMCS-9(1:8)2013](https://doi.org/10.2168/LMCS-9(1:8)2013),
[arXiv record](https://arxiv.org/abs/1302.2818). The article studies weighted
automata over rationals and finite-word equivalence, and notes finite
distinguishing words. This supports the exact-arithmetic precedent, not a
claim that the present observer encoding or certificate format is novel in
automata theory.

## Current implementation/evidence boundary

The current producer implements the row-span construction with exact
fractions and state, matrix-entry, deterministic byte-work, and
rational-precision caps. The independent replayer uses a separate exact
elimination implementation and reconstructs the graph/kernel closure before
checking the basis or finite witness. The controlled study
[`trace_equivalence.json`](../bench/results/trace_equivalence.json) reports 12
authored fixtures: six proved equal and six unequal with finite words; all 12
independently replay. Equal cases have 48 finite-DP cross-checks over 96
scenario histograms at horizons 1, 2, 4, and 8. All six witness checks match
the exact reported probabilities. Twelve fresh resource-cap probes return
unknown, and twelve semantically tampered reports are rejected. One fixture
has equal trace laws while strong probabilistic bisimulation is inconclusive.

These are controlled software-verification results, not independent
applications. The gap fixture and kernel are authored. Replay checks the
certificate against the supplied graph, kernel, and implemented semantics; it
does not validate that a provider follows the kernel or that usage labels
match an invoice.

## Trace equivalence as a security verification technique

The most direct tool antecedent is the CAV paper above and its companion
software paper: Stefan Kiefer, Andrzej S. Murawski, Joël Ouaknine, Björn
Wachter, and James Worrell, “APEX: An Analyzer for Open Probabilistic
Programs,” in *Computer Aided Verification (CAV 2012)*, LNCS 7358,
pp. 693–698, DOI
[10.1007/978-3-642-31424-7_51](https://doi.org/10.1007/978-3-642-31424-7_51).
The Oxford University Research Archive
[record](https://ora.ox.ac.uk/objects/uuid:292e6279-40b6-4f9c-a11a-e6e1723b64e1)
states that APEX translates open probabilistic programs into automata,
checks equivalence, and uses it to verify anonymity and termination properties
of randomized protocols. Kiefer et al. 2011 explicitly identify obliviousness
and anonymity as properties suited to equivalence checking. Thus the general
idea “compare probabilistic behaviors to verify a security property” predates
OrchLang. The domain-specific application here is equality of an LLM workflow's
selected request or token-usage observations under a declared finite kernel.

Nathanaël Fijalkow, Stefan Kiefer, and Mahsa Shirmohammadi, “Trace Refinement
in Labelled Markov Decision Processes,” *Logical Methods in Computer Science*
16(2), 2020, pp. 10:1–10:28, DOI
[10.23638/LMCS-16(2:10)2020](https://doi.org/10.23638/LMCS-16(2:10)2020),
[full text](https://lmcs.episciences.org/6528/pdf), defines the trace
probability assigned to every finite label word and studies equivalence and
refinement for labelled Markov chains/decision processes. It is strong prior
art for finite trace-law semantics. Its MDP refinement problem is broader in
control and different in statement from the fixed-kernel, paired-secret
analysis here; cite it for the trace-equivalence foundation, not as an exact
match to OrchLang's checker.

## Manuscript-ready related-work/method paragraph

> Equality of probabilistic behaviors is a long-standing verification
> technique: APEX translates open probabilistic programs to automata and uses
> equivalence checking for properties including anonymity and termination,
> while probabilistic-automata and labelled-Markov-chain work establishes
> linear-algebraic equivalence methods for finite words [Tzeng 1992; Kiefer et
> al. 2011, 2012; Fijalkow et al. 2020]. Rational weighted-automata work
> supplies a direct exact-arithmetic setting [Kiefer et al. 2013]. OrchLang
> specializes these established methods to
> a finite rational model of successful LLM calls. Its emitted symbols encode
> the selected ordered usage observation (resolved contract and token
> counts), and its terminal observation distinguishes stopping from a live
> prefix. An exact rational span check compares the resulting word-probability
> series for the selected secret scenarios. This is a software specialization
> with a replayable certificate, not a new general equivalence algorithm or a
> statement about real-provider distributions.

The bracketed bibliography citations should be replaced by the manuscript's
numeric references. Keep the success-only kernel, fixed inputs/scenarios,
finite model, selected observer, and absence of a provider claim explicit.

## One external workflow checked: IBM PDL PDF RAG query

The one source case inspected for this review is IBM Prompt Declaration
Language's pinned
[`examples/rag/pdf_query.pdl`](https://github.com/IBM/prompt-declaration-language/blob/44a1383f2869afdf69a5bc96954af39490399a3f/examples/rag/pdf_query.pdl)
at commit `44a1383f2869afdf69a5bc96954af39490399a3f`, SHA-256
`f252382caf69042fc1d8865753325a4e3c7460012581a6bf5ed56785c9a611ad`.
The repository's pinned license is Apache-2.0:
[`LICENSE`](https://github.com/IBM/prompt-declaration-language/blob/44a1383f2869afdf69a5bc96954af39490399a3f/LICENSE).
The file asks two fixed questions, retrieves passages from the local RAG
collection, generates an answer for each, and joins the outputs. Its paired
[`rag_library1.pdl`](https://github.com/IBM/prompt-declaration-language/blob/44a1383f2869afdf69a5bc96954af39490399a3f/examples/rag/rag_library1.pdl)
and [`rag.py`](https://github.com/IBM/prompt-declaration-language/blob/44a1383f2869afdf69a5bc96954af39490399a3f/examples/rag/rag.py)
show embedding calls, a retry path, Milvus retrieval, and passage assembly.

The current P08 fixture preserves only two answer-call positions with supplied
retrieved passages. It replaces prompts with authored neutral text and adds
authored labels, bounds, secret routing, and mutations. It excludes the
embedding call, library execution, retry, database and retrieval semantics,
context/wire assembly, and array rendering. The upstream questions are fixed
public constants; this source does not define a secret-controlled route, and
the RAG database is not the evaluated data. The adaptation is useful evidence
that the repository contains this workflow shape, but it is not an execution
or security finding about IBM's example, does not establish usage-accounting
accuracy, and does not add independent application-impact evidence. A route or
secret assignment in the fixture is an OrchLang-authored experiment.

The parent-owned workflow catalog had a stale organization URL spelling
(`IBM/PromptDeclarationLanguage`). The working pinned repository path uses
`IBM/prompt-declaration-language`; source hashes and commit are unchanged.
