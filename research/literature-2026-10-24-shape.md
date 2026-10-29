# Prior-art and novelty report: usage-metadata side channels in LLM workflows

**Date:** 2026-10-23
**Planned contribution:** Usage metadata (number of calls, model, input and output tokens, latency, retries) of multi-call LLM workflows leaks secret routing decisions, even when content is redacted or encrypted. The paper plans (1) measurements, (2) a DSL and compiler with IFC labels and static token bounds, (3) a taint-guided shape-alignment transformation (dummy calls, tokenizer-exact input padding, forced output length), (4) a Lean-verified translation-validation checker with a usage-noninterference theorem, and (5) leakage, overhead and functional-preservation measurements.

**How entries were verified.** For every arXiv entry I fetched the metadata (title, authors, date, comments, DOI) from the arXiv export API, and for most I also fetched the abstract or full text. Conference and journal entries were checked against Crossref DOI records or the official venue page (USENIX, NDSS, ICML/PMLR, NeurIPS, ICLR). Industry and documentation entries were fetched from the vendor's own page. Where I could not verify something, I say so; see "Unverified / not found" at the end.

**Closeness scale.** *High* means it overlaps a planned contribution and must be discussed head-on. *Medium* means it shares the threat model or the technique and must be differentiated. *Low* means background.

---

## A. Token-length, packet-size and timing side channels on LLMs, agents and RAG

### A.1 Core network and timing channels on single LLM calls

1. **Weiss, Ayzenshteyn, Amit, Mirsky. "What Was Your Prompt? A Remote Keylogging Attack on AI Assistants." USENIX Security 2024, pp. 3367–3384.** arXiv:2403.09751. https://www.usenix.org/conference/usenixsecurity24/presentation/weiss
   - **What it does:** Streamed responses leak per-token character lengths through encrypted packet sizes. An LLM trained to translate length sequences reconstructs responses: 27% reconstructed and 53% topic inferred in the USENIX version. The paper suggests random padding, grouping tokens, and batching whole responses.
   - **Closeness:** Low–medium. This is a per-token length channel inside one stream; it does not cover call-level usage records.
   - **Positioning:** Cite as the founding token-length channel. Our observer sees usage records (the call is the unit), and our leak survives full-response batching and TLS.

2. **McDonald, Bar Or (Microsoft). "Whisper Leak: a side-channel attack on Large Language Models." arXiv:2511.03675, Nov 2025.** https://arxiv.org/abs/2511.03675
   - **What it does:** Packet-size and timing sequences of streamed responses classify prompt topic across 28 LLMs, often above 98% AUPRC. The authors evaluated three mitigations: random padding, token batching (5 tokens) and packet injection. On gpt-4o-mini these cut AUPRC by only about 3.5–4.8 points (Table 3), and none gives complete protection.
   - **Closeness:** Medium. Same "topic or route inferred from metadata" goal, at network level.
   - **Positioning:** Their mitigations are heuristic and only partially effective. Our defense is deterministic shape equalization with a proof, at the call level. Cite their numbers as motivation for exact rather than random padding.

3. **Zhang, Saileshwar, Lie. "Time Will Tell: Timing Side Channels via Output Token Count in Large Language Models." arXiv:2412.15431, Dec 2024.** https://arxiv.org/abs/2412.15431
   - **What it does:** Output token count, recoverable remotely through timing, leaks the target language in translation and the output class in LLM classification: above 70% precision, including GPT-4o. They propose three defenses (§7):
     - tokenizer-level: uniform token density;
     - prompt-level: "Provide a 60-word explanation", which works on some models only;
     - system-level: "pad the output token count and the output plaintext length to match the longest expected output length". This costs about 93% latency on Tower and about 13% on MBart50/M2M100.
   - **Closeness:** **High** for components (1) and (3). Their "LLM classifier output length leaks the class" finding is the single-call version of our routing leak, and their system-level padding is the single-call version of our output forcing.
   - **Positioning:** Must be cited prominently. Our deltas:
     - multi-call workflows, where the route changes which later calls happen, so the call graph itself leaks, not just one output length;
     - input-token padding and model-identity alignment;
     - static bounds that tell us how much to pad, with soundness;
     - a verified guarantee;
     - usage records as the observation channel, not timing.
     They never ran the system-level padding end to end, so our measured overhead compared with "pad to global cap" is new.

4. **Carlini, Nasr. "Remote Timing Attacks on Efficient Language Model Inference." arXiv:2410.17175, Oct 2024.** https://arxiv.org/abs/2410.17175
   - **What it does:** Efficiency tricks (speculative decoding, caching) cause data-dependent timing. A passive observer learns conversation topic, for example medical versus coding, with 90%+ precision on open systems, and distinguishes messages on ChatGPT and Claude. As a defense (§7) they apply a constant output-rate scheme (one token every 1/r s, sending empty messages when nothing is ready). It "will thwart our attacks completely", with a reported latency/bandwidth trade-off (Fig. 12).
   - **Closeness:** Medium.
   - **Positioning:** A constant-rate stream is the network analogue of our constant-shape call trace. Our defense must also equalize the number and kind of calls and the token totals that appear in billing and telemetry, which no transport shaping can hide from the provider or the observability vendor.

5. **Wei, Abdulrazzag, Zhang, Muursepp, Saileshwar. "When Speculation Spills Secrets: Side Channels via Speculative Decoding in LLMs." arXiv:2411.01076 (v4, Feb 2026).** https://arxiv.org/abs/2411.01076
   - **What it does:** Patterns of correct and incorrect speculation show up in per-iteration token counts or packet sizes. These fingerprint queries with over 75% accuracy across REST, LADE, BiLD and EAGLE, and leak datastore contents. The authors propose packet padding and iteration-wise token aggregation.
   - **Closeness:** Low–medium.
   - **Positioning:** It shows that forcing the total output length does not fix per-iteration leakage on a streaming observer. State that our observer model is per-call usage records plus coarse latency, and list streaming-granularity channels as out of scope or as composable with their defenses.

6. **Gu, Li, Kuditipudi, Liang, Hashimoto. "Auditing Prompt Caching in Language Model APIs." ICML 2025 (PMLR 267:20477–20496).** arXiv:2502.07776. https://proceedings.mlr.press/v267/gu25b.html
   - **What it does:** Statistical audits found prompt caching at 8 of 17 API providers, and global cross-user cache sharing at 7, including OpenAI.
   - **Closeness:** Low–medium.
   - **Positioning:** Caching changes latency and also the usage fields themselves (cached-token counts). Our padding must either disable caching or treat cache hits as part of the observable trace. Otherwise a padded prefix that is shared only on one branch creates a new channel. Cite as a threat to the "explicit assumptions" of our theorem.

7. **Zheng, Han, Shi, Fang, Du, Hu, Guo. "InputSnatch: Stealing Input in LLM Services via Timing Side-Channel Attacks." arXiv:2411.18191, Nov 2024.** https://arxiv.org/abs/2411.18191
   - **What it does:** Timing attacks on KV and semantic caches recover user inputs. Proposed defenses (§6.2): per-user cache isolation, rate limiting, constant-time execution or random delays, and disabling streaming.
   - **Closeness:** Low.
   - **Positioning:** Cache-timing background.

8. **Song, Pang, Wang, Wang, Wang, Chen, Song, Jin, Meng, Hou. "The Early Bird Catches the Leak: Unveiling Timing Side Channels in LLM Serving Systems." arXiv:2409.20002 (v5; arXiv comment: accepted to IEEE TIFS).** https://arxiv.org/abs/2409.20002
   - **What it does:** KV-cache and semantic-cache timing leaks system prompts and other users' prompts. Proposed defenses: share prefix caches only in k-token batches, and anonymize private content before semantic-cache lookup (about 4% overhead).
   - **Closeness:** Low.
   - **Positioning:** Background on serving-layer channels.

9. **Wu, Zhang, Zhang, Wang, Niu, Wu, Zhang. "I Know What You Asked: Prompt Leakage via KV-Cache Sharing in Multi-Tenant LLM Serving." NDSS 2025.** https://www.ndss-symposium.org/ndss-paper/i-know-what-you-asked-prompt-leakage-via-kv-cache-sharing-in-multi-tenant-llm-serving/
   - **What it does:** The PROMPTPEEK attack reconstructs other tenants' prompts through shared KV caches in vLLM and SGLang.
   - **Closeness:** Low.
   - **Positioning:** Background; again an argument for per-principal cache isolation as an assumption.

10. **Adiletta, Sunar. "Spill The Beans: Exploiting CPU Cache Side-Channels to Leak Tokens from Large Language Models." arXiv:2505.00817, May 2025.** https://arxiv.org/abs/2505.00817
    - **What it does:** Flush+Reload on embedding rows leaks generated tokens to a co-located attacker.
    - **Closeness:** Low.
    - **Positioning:** Hardware channel; out of scope.

11. **Zhang, Wu, Deng, Wang, Zhang. "NetEcho: From Real-World Streaming Side-Channels to Full LLM Conversation Recovery." arXiv:2510.25472, Oct 2025.** https://arxiv.org/abs/2510.25472
    - **What it does:** Surveys deployed padding and obfuscation defenses (OpenAI, DeepSeek) across seven deployment scenarios, finds residual leakage, and recovers full conversations.
    - **Closeness:** Medium as evidence.
    - **Positioning:** Strong motivation that ad-hoc padding leaves residual leakage. Our approach replaces "pad and hope" with a checkable invariant.

12. **Li, Cui, Chen, Lin, Gu, Deng, Xu, Li. "From Length to Content: Token-Length Side-Channel Attacks on LLM API Merged Outputs." USENIX Security 2026.** https://www.usenix.org/system/files/usenixsecurity26-li-sijia.pdf
    - **What it does:** Token aggregation, the deployed fix for Weiss et al., creates a "merged token-length" channel that still reveals content. Discussed mitigations: padding to MSS, dynamic padding (about 1.4× bandwidth), randomized batching.
    - **Closeness:** Low–medium.
    - **Positioning:** More evidence that heuristic, network-level mitigations fail.

13. **Ding, Xu, Shen, Ding, Fei. "MoEcho: Exploiting Side-Channel Attacks to Compromise User Privacy in Mixture-of-Experts LLMs." ACM CCS 2025, pp. 2159–2173.** DOI:10.1145/3719027.3765174 (Crossref-verified).
    - **What it does:** MoE expert routing shows up in hardware side channels.
    - **Closeness:** Low.
    - **Positioning:** "Routing" inside the model, not workflow routing. Clarify the terminology to avoid confusion.

14. **Kannan, Feamster, Hoffmann. "Prediction Privacy in Distributed Multi-Exit Neural Networks: Vulnerabilities and Solutions." ACM CCS 2023.** DOI:10.1145/3576915.3623069. **Akinsanya, Brennan. "Timing Channels in Adaptive Neural Networks." NDSS 2024.** DOI:10.14722/ndss.2024.24125 (both Crossref-verified).
    - **What they do:** Input-dependent computation (early exits) leaks predictions through timing and messages. Kannan et al. propose defenses.
    - **Closeness:** Medium conceptually.
    - **Positioning:** The closest pre-LLM analogue of "the amount of computation reveals the classification result". Cite as precedent: secret-dependent work in ML pipelines is a known channel, but nobody has handled it at LLM-workflow granularity with a compiler.

### A.2 Side channels in LLM agents, multi-agent systems and RAG

15. **Zhang, Deng, Gu, Chen, Xu, Li, Wu. "Exposing LLM User Privacy via Traffic Fingerprint Analysis: A Study of Privacy Risks in LLM Agent Interactions." arXiv:2510.07176, Oct 2025.** https://arxiv.org/abs/2510.07176
    - **What it does:** AgentPrint fingerprints agents and tool-invocation workflows from encrypted traffic: F1 0.866 for agent identification, and 73.9% / 69.1% top-3 accuracy for user attributes. It lists dummy packets, batching and padding as candidate mitigations but does not evaluate them.
    - **Closeness:** **Medium–high** for component (1): the agent workflow leaks through metadata.
    - **Positioning:** Their observer is the network. Ours is the usage and telemetry record, which also exists when the network is protected (VPN, on-premise) and which the provider, gateway and observability vendor always see. We also contribute a defense with guarantees.

16. **Pouryousef, Lopez, Nowmi, Kamol, Hossain, Tran, Rahman. "A Large-Scale Benchmark and Risk Assessment of Traffic Analysis Attacks on Cloud LLM Services." arXiv:2609.31877, Sep 2026.** https://arxiv.org/abs/2609.31877
    - **What it does:** A benchmark of 60k user–LLM interactions plus 2,838 multi-agent executions. Model fingerprinting reaches 97.7%, prompt category 76.7%, and multi-agent task 90.7%. The lightweight countermeasures tested (prompt reformulation, temperature variation) only reduce leakage. The authors argue that effective defenses "must shape the overall traffic profile rather than mask a single feature".
    - **Closeness:** Medium–high, as evidence of the threat in multi-agent workflows.
    - **Positioning:** Their conclusion is exactly the gap we fill: whole-profile shaping. Cite as motivation, and contrast network observers with usage-record observers.

17. **Li, Gao, Liu, Li, Fu, Wang, Xu. "ANT: A Multi-Granularity Network Traffic Dataset and Benchmark for Agents Behavior Auditing." arXiv:2610.06514, Oct 2026.** https://arxiv.org/abs/2610.06514
    - **What it does:** 3,114 agent episodes. Traffic reveals agent risk, scenario and behaviour primitives.
    - **Closeness:** Low–medium.
    - **Positioning:** Treats traffic leakage as a feature for auditing. Notes the tension between auditing and privacy.

18. **Li, Zhuang, Wei, Luo, Zhang, Zhang, Li, Huang. "SkillWatermark: An Embedded Skill Watermark of Progressive Privacy Inference via Benign Prompts." arXiv:2608.16026, Aug 2026.** https://arxiv.org/abs/2608.16026
    - **What it does:** Malicious skill descriptions induce traffic patterns that encode private prompt information, creating a covert channel to a passive network observer.
    - **Closeness:** Low–medium.
    - **Positioning:** An active or covert variant. Our compile-time shape invariant would also neutralize such an encoding if the skill sits inside a labeled region; mention it as an extra benefit.

19. **Sun, Liu, Ma, Li, Xiao, Jiang. "Agent-Assisted Side-Channel Attacks on Non-Prefix KV Cache in RAG." arXiv:2606.21842, Jun 2026.** https://arxiv.org/abs/2606.21842
    - **What it does:** SpliceLeak fingerprints hidden prompt lengths and extracts RAG content through timing of chunk-fused KV caches (vLLM with LMCache).
    - **Closeness:** Low.
    - **Positioning:** RAG serving-layer channel; it shows that input length is itself a target. This supports our input padding.

20. **Shahriar, Rahman, Ahmed, Sadeque, Parvez. "AgentTell: Behavioural Side-Channel Leakage in Browser-Use Agents." arXiv:2609.32915, Sep 2026.** https://arxiv.org/abs/2609.32915
    - **What it does:** Agents reveal a carried secret through which action they choose, in 61.1% of sessions.
    - **Closeness:** Low–medium.
    - **Positioning:** Semantic action choice, not usage metadata. A good example of why routing on secrets is observable.

### A.3 Industry mitigations (deployed padding)

21. **Martinho, Chen (Cloudflare). "Mitigating a token-length side-channel attack in our AI products." Cloudflare blog, Mar 14 2024.** https://blog.cloudflare.com/ai-side-channel-attack-mitigated
    - **What it does:** Adds a random-length `"p"` padding property to each streamed JSON object (Workers AI), and random padding on all streams proxied through AI Gateway.
    - **Closeness:** Low.
    - **Positioning:** Random per-message padding, with no guarantee and nothing at the call level.

22. **OpenAI API reference: `stream_options.include_obfuscation`.** https://developers.openai.com/api/docs/api-reference/responses/get
    - **What it does:** "Stream obfuscation adds random characters to an `obfuscation` field on streaming delta events to normalize payload sizes as a mitigation to certain side-channel attacks". It is on by default.
    - **Closeness:** Low.
    - **Positioning:** A vendor admission that the channel matters. It does nothing for usage fields (`usage.*_tokens`), which are returned and logged unpadded.

### A.4 Mitigation-side systems for serving-layer channels

23. **Chu et al. "Selective KV-Cache Sharing to Mitigate Timing Side-Channels in LLM Inference" (SafeKV). arXiv:2508.08438.** https://arxiv.org/abs/2508.08438
24. **Addagada. "Governing the KV Cache: Preventing Timing Side-Channel Leakage in Multi-Tenant LLM Inference" (KVGov). arXiv:2608.09225, Aug 2026.** https://arxiv.org/abs/2608.09225
    - **What they do:** Cache isolation or partitioning (SafeKV, KVGov).
    - **Closeness:** Low.
    - **Positioning:** Orthogonal. Cite as a deployment assumption ("per-principal cache salt") for our latency claims.

**Answer to "did anyone formally verify or statically analyze an LLM side-channel mitigation?"** In all the A-section work I examined, none statically analyzes or formally verifies an LLM side-channel mitigation. Every defense above is evaluated empirically: random padding, batching or aggregation, constant-rate streaming, packet injection, cache isolation, prompt-level length instructions, and pad-to-maximum-length.

The closest formal statements come from elsewhere:
- Carlini–Nasr argue informally that constant-rate output defeats their attack.
- Dangol (C.11) gives indistinguishability-game proofs that are "immediate from the definitions" for transport-level cover traffic.
- SICC (C.10) proves noninterference of message *form*.

None of these addresses call-level usage traces or uses a verified checker.

---

## B. Usage-metadata, telemetry, billing and cost channels

25. **Chen. "Sensitive-Topic Leakage Through LLM Routing Metadata: Measurement and Mitigation." arXiv:2610.09981, Oct 7 2026.** https://arxiv.org/abs/2610.09981
    - **What it does:**
      - Measures leakage through the logged model choice of LLM routers (RouteLLM, Not Diamond, the vLLM semantic router), beyond what token counts reveal. The data are 1.7M real requests from WildChat and LMSYS.
      - Surveys 11 gateways and platforms (OpenRouter, LiteLLM, Kong, Cloudflare, Helicone, AWS Bedrock/CloudTrail, Portkey, Azure and others). They find that per-request metadata (served model, time, caller, often token counts) is kept with content logging off, often by default.
      - The threat model is insider gateway admins, SIEM, finance (bill-only) and observability sub-processors.
      - Defenses tested: per-category length-matched parity post-processing removes the gap at a cost of at most 0.2 accuracy points. Stickiness, per-user budget bands and pooled parity fail.
    - **Closeness:** **High** for the threat model and for component (1). It is the closest work to our motivating claim that usage metadata in logs leaks secret routing even when content is redacted.
    - **Positioning:** Must be cited and positioned explicitly as concurrent or prior. Our deltas:
      - multi-call workflows and agent graphs rather than one routing decision per request;
      - a full usage trace (call count, per-call model, input and output tokens, latency, retries) rather than a binary strong-or-weak bit;
      - a program-level transformation that preserves the routing's functionality rather than changing the router's decisions (their parity changes outputs; ours keeps the route secret but executes all shapes);
      - static analysis and a verified checker.
      Do **not** claim to be the first to show that LLM usage logs leak routing or topic.

26. **OpenTelemetry GenAI semantic conventions: spans (status: Development).** Now maintained at https://github.com/open-telemetry/semantic-conventions-genai (`docs/gen-ai/gen-ai-spans.md`).
    - **What it says:** `gen_ai.usage.input_tokens`, `gen_ai.response.model` and others are *Recommended* attributes, and `gen_ai.request.model` is Conditionally Required. Content attributes (`gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`) are *Opt-In*.
    - **Closeness:** n/a (motivation).
    - **Positioning:** The standard is designed so that a content-free deployment still exports exactly the usage fields we show to be sensitive. Strong motivating citation.

27. **LangSmith docs, "Prevent logging of sensitive data in traces".** https://docs.langchain.com/langsmith/mask-inputs-outputs
    - **What it says:** `LANGSMITH_HIDE_INPUTS` / `LANGSMITH_HIDE_OUTPUTS` hide inputs and outputs, and "the trace produced will have its metadata present".
    - **Positioning:** Motivation.

28. **Langfuse docs, "Masking".** https://langfuse.com/docs/observability/features/masking
    - **What it says:** Masking redacts inputs, outputs and metadata strings through hooks, including OTel span attributes.
    - **Positioning:** Masking is string-level. Token counts and observation structure remain. Motivation.

29. **Helicone docs, "Omit Logs".** https://docs.helicone.ai/features/advanced-usage/omit-logs
    - **What it says:** With `Helicone-Omit-Request/Response` set, bodies are not stored, but "you can still see the key metrics for each request": costs, latency and token usage. Bodies are still sent to the backend.
    - **Positioning:** Direct evidence for our observer model.

30. **Kelly, Glavin, Barrett. "Denial of wallet—Defining a looming threat to serverless computing." J. Information Security and Applications 60, 2021.** DOI:10.1016/j.jisa.2021.102843 (Crossref).
    - **What it does:** Defines denial-of-wallet: billing abuse in pay-per-use systems.
    - **Closeness:** Low.
    - **Positioning:** Denial-of-wallet is about *availability* and money. We are about *confidentiality* through cost records. Use it to name the "cost channel" lineage.

31. **Zhang, Xia, Wu, Yue, Zhang, Cheng, Tu. "Persistent Billable State: Denial-of-Wallet Attacks and Defenses in Tool-Calling LLM Agents." arXiv:2609.28585, Sep 2026.** https://arxiv.org/abs/2609.28585
    - **What it does:** Malicious tools inflate re-metered context in agents. DOW-BENCH observes up to 14,293× growth in per-session cumulative input.
    - **Closeness:** Low.
    - **Positioning:** Different property (integrity and cost). It also shows that usage telemetry is rich and per-call.

32. **Kumar, Roh, Naseh, Karpinska, Iyyer, Houmansadr, Bagdasarian. "OverThink: Slowdown Attacks on Reasoning LLMs." arXiv:2502.02542.** https://arxiv.org/abs/2502.02542
    - **What it does:** Decoy problems inflate hidden reasoning tokens.
    - **Closeness:** Low.
    - **Positioning:** Reasoning tokens are a usage field that the client cannot control. This is a scope limit for our output forcing: exclude reasoning models, or treat reasoning tokens as unpaddable.

33. **Sun et al. "CoIn: Counting the Invisible Reasoning Tokens in Commercial Opaque LLM APIs." arXiv:2505.13778.** https://arxiv.org/abs/2505.13778
34. **Sun et al. "Invisible Tokens, Visible Bills: The Urgent Need to Audit Hidden Operations in Opaque LLM Services." arXiv:2505.18471.** https://arxiv.org/abs/2505.18471
35. **Cai, Shi, Zhao, Song. "Are You Getting What You Pay For? Auditing Model Substitution in LLM APIs." arXiv:2504.04715.** https://arxiv.org/abs/2504.04715
36. **Chen et al. "The More It Says, the More You Pay: A Black-Box Audit of Provider-Side Token Inflation in LLM Services." arXiv:2609.20370.** https://arxiv.org/abs/2609.20370
    - **What they do:** Billing integrity: verifying reported counts and models.
    - **Closeness:** Low.
    - **Positioning:** They treat usage records as something the *user* must trust. We treat them as something a *third party* observes. They are relevant to the assumption in our theorem that the provider reports usage faithfully and honors `max_tokens`/`ignore_eos`.

**Summary for B:** usage-metadata leakage through gateway logs has a direct prior in Chen (Oct 2026), but only for single routing decisions. I found no prior work on multi-call workflow telemetry, meaning OTel GenAI spans or LangSmith/Langfuse traces of multi-node graphs, as a side channel. The billing and cost literature is about integrity or availability, not confidentiality.

---

## C. Static analysis, IFC and type systems for LLM agents and workflows; cost analysis; LLM DSLs

### C.1 IFC and capability systems for agents (none handles usage side channels)

37. **Debenedetti, Shumailov, Fan, Hayes, Carlini, Fabian, Kern, Shi, Terzis, Tramèr. "Defeating Prompt Injections by Design" (CaMeL). arXiv:2503.18813.** https://arxiv.org/abs/2503.18813
    - **What it does:** A privileged LLM writes code; a custom interpreter tracks provenance and capabilities; a quarantined LLM handles untrusted data.
    - **What it says about side channels:** Section 7, "Side Channels Can Be a Problem", shows three examples: a loop count observed through external fetches, exception-based 1-bit leaks, and timing. STRICT mode makes statements inside control-flow blocks depend on the condition. The authors "do not exclude that other timing side-channels could be present".
    - **Closeness:** Medium.
    - **Positioning:** CaMeL explicitly leaves side channels open. Our paper addresses precisely the "number of calls depends on private data" channel they illustrate, for the usage-record observer, and closes it by transformation rather than by blocking.

38. **Costa, Köpf, Kolluri, Paverd, Russinovich, Salem, Tople, Wutschitz, Zanella-Béguelin. "Securing AI Agents with Information-Flow Control" (FIDES). arXiv:2505.23643.** https://arxiv.org/abs/2505.23643
    - **What it does:** Formal planner model with dynamic taint tracking. Guarantees noninterference for integrity, and only *explicit secrecy* for confidentiality. Quote: "does not prevent implicit flows due to data-dependent control flow. An adversary that is able to see the sequence of tool calls may still be able to infer limited information leaked through the decisions made by the agent."
    - **Closeness:** Medium–high.
    - **Positioning:** FIDES's admitted gap is our target. We provide a termination- and usage-sensitive confidentiality guarantee for an observer of the call trace and usage counters.

39. **Zhong, Chen, Wang, McCall, Titzer, Miller, Gibbons. "RTBAS: Defending LLM Agents Against Prompt Injection and Privacy Leakage." arXiv:2502.08966.** https://arxiv.org/abs/2502.08966
    - **What it does:** Dependency screening for tool calls. The threat model assumes the attacker has no "knowledge of timing mechanisms".
    - **Closeness:** Low–medium.
    - **Positioning:** Explicitly excludes timing and side channels.

40. **Wu, Cecchetti, Xiao. "System-Level Defense against Indirect Prompt Injection Attacks: An Information Flow Control Perspective" (f-secure). arXiv:2409.19091.** https://arxiv.org/abs/2409.19091
    - **What it does:** IFC for integrity in agent planners.
    - **Closeness:** Low.

41. **Bagdasarian, Yi, Ghalebikesabi, Kairouz, Gruteser, Oh, Balle, Ramage. "AirGapAgent: Protecting Privacy-Conscious Conversational Agents." CCS 2024.** arXiv:2405.05175. https://arxiv.org/abs/2405.05175
    - **What it does:** Data minimization by contextual-integrity gating.
    - **Closeness:** Low.
    - **Positioning:** Content minimization does not hide which calls happen.

42. **Tsai, Bagdasarian. "Contextual Agent Security: A Policy for Every Purpose" (Conseca). HotOS 2025.** DOI:10.1145/3713082.3730378; arXiv:2501.17070.
    - **What it does:** Generates just-in-time security policies for agents.
    - **Closeness:** Low.

43. **Shi, He, Wang, Li, Wu, Guo, Song. "Progent: Securing AI Agents with Privilege Control." arXiv:2504.11703.** https://arxiv.org/abs/2504.11703
    - **What it does:** A privilege-control DSL for agent tool calls.
    - **Closeness:** Low.

44. **Zhou, D'Antoni, Polikarpova. "Language-Based Agent Control" (LBAC). arXiv:2605.12863 (cs.PL, v2 Oct 2026).** https://arxiv.org/abs/2605.12863
    - **What it does:** Agents must generate well-typed Haskell programs inside typed scaffolding. Case studies cover capabilities, provenance and IFC. Fig. 2 lists "Cost / Resource Types — bounds time, memory, or API usage" as a possible policy kind.
    - **Closeness:** **Medium–high** on PL framing. Cost/resource types are named only as a possibility, with no side-channel use.
    - **Positioning:** The closest PL-for-agents framework. We add resource-aware noninterference for usage traces, which LBAC does not provide. Cite as complementary; our DSL could be seen as an LBAC-style policy instance.

45. **Shim, Karim, Jakkula, Zhou, Liu, Wang, Li. "Confuse the Model, Control the Flow: Understanding and Mitigating Privacy Leakage from LLM Agents with Information Flow Control" (FLOWSEAL). arXiv:2609.14003, Sep 2026.** https://arxiv.org/abs/2609.14003
    - **What it does:** A tool-level IFC interceptor against new disclosure attacks.
    - **Closeness:** Low–medium.
    - **Positioning:** Content IFC; no metadata channel.

46. **Nikolaou, Eckhoff, Flood, Grov, Mavroeidis, Aspinall. "CaMeLoT: CaMeL orchestrated with Temporal logic for static verification and liveness." CAMLIS 2026; arXiv:2609.18674.** https://arxiv.org/abs/2609.18674
    - **What it does:** Static CTL model checking (nuXmv) of CaMeL plans with taint labels.
    - **Closeness:** Low–medium.
    - **Positioning:** Static verification of agent plans exists, but checks trace properties, not hyperproperties such as noninterference or constant shape.

47. **Ammanaghatta Shivakumar, Priya, Gao. "Agenra: A Language and Verified Core for Stateful LLM Agent Authorization." arXiv:2608.22868 (v2 Oct 2026).** https://arxiv.org/abs/2608.22868
    - **What it does:** An agent policy language with a **Lean** enforcement core. It certifies permission revisions via simulation, under explicit assumptions (serialized calls, identical service results, trusted Python translation layer).
    - **Closeness:** **Medium** for component (4). It is a precedent for "Lean-verified core plus explicit assumptions plus trusted translation layer" in agent security.
    - **Positioning:** Its property is authorization or workflow preservation, not confidentiality or side channels. Cite as methodological precedent and contrast the property.

48. **Wang, Huang, Wang, Liu, Kong, Zhang. "Lean4Agent: Formal Modeling and Verification for Agent Workflow and Trajectory." arXiv:2606.06523 (comment: NeurIPS 2026 accepted).** https://arxiv.org/abs/2606.06523
    - **What it does:** Lean 4 library for modeling agent workflows and verifying semantic consistency.
    - **Closeness:** Low–medium.
    - **Positioning:** Lean for agents exists, but not for security hyperproperties or usage.

### C.2 Agent-communication metadata channels (closest conceptual neighbours)

49. **Xu, Fan, Wang, Li, Liu. "Selection-Invariant Communication Compilers for Privacy-Aware Multi-Agent LLM Workflows" (SICC). arXiv:2609.26076, Aug 2026.** https://arxiv.org/abs/2609.26076
    - **What it does:**
      - Defines "selection-channel leakage": a private-state-dependent *choice of message form* (type, structure, length, abstraction level) leaks private state even after authorization.
      - The compiler fixes message form as a function of public inputs and authorization only (requirement-indexed canonical forms). Theorem 1 proves compositional communication-layer noninterference, I(S; Z | O_pub, X_auth, A_pub) = 0.
      - Evaluated on 132 AgentLeak replays and 100 executable **LangGraph** tasks. "Length-matched" controls still leak.
    - **Closeness:** **High** in spirit: a compiler, multi-agent LangGraph workflows, a noninterference theorem, the observable *shape* of intermediate artifacts. Different channel: inter-agent message content and form, not LLM-call usage records. Their compiler emits no LLM calls, and the paper does not address token counts, the number of model calls, model identity or latency. The proof is pen-and-paper information theory, not mechanized.
    - **Positioning:** Must be cited and contrasted explicitly. Suggested sentence: "SICC equalizes the *form of messages* exchanged between agents. We equalize the *resource footprint of the LLM calls* that produce them, which is observable by the provider, gateway and telemetry even when messages are never seen." The two are complementary and compose: SICC for transcripts, ours for usage traces.

50. **Dangol. "From Privacy to Workflow Integrity: Communication-Graph Metadata in Autonomous Agent Interoperability." arXiv:2606.07150 (v3, Jun 2026).** https://arxiv.org/abs/2606.07150
    - **What it does:** In A2A/MCP, transports protect content but expose the communication graph: who contacts whom, when, and how often. A label-blind classifier recovers task class at 6× chance from passive metadata.
    - **Formal part:** Indistinguishability-game semantics for transport properties (unlinkability, metadata minimization with constant cells, constant-rate fixed-length cover). The proofs are "immediate from the definitions".
    - **Key finding:** A residual "structural channel of message counts and sequence shape that padding does not target" requires constant-rate cover to reach chance.
    - **Closeness:** **Medium–high.** It shows that the count and shape of interactions is the residual channel, which is our central observation, at the transport level.
    - **Positioning:** Ours is the program-level, compile-time counterpart. Instead of a transport injecting cover traffic, the compiler makes the workflow's call shape secret-independent, with static bounds. That also covers non-network observers (billing, telemetry) that transport cover cannot fool.

51. **Kim, Yang. "AgentCardLeak: Inferring User Intent from AI-Agent Discovery Metadata." ICCCI 2026, pp. 193–198.** DOI:10.1109/ICCCI70321.2026.11666528 (Crossref).
    - **What it does:** Agent-discovery metadata reveals user intent.
    - **Closeness:** Low–medium. Another metadata channel in agents.

52. **Peng, Jiang, Liu, Yu, Zhu. "Privacy-Preserving Agentic AI in Edge Networks With Content and Trace Protection." IEEE Trans. Network Science and Engineering 13 (2026), pp. 10918–10932.** DOI:10.1109/TNSE.2026.3720648 (Crossref-verified title, authors and venue; abstract not retrievable from IEEE Xplore in this session).
    - **Closeness:** **Unknown, possibly medium.** "Trace protection" may mean hiding agent execution traces, possibly with cover traffic.
    - **Action:** Obtain and read the full text before submission.

53. **He, Wen, Li, Su, Wang. "Concealing LLM-Based Multi-Agent Topology via Phantom Structure Injection" (MIRAGE). arXiv:2609.37567, Sep 2026.** https://arxiv.org/abs/2609.37567
    - **What it does:** Injects phantom (decoy) edges and semantic evidence so that an adversary infers a fake topology.
    - **Closeness:** Low–medium. Decoy structure injection is analogous to our dummy calls, but the goal is IP protection of topology against semantic-trace inference, with no guarantee.
    - **Positioning:** Cite as a "decoy" analogue. Ours aims at indistinguishability, not deception.

54. **He, Hou, Yu, Jiang. "Indistinguishable Agents: Training Agent Privacy as Twin-World Indistinguishability." arXiv:2610.25161, Oct 2026.** https://arxiv.org/abs/2610.25161
    - **What it does:** Trains agents (paired GRPO) so that observer views in twin worlds differing only in a private fact become indistinguishable, and proves the objective bounds Bayes success.
    - **Closeness:** Medium on the formal goal (indistinguishability of observable behavior); the method is training, not compilation.
    - **Positioning:** Learning-based and statistical. Ours is program-transformation-based and exact for usage counts.

55. **El Yagoubi, Badu-Marfo, Al Mallah. "AgentLeak: A Benchmark for Internal-Channel Privacy Leakage in Multi-Agent LLM Systems." IEEE Access 2026.** DOI:10.1109/ACCESS.2026.3704541; arXiv:2602.11510.
    - **What it does:** Benchmark of content leakage through inter-agent messages, used by SICC.
    - **Closeness:** Low.
    - **Positioning:** Possible source of workflows to port, but it is a content-channel benchmark.

### C.3 Cost and resource analysis of agent workflows

56. **Khan. "Token Budgets: An Empirical Catalog of 63 LLM-Agent Budget-Overrun Incidents, with an Affine-Typed Rust Mitigation as a Case Study." arXiv:2606.04056, Jun 2026.** https://arxiv.org/abs/2606.04056
    - **What it does:** A catalog of 63 incidents from 21 frameworks, plus an affine-typed Rust budget crate (no aliasing or double-spend of budgets). The dollar cap is runtime arithmetic "under an estimator assumption".
    - **Closeness:** Low–medium.
    - **Positioning:** Types for budget *integrity*, not static token bounds or noninterference.

57. **Costwright (MCP server, author Hernán Inverso).** https://mcp.so/servers/costwright-mcp ; repo listed as github.com/hernaninverso/costwright-mcp.
    - **What it claims:** "Static worst-case token-budget analysis of LLM-agent workflows" for LangGraph, CrewAI and the OpenAI Agents SDK, via AST analysis, with Ed25519-signed budget certificates.
    - **Status:** A tool, not a peer-reviewed paper. The repository could not be inspected (GitHub API blocked in this session).
    - **Closeness:** Medium for the "static token bounds" sub-claim in component (2).
    - **Positioning:** Cite as existing tooling. Our bounds are *relational* (equal across secret branches) and feed a transformation. Worst-case upper bounds alone do not give noninterference.

58. **Hou, Wang, Zhao, Wang. "When Agents Do Not Stop: Uncovering Infinite Agentic Loops in LLM Agents" (IAL-Scan). arXiv:2607.01641.** https://arxiv.org/abs/2607.01641
    - **What it does:** A static analyzer over a framework-independent Agent IR and a loop-dependence graph that finds unbounded costly loops.
    - **Closeness:** Low–medium. A precedent for a static IR over LangGraph-like code.
59. **Wang, Hou, Zhao, Cheng, Wang. "AgentFlow: Building Agent Dependency Graphs for Static Analysis of Agent Programs." arXiv:2607.01640.** https://arxiv.org/abs/2607.01640
    - **Closeness:** Low–medium. Same group and line of work as IAL-Scan; cite both for "static analysis of agent programs exists, but not for side channels".

60. **Ouyang et al. "TokenCast: Forecasting Token Consumption During LLM Agent Execution." arXiv:2609.35760.** https://arxiv.org/abs/2609.35760
    - **What it does:** Shows that token use varies by over an order of magnitude across runs of the same task.
    - **Positioning:** Motivates why usage is a rich signal, and why tight static bounds need structured workflows rather than free-form agents.

### C.4 LLM programming DSLs (no confidentiality or side-channel guarantees)

61. **Beurer-Kellner, Fischer, Vechev. "Prompting Is Programming: A Query Language for Large Language Models" (LMQL). PLDI 2023.** DOI:10.1145/3591300; arXiv:2212.06094.
    - **What it does:** Constraint-guided decoding; constraints can bound length, which is a useful mechanism for output forcing.
    - **Closeness:** Low. No IFC.
62. **Khattab et al. "DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines." ICLR 2024** (proceedings title "…into State-of-the-Art Pipelines"); arXiv:2310.03714.
    - **Closeness:** Low. A "compiler" for prompt optimization, not security.
63. **Zheng et al. "SGLang: Efficient Execution of Structured Language Model Programs." NeurIPS 2024.** arXiv:2312.07104. https://proceedings.neurips.cc/paper_files/paper/2024/hash/724be4472168f31ba1c9ac630f15dec8-Abstract.html
    - **Closeness:** Low. Its RadixAttention prefix sharing is itself a cache channel (see A.9).
64. **Guidance (guidance-ai/guidance).** https://github.com/guidance-ai/guidance
    - **What it does:** Regex, CFG and JSON-schema constrained generation, with token fast-forwarding.
    - **Closeness:** Low.
    - **Positioning:** Grammar constraints could implement exact-length outputs on open models.

---

## D. Constant-time and constant-resource transformations, their verification, and fixed-shape traffic padding

### D.1 Constant-resource types, transformations and secure compilation

65. **Ngo, Dehesa-Azuara, Fredrikson, Hoffmann. "Verifying and Synthesizing Constant-Resource Implementations with Types." IEEE S&P 2017.** DOI:10.1109/SP.2017.53; arXiv:1801.01896.
    - **What it does:** Extends AARA with information-flow tracking to prove *resource-aware noninterference*, and uses type inference to *synthesize* constant-resource implementations by repairing insecure programs automatically.
    - **Closeness:** **High** on the PL technique: IFC plus resource bounds plus automatic repair (padding) plus a proof. Essentially our components (2) and (3) for classical resources.
    - **Positioning:** Present our work as "resource-aware noninterference lifted to LLM usage traces". Our deltas:
      - multi-dimensional, provider-defined resources (calls, model id, input and output tokens) whose costs are determined by a tokenizer and by stochastic generation;
      - padding mechanisms that are LLM-specific (tokenizer-exact filler, `ignore_eos`/`min_tokens`, dummy calls with matched model);
      - a Lean translation-validation checker rather than a type-soundness proof.

66. **Molnar, Piotrowski, Schultz, Wagner. "The Program Counter Security Model: Automatic Detection and Removal of Control-Flow Side Channel Attacks." ICISC 2005, LNCS 3935 (2006).** DOI:10.1007/11734727_14.
    - **What it does:** Requires the PC trace to be secret-independent; static detection plus source transformation.
    - **Closeness:** Medium–high conceptually. Our "call trace" plays the role of their PC trace.

67. **Agat. "Transforming out timing leaks." POPL 2000.** DOI:10.1145/325694.325702.
    - **What it does:** Type-directed cross-copying pads each secret branch with dummy versions of the other branch's operations.
    - **Closeness:** **High** analogue: our "dummy calls aligning branches' call shapes" is LLM-level cross-copying.
    - **Follow-ups:** Siveroni, "Filling Out the Gaps: A Padding Algorithm for Transforming Out Timing Leaks," ENTCS 2006 (DOI:10.1016/j.entcs.2005.10.041). Mantel & Starostin, "Transforming Out Timing Leaks, More or Less," ESORICS 2015 (DOI:10.1007/978-3-319-24174-6_23).
    - **Positioning:** Cite the lineage. Our alignment is cross-copying with call-signature unification (model, token bounds).

68. **Devriese, Piessens. "Noninterference through Secure Multi-Execution." IEEE S&P 2010.** DOI:10.1109/SP.2010.15.
    - **Closeness:** Medium. This is the formal ancestor of the "run-both-branches" baseline. Use it as a named baseline, and note that it doubles calls and our alignment does not.

69. **Rane, Lin, Tiwari. "Raccoon: Closing Digital Side-Channels through Obfuscated Execution." USENIX Security 2015, pp. 431–446.** https://www.usenix.org/conference/usenixsecurity15/technical-sessions/presentation/rane
    - **What it does:** Executes decoy paths so that the real path is hidden.
    - **Closeness:** Medium. Its decoy-path execution is close to our dummy LLM calls.

70. **Cauligi, Soeller, Johannesmeyer, Brown, Wahby, Renner, Grégoire, Barthe, Jhala, Stefan. "FaCT: A DSL for Timing-Sensitive Computation." PLDI 2019.** DOI:10.1145/3314221.3314605.
    - **What it does:** A DSL with secret annotations; the compiler automatically transforms secret-dependent branches and returns into constant-time code.
    - **Closeness:** **High** on architecture: "secret-labeled DSL plus compiler that rewrites secret branches into constant-shape code". This is the template our DSL follows.
    - **Positioning:** Cite as the direct architectural ancestor. Our differences are the LLM resource model and verification by translation validation in Lean.

71. **Barthe, Betarte, Campo, Luna, Pichardie. "System-level Non-interference for Constant-time Cryptography." CCS 2014.** DOI:10.1145/2660267.2660283.
    - **Closeness:** Low–medium. A machine-checked (Coq) system-level noninterference argument.
72. **Barthe, Grégoire, Laporte. "Secure Compilation of Side-Channel Countermeasures: The Case of Cryptographic 'Constant-Time'." CSF 2018.** DOI:10.1109/CSF.2018.00031.
    - **What it does:** A framework for proving that compiler passes preserve constant-time.
73. **Barthe, Blazy, Grégoire, Hutin, Laporte, Pichardie, Trieu. "Formal verification of a constant-time preserving C compiler." PACMPL 4 (POPL 2020).** DOI:10.1145/3371075.
    - **What it does:** CompCert extended with machine-checked constant-time preservation.
74. **Barthe, Blazy, Hutin, Pichardie. "Secure Compilation of Constant-Resource Programs." CSF 2021.** DOI:10.1109/CSF51468.2021.00020.
    - **Closeness (72–74):** **Medium–high** for component (4). Verified preservation of constant-time and constant-resource through compilation.
    - **Positioning:** We use *translation validation* (per-run certificate checking in Lean), not a verified compiler. Cite these as the verified-compiler alternative and justify translation validation: an untrusted Python compiler, a small trusted checker, and the LLM-specific semantics. Entry 74 is the closest formal analogue to "well-padded programs have secret-independent usage".
75. **Almeida, Barbosa, Barthe, Blot, Grégoire, Laporte, Oliveira, Pacheco. "Jasmin: High-Assurance and High-Speed Cryptography." CCS 2017.** DOI:10.1145/3133956.3134078.
    - **What it does:** A DSL plus a verified compiler; constant-time checking.
    - **Closeness:** Low–medium.
76. **Cauligi, Disselkoen, von Gleissenthall, Tullsen, Stefan, Rezk, Barthe. "Constant-time foundations for the new Spectre era." PLDI 2020.** DOI:10.1145/3385412.3385970.
    - **Closeness:** Low. A reminder that the observation model must be explicit.

### D.2 Static analysis of resource and timing side channels

77. **Zhang, Askarov, Myers. "Language-based control and mitigation of timing channels." PLDI 2012.** DOI:10.1145/2254064.2254078. **Askarov, Zhang, Myers. "Predictive black-box mitigation of timing channels." CCS 2010.** DOI:10.1145/1866307.1866341.
    - **What they do:** Predictive mitigation pads timing to a schedule, with bounded leakage (log-bounded in the number of mispredictions). The PLDI paper adds a type system.
    - **Closeness:** Medium.
    - **Positioning:** A good model for *latency*, which we cannot equalize exactly. We could adopt predictive mitigation for latency and exact padding for counts.
78. **Antonopoulos, Gazzillo, Hicks, Koskinen, Terauchi, Wei. "Decomposition instead of self-composition for proving the absence of timing channels" (Blazer). PLDI 2017.** DOI:10.1145/3062341.3062378.
79. **Chen, Feng, Dillig. "Precise Detection of Side-Channel Vulnerabilities using Quantitative Cartesian Hoare Logic" (Themis). CCS 2017.** DOI:10.1145/3133956.3134058.
80. **Çiçek, Barthe, Gaboardi, Garg, Hoffmann. "Relational cost analysis." POPL 2017.** DOI:10.1145/3009837.3009858.
    - **What it does:** Bounds the *difference* in cost between two runs.
    - **Closeness (78–80):** Medium. Relational and resource-side-channel verification techniques.
    - **Positioning:** Our "static token bounds that detect secret-dependent usage" is a relational cost property. Relational cost analysis (80) is the formal ancestor, so cite it and say that ours is an instance specialized to LLM usage vectors.

### D.3 Translation validation and Lean

81. **Pnueli, Siegel, Singerman. "Translation Validation." TACAS 1998, LNCS 1384.** DOI:10.1007/BFb0054170. **Necula. "Translation validation for an optimizing compiler." PLDI 2000.** DOI:10.1145/349299.349314.
    - **Positioning:** The standard citations for the approach used in component (4).
82. **de Moura, Ullrich. "The Lean 4 Theorem Prover and Programming Language." CADE 2021, LNCS 12699.** DOI:10.1007/978-3-030-79876-5_37.
    - **Positioning:** Tool citation.

### D.4 Traffic-analysis padding defenses (fixed-shape and fixed-rate)

83. **Dyer, Coull, Ristenpart, Shrimpton. "Peek-a-Boo, I Still See You: Why Efficient Traffic Analysis Countermeasures Fail." IEEE S&P 2012.** DOI:10.1109/SP.2012.28.
    - **What it does:** Shows that per-packet padding fails, and introduces BuFLO: fixed-size packets at a fixed rate for a minimum duration.
    - **Closeness:** Medium. BuFLO is the network ancestor of "pad to a global cap".
84. **Cai, Nithyanand, Wang, Johnson, Goldberg. "A Systematic Approach to Developing and Evaluating Website Fingerprinting Defenses." CCS 2014.** DOI:10.1145/2660267.2660362.
    - **What it does:** Introduces Tamaraw: separate fixed rates for each direction plus padding the total to a multiple, with a bound on leakage.
    - **Companion:** Cai, Nithyanand, Johnson, "CS-BuFLO," WPES 2014 (DOI:10.1145/2665943.2665949).
85. **Wang, Cai, Nithyanand, Johnson, Goldberg. "Effective Attacks and Provable Defenses for Website Fingerprinting." USENIX Security 2014, pp. 143–157.** https://www.usenix.org/conference/usenixsecurity14/technical-sessions/presentation/wang_tao
    - **What it does:** Proves privacy for deterministic, simulatable defenses, and minimizes overhead by padding to *supersequences over anonymity sets*.
    - **Measured overheads on their dataset:** BuFLO about 190% ± 20% bandwidth; Tamaraw about 96% ± 9%; their class-level supersequence defense about 59% ± 3% (maximum uniform accuracy 0.1).
    - **Closeness:** **High** for components (3) and (5). "Pad each secret class to the supersequence of its anonymity set" is exactly "align secret branches to a common call shape" rather than "pad to the global cap".
    - **Positioning:** Our "align only the secret-dependent branches to their least upper bound" corresponds to their anonymity-set supersequence, and "pad to global cap" corresponds to BuFLO. Report our overheads in the same style (bandwidth becomes tokens or dollars, latency stays latency), and cite their numbers as a reference point.
86. **Wright, Coull, Monrose. "Traffic Morphing: An Efficient Defense Against Statistical Traffic Analysis." NDSS 2009** (listed on the NDSS 2009 accepted-papers page). https://www.ndss-symposium.org/ndss2009/accepted-papers/
    - **What it does:** Convex-optimization morphing of one traffic class to look like another, with lower overhead than padding.
    - **Closeness:** Low–medium. An alternative, statistical-only defense; usable as a "random or morphing padding" baseline argument.
87. **Mehta, Alzayat, De Viti, Brandenburg, Druschel, Garg. "Pacer: Comprehensive Network Side-Channel Mitigation in the Cloud." USENIX Security 2022.** arXiv:1908.11568. https://www.usenix.org/conference/usenixsecurity22/presentation/mehta
    - **What it does:** Shapes guest traffic outside the guest so that its shape is secret-independent by design. Security of key design aspects is proved in a formal model, with moderate overheads.
    - **Closeness:** Medium–high analogue: "make the observable shape independent of secrets by construction, prove it in a model, measure the overhead".
    - **Positioning:** Pacer works at the hypervisor and network level. We work at the application or workflow level and target usage records that Pacer cannot reshape.
88. **Bater, He, Ehrich, Machanavajjhala, Rogers. "Shrinkwrap: Efficient SQL Query Processing in Differentially Private Data Federations." PVLDB 12(3), 2018.** DOI:10.14778/3291264.3291274.
    - **What it does:** Intermediate-result sizes in oblivious query plans leak; it pads them, choosing padding amounts with differential privacy.
    - **Closeness:** Medium analogue for the random-padding baseline.
    - **Positioning:** It shows the design space between exact, worst-case and DP padding of intermediate sizes in a dataflow plan. Our workflow graphs are similar dataflow plans with LLM nodes.

---

## E. Key novelty risk: "pad LLM calls, force output length, constant-shape agent execution"

I searched with WebSearch (standard and extended), alphaXiv discovery (seven targeted queries), and arXiv keyword search. Queries included LLM side-channel padding, token-count padding, constant-time LLM, agent traffic-analysis defenses, oblivious LLM workflows, hiding routing decisions, metadata privacy for LLM agents, dummy LLM calls, fixed output length, and Lean-verified agent noninterference.

| Idea | Who already did something close | How close |
|---|---|---|
| Pad a single LLM output to the maximum expected length to hide an attribute | **Time Will Tell** (A.3), §7.3 system-level defense: proposed and costed (about 93% / 13% latency), not implemented end to end | High for one call |
| Instruct the model to produce fixed length | **Time Will Tell** §7.2, "60-word explanation": works on GPT-4o (−26% ASR), fails on Gemma2 | Medium |
| Constant output rate for streams | **Carlini & Nasr** (A.4); BuFLO/Tamaraw lineage | Medium |
| Random padding, batching, packet injection | Weiss (A.1), Cloudflare (A.21), OpenAI obfuscation (A.22), Whisper Leak (A.2), Li et al. USENIX'26 (A.12), speculative-decoding paper (A.5) | Medium (heuristic) |
| Mitigating logged *routing* leakage | **Chen 2610.09981** (B.25): per-category length-matched parity post-processing; per-user exact-rate. Changes routing behavior | High on threat; different mechanism |
| Constant-rate, fixed-length *cover* for agent communication graphs, with an indistinguishability game | **Dangol 2606.07150** (C.50) | Medium–high (transport level) |
| Compiler making inter-agent message *form* secret-independent, with a noninterference theorem, on LangGraph | **SICC 2609.26076** (C.49) | High in spirit; different channel |
| Decoy agents and edges to hide topology | **MIRAGE 2609.37567** (C.53) | Low–medium |
| Training agents for twin-world indistinguishability | **2610.25161** (C.54) | Medium (formal goal) |
| IFC for agents that admits implicit or side-channel gaps | **FIDES** explicit secrecy; **CaMeL** §7 STRICT mode | Medium (they name the gap) |
| Static token or cost bounds for agent workflows | **Costwright** (tool); IAL-Scan; Token Budgets (affine types) | Medium for (2) |
| Lean-verified core for agent security | **Agenra** (authorization); **Lean4Agent** (semantic consistency) | Medium for (4) |
| *Combination:* IFC labels plus relational token bounds plus automatic dummy-call alignment plus tokenizer-exact input padding plus `ignore_eos`/`min_tokens` output forcing plus a Lean translation-validation checker, for multi-call LLM workflows, with the usage-record observer | **Not found** | — |

Engineering facts checked against primary sources:
- vLLM `SamplingParams` has `ignore_eos` and `min_tokens`, and validates `min_tokens ≤ max_tokens` (vllm/sampling_params.py).
- The llama.cpp server documents `ignore_eos` and `n_predict`.
- Both are needed for exact output forcing on self-hosted models.

**Verdict for E:** no prior work does constant-shape execution at the LLM-call or usage-record level for workflows, or verifies such a transformation. The nearest are:
- (i) Time Will Tell's single-call padding proposal;
- (ii) SICC's compiler for message form;
- (iii) Dangol's transport-level cover traffic;
- (iv) Chen's router-log parity.

All four were published between Dec 2024 and Oct 2026, three of them in the last four months, so the area is moving fast. Re-check arXiv right before submission.

---

## Novelty verdict

### Already done by others (do not claim as new)
1. **"Metadata leaks LLM secrets despite encryption"**: well established at network level (Weiss 2024; Carlini & Nasr 2024; Time Will Tell 2024; Whisper Leak 2025; NetEcho 2025; Li et al. 2026). It is also established for **agent and multi-agent workflows** at network level (AgentPrint 2025; Pouryousef et al. 2026; ANT 2026) and at communication-graph level (Dangol 2026).
2. **"Logged usage metadata (served model plus token counts, content logging off) leaks sensitive topics through routing"**: Chen, arXiv:2610.09981 (Oct 2026), on real traffic, including a survey of gateway logging defaults. This is the biggest threat to the "telemetry leaks routing" framing.
3. **"An LLM classifier's output length leaks the class"**, and **"pad output to max length" as a mitigation idea**: Time Will Tell.
4. **IFC plus resource-bound types plus automatic padding repair plus noninterference proof**: Ngo et al. S&P 2017 (classical resources), with FaCT (DSL plus compiler), Agat (cross-copying), Molnar (PC model), and relational cost analysis as close PL precedents.
5. **A noninterference-style compiler for multi-agent LangGraph workflows**: SICC (message form, Aug 2026).
6. **Static token-budget analysis of LangGraph code**: Costwright (tool), IAL-Scan-style static IRs.

### Appears new (as of 2026-10-23; no matching work found)
- **(a) The usage-trace observer for multi-call workflows.** Per-call (model, input tokens, output tokens, latency, retries) sequences of LangGraph or Prompt Flow graphs, as exported by OTel GenAI, LangSmith, Langfuse or Helicone with content hidden, used to recover *secret routing decisions inside a workflow*. Shown on faithful ports of public workflows with real models. Chen covers only one router decision per request; SICC covers message form; network papers cover traffic.
- **(b) A DSL/compiler with IFC labels plus *relational* static usage bounds** (per-branch call-shape and token-interval equality) that **detects secret-dependent usage** in LLM workflows.
- **(c) Taint-guided shape alignment at LLM-call granularity:** dummy calls with matched model identity, tokenizer-exact input padding, and forced output length through `ignore_eos`/`min_tokens`. Branch-local least-upper-bound alignment (the analogue of Wang et al.'s supersequence) instead of a global cap.
- **(d) A Lean-checked translation validator** with a theorem that validated programs produce secret-independent usage traces under explicit assumptions. Nothing similar exists for LLM workflows. Agenra (Lean, authorization) and the CompCert CT work (Coq, compilers) are methodological precedents only.
- **(e) A quantitative comparison** against run-both-branches (secure multi-execution), pad-to-global-cap (BuFLO-style) and random padding (Cloudflare/OpenAI/Shrinkwrap-style), reporting leakage, token and dollar overhead, latency, and functional preservation.

### Risks reviewers will raise
1. **Concurrent work.** Chen (Oct 7 2026), SICC (Aug 2026) and Dangol (Jun 2026) are recent. Reviewers may see the threat as "known". Mitigation: position the threat as an *extension* (multi-call, full usage vector, telemetry standards), and make the PL plus verification contributions the headline.
2. **Theorem strength.** If the theorem says "padded programs have equal usage traces, assuming the provider honors max/min tokens, the tokenizer is deterministic, there is no caching, and retries are secret-independent", reviewers may call it shallow.
   - Make the assumptions explicit and test each one empirically.
   - Show the checker catches real bugs: mis-padded branches, tokenizer drift, chat-template tokens, BOS/EOS accounting, retries.
   - Keep latency out of the exact theorem; treat it with bounded or predictive mitigation (Askarov/Zhang/Myers) plus measurements.
3. **Closed APIs.** Hosted providers may not expose `min_tokens` or `ignore_eos`. This should be verified per provider; I found no such parameter documented in the sources checked. Reasoning tokens are hidden and billed (OverThink, CoIn), and prompt caching changes the usage fields (Gu et al.).
   - Scope exact output forcing to self-hosted serving (vLLM, llama.cpp).
   - For hosted APIs, offer only upper-bound padding with residual leakage measured.
   - Disable or account for caching.
4. **Functional preservation.** Forced output length changes the text: extra tokens after EOS must be discarded. Dummy calls may have side effects (tools) and costs.
   - Show semantic equivalence of the post-processed outputs.
   - Show dummy calls are side-effect-free: no tools, separate keys, so rate limits do not change.
5. **Baseline fairness.** Compare against SICC-style canonicalization, against Chen-style parity post-processing where applicable, and against Time Will Tell's pad-to-max.
6. **Streaming and serving-layer channels** (speculative decoding, per-iteration packet sizes, cache timing) remain open. State that the observer model excludes them, or that it composes with Carlini–Nasr constant-rate streaming and per-tenant cache isolation.
7. **Reference to verify.** Peng et al., IEEE TNSE 2026, "Content and Trace Protection": its abstract was unavailable here. Read it before submission in case "trace protection" means call-pattern hiding.

### Recommended framing
- Present the paper as **resource-aware noninterference for LLM workflows**: the Ngo et al. / FaCT / Agat line moved to a new resource model (LLM usage vectors) and a new observer (provider, gateway, observability telemetry), plus a practical compiler and a verified checker.
- Present the measurement as evidence that **the observability ecosystem is designed to export exactly the leaking fields**. OTel GenAI marks content Opt-In but token usage Recommended; LangSmith keeps metadata; Helicone keeps cost, latency and tokens. Generalize Chen's single-router finding to whole workflows.
- Make the defensive novelty explicit:
  - (i) relational static bounds;
  - (ii) branch-local alignment, the anonymity-set supersequence analogue, which is cheaper than global padding;
  - (iii) tokenizer-exact padding and output forcing;
  - (iv) translation validation in Lean.
- Avoid "first to show metadata leakage". Say "first compiler with machine-checked guarantees that eliminates usage-metadata side channels in multi-call LLM workflows".

### Title options
1. **"Constant-Shape LLM Workflows: Eliminating Usage-Metadata Side Channels with Verified Compilation"**
2. "Your Telemetry Knows the Route: Detecting and Closing Usage-Metadata Side Channels in LLM Workflows"
3. "Usage Noninterference for LLM Agents: Information-Flow Types, Call-Shape Padding, and Lean-Validated Translation"

---

## Suitable venues (deadlines verified on official pages unless noted)

| Venue | Type | Next deadline(s) | Fit | Source |
|---|---|---|---|---|
| **IEEE S&P 2027** (Montreal, May 17–20 2027) | Conference | Cycle 2: abstract **Nov 10 2026**, paper **Nov 17 2026** (AoE) | Top security; systems plus formal plus measurement | https://www.ieee-security.org/TC/SP2027/cfpapers.html |
| **USENIX Security 2027** (Denver, Aug 11–13 2027) | Conference | Cycle 2: registration **Jan 19 2027**, paper **Jan 26 2027** | Strong for measurement plus defense plus artifacts; prior LLM side-channel papers appeared here | https://www.usenix.org/conference/usenixsecurity27/call-for-papers |
| **PLDI 2027** (Atlanta, Jun 5–11 2027) | Conference (PACMPL) | **Nov 12 2026** (AoE) | DSL, compiler and translation validation as the headline; FaCT is a PLDI precedent | https://pldi27.sigplan.org/track/pldi-2027-papers |
| **OOPSLA 2027** (SPLASH, Prague, Oct 10–15 2027) | Journal-style (PACMPL) | Round 2: **Apr 7 2027** (Round 1 closed Oct 14 2026) | PL plus security systems with a Lean artifact | https://2027.splashcon.org/track/splashoopsla2027 |
| **IEEE CSF 2027** (Tokyo, Sep 13–17 2027) | Conference | Winter cycle: **Jan 28 2027** | Formal foundations; noninterference theorem plus verified checker; lists "language-based security" | https://www.ieee-security.org/TC/CSF2027/cfp.html |
| **PETS 2027** (PoPETs; Delft, Jul 19–24 2027) | Journal-style (quarterly issues) | Issue 3: **Nov 30 2026**; Issue 4: **Feb 28 2027** | Privacy and metadata-leakage framing; traffic-analysis defense community (Tamaraw/BuFLO lineage) | https://petsymposium.org/cfp27.php |

Journals with rolling submission (no deadline): **ACM Transactions on Privacy and Security (TOPS)**, **IEEE Transactions on Dependable and Secure Computing (TDSC)**, **IEEE TIFS** (where Early Bird appeared), **ACM TOPLAS**, **Journal of Computer Security**. These are a good fallback or extended-version target.

Not verified: ACM CCS 2027 has no call for papers posted yet; NDSS 2027 deadlines are not stated on its official submissions page and are likely past.

**Recommendation:** S&P 2027 cycle 2 (Nov 17 2026) is tight but possible if the artifact is mature. Otherwise USENIX Security 2027 cycle 2 (Jan 26 2027) for a security-first framing, or PLDI 2027 (Nov 12 2026) / OOPSLA R2 (Apr 7 2027) for a PL-first framing. Use CSF if the formal part is strongest.

---

## Unverified / not found
- **"Loom: Statically Bounding Resource Accumulation in LLM Agent Workflows"**: **not found.** Searched arXiv (title and abstract), alphaXiv, and web (standard and extended). Semantic Scholar was rate-limited (HTTP 429). Treat as unverified; do not cite unless the authors supply a link.
- **Costwright**: exists only as an MCP server listing (mcp.so, author Hernán Inverso); no paper. The GitHub repo could not be inspected.
- **Peng et al., IEEE TNSE 2026**: title, authors and venue verified via Crossref; abstract not retrievable.
- Semantic Scholar API was rate-limited throughout. Verification used the arXiv export API, Crossref, official venue pages and vendor documentation instead.
