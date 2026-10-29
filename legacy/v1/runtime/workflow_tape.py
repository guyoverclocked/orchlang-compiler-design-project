"""Conformance-only replay of captured actual model outcomes.

This performs zero inference. An exact complete request/schema/cap match is
required before any response is returned; all recorded calls must be consumed.
It tests a port under common captured outcomes and cannot establish independent
model determinism or universal semantic equivalence.
"""
import copy
import json
from .local_model import render_messages, effective_output_cap


def key(request, schema, cap):
    return request, json.dumps(schema, sort_keys=True), cap


class CapturedTape:
    def __init__(self, trace, *, output_cap, allow_reorder=False):
        if not trace or any(e["status"] != "ok" for e in trace):
            raise ValueError("only complete successful actual traces can be replayed")
        self.remaining = list(enumerate(copy.deepcopy(trace)))
        self.trace, self.output_cap, self.actual_generation_calls = [], output_cap, 0
        self.allow_reorder = allow_reorder

    def generate(self, *, prompt=None, messages=None, schema=None, upstream_cap=None):
        if (prompt is None) == (messages is None):
            raise ValueError("exactly one request representation required")
        request = prompt if prompt is not None else render_messages(messages)
        cap = effective_output_cap(self.output_cap, upstream_cap)
        desired = key(request, schema, cap)
        candidates = self.remaining if self.allow_reorder else self.remaining[:1]
        found = [(position, original_index, e) for position, (original_index, e) in enumerate(candidates)
                 if key(e["rendered_request"], e["schema"], e["output_cap"]) == desired]
        if not found:
            raise ValueError("port request/schema/cap does not exactly match an unconsumed original generation")
        position, original_index, event = found[0]
        self.remaining.pop(position)
        event["source_actual_attempt"] = original_index + 1
        event["conformance_replay"] = True
        event["attempt"] = len(self.trace) + 1
        self.trace.append(event)
        return event["response"]

    def finish(self):
        if self.remaining:
            raise ValueError("port omitted one or more captured original calls")
        return dict(replay_calls=len(self.trace), actual_generation_calls=0,
                    exact_requests_matched=len(self.trace), all_original_calls_consumed=True,
                    ordering="independent parallel calls only" if self.allow_reorder else "strict source call order")
