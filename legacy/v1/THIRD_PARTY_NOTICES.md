# Third Party Notices

The C++ compiler uses the C++17 standard library and the host compiler/build tools.
The CPU reference and core validation scripts use the Python standard library.
Optional proof/tokenizer/manuscript tiers use separately licensed dependencies;
the code's MIT license does not replace their licenses.

The supplied Compiler Design planning document was read as background for the project context. No source code, grammar implementation, diagrams, or report text were copied from it into the compiler implementation.

## Optional dependencies and templates

- Lean 4.19.0 is installed separately from the official leanprover/lean4 release;
  preserve its upstream license when distributing binaries. No Lean runtime is
  vendored in this repository. Proof files here are authored for this project.
- Hugging Face Tokenizers 0.21.4 and its Python dependencies are installed in a
  separate optional environment. Their observed versions are recorded with runs.
  GPT-2 tokenizer artifacts (openai-community/gpt2) are MIT licensed; BERT
  tokenizer artifacts (google-bert/bert-base-uncased) are Apache-2.0 licensed per
  the pinned source model cards. They are downloaded outside this repository.
- The SCP OSP manuscript uses Elsevier's official `scico-osp-template.tex`,
  obtained from the current guide on 23 October 2026. The template carries
  Elsevier 2007–2009 copyright and LPPL 1.2-or-later notices; those notices are
  retained with the adapted manuscript. This material is not relicensed as MIT.

## External workflow projections

`bench/corpus/external-v1` contains authored cost projections of the pinned
Microsoft Prompt Flow examples and LangChain documentation workflow patterns.
They are not executions, faithful functional translations or provider results.
Exact source revisions, files, hashes, exclusions and changes are in its manifest.
Upstream source files and private paper PDFs are not redistributed here.

Upstream notices for any adapted portions:

MIT License

Copyright (c) Microsoft Corporation.
Copyright (c) 2025 LangChain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
