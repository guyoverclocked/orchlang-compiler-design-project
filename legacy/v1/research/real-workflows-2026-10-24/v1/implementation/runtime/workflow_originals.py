"""Original-framework execution and explicit host composition for real workflows.

Upstream source files/snippets are hash checked by the experiment driver. The
only provider is the shared pinned local adapter. No graph predicate, source
prompt, response binding, aggregation or cleansing is deleted to fit OrchLang.
The non-OrchLang operations of hybrid ports are visible below.
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import threading
import time
import types

from .workflow_kernels import Kernel


class LangGraphModel:
    def __init__(self, backend, schema=None):
        self.backend, self.schema = backend, schema

    def invoke(self, value):
        from langchain_core.messages import AIMessage
        if isinstance(value, str):
            messages = [{"role": "user", "content": value}]
        else:
            roles = {"human": "user", "ai": "assistant", "system": "system"}
            messages = [{"role": roles[m.type], "content": m.content} for m in value]
        text = self.backend.generate(messages=messages,
            schema=None if self.schema is None else self.schema.model_json_schema())
        if self.schema is not None:
            return self.schema.model_validate_json(text)
        return AIMessage(content=text)

    def with_structured_output(self, schema):
        return LangGraphModel(self.backend, schema)


@contextmanager
def openai_bridge(backend):
    """Local OpenAI wire shim; original Prompt Flow tools/engine remain in use."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                text = backend.generate(
                    prompt=request.get("prompt"), messages=request.get("messages"),
                    upstream_cap=request.get("max_tokens"))
                event = backend.trace[-1]
                choice = dict(index=0, finish_reason="length" if event["done_reason"] == "length" else "stop")
                if "messages" in request:
                    choice["message"] = {"role": "assistant", "content": text}
                    obj = "chat.completion"
                else:
                    choice["text"] = text
                    choice["logprobs"] = None
                    obj = "text_completion"
                payload = dict(id="local-"+str(event["attempt"]), object=obj,
                    created=int(time.time()), model=backend.model, choices=[choice],
                    usage=dict(prompt_tokens=event["server_input_tokens"],
                        completion_tokens=event["generated_tokens"],
                        total_tokens=event["server_input_tokens"]+event["generated_tokens"]))
                self.send_response(200)
            except Exception as error:
                payload = {"error": {"message": repr(error), "type": "local_adapter_error"}}
                self.send_response(400)
            data = json.dumps(payload).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown(); server.server_close(); thread.join()


def original_langgraph(case, values, corpus_dir, backend):
    from typing_extensions import TypedDict
    from pydantic import BaseModel, Field
    from langgraph.graph import StateGraph, START, END
    env = dict(llm=LangGraphModel(backend), TypedDict=TypedDict, BaseModel=BaseModel,
               Field=Field, StateGraph=StateGraph, START=START, END=END, __name__="upstream_workflow")
    path = corpus_dir/case["executable"]
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), env)
    case_id = case["id"]
    if case_id == "lg-chain-graph":
        return env["chain"].invoke(values)
    if case_id == "lg-chain-functional":
        return env["prompt_chaining_workflow"].invoke(values["topic"])
    if case_id == "lg-parallel-graph":
        return env["parallel_workflow"].invoke(values)
    if case_id == "lg-routing-graph":
        return env["router_workflow"].invoke(values)
    raise ValueError("unknown upstream LangGraph case")


def original_promptflow(case, values, sources, backend):
    from promptflow.executor import FlowExecutor
    from promptflow.connections import OpenAIConnection
    flow = sources/"microsoft--promptflow"/Path(case["source"]["path"]).parent
    with openai_bridge(backend) as url:
        # Dummy values only: the wire shim never contacts OpenAI/Azure.
        keys = {"AZURE_OPENAI_API_KEY": "sk-local-dummy", "AZURE_OPENAI_API_BASE": url,
                "OPENAI_BASE_URL": url, "PF_DISABLE_TRACING": "true"}
        prior = {key: os.environ.get(key) for key in keys}
        os.environ.update(keys)
        try:
            connection = OpenAIConnection(name="open_ai_connection", api_key="sk-local-dummy", base_url=url)
            executor = FlowExecutor.create(flow/"flow.dag.yaml",
                connections={"open_ai_connection": connection._to_execution_connection_dict()},
                working_dir=flow, raise_ex=True)
            result = executor.exec_line(values, node_concurrency=1)
            if result.run_info.status != "Completed":
                raise RuntimeError(f"Prompt Flow execution status {result.run_info.status}: {result.run_info.error}")
            return result.output
        finally:
            for key, value in prior.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def port(case, values, corpus_dir, backend):
    def call(name, **bindings):
        kernel = Kernel((corpus_dir/(name+".orch")).read_text(encoding="utf-8"))
        return kernel.run(bindings, backend)
    case_id = case["id"]
    if case_id in {"lg-chain-graph", "lg-chain-functional"}:
        topic = values["topic"]
        joke = call("first", topic=topic)
        punctuation = "?" in joke or "!" in joke
        # These two upstream Python examples have opposite gates. Preserve both.
        improve = (not punctuation) if case_id == "lg-chain-graph" else punctuation
        state = dict(topic=topic, joke=joke)
        if improve:
            kernel = Kernel((corpus_dir/"refine.orch").read_text(encoding="utf-8"))
            polished = kernel.run({"joke": joke}, backend)
            better = kernel.last_env["better"]
            state.update(improved_joke=better, final_joke=polished)
        return state if case_id == "lg-chain-graph" else state.get("final_joke", joke)
    if case_id == "lg-parallel-graph":
        # A CPU deployment serializes inference. The original graph still
        # schedules concurrent nodes; this host port preserves output/dataflow
        # but intentionally does not promise schedule or latency equivalence.
        topic = values["topic"]
        joke, story, poem = (call(n, topic=topic) for n in ("joke", "story", "poem"))
        combined = (f"Here's a story, joke, and poem about {topic}!\n\n"
                    f"STORY:\n{story}\n\nJOKE:\n{joke}\n\nPOEM:\n{poem}")
        return dict(topic=topic, joke=joke, story=story, poem=poem, combined_output=combined)
    if case_id == "lg-routing-graph":
        from typing_extensions import Literal
        from pydantic import BaseModel, Field
        class Route(BaseModel):
            step: Literal["poem", "story", "joke"] = Field(
                None, description="The next step in the routing process")
        schema = Route.model_json_schema()
        raw = Kernel((corpus_dir/"route.orch").read_text(encoding="utf-8")).run(
            {"request": values["input"]}, backend, schema=schema)
        decision = Route.model_validate_json(raw).step
        if decision not in {"poem", "story", "joke"}:
            raise ValueError("invalid router decision")
        output = call("respond", request=values["input"])
        return dict(input=values["input"], decision=decision, output=output)
    if case_id == "pf-basic":
        return {"output": call("basic", language=values["text"])}
    if case_id == "pf-ner":
        raw = call("ner", entity_type=values["entity_type"], document=values["text"])
        # Independently implemented equivalent of the upstream cleansing tool.
        entities = [item.strip(' \t."') for item in raw.split(",")]
        return {"entities": [item for item in entities if item]}
    raise ValueError("unknown executable port")
