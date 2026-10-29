# Third-party notices

The OrchLang software in this repository is MIT-licensed (see LICENSE). The items below
are third-party material used by, or derived into, the repository. Their own licenses
apply; the MIT license does not replace them.

## Ported prompts and workflow structure

The nine workflows in `workflows/` port the control structure and copy prompt text from:

- LangChain/LangGraph documentation, `langchain-ai/docs` at
  `5d83d5e690af84ed654a8d4320bf9969af28e39f` (`docs/src/oss/langgraph/workflows-agents.mdx`,
  `thinking-in-langgraph.mdx`), MIT License.
- LangGraph examples, `langchain-ai/langgraph` at `eb066bd31a2bf01fc0cd58256df4800a3695c233`
  (`examples/rag/langgraph_crag_local.ipynb`, `langgraph_adaptive_rag.ipynb`), MIT License.
- Prompt Flow examples, `microsoft/promptflow` at `33a68c9d3cf349d7fdfad1f41969af27543c0406`
  (`examples/flows/standard/conditional-flow-for-switch/`), MIT License.

The census in `experiments/census/` records file paths and line numbers in these
repositories and quotes short excerpts in its port specifications.

## Datasets (derived inputs in `experiments/data/`)

Sampled subsets are committed for reproducibility; `experiments/prepare_data.py`
regenerates them from these pinned revisions.

| Dataset | Revision | License |
|---|---|---|
| `fancyzhx/dbpedia_14` | `9abd46cf7fc8b4c64290f26993c540b92aa145ac` | CC BY-SA 3.0 |
| `bitext/Bitext-retail-ecommerce-llm-chatbot-training-dataset` | `12dd624ddcd3057382b2faad661bcda1fa869491` | CDLA-Sharing-1.0 |
| `Tobi-Bueck/customer-support-tickets` | `ddf1c81a5475992c4fa6752bf1e8b4e31f07bbeb` | CC BY-NC 4.0 (non-commercial; synthetic) |
| `rajpurkar/squad` | `7b6d24c440a36b6815f21b70d25016731768db1f` | CC BY-SA 4.0 |
| `rajpurkar/squad_v2` | `3ffb306f725f7d2ce8394bc1873b24868140c412` | CC BY-SA 4.0 |
| `openai/gsm8k` | `740312add88f781978c0658806c59bc2815b9866` | MIT |
| `fancyzhx/ag_news` (filler pilot only) | `eb185aade064a813bc0b7f42de02595523103ca4` | see dataset card |

Derived files keep the license of their source dataset.

## Models (not redistributed)

`experiments/fetch_models.py` downloads, at pinned revisions with SHA-256 checks:
Llama 3.2 1B and 3B Instruct GGUF quantizations (`bartowski/Llama-3.2-{1B,3B}-Instruct-GGUF`),
under the Llama 3.2 Community License; and, for pilots, Qwen 2.5 0.5B/1.5B Instruct GGUF
(`Qwen/Qwen2.5-*-Instruct-GGUF`), under Apache 2.0.

## Tools

Lean 4.19.0 (Apache 2.0) is installed separately. `llama-cpp-python` (MIT) wraps
llama.cpp (MIT). Python packages are listed in `requirements.txt` with their own licenses.

## Legacy prototype

`legacy/v1/` retains the earlier prototype and its notices, including the Elsevier
template derivative under the LaTeX Project Public License
(`legacy/v1/docs/manuscript/`) and the upstream sources documented in
`legacy/v1/THIRD_PARTY_NOTICES.md`.
