"""Authored successful workflow for completed-state differential checks."""
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from integrations.langgraph.source_frontend.runtime import request, tokens
class State(TypedDict):
    question: str
    draft: str
    answer: str

def draft_node(state):
    draft = request(model="writer", template="draft", arguments=[state["question"]])
    return {"draft": draft}
def route(state):
    if tokens(state["draft"]) < 2:
        return "yes"
    return "no"
def answer_yes(state):
    answer = request(model="writer", template="answer-yes", arguments=[state["draft"]])
    return {"answer": answer}
def answer_no(state):
    answer = request(model="writer", template="answer-no", arguments=[state["draft"]])
    return {"answer": answer}
builder = StateGraph(State)
builder.add_node("draft", draft_node)
builder.add_node("yes", answer_yes)
builder.add_node("no", answer_no)
builder.add_edge(START, "draft")
builder.add_conditional_edges("draft", route, {"yes": "yes", "no": "no"})
builder.add_edge("yes", END)
builder.add_edge("no", END)
app = builder.compile()
