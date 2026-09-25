# Third Party Notices

OrchLang uses only the C++17 standard library and the host C++ compiler and `make` build tool. It includes no third-party source code, parsing generator, package, framework, network SDK, model SDK, database library, or copied implementation material.

The supplied Compiler Design planning document was read as background for the project context. No source code, grammar implementation, diagrams, or report text were copied from it into the compiler implementation.

## Excerpts in the real-workflow corpus (`bench/real/`)

The ports in `bench/real/*.orch` reproduce prompt text verbatim from the
following projects, at the revisions pinned in `bench/real/manifest.json`, so
that the analyses run on the prompts those workflows actually send. Each
project is distributed under the MIT License, whose notice is reproduced here as
that license requires.

* **anthropics/anthropic-cookbook** — MIT License, Copyright (c) 2023 Anthropic.
* **langchain-ai/langgraph** — MIT License, Copyright (c) 2024 LangChain, Inc.
* **ethz-spylab/agentdojo** — MIT License, Copyright (c) 2024 Edoardo
  Debenedetti, Jie Zhang, Mislav Balunovic, Luca Beurer-Kellner, Marc Fischer,
  and Florian Tramèr. `bench/real/agentdojo_canaries.json` and
  `agentdojo_runs.json` are derived from AgentDojo's task suites and recorded
  runs.

> Permission is hereby granted, free of charge, to any person obtaining a copy of
> this software and associated documentation files (the "Software"), to deal in
> the Software without restriction, including without limitation the rights to
> use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
> the Software, and to permit persons to whom the Software is furnished to do so,
> subject to the following conditions: The above copyright notice and this
> permission notice shall be included in all copies or substantial portions of
> the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
> EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
> MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO
> EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
> OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
> FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
> THE SOFTWARE.

Two LangGraph tutorials pull prompts from the public LangChain Hub
(`rlm/rag-prompt` and the four `hwchase17/self-discovery-*` prompts), fetched by
commit hash; the Hub pages state no license. The self-discovery prompts
implement the method of Zhou et al., *Self-Discover: Large Language Models
Self-Compose Reasoning Structures* (2024).

The measurement scripts in `bench/tokenizers/` and `bench/provider/` download
tokenizers and one small model from their publishers at pinned revisions into
`bench/.cache/`, which is not committed.
