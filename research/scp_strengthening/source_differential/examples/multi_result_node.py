"""Authored successful workflow for completed-state differential checks."""
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from integrations.langgraph.source_frontend.runtime import request, tokens
class State(TypedDict):
    question: str
    draft: str
    answer: str

def compose(state):
    draft = request(model="writer", template="draft", arguments=[state["question"], "café"])
    intermediate = request(model="writer", template="critique", arguments=[draft, "check"])
    answer = request(model="writer", template="answer", arguments=[intermediate, draft])
    return {"draft": draft, "answer": answer}
builder = StateGraph(State)
builder.add_node("compose", compose)
builder.add_edge(START, "compose")
builder.add_edge("compose", END)
app = builder.compile()
