# Multi-Agent Security Incident Triage

![CI](https://github.com/codewithkachi/agent-incident-triage/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![LangGraph](https://img.shields.io/badge/langgraph-StateGraph-purple)
![License](https://img.shields.io/badge/license-MIT-green)

Incoming incident reports get classified, enriched, prioritised and
drafted into structured response reports by a LangGraph agent pipeline,
with the production concerns most agent demos skip: **schema guardrails
with a repair loop, PII redaction, per-node cost tracking with a hard
budget, a human approval gate, and trajectory evaluation as a CI quality
gate**. The domain comes from my years working security and compliance
operations: this is the triage I used to do by hand.

```
            +----------+     +---------+     +------------+     +-------+
incident -> | classify | --> | enrich  | --> | prioritise | --> | draft | --interrupt--> human approves --> dispatch
            |  (LLM)   |     | (tool)  |     | (policy)   |     | (LLM) |
            +----------+     +---------+     +------------+     +-------+
                 |                |                                  |
                 +---- any guardrail failure -----> human_review <---+
```

## Where the LLM is allowed to think, and where it is not

| Step | Who decides | Why |
|---|---|---|
| Classification (category, severity, summary) | LLM, schema-enforced | language understanding is the job |
| Enrichment (site criticality, SOPs, history) | deterministic tool call | registry lookups should never hallucinate |
| **Priority and SLA** | **policy matrix, no LLM** | "which SLA applies" is a business rule; the matrix is 8 lines of config |
| Action drafting | LLM, list-validated | wording help, human still approves |
| Dispatch | **human** | the graph interrupts before dispatch, always |

## Guardrails, all tested

* **Structured outputs**: every LLM response must validate against a
  Pydantic schema. A failed response gets one repair attempt with the
  validation error included; a second failure routes the incident to
  human review instead of guessing. Tested with deliberately flaky and
  hopeless LLM stubs.
* **PII redaction**: emails, UK phone numbers and NI numbers are redacted
  before any text reaches a model.
* **Cost tracking**: every call is metered per node against a pricing
  table with a hard per-incident budget; over budget aborts to review.
* **Human-in-the-loop**: LangGraph checkpointing with
  `interrupt_before=["dispatch"]`; nothing is dispatched without an
  approval call.

## Evaluated trajectories (CI gate)

`python -m triage.evaluate` runs 8 golden incidents through the full
graph and scores the trajectory. Current offline results:

| Metric | Score |
|---|---:|
| Category accuracy | 0.875 |
| **Priority accuracy** | **1.000** |
| Procedure attachment | 0.875 |

The one category miss is the chemical-spill incident, which genuinely
sits on the safety/environmental boundary; its priority still lands
correctly at P1 because priority never depends on the LLM's category
opinion. That separation is the design working as intended.

## Offline by default

`TRIAGE_LLM=mock` (default) uses a deterministic rule-based provider, so
the graph, guardrails, costs, HITL flow, API and evaluation all run with
zero credentials, in CI, every push. `TRIAGE_LLM=openai` swaps in
`gpt-4o-mini` with JSON mode; the graph does not change.

## Run it

```bash
pip install -r requirements.txt
python -m pytest tests -q                     # 13 tests
PYTHONPATH=src python -m triage.run_demo      # triage 8 sample incidents + approval flow
PYTHONPATH=src python -m triage.evaluate      # trajectory eval
uvicorn triage.api:app --app-dir src --port 8090
```

```bash
curl -X POST localhost:8090/triage -H "Content-Type: application/json" -d @incident.json
# -> {"status": "pending_approval", "report": {...}, "cost_usd": 0.00021, "approve_via": "/approve/INC-1"}
curl -X POST localhost:8090/approve/INC-1
# -> {"status": "approved", ...}
```

## Repo tour

```
src/triage/
  models.py      Pydantic contracts between agents
  graph.py       the LangGraph StateGraph + HITL interrupt
  guardrails.py  PII redaction, schema parse + repair loop
  costs.py       per-node token/cost metering with budget
  llm.py         mock / OpenAI providers
  evaluate.py    golden trajectory scoring (CI quality gate)
  api.py         FastAPI: /triage, /approve/{id}, /health
data/            site registry (the enrichment "tool") + sample incidents
eval/            golden trajectories + committed results
tests/           13 tests incl. misbehaving-LLM guardrail tests
```

---

Built by [Onyeka Ogbonna](https://onyekaogbonna.com) · MSc Applied Data
Science · [LinkedIn](https://linkedin.com/in/onyekaogbonna)
