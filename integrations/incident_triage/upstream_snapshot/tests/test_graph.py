from triage.graph import approve, build_graph, triage_incident
from triage.models import IncidentReport

INTRUSION = IncidentReport(
    incident_id="T-1",
    site="NCL-02",
    reported_by="guard",
    text="An intruder forced the gate and was seen near the server racks before fleeing.",
)


def test_full_trajectory_stops_at_human_gate(app):
    state = triage_incident(app, INTRUSION, thread_id="t1")
    report = state["report"]
    assert report["status"] == "pending_approval"
    assert report["classification"]["category"] == "physical_security"
    assert report["priority"]["level"] in {"P1", "P2"}
    assert report["enrichment"]["site_name"] == "Newcastle Data Hall"
    assert report["recommended_actions"]


def test_approval_resumes_past_interrupt(app):
    triage_incident(app, INTRUSION, thread_id="t2")
    approved = approve(app, thread_id="t2")
    assert approved["report"]["status"] == "approved"


def test_unknown_site_routes_to_human_review(app):
    incident = IncidentReport(
        incident_id="T-3", site="NOPE-99", reported_by="x",
        text="Something happened at a site that does not exist in the registry.",
    )
    state = triage_incident(app, incident, thread_id="t3")
    assert "error" in state and "unknown site" in state["error"]
    assert "report" not in state


def test_critical_site_bumps_priority(app):
    # medium severity, no people at risk -> P3 normally, P2 at a critical site
    incident = IncidentReport(
        incident_id="T-4", site="NCL-02", reported_by="reception",
        text="A person tailgated an employee through the turnstile and left when challenged.",
    )
    state = triage_incident(app, incident, thread_id="t4")
    assert state["report"]["priority"]["level"] == "P2"


def test_costs_are_tracked_per_incident(app):
    state = triage_incident(app, INTRUSION, thread_id="t5")
    costs = state["costs"]
    assert costs
    nodes = {c["node"] for c in costs}
    assert "classify" in nodes and "draft" in nodes
