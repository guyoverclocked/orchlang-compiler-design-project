"""Typed contracts between agents. Every hop in the graph is a Pydantic
model, so a malformed LLM response can never propagate downstream."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
    "physical_security", "cyber", "safety", "operational", "environmental"
]
Severity = Literal["low", "medium", "high", "critical"]


class IncidentReport(BaseModel):
    """Raw inbound report, as filed by a guard, sensor or employee."""

    incident_id: str
    site: str
    reported_by: str
    text: str = Field(..., min_length=10, max_length=4_000)


class Classification(BaseModel):
    category: Category
    severity: Severity
    summary: str = Field(..., max_length=300)
    people_at_risk: bool


class Enrichment(BaseModel):
    site_name: str
    site_criticality: Literal["standard", "sensitive", "critical"]
    related_procedures: list[str]
    prior_incidents_at_site: int


class Priority(BaseModel):
    level: Literal["P1", "P2", "P3", "P4"]
    rationale: str
    response_sla_minutes: int


class TriageReport(BaseModel):
    incident_id: str
    classification: Classification
    enrichment: Enrichment
    priority: Priority
    recommended_actions: list[str]
    status: Literal["pending_approval", "approved", "rejected"] = "pending_approval"


class NodeCost(BaseModel):
    node: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
