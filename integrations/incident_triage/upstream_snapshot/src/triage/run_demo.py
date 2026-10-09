"""Triage the sample incidents and show the full report + costs for one.

Run: python -m triage.run_demo
"""

from __future__ import annotations

import json

from . import config
from .graph import approve, build_graph, triage_incident
from .models import IncidentReport


def main() -> None:
    incidents = [
        json.loads(line)
        for line in config.SAMPLE_INCIDENTS.read_text(encoding="utf-8").strip().splitlines()
    ]
    app = build_graph()

    print(f"{'incident':10} {'category':18} {'sev':8} {'prio':4} {'SLA':>6}  actions")
    for raw in incidents:
        incident = IncidentReport.model_validate(raw)
        state = triage_incident(app, incident, thread_id=incident.incident_id)
        if state.get("error"):
            print(f"{incident.incident_id:10} -> human review: {state['error']}")
            continue
        report = state["report"]
        print(
            f"{incident.incident_id:10} {report['classification']['category']:18} "
            f"{report['classification']['severity']:8} {report['priority']['level']:4} "
            f"{report['priority']['response_sla_minutes']:>4}m  "
            f"{len(report['recommended_actions'])} drafted"
        )

    # walk one incident through the human gate
    first = IncidentReport.model_validate(incidents[1])
    state = triage_incident(app, first, thread_id="demo-approval")
    print(f"\n--- {first.incident_id} full report (status: {state['report']['status']}) ---")
    print(json.dumps(state["report"], indent=2))
    total = sum(c["cost_usd"] for c in state.get("costs", []))
    print(f"LLM cost for this incident: ${total:.6f} "
          f"({len(state.get('costs', []))} calls, budget ${config.MAX_COST_PER_INCIDENT_USD})")

    approved = approve(app, thread_id="demo-approval")
    print(f"after human approval: status = {approved['report']['status']}")


if __name__ == "__main__":
    main()
