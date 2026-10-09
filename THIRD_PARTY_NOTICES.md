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
