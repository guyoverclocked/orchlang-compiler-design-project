"""Configuration: provider selection, pricing, and the priority policy."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS_FILE = ROOT / "data" / "sites.json"
SAMPLE_INCIDENTS = ROOT / "data" / "sample_incidents.jsonl"
GOLDEN_FILE = ROOT / "eval" / "golden_trajectories.jsonl"

# "openai" | "mock" (mock = deterministic rules, used in tests/CI)
LLM_PROVIDER = os.environ.get("TRIAGE_LLM", "mock")
OPENAI_MODEL = os.environ.get("TRIAGE_OPENAI_MODEL", "gpt-4o-mini")

# USD per 1M tokens, used by the cost tracker.
PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "mock": {"input": 0.0, "output": 0.0},
}

# Hard budget per incident; the graph aborts to human review if exceeded.
MAX_COST_PER_INCIDENT_USD = 0.05

# Deterministic priority policy. The LLM assesses severity and risk; the
# PRIORITY of the response is a business rule and never delegated to a
# language model.
#   (severity, people_at_risk) -> (level, SLA minutes)
PRIORITY_MATRIX = {
    ("critical", True): ("P1", 15),
    ("critical", False): ("P1", 15),
    ("high", True): ("P1", 15),
    ("high", False): ("P2", 60),
    ("medium", True): ("P2", 60),
    ("medium", False): ("P3", 240),
    ("low", True): ("P3", 240),
    ("low", False): ("P4", 1_440),
}
