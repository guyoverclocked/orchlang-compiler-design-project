# Source-to-execution assumption ledger

| Boundary | Check or result | Trusted premise / practical limit |
|---|---|---|
| User source -> original core, declared secrets | `assurance.source_binding`, source hash, omission-attack receipt | Python parser, lowering, template implementation and source policy are trusted. An undeclared secret is not inferred. |
| Proposed candidate -> accepted core | Actual Lean `validateProgram`; binding supplied independently | JSON decoding, Python serialization and correspondence to source are outside the proof. |
| Accepted core -> logical usage | `ShapeCore.noninterference` under global conformance; `AdmissionDomain.shape_exec_on` under reached-contract conformance | Global and restricted theorems have different domains; do not silently substitute their premises. |
| Visible admission status | `admitted_noninterference`, `certified_domain_noninterference` | Uniform membership / all-inputs-and-tapes certificate is required. The ideal adapter is noncomputable specification code. No automatic certificate for physical workflow trajectories. |
| Shaped vs original useful state | `erase_correct`, cap discipline and `World.Transparent` | Primitive visible-prefix transparency is conditional; finite falsification is not a universal model guarantee. |
| Core -> production interpreter | 6,320 current-code Lean / independent interpreter / Python comparisons | Authored finite character-token world; no verified general frontend/backend refinement. |
| Complete request -> dispatch | Exact tokenizer admission; overflow rejection; model-specific reservations | Source sizing annotations are heuristics. Refusal may leak secrets; count errors detected after dispatch cannot retract observations. |
| Backend -> logical accounting | Returned token-ID/count checks; separately captured local eval/generate calls | Client instrumentation is trusted, not authoritative remote telemetry. Natural stop IDs and isolated prefill have declared conventions. |
| Physical failure / lost dispatch | Retained prefix and unconfirmed reservation, explicit negative test | Neither equal-status behavior nor provider bill is proved; failed/unknown constructors in the formal alphabet do not prove implementation refinement. |
| Tool event -> external effect | Instrumented logical tool name; dummy tool records no actual invocation | Pure local tool semantics only; external service/network observers are outside this contract. |
| Retained execution -> manuscript | Exact planned ID reconciliation, cohort separation, raw hashes, generated tables | Saved fields are distinguished from full store; quality and timing are separate negative results. |
| Review package -> publication | Exact byte manifest, history bundle and restore/replay commands | Integrity is not public availability, permission, independent review, usefulness or acceptance. |
