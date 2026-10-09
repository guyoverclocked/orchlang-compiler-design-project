"""Rejected: direct secret values cannot enter modeled request content."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from integrations.langgraph.source_frontend.runtime import request, tokens


class State(TypedDict):
    secret_text: str
    answer: str


def call_model(state):
    answer = request(model="writer", template="summarize", arguments=[state["secret_text"]])
    return {"answer": answer}


builder = StateGraph(State)
builder.add_node("call", call_model)
builder.add_edge(START, "call")
builder.add_edge("call", END)
app = builder.compile()
