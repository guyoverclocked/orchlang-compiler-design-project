import pytest

from triage.guardrails import (
    SchemaViolation,
    call_with_repair,
    parse_structured,
    redact_pii,
)
from triage.models import Classification


def test_pii_redaction():
    text = ("Contact john.smith@corp.example or 0191 496 0000, "
            "NI number QQ 12 34 56 C, about the intruder.")
    redacted = redact_pii(text)
    assert "[EMAIL]" in redacted and "[PHONE]" in redacted and "[NI-NUMBER]" in redacted
    assert "john.smith" not in redacted and "0191" not in redacted
    assert "intruder" in redacted  # content survives


def test_parse_structured_accepts_fenced_json():
    raw = '```json\n{"category": "cyber", "severity": "high", "summary": "s", "people_at_risk": false}\n```'
    parsed = parse_structured(raw, Classification)
    assert parsed.category == "cyber"


def test_parse_structured_rejects_bad_enum():
    raw = '{"category": "alien_invasion", "severity": "high", "summary": "s", "people_at_risk": false}'
    with pytest.raises(SchemaViolation):
        parse_structured(raw, Classification)


class FlakyLLM:
    """Fails once, then produces valid JSON: the repair path."""

    name = "flaky"

    def __init__(self):
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        if self.calls == 1:
            return "sorry, here is some prose instead of JSON"
        assert "failed validation" in user  # repair prompt includes the error
        return '{"category": "safety", "severity": "low", "summary": "s", "people_at_risk": false}'


class HopelessLLM:
    name = "hopeless"

    def complete(self, system, user):
        return "still not json"


def test_repair_loop_recovers_once():
    llm = FlakyLLM()
    result = call_with_repair(llm, "sys", "user", Classification)
    assert result.category == "safety"
    assert llm.calls == 2


def test_repair_loop_gives_up_after_second_failure():
    with pytest.raises(SchemaViolation):
        call_with_repair(HopelessLLM(), "sys", "user", Classification)
