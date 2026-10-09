"""FastAPI layer: submit an incident, review the pending report, approve it.

    uvicorn triage.api:app --app-dir src --port 8090
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .graph import approve, build_graph, triage_incident
from .models import IncidentReport

app = FastAPI(
    title="Incident Triage Agents",
    description="Multi-agent triage with guardrails, cost tracking and human approval.",
    version="1.0.0",
)

_state: dict = {}


def _graph():
    if "app" not in _state:
        _state["app"] = build_graph()
    return _state["app"]


@app.get("/health")
def health() -> dict:
    _graph()
    return {"status": "ok"}


@app.post("/triage")
def submit(incident: IncidentReport) -> dict:
    state = triage_incident(_graph(), incident, thread_id=incident.incident_id)
    if state.get("error"):
        return {"status": "human_review", "error": state["error"]}
    report = state["report"]
    return {
        "status": report["status"],  # pending_approval
        "report": report,
        "cost_usd": round(sum(c["cost_usd"] for c in state.get("costs", [])), 6),
        "approve_via": f"/approve/{incident.incident_id}",
    }


@app.post("/approve/{incident_id}")
def approve_incident(incident_id: str) -> dict:
    try:
        state = approve(_graph(), thread_id=incident_id)
    except Exception as exc:  # unknown thread or already completed
        raise HTTPException(404, f"no pending triage for {incident_id!r}: {exc}")
    if not state.get("report"):
        raise HTTPException(409, "triage ended in human_review; nothing to approve")
    return {"status": state["report"]["status"], "report": state["report"]}
