"""Guardrails: PII redaction on the way in, schema enforcement on the way out.

Structured output discipline: the LLM is asked for JSON matching a
Pydantic schema; a response that fails validation gets ONE repair attempt
with the validation error included, then the incident is routed to human
review rather than guessed at.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"(?:\+44\s?|0)\d{2,4}[\s-]?\d{3}[\s-]?\d{3,4}")
NI_NUMBER_RE = re.compile(r"\b[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-Z]\b")


def redact_pii(text: str) -> str:
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    return NI_NUMBER_RE.sub("[NI-NUMBER]", text)


class SchemaViolation(Exception):
    """Raised when the LLM cannot produce valid output after repair."""


def parse_structured[T: BaseModel](raw: str, schema: type[T]) -> T:
    """Parse an LLM response into `schema`, tolerating markdown fences."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.S)
    try:
        return schema.model_validate(json.loads(cleaned))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise SchemaViolation(str(exc)) from exc


def call_with_repair[T: BaseModel](llm, system: str, user: str, schema: type[T]) -> T:
    """One shot + one schema-guided repair attempt, then SchemaViolation."""
    first = llm.complete(system, user)
    try:
        return parse_structured(first, schema)
    except SchemaViolation as exc:
        repair_user = (
            f"{user}\n\nYour previous response failed validation with:\n{exc}\n"
            f"Respond again with ONLY valid JSON for the schema."
        )
        second = llm.complete(system, repair_user)
        return parse_structured(second, schema)  # raises if still invalid
