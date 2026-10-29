# Primary-source access and comparison record

Checked 23 October 2026. Access status is deliberately separate from proof review.
This is a focused comparison, not a systematic review or priority claim.

| Source/version | Inspected evidence | Consequence for OrchLang |
|---|---|---|
| [Ngo et al., IEEE S&P 2017](https://www.ieee-security.org/TC/SP2017/papers/408.pdf) | Open primary PDF, abstract/introduction | Joint resource analysis and IFC, including resource-aware noninterference, already exist. Combining the two is not a new general contribution. Relevant rules/proofs still need detailed encoding comparison. |
| [RelCost, POPL 2017](https://people.mpi-sws.org/~dg/papers/popl17.pdf) | Open PDF, introduction and abstract semantic-model account | Relational versus unary cost reasoning and dependence on similar inputs are established. No claim that stochastic calls make numeric specifications impossible. Full encoding not implemented. |
| [Wang, Kahn, Hoffmann, ICFP 2020](https://www.cs.cmu.edu/~janh/assets/pdf/WangKH20.pdf) | Open PDF abstract; repeat fetch timed out | Probabilistic expected-cost AARA exists and is compositional/parametric in the cost model. Withdraw blanket AARA impossibility. No reproduction of its artifact yet. |
| [Barthe et al., arXiv:1509.03476v2](https://arxiv.org/abs/1509.03476v2) | Primary metadata/abstract | Couplings and mechanized relational probabilistic reasoning are established. Marginals must match the actual kernels. Full relevant rule audit pending. |
| [eRHL, arXiv:2407.17127v2](https://arxiv.org/html/2407.17127v2) | Primary metadata, HTML examples and related-work discussion | Quantitative relational expectations and probabilistic equivalence are existing capabilities. A restricted DSL may improve automation/usability; it does not establish an expressiveness separation. Theorem-level encoding remains pending. |
| [PC2, arXiv:2610.28484v1](https://arxiv.org/html/2610.28484v1) | Metadata, framework summary, Appendix E budget correspondence and Proposition E.1 | Proof-before-operation contracts and reservation/service correspondence are prior art. Late charges and retries require reservations independent of receipts. No novelty claimed for this principle. Not a complete 70-page audit. |
| [Hard-KLAIM, DOI 10.1016/j.jlamp.2026.101191](https://doi.org/10.1016/j.jlamp.2026.101191) | Author-provided 45-page journal pre-proof; sections 3, 6–8, Theorems 1–2 and Appendix A inspected, theorem page visually checked | Typed trace safety, immutable identities, provenance/authority confinement, and an explicit adapter trust boundary already exist. Its principal theorem concerns finite interface traces; ours would concern observer distributions and quantitative bounds under primitive contracts. This is a goal difference, not evidence of superior expressiveness or a completed novel result. |
| [Monadic refinements, POPL 2018](https://www.radicek.com/papers/popl18.pdf) | Primary URL failed | Access/rule comparison unresolved. Do not assert absence of a feature. |
| [SCP scope](https://shop.elsevier.com/journals/science-of-computer-programming/0167-6423), [EAPLS software call](https://eapls.org/news/issues/open-call-for-software-submissions-science-of-computer-programming-software-track-xjw27/) | Primary scope and editor call accessible | Original Software Publication is a plausible route for useful, documented, reproducible software. Novelty, quality and accessibility still matter. Current author-guide/template verification remains open. |

Hard-KLAIM private copy: an author-provided private copy stored outside the source export.
SHA256: `29eecd214dc0fc1f3257c97f5117fb1dc28ade451f43ac3ace57d5f4c82d0cbd`.
Do not commit the PDF or extracted full text. Cover metadata has an apparent
2025 citation-template inconsistency; DOI, acceptance date and publisher record
identify the 2026 pre-proof. Verify final bibliographic year at submission.
Its JANJI-ROCQ artifact is linked at https://github.com/LucaRoversi/JANJI-ROCQ;
it has not been built or independently proof-audited here.

The SCP guide returned HTTP 403 through HTTP tools, but was subsequently read
successfully in the browser on 23 October. See docs/VENUE_CHECKLIST.md and the
official template derivative in docs/manuscript. No paywalled guide is needed.
The current public
[guide](https://www.sciencedirect.com/journal/science-of-computer-programming/publish/guide-for-authors)
is authoritative; a third-party copy is not.

## Narrative decision

The author supplied a one-week deadline on 23 October (target 30 October 2026).
Use a software/reproducibility candidate as the working route. Research novelty
is not established. Existing logics can express the central equal-kernel idea;
the credible candidate contribution is a carefully engineered specialization
with counterexamples, conservative checking, independent falsification and
reproduction. Do not sell observer projection as a new theorem. Do not promise
an SCP-ready package until the release, license and review gates actually pass.

Remaining primary reading includes the full applicable rules of the foundational
logics, Time Will Tell, CaMeL, FIDES and the structural LLM workflow cost report.
The master plan's old access descriptions do not count as new reading.
