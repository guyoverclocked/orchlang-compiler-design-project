"""The triage graph: classify -> enrich -> prioritise -> draft -> human gate.

Built with LangGraph. Design rules:
  * LLM judgement is confined to classification and action drafting.
    Enrichment is a deterministic tool call and priority is a policy
    matrix, because "which SLA applies" is a business rule, not a
    language-model opinion.
  * The graph checkpoints and interrupts before `dispatch`: nothing
    leaves triage without a human approving the report.
  * Any guardrail failure (schema violation after repair, cost budget
    exceeded) routes to `human_review` instead of guessing.
"""

from __future__ import annotations

import json
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from . import config
from .costs import CostTracker, TrackingLLM
from .guardrails import SchemaViolation, call_with_repair, redact_pii
from .llm import get_llm
from .models import (
    Classification,
    Enrichment,
    IncidentReport,
    NodeCost,
    Priority,
    TriageReport,
)

CLASSIFY_SYSTEM = """You classify the incident report of a UK facilities \
and security operation. Respond with ONLY JSON: {"category": one of \
["physical_security","cyber","safety","operational","environmental"], \
"severity": one of ["low","medium","high","critical"], "summary": string \
(max 280 chars), "people_at_risk": boolean}."""

ACTIONS_SYSTEM = """You draft recommended actions for a triaged incident. \
Respond with ONLY a JSON array of 2-5 short imperative action strings, \
specific to the category and priority given."""


class TriageState(TypedDict, total=False):
    incident: dict
    classification: dict
    enrichment: dict
    priority: dict
    report: dict
    costs: list[dict]
    error: str


def _load_sites() -> dict:
    return json.loads(config.ASSETS_FILE.read_text(encoding="utf-8"))


def build_graph(llm=None, checkpointer=None):
    base_llm = llm or get_llm()
    tracker = CostTracker(base_llm.name)
    tracked = TrackingLLM(base_llm, tracker)
    sites = _load_sites()

    def classify(state: TriageState) -> TriageState:
        tracked.current_node = "classify"
        # classify is the entry node: reset the tracker so state["costs"]
        # is per-incident (a multi-worker deployment would key by thread_id)
        tracker.entries.clear()
        incident = IncidentReport.model_validate(state["incident"])
        clean_text = redact_pii(incident.text)
        try:
            result = call_with_repair(
                tracked, CLASSIFY_SYSTEM,
                f"INCIDENT REPORT: {clean_text}", Classification,
            )
        except SchemaViolation as exc:
            return {"error": f"classification failed schema validation: {exc}"}
        return {"classification": result.model_dump(),
                "costs": [e.model_dump() for e in tracker.entries]}

    def enrich(state: TriageState) -> TriageState:
        # deterministic tool call: site registry lookup, no LLM involved
        incident = IncidentReport.model_validate(state["incident"])
        site = sites.get(incident.site)
        if site is None:
            return {"error": f"unknown site {incident.site!r}"}
        category = state["classification"]["category"]
        enrichment = Enrichment(
            site_name=site["name"],
            site_criticality=site["criticality"],
            related_procedures=site["procedures"].get(category, []),
            prior_incidents_at_site=site["prior_incidents"],
        )
        return {"enrichment": enrichment.model_dump()}

    def prioritise(state: TriageState) -> TriageState:
        cls = Classification.model_validate(state["classification"])
        level, sla = config.PRIORITY_MATRIX[(cls.severity, cls.people_at_risk)]
        # policy bump: critical sites move one level up
        if state["enrichment"]["site_criticality"] == "critical" and level != "P1":
            level = f"P{int(level[1]) - 1}"
            sla = {"P1": 15, "P2": 60, "P3": 240}[level]
        priority = Priority(
            level=level,
            rationale=(
                f"severity={cls.severity}, people_at_risk={cls.people_at_risk}, "
                f"site_criticality={state['enrichment']['site_criticality']}"
            ),
            response_sla_minutes=sla,
        )
        return {"priority": priority.model_dump()}

    def draft(state: TriageState) -> TriageState:
        tracked.current_node = "draft"
        if tracker.over_budget:
            return {"error": f"cost budget exceeded (${tracker.total_usd})"}
        prompt = (
            f"category: {state['classification']['category']}\n"
            f"priority: {state['priority']['level']}\n"
            f"summary: {state['classification']['summary']}"
        )
        raw = tracked.complete(ACTIONS_SYSTEM, prompt)
        try:
            actions = json.loads(raw)
            assert isinstance(actions, list) and actions
        except (json.JSONDecodeError, AssertionError):
            actions = ["Review incident manually; drafting agent returned invalid output"]
        report = TriageReport(
            incident_id=state["incident"]["incident_id"],
            classification=Classification.model_validate(state["classification"]),
            enrichment=Enrichment.model_validate(state["enrichment"]),
            priority=Priority.model_validate(state["priority"]),
            recommended_actions=[str(a) for a in actions][:5],
        )
        return {"report": report.model_dump(),
                "costs": [e.model_dump() for e in tracker.entries]}

    def dispatch(state: TriageState) -> TriageState:
        report = dict(state["report"])
        report["status"] = "approved"
        return {"report": report}

    def human_review(state: TriageState) -> TriageState:
        return state  # terminal: the error is surfaced to an operator

    def route_after(key: str):
        def _route(state: TriageState) -> str:
            return "human_review" if state.get("error") else key
        return _route

    graph = StateGraph(TriageState)
    graph.add_node("classify", classify)
    graph.add_node("enrich", enrich)
    graph.add_node("prioritise", prioritise)
    graph.add_node("draft", draft)
    graph.add_node("dispatch", dispatch)
    graph.add_node("human_review", human_review)

    graph.set_entry_point("classify")
    graph.add_conditional_edges("classify", route_after("enrich"))
    graph.add_conditional_edges("enrich", route_after("prioritise"))
    graph.add_edge("prioritise", "draft")
    graph.add_conditional_edges("draft", route_after("dispatch"))
    graph.add_edge("dispatch", END)
    graph.add_edge("human_review", END)

    return graph.compile(
        checkpointer=checkpointer or MemorySaver(),
        interrupt_before=["dispatch"],  # human-in-the-loop gate
    )


def triage_incident(app, incident: IncidentReport, thread_id: str) -> TriageState:
    """Run triage up to the human gate; returns the pending state."""
    cfg = {"configurable": {"thread_id": thread_id}}
    return app.invoke({"incident": incident.model_dump()}, cfg)


def approve(app, thread_id: str) -> TriageState:
    """Resume past the interrupt: the human has approved dispatch."""
    cfg = {"configurable": {"thread_id": thread_id}}
    return app.invoke(None, cfg)
