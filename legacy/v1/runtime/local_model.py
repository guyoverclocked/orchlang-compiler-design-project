"""Pinned, fully rendered local CPU generation with fail-closed admission.

This is an experimental deployment adapter, outside the Lean theorem. Requests
are stateless and raw: no implicit Ollama system prompt or chat template is used.
The pinned tokenizer must agree with the server's reported prompt token count.
"""
import hashlib
import importlib.metadata
import json
import threading
import time
import urllib.request


MODEL = "qwen2.5:3b"
MODEL_DIGEST = "357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b"
SERIALIZER = "explicit-qwen-chatml-v1"


class AdmissionError(ValueError):
    pass


def effective_output_cap(deployment_cap, upstream_cap):
    if type(deployment_cap) is not int or deployment_cap < 1:
        raise ValueError("positive integer deployment output cap required")
    if upstream_cap is not None and (type(upstream_cap) is not int or upstream_cap < 1):
        raise ValueError("upstream output cap must be None or a positive integer")
    return deployment_cap if upstream_cap is None else min(deployment_cap, upstream_cap)


def render_messages(messages):
    """Qwen ChatML, explicit assistant prefix; no default system message."""
    if not messages or any(set(m) != {"role", "content"} for m in messages):
        raise ValueError("messages must explicitly contain only role/content")
    if any(m["role"] not in {"system", "user", "assistant"} or
           not isinstance(m["content"], str) for m in messages):
        raise ValueError("unsupported message")
    return "".join("<|im_start|>" + m["role"] + "\n" + m["content"] +
                   "<|im_end|>\n" for m in messages) + "<|im_start|>assistant\n"


class LocalModel:
    def __init__(self, tokenizer_file, tokenizer_sha256, endpoint="http://127.0.0.1:11434",
                 model=MODEL, digest=MODEL_DIGEST, expected_tokenizers_version="0.21.4"):
        from tokenizers import Tokenizer
        from pathlib import Path
        data = Path(tokenizer_file).read_bytes()
        if hashlib.sha256(data).hexdigest() != tokenizer_sha256:
            raise ValueError("pinned tokenizer hash mismatch")
        if importlib.metadata.version("tokenizers") != expected_tokenizers_version:
            raise ValueError("pinned tokenizers dependency version mismatch")
        configuration = json.loads(data)
        if configuration.get("truncation") is not None or configuration.get("padding") is not None:
            raise ValueError("tokenizer padding/truncation forbidden")
        self.tokenizer = Tokenizer.from_str(data.decode("utf-8"))
        self.tokenizer_sha256 = tokenizer_sha256
        self.endpoint, self.model, self.digest = endpoint, model, digest
        self.lock = threading.RLock()
        self.trace, self.attempts = [], 0
        self.input_cap, self.output_cap, self.max_calls, self.seed = 512, 64, 3, 1
        tags = self.api("/api/tags")
        match = [m for m in tags["models"] if m["name"] == model]
        if len(match) != 1 or match[0]["digest"] != digest:
            raise ValueError("local model manifest digest mismatch")
        self.identity = dict(model=model, model_manifest_sha256=digest,
                             tokenizer_sha256=tokenizer_sha256,
                             tokenizers_version=expected_tokenizers_version,
                             serializer=SERIALIZER,
                             serializer_sha256=hashlib.sha256(render_messages([
                                 {"role": "user", "content": "{content}"}]).encode()).hexdigest(),
                             ollama_version=self.api("/api/version"),
                             model_details=match[0]["details"], device="CPU",
                             truncation="forbidden; compare entire input count to server",
                             special_tokens="tokenizer.json; add_special_tokens=False",
                             hidden_system_prompt=False, implicit_conversation_state=False,
                             retries=0, threads=4)

    def api(self, path, data=None):
        body = None if data is None else json.dumps(data).encode("utf-8")
        req = urllib.request.Request(self.endpoint + path, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=240) as response:
            return json.load(response)

    def begin(self, *, input_cap, output_cap, max_calls, seed):
        if any(type(n) is not int or n < 1 for n in (input_cap, output_cap, max_calls, seed)):
            raise ValueError("positive integer contract required")
        self.input_cap, self.output_cap = input_cap, output_cap
        self.max_calls, self.seed = max_calls, seed
        self.trace, self.attempts = [], 0

    def generate(self, *, prompt=None, messages=None, schema=None, upstream_cap=None):
        if (prompt is None) == (messages is None):
            raise ValueError("exactly one of prompt/messages required")
        rendered = prompt if prompt is not None else render_messages(messages)
        ids = self.tokenizer.encode(rendered, add_special_tokens=False).ids
        effective_cap = effective_output_cap(self.output_cap, upstream_cap)
        with self.lock:
            if len(ids) > self.input_cap:
                raise AdmissionError(f"constructed input {len(ids)} exceeds {self.input_cap}")
            if len(ids) + effective_cap > 4096:
                raise AdmissionError("context admission failed")
            if self.attempts >= self.max_calls:
                raise AdmissionError("call-count admission failed")
            self.attempts += 1
            body = dict(model=self.model, prompt=rendered, raw=True, stream=False,
                        keep_alive="30m", options=dict(num_predict=effective_cap,
                            num_ctx=4096, temperature=0, seed=self.seed,
                            num_gpu=0, num_thread=4, repeat_penalty=1.0))
            if schema is not None:
                body["format"] = schema
            event = dict(attempt=self.attempts, messages=messages, completion_prompt=prompt,
                         rendered_request=rendered, request_token_ids=ids,
                         tokenizer_input_tokens=len(ids), input_cap=self.input_cap,
                         output_cap=effective_cap, schema=schema, http_body=body,
                         status="pending")
            self.trace.append(event)
            start = time.perf_counter()
            try:
                result = self.api("/api/generate", body)
                event.update(response=result["response"], server_input_tokens=result["prompt_eval_count"],
                             generated_tokens=result["eval_count"],
                             response_reencoded_tokens=len(self.tokenizer.encode(
                                 result["response"], add_special_tokens=False).ids),
                             done_reason=result.get("done_reason"),
                             server_metadata={k: v for k, v in result.items() if k != "response"},
                             elapsed_seconds=time.perf_counter() - start, status="ok")
                if len(ids) != result["prompt_eval_count"]:
                    raise ValueError("server/tokenizer full-request count disagreement or truncation")
                if result["eval_count"] > effective_cap:
                    raise ValueError("server output cap violated")
                return result["response"]
            except Exception as error:
                event.update(status="error", error=repr(error), elapsed_seconds=time.perf_counter()-start)
                raise

    def totals(self):
        complete = len(self.trace) == self.attempts and all(
            e["status"] == "ok" and "server_input_tokens" in e and "generated_tokens" in e
            for e in self.trace)
        recorded_input = sum(e.get("server_input_tokens", 0) for e in self.trace)
        recorded_output = sum(e.get("generated_tokens", 0) for e in self.trace)
        return dict(calls=self.attempts, usage_complete=complete,
                    usage_unconfirmed_attempts=sum(e["status"] != "ok" for e in self.trace),
                    input=recorded_input if complete else None,
                    output=recorded_output if complete else None,
                    recorded_input=recorded_input, recorded_output=recorded_output,
                    runtime_bound=self.max_calls*(self.input_cap+self.output_cap),
                    max_call_bound=self.max_calls,
                    guard="fully rendered exact input admission + output cap + maximum calls",
                    whole_source_static_token_bound=False)
