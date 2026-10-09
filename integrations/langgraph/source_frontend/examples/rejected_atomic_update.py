"""Rejected: a returned state update is atomic at node completion."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from integrations.langgraph.source_frontend.runtime import request, tokens


class State(TypedDict):
    question: str
    draft: str
    answer: str


def call_twice(state):
    draft = request(model="writer", template="draft", arguments=[state["question"]])
    answer = request(model="writer", template="answer", arguments=[state["draft"]])
    return {"draft": draft, "answer": answer}


builder = StateGraph(State)
builder.add_node("call", call_twice)
builder.add_edge(START, "call")
builder.add_edge("call", END)
app = builder.compile()
