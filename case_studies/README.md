# Case studies

Twelve real-world LLM application failures, eight of them prompt-injection
attacks, each modelled as a vulnerable OrchLang workflow and a repaired one. The report, with citations, is
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
| `08_gemini_calendar` | Calendar invite drives Google Home through Gemini (SafeBreach, 2025) | `E233` | accepted |
| `09_agentforce_forcedleak` | ForcedLeak, Salesforce Agentforce (Noma Security, 2025) | `E233` | accepted |
| `10_comet_browser` | Perplexity Comet hijacked by a Reddit comment (Brave, 2025) | `E233`, and a regression of the repair also `E233` | accepted, no escape hatch |
| `11_mcp_tool_poisoning` | MCP tool poisoning (Invariant Labs, 2025) | `E233` | accepted |
| `12_dpd_chatbot` | DPD chatbot talked into swearing (2024) | accepted: out of scope | n/a |

Files named `limitation_*.orch` and `out_of_scope.orch` are accepted on purpose.
They show what the compiler cannot see or does not claim to address: a
mislabelled input, an effect that was never declared, and harm that lies in
what a model says rather than what it does.

```sh
make                             # build orchc
python3 case_studies/verify.py   # check every verdict and rerun both experiments
```

`verify.py` rewrites `results/`. Its output is deterministic, so `git diff
results/` after a run should be empty, and `./verify.sh` checks exactly that.
