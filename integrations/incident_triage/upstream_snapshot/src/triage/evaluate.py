"""Trajectory evaluation: run every golden incident through the graph and
score category, priority and procedure attachment.

Run: python -m triage.evaluate

Agent demos usually show one happy path; this scores the whole golden set
and CI fails if the trajectory accuracy regresses.
"""

from __future__ import annotations

import json

from . import config
from .graph import build_graph, triage_incident
from .models import IncidentReport


def load_jsonl(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").strip().splitlines()]


def main() -> None:
    incidents = {i["incident_id"]: i for i in load_jsonl(config.SAMPLE_INCIDENTS)}
    golden = load_jsonl(config.GOLDEN_FILE)

    app = build_graph()
    rows = []
    for item in golden:
        incident = IncidentReport.model_validate(incidents[item["incident_id"]])
        state = triage_incident(app, incident, thread_id=f"eval-{incident.incident_id}")
        report = state.get("report")
        if report is None:
            rows.append({**item, "category_ok": False, "priority_ok": False,
                         "procedure_ok": False, "error": state.get("error", "no report")})
            continue
        rows.append(
            {
                **item,
                "got_category": report["classification"]["category"],
                "got_priority": report["priority"]["level"],
                "category_ok": report["classification"]["category"] == item["expected_category"],
                "priority_ok": report["priority"]["level"] == item["expected_priority"],
                "procedure_ok": item["expected_procedure"]
                in report["enrichment"]["related_procedures"],
                "cost_usd": sum(c["cost_usd"] for c in state.get("costs", [])),
            }
        )

    n = len(rows)
    summary = {
        "n_incidents": n,
        "category_accuracy": round(sum(r["category_ok"] for r in rows) / n, 3),
        "priority_accuracy": round(sum(r["priority_ok"] for r in rows) / n, 3),
        "procedure_attachment_rate": round(sum(r["procedure_ok"] for r in rows) / n, 3),
        "llm": config.LLM_PROVIDER,
    }
    out = config.ROOT / "eval" / "results.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")

    for row in rows:
        flags = "".join("Y" if row[k] else "N" for k in ("category_ok", "priority_ok", "procedure_ok"))
        print(f"{row['incident_id']}  [{flags}]  "
              f"{row.get('got_category', '-'):18} {row.get('got_priority', '-')}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
