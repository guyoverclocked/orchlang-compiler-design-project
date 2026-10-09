"""Actual LangGraph example: secret routing, then dependent calls."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from integrations.langgraph.source_frontend.runtime import request, tokens


class State(TypedDict):
    question: str
    private_route: bool
    public_mode: bool
    draft: str
    answer: str


def begin(state):
    return {}


def public_choice(state):
    return {}


def draft_left(state):
    draft = request(model="writer", template="draft-v1", arguments=[state["question"]])
    return {"draft": draft}


def draft_right(state):
    draft = request(model="writer", template="draft-v1", arguments=[state["question"]])
    return {"draft": draft}


def choose_private(state):
    if state["private_route"]:
        return "left"
    return "right"


def choose_public(state):
    if state["public_mode"]:
        return "public-a"
    return "public-b"


def finish_a(state):
    answer = request(model="writer", template="answer-v2",
                     arguments=[state["draft"], "suffix"])
    return {"answer": answer}


def finish_b(state):
    answer = request(model="writer", template="answer-v2",
                     arguments=[state["draft"], "suffix"])
    return {"answer": answer}


builder = StateGraph(State)
builder.add_node("begin", begin)
builder.add_node("draft-left", draft_left)
builder.add_node("draft-right", draft_right)
builder.add_node("public-choice", public_choice)
builder.add_node("finish-a", finish_a)
builder.add_node("finish-b", finish_b)
builder.add_edge(START, "begin")
builder.add_conditional_edges("begin", choose_private,
                              {"left": "draft-left", "right": "draft-right"})
builder.add_edge("draft-left", "public-choice")
builder.add_edge("draft-right", "public-choice")
builder.add_conditional_edges("public-choice", choose_public,
                              {"public-a": "finish-a", "public-b": "finish-b"})
builder.add_edge("finish-a", END)
builder.add_edge("finish-b", END)
app = builder.compile()
