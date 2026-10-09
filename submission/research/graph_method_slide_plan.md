# Provisional slide plan: cyclic graph product checker

**Status:** planning note only. The JSON graph checker, formal review, and
independent replay results are not frozen. Keep the current 26-slide deck as a
stable candidate. This plan contains no new evaluation numbers or novelty score.

## Narrative bridge

The current OrchLang compiler analyzes a finite, bounded AST. The proposed
checker is a separate JSON-graph front end; it does not add graph syntax or
cycles to the frozen OrchLang core. Its method should be presented as a
domain-specific application of self-composition/product-program and
bisimulation ideas, not as new general noninterference theory.

The potentially stronger contribution is the complete chain from a cyclic
workflow graph to a paired-execution product, a checkable certificate, and an
independent replay verifier. Do not call that chain proof-producing until the
certificate and verifier have been audited together.

## Four proposed main-deck slides

| Beat | Draft headline | Visual object | Claim boundary / evidence needed |
|---|---|---|---|
| 1. Separate input model | **A cyclic workflow graph is a different input from the bounded DSL** | Two clearly labeled lanes: frozen OrchLang front end → AST checks; experimental JSON graph front end → graph product checker. In the graph lane, draw one call node and a visible back-edge. | State that this is a separate experimental front end. Cite its schema, parser, and a hash-pinned input. Do not imply the frozen DSL gained general loops. |
| 2. Motivating cycle | **A secret can change how many times one call node is visited** | One small graph: secret guard chooses exit or back-edge; show two paired executions. The first equal call event is teal; the extra event on the cycling side is coral/rust. | Use only a graph the final checker accepts/rejects as described. Show no finite total-budget result. The cycle example should be replayed by the frozen checker and verifier before appearing as evidence. |
| 3. Product construction | **The check explores pairs of graph states** | Side-by-side executions fold into product states `(pcL, pcR, R)`. Label `R` as justified equal-register pairs. Show public-guard synchronization, all secret-successor pairs, call descriptor matching/result-pair update, and aligned stop. Use a loop on the product graph rather than a bounded unrolling. | Match the final transition semantics exactly. Explain that billable-cycle acceptance is coinductive and establishes only equality of every finite usage-trace prefix under the declared coupling. No termination or finite aggregate-cost bound follows. Call-free cycles fail closed; resource caps fail closed. |
| 4. Independent replay | **An independent checker can replay the reachable product graph** | Producer → certificate → small replay verifier. The verifier rechecks input identity, reachable product states/edges, local transition obligations, register-pair updates, call-event matches, and cycle handling; then emits accept/reject. | Replace this checklist with the actual certificate fields and verifier checks. Demonstrate tamper rejection and independently reproduced decisions. Do not imply a mechanized theorem or validate the input parser unless the artifact covers those claims. |

## Two proposed appendix slides

1. **Product transition rules and cycle cases.** Give the state tuple, relation
   `R`, public/secret guard rules, call matching and result-register relation,
   stop alignment, call-free cycle behavior, and coinductive billable-cycle
   behavior. Cite exact implementation/formal-spec sections.
2. **Scope of graph-checker guarantees.** Distinguish (a) finite usage-prefix
   equality, (b) termination, and (c) finite total token/cost bounds. State
   which one the checker establishes; list unsupported JSON constructs,
   resource limits, oracle assumptions, and what independent replay does and
   does not verify. Include only final red-team counterexamples and outcomes.

## Presentation structure after validation

Keep the existing deck unchanged until the graph implementation and evidence
are frozen. Then make a new candidate version. A 20-slide main talk can fit the
four method slides by consolidating three pairs of existing material:

- Combine the threat-model and information-flow slides into one path diagram.
- Combine the equal-cap counterexample and its numerical explanation.
- Combine the paired-run coupling and request-signature slides.

Retain the compiler pipeline and current bounded-DSL results as the baseline;
move the graph method before the evaluation section. The two new appendix
slides can fit by combining the current formal-relation/signature appendices
and merging the diagnostics/likely-questions pages, if readability survives.
Do not force these merges if they create dense slides; a longer technical talk
is preferable to shrinking text below the existing design system's limits.

Possible title only after the scope is confirmed: **Relational checking for
cyclic LLM workflow graphs**. Keep OrchLang clearly labeled as the bounded-DSL
baseline and the graph checker as a distinct prototype.

## Freeze gate before editing the final deck

- Final graph schema, normalized node semantics, and input hash are pinned.
- Formal contract agrees with checker, certificate, and verifier.
- The loop counterexample has a source/input artifact and independently
  replayed expected result.
- A separate red team has challenged cycle handling, register relation,
  request identity, and stop/termination cases.
- The verifier replays both accepting and rejecting certificates and fails
  closed under tampering and its resource limit.
- Root freezes experiment denominators and exact claim language.
- Related-work review distinguishes graph product checking from static
  workflow verification and existing relational/resource analyses.

Until then, use no updated novelty score and no publication-fit score. A
coinductive acceptance of a billable cycle must never be described as a finite
worst-case budget guarantee.
