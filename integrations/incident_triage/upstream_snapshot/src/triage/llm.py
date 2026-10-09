"""LLM providers. The mock provider is deterministic and rule-based so the
full graph, guardrails, cost tracking and trajectory evaluation run
offline; it deliberately mimics an imperfect model (it only knows JSON
for the prompts it recognises)."""

from __future__ import annotations

import json
import re

from . import config

KEYWORDS = {
    "cyber": ["phishing", "malware", "ransomware", "password", "login",
              "laptop", "usb", "email", "server", "network"],
    "physical_security": ["intruder", "break-in", "forced", "tailgat",
                          "unauthorised", "unauthorized", "theft", "stolen",
                          "fence", "gate", "cctv", "trespass", "badge"],
    "safety": ["injury", "injured", "fall", "fell", "burn", "chemical",
               "spill", "forklift", "unconscious", "ambulance", "slipped"],
    "environmental": ["leak", "flood", "fumes", "asbestos", "contamination",
                      "oil", "smoke"],
}

SEVERITY_MARKERS = {
    "critical": ["unconscious", "ambulance", "ransomware", "armed", "fire",
                 "explosion", "hospital"],
    "high": ["injury", "injured", "intruder", "break-in", "stolen", "breach",
             "chemical", "asbestos"],
    "medium": ["phishing", "tailgat", "spill", "leak", "near miss",
               "unauthorised", "unauthorized", "credential"],
}

RISK_MARKERS = ["injur", "unconscious", "ambulance", "fumes", "armed",
                "fire", "evacuat", "chemical", "hospital"]


class MockLLM:
    """Deterministic stand-in that answers the graph's prompts with JSON."""

    name = "mock"

    def complete(self, system: str, user: str) -> str:
        text = user.lower()
        if "classify the incident" in system.lower():
            return self._classify(text)
        if "recommended actions" in system.lower():
            return self._actions(text)
        return "{}"

    @staticmethod
    def _classify(text: str) -> str:
        scores = {
            cat: sum(1 for kw in kws if kw in text) for cat, kws in KEYWORDS.items()
        }
        category = max(scores, key=scores.get) if any(scores.values()) else "operational"

        severity = "low"
        for level in ("critical", "high", "medium"):
            if any(m in text for m in SEVERITY_MARKERS[level]):
                severity = level
                break

        summary = re.sub(r"\s+", " ", text.split("incident report:")[-1]).strip()
        return json.dumps(
            {
                "category": category,
                "severity": severity,
                "summary": summary[:280],
                "people_at_risk": any(m in text for m in RISK_MARKERS),
            }
        )

    @staticmethod
    def _actions(text: str) -> str:
        actions = ["Log the incident and notify the site duty manager"]
        if "p1" in text or "critical" in text:
            actions.append("Escalate to the on-call incident commander immediately")
        if "cyber" in text:
            actions.append("Isolate affected devices and reset exposed credentials")
        if "safety" in text:
            actions.append("Preserve the scene and complete a RIDDOR assessment")
        if "physical_security" in text:
            actions.append("Review CCTV and secure the affected entry point")
        if "environmental" in text:
            actions.append("Contain the release and check ventilation before re-entry")
        return json.dumps(actions)


class OpenAILLM:
    name = config.OPENAI_MODEL

    def __init__(self) -> None:
        from openai import OpenAI

        self._client = OpenAI()

    def complete(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""


def get_llm():
    if config.LLM_PROVIDER == "openai":
        return OpenAILLM()
    return MockLLM()
