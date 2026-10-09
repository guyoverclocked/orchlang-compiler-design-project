"""Graph-check rejection: a secret choice changes the exact template."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from integrations.langgraph.source_frontend.runtime import request, tokens


class State(TypedDict):
    private_route: bool
    answer: str


def choose(state):
    return {}


def left(state):
    answer = request(model="writer", template="left-template", arguments=["same"])
    return {"answer": answer}


def right(state):
    answer = request(model="writer", template="right-template", arguments=["same"])
    return {"answer": answer}


def route(state):
    if state["private_route"]:
        return "left"
    return "right"


builder = StateGraph(State)
builder.add_node("choose", choose)
builder.add_node("left", left)
builder.add_node("right", right)
builder.add_edge(START, "choose")
builder.add_conditional_edges("choose", route, {"left": "left", "right": "right"})
builder.add_edge("left", END)
builder.add_edge("right", END)
app = builder.compile()
