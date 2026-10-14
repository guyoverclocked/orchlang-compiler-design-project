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
def revise_node(state):
    draft = request(model="writer", template="revise", arguments=[state["draft"], state["question"]])
    return {"draft": draft}
def answer_node(state):
    answer = request(model="writer", template="answer", arguments=[state["draft"]])
    return {"answer": answer}
builder = StateGraph(State)
builder.add_node("draft", draft_node)
builder.add_node("revise", revise_node)
builder.add_node("answer", answer_node)
builder.add_edge(START, "draft")
builder.add_edge("draft", "revise")
builder.add_edge("revise", "answer")
builder.add_edge("answer", END)
app = builder.compile()
