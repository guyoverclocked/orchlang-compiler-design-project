"""Per-node token and cost tracking.

Tokens are estimated at ~4 characters/token (close enough for budget
enforcement; exact counts come from the API response in production).
The graph checks the running total against MAX_COST_PER_INCIDENT_USD and
aborts to human review if an incident starts burning money.
"""

from __future__ import annotations

from .config import MAX_COST_PER_INCIDENT_USD, PRICING
from .models import NodeCost


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class CostTracker:
    def __init__(self, model: str) -> None:
        self.model = model
        self.entries: list[NodeCost] = []

    def record(self, node: str, prompt: str, completion: str) -> NodeCost:
        pricing = PRICING.get(self.model, PRICING["mock"])
        input_tokens = estimate_tokens(prompt)
        output_tokens = estimate_tokens(completion)
        cost = (
            input_tokens * pricing["input"] + output_tokens * pricing["output"]
        ) / 1_000_000
        entry = NodeCost(
            node=node, input_tokens=input_tokens,
            output_tokens=output_tokens, cost_usd=round(cost, 6),
        )
        self.entries.append(entry)
        return entry

    @property
    def total_usd(self) -> float:
        return round(sum(e.cost_usd for e in self.entries), 6)

    @property
    def over_budget(self) -> bool:
        return self.total_usd > MAX_COST_PER_INCIDENT_USD


class TrackingLLM:
    """Wraps a provider so every call is recorded against a node name."""

    def __init__(self, llm, tracker: CostTracker) -> None:
        self._llm = llm
        self.tracker = tracker
        self.current_node = "unknown"

    @property
    def name(self) -> str:
        return self._llm.name

    def complete(self, system: str, user: str) -> str:
        out = self._llm.complete(system, user)
        self.tracker.record(self.current_node, system + user, out)
        return out
