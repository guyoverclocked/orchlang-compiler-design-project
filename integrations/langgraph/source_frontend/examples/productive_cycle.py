"""Actual LangGraph example: one billable state can loop or terminate."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from integrations.langgraph.source_frontend.runtime import request, tokens


class State(TypedDict):
    question: str
    repeat: bool
    last: str


def generate(state):
    last = request(model="writer", template="cycle-v1", arguments=[state["question"]])
    return {"last": last}


def route(state):
    if state["repeat"]:
        return "again"
    return "done"


builder = StateGraph(State)
builder.add_node("generate", generate)
builder.add_edge(START, "generate")
builder.add_conditional_edges("generate", route, {"again": "generate", "done": END})
app = builder.compile()
