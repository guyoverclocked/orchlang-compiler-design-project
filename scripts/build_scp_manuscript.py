#!/usr/bin/env python3
"""Fill the publisher's OSP template without changing its formatting settings.

Bibliography is inline: the editable manuscript is a standalone LaTeX file.
Author declaration/contact/release fields remain explicit until factually filled.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
ROOT=Path(__file__).resolve().parents[1]
cli=argparse.ArgumentParser(description=__doc__)
cli.add_argument('--release-url', help='verified immutable public software revision URL, after candidate freeze')
args=cli.parse_args()
manifest=json.loads((ROOT/'audit/final/manifest.json').read_text())
if manifest.get('status')!='passed' or manifest.get('quick') or not all(
    manifest.get(key) for key in ('sanitizer_requested','packaging_requested','optional_langgraph_requested','inputs_unchanged_during_run')):
    raise ValueError('The manuscript requires a complete, frozen sanitized/package/LangGraph reproduction.')
bound={}
for key,value in manifest.items():
    if key.endswith('_sha256') and isinstance(value,dict):
        for name,digest in value.items():
            if name in bound and bound[name]!=digest:
                raise ValueError('Inconsistent manifest binding: '+name)
            bound[name]=digest
for name,digest in bound.items():
    path=ROOT/name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise ValueError('Stale manuscript evidence/source: '+name)
trace_study=json.loads((ROOT/'bench/results/trace_equivalence.json').read_text())
if trace_study.get('status')!='passed' or trace_study.get('failures'):
    raise ValueError('Exact trace-equivalence evidence has not passed.')
trace=trace_study['summary']
trace_equal=trace['producer_decision_counts'].get('proved_equal',0)
trace_unequal=trace['producer_decision_counts'].get('unequal',0)
if trace_equal+trace_unequal!=trace['fixture_count']:
    raise ValueError('The manuscript requires complete decisions on the finite trace-law corpus.')
template=(ROOT/'submission/research/journal_templates/scico-osp-template.tex').read_text()
header=template[:template.index('\\begin{document}')]
front=r'''
% Change only the stock submission wording; retain its font and placement.
\makeatletter
\patchcmd{\ps@pprintTitle}{Preprint submitted to}{Manuscript prepared for}{}{\PackageError{orchlang}{Could not replace the draft footer wording}{}}
\makeatother
\begin{document}
\begin{frontmatter}
\title{OrchLang: Replayable Contracts for Token Usage and Request-Equivalent LLM Workflows}
\author{Nambi Rajan M\corref{cor1}}
\address{Affiliation and postal address to be confirmed by the author}
\cortext[cor1]{Correspondence details await author confirmation. Research draft, 9 October 2026; not submitted.}
\begin{abstract}
Equal token budgets do not establish that a language-model workflow's usage is independent of private routing. OrchLang is offline research software that separates bounded accounting, request equivalence, and model-specific usage distributions. Its C++ compiler resolves typed requests and dependent results; a graph checker supports productive cycles and independently replayed product certificates. Rational-kernel tools quantify finite usage leakage, check sufficient stochastic bisimulation, and decide ordered trace-law equality at every finite horizon by exact linear algebra. Equality certificates and finite inequality witnesses are independently replayed. Narrow source bridges connect admitted OrchLang and Python LangGraph programs to replay-gated execution. Fifteen balanced source projections are admitted, versus eight by the preceding compiler. Independent bounded semantics find no accepted difference in 13,824 secret comparisons; exact channel analysis agrees with independent enumeration in 260 comparisons. An authored equal-law example resolves a bisimulation-inconclusive case. The contribution specializes established relational and probabilistic methods in an inspectable software pipeline. Guarantees require declared accounting and successful-outcome assumptions; provider invoices, unrestricted framework translation, termination and whole-cycle budgets are outside its scope.
\end{abstract}
\begin{keyword}
static analysis \sep confidentiality \sep token accounting \sep probabilistic verification \sep research software \sep reproducibility
\end{keyword}
\end{frontmatter}
'''
body=r'''
\section{Motivation and significance}
A private flag may select one model call on either of two public inputs bounded by the same token cap. Equal worst-case budgets do not prevent their concrete input lengths from revealing the flag. Conversely, different requests can have the same usage law under a particular stochastic model. These distinctions matter when a per-run observer sees usage records and knows the public context.

Constant-resource typing and relational cost analysis already study information flow through resource use~\cite{ranif,relcost}. PPDL models uncertain flows with multiple language-model calls and uses token budgeting~\cite{ppdl}; quantitative information flow supplies vulnerability and entropy measures~\cite{smith,symbolic}. OrchLang specializes these established methods. Its software retains resolved model identity, exact typed requests, corresponding earlier outcomes, source provenance and independently checked evidence for a declared usage observer. Researchers can compare conservative checks valid for any admitted outcome oracle with precise examples under one stochastic model. External adoption and practical impact are unmeasured.

\section{Software description}
\subsection{Software architecture}
The C++17 compiler performs lexing, parsing, scoped resolution, flow-policy checking, cost analysis, relational analysis, dependency-graph generation, certificate emission and offline execution. The bounded source language supports calls, branches, literal-bounded retries, outputs, effects and explicit releases; it has no unbounded loop or concurrency. Sequence adds token-bound components, branches take componentwise maxima and retries multiply bounds. Saturation and invalid runtime inputs fail closed.

A separate Python graph frontend handles ordered calls, mutable result registers, scalar guards and productive cycles. Its product state $(pc_L,pc_R,R)$ tracks two control positions and a sufficient equal-value relation. Secret choices generate universal obligations; aligned public guards require equal subjects and predicates. Calls require equal resolved contracts, templates and ordered typed literals or related values. Assignment removes stale result relations before adding the new pair. Finite closure closes repeated product states; stops must match and reachable call-free cycles reject. A separately implemented replayer reconstructs the complete rooted closure without importing the producer.

Two narrow adapters export bounded OrchLang source and static Python LangGraph source. Contracts supply input labels, bounds and model declarations; the Python AST supplies calls and control. Unsupported effects, dynamic syntax, reducers and parallel edges reject. The AST adapter checks LangGraph's atomic returned-state updates before lowering them to sequential registers. An actual pinned LangGraph backend requires independent certificate replay and executes bounded offline sessions. Immutable source and compiler snapshots bind translation evidence through recorded digests. The translation guarantee is limited to the documented subsets and finite differential checks.

\subsection{Software functionalities and assumptions}
The resolved contract contains provider, model identifier, output cap and optional nominal binary64 price metadata. The abstract request contains exact template bytes and ordered typed atoms or full argument values. Provider envelopes, tokenizers, hidden system messages, caches and account state are absent. Bounds require compatible argument units, cap-respecting outputs and full modeled input usage bounded by the declared additive UTF-8 estimates. Price metadata is not an exact currency theorem.

A shared complete-outcome oracle keyed by contract, per-contract ordinal and request gives corresponding equal outcomes; retries also require coupled success events. Under equal public inputs, admitted bounded workflows without declassification have equal modeled request and usage traces. Productive graph cycles have matching finite prefixes and stop positions; they need not terminate or have a finite total budget. Explicit-data labels permit dependent calls under matched private control, while effective labels still enforce output/effect policies. Declared releases withhold the unrestricted secrecy guarantee.

For model-specific analysis, users declare a finite rational kernel indexed by contract, ordinal, exact request and the last zero to four complete outcome events. Exact dynamic programming retains all future-relevant values, control, ordinals, observation and history. Identical states merge probability mass. A completed histogram must have mass exactly one; caps produce unknown without partial-safe conclusions. The tool reports exact total variation and Bayes vulnerability, and symbolic mutual information with approximate logarithm displays. The channel covers selected secret assignments, a fixed public store, successful calls and integer usage; it excludes errors and real-provider probability fitting.

An additional finite semantic transducer omits accumulated usage and history-independent work counters. It saturates ordinals at 33: every literal ordinal/history test in kernel version~1 is at most 32. Finite outcome support, fixed inputs and bounded complete history therefore give a finite reachable state system. Exact partition refinement groups states with the same terminal class and distribution over visible usage labels and successor blocks, following established probabilistic bisimulation~\cite{bisim}. Equal initial blocks imply equal ordered success-only usage laws at every finite call horizon. Split blocks are inconclusive, not leakage witnesses. This result excludes cumulative runtime resource monitors and any infinite-run or total-cost claim.

For a stable partition $\mathcal{P}$, each pair $s,t$ in a block satisfies, for every visible label $\ell$ and target block $B$,
\begin{equation}
\sum_{u\in B}P(s,\ell,u)=\sum_{u\in B}P(t,\ell,u).
\end{equation}
Terminal status also agrees. Induction on the remaining horizon gives equal trace laws. The independent replayer reconstructs transitions and checks this equation using exact rational arithmetic.

Because strong bisimulation is incomplete for observable-law equality, an exact trace-equivalence tool applies established weighted-automaton span reasoning~\cite{tzeng,langeq,qweighted}. APEX previously used program-to-automata equivalence for anonymity and other probabilistic properties~\cite{apex}. For each selected secret scenario $i$ against scenario~0, let $\mu_i=e_i-e_0$, $A_\ell$ be the rational transition matrix for a visible usage label, and $b_S,b_N$ indicate stopped and nonterminal states. Equality holds exactly when
\begin{equation}
\mu_i A_w b_S=\mu_i A_w b_N=0\quad\mbox{for every finite word }w.
\end{equation}
The implementation explores a rational basis for reachable rows $\mu_i A_w$. A closed basis annihilating both columns certifies equality; a nonzero output gives a finite word with exact differing probabilities. Independent replay reconstructs the system, word rows, span closure and both outputs. Work, matrix-entry and precision caps give unknown without a partial decision. Completeness concerns the supplied finite model and listed inputs; provider premises and infinite-run properties remain excluded.

\subsection{Installation and use}
Core compilation needs \texttt{make} and C++17; the audit tools use Python~3.10+ and the standard library. Checking and replay are available in a wheel tested from an isolated directory. LangGraph execution is optional, pinned to version~1.2.14 with a dependency lock~\cite{langgraph}. No provider key, paid call or real tool execution is needed.

\begin{verbatim}
make check
./orchc check \
  examples/research/accepted/chain_matched.orch
python3 audit/orchgraph.py GRAPH --report CERTIFICATE
python3 audit/replay_graph_certificate.py GRAPH CERTIFICATE
python3 audit/reproduce_final.py --sanitize --package
\end{verbatim}

The reproduction manifest records code/result hashes, commands, outcomes and environment. Optional integration execution requires its pinned environment and is recorded separately. Documentation specifies each subset and theorem boundary, negative cases, provenance and unknown outcomes. A closing HTML demonstration runs the real local tools, with any saved-evidence fallback explicitly labeled. AI-assisted development and adversarial review used Codex and GPT-6 Luna; tools also assisted literature checking, test generation and drafting. The human author must review implementation, sources and disclosures before submission.

\section{Illustrative examples}
Matched private alternatives can each call a model on the same public query and then on the corresponding earlier result. The first requests agree; coupled outcomes agree; the second requests agree. This now passes, while changing the template, model contract or outer argument fails. Boolean \texttt{true} and text \texttt{"true"} are distinct request atoms; an audit found and repaired their earlier collision.

A quantitative example gives output usage 1 or 3 with equal probability in one arm, and deterministic usage 2 in the other. Both means are 2, but total variation is 1: the observation identifies the private arm. Another emits $(1,3)$ versus $(3,1)$. Its aggregate totals coincide while ordered usage laws are disjoint. A noisy example with probabilities $3/4$ versus $1/4$ has total variation $1/2$ and posterior Bayes vulnerability $3/4$ under a uniform binary prior. These synthetic cases show why observer choice and the complete conditional law belong in the contract; they do not estimate a provider.

An additional example samples a hidden first response with the same visible usage. One private arm chooses deterministic second usage from that response; the other uses the same marginal mixture. Both ordered laws agree. Strong bisimulation splits their states; exact span checking proves equality, showing a concrete precision improvement.

\section{Impact and validation}
The artifact enables reproducible experiments on relational precision, source translation, stochastic usage observations and evidence trust. It improves the project's original conservative checker and provides executable examples for compiler teaching. There is no independently documented external deployment, commercial impact or user-count claim.

Table~\ref{tab:evidence} summarizes distinct evidence families. The 15 source patterns are partial author-created bounded projections of pinned PDL/APPL/LMQL files, with omissions and mutations recorded. The identical balanced files are compared against immutable baseline revision \texttt{a49fcdbd}. These are not complete framework ports or held-out benchmarks. The two deterministic oracle modes repeat the same corpus and are reported separately.

\begin{table}[ht]
\centering
\begin{tabular}{lp{8cm}}
\hline
Evidence & Recorded result \\
\hline
Compiler regression & 112 tests; ASan/UBSan and examples pass \\
Source precision & 8/15 baseline admissions versus 15/15 current \\
Bounded stress & 13,824 accepted secret comparisons; no request or usage difference \\
Cyclic graph fixtures & Six accepted proofs replay; eight rejected fixtures have finite witnesses \\
Bounded source bridge & 17/20 exports; 720 differential run pairs agree; three retry exclusions \\
Actual LangGraph backend & 888 runs and 4,528 call-event pairs agree; 24 call-cap prefixes \\
Actual Python source & 30 accepted trace pairs and six rejected value probes agree \\
Finite stochastic study & 11 kernels, 130 analyses, 260 exact independent histogram comparisons \\
Stochastic closure & Five equality proofs and six inconclusive cases; all 11 independently replay \\
Exact trace equivalence & @@TRACE_CASES@@ cases: @@TRACE_EQUAL@@ equality proofs and @@TRACE_UNEQUAL@@ finite witnesses; all independently replay \\
\hline
\end{tabular}
\caption{Offline evidence families; repeated inputs/seeds are not independent applications.}
\label{tab:evidence}
\end{table}

The bounded full-text interpreter shares its generated AST with source rendering but imports no compiler/runtime facts. Of 120 negative stress cases it witnesses 117; three retry mutations remain unknown on the finite grid. The graph value probe shares producer normalization, while structural replay is separately written. Source/graph interpretation shares the source parser, so it is finite translation evidence. The actual source study uses authored restricted Python functions; 20 frontend tests include stale-attestation invalidation.

The quantitative DP agrees with independently parsed no-merge enumeration in all 260 comparisons. Seventeen slices have equal expected usage but positive total variation; all 11 state-cap probes remain unknown. All 130 saved reports independently replay at explicit limits of one million paths, ten million work steps and one GiB byte work. At the default 64 MiB limit, one largest trace case remains unknown. Producer counters and approximate logarithms are excluded from replayed facts.

The stochastic closure study yields five equality proofs and six inconclusive cases. All 11 certificates replay independently. The proved cases also pass 60 DP checks at horizons 1, 2, 4, 8, 16 and 32 with both observers, covering 120 unit-mass scenario histograms. All 11 fresh state-cap certificates and attestations remain unknown. These checks corroborate implementation behavior. Partition stability supports the result for every finite horizon under the declared model; neither the tests nor replay validate a provider.

The exact trace-law corpus adds the equal-but-non-bisimilar example to those eleven models. All @@TRACE_CASES@@ decisions independently replay. Equality cases pass @@TRACE_DP@@ finite DP checks; all @@TRACE_UNEQUAL@@ finite witness probabilities agree with DP. All @@TRACE_CASES@@ fresh cap probes remain unknown, and @@TRACE_CASES@@ semantic report mutations reject. The span certificate, rather than sampled horizons, supports all-finite-horizon equality.

\section{Conclusions}
OrchLang makes the boundary between a token ceiling, request equivalence and usage-law equality explicit in runnable software. Typed request identities, dependent results, productive cycles, source provenance and independent checks give a stronger inspectable artifact than its preceding bounded demo. The contribution is a focused specialization of established relational and probabilistic methods. Provider accounting validation, independently reused applications, mechanized soundness and richer framework extraction remain future work.

\section*{Declaration of generative AI and AI-assisted technologies}
Codex and GPT-6 Luna assisted implementation, testing, adversarial review, literature investigation and manuscript drafting. This draft records their use. The human author's review, edits and responsibility statement must be completed before submission; this text does not assert that approval has occurred.

\section*{Author completion and availability}
The author must confirm authorship, affiliation, correspondence, CRediT roles, funding and competing interests. The MIT-licensed repository~\cite{orchlang} supplies code, manuals and generated offline evidence. An immutable public release link must be supplied after candidate freeze. No DOI or editorial acceptance is asserted.
'''
metadata=template[template.index('\\section*{Metadata}'):template.index('\\section{Motivation and significance}')]
metadata=metadata.replace('This ancillary data table is required for the sub-version of the codebase.\nPlease replace the text in the right column with the correct information\nabout your current code and leave the left column untouched.','Candidate metadata; public immutable release and support contact await completion.')
metadata=metadata.replace('For example v42','0.5.0-rc1 (research candidate)')
metadata=metadata.replace('Please fill in this column','Value')
metadata=metadata.replace('For example: $https://github.com/mozart/mozart2$',r'\href{https://github.com/guyoverclocked/orchlang-compiler-design-project}{\texttt{https://github.com/}\newline\texttt{guyoverclocked/}\newline\texttt{orchlang-compiler-design-}\newline\texttt{project}}; immutable candidate link pending')
metadata=metadata.replace('C3  & Permanent link to Reproducible Capsule & \\\\',r'C3  & Permanent link to Reproducible Capsule & No hosted capsule assigned; local reproduction manifest supplied \\')
metadata=metadata.replace('List one of the approved licenses','MIT')
metadata=metadata.replace('For example svn, git, mercurial, etc. put none if none','Git')
metadata=metadata.replace('For example C++, python, r, MPI, OpenCL, etc.','C++17; Python; optional LangGraph 1.2.14; HTML/JavaScript demo')
metadata=metadata.replace('C7 & Compilation requirements, operating environments and dependencies & \\\\',r'C7 & Compilation requirements, operating environments and dependencies & C++17, make, Python 3.10+; optional locked LangGraph environment \\')
metadata=metadata.replace('For example: $http://mozart.github.io/documentation/$',r'Repository \texttt{docs/}: installation, contracts, reproduction, user/developer notes')
metadata=metadata.replace('C9 & Support email for questions & \\\\',r'C9 & Support email for questions & To be confirmed by corresponding author \\')
metadata=metadata.replace('\\label{}','\\label{tab:metadata}',1).replace('\\label{}','\\label{tab:code_metadata}',1)
if args.release_url:
    prefix='https://github.com/guyoverclocked/orchlang-compiler-design-project/tree/'
    if not args.release_url.startswith(prefix) or not re.fullmatch(r'[0-9a-f]{40}',args.release_url[len(prefix):]):
        raise ValueError('release URL must identify an exact 40-hex commit in the software repository')
    commit=args.release_url[len(prefix):]
    metadata=metadata.replace(r'\href{https://github.com/guyoverclocked/orchlang-compiler-design-project}{\texttt{https://github.com/}\newline\texttt{guyoverclocked/}\newline\texttt{orchlang-compiler-design-}\newline\texttt{project}}; immutable candidate link pending',
        r'\href{'+args.release_url+r'}{Immutable Git revision}\newline\texttt{'+commit[:20]+r'}\newline\texttt{'+commit[20:]+r'}')
    body=body.replace('An immutable public release link must be supplied after candidate freeze.',
        'The exact public software revision is recorded in the metadata table.')
refs=r'''
\begin{thebibliography}{12}
\bibitem{ranif} V.C. Ngo, M. Dehesa-Azuara, M. Fredrikson, J. Hoffmann, Verifying and synthesizing constant-resource implementations with types, IEEE Symposium on Security and Privacy (2017). \url{https://doi.org/10.1109/SP.2017.53}.
\bibitem{relcost} E. \c{C}i\c{c}ek, G. Barthe, M. Gaboardi, D. Garg, J. Hoffmann, Relational cost analysis, POPL (2017) 316--329. \url{https://doi.org/10.1145/3009837.3009858}.
\bibitem{ppdl} L. Mandel, G. Baudart, M. Vaziri, M. Hirzel, PPDL: LLM-based flows as probabilistic programs, ICML, PMLR 306 (2026) 86172--86197. \url{https://proceedings.mlr.press/v306/mandel26a.html}.
\bibitem{smith} G. Smith, On the foundations of quantitative information flow, FOSSACS (2009). \url{https://doi.org/10.1007/978-3-642-00596-1_21}.
\bibitem{symbolic} P. Schr\"oer, F. Randone, R. Pardo, A. W\k{a}sowski, Symbolic quantitative information flow for probabilistic programs (2024). \url{https://doi.org/10.1007/978-3-031-75783-9_6}.
\bibitem{bisim} K.G. Larsen, A. Skou, Bisimulation through probabilistic testing, Information and Computation 94(1) (1991). \url{https://doi.org/10.1016/0890-5401(91)90030-6}.
\bibitem{tzeng} W.-G. Tzeng, A polynomial-time algorithm for the equivalence of probabilistic automata, SIAM Journal on Computing 21(2) (1992) 216--227. \url{https://doi.org/10.1137/0221017}.
\bibitem{langeq} S. Kiefer, A.S. Murawski, J. Ouaknine, B. Wachter, J. Worrell, Language equivalence for probabilistic automata, CAV, LNCS 6806 (2011) 526--540. \url{https://doi.org/10.1007/978-3-642-22110-1_42}.
\bibitem{qweighted} S. Kiefer, A.S. Murawski, J. Ouaknine, B. Wachter, J. Worrell, On the complexity of equivalence and minimisation for Q-weighted automata, Logical Methods in Computer Science 9(1) (2013), article 8. \url{https://doi.org/10.2168/LMCS-9(1:8)2013}.
\bibitem{apex} S. Kiefer, A.S. Murawski, J. Ouaknine, B. Wachter, J. Worrell, APEX: An analyzer for open probabilistic programs, CAV, LNCS 7358 (2012) 693--698. \url{https://doi.org/10.1007/978-3-642-31424-7_51}.
\bibitem{langgraph} LangChain, LangGraph 1.2.14 [software], Python Package Index (2026), accessed 9 October 2026. \url{https://pypi.org/project/langgraph/1.2.14/}.
\bibitem{orchlang} Nambi Rajan M, OrchLang 0.5.0-rc1 [software candidate], GitHub repository (2026), accessed 9 October 2026. \url{https://github.com/guyoverclocked/orchlang-compiler-design-project}.
\end{thebibliography}
\end{document}
'''
out=ROOT/'submission/research/manuscript/OrchLang_SCP_OSP.tex'
for token,value in {
    '@@TRACE_CASES@@':trace['fixture_count'], '@@TRACE_EQUAL@@':trace_equal,
    '@@TRACE_UNEQUAL@@':trace_unequal,
    '@@TRACE_DP@@':trace['proved_equal_finite_dp_checks'],
}.items():
    body=body.replace(token,str(value))
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(header+front+body+metadata+refs)
highlights=['OrchLang separates token ceilings from secrecy of usage observations.',
            'Independent replay checks request-product and stochastic evidence.',
            'Exact kernels expose leaks hidden by equal expected usage totals.',
            'Narrow source adapters connect proofs to real LangGraph execution.',
            'Exact finite-state trace laws have replayable proofs and witnesses.']
assert 3<=len(highlights)<=5 and all(len(s)<=85 for s in highlights)
(out.parent/'OrchLang_highlights.txt').write_text('\n'.join('- '+x for x in highlights)+'\n')
abstract=front.split(r'\begin{abstract}',1)[1].split(r'\end{abstract}',1)[0].strip()
running_text=re.sub(r'\\begin\{(?:table|verbatim|equation)\}.*?\\end\{(?:table|verbatim|equation)\}','',body,flags=re.S)
compliance={'abstract_words':len(abstract.split()),'keywords':6,
    'highlights_characters':[len(s)for s in highlights],
    'official_template_header_preserved':(header+front+body+metadata+refs).startswith(header),
    'official_template_class_preserved':r'\documentclass[preprint,12pt, a4paper]{elsarticle}'in header,
    'single_column':True,'source':'official OSP LaTeX template; current guide read 2026-10-09',
    'estimated_running_text_words':len(running_text.split()),
    'suggested_text_pages':'3-6, abstract plus running text; title, authors, affiliations, references, metadata, tables and figures excluded',
    'public_immutable_software_url':args.release_url,
    'reproduction_manifest_sha256':hashlib.sha256((ROOT/'audit/final/manifest.json').read_bytes()).hexdigest(),
    'exact_trace_study_sha256':hashlib.sha256((ROOT/'bench/results/trace_equivalence.json').read_bytes()).hexdigest(),
    'status':'draft; PDF visual QA recorded separately; author facts and approval required',
    'author_actions':['name/affiliation/correspondence','CRediT/funding/conflicts',
        'human review and AI responsibility','submission approval'],
    'unverified_claims':[]}
assert compliance['abstract_words']<=250
(out.parent/'compliance.json').write_text(json.dumps(compliance,indent=2)+'\n')
print(out)
