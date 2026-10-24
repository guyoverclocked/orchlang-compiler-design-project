"""Export run records as content-free OpenTelemetry GenAI spans.

Each model call becomes a span with the attributes the OpenTelemetry GenAI semantic
conventions recommend when message content is not captured
(gen_ai.operation.name, gen_ai.request.model, gen_ai.response.model,
gen_ai.usage.input_tokens, gen_ai.usage.output_tokens) plus its duration; each tool
call becomes an execute_tool span with gen_ai.tool.name. Prompt and response text,
and the analysis-only fields of the run records (dummy flag, call site, natural
length), are not exported. This is exactly the attacker's view in the paper.

Usage: python experiments/export_otel.py RUN_DIR/ours.jsonl OUT.jsonl
"""
from __future__ import annotations

import hashlib
import json
import sys


def spans(rec):
    trace_id = hashlib.sha256(rec["id"].encode()).hexdigest()[:32]
    t = 0
    for k, (kind, name, i, o, lat, _dummy, _site, _nat) in enumerate(rec["trace"]):
        dur = int(lat * 1e9)
        span = {"trace_id": trace_id, "span_id": f"{k:016x}", "start_time_unix_nano": t,
                "end_time_unix_nano": t + dur}
        if kind == "llm":
            span["name"] = f"chat {name}"
            span["attributes"] = {"gen_ai.operation.name": "chat", "gen_ai.request.model": name,
                                  "gen_ai.response.model": name, "gen_ai.usage.input_tokens": i,
                                  "gen_ai.usage.output_tokens": o}
        else:
            span["name"] = f"execute_tool {name}"
            span["attributes"] = {"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": name}
        t += dur
        yield span


def main():
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8") as f, open(dst, "w", encoding="utf-8") as g:
        for line in f:
            if line.strip():
                for s in spans(json.loads(line)):
                    g.write(json.dumps(s) + "\n")


if __name__ == "__main__":
    main()
