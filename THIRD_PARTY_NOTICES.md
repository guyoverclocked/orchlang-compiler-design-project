# Third Party Notices

The core compiler uses the C++17 standard library and the host C++ compiler and
`make`. It contains no third-party parser generator, model/network SDK, or copied
compiler implementation. Research scripts use Python's standard library.

The authored bounded projections in `bench/sourced/` re-express call/control
patterns from pinned examples in IBM PDL (Apache-2.0), APPL (MIT), and LMQL
(Apache-2.0). They do not copy upstream program implementations or prompt
passages. Exact source URLs, revisions, source-file hashes, licenses, retained
features and exclusions are recorded in `bench/sourced/manifest.json`.
`research/workflow_patterns.csv` also catalogs LangGraph examples (MIT) as
candidate sources; those are not executed ports. Upstream copyright and
licensing are unaffected by OrchLang's MIT license.

The presentation builder uses OpenAI's bundled Artifact Tool. Historical
submission generators used document/presentation packages listed in their
package metadata. These are development/output dependencies, not compiler
runtime dependencies. ArchiveGate was used as the supplied presentation-style
reference; its original deck is not redistributed in this repository.

The supplied Compiler Design planning document was read as background for the project context. No source code, grammar implementation, diagrams, or report text were copied from it into the compiler implementation.

The 0.5.0rc2 publication corpus retains unchanged public-source files under
`output/publication_upgrade/corpus/sources/`. Each repository snapshot has its
upstream LICENSE and README, and the repository/source manifests identify the
owner, immutable commit, GitHub API SPDX label and exact file hashes. The 12
projects carry MIT or Apache-2.0 labels in that frozen API record. Their files
retain their own upstream licenses and are not relicensed by OrchLang's MIT
license. The SPDX selection replay is an eligibility audit, not legal advice
or a legal verification of every file.

The publication measurement scripts optionally use MIT-licensed `tiktoken`
0.12.0 and its public BPE encoding data; versions, vocabulary/cache hashes and
source URLs are recorded by the calibration report and cache README. They also
use Matplotlib 3.10.8 for scientific figures, under Matplotlib's own license.
These are research/build dependencies, not dependencies of the analysis wheel.
The pinned optional LangGraph runtime and its transitive packages retain the
licenses of those packages and are identified by the integration lockfiles.

The frozen version-1 trace report fixture was extracted from the audit evidence
provided by the project author; its original archive member names and hashes
are recorded beside the fixture. It is used only for compatibility replay.
