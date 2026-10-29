# Port spec: `wa-evaluator-optimizer` (pattern: evaluator-optimizer loop)

## 1. Source

- Repo/commit: `langchain-ai/docs` @ `5d83d5e690af84ed654a8d4320bf9969af28e39f`
- File: `docs/src/oss/langgraph/workflows-agents.mdx`, section "Evaluator-optimizer".
  - Python Graph API: lines 1522-1601
  - Python Functional API: lines 1604-1653
  - JS Graph/Functional: lines 1661-1797 (duplicates)
- Model: lines 35-47 of the same file (`ChatAnthropic(model="claude-sonnet-4-6")`).

## 2. Node graph

```
START -> llm_call_generator -> llm_call_evaluator --route_joke--> "Accepted": END
                ^                                            |
                +---------------- "Rejected + Feedback" -----+
```

## 3. Verbatim code and prompts

_Verbatim from `docs/src/oss/langgraph/workflows-agents.mdx` lines 1522-1601:_

```python
# Graph state
class State(TypedDict):
    joke: str
    topic: str
    feedback: str
    funny_or_not: str


# Schema for structured output to use in evaluation
class Feedback(BaseModel):
    grade: Literal["funny", "not funny"] = Field(
        description="Decide if the joke is funny or not.",
    )
    feedback: str = Field(
        description="If the joke is not funny, provide feedback on how to improve it.",
    )


# Augment the LLM with schema for structured output
evaluator = llm.with_structured_output(Feedback)


# Nodes
def llm_call_generator(state: State):
    """LLM generates a joke"""

    if state.get("feedback"):
        msg = llm.invoke(
            f"Write a joke about {state['topic']} but take into account the feedback: {state['feedback']}"
        )
    else:
        msg = llm.invoke(f"Write a joke about {state['topic']}")
    return {"joke": msg.content}


def llm_call_evaluator(state: State):
    """LLM evaluates the joke"""

    grade = evaluator.invoke(f"Grade the joke {state['joke']}")
    return {"funny_or_not": grade.grade, "feedback": grade.feedback}


# Conditional edge function to route back to joke generator or end based upon feedback from the evaluator
def route_joke(state: State):
    """Route back to joke generator or end based upon feedback from the evaluator"""

    if state["funny_or_not"] == "funny":
        return "Accepted"
    elif state["funny_or_not"] == "not funny":
        return "Rejected + Feedback"


# Build workflow
optimizer_builder = StateGraph(State)

# Add the nodes
optimizer_builder.add_node("llm_call_generator", llm_call_generator)
optimizer_builder.add_node("llm_call_evaluator", llm_call_evaluator)

# Add edges to connect nodes
optimizer_builder.add_edge(START, "llm_call_generator")
optimizer_builder.add_edge("llm_call_generator", "llm_call_evaluator")
optimizer_builder.add_conditional_edges(
    "llm_call_evaluator",
    route_joke,
    {  # Name returned by route_joke : Name of next node to visit
        "Accepted": END,
        "Rejected + Feedback": "llm_call_generator",
    },
)

# Compile the workflow
optimizer_workflow = optimizer_builder.compile()

# Show the workflow
display(Image(optimizer_workflow.get_graph().draw_mermaid_png()))

# Invoke
state = optimizer_workflow.invoke({"topic": "Cats"})
print(state["joke"])
```

_Verbatim from `docs/src/oss/langgraph/workflows-agents.mdx` lines 1604-1653:_

```python
# Schema for structured output to use in evaluation
class Feedback(BaseModel):
    grade: Literal["funny", "not funny"] = Field(
        description="Decide if the joke is funny or not.",
    )
    feedback: str = Field(
        description="If the joke is not funny, provide feedback on how to improve it.",
    )


# Augment the LLM with schema for structured output
evaluator = llm.with_structured_output(Feedback)


# Nodes
@task
def llm_call_generator(topic: str, feedback: Feedback):
    """LLM generates a joke"""
    if feedback:
        msg = llm.invoke(
            f"Write a joke about {topic} but take into account the feedback: {feedback}"
        )
    else:
        msg = llm.invoke(f"Write a joke about {topic}")
    return msg.content


@task
def llm_call_evaluator(joke: str):
    """LLM evaluates the joke"""
    feedback = evaluator.invoke(f"Grade the joke {joke}")
    return feedback


@entrypoint()
def optimizer_workflow(topic: str):
    feedback = None
    while True:
        joke = llm_call_generator(topic, feedback).result()
        feedback = llm_call_evaluator(joke).result()
        if feedback.grade == "funny":
            break

    return joke

# Invoke
stream = optimizer_workflow.stream_events("Cats", version="v3")
for snapshot in stream.values:
    print(snapshot)
    print("\n")
```

Prompts are single user strings:
- generator, first round: `f"Write a joke about {state['topic']}"`
- generator, later rounds: `f"Write a joke about {state['topic']} but take into account the feedback: {state['feedback']}"`
- evaluator: `f"Grade the joke {state['joke']}"`, sent through `llm.with_structured_output(Feedback)`

## 4. Routing condition

- `route_joke` (lines 1565-1571): `funny_or_not == "funny"` returns `"Accepted"` (END); `funny_or_not == "not funny"` returns `"Rejected + Feedback"` (back to the generator).
- Any other value returns `None`, which is not a key of the path map; the docs do not handle this case.
- Functional API: `while True: ... if feedback.grade == "funny": break` (lines 1641-1645).

## 5. Loop bound

- **Original: unbounded.** There is no iteration counter. Termination relies on the evaluator eventually answering "funny", or on LangGraph's `recursion_limit`.
  - `recursion_limit` is 10007 super-steps by default at langgraph 1.2.16 (`langgraph/libs/langgraph/langgraph/_internal/_config.py:32`). The docs say 1000 since 1.0.6 (`graph-api.mdx:1502`). Each round costs 2 super-steps.
  - The Functional API `while True` has no bound at all.
- **Proposed bound: N = 5 rounds (at most 10 LLM calls).** Justification:
  1. It must be finite for the DSL.
  2. It matches the order of magnitude of explicit bounds elsewhere in the same corpus: `max_iterations = 3` in `langgraph_code_assistant_mistral.ipynb:238`, `max_num_turns = 5` in `libs/cli/examples/graphs/storm.py:356`, `max_turns = 6` in `simulation_utils.py:88`.
  3. It is large enough that the bound should rarely bind if the evaluator accepts within a few rounds.
- Report the fraction of runs that hit N, and treat "hit bound" as its own observable class.

## 6. Structured output

`Feedback(BaseModel)`: `grade: Literal["funny", "not funny"]` (description "Decide if the joke is funny or not."), `feedback: str` ("If the joke is not funny, provide feedback on how to improve it.").

Emulation: keep the evaluator's user prompt verbatim and append a format instruction derived from the schema descriptions, asking for exactly:
```
grade: <funny|not funny>
feedback: <text>
```
Route with `contains(out, "grade: not funny")` -> reject, else `contains(out, "grade: funny")` -> accept. The "not funny" test must come first, because the substring "funny" occurs in both. The feedback is the text after `feedback:`. If the DSL has no extraction primitive, pass the whole evaluator output as `{feedback}`; that is a deviation that changes input tokens. Proposed `max_tokens`: 120 for the evaluator, 200 for the generator.

## 7. Secret attribute and expected leak

The number of rounds (= LLM calls / 2) reveals how many hidden jokes the hidden evaluator rejected, which correlates with the topic. Per-round generator input tokens grow with feedback length. Secret: the topic's category, with DBpedia labels as the proxy.

## 8. Port sketch

```
feedback = ""
repeat up to 5:
    joke = feedback == "" ? LLM([user: "Write a joke about {topic}"], 200)
                          : LLM([user: "Write a joke about {topic} but take into account the feedback: {feedback}"], 200)
    ev   = LLM([user: "Grade the joke {joke}" + FEEDBACK_FORMAT_SUFFIX], 120)
    if contains(ev, "grade: not funny"): feedback = after(ev, "feedback:")
    elif contains(ev, "grade: funny"):   break
    else:                                break      # original: undefined route
return joke
```

## 9. Deviations

1. A bound of N=5 is added (the original is unbounded).
2. Structured output is emulated with text plus a format suffix (no tool schema in the request).
3. In the original, `{feedback}` is the Pydantic field value. In the Python Functional API it is the whole `Feedback` object (line 1624 interpolates `{feedback}`, a `Feedback` instance, so its string form with both fields enters the prompt), while JS Functional uses `${params.feedback.feedback}` (line 1761). The original variants therefore send different prompts. The port follows the Graph API variant.
4. An undefined grade is mapped to stop (the original would raise on an unknown route key).
5. `max_tokens` is added and the model is changed.

## 10. Dataset

- **`fancyzhx/dbpedia_14`** (same as `wa-prompt-chaining`). Verified HTTP 200; `cc-by-sa-3.0`; 560k/70k.
  - Input: `title` -> `topic`. Secret: `label` (14 categories).
- The original demo topic is `"Cats"`.
