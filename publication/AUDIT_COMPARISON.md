# Frozen comparison, 24 October 2026

The original checkout remains on `research/defensible-publication` at
`cef4772d1568af0b0042d97dcff6c396e8d95a52`. Its eleven untracked review-3 files
are included in `evidence/disk-before.json`. No pull, checkout, merge, reset or
source edit was performed in that original directory.

The remote main branch remains `460bf3a453879618a86916ca6540bbf6b4f0e21c`.
The incoming research branch is `claude/trusting-clarke-c7eqeh`, frozen at
`9134aaea780d14d53eedb7423df6ad6f727c9599`. The two research versions have a
common main-branch base and diverge by 20 incoming versus three disk commits.
The incoming branch archives the older main version under `legacy/v1`; it
does not contain the disk branch's subsequent scientific revision.

## Freshly reproduced evidence

* Disk: 106 C++ tests, 82 Python tests without skips, four Lean files and 223
  core-runner commands pass. Fresh Linux ASan/UBSan validation passes 44 commands.
* Disk: ordered precision repeats 64/80 source accepts versus 8/80 historical;
  64/72 core accepts versus 8/72; 3,648 contexts, no accepted supplied-kernel
  counterexample. These are development grammars, not application frequencies.
* Disk: aggregate decision repeats 28/256 accepts versus 16 ordered accepts;
  its twelve gains intentionally change ordered observations. The private-result
  extension repeats 512 contexts/2,048 paths without disagreement.
* Disk: exact accounting repeats 5,344 text and 8,996 concatenation observations,
  40 supported of 64 finite configurations, 128 supported paths, no bound
  violations. All four compiled mutants are detected.
* Disk: captured-outcome replay passes 24/24 comparisons and 44 exact requests
  in the documented optional environment. A first attempt in the tokenizer-only
  environment passed 20/24 and failed four routing cases because Pydantic was
  absent. Both attempts are retained. No new inference was performed here.
* Incoming: ShapeCore checks without admitted proofs; its printed dependencies
  are propext/Quot.sound. The mock differential campaign repeats 1,000 programs,
  5,000 validator checks, and 16,000 trace/store comparisons across four strategies.
  Unit discovery runs eleven tests, with two model-dependent skips in this audit.
* Incoming retained main evaluation: seven completed workflows, 962 paired inputs,
  1,924 executions, 2,028 original and 2,964 shaped model events. Every paired saved
  output/store agrees; every full shaped trace, including tool names, agrees with
  its Lean shape. No recorded input truncation. CRAG, adaptive RAG and Qwen
  replication are absent. Main evaluation coverage is 962/1,172 planned pairs
  (82.1%); including 512 replication pairs it is 962/1,684 (57.1%).
* Incoming raw census recount: 72 rows; 54 application workflows; 37 coded as
  content-dependent. Coding validity and representativeness are separate issues.
* Incoming seven-workflow aggregation was rerun with pinned NumPy 2.5.4 and
  scikit-learn 1.9.1. Results are in `evidence/incoming-analysis/`, separate from
  the source. Median original decision balanced accuracy is about 95%, but the
  switch is at chance. Weighted cost median is 1.83x, range 1.13x--14.47x;
  unweighted token median is about 2.1x. No permutation p-values were computed.

## Confirmed boundaries and required repairs

1. Incoming runtime does not validate backend returned output lengths against
   the expected padding shape. An accepted program with a nonconforming backend
   emits output counts 1 versus 2 without rejection. This refutes the prose
   claiming runtime conformance checks on every call, not the conditional Lean
   theorem. See `audit_probes.py` and `evidence/incoming-boundary-probes.json`.
2. Incoming source binding still trusts Python lowering and the supplied secret
   list. Forgetting a label alone is rejected; forgetting both the label and
   supplied secret list admits an unpadded leaky program. The ordinary public
   helper also defaults the secret list to empty. Shaping alone can be untrusted;
   the whole frontend cannot be described as removed from the trusted base.
3. Incoming runtime can silently truncate an oversized input and change its
   output. Its per-piece input sizing and scalar caps are not a sound cross-unit
   token theorem: text counted as one BERT token yields a 259-token GPT-2 request where
   the computed target is 18. Exact execution targets and sound source bounds
   must be named separately. The disk accounting module already makes this
   distinction and supplies explicit byte contracts for a supported tokenizer.
4. Incoming generated paper tables summarize only the switch (210 pairs), while
   the abstract describes nine workflows. Mutation macros are stale (201/89/11
   versus retained 210/103/12). Finalizing numbers does not fix stale prose.
5. Incoming record resumption skips by input ID and overwrites compile.json
   without checking source/model/config/data fingerprints. Add immutable custody
   and resume guards before extending campaigns. No contamination of the retained
   seven-workflow records was established by this audit.
6. Attack features drop tools although the stated observer and Lean shape include
   tool names. Full-trace conformance passed; attacker features should match that
   observer. Derived weak baselines must remain labeled as counterfactuals.
7. Isolated padding is a trusted serving/telemetry mechanism. It evaluates filler
   separately and reports its count as part of a logical call. That is not a
   demonstrated hosted-provider invoice. Output-token IDs, decoded text, errors,
   caching and visible subrequests require explicit correspondence obligations.
8. The root v2 language changes the meaning of secret: the model is trusted with
   content. It omits v1's integrity policy and is not a replacement for prohibiting
   credentials from reaching prompts. The two software judgments must stay distinct.

The older remote `codex/scp-strengthening` branch is a third, separate research
line with cyclic graphs, rational/uncertain finite laws, and a Rocq refinement.
It reports zero whole-file admissions in both external cohorts. Its standard
reproducer fails Windows raw-byte custody with autocrlf enabled; a fresh LF
checkout passes the initial Python stages but reaches a Unix-only `resource`
import in capsule tests. Neither failure falsifies its mathematical claims.
Its Rocq proofs and full integration were not independently rebuilt in this audit.

## Prior-art assessment

The following primary sources were checked during this audit. Claims below are
the audit's comparison, not priority assertions or a systematic-review guarantee.

* [Ngo et al., S&P 2017](https://www.cs.cmu.edu/~janh/assets/pdf/NgoDFH16.pdf):
  IFC, resource analysis and automatic constant-resource repair already combine.
* [RelCost, POPL 2017](https://www.cs.cmu.edu/~janh/papers/CicekBGGH17.pdf),
  [monadic relational cost, POPL 2018](https://people.mpi-sws.org/~dg/papers/popl18.pdf),
  [Raising Expectations, ICFP 2020](https://arxiv.org/abs/2006.14010), and
  [eRHL v2](https://arxiv.org/html/2407.17127v2) preclude generic novelty claims
  for relational/probabilistic resource reasoning.
* [FaCT](https://cseweb.ucsd.edu/~dstefan/pubs/cauligi%3A2019%3Afact.pdf) is a
  close language/compiler precedent; [Wang et al., USENIX 2014](https://www.usenix.org/conference/usenixsecurity14/technical-sessions/presentation/wang_tao)
  already studies deterministic supersequence defenses; [Pacer](https://www.usenix.org/conference/usenixsecurity22/presentation/mehta)
  is an important deployment/traffic-shaping precedent.
* [Time Will Tell](https://arxiv.org/abs/2412.15431) establishes token-count
  leakage and proposes padding. [Chen 2026](https://arxiv.org/html/2610.09981)
  directly addresses sensitive-topic leakage from routing metadata. The threat
  itself is established prior art; a multi-call compiler is a possible extension.
* [SICC](https://arxiv.org/html/2609.26076) compiles a policy-relative communication
  channel; [Dangol](https://arxiv.org/html/2606.07150) addresses communication-graph
  metadata and cover traffic. Formal comparison must distinguish authorized
  message content/form, transport traffic, and exact logical usage observations.
* [CaMeL](https://arxiv.org/abs/2503.18813), [FIDES](https://arxiv.org/html/2505.23643),
  [PC2](https://arxiv.org/html/2610.28484v1), and Hard-KLAIM are close assurance
  precedents, not interchangeable empirical baselines. The locally supplied
  Hard-KLAIM full-text extraction was available, including Theorems 1--2:
  provenance/authority trace safety is distinct from equal resource distributions.
* [Token Budgets](https://arxiv.org/abs/2606.04056),
  [Costwright](https://github.com/eleata/costwright),
  [Typed Resources](https://github.com/eleata/typed-resources), and
  [Loom](https://loom.technology/research/bounded-llm-cost/) overlap with resource
  contracts, caps, and sound bounds. Their external proofs were not rebuilt here.

The defensible combined contribution is a specialized, executable bridge from
usage-trace shaping to explicit accounting and execution contracts, with a small
mechanized validator and auditable empirical evidence. Most component techniques
are established. Stronger novelty requires a precise useful delta and fair
comparison; adding modules or test counts alone does not create it.

## Publication assessment before unification

Neither frozen manuscript is ready for submission. The disk version is a scoped
software candidate with comparatively strong custody and limited usefulness
evidence. The incoming version has a stronger security-method narrative and a
larger retained evaluation, but has the concrete gaps above and unfinished data.
The user subsequently selected Science of Computer Programming for a combined
revision, implemented separately in `unified-publication/`.

[SCP's official scope](https://shop.elsevier.com/journals/science-of-computer-programming/0167-6423)
includes programming-language design/implementation/evaluation and an Original
Software Publication track. [STTT](https://link.springer.com/journal/10009/aims-and-scope)
emphasizes realistic tool use. [JORS](https://openresearchsoftware.metajnl.com/about)
requires research-software reuse and archival availability. [PoPETs](https://petsymposium.org/cfp27.php)
is a privacy journal route for a completed security evaluation, not a software
fallback. [Programming](https://programming-journal.org/cfp/) explicitly asks
engineering submissions for a better accepted baseline. [JOSS](https://joss.readthedocs.io/en/latest/submitting.html)
currently requires more than six months of public development and demonstrated
research impact; eligibility is not established. Current detailed SCP/SoftwareX
guides and ACM TOPS pages returned 403, so exact present fees and administrative
requirements are not asserted. No acceptance probability is justified.

All new audit outputs, environments and checkouts are under this audit directory.
API expenditure and new model inference for the audit phase are both zero.
