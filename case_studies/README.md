# Case studies

Seven real-world LLM application failures, each modelled as a vulnerable OrchLang
workflow and a repaired one. The report, with citations, is
[docs/CASE_STUDY.md](../docs/CASE_STUDY.md).

| Directory | Problem | Vulnerable | Repaired |
|---|---|---|---|
| `01_github_mcp` | GitHub MCP toxic agent flow (Invariant Labs, 2025) | `E233` | accepted |
| `02_supabase_mcp` | Supabase MCP support-ticket leak (General Analysis, 2025) | `E233` | accepted |
| `03_echoleak` | EchoLeak, CVE-2025-32711 (Microsoft 365 Copilot) | `E233` | accepted |
| `04_langchain_exec` | LangChain LLMMathChain, CVE-2023-29374 | `E233` | accepted |
| `05_credentials_in_prompt` | Credential in the system prompt (OWASP LLM07:2025) | `E230`, `E231` | accepted |
| `06_retry_overrun` | Retry-loop budget overrun (arXiv:2606.04056) | `E260` | accepted |
| `07_billing_side_channel` | Bill reveals a secret (constructed; token-count side channels) | `E236` | accepted |

Files named `limitation_*.orch` are accepted on purpose. They show what the
compiler cannot see: a mislabelled input, and an effect that was never declared.

```sh
make                             # build orchc
python3 case_studies/verify.py   # check every verdict and rerun both experiments
```

`verify.py` rewrites `results/`. Its output is deterministic, so `git diff
results/` after a run should be empty, and `./verify.sh` checks exactly that.
